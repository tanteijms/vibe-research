from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any

from .evidence_ledger import EvidenceLedger, EvidenceLedgerReport
from .memory_commit import MemoryRecord
from .schema import ArtifactRef, RuntimeState, TraceEvent
from .transition_graph import TransitionGraph, TransitionGraphReport


JsonDict = dict[str, Any]


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _normalize_refs(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _event_label(event: TraceEvent) -> str:
    return str(event.data.get("tool") or event.data.get("action_name") or event.kind)


@dataclass(frozen=True, slots=True)
class ProvenanceNode:
    node_id: str
    kind: str
    label: str
    refs: list[str] = field(default_factory=list)
    payload_hash: str = ""
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProvenanceEdge:
    source_node_id: str
    target_node_id: str
    relation: str
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProvenanceGraph:
    graph_id: str
    scope: str
    nodes: list[ProvenanceNode] = field(default_factory=list)
    edges: list[ProvenanceEdge] = field(default_factory=list)
    root_node_ids: list[str] = field(default_factory=list)
    leaf_node_ids: list[str] = field(default_factory=list)
    graph_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return {
            "graph_id": self.graph_id,
            "scope": self.scope,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "root_node_ids": list(self.root_node_ids),
            "leaf_node_ids": list(self.leaf_node_ids),
            "graph_fingerprint": self.graph_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ProvenanceGraphCompileReport:
    execution_graph: ProvenanceGraph
    evidence_support_graph: ProvenanceGraph
    transition_report: TransitionGraphReport
    replay_summary: JsonDict
    evidence_report: JsonDict | None = None
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    report_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return {
            "execution_graph": self.execution_graph.to_dict(),
            "evidence_support_graph": self.evidence_support_graph.to_dict(),
            "transition_report": self.transition_report.to_dict(),
            "replay_summary": dict(self.replay_summary),
            "evidence_report": dict(self.evidence_report) if self.evidence_report is not None else None,
            "warnings": list(self.warnings),
            "failures": list(self.failures),
            "report_fingerprint": self.report_fingerprint,
        }


class ProvenanceGraphCompiler:
    """Compiles trace, evidence, and memory into replay-friendly provenance graphs."""

    def compile(
        self,
        events: list[TraceEvent],
        *,
        state: RuntimeState | None = None,
        artifact_refs: list[ArtifactRef] | None = None,
        memory_records: list[MemoryRecord] | None = None,
        evidence_ledger: EvidenceLedger | None = None,
    ) -> ProvenanceGraphCompileReport:
        warnings: list[str] = []
        failures: list[str] = []
        all_artifacts = list(artifact_refs or [])
        if state is not None:
            all_artifacts.extend(state.artifact_refs)

        execution_graph = self._execution_graph(events, warnings=warnings)
        evidence_graph = self._evidence_graph(
            events,
            artifacts=all_artifacts,
            memory_records=memory_records or [],
            evidence_ledger=evidence_ledger,
            warnings=warnings,
        )
        transition_report = TransitionGraph.from_events(events).diagnose()
        evidence_report: EvidenceLedgerReport | None = None
        if evidence_ledger is not None:
            evidence_report = evidence_ledger.evaluate()
            if not evidence_report.sound:
                warnings.extend(f"evidence ledger: {failure}" for failure in evidence_report.failures)

        completed_tool_count = sum(1 for event in events if event.kind == "tool_completed")
        envelope_count = sum(
            1
            for event in events
            if event.kind == "tool_completed" and "trace_envelope" in event.data
        )
        replay_summary = {
            "task_id": state.task_id if state is not None else (events[0].task_id if events else None),
            "run_id": state.run_id if state is not None else (events[0].run_id if events else None),
            "event_count": len(events),
            "completed_tool_count": completed_tool_count,
            "trace_envelope_count": envelope_count,
            "trace_envelope_coverage": round(envelope_count / completed_tool_count, 6) if completed_tool_count else 1.0,
            "artifact_uri_count": len({ref.uri for ref in all_artifacts}),
            "memory_record_count": len(memory_records or []),
            "evidence_claim_count": len(evidence_ledger.claims) if evidence_ledger is not None else 0,
            "critical_transition_chain": list(transition_report.critical_transition_chain),
            "branch_points": list(transition_report.branch_points),
            "execution_graph_fingerprint": execution_graph.graph_fingerprint,
            "evidence_support_graph_fingerprint": evidence_graph.graph_fingerprint,
            "replay_ready": completed_tool_count == 0 or envelope_count == completed_tool_count,
        }
        if completed_tool_count and envelope_count != completed_tool_count:
            warnings.append("not every completed tool boundary carries a trace envelope")

        payload = {
            "execution_graph": execution_graph.to_dict(),
            "evidence_support_graph": evidence_graph.to_dict(),
            "transition_report": transition_report.to_dict(),
            "replay_summary": replay_summary,
            "evidence_report": evidence_report.to_dict() if evidence_report is not None else None,
            "warnings": warnings,
            "failures": failures,
        }
        return ProvenanceGraphCompileReport(
            execution_graph=execution_graph,
            evidence_support_graph=evidence_graph,
            transition_report=transition_report,
            replay_summary=replay_summary,
            evidence_report=evidence_report.to_dict() if evidence_report is not None else None,
            warnings=warnings,
            failures=failures,
            report_fingerprint=_stable_hash(payload),
        )

    def _execution_graph(self, events: list[TraceEvent], *, warnings: list[str]) -> ProvenanceGraph:
        nodes: dict[str, ProvenanceNode] = {}
        edges: list[ProvenanceEdge] = []
        previous_event_node_id: str | None = None

        for event in events:
            event_node_id = f"event:{event.event_id}"
            artifact_refs = _normalize_refs(event.data.get("artifact_refs"))
            nodes[event_node_id] = ProvenanceNode(
                node_id=event_node_id,
                kind="trace_event",
                label=_event_label(event),
                refs=artifact_refs,
                payload_hash=_stable_hash(event.to_dict()),
                metadata={
                    "cursor": event.cursor,
                    "kind": event.kind,
                },
            )
            if previous_event_node_id is not None:
                edges.append(
                    ProvenanceEdge(
                        source_node_id=previous_event_node_id,
                        target_node_id=event_node_id,
                        relation="sequence",
                    )
                )
            previous_event_node_id = event_node_id

            for dependency_key in ("depends_on", "parent_transition_ids", "parent_unit_ids"):
                for dependency_id in _normalize_refs(event.data.get(dependency_key)):
                    dependency_node_id = f"event:{dependency_id}"
                    if dependency_node_id in nodes:
                        edges.append(
                            ProvenanceEdge(
                                source_node_id=dependency_node_id,
                                target_node_id=event_node_id,
                                relation="depends_on",
                                metadata={"source_key": dependency_key},
                            )
                        )
                    else:
                        warnings.append(f"missing execution dependency for provenance graph: {dependency_id}")

            envelope = event.data.get("trace_envelope")
            if isinstance(envelope, dict):
                envelope_fingerprint = str(
                    event.data.get("trace_envelope_fingerprint") or _stable_hash(envelope)
                )
                envelope_node_id = f"envelope:{envelope_fingerprint[:16]}"
                nodes.setdefault(
                    envelope_node_id,
                    ProvenanceNode(
                        node_id=envelope_node_id,
                        kind="trace_envelope",
                        label=str(envelope.get("action_name") or event.kind),
                        refs=_normalize_refs(envelope.get("artifact_refs")),
                        payload_hash=envelope_fingerprint,
                        metadata={
                            "boundary": envelope.get("boundary"),
                            "provider_name": envelope.get("provider_name"),
                            "protocol_name": envelope.get("protocol_name"),
                        },
                    ),
                )
                edges.append(
                    ProvenanceEdge(
                        source_node_id=event_node_id,
                        target_node_id=envelope_node_id,
                        relation="enveloped_by",
                    )
                )

                receipts = envelope.get("receipts", [])
                if isinstance(receipts, list):
                    for receipt in receipts:
                        if not isinstance(receipt, dict):
                            continue
                        receipt_hash = str(receipt.get("payload_hash") or _stable_hash(receipt))
                        receipt_node_id = f"receipt:{receipt_hash[:16]}"
                        nodes.setdefault(
                            receipt_node_id,
                            ProvenanceNode(
                                node_id=receipt_node_id,
                                kind=f"receipt/{receipt.get('kind', 'unknown')}",
                                label=str(receipt.get("subject") or receipt.get("kind") or "receipt"),
                                refs=[],
                                payload_hash=receipt_hash,
                                metadata=dict(receipt.get("metadata") or {}),
                            ),
                        )
                        edges.append(
                            ProvenanceEdge(
                                source_node_id=receipt_node_id,
                                target_node_id=envelope_node_id,
                                relation="attests",
                            )
                        )
            elif event.kind == "tool_completed":
                warnings.append(f"tool boundary has no trace envelope: {event.event_id}")

            for artifact_uri in artifact_refs:
                artifact_node_id = f"artifact:{artifact_uri}"
                nodes.setdefault(
                    artifact_node_id,
                    ProvenanceNode(
                        node_id=artifact_node_id,
                        kind="artifact",
                        label=artifact_uri,
                        refs=[artifact_uri],
                        payload_hash=_stable_hash(artifact_uri),
                    ),
                )
                edges.append(
                    ProvenanceEdge(
                        source_node_id=event_node_id,
                        target_node_id=artifact_node_id,
                        relation="produces",
                    )
                )

        return self._freeze_graph("execution_provenance", nodes, edges)

    def _evidence_graph(
        self,
        events: list[TraceEvent],
        *,
        artifacts: list[ArtifactRef],
        memory_records: list[MemoryRecord],
        evidence_ledger: EvidenceLedger | None,
        warnings: list[str],
    ) -> ProvenanceGraph:
        nodes: dict[str, ProvenanceNode] = {}
        edges: list[ProvenanceEdge] = []
        event_node_ids = {event.event_id: f"event:{event.event_id}" for event in events}

        for event in events:
            event_node_id = event_node_ids[event.event_id]
            nodes.setdefault(
                event_node_id,
                ProvenanceNode(
                    node_id=event_node_id,
                    kind="trace_event",
                    label=_event_label(event),
                    refs=_normalize_refs(event.data.get("artifact_refs")),
                    payload_hash=_stable_hash(event.to_dict()),
                    metadata={"cursor": event.cursor, "kind": event.kind},
                ),
            )

        for artifact in artifacts:
            artifact_node_id = f"artifact:{artifact.uri}"
            nodes.setdefault(
                artifact_node_id,
                ProvenanceNode(
                    node_id=artifact_node_id,
                    kind=f"artifact/{artifact.kind}",
                    label=artifact.uri,
                    refs=[artifact.uri],
                    payload_hash=_stable_hash(asdict(artifact)),
                    metadata=dict(artifact.metadata),
                ),
            )

        artifact_index = {ref.uri: f"artifact:{ref.uri}" for ref in artifacts}

        for record in memory_records:
            record_node_id = f"memory:{record.record_id}"
            nodes[record_node_id] = ProvenanceNode(
                node_id=record_node_id,
                kind=f"memory/{record.kind}",
                label=record.record_id,
                refs=list(record.source_refs),
                payload_hash=record.fingerprint(),
                metadata={
                    "status": record.status,
                    "parent_record_ids": list(record.parent_record_ids),
                },
            )
            for source_ref in record.source_refs:
                artifact_node_id = artifact_index.get(source_ref)
                if artifact_node_id is not None:
                    edges.append(
                        ProvenanceEdge(
                            source_node_id=artifact_node_id,
                            target_node_id=record_node_id,
                            relation="supports_memory",
                        )
                    )
                    continue
                if source_ref in event_node_ids:
                    edges.append(
                        ProvenanceEdge(
                            source_node_id=event_node_ids[source_ref],
                            target_node_id=record_node_id,
                            relation="supports_memory",
                        )
                    )
                    continue
                warnings.append(f"memory source ref is unresolved in provenance graph: {source_ref}")
            for parent_record_id in record.parent_record_ids:
                parent_node_id = f"memory:{parent_record_id}"
                if parent_node_id in nodes:
                    edges.append(
                        ProvenanceEdge(
                            source_node_id=parent_node_id,
                            target_node_id=record_node_id,
                            relation="memory_parent",
                        )
                    )

        if evidence_ledger is not None:
            for entry in evidence_ledger.entries.values():
                entry_node_id = f"evidence:{entry.entry_id}"
                nodes[entry_node_id] = ProvenanceNode(
                    node_id=entry_node_id,
                    kind=f"evidence/{entry.kind}",
                    label=entry.entry_id,
                    refs=[entry.source_ref],
                    payload_hash=entry.fingerprint(),
                    metadata={
                        "status": entry.status,
                        "labels": list(entry.labels),
                    },
                )
                artifact_node_id = artifact_index.get(entry.source_ref)
                if artifact_node_id is not None:
                    edges.append(
                        ProvenanceEdge(
                            source_node_id=artifact_node_id,
                            target_node_id=entry_node_id,
                            relation="materializes_evidence",
                        )
                    )
                if entry.produced_by_transition_id and entry.produced_by_transition_id in event_node_ids:
                    edges.append(
                        ProvenanceEdge(
                            source_node_id=event_node_ids[entry.produced_by_transition_id],
                            target_node_id=entry_node_id,
                            relation="produced_evidence",
                        )
                    )
                for parent_entry_id in entry.parent_entry_ids:
                    parent_node_id = f"evidence:{parent_entry_id}"
                    if parent_node_id in nodes:
                        edges.append(
                            ProvenanceEdge(
                                source_node_id=parent_node_id,
                                target_node_id=entry_node_id,
                                relation="derived_support",
                            )
                        )
                    else:
                        warnings.append(f"evidence parent missing in provenance graph: {entry.entry_id} -> {parent_entry_id}")

            for claim in evidence_ledger.claims.values():
                claim_node_id = f"claim:{claim.claim_id}"
                nodes[claim_node_id] = ProvenanceNode(
                    node_id=claim_node_id,
                    kind="evidence_claim",
                    label=claim.claim_id,
                    refs=list(claim.cited_entry_ids),
                    payload_hash=claim.fingerprint(),
                    metadata={
                        "required_labels": list(claim.required_labels),
                        "status": claim.status,
                    },
                )
                for cited_entry_id in claim.cited_entry_ids:
                    entry_node_id = f"evidence:{cited_entry_id}"
                    if entry_node_id in nodes:
                        edges.append(
                            ProvenanceEdge(
                                source_node_id=entry_node_id,
                                target_node_id=claim_node_id,
                                relation="supports_claim",
                            )
                        )
                    else:
                        warnings.append(f"claim cites missing evidence in provenance graph: {claim.claim_id} -> {cited_entry_id}")

        return self._freeze_graph("evidence_support", nodes, edges)

    def _freeze_graph(
        self,
        scope: str,
        nodes: dict[str, ProvenanceNode],
        edges: list[ProvenanceEdge],
    ) -> ProvenanceGraph:
        incoming: dict[str, set[str]] = {node_id: set() for node_id in nodes}
        outgoing: dict[str, set[str]] = {node_id: set() for node_id in nodes}
        unique_edges: list[ProvenanceEdge] = []
        seen_edges: set[str] = set()
        for edge in edges:
            edge_key = _stable_hash(edge.to_dict())
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            unique_edges.append(edge)
            incoming.setdefault(edge.target_node_id, set()).add(edge.source_node_id)
            outgoing.setdefault(edge.source_node_id, set()).add(edge.target_node_id)
            incoming.setdefault(edge.source_node_id, incoming.get(edge.source_node_id, set()))
            outgoing.setdefault(edge.target_node_id, outgoing.get(edge.target_node_id, set()))

        ordered_node_ids = sorted(nodes)
        graph_payload = {
            "scope": scope,
            "nodes": [nodes[node_id].to_dict() for node_id in ordered_node_ids],
            "edges": [edge.to_dict() for edge in unique_edges],
        }
        return ProvenanceGraph(
            graph_id=f"{scope}:{_stable_hash(graph_payload)[:16]}",
            scope=scope,
            nodes=[nodes[node_id] for node_id in ordered_node_ids],
            edges=unique_edges,
            root_node_ids=[node_id for node_id in ordered_node_ids if not incoming.get(node_id)],
            leaf_node_ids=[node_id for node_id in ordered_node_ids if not outgoing.get(node_id)],
            graph_fingerprint=_stable_hash(graph_payload),
        )
