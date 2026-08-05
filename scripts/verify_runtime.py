from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research import (
    AuthorityWitness,
    DecisionMemoryProjection,
    EvidenceClaim,
    EvidenceEntry,
    EvidenceKind,
    EvidenceLedger,
    EvidenceStatus,
    FootprintMeter,
    FseBenchmarkPlan,
    FseLocalToyTaskRunner,
    HarnessDiagnosticWorkbench,
    HarnessHermesRuntime,
    HarnessPolicy,
    HermesRuntime,
    HydrationManifestBuilder,
    InterventionReplayWorkbench,
    InterventionSpec,
    JsonCheckpointStore,
    MemoryCommitProtocol,
    MemoryKind,
    AuditLink,
    CompactionVerifier,
    Obligation,
    ObligationAuditMap,
    ObligationStatus,
    PermissionGrant,
    PermissionGraph,
    PolicyHarness,
    ProcessLifecycleVerifier,
    ResearchPhase,
    ResearchPhaseGate,
    ResearchSessionAuditBridge,
    ResearchSessionVerifier,
    SkillManifest,
    ToolCall,
    ToolDescriptionContract,
    ToolResult,
    TransitionGraph,
    ValidationReceipt,
    get_provider_profile,
    get_protocol_profile,
    research_session_from_state,
    state_ledger_items_from_state,
    SyntheticFseBenchmarkRunner,
    SyntheticFseTraceRunner,
)
from vibe_research.schema import ArtifactRef
from vibe_research.schema import ToolEffect


def read_note(call: ToolCall, _state) -> ToolResult:
    topic = call.args.get("topic", "unknown")
    return ToolResult(output=f"research note for {topic}", tokens_used=32, cost_usd=0.0001)


def run_experiment(_call: ToolCall, _state) -> ToolResult:
    return ToolResult(output="experiment completed; metric=0.91", tokens_used=64, cost_usd=0.0002)


