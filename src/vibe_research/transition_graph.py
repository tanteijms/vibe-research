from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any

from .schema import TraceEvent


JsonDict = dict[str, Any]


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


def _transition_phase(kind: str) -> str:
    if kind in {"tool_completed", "tool_failed", "tool_blocked", "tool_paused", "tool_started"}:
        return "action"
    if kind in {"approval", "tool_approved", "tool_denied"}:
        return "feedback"
    if kind == "checkpoint":
        return "checkpoint"
    return "observation"


def _transition_status(event: TraceEvent) -> str:
    if event.kind in {"tool_failed", "tool_blocked"}:
        return "failed"
    if event.kind == "tool_paused":
        return "paused"
    if event.kind == "tool_completed":
        return "completed"
    if event.kind == "checkpoint":
        return "checkpointed"
    if event.kind in {"approval", "tool_approved"}:
        return "approved"
    if event.kind == "tool_denied":
        return "denied"
    return "observed"


def _event_label(event: TraceEvent) -> str:
    return str(event.data.get("tool") or event.data.get("reason") or event.kind)


def _event_actor(event: TraceEvent) -> str:
    return str(event.data.get("actor") or event.data.get("subject") or "agent")


def _event_evidence_refs(event: TraceEvent) -> list[str]:
    refs: list[str] = []
    for key in ("artifact_refs", "evidence_refs", "source_refs"):
        refs.extend(_normalize_refs(event.data.get(key)))
    return sorted(set(refs))


@dataclass(frozen=True, slots=True)
class TransitionUnit:
    """A state-changing slice of agent execution."""

    unit_id: str
    event_id: str
    kind: str
    phase: str
    status: str
    label: str
    actor: str
    sequence_index: int
    dependency_ids: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class TransitionEdge:
    """A directed relation between transition units."""

    source_unit_id: str
    target_unit_id: str
    relation: str = "dependency"
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TransitionGraphReport:
    """Critical subtrajectory diagnosis for an execution graph."""

    target_unit_id: str | None
    unit_count: int
    edge_count: int
    critical_transition_chain: list[str]
    critical_transition_subgraph: list[str]
    branch_points: list[str]
    root_unit_ids: list[str]
    leaf_unit_ids: list[str]
    target_status: str | None
    target_label: str | None
    graph_fingerprint: str
    chain_fingerprint: str
    subgraph_fingerprint: str

    def to_dict(self) -> JsonDict:
        return asdict(self)


