from __future__ import annotations

from dataclasses import dataclass

from .path_policy import ActionPathPolicy
from .schema import TraceEvent
from .transition_graph import TransitionGraph, TransitionGraphReport


@dataclass(frozen=True, slots=True)
class ReplayReport:
    passed: bool
    failures: list[str]


class ReplayVerifier:
    """Checks that a replayed run preserves audited tool boundaries."""

    def compare(self, expected: list[TraceEvent], actual: list[TraceEvent]) -> ReplayReport:
        expected_completed = [event for event in expected if event.kind == "tool_completed"]
        actual_completed = [event for event in actual if event.kind == "tool_completed"]
        failures: list[str] = []

        if len(expected_completed) != len(actual_completed):
            failures.append(f"completed tool count differs: {len(expected_completed)} != {len(actual_completed)}")

        for index, (left, right) in enumerate(zip(expected_completed, actual_completed)):
            for key in ("tool", "args_hash", "output_hash", "trace_envelope_fingerprint"):
                if left.data.get(key) != right.data.get(key):
                    failures.append(f"event {index} {key} differs")
            failures.extend(self._compare_trace_envelopes(index, left, right))

        return ReplayReport(passed=not failures, failures=failures)

    def _compare_trace_envelopes(self, index: int, left: TraceEvent, right: TraceEvent) -> list[str]:
        left_envelope = left.data.get("trace_envelope")
        right_envelope = right.data.get("trace_envelope")
        if left_envelope is None and right_envelope is None:
            return []
        if left_envelope is None or right_envelope is None:
            return [f"event {index} trace envelope presence differs"]

        failures: list[str] = []
        for key in (
            "schema_version",
            "boundary",
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
        ):
            if left_envelope.get(key) != right_envelope.get(key):
                failures.append(f"event {index} trace_envelope.{key} differs")
        return failures


@dataclass(frozen=True, slots=True)
class PathVerificationReport:
    passed: bool
    failures: list[str]
    action_path: list[str]


class PathVerifier:
    """Checks runtime action paths against governance policies."""

    def compare(self, events: list[TraceEvent], policy: ActionPathPolicy) -> PathVerificationReport:
        action_path = [event.data["tool"] for event in events if event.kind == "tool_completed" and "tool" in event.data]
        failures = policy.check(action_path)
        return PathVerificationReport(passed=not failures, failures=failures, action_path=action_path)


class TransitionVerifier:
    """Diagnoses the critical transition chain of a trace."""

    def compare(self, events: list[TraceEvent], *, target_unit_id: str | None = None) -> TransitionGraphReport:
        return TransitionGraph.from_events(events).diagnose(target_unit_id=target_unit_id)
