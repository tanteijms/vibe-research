from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research import (
    CompactionVerifier,
    ContextControlPlane,
    EvidenceClaim,
    EvidenceEntry,
    EvidenceKind,
    EvidenceLedger,
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
    ProcessStage,
    ProvenanceGraphCompiler,
    RuntimeState,
)
from vibe_research.schema import ArtifactRef, TraceEvent
from vibe_research.trace_contract import TraceBoundary, TraceEnvelope, hash_payload, make_action_receipt


class ContextAndProvenanceTests(unittest.TestCase):
    def test_context_control_plane_records_actions_and_dashboard(self):
        state = RuntimeState(
            task_id="task-context",
            session_id="sess-context",
            run_id="run-context",
            goal="govern a long-horizon context",
            execution_cursor="after:analysis",
            active_step="analysis",
            process_stage=ProcessStage.ACTIVE,
            policy_snapshot={"allowed_tools": ["read_note"], "require_review": True},
            artifact_refs=[ArtifactRef(kind="analysis_report", uri="artifact://analysis.md")],
        )
        plane = ContextControlPlane(state)

        pin_receipt = plane.pin(
            pin_id="policy-standing-rule",
            surface="harness_policy",
            value="Never publish without a review receipt.",
            reason="pin the standing publication rule",
        )
        retain_receipt = plane.retain(
            pin_id="policy-snapshot",
            surface="harness_policy",
            source_path="policy_snapshot",
            reason="retain the exact policy snapshot during compaction",
        )
        branch_receipt = plane.branch(reason="fork a review-sensitive branch")
        compress_receipt = plane.compress(
            "Compacted context. Never publish without a review receipt.",
            retained_pin_ids=["policy-standing-rule", "policy-snapshot"],
            reason="compact while preserving review-critical pins",
        )
        rehydrate_receipt = plane.rehydrate(
            source_ref="checkpoint://task-context/ckpt_000001.json",
            branch_id=branch_receipt.branch_id,
            restored_pin_ids=["policy-standing-rule", "policy-snapshot"],
            summary="Restored context with review-critical pins.",
            reason="resume the compacted branch safely",
        )

        dashboard = plane.dashboard()

        self.assertEqual(pin_receipt.kind, "pin")
        self.assertEqual(retain_receipt.kind, "retain")
        self.assertEqual(compress_receipt.kind, "compress")
        self.assertEqual(rehydrate_receipt.kind, "rehydrate")
        self.assertEqual(len(state.metadata["context_actions"]), 5)
        self.assertEqual(dashboard.branch_id, branch_receipt.branch_id)
        self.assertEqual(
            dashboard.pinned_pin_ids,
            ["policy-standing-rule", "policy-snapshot"],
        )
        self.assertEqual(dashboard.required_pin_ids, ["policy-standing-rule", "policy-snapshot"])
        self.assertEqual(dashboard.summary, "Restored context with review-critical pins.")
        self.assertEqual(dashboard.artifact_uris, ["artifact://analysis.md"])
        self.assertGreater(dashboard.retention_budget_bytes, 0)
        self.assertEqual(len(dashboard.dashboard_fingerprint), 64)

    def test_context_control_plane_pins_round_trip_through_compaction_verifier(self):
        state = RuntimeState(
            task_id="task-compact",
            session_id="sess-compact",
            run_id="run-compact",
            goal="preserve approval context",
            process_stage=ProcessStage.ACTIVE,
            policy_snapshot={"allowed_tools": ["publish_report"], "require_approval": True},
            artifact_refs=[ArtifactRef(kind="report", uri="artifact://report.md")],
        )
        plane = ContextControlPlane(state)
        plane.retain(
            pin_id="policy-snapshot",
            surface="harness_policy",
            source_path="policy_snapshot",
            reason="carry the policy snapshot into the compacted scene",
        )
        plane.pin(
            pin_id="report-lineage",
            surface="artifact_lineage",
            value="artifact://report.md",
            reason="keep the report lineage live",
        )
        plane.compress(
            "Compacted scene retaining policy snapshot and report lineage.",
            retained_pin_ids=["policy-snapshot", "report-lineage"],
            reason="prepare the scene for safe resume",
        )

        compacted = RuntimeState.from_dict(state.to_dict())
        report = CompactionVerifier().verify(state, compacted)

        self.assertTrue(report.safe_to_resume)
        self.assertIn("context:policy-snapshot", report.retained_pin_ids)
        self.assertIn("context:report-lineage", report.retained_pin_ids)
        self.assertEqual(report.failures, [])

    def test_provenance_graph_compiler_builds_execution_and_support_graphs(self):
        state = RuntimeState(
            task_id="task-prov",
            session_id="sess-prov",
            run_id="run-prov",
            goal="compile trace provenance",
            execution_cursor="after:analysis",
            active_step="analysis",
            process_stage=ProcessStage.ACTIVE,
            artifact_refs=[ArtifactRef(kind="analysis_report", uri="artifact://analysis.md")],
        )
        first_envelope = TraceEnvelope(
            boundary=TraceBoundary.TOOL,
            task_id=state.task_id,
            run_id=state.run_id,
            cursor="after:paper_scan",
            provider_name="openai",
            provider_fingerprint="provider-hash",
            policy_fingerprint="policy-hash",
            action_name="paper_scan",
            action_effect="read",
            input_hash=hash_payload({"query": "fse runtime"}),
            output_hash=hash_payload({"artifact": "artifact://papers.json"}),
            artifact_refs=["artifact://papers.json"],
            receipts=[make_action_receipt(action_name="paper_scan", input_payload={"query": "fse runtime"})],
        )
        second_envelope = TraceEnvelope(
            boundary=TraceBoundary.TOOL,
            task_id=state.task_id,
            run_id=state.run_id,
            cursor="after:analysis",
            provider_name="openai",
            provider_fingerprint="provider-hash",
            policy_fingerprint="policy-hash",
            action_name="analysis",
            action_effect="read",
            input_hash=hash_payload({"artifact": "artifact://papers.json"}),
            output_hash=hash_payload({"artifact": "artifact://analysis.md"}),
            artifact_refs=["artifact://analysis.md"],
            receipts=[make_action_receipt(action_name="analysis", input_payload={"artifact": "artifact://papers.json"})],
        )
        events = [
            TraceEvent(
                event_id="e1",
                task_id=state.task_id,
                run_id=state.run_id,
                cursor="after:paper_scan",
                kind="tool_completed",
                data={
                    "tool": "paper_scan",
                    "artifact_refs": ["artifact://papers.json"],
                    "trace_envelope": first_envelope.to_dict(),
                    "trace_envelope_fingerprint": first_envelope.fingerprint(),
                },
            ),
            TraceEvent(
                event_id="e2",
                task_id=state.task_id,
                run_id=state.run_id,
                cursor="after:analysis",
                kind="tool_completed",
                data={
                    "tool": "analysis",
                    "artifact_refs": ["artifact://analysis.md"],
                    "parent_transition_ids": ["e1"],
                    "trace_envelope": second_envelope.to_dict(),
                    "trace_envelope_fingerprint": second_envelope.fingerprint(),
                },
            ),
        ]
        memory_records = [
            MemoryRecord(
                record_id="mem-analysis",
                kind=MemoryKind.BELIEF,
                payload={"claim": "analysis is ready"},
                status=MemoryStatus.COMMITTED,
                source_refs=["artifact://analysis.md"],
            )
        ]
        ledger = EvidenceLedger(
            entries=[
                EvidenceEntry(
                    entry_id="analysis-entry",
                    kind=EvidenceKind.ARTIFACT,
                    source_ref="artifact://analysis.md",
                    labels=["analysis"],
                    produced_by_transition_id="e2",
                )
            ],
            claims=[
                EvidenceClaim(
                    claim_id="claim-analysis-ready",
                    statement="The analysis step produced a reviewable artifact.",
                    cited_entry_ids=["analysis-entry"],
                    required_labels=["analysis"],
                )
            ],
        )

        report = ProvenanceGraphCompiler().compile(
            events,
            state=state,
            memory_records=memory_records,
            evidence_ledger=ledger,
        )

        execution_node_ids = {node.node_id for node in report.execution_graph.nodes}
        execution_relations = {edge.relation for edge in report.execution_graph.edges}
        evidence_node_ids = {node.node_id for node in report.evidence_support_graph.nodes}
        evidence_relations = {edge.relation for edge in report.evidence_support_graph.edges}

        self.assertIn("event:e1", execution_node_ids)
        self.assertIn("event:e2", execution_node_ids)
        self.assertTrue(any(node_id.startswith("envelope:") for node_id in execution_node_ids))
        self.assertTrue(any(node_id.startswith("receipt:") for node_id in execution_node_ids))
        self.assertIn("produces", execution_relations)
        self.assertIn("depends_on", execution_relations)
        self.assertIn("artifact:artifact://analysis.md", evidence_node_ids)
        self.assertIn("memory:mem-analysis", evidence_node_ids)
        self.assertIn("evidence:analysis-entry", evidence_node_ids)
        self.assertIn("claim:claim-analysis-ready", evidence_node_ids)
        self.assertIn("supports_claim", evidence_relations)
        self.assertIn("supports_memory", evidence_relations)
        self.assertEqual(report.replay_summary["trace_envelope_coverage"], 1.0)
        self.assertTrue(report.replay_summary["replay_ready"])
        self.assertEqual(report.warnings, [])
        self.assertEqual(len(report.report_fingerprint), 64)

    def test_provenance_graph_compiler_warns_on_missing_envelopes_and_unresolved_refs(self):
        events = [
            TraceEvent(
                event_id="e1",
                task_id="task",
                run_id="run",
                cursor="after:tool",
                kind="tool_completed",
                data={"tool": "tool_without_envelope"},
            )
        ]
        memory_records = [
            MemoryRecord(
                record_id="mem-unresolved",
                kind=MemoryKind.BELIEF,
                payload={"claim": "something happened"},
                status=MemoryStatus.COMMITTED,
                source_refs=["artifact://missing.md"],
            )
        ]

        report = ProvenanceGraphCompiler().compile(events, memory_records=memory_records)

        self.assertFalse(report.replay_summary["replay_ready"])
        self.assertIn("tool boundary has no trace envelope: e1", report.warnings)
        self.assertIn(
            "memory source ref is unresolved in provenance graph: artifact://missing.md",
            report.warnings,
        )


if __name__ == "__main__":
    unittest.main()