class TransitionGraph:
    """Graph-gated execution trace representation for diagnosis and audit."""

    def __init__(self):
        self.units: dict[str, TransitionUnit] = {}
        self.edges: list[TransitionEdge] = []
        self._order: list[str] = []
        self._incoming: dict[str, set[str]] = {}
        self._outgoing: dict[str, set[str]] = {}

    @classmethod
    def from_events(
        cls,
        events: list[TraceEvent],
        *,
        include_non_state_changing_events: bool = False,
    ) -> "TransitionGraph":
        graph = cls()
        previous_unit_id: str | None = None

        for index, event in enumerate(events):
            if not include_non_state_changing_events and event.kind not in {
                "tool_completed",
                "tool_failed",
                "tool_blocked",
                "tool_paused",
                "checkpoint",
                "approval",
                "tool_approved",
                "tool_denied",
            }:
                continue

            unit_id = event.event_id or f"unit_{index}"
            explicit_dependencies = []
            for key in ("depends_on", "parent_transition_ids", "parent_unit_ids", "parent_record_ids"):
                explicit_dependencies.extend(_normalize_refs(event.data.get(key)))
            missing_dependency_ids: list[str] = []
            dependency_ids = []
            for dependency_id in dict.fromkeys(explicit_dependencies):
                if dependency_id in graph.units:
                    dependency_ids.append(dependency_id)
                else:
                    missing_dependency_ids.append(dependency_id)

            if not explicit_dependencies and previous_unit_id is not None:
                dependency_ids = [previous_unit_id]

            metadata = dict(event.data)
            if missing_dependency_ids:
                metadata["missing_dependency_refs"] = missing_dependency_ids

            unit = TransitionUnit(
                unit_id=unit_id,
                event_id=event.event_id,
                kind=event.kind,
                phase=_transition_phase(event.kind),
                status=_transition_status(event),
                label=_event_label(event),
                actor=_event_actor(event),
                sequence_index=len(graph._order),
                dependency_ids=dependency_ids,
                evidence_refs=_event_evidence_refs(event),
                metadata=metadata,
            )
            graph.add_unit(unit)
            for dependency_id in dependency_ids:
                graph.add_edge(
                    dependency_id,
                    unit_id,
                    relation="dependency" if dependency_id in explicit_dependencies else "sequence",
                )
            previous_unit_id = unit_id

        return graph

    def add_unit(self, unit: TransitionUnit) -> None:
        if unit.unit_id in self.units:
            raise ValueError(f"duplicate transition unit: {unit.unit_id}")
        self.units[unit.unit_id] = unit
        self._order.append(unit.unit_id)
        self._incoming.setdefault(unit.unit_id, set())
        self._outgoing.setdefault(unit.unit_id, set())

    def add_edge(self, source_unit_id: str, target_unit_id: str, *, relation: str = "dependency") -> None:
        if source_unit_id not in self.units:
            raise KeyError(f"unknown source transition unit: {source_unit_id}")
        if target_unit_id not in self.units:
            raise KeyError(f"unknown target transition unit: {target_unit_id}")
        edge = TransitionEdge(source_unit_id=source_unit_id, target_unit_id=target_unit_id, relation=relation)
        self.edges.append(edge)
        self._outgoing[source_unit_id].add(target_unit_id)
        self._incoming[target_unit_id].add(source_unit_id)

    def predecessors(self, unit_id: str) -> list[str]:
        return sorted(self._incoming.get(unit_id, set()), key=self._unit_sort_key)

    def successors(self, unit_id: str) -> list[str]:
        return sorted(self._outgoing.get(unit_id, set()), key=self._unit_sort_key)

    def roots(self) -> list[str]:
        return [unit_id for unit_id in self._order if not self._incoming.get(unit_id)]

    def leaves(self) -> list[str]:
        return [unit_id for unit_id in self._order if not self._outgoing.get(unit_id)]

    def branch_points(self) -> list[str]:
        points = [
            unit_id
            for unit_id in self._order
            if len(self._incoming.get(unit_id, set())) > 1 or len(self._outgoing.get(unit_id, set())) > 1
        ]
        return points

    def choose_target(self, target_unit_id: str | None = None) -> str | None:
        if target_unit_id is not None:
            if target_unit_id not in self.units:
                raise KeyError(f"unknown transition unit: {target_unit_id}")
            return target_unit_id

        failed_units = [unit for unit in self.units.values() if unit.status in {"failed", "blocked", "denied"}]
        if failed_units:
            return max(failed_units, key=lambda unit: unit.sequence_index).unit_id
        if self._order:
            return self._order[-1]
        return None

    def critical_chain(self, target_unit_id: str | None = None) -> list[str]:
        target = self.choose_target(target_unit_id)
        if target is None:
            return []

        memo: dict[str, list[str]] = {}
        visiting: set[str] = set()

        def walk(unit_id: str) -> list[str]:
            if unit_id in memo:
                return memo[unit_id]
            if unit_id in visiting:
                raise ValueError(f"cycle detected in transition graph at {unit_id}")
            visiting.add(unit_id)
            predecessors = self.predecessors(unit_id)
            if not predecessors:
                chain = [unit_id]
            else:
                candidate_chains = [walk(predecessor) for predecessor in predecessors]
                chain = max(candidate_chains, key=lambda path: (len(path), [self._unit_sort_key(item) for item in path]))
                chain = chain + [unit_id]
            visiting.remove(unit_id)
            memo[unit_id] = chain
            return chain

        return walk(target)

    def critical_subgraph(self, target_unit_id: str | None = None) -> list[str]:
        target = self.choose_target(target_unit_id)
        if target is None:
            return []

        closure: set[str] = set()
        stack = [target]
        while stack:
            unit_id = stack.pop()
            if unit_id in closure:
                continue
            closure.add(unit_id)
            stack.extend(self.predecessors(unit_id))

        return sorted(closure, key=self._unit_sort_key)

    def diagnose(self, target_unit_id: str | None = None) -> TransitionGraphReport:
        target = self.choose_target(target_unit_id)
        chain = self.critical_chain(target)
        subgraph = self.critical_subgraph(target)
        target_unit = self.units.get(target) if target is not None else None

        return TransitionGraphReport(
            target_unit_id=target,
            unit_count=len(self.units),
            edge_count=len(self.edges),
            critical_transition_chain=chain,
            critical_transition_subgraph=subgraph,
            branch_points=self.branch_points(),
            root_unit_ids=self.roots(),
            leaf_unit_ids=self.leaves(),
            target_status=target_unit.status if target_unit else None,
            target_label=target_unit.label if target_unit else None,
            graph_fingerprint=self.fingerprint(),
            chain_fingerprint=_stable_hash(chain),
            subgraph_fingerprint=_stable_hash(subgraph),
        )

    def to_dict(self) -> JsonDict:
        return {
            "units": [self.units[unit_id].to_dict() for unit_id in self._order],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def _unit_sort_key(self, unit_id: str) -> tuple[int, str]:
        unit = self.units[unit_id]
        return (unit.sequence_index, unit.unit_id)
