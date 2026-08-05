from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any

from .schema import TraceEvent


JsonDict = dict[str, Any]

_COMPARISON_KEYS = ("tool", "args_hash", "output_hash", "trace_envelope_fingerprint")


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _completed_tool_events(events: list[TraceEvent]) -> list[TraceEvent]:
    return [event for event in events if event.kind == "tool_completed" and "tool" in event.data]


def _clone_event(event: TraceEvent, *, data_updates: JsonDict) -> TraceEvent:
    payload = dict(event.data)
    payload.update(data_updates)
    return TraceEvent(
        event_id=event.event_id,
        task_id=event.task_id,
        run_id=event.run_id,
        cursor=event.cursor,
        kind=event.kind,
        data=payload,
    )


def _difference_reason(left: TraceEvent, right: TraceEvent) -> str | None:
    for key in _COMPARISON_KEYS:
        if left.data.get(key) != right.data.get(key):
            return f"{key} differs"
    return None


def _common_prefix_report(left: list[TraceEvent], right: list[TraceEvent]) -> "TraceComparisonReport":
    limit = min(len(left), len(right))
    for index in range(limit):
        reason = _difference_reason(left[index], right[index])
        if reason is not None:
            return TraceComparisonReport(
                left_count=len(left),
                right_count=len(right),
                common_prefix_count=index,
                divergence_index=index,
                divergence_reason=reason,
                left_fingerprint=_stable_hash([event.to_dict() for event in left]),
                right_fingerprint=_stable_hash([event.to_dict() for event in right]),
            )

    if len(left) != len(right):
        return TraceComparisonReport(
            left_count=len(left),
            right_count=len(right),
            common_prefix_count=limit,
            divergence_index=limit,
            divergence_reason="trace length differs",
            left_fingerprint=_stable_hash([event.to_dict() for event in left]),
            right_fingerprint=_stable_hash([event.to_dict() for event in right]),
        )

    return TraceComparisonReport(
        left_count=len(left),
        right_count=len(right),
        common_prefix_count=limit,
        divergence_index=None,
        divergence_reason=None,
        left_fingerprint=_stable_hash([event.to_dict() for event in left]),
        right_fingerprint=_stable_hash([event.to_dict() for event in right]),
    )


@dataclass(frozen=True, slots=True)
class InterventionSpec:
    """A reproducible fault injection for AgentCheck-style replay."""

    fault_kind: str
    target_tool: str | None = None
    target_event_index: int | None = None
    response_overrides: JsonDict = field(default_factory=dict)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class TraceComparisonReport:
    """Prefix/suffix report for a pair of tool traces."""

    left_count: int
    right_count: int
    common_prefix_count: int
    divergence_index: int | None
    divergence_reason: str | None
    left_fingerprint: str
    right_fingerprint: str

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InterventionReplayReport:
    """AgentCheck-style reproduce/intervene/confirm report."""

    fault_spec: InterventionSpec
    injected_at_index: int | None
    baseline_report: TraceComparisonReport
    faulted_report: TraceComparisonReport
    mitigated_report: TraceComparisonReport | None
    cached_prefix_count: int
    live_suffix_count: int
    mitigation_effective: bool | None
    faulted_fingerprint: str
    mitigated_fingerprint: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return asdict(self)


class InterventionReplayWorkbench:
    """Fault-injection and mitigation replay for long-horizon agent traces."""

    def inject_fault(self, events: list[TraceEvent], fault_spec: InterventionSpec) -> list[TraceEvent]:
        injected: list[TraceEvent] = []
        injected_index: int | None = None

        for index, event in enumerate(events):
            if event.kind != "tool_completed" or "tool" not in event.data:
                injected.append(event)
                continue

            if fault_spec.target_event_index is not None and index != fault_spec.target_event_index:
                injected.append(event)
                continue

            if fault_spec.target_tool is not None and event.data.get("tool") != fault_spec.target_tool:
                injected.append(event)
                continue

            if injected_index is None:
                injected_index = index
                mutated_data = dict(event.data)
                mutated_data.update(fault_spec.response_overrides)
                mutated_data["intervention"] = {
                    "fault_kind": fault_spec.fault_kind,
                    "target_tool": fault_spec.target_tool,
                    "target_event_index": fault_spec.target_event_index,
                    "metadata": dict(fault_spec.metadata),
                }
                mutated_data["intervention_fingerprint"] = fault_spec.fingerprint()
                injected.append(_clone_event(event, data_updates=mutated_data))
                continue

            injected.append(event)

        if injected_index is None:
            return events

        return injected

    def compare(self, left: list[TraceEvent], right: list[TraceEvent]) -> TraceComparisonReport:
        return _common_prefix_report(_completed_tool_events(left), _completed_tool_events(right))

    def evaluate(
        self,
        baseline: list[TraceEvent],
        fault_spec: InterventionSpec,
        mitigated: list[TraceEvent] | None = None,
    ) -> InterventionReplayReport:
        faulted = self.inject_fault(baseline, fault_spec)
        baseline_report = self.compare(baseline, baseline)
        faulted_report = self.compare(baseline, faulted)
        mitigated_report = self.compare(baseline, mitigated) if mitigated is not None else None

        mitigation_effective: bool | None = None
        mitigated_fingerprint = None
        notes = [
            "matching tool calls are replayed from cache until the first divergence",
        ]

        if faulted_report.divergence_index is None:
            notes.append("faulted trace still matches baseline")
        else:
            notes.append(f"first divergence at tool event {faulted_report.divergence_index}")

        if mitigated_report is not None:
            mitigated_fingerprint = mitigated_report.right_fingerprint
            mitigation_effective = (
                mitigated_report.divergence_index is None
                or (
                    faulted_report.divergence_index is not None
                    and mitigated_report.common_prefix_count > faulted_report.common_prefix_count
                )
            )
            if mitigation_effective:
                notes.append("mitigation recovered more of the baseline prefix")
            else:
                notes.append("mitigation did not improve prefix recovery")

        return InterventionReplayReport(
            fault_spec=fault_spec,
            injected_at_index=faulted_report.divergence_index,
            baseline_report=baseline_report,
            faulted_report=faulted_report,
            mitigated_report=mitigated_report,
            cached_prefix_count=faulted_report.common_prefix_count,
            live_suffix_count=max(faulted_report.right_count - faulted_report.common_prefix_count, 0),
            mitigation_effective=mitigation_effective,
            faulted_fingerprint=faulted_report.right_fingerprint,
            mitigated_fingerprint=mitigated_fingerprint,
            notes=notes,
        )
