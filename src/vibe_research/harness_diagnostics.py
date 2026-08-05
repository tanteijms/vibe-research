from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any

from .intervention_replay import InterventionReplayWorkbench, TraceComparisonReport
from .schema import TraceEvent
from .transition_graph import TransitionGraph


JsonDict = dict[str, Any]

_ENVELOPE_KEYS = (
    "provider_fingerprint",
    "protocol_fingerprint",
    "policy_fingerprint",
    "tool_contract_fingerprint",
    "skill_manifest_fingerprint",
    "evidence_ledger_fingerprint",
    "evidence_claim_ids",
    "action_effect",
    "input_hash",
    "output_hash",
)

_SURFACE_BY_KEY = {
    "provider_fingerprint": "provider_capability",
    "protocol_fingerprint": "protocol_contract",
    "policy_fingerprint": "harness_policy",
    "tool_contract_fingerprint": "tool_contract",
    "skill_manifest_fingerprint": "skill_manifest",
    "evidence_ledger_fingerprint": "evidence_ledger",
    "evidence_claim_ids": "evidence_claim",
    "action_effect": "effect_classification",
    "input_hash": "planning_or_context_rendering",
    "output_hash": "tool_output_or_artifact",
}


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _completed_tool_events(events: list[TraceEvent]) -> list[TraceEvent]:
    return [event for event in events if event.kind == "tool_completed" and "tool" in event.data]


def _event_at_index(events: list[TraceEvent], index: int | None) -> TraceEvent | None:
    if index is None:
        return None
    completed = _completed_tool_events(events)
    if 0 <= index < len(completed):
        return completed[index]
    return None


def _event_unit_id(event: TraceEvent | None) -> str | None:
    return event.event_id if event is not None else None


def _trace_envelope(event: TraceEvent | None) -> JsonDict:
    if event is None:
        return {}
    envelope = event.data.get("trace_envelope")
    return dict(envelope) if isinstance(envelope, dict) else {}


@dataclass(frozen=True, slots=True)
class HarnessDiagnosisReport:
    """Replay divergence mapped back to transition graph and trace surfaces."""

    replay_passed: bool
    comparison: TraceComparisonReport
    divergence_unit_id: str | None
    divergence_label: str | None
    divergence_status: str | None
    cached_prefix_unit_ids: list[str] = field(default_factory=list)
    live_suffix_unit_ids: list[str] = field(default_factory=list)
    critical_transition_chain: list[str] = field(default_factory=list)
    critical_transition_subgraph: list[str] = field(default_factory=list)
    branch_points: list[str] = field(default_factory=list)
    fingerprint_drift: dict[str, JsonDict] = field(default_factory=dict)
    suspect_surfaces: list[str] = field(default_factory=list)
    affected_artifact_refs: list[str] = field(default_factory=list)
    repair_hints: list[str] = field(default_factory=list)
    graph_fingerprint: str = ""
    diagnosis_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return asdict(self)


