from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any

from .evidence_ledger import EvidenceLedger
from .obligation_audit import AuditLink, AuditRelation, Obligation, ObligationAuditMap, ObligationAuditReport, ObligationStatus
from .research_session import ResearchPhaseGate, ResearchSession, ResearchSessionReport, ResearchSessionVerifier
from .transition_graph import TransitionGraph


JsonDict = dict[str, Any]


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _phase_gate_for(phase: str, phase_gates: list[ResearchPhaseGate]) -> ResearchPhaseGate | None:
    for gate in phase_gates:
        if gate.phase == phase:
            return gate
    return None


def _find_transition_unit_id(session: ResearchSession, graph: TransitionGraph, gate: ResearchPhaseGate) -> str | None:
    if session.transition_unit_ids:
        for unit_id in reversed(session.transition_unit_ids):
            if unit_id in graph.units:
                return unit_id
        return None

    if gate.required_transition_labels:
        required = set(gate.required_transition_labels)
        for unit_id in reversed(graph._order):
            unit = graph.units[unit_id]
            if unit.label in required:
                return unit_id

    return None


def _evidence_refs_for(session: ResearchSession, gate: ResearchPhaseGate) -> list[str]:
    refs: list[str] = []
    refs.extend(session.evidence_refs)
    refs.extend(ref.uri for ref in session.artifact_refs)
    refs.extend(session.validation_receipt_refs)
    refs.extend(session.review_refs)
    refs.extend(gate.required_evidence_refs)
    refs.extend(f"claim://{claim_id}" for claim_id in gate.required_evidence_claim_ids)
    return _dedupe(refs)


@dataclass(frozen=True, slots=True)
class ResearchSessionAuditBridgeReport:
    """Composite report that binds a research session gate to an obligation audit."""

    session_report: ResearchSessionReport
    obligation_report: ObligationAuditReport
    phase: str
    actor: str
    obligation_id: str
    transition_unit_id: str | None
    bridge_evidence_refs: list[str] = field(default_factory=list)
    bridge_obligation_ids: list[str] = field(default_factory=list)
    ready_for_phase_exit: bool = False
    sound: bool = False
    stable: bool = False
    warnings: list[str] = field(default_factory=list)
    bridge_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return asdict(self)


class ResearchSessionAuditBridge:
    """Connects a typed research session report to ObligationAuditMap."""

    def evaluate(
        self,
        session: ResearchSession,
        graph: TransitionGraph,
        *,
        phase_gates: list[ResearchPhaseGate],
        evidence_ledger: EvidenceLedger | None = None,
        phase_actors: dict[str, str] | None = None,
        candidate_actor_scores: dict[str, dict[str, float]] | None = None,
        assignment_stability_margin: float = 0.05,
    ) -> ResearchSessionAuditBridgeReport:
        session_report = ResearchSessionVerifier().evaluate(
            session,
            phase_gates=phase_gates,
            evidence_ledger=evidence_ledger,
        )
        gate = _phase_gate_for(session.current_phase, phase_gates)
        if gate is None:
            raise ValueError(f"missing phase gate for current phase: {session.current_phase}")

        actor = (phase_actors or {}).get(
            session.current_phase,
            str(session.metadata.get("phase_actor") or session.metadata.get("default_actor") or "researcher"),
        )
        actor_scores = (candidate_actor_scores or {}).get(session.current_phase, {})
        obligation_id = f"{session.session_id}:{session.current_phase}:phase_gate"
        transition_unit_id = _find_transition_unit_id(session, graph, gate)
        bridge_evidence_refs = _evidence_refs_for(session, gate)

        obligation_status = ObligationStatus.SATISFIED if session_report.phase_gate_passed else ObligationStatus.OPEN
        obligation = Obligation(
            obligation_id=obligation_id,
            actor=actor,
            description=f"Satisfy {session.current_phase} gate for research session {session.session_id}",
            status=obligation_status,
            required_transition_labels=list(gate.required_transition_labels),
            due_before_transition_id=transition_unit_id,
            evidence_required=True,
            candidate_actor_scores=dict(actor_scores),
            metadata={
                "session_id": session.session_id,
                "phase": session.current_phase,
                "gate_fingerprint": gate.fingerprint(),
                "session_fingerprint": session.fingerprint(),
            },
        )

        links: list[AuditLink] = []
        if transition_unit_id is not None:
            relation = AuditRelation.SATISFIES if session_report.phase_gate_passed else AuditRelation.SUPPORTS
            links.append(
                AuditLink(
                    obligation_id=obligation_id,
                    transition_unit_id=transition_unit_id,
                    relation=relation,
                    evidence_refs=bridge_evidence_refs,
                    metadata={
                        "phase": session.current_phase,
                        "session_report_fingerprint": session_report.report_fingerprint,
                        "gate_fingerprint": gate.fingerprint(),
                    },
                )
            )

        obligation_map = ObligationAuditMap(obligations=[obligation], links=links)
        obligation_report = obligation_map.evaluate(graph, assignment_stability_margin=assignment_stability_margin)
        bridge_payload = {
            "session_report": session_report.to_dict(),
            "obligation_report": obligation_report.to_dict(),
            "phase": session.current_phase,
            "actor": actor,
            "obligation_id": obligation_id,
            "transition_unit_id": transition_unit_id,
            "bridge_evidence_refs": bridge_evidence_refs,
            "bridge_obligation_ids": [obligation_id],
        }

        return ResearchSessionAuditBridgeReport(
            session_report=session_report,
            obligation_report=obligation_report,
            phase=session.current_phase,
            actor=actor,
            obligation_id=obligation_id,
            transition_unit_id=transition_unit_id,
            bridge_evidence_refs=bridge_evidence_refs,
            bridge_obligation_ids=[obligation_id],
            ready_for_phase_exit=session_report.ready_for_phase_exit and obligation_report.sound and obligation_report.stable,
            sound=obligation_report.sound,
            stable=obligation_report.stable,
            warnings=list(session_report.warnings) + list(obligation_report.assignment_warnings),
            bridge_fingerprint=_stable_hash(bridge_payload),
        )
