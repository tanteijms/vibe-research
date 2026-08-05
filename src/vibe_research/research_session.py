from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from .evidence_ledger import EvidenceLedger
from .schema import ArtifactRef, RuntimeState


JsonDict = dict[str, Any]


class ResearchPhase:
    INTAKE = "intake"
    PAPER_SCAN = "paper_scan"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT_PLAN = "experiment_plan"
    EXPERIMENT_RUN = "experiment_run"
    ANALYSIS = "analysis"
    REVIEW = "review"
    WRITEUP = "writeup"
    ARCHIVE = "archive"


ALLOWED_PHASE_TRANSITIONS: dict[str, set[str]] = {
    ResearchPhase.INTAKE: {ResearchPhase.PAPER_SCAN, ResearchPhase.HYPOTHESIS},
    ResearchPhase.PAPER_SCAN: {ResearchPhase.HYPOTHESIS, ResearchPhase.EXPERIMENT_PLAN},
    ResearchPhase.HYPOTHESIS: {ResearchPhase.EXPERIMENT_PLAN, ResearchPhase.PAPER_SCAN},
    ResearchPhase.EXPERIMENT_PLAN: {ResearchPhase.EXPERIMENT_RUN, ResearchPhase.PAPER_SCAN},
    ResearchPhase.EXPERIMENT_RUN: {ResearchPhase.ANALYSIS, ResearchPhase.EXPERIMENT_PLAN},
    ResearchPhase.ANALYSIS: {ResearchPhase.REVIEW, ResearchPhase.EXPERIMENT_RUN},
    ResearchPhase.REVIEW: {ResearchPhase.WRITEUP, ResearchPhase.EXPERIMENT_PLAN, ResearchPhase.ANALYSIS},
    ResearchPhase.WRITEUP: {ResearchPhase.ARCHIVE, ResearchPhase.REVIEW},
    ResearchPhase.ARCHIVE: set(),
}


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _normalize_refs(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


@dataclass(frozen=True, slots=True)
class ResearchPhaseGate:
    """Evidence requirements for a typed research phase."""

    phase: str
    required_artifact_kinds: list[str] = field(default_factory=list)
    required_transition_labels: list[str] = field(default_factory=list)
    required_memory_record_ids: list[str] = field(default_factory=list)
    required_evidence_refs: list[str] = field(default_factory=list)
    required_evidence_claim_ids: list[str] = field(default_factory=list)
    forbidden_evidence_labels: list[str] = field(default_factory=list)
    require_validation_receipt: bool = False
    require_review_ref: bool = False
    description: str = ""
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(slots=True)
class ResearchSession:
    """A typed scientific-workflow state object carried by Hermes."""

    session_id: str
    runtime_task_id: str
    goal: str
    current_phase: str = ResearchPhase.INTAKE
    phase_history: list[str] = field(default_factory=lambda: [ResearchPhase.INTAKE])
    artifact_refs: list[ArtifactRef] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    transition_unit_ids: list[str] = field(default_factory=list)
    transition_labels: list[str] = field(default_factory=list)
    memory_record_ids: list[str] = field(default_factory=list)
    validation_receipt_refs: list[str] = field(default_factory=list)
    review_refs: list[str] = field(default_factory=list)
    policy_snapshot_hash: str | None = None
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        data["artifact_refs"] = [asdict(ref) for ref in self.artifact_refs]
        return data

    @classmethod
    def from_dict(cls, data: JsonDict) -> "ResearchSession":
        payload = dict(data)
        payload["artifact_refs"] = [ArtifactRef(**item) for item in payload.get("artifact_refs", [])]
        return cls(**payload)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def advance_to(
        self,
        phase: str,
        *,
        artifact_refs: list[ArtifactRef] | None = None,
        evidence_refs: list[str] | None = None,
        transition_unit_ids: list[str] | None = None,
        transition_labels: list[str] | None = None,
        memory_record_ids: list[str] | None = None,
        validation_receipt_refs: list[str] | None = None,
        review_refs: list[str] | None = None,
        metadata: JsonDict | None = None,
        strict: bool = True,
    ) -> "ResearchSession":
        if phase != self.current_phase:
            allowed = ALLOWED_PHASE_TRANSITIONS.get(self.current_phase, set())
            if strict and phase not in allowed:
                raise ValueError(f"invalid research phase transition: {self.current_phase} -> {phase}")
            self.current_phase = phase
            self.phase_history.append(phase)

        self.artifact_refs.extend(artifact_refs or [])
        self.evidence_refs = _dedupe(self.evidence_refs + list(evidence_refs or []))
        self.transition_unit_ids = _dedupe(self.transition_unit_ids + list(transition_unit_ids or []))
        self.transition_labels = _dedupe(self.transition_labels + list(transition_labels or []))
        self.memory_record_ids = _dedupe(self.memory_record_ids + list(memory_record_ids or []))
        self.validation_receipt_refs = _dedupe(self.validation_receipt_refs + list(validation_receipt_refs or []))
        self.review_refs = _dedupe(self.review_refs + list(review_refs or []))
        if metadata:
            self.metadata.update(metadata)
        return self


@dataclass(frozen=True, slots=True)
class ResearchSessionReport:
    """Phase-path and evidence-gate report for a research session."""

    session_id: str
    current_phase: str
    phase_path_valid: bool
    phase_gate_passed: bool
    ready_for_phase_exit: bool
    missing_artifact_kinds: list[str] = field(default_factory=list)
    missing_transition_labels: list[str] = field(default_factory=list)
    missing_memory_record_ids: list[str] = field(default_factory=list)
    missing_evidence_refs: list[str] = field(default_factory=list)
    missing_evidence_claim_ids: list[str] = field(default_factory=list)
    unsupported_evidence_claim_ids: list[str] = field(default_factory=list)
    missing_validation_receipt: bool = False
    missing_review_ref: bool = False
    evidence_ledger_sound: bool | None = None
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifact_kinds: list[str] = field(default_factory=list)
    phase_history: list[str] = field(default_factory=list)
    session_fingerprint: str = ""
    gate_fingerprint: str | None = None
    report_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return asdict(self)


class ResearchSessionVerifier:
    """Checks a typed research session against phase topology and evidence gates."""

    def evaluate(
        self,
        session: ResearchSession,
        *,
        phase_gates: list[ResearchPhaseGate] | None = None,
        evidence_ledger: EvidenceLedger | None = None,
    ) -> ResearchSessionReport:
        failures: list[str] = []
        warnings: list[str] = []
        phase_path_failures = self._phase_path_failures(session.phase_history)
        failures.extend(phase_path_failures)

        gate = self._select_gate(session.current_phase, phase_gates or [])
        artifact_kinds = [ref.kind for ref in session.artifact_refs]
        missing_artifact_kinds: list[str] = []
        missing_transition_labels: list[str] = []
        missing_memory_record_ids: list[str] = []
        missing_evidence_refs: list[str] = []
        missing_evidence_claim_ids: list[str] = []
        unsupported_evidence_claim_ids: list[str] = []
        missing_validation_receipt = False
        missing_review_ref = False
        evidence_ledger_sound: bool | None = None

        if gate is not None:
            missing_artifact_kinds = [
                kind for kind in gate.required_artifact_kinds if kind not in artifact_kinds
            ]
            missing_transition_labels = [
                label for label in gate.required_transition_labels if label not in session.transition_labels
            ]
            missing_memory_record_ids = [
                record_id for record_id in gate.required_memory_record_ids if record_id not in session.memory_record_ids
            ]
            missing_evidence_refs = [
                ref for ref in gate.required_evidence_refs if ref not in session.evidence_refs
            ]
            if gate.required_evidence_claim_ids:
                if evidence_ledger is None:
                    evidence_ledger_sound = False
                    missing_evidence_claim_ids = list(gate.required_evidence_claim_ids)
                    failures.append(f"missing evidence ledger for {gate.phase}")
                else:
                    evidence_report = evidence_ledger.evaluate(
                        required_claim_ids=gate.required_evidence_claim_ids,
                        forbidden_evidence_labels=gate.forbidden_evidence_labels,
                    )
                    evidence_ledger_sound = evidence_report.sound
                    missing_evidence_claim_ids = list(evidence_report.missing_required_claim_ids)
                    unsupported_evidence_claim_ids = list(evidence_report.unsupported_claim_ids)
                    failures.extend(f"evidence ledger: {failure}" for failure in evidence_report.failures)
            missing_validation_receipt = gate.require_validation_receipt and not session.validation_receipt_refs
            missing_review_ref = gate.require_review_ref and not session.review_refs

            for kind in missing_artifact_kinds:
                failures.append(f"missing required artifact kind for {gate.phase}: {kind}")
            for label in missing_transition_labels:
                failures.append(f"missing required transition label for {gate.phase}: {label}")
            for record_id in missing_memory_record_ids:
                failures.append(f"missing required memory record for {gate.phase}: {record_id}")
            for ref in missing_evidence_refs:
                failures.append(f"missing required evidence ref for {gate.phase}: {ref}")
            for claim_id in missing_evidence_claim_ids:
                failures.append(f"missing required evidence claim for {gate.phase}: {claim_id}")
            for claim_id in unsupported_evidence_claim_ids:
                if claim_id not in set(missing_evidence_claim_ids):
                    failures.append(f"unsupported evidence claim for {gate.phase}: {claim_id}")
            if missing_validation_receipt:
                failures.append(f"missing validation receipt for {gate.phase}")
            if missing_review_ref:
                failures.append(f"missing review ref for {gate.phase}")
        else:
            warnings.append(f"no phase gate configured for {session.current_phase}")

        if not session.policy_snapshot_hash:
            warnings.append("research session has no policy snapshot hash")
        if not session.evidence_refs:
            warnings.append("research session has no evidence refs")

        gate_fingerprint = gate.fingerprint() if gate is not None else None
        phase_path_valid = not phase_path_failures
        phase_gate_passed = not failures
        report_payload = {
            "session_id": session.session_id,
            "current_phase": session.current_phase,
            "phase_path_valid": phase_path_valid,
            "phase_gate_passed": phase_gate_passed,
            "missing_artifact_kinds": missing_artifact_kinds,
            "missing_transition_labels": missing_transition_labels,
            "missing_memory_record_ids": missing_memory_record_ids,
            "missing_evidence_refs": missing_evidence_refs,
            "missing_evidence_claim_ids": missing_evidence_claim_ids,
            "unsupported_evidence_claim_ids": unsupported_evidence_claim_ids,
            "evidence_ledger_sound": evidence_ledger_sound,
            "gate_fingerprint": gate_fingerprint,
            "session_fingerprint": session.fingerprint(),
        }

        return ResearchSessionReport(
            session_id=session.session_id,
            current_phase=session.current_phase,
            phase_path_valid=phase_path_valid,
            phase_gate_passed=phase_gate_passed,
            ready_for_phase_exit=phase_path_valid and phase_gate_passed,
            missing_artifact_kinds=missing_artifact_kinds,
            missing_transition_labels=missing_transition_labels,
            missing_memory_record_ids=missing_memory_record_ids,
            missing_evidence_refs=missing_evidence_refs,
            missing_evidence_claim_ids=missing_evidence_claim_ids,
            unsupported_evidence_claim_ids=unsupported_evidence_claim_ids,
            missing_validation_receipt=missing_validation_receipt,
            missing_review_ref=missing_review_ref,
            evidence_ledger_sound=evidence_ledger_sound,
            failures=failures,
            warnings=warnings,
            artifact_kinds=artifact_kinds,
            phase_history=list(session.phase_history),
            session_fingerprint=session.fingerprint(),
            gate_fingerprint=gate_fingerprint,
            report_fingerprint=_stable_hash(report_payload),
        )

    @staticmethod
    def _select_gate(phase: str, gates: list[ResearchPhaseGate]) -> ResearchPhaseGate | None:
        for gate in gates:
            if gate.phase == phase:
                return gate
        return None

    @staticmethod
    def _phase_path_failures(phase_history: list[str]) -> list[str]:
        if not phase_history:
            return ["research session has empty phase history"]

        failures: list[str] = []
        if phase_history[0] != ResearchPhase.INTAKE:
            failures.append(f"phase history must start at intake: {phase_history[0]}")

        for left, right in zip(phase_history, phase_history[1:]):
            if right == left:
                continue
            allowed = ALLOWED_PHASE_TRANSITIONS.get(left)
            if allowed is None:
                failures.append(f"unknown research phase: {left}")
                continue
            if right not in allowed:
                failures.append(f"invalid research phase transition: {left} -> {right}")
        if phase_history[-1] not in ALLOWED_PHASE_TRANSITIONS:
            failures.append(f"unknown research phase: {phase_history[-1]}")
        return failures


def research_session_from_state(state: RuntimeState, *, current_phase: str | None = None) -> ResearchSession:
    raw = state.metadata.get("research_session")
    if isinstance(raw, ResearchSession):
        return raw
    if isinstance(raw, dict):
        return ResearchSession.from_dict(raw)

    selected_phase = current_phase or str(state.metadata.get("research_phase") or ResearchPhase.INTAKE)
    history = state.metadata.get("research_phase_history")
    phase_history = list(history) if isinstance(history, list) and history else [selected_phase]
    if phase_history[0] != ResearchPhase.INTAKE:
        phase_history.insert(0, ResearchPhase.INTAKE)

    return ResearchSession(
        session_id=f"research_{uuid4().hex[:12]}",
        runtime_task_id=state.task_id,
        goal=state.goal,
        current_phase=selected_phase,
        phase_history=phase_history,
        artifact_refs=list(state.artifact_refs),
        evidence_refs=_normalize_refs(state.metadata.get("evidence_refs")),
        transition_unit_ids=_normalize_refs(state.metadata.get("transition_unit_ids")),
        transition_labels=_normalize_refs(state.metadata.get("transition_labels")),
        memory_record_ids=_normalize_refs(state.metadata.get("memory_record_ids")),
        validation_receipt_refs=_normalize_refs(state.metadata.get("validation_receipt_refs")),
        review_refs=_normalize_refs(state.metadata.get("review_refs")),
        policy_snapshot_hash=_stable_hash(state.policy_snapshot) if state.policy_snapshot else None,
        metadata={"source": "runtime_state"},
    )