class HarnessDiagnosticWorkbench:
    """HTIR/HarnessFix-style failure trajectory diagnosis for Harness x Hermes.

    The workbench does not attempt to repair a run by itself. It creates a
    compact evidence object that connects:

    - replay divergence: which completed tool boundary drifted first;
    - transition graph: which state-changing unit and critical chain is hit;
    - trace envelope: which harness surface likely changed.
    """

    def __init__(self, replay: InterventionReplayWorkbench | None = None):
        self.replay = replay or InterventionReplayWorkbench()

    def diagnose(
        self,
        baseline: list[TraceEvent],
        actual: list[TraceEvent],
        *,
        target_unit_id: str | None = None,
    ) -> HarnessDiagnosisReport:
        comparison = self.replay.compare(baseline, actual)
        graph = TransitionGraph.from_events(baseline)

        baseline_event = _event_at_index(baseline, comparison.divergence_index)
        actual_event = _event_at_index(actual, comparison.divergence_index)
        divergence_unit_id = target_unit_id or _event_unit_id(baseline_event) or _event_unit_id(actual_event)
        graph_target = divergence_unit_id if divergence_unit_id in graph.units else None
        transition_report = graph.diagnose(graph_target)
        divergence_unit = graph.units.get(divergence_unit_id) if divergence_unit_id else None

        completed = _completed_tool_events(baseline)
        cached_prefix_unit_ids = [
            event.event_id for event in completed[: comparison.common_prefix_count] if event.event_id
        ]
        live_suffix_unit_ids = [
            event.event_id for event in completed[comparison.common_prefix_count :] if event.event_id
        ]

        fingerprint_drift = self._fingerprint_drift(baseline_event, actual_event)
        suspect_surfaces = self._suspect_surfaces(comparison, fingerprint_drift)
        repair_hints = self._repair_hints(comparison, suspect_surfaces)
        affected_artifact_refs = sorted(
            set(
                _normalize_refs(baseline_event.data.get("artifact_refs") if baseline_event else None)
                + _normalize_refs(actual_event.data.get("artifact_refs") if actual_event else None)
                + (divergence_unit.evidence_refs if divergence_unit is not None else [])
            )
        )

        payload = {
            "comparison": comparison.to_dict(),
            "divergence_unit_id": divergence_unit_id,
            "critical_transition_chain": transition_report.critical_transition_chain,
            "fingerprint_drift": fingerprint_drift,
            "suspect_surfaces": suspect_surfaces,
            "graph_fingerprint": graph.fingerprint(),
        }

        return HarnessDiagnosisReport(
            replay_passed=comparison.divergence_index is None,
            comparison=comparison,
            divergence_unit_id=divergence_unit_id,
            divergence_label=divergence_unit.label if divergence_unit else None,
            divergence_status=divergence_unit.status if divergence_unit else None,
            cached_prefix_unit_ids=cached_prefix_unit_ids,
            live_suffix_unit_ids=live_suffix_unit_ids,
            critical_transition_chain=transition_report.critical_transition_chain,
            critical_transition_subgraph=transition_report.critical_transition_subgraph,
            branch_points=transition_report.branch_points,
            fingerprint_drift=fingerprint_drift,
            suspect_surfaces=suspect_surfaces,
            affected_artifact_refs=affected_artifact_refs,
            repair_hints=repair_hints,
            graph_fingerprint=graph.fingerprint(),
            diagnosis_fingerprint=_stable_hash(payload),
        )

    @staticmethod
    def _fingerprint_drift(baseline_event: TraceEvent | None, actual_event: TraceEvent | None) -> dict[str, JsonDict]:
        drift: dict[str, JsonDict] = {}

        for key in ("tool", "args_hash", "output_hash", "trace_envelope_fingerprint"):
            left = baseline_event.data.get(key) if baseline_event is not None else None
            right = actual_event.data.get(key) if actual_event is not None else None
            if left != right:
                drift[key] = {"baseline": left, "actual": right}

        baseline_envelope = _trace_envelope(baseline_event)
        actual_envelope = _trace_envelope(actual_event)
        if baseline_envelope or actual_envelope:
            for key in _ENVELOPE_KEYS:
                left = baseline_envelope.get(key)
                right = actual_envelope.get(key)
                if left != right:
                    drift[f"trace_envelope.{key}"] = {"baseline": left, "actual": right}

        return drift

    @staticmethod
    def _suspect_surfaces(
        comparison: TraceComparisonReport,
        fingerprint_drift: dict[str, JsonDict],
    ) -> list[str]:
        surfaces: set[str] = set()

        if comparison.divergence_reason == "args_hash differs":
            surfaces.add("planning_or_context_rendering")
        elif comparison.divergence_reason == "output_hash differs":
            surfaces.add("tool_output_or_artifact")
        elif comparison.divergence_reason == "trace length differs":
            surfaces.add("action_path_policy")
        elif comparison.divergence_reason == "trace_envelope_fingerprint differs":
            surfaces.add("trace_contract")

        for key in fingerprint_drift:
            bare_key = key.removeprefix("trace_envelope.")
            surface = _SURFACE_BY_KEY.get(bare_key)
            if surface is not None:
                surfaces.add(surface)

        return sorted(surfaces)

    @staticmethod
    def _repair_hints(comparison: TraceComparisonReport, suspect_surfaces: list[str]) -> list[str]:
        hints: list[str] = []

        if comparison.divergence_index is None:
            return ["no replay divergence detected; keep current harness fingerprints pinned"]

        if "provider_capability" in suspect_surfaces:
            hints.append("pin or re-validate the provider capability snapshot before resume")
        if "protocol_contract" in suspect_surfaces:
            hints.append("compare protocol/tool schema hashes and rerun service-discovery regression")
        if "harness_policy" in suspect_surfaces:
            hints.append("treat policy snapshot drift as a resume gate before continuing the run")
        if "tool_contract" in suspect_surfaces:
            hints.append("re-run the tool description quality gate and update compact/rich context policy")
        if "skill_manifest" in suspect_surfaces:
            hints.append("hold skill promotion until the manifest fingerprint passes replay regression")
        if "planning_or_context_rendering" in suspect_surfaces:
            hints.append("inspect context compaction and planner inputs before replaying the live suffix")
        if "tool_output_or_artifact" in suspect_surfaces:
            hints.append("re-capture the tool output/artifact snapshot and replay from the cached prefix")
        if "action_path_policy" in suspect_surfaces:
            hints.append("diff the completed action path and check missing/extra tool transitions")

        if not hints:
            hints.append("inspect the divergent transition unit and compare trace receipts")

        return hints


def _normalize_refs(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]