def main() -> int:
    with TemporaryDirectory() as temp_dir:
        policy = HarnessPolicy(allowed_tools=["read_note", "run_experiment"])
        hermes = HermesRuntime(JsonCheckpointStore(Path(temp_dir) / "checkpoints"), policy=policy)
        runtime = HarnessHermesRuntime(
            hermes=hermes,
            harness=PolicyHarness(policy),
            tools={"read_note": read_note, "run_experiment": run_experiment},
        )

        state = runtime.start("verify Harness x Hermes")
        state, read_result = runtime.run_tool(
            state,
            ToolCall("read_note", {"topic": "agent harness"}, effect=ToolEffect.READ, estimated_tokens=32),
        )
        state, paused_result = runtime.run_tool(
            state,
            ToolCall("run_experiment", {"epochs": 1}, effect=ToolEffect.EXECUTE, estimated_tokens=64),
        )
        resumed = runtime.load_latest(state.task_id)
        resumed, experiment_result = runtime.approve_pending_tool(resumed)
        resumed.metadata["state_ledger"] = [
            {
                "item_id": "task-ledger",
                "item_type": "task_ledger",
                "authority": "researcher",
                "scope": resumed.task_id,
                "mutability": "append_only",
                "provenance_refs": [resumed.checkpoint_ref or ""],
                "recoverability": "replayable",
                "actionability": "audit",
                "source_refs": [resumed.checkpoint_ref or ""],
            },
            {
                "item_id": "policy-pin",
                "item_type": "permission",
                "authority": "harness",
                "scope": "policy/runtime",
                "mutability": "immutable",
                "provenance_refs": [resumed.checkpoint_ref or ""],
                "recoverability": "snapshot",
                "actionability": "read",
                "source_refs": [resumed.checkpoint_ref or ""],
            },
            {
                "item_id": "publish-gate",
                "item_type": "commitment",
                "authority": "researcher",
                "scope": "artifact/report",
                "mutability": "append_only",
                "provenance_refs": [resumed.checkpoint_ref or ""],
                "recoverability": "replayable",
                "actionability": "publish",
                "source_refs": [resumed.checkpoint_ref or ""],
            },
        ]
        resumed.metadata["context_pins"] = [
            {
                "pin_id": "publish-validation-rule",
                "surface": "harness_policy",
                "text": "Never publish a metric without a validation receipt.",
            }
        ]
        compacted_state = type(resumed).from_dict(resumed.to_dict())
        compacted_state.metadata = {
            "summary": "Compacted run state. Never publish a metric without a validation receipt.",
            "context_pins": [
                {
                    "pin_id": "publish-validation-rule",
                    "surface": "harness_policy",
                    "text": "Never publish a metric without a validation receipt.",
                }
            ],
        }
        compaction_report = CompactionVerifier().verify(resumed, compacted_state)
        process_lifecycle_report = ProcessLifecycleVerifier().evaluate(resumed, state_ledger_items_from_state(resumed))
        footprint = FootprintMeter().measure(resumed, runtime.events)
        permission_graph = PermissionGraph(
            grants=[
                PermissionGrant(
                    grant_id="publish-metric",
                    subject="research-agent",
                    effects=[ToolEffect.EXTERNAL],
                    resource_pattern="external://metric-board/*",
                    requires_witness=True,
                )
            ],
            witnesses=[
                AuthorityWitness(
                    witness_id="approval-smoke",
                    subject="research-agent",
                    effect=ToolEffect.EXTERNAL,
                    resource_pattern="external://metric-board/*",
                    issued_at_version=resumed.version,
                    expires_after_version=resumed.version,
                )
            ],
        )
        permission_decision = permission_graph.authorize_action(
            subject="research-agent",
            effect=ToolEffect.EXTERNAL,
            resource="external://metric-board/demo",
            checkpoint_version=resumed.version,
        )
        intervention_report = InterventionReplayWorkbench().evaluate(
            runtime.events,
            InterventionSpec(
                fault_kind="stale_tool_response",
                target_tool="read_note",
                response_overrides={"output_hash": "faulted-output"},
            ),
            mitigated=runtime.events,
        )
        faulted_events = InterventionReplayWorkbench().inject_fault(
            runtime.events,
            InterventionSpec(
                fault_kind="stale_tool_response",
                target_tool="read_note",
                response_overrides={"output_hash": "faulted-output"},
            ),
        )
        harness_diagnosis = HarnessDiagnosticWorkbench().diagnose(runtime.events, faulted_events)
        memory_protocol = MemoryCommitProtocol()
        memory_protocol.begin_transaction(transaction_id="tx-smoke", checkpoint_version=resumed.version)
        memory_protocol.stage_record(
            "tx-smoke",
            record_id="belief-smoke",
            kind=MemoryKind.BELIEF,
            payload={"claim": "experiment metric is ready for reporting"},
            source_refs=[resumed.checkpoint_ref or ""],
        )
        memory_protocol.validate_record(
            "belief-smoke",
            ValidationReceipt(
                validator="smoke-verifier",
                passed=True,
                reasons=["experiment output present"],
                checkpoint_version=resumed.version,
            ),
        )
        memory_commit = memory_protocol.commit("tx-smoke", checkpoint_version=resumed.version)
        memory_safety = memory_protocol.safety_gate(["belief-smoke"])
        memory_projection = DecisionMemoryProjection().project(
            memory_protocol.records.values(),
            task_context={"goal": "publish metric report", "query_terms": ["metric"]},
            required_kinds=[MemoryKind.BELIEF],
        )
        research_session = research_session_from_state(resumed)
        research_session.advance_to(
            ResearchPhase.PAPER_SCAN,
            artifact_refs=[ArtifactRef(kind="paper_shortlist", uri="artifact://papers.json")],
            evidence_refs=["source://paper-a"],
            transition_labels=["paper_scan"],
        )
        research_session.advance_to(
            ResearchPhase.HYPOTHESIS,
            artifact_refs=[ArtifactRef(kind="hypothesis", uri="artifact://hypothesis.md")],
            transition_labels=["hypothesis"],
        )
        research_session.advance_to(
            ResearchPhase.EXPERIMENT_PLAN,
            artifact_refs=[ArtifactRef(kind="experiment_plan", uri="artifact://plan.md")],
            transition_labels=["experiment_plan"],
        )
        research_session.advance_to(
            ResearchPhase.EXPERIMENT_RUN,
            artifact_refs=[ArtifactRef(kind="metric", uri="artifact://metric.json")],
            transition_labels=["run_experiment"],
            memory_record_ids=memory_commit.committed_record_ids,
            validation_receipt_refs=["receipt://metric-check"],
        )
        research_session.advance_to(
            ResearchPhase.ANALYSIS,
            artifact_refs=[ArtifactRef(kind="analysis_report", uri="artifact://analysis.md")],
            transition_labels=["analysis"],
        )
        research_session.advance_to(
            ResearchPhase.REVIEW,
            transition_labels=["peer_review"],
            review_refs=["review://virtual-reviewer"],
        )
        research_session.advance_to(ResearchPhase.WRITEUP)
        evidence_ledger = EvidenceLedger(
            entries=[
                EvidenceEntry(
                    entry_id="paper-a",
                    kind=EvidenceKind.SOURCE,
                    source_ref="https://arxiv.org/abs/example",
                    content_hash="paper-hash",
                    labels=["source"],
                ),
                EvidenceEntry(
                    entry_id="analysis-a",
                    kind=EvidenceKind.DERIVED,
                    source_ref="artifact://analysis.md",
                    content_hash="analysis-hash",
                    labels=["analysis"],
                    parent_entry_ids=["paper-a"],
                ),
                EvidenceEntry(
                    entry_id="quarantined-a",
                    kind=EvidenceKind.SOURCE,
                    source_ref="source://poisoned",
                    status=EvidenceStatus.QUARANTINED,
                    labels=["misleading"],
                ),
            ],
            claims=[
                EvidenceClaim(
                    claim_id="claim-analysis",
                    statement="The analysis claim is backed by the active ledger.",
                    cited_entry_ids=["analysis-a"],
                    required_labels=["analysis"],
                ),
            ],
        )
        evidence_ledger_report = evidence_ledger.evaluate(
            required_claim_ids=["claim-analysis"],
            forbidden_evidence_labels=["misleading"],
        )
        profiled_policy = HarnessPolicy(allowed_tools=["read_note"])
        profiled_runtime = HarnessHermesRuntime(
            hermes=HermesRuntime(JsonCheckpointStore(Path(temp_dir) / "profiled-checkpoints"), policy=profiled_policy),
            harness=PolicyHarness(profiled_policy),
            tools={"read_note": read_note},
            provider_profile=get_provider_profile("openai"),
            protocol_profile=get_protocol_profile("mcp"),
            tool_contracts={
                "read_note": ToolDescriptionContract(
                    name="read_note",
                    purpose="Read a bounded research note and return source-backed observations.",
                    input_schema={"type": "object", "properties": {"topic": {"type": "string"}}},
                    output_schema={"type": "object", "properties": {"note": {"type": "string"}}},
                    limitations=["Only reads local or cited notes."],
                    side_effects=["None; read-only action."],
                    failure_modes=["Missing source note."],
                )
            },
        )
        profiled_state = profiled_runtime.start("verify trace evidence receipts")
        profiled_state.active_skill_manifest = SkillManifest(
            name="paper_scan",
            version="0.1.0",
            purpose="Scan papers and produce cited observations.",
            context_influence=["query", "source corpus"],
            required_tools=["read_note"],
            required_capabilities=["read"],
            evidence_gates=["source-backed claim recorded"],
            fallback_paths=["narrow query and retry"],
            action_effects=[ToolEffect.READ],
        ).to_dict()
        profiled_state.metadata["active_evidence_ledger"] = {
            "name": "research-evidence",
            "fingerprint": evidence_ledger.fingerprint(),
            "claim_ids": ["claim-analysis"],
        }
        profiled_state, _profiled_result = profiled_runtime.run_tool(
            profiled_state,
            ToolCall("read_note", {"topic": "evidence receipts"}, effect=ToolEffect.READ, estimated_tokens=16),
        )
        profiled_completed = [event for event in profiled_runtime.events if event.kind == "tool_completed"]
        profiled_envelope = profiled_completed[-1].data["trace_envelope"] if profiled_completed else {}
        profiled_receipt_kinds = [
            receipt["kind"]
            for receipt in profiled_envelope.get("receipts", [])
            if isinstance(receipt, dict)
        ]
        writeup_gate = ResearchPhaseGate(
            phase=ResearchPhase.WRITEUP,
            required_artifact_kinds=["paper_shortlist", "hypothesis", "metric", "analysis_report"],
            required_transition_labels=["run_experiment"],
            required_memory_record_ids=memory_commit.committed_record_ids,
            required_evidence_claim_ids=["claim-analysis"],
            forbidden_evidence_labels=["misleading"],
            require_validation_receipt=True,
            require_review_ref=True,
        )
        research_report = ResearchSessionVerifier().evaluate(
            research_session,
            phase_gates=[writeup_gate],
            evidence_ledger=evidence_ledger,
        )
        transition_graph = TransitionGraph.from_events(runtime.events)
        transition_report = transition_graph.diagnose()
        research_audit = ResearchSessionAuditBridge().evaluate(
            research_session,
            transition_graph,
            phase_gates=[writeup_gate],
            evidence_ledger=evidence_ledger,
            phase_actors={ResearchPhase.WRITEUP: "research-agent"},
            candidate_actor_scores={ResearchPhase.WRITEUP: {"research-agent": 0.9, "reviewer-agent": 0.75}},
        )
        hydration_manifest = HydrationManifestBuilder().dehydrate(
            resumed,
            runtime.events,
            memory_records=list(memory_protocol.records.values()),
            evidence_ledger=evidence_ledger,
            research_session=research_session,
            required_memory_record_ids=memory_commit.committed_record_ids,
            required_evidence_claim_ids=["claim-analysis"],
            required_artifact_uris=["artifact://analysis.md"],
            forbidden_evidence_labels=["misleading"],
        )
        hydration_report = HydrationManifestBuilder().verify(
            hydration_manifest,
            resumed,
            runtime.events,
            memory_records=list(memory_protocol.records.values()),
            evidence_ledger=evidence_ledger,
            research_session=research_session,
        )
        obligation_audit = ObligationAuditMap(
            obligations=[
                Obligation(
                    obligation_id="verify-read-note",
                    actor="research-agent",
                    description="Verify the note-reading transition has a durable trace.",
                    status=ObligationStatus.SATISFIED,
                    required_transition_labels=["read_note"],
                )
            ],
            links=[
                AuditLink(
                    obligation_id="verify-read-note",
                    transition_unit_id=transition_report.root_unit_ids[0],
                    evidence_refs=[resumed.checkpoint_ref or ""],
                )
            ],
        ).evaluate(transition_graph)
        fse_benchmark_plan = FseBenchmarkPlan.default()
        fse_benchmark_readiness = fse_benchmark_plan.evaluate()
        fse_benchmark_matrix = SyntheticFseBenchmarkRunner(fse_benchmark_plan).build_matrix()
        fse_benchmark_matrix_report = fse_benchmark_matrix.report(fse_benchmark_plan)
        fse_benchmark_trace_report = SyntheticFseTraceRunner(fse_benchmark_plan, fse_benchmark_matrix).run()
        fse_local_report = FseLocalToyTaskRunner(fse_benchmark_plan).run(Path(temp_dir) / "local-fse")

        summary = {
            "read_output": read_result.output if read_result else None,
            "paused_before_approval": paused_result is None,
            "final_status": resumed.status,
            "budget_tokens_used": resumed.budget_state.tokens_used,
            "experiment_output": experiment_result.output if experiment_result else None,
            "checkpoint_ref": resumed.checkpoint_ref,
            "compaction_safe_to_resume": compaction_report.safe_to_resume,
            "compaction_retained_pin_count": compaction_report.retained_pin_count,
            "compaction_surfaces_at_risk": compaction_report.surfaces_at_risk,
            "process_lifecycle_stage": process_lifecycle_report.lifecycle_stage,
            "process_lifecycle_stage_matches_status": process_lifecycle_report.stage_matches_status,
            "process_lifecycle_effectful_item_ids": process_lifecycle_report.effectful_item_ids,
            "process_lifecycle_failures": process_lifecycle_report.failures,
            "footprint_total_checkpoint_bytes": footprint.total_checkpoint_bytes,
            "permission_external_allowed": permission_decision.allowed,
            "permission_witness_ids": permission_decision.witness_ids,
            "intervention_cached_prefix_count": intervention_report.cached_prefix_count,
            "intervention_live_suffix_count": intervention_report.live_suffix_count,
            "intervention_mitigation_effective": intervention_report.mitigation_effective,
            "harness_diagnosis_divergence_unit_id": harness_diagnosis.divergence_unit_id,
            "harness_diagnosis_suspect_surfaces": harness_diagnosis.suspect_surfaces,
            "harness_diagnosis_replay_passed": harness_diagnosis.replay_passed,
            "memory_committed_record_ids": memory_commit.committed_record_ids,
            "memory_safety_gate_safe": memory_safety.safe,
            "memory_projection_selected_count": memory_projection.selected_record_count,
            "research_session_current_phase": research_report.current_phase,
            "research_session_phase_gate_passed": research_report.phase_gate_passed,
            "research_session_ready_for_phase_exit": research_report.ready_for_phase_exit,
            "research_session_artifact_kinds": research_report.artifact_kinds,
            "research_session_evidence_ledger_sound": research_report.evidence_ledger_sound,
            "research_session_missing_evidence_claim_ids": research_report.missing_evidence_claim_ids,
            "research_session_unsupported_evidence_claim_ids": research_report.unsupported_evidence_claim_ids,
            "research_session_obligation_sound": research_audit.sound,
            "research_session_obligation_stable": research_audit.stable,
            "research_session_obligation_actor": research_audit.actor,
            "evidence_ledger_sound": evidence_ledger_report.sound,
            "evidence_ledger_active_entry_count": evidence_ledger_report.active_entry_count,
            "evidence_ledger_claim_count": evidence_ledger_report.claim_count,
            "evidence_ledger_forbidden_label_claim_ids": evidence_ledger_report.forbidden_label_claim_ids,
            "trace_evidence_receipt_present": "evidence_ledger" in profiled_receipt_kinds,
            "trace_evidence_claim_ids": profiled_envelope.get("evidence_claim_ids", []),
            "trace_evidence_ledger_fingerprint_matches": profiled_envelope.get("evidence_ledger_fingerprint") == evidence_ledger.fingerprint(),
            "hydration_manifest_safe_to_hydrate": hydration_report.safe_to_hydrate,
            "hydration_manifest_retained_surfaces": hydration_report.retained_surfaces,
            "hydration_manifest_missing_surfaces": hydration_report.missing_surfaces,
            "hydration_manifest_drifted_surfaces": hydration_report.drifted_surfaces,
            "transition_target_unit_id": transition_report.target_unit_id,
            "transition_critical_chain_length": len(transition_report.critical_transition_chain),
            "transition_branch_points": transition_report.branch_points,
            "obligation_audit_sound": obligation_audit.sound,
            "obligation_audit_stable": obligation_audit.stable,
            "fse_benchmark_ready": fse_benchmark_readiness.ready_for_fse,
            "fse_benchmark_runner_ready": fse_benchmark_matrix_report.ready_for_runner,
            "fse_benchmark_trace_ready": fse_benchmark_trace_report.ready_for_synthetic_trace,
            "fse_benchmark_experiment_cell_count": fse_benchmark_matrix_report.total_cell_count,
            "fse_benchmark_main_cell_count": fse_benchmark_matrix_report.main_cell_count,
            "fse_benchmark_ablation_cell_count": fse_benchmark_matrix_report.ablation_cell_count,
            "fse_benchmark_trace_processed_cell_count": fse_benchmark_trace_report.processed_cell_count,
            "fse_benchmark_trace_fault_detected_count": fse_benchmark_trace_report.fault_detected_count,
            "fse_benchmark_trace_evidence_drift_detected_count": fse_benchmark_trace_report.evidence_drift_detected_count,
            "fse_benchmark_trace_replay_passed_count": fse_benchmark_trace_report.replay_passed_count,
            "fse_local_runner_ready": fse_local_report.ready_for_local_runner,
            "fse_local_task_count": fse_local_report.task_count,
            "fse_local_success_count": fse_local_report.success_count,
            "fse_local_hydration_safe_count": fse_local_report.hydration_safe_count,
            "fse_local_phase_gate_passed_count": fse_local_report.phase_gate_passed_count,
            "fse_local_artifact_count": fse_local_report.artifact_count,
            "fse_local_evidence_claim_count": fse_local_report.evidence_claim_count,
            "fse_local_committed_memory_count": fse_local_report.committed_memory_count,
            "fse_benchmark_task_families": fse_benchmark_readiness.covered_task_families,
            "fse_benchmark_baseline_count": fse_benchmark_readiness.baseline_count,
            "fse_benchmark_fault_count": fse_benchmark_readiness.fault_count,
            "fse_benchmark_ablation_count": fse_benchmark_readiness.ablation_count,
            "fse_benchmark_rq_ids": fse_benchmark_readiness.rq_ids,
            "fse_benchmark_failures": fse_benchmark_readiness.failures + fse_benchmark_matrix_report.failures + fse_benchmark_trace_report.failures + fse_local_report.failures,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
