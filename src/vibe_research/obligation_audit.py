from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any

from .transition_graph import TransitionGraph


JsonDict = dict[str, Any]


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


class ObligationStatus:
    OPEN = "open"
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    WAIVED = "waived"


class AuditRelation:
    SATISFIES = "satisfies"
    VIOLATES = "violates"
    SUPPORTS = "supports"
    WAIVES = "waives"


@dataclass(frozen=True, slots=True)
class Obligation:
    """A responsibility that an actor must satisfy during an agent run."""

    obligation_id: str
    actor: str
    description: str
    status: str = ObligationStatus.OPEN
    required_transition_labels: list[str] = field(default_factory=list)
    due_before_transition_id: str | None = None
    evidence_required: bool = True
    candidate_actor_scores: dict[str, float] = field(default_factory=dict)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class AuditLink:
    """A link from an obligation to transition evidence."""

    obligation_id: str
    transition_unit_id: str
    relation: str = AuditRelation.SATISFIES
    evidence_refs: list[str] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class ObligationAuditReport:
    """Audit result for obligation soundness and assignment stability."""

    sound: bool
    stable: bool
    open_obligation_ids: list[str] = field(default_factory=list)
    violated_obligation_ids: list[str] = field(default_factory=list)
    unsupported_obligation_ids: list[str] = field(default_factory=list)
    assignment_warnings: list[str] = field(default_factory=list)
    actor_load: dict[str, int] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    audit_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return asdict(self)


class ObligationAuditMap:
    """iCORE-inspired obligation graph and audit map for transition graphs."""

    def __init__(
        self,
        *,
        obligations: list[Obligation] | None = None,
        links: list[AuditLink] | None = None,
    ):
        self.obligations: dict[str, Obligation] = {item.obligation_id: item for item in obligations or []}
        self.links: list[AuditLink] = list(links or [])

    def add_obligation(self, obligation: Obligation) -> None:
        if obligation.obligation_id in self.obligations:
            raise ValueError(f"duplicate obligation: {obligation.obligation_id}")
        self.obligations[obligation.obligation_id] = obligation

    def add_link(self, link: AuditLink) -> None:
        if link.obligation_id not in self.obligations:
            raise KeyError(f"unknown obligation: {link.obligation_id}")
        self.links.append(link)

    def links_for(self, obligation_id: str, *, relation: str | None = None) -> list[AuditLink]:
        links = [link for link in self.links if link.obligation_id == obligation_id]
        if relation is not None:
            links = [link for link in links if link.relation == relation]
        return links

    def evaluate(
        self,
        graph: TransitionGraph,
        *,
        assignment_stability_margin: float = 0.05,
    ) -> ObligationAuditReport:
        failures: list[str] = []
        open_ids: list[str] = []
        violated_ids: list[str] = []
        unsupported_ids: list[str] = []
        assignment_warnings: list[str] = []
        actor_load: dict[str, int] = {}

        for obligation in self.obligations.values():
            actor_load[obligation.actor] = actor_load.get(obligation.actor, 0) + 1

            if obligation.status == ObligationStatus.OPEN:
                open_ids.append(obligation.obligation_id)
                failures.append(f"obligation still open: {obligation.obligation_id}")
            if obligation.status == ObligationStatus.VIOLATED:
                violated_ids.append(obligation.obligation_id)
                failures.append(f"obligation violated: {obligation.obligation_id}")

            supporting_links = self.links_for(obligation.obligation_id, relation=AuditRelation.SATISFIES)
            if obligation.status == ObligationStatus.SATISFIED:
                link_failures = self._support_failures(obligation, supporting_links, graph)
                if link_failures:
                    unsupported_ids.append(obligation.obligation_id)
                    failures.extend(link_failures)

            warning = self._assignment_warning(obligation, margin=assignment_stability_margin)
            if warning is not None:
                assignment_warnings.append(warning)

        return ObligationAuditReport(
            sound=not failures,
            stable=not assignment_warnings,
            open_obligation_ids=open_ids,
            violated_obligation_ids=violated_ids,
            unsupported_obligation_ids=unsupported_ids,
            assignment_warnings=assignment_warnings,
            actor_load=dict(sorted(actor_load.items())),
            failures=failures,
            audit_fingerprint=self.fingerprint(),
        )

    def to_dict(self) -> JsonDict:
        return {
            "obligations": [obligation.to_dict() for obligation in sorted(self.obligations.values(), key=lambda item: item.obligation_id)],
            "links": [link.to_dict() for link in self.links],
        }

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def _support_failures(
        self,
        obligation: Obligation,
        supporting_links: list[AuditLink],
        graph: TransitionGraph,
    ) -> list[str]:
        failures: list[str] = []
        if not supporting_links:
            return [f"satisfied obligation has no satisfying transition: {obligation.obligation_id}"]

        for link in supporting_links:
            if link.transition_unit_id not in graph.units:
                failures.append(
                    f"audit link targets missing transition: {obligation.obligation_id} -> {link.transition_unit_id}"
                )
                continue

            unit = graph.units[link.transition_unit_id]
            if obligation.required_transition_labels and unit.label not in obligation.required_transition_labels:
                failures.append(
                    f"audit link label mismatch: {obligation.obligation_id} requires "
                    f"{', '.join(obligation.required_transition_labels)} got {unit.label}"
                )

            if obligation.evidence_required and not (link.evidence_refs or unit.evidence_refs):
                failures.append(f"satisfied obligation lacks evidence refs: {obligation.obligation_id}")

            if obligation.due_before_transition_id is not None:
                due = graph.units.get(obligation.due_before_transition_id)
                if due is None:
                    failures.append(
                        f"obligation due transition missing: {obligation.obligation_id} -> {obligation.due_before_transition_id}"
                    )
                elif unit.sequence_index > due.sequence_index:
                    failures.append(
                        f"obligation satisfied after due transition: {obligation.obligation_id}"
                    )

        return failures

    @staticmethod
    def _assignment_warning(obligation: Obligation, *, margin: float) -> str | None:
        if not obligation.candidate_actor_scores:
            return None

        assigned_score = obligation.candidate_actor_scores.get(obligation.actor)
        if assigned_score is None:
            return f"assigned actor has no score: {obligation.obligation_id}:{obligation.actor}"

        best_actor, best_score = max(
            obligation.candidate_actor_scores.items(),
            key=lambda item: (item[1], item[0]),
        )
        if best_actor != obligation.actor and best_score > assigned_score + margin:
            return (
                f"assignment unstable: {obligation.obligation_id} assigned {obligation.actor} "
                f"({assigned_score}) but {best_actor} scores {best_score}"
            )
        return None
