from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research import AuditLink, AuthorityWitness, CompactionVerifier, DecisionMemoryProjection, EvidenceClaim, EvidenceEntry, EvidenceKind, EvidenceLedger, EvidenceStatus, FootprintMeter, HarnessDiagnosticWorkbench, HarnessHermesRuntime, HarnessPolicy, HermesRuntime, HydrationManifestBuilder, HydrationSurface, InterventionReplayWorkbench, InterventionSpec, JsonCheckpointStore, MemoryCommitProtocol, MemoryKind, MemoryRecord, MemoryStatus, Obligation, ObligationAuditMap, ObligationStatus, PermissionGrant, PermissionGraph, PolicyHarness, ProcessLifecycleVerifier, ProcessStage, ResearchPhase, ResearchPhaseGate, ResearchSession, ResearchSessionAuditBridge, ResearchSessionVerifier, RuntimeState, SkillManifest, StateLedgerItem, ToolCall, ToolResult, TransitionGraph, TransitionVerifier, ValidationReceipt, research_session_from_state, state_ledger_items_from_state
from vibe_research.eval import PathVerifier, ReplayVerifier
from vibe_research.provider_profiles import get_provider_profile
from vibe_research.protocol_profiles import get_protocol_profile
from vibe_research.path_policy import ActionPathPolicy
from vibe_research.runtime import stable_hash
from vibe_research.secrets import load_secret_file
from vibe_research.schema import ArtifactRef, RunStatus, RuntimeState, ToolEffect, TraceEvent
from vibe_research.tool_contracts import ToolDescriptionContract
from vibe_research.trace_contract import TraceBoundary, TraceEnvelope, hash_payload, make_action_receipt


class HarnessHermesTests(unittest.TestCase):
    def build_runtime(self, temp_dir: str, *, policy: HarnessPolicy | None = None):
        selected_policy = policy or HarnessPolicy(allowed_tools=["read_note", "run_experiment"])
        hermes = HermesRuntime(JsonCheckpointStore(Path(temp_dir) / "checkpoints"), policy=selected_policy)
        calls: list[str] = []

        def read_note(_call: ToolCall, _state) -> ToolResult:
            calls.append("read_note")
            return ToolResult(output="note api_key=sk-test-secret", tokens_used=10, cost_usd=0.01)

        def run_experiment(_call: ToolCall, _state) -> ToolResult:
            calls.append("run_experiment")
            return ToolResult(output="metric=0.95", tokens_used=20, cost_usd=0.02)

        runtime = HarnessHermesRuntime(
            hermes=hermes,
            harness=PolicyHarness(selected_policy),
            tools={"read_note": read_note, "run_experiment": run_experiment},
        )
        return runtime, calls

    def build_profiled_runtime(self, temp_dir: str):
        policy = HarnessPolicy(allowed_tools=["run_experiment"])
        hermes = HermesRuntime(JsonCheckpointStore(Path(temp_dir) / "checkpoints"), policy=policy)
        contract = ToolDescriptionContract(
            name="run_experiment",
            purpose="Run a bounded experiment and return metrics.",
            input_schema={"type": "object", "properties": {"epochs": {"type": "integer"}}},
            output_schema={"type": "object", "properties": {"metric": {"type": "number"}}},
            limitations=["Requires prepared dataset."],
            side_effects=["Writes metrics artifacts."],
            failure_modes=["Environment setup may fail."],
        )

        def run_experiment(_call: ToolCall, _state) -> ToolResult:
            return ToolResult(output="metric=0.97", tokens_used=20, cost_usd=0.02)

        return HarnessHermesRuntime(
            hermes=hermes,
            harness=PolicyHarness(policy),
            tools={"run_experiment": run_experiment},
            provider_profile=get_provider_profile("openai"),
            protocol_profile=get_protocol_profile("mcp"),
            tool_contracts={"run_experiment": contract},
        )

    def test_secrets_are_ignored(self):
        ignore_text = Path(".gitignore").read_text(encoding="utf-8")
        self.assertIn("secrets.txt", ignore_text)

    def test_secret_loader_does_not_treat_urls_as_api_keys(self):
        with TemporaryDirectory() as temp_dir:
            secret_path = Path(temp_dir) / "secrets.txt"
            secret_path.write_text("http://127.0.0.1:8081\nOPENAI_BASE_URL=http://127.0.0.1:8081\n", encoding="utf-8")

            secrets = load_secret_file(secret_path)

            self.assertNotIn("OPENAI_API_KEY", secrets)
            self.assertEqual(secrets["OPENAI_BASE_URL"], "http://127.0.0.1:8081")

    def test_secret_loader_accepts_raw_base_url_line(self):
        with TemporaryDirectory() as temp_dir:
            secret_path = Path(temp_dir) / "secrets.txt"
            secret_path.write_text("http://127.0.0.1:8081\nsk-test-key\n", encoding="utf-8")

            secrets = load_secret_file(secret_path)

            self.assertEqual(secrets["OPENAI_BASE_URL"], "http://127.0.0.1:8081")
            self.assertEqual(secrets["OPENAI_API_KEY"], "sk-test-key")

    def test_budget_blocks_before_tool_execution(self):
        with TemporaryDirectory() as temp_dir:
            policy = HarnessPolicy(allowed_tools=["read_note"], max_tool_cost_usd=0.005)
            runtime, calls = self.build_runtime(temp_dir, policy=policy)
            state = runtime.start("budget test")
            state, result = runtime.run_tool(
                state,
                ToolCall("read_note", estimated_cost_usd=0.01, effect=ToolEffect.READ),
            )

            self.assertIsNone(result)
            self.assertEqual(state.status, RunStatus.BLOCKED)
            self.assertEqual(calls, [])
            self.assertIn("exceeds per-call limit", state.failure_state["reason"])

    def test_approval_checkpoint_resume_and_redaction(self):
        with TemporaryDirectory() as temp_dir:
            runtime, calls = self.build_runtime(temp_dir)
            state = runtime.start("approval test")
            self.assertEqual(state.process_stage, ProcessStage.ACTIVE)

            state, read_result = runtime.run_tool(
                state,
                ToolCall("read_note", {"topic": "harness"}, effect=ToolEffect.READ),
            )
            state, pending_result = runtime.run_tool(
                state,
                ToolCall("run_experiment", {"epochs": 1}, effect=ToolEffect.EXECUTE),
            )

            self.assertEqual(read_result.output, "note [REDACTED]")
            self.assertIsNone(pending_result)
            self.assertEqual(state.status, RunStatus.AWAITING_APPROVAL)
            self.assertEqual(state.process_stage, ProcessStage.WAITING)
            self.assertEqual(calls, ["read_note"])

            resumed = runtime.load_latest(state.task_id)
            resumed, experiment_result = runtime.approve_pending_tool(resumed)

            self.assertEqual(experiment_result.output, "metric=0.95")
            self.assertEqual(resumed.status, RunStatus.READY)
            self.assertEqual(resumed.process_stage, ProcessStage.ACTIVE)
            self.assertEqual(calls, ["read_note", "run_experiment"])
            self.assertEqual(resumed.budget_state.tokens_used, 30)

    def test_replay_verifier_detects_drift(self):
        expected = [
            TraceEvent(
                event_id="e1",
                task_id="task",
                run_id="run",
                cursor="c",
                kind="tool_completed",
                data={"tool": "read_note", "args_hash": stable_hash({"a": 1}), "output_hash": stable_hash("ok")},
            )
        ]
        actual = [
            TraceEvent(
                event_id="e2",
                task_id="task",
                run_id="run",
                cursor="c",
                kind="tool_completed",
                data={"tool": "read_note", "args_hash": stable_hash({"a": 1}), "output_hash": stable_hash("changed")},
            )
        ]

        report = ReplayVerifier().compare(expected, actual)
        self.assertFalse(report.passed)
        self.assertEqual(report.failures, ["event 0 output_hash differs"])

    def test_runtime_records_trace_envelope_with_all_fingerprints(self):
        with TemporaryDirectory() as temp_dir:
            runtime = self.build_profiled_runtime(temp_dir)
            state = runtime.start("trace v2 test")
            evidence_ledger = EvidenceLedger(
                entries=[
                    EvidenceEntry(
                        entry_id="metric-source",
                        kind=EvidenceKind.ARTIFACT,
                        source_ref="artifact://metric.json",
                        content_hash="metric-hash",
                        labels=["metric"],
                    )
                ],
                claims=[
                    EvidenceClaim(
                        claim_id="claim-metric-ready",
                        statement="The metric is ready for analysis.",
                        cited_entry_ids=["metric-source"],
                        required_labels=["metric"],
                    )
                ],
            )
            skill = SkillManifest(
                name="baseline_reproduce",
                version="0.1.0",
                purpose="Reproduce a bounded baseline experiment.",
                context_influence=["experiment plan"],
                required_tools=["run_experiment"],
                required_capabilities=["execute"],
                evidence_gates=["metrics artifact recorded"],
                fallback_paths=["reduce epochs and retry once"],
                action_effects=[ToolEffect.EXECUTE],
            )
            state.active_skill_manifest = skill.to_dict()
            state.metadata["active_evidence_ledger"] = {
                "name": "research-evidence",
                "fingerprint": evidence_ledger.fingerprint(),
                "claim_ids": ["claim-metric-ready"],
            }

            state, pending = runtime.run_tool(
                state,
                ToolCall("run_experiment", {"epochs": 1}, effect=ToolEffect.EXECUTE),
            )
            self.assertIsNone(pending)
            state = runtime.load_latest(state.task_id)
            state, result = runtime.approve_pending_tool(state)

            self.assertEqual(result.output, "metric=0.97")
            completed = [event for event in runtime.events if event.kind == "tool_completed"]
            self.assertEqual(len(completed), 1)
            envelope = completed[0].data["trace_envelope"]
            self.assertEqual(envelope["provider_name"], "openai")
            self.assertEqual(envelope["protocol_name"], "mcp-2026-07-28")
            self.assertIsNotNone(envelope["tool_contract_fingerprint"])
            self.assertEqual(envelope["skill_name"], "baseline_reproduce")
            self.assertEqual(envelope["skill_manifest_fingerprint"], skill.fingerprint())
            self.assertEqual(envelope["evidence_ledger_fingerprint"], evidence_ledger.fingerprint())
            self.assertEqual(envelope["evidence_claim_ids"], ["claim-metric-ready"])
            self.assertIn("evidence_ledger", [receipt["kind"] for receipt in envelope["receipts"]])
            self.assertEqual(envelope["action_effect"], ToolEffect.EXECUTE)
            self.assertEqual(len(completed[0].data["trace_envelope_fingerprint"]), 64)

    def test_replay_verifier_detects_trace_envelope_drift(self):
        base_envelope = {
            "schema_version": "trace-envelope-v2",
            "boundary": TraceBoundary.TOOL,
            "provider_fingerprint": "provider-a",
            "protocol_fingerprint": "protocol-a",
            "policy_fingerprint": "policy-a",
            "tool_contract_fingerprint": "tool-a",
            "skill_manifest_fingerprint": "skill-a",
            "evidence_ledger_fingerprint": "evidence-a",
            "evidence_claim_ids": ["claim-a"],
            "action_effect": ToolEffect.EXECUTE,
            "input_hash": "input-a",
            "output_hash": "output-a",
        }
        expected = [
            TraceEvent(
                event_id="e1",
                task_id="task",
                run_id="run",
                cursor="c",
                kind="tool_completed",
                data={
                    "tool": "run_experiment",
                    "args_hash": "args",
                    "output_hash": "output",
                    "trace_envelope_fingerprint": "left",
                    "trace_envelope": dict(base_envelope),
                },
            )
        ]
        drifted = dict(base_envelope)
        drifted["protocol_fingerprint"] = "protocol-b"
        drifted["skill_manifest_fingerprint"] = "skill-b"
        drifted["evidence_ledger_fingerprint"] = "evidence-b"
        drifted["evidence_claim_ids"] = ["claim-b"]
        actual = [
            TraceEvent(
                event_id="e2",
                task_id="task",
                run_id="run",
                cursor="c",
                kind="tool_completed",
                data={
                    "tool": "run_experiment",
                    "args_hash": "args",
                    "output_hash": "output",
                    "trace_envelope_fingerprint": "right",
                    "trace_envelope": drifted,
                },
            )
        ]

        report = ReplayVerifier().compare(expected, actual)

        self.assertFalse(report.passed)
        self.assertIn("event 0 trace_envelope_fingerprint differs", report.failures)
        self.assertIn("event 0 trace_envelope.protocol_fingerprint differs", report.failures)
        self.assertIn("event 0 trace_envelope.skill_manifest_fingerprint differs", report.failures)
        self.assertIn("event 0 trace_envelope.evidence_ledger_fingerprint differs", report.failures)
        self.assertIn("event 0 trace_envelope.evidence_claim_ids differs", report.failures)

    def test_provider_profile_has_stable_checkpoint_snapshot(self):
        profile = get_provider_profile("dpsk")
        snapshot = profile.checkpoint_snapshot()

        self.assertEqual(snapshot["name"], "deepseek")
        self.assertIn("fingerprint", snapshot)
        self.assertEqual(snapshot["fingerprint"], profile.fingerprint())
        self.assertIn("provider capability adapter", profile.harness_hooks)

    def test_latest_runtime_profiles_capture_agent_sdk_and_durable_orchestration(self):
        claude = get_provider_profile("claude")
        google = get_provider_profile("adk")
        temporal = get_provider_profile("temporal-langgraph")
        agentcore = get_provider_profile("agentcore")
        pydantic = get_provider_profile("pydantic-ai")
        mistral = get_provider_profile("mistral")
        microsoft = get_provider_profile("maf")
        governance_toolkit = get_provider_profile("agt")
        cloudflare = get_provider_profile("cloudflare")
        vercel = get_provider_profile("workflowagent")
        mastra = get_provider_profile("mastra")

        self.assertEqual(claude.name, "anthropic-agent-sdk")
        self.assertIn("permissions", claude.governance_surfaces)
        self.assertIn("sandbox snapshots", google.state_surfaces)
        self.assertIn("approval signal adapter", temporal.harness_hooks)
        self.assertIn("identity witness adapter", agentcore.harness_hooks)
        self.assertIn("durable wait adapter", pydantic.harness_hooks)
        self.assertIn("approval state adapter", mistral.harness_hooks)
        self.assertIn("connector permission adapter", microsoft.harness_hooks)
        self.assertIn("policy artifact adapter", governance_toolkit.harness_hooks)
        self.assertIn("identity assertions", governance_toolkit.state_surfaces)
        self.assertIn("durable object state adapter", cloudflare.harness_hooks)
        self.assertIn("workflow resume adapter", vercel.harness_hooks)
        self.assertIn("approval suspend adapter", mastra.harness_hooks)

    def test_trace_envelope_records_provider_and_policy_fingerprints(self):
        profile = get_provider_profile("openai")
        receipt = make_action_receipt(action_name="run_experiment", input_payload={"epochs": 1}, output_payload="ok")
        envelope = TraceEnvelope(
            boundary=TraceBoundary.TOOL,
            task_id="task",
            run_id="run",
            cursor="after:plan",
            provider_name=profile.name,
            provider_fingerprint=profile.fingerprint(),
            policy_fingerprint=hash_payload({"allowed_tools": ["run_experiment"]}),
            action_name="run_experiment",
            action_effect=ToolEffect.EXECUTE,
            input_hash=hash_payload({"epochs": 1}),
            output_hash=hash_payload("ok"),
            receipts=[receipt],
        )

        self.assertEqual(envelope.to_dict()["receipts"][0]["subject"], "run_experiment")
        self.assertEqual(len(envelope.fingerprint()), 64)

    def test_protocol_profile_captures_mcp_2026_runtime_implications(self):
        profile = get_protocol_profile("mcp")

        self.assertEqual(profile.name, "mcp-2026-07-28")
        self.assertIn("stateless request core", profile.primitives)
        self.assertIn("input_required mid-call approvals", profile.governance_hooks)
        self.assertEqual(len(profile.fingerprint()), 64)

    def test_tool_description_contract_quality_gate_and_compact_context(self):
        contract = ToolDescriptionContract(
            name="run_experiment",
            purpose="Run a bounded experiment and return metrics.",
            input_schema={"type": "object", "properties": {"epochs": {"type": "integer"}}},
            output_schema={"type": "object", "properties": {"metric": {"type": "number"}}},
            limitations=["Requires prepared dataset."],
            side_effects=["Writes logs and metrics artifacts."],
            failure_modes=["Environment setup may fail."],
            examples=["run_experiment({epochs: 1})"],
        )

        self.assertEqual(contract.missing_components(), [])
        compact = contract.compact_context()
        self.assertNotIn("Examples:", compact)
        metadata = contract.to_mcp_metadata()
        self.assertEqual(metadata["name"], "run_experiment")
        self.assertEqual(metadata["_meta"]["vibe_research/qualityWarnings"], [])

    def test_tool_description_contract_warns_on_missing_components(self):
        contract = ToolDescriptionContract(name="x", purpose="Run")

        self.assertIn("missing:input_schema", contract.quality_warnings())
        self.assertIn("purpose_too_short", contract.quality_warnings())

    def test_skill_manifest_is_permission_bearing_artifact(self):
        manifest = SkillManifest(
            name="paper_scan",
            version="0.1.0",
            purpose="Scan papers and produce a cited shortlist.",
            context_influence=["query", "source corpus"],
            required_tools=["search", "read_pdf"],
            required_capabilities=["network", "read"],
            evidence_gates=["sources cited", "stale claims flagged"],
            fallback_paths=["narrow query", "ask for clarification"],
            action_effects=[ToolEffect.READ, ToolEffect.NETWORK],
        )

        guard = manifest.to_skill_guard_manifest()

        self.assertEqual(manifest.quality_warnings(), [])
        self.assertEqual(guard["permissions"]["required_tools"], ["search", "read_pdf"])
        self.assertEqual(len(guard["_meta"]["vibe_research/skillManifestHash"]), 64)

    def test_path_verifier_enforces_governance_sequence(self):
        events = [
            TraceEvent(event_id="e1", task_id="task", run_id="run", cursor="c1", kind="tool_completed", data={"tool": "paper_scan"}),
            TraceEvent(event_id="e2", task_id="task", run_id="run", cursor="c2", kind="tool_completed", data={"tool": "run_experiment"}),
            TraceEvent(event_id="e3", task_id="task", run_id="run", cursor="c3", kind="tool_completed", data={"tool": "publish_report"}),
        ]
        policy = ActionPathPolicy(
            required_order=["paper_scan", "run_experiment"],
            required_actions=["paper_scan", "run_experiment"],
            forbidden_subsequences=[["run_experiment", "publish_report"]],
            max_repeats={"run_experiment": 1},
            end_with_any_of=["run_experiment"],
        )

        report = PathVerifier().compare(events, policy)

        self.assertFalse(report.passed)
        self.assertEqual(report.action_path, ["paper_scan", "run_experiment", "publish_report"])
        self.assertIn("forbidden subsequence present: run_experiment -> publish_report", report.failures)
        self.assertIn("final action publish_report not in allowed endings: run_experiment", report.failures)

    def test_footprint_report_includes_checkpoint_surfaces(self):
        state = RuntimeState(
            task_id="task",
            session_id="session",
            run_id="run",
            goal="measure footprint",
            metadata={"checkpoint_reason": "test"},
            active_skill_manifest={
                "name": "paper_scan",
                "version": "0.1.0",
                "purpose": "Scan papers.",
            },
        )
        state.artifact_refs.append(ArtifactRef(kind="metric", uri="artifact://metric.json", sha256="abc"))
        events = [
            TraceEvent(
                event_id="event",
                task_id="task",
                run_id="run",
                cursor="after:tool",
                kind="tool_completed",
                data={"tool": "paper_scan", "trace_envelope": {"provider_fingerprint": "provider"}},
            )
        ]

        report = FootprintMeter().measure(state, events)

        self.assertEqual(report.event_count, 1)
        self.assertEqual(report.artifact_count, 1)
        self.assertEqual(report.trace_envelope_count, 1)
        self.assertGreater(report.state_bytes, 0)
        self.assertGreater(report.events_bytes, 0)
        self.assertGreater(report.artifact_refs_bytes, 0)
        self.assertGreater(report.metadata_bytes, 0)
        self.assertGreater(report.active_skill_manifest_bytes, 0)
        self.assertGreater(report.trace_envelope_bytes, 0)
        self.assertEqual(report.channel_bytes["state"], report.state_bytes)
        self.assertEqual(len(report.state_fingerprint), 64)
        self.assertEqual(len(report.events_fingerprint), 64)

    def test_footprint_grows_when_events_and_artifacts_increase(self):
        state = RuntimeState(task_id="task", session_id="session", run_id="run", goal="measure footprint")
        base = FootprintMeter().measure(state, [])

        state.artifact_refs.append(ArtifactRef(kind="log", uri="artifact://run.log"))
        events = [
            TraceEvent(
                event_id="event",
                task_id="task",
                run_id="run",
                cursor="after:tool",
                kind="tool_completed",
                data={"tool": "run_experiment", "output_hash": "hash"},
            )
        ]
        expanded = FootprintMeter().measure(state, events)

        self.assertGreater(expanded.total_checkpoint_bytes, base.total_checkpoint_bytes)
        self.assertGreater(expanded.artifact_count, base.artifact_count)
        self.assertGreater(expanded.event_count, base.event_count)

    def test_compaction_verifier_allows_resume_when_governance_pins_are_retained(self):
        original = RuntimeState(
            task_id="task",
            session_id="session",
            run_id="run",
            goal="retain harness policy",
            execution_cursor="after:review",
            active_step="review",
            policy_snapshot={"allowed_tools": ["read_note"], "require_approval_for_effects": [ToolEffect.EXECUTE]},
            trace_id="trace",
            active_skill_manifest={
                "name": "paper_scan",
                "version": "0.1.0",
                "purpose": "Scan papers with cited evidence.",
            },
            metadata={
                "summary": "Long context before compaction.",
                "context_pins": [
                    {
                        "pin_id": "policy-standing-rule",
                        "surface": "harness_policy",
                        "text": "Never publish without validation receipt.",
                    }
                ],
            },
        )
        original.artifact_refs.append(ArtifactRef(kind="metric", uri="artifact://metric.json", sha256="abc"))
        compacted = RuntimeState.from_dict(original.to_dict())
        compacted.metadata = {
            "summary": "Compacted context. Never publish without validation receipt.",
            "context_pins": [
                {
                    "pin_id": "policy-standing-rule",
                    "surface": "harness_policy",
                    "text": "Never publish without validation receipt.",
                }
            ],
        }

        report = CompactionVerifier().verify(original, compacted)

        self.assertTrue(report.safe_to_resume)
        self.assertEqual(report.failures, [])
        self.assertIn("harness_policy:policy_snapshot", report.retained_pin_ids)
        self.assertIn("context:policy-standing-rule", report.retained_pin_ids)
        self.assertEqual(report.surfaces_at_risk, [])
        self.assertEqual(len(report.report_fingerprint), 64)

    def test_compaction_verifier_blocks_resume_when_policy_pending_approval_or_context_pin_is_lost(self):
        original = RuntimeState(
            task_id="task",
            session_id="session",
            run_id="run",
            goal="approval-sensitive run",
            status=RunStatus.AWAITING_APPROVAL,
            policy_snapshot={"allowed_tools": ["run_experiment"], "max_tool_cost_usd": 0.1},
            pending_tool_call=ToolCall("run_experiment", {"epochs": 1}, effect=ToolEffect.EXECUTE).to_dict(),
            approval_token="approval-1",
            metadata={
                "context_pins": [
                    {
                        "pin_id": "dataset-lineage",
                        "surface": "artifact_lineage",
                        "text": "dataset hash must remain sha256:dataset-a",
                    }
                ]
            },
        )
        compacted = RuntimeState.from_dict(original.to_dict())
        compacted.policy_snapshot = {"allowed_tools": ["run_experiment"]}
        compacted.pending_tool_call = None
        compacted.approval_token = None
        compacted.metadata = {"summary": "Compacted context without dataset lineage."}

        report = CompactionVerifier().verify(original, compacted)

        self.assertFalse(report.safe_to_resume)
        self.assertIn("harness_policy:policy_snapshot", report.drifted_pin_ids)
        self.assertIn("approval_boundary:pending_tool_call", report.missing_pin_ids)
        self.assertIn("approval_boundary:approval_token", report.missing_pin_ids)
        self.assertIn("context:dataset-lineage", report.missing_pin_ids)
        self.assertIn("harness_policy", report.surfaces_at_risk)
        self.assertIn("approval_boundary", report.surfaces_at_risk)
        self.assertIn("artifact_lineage", report.surfaces_at_risk)

    def test_process_lifecycle_verifier_accepts_always_on_state_ledger(self):
        state = RuntimeState(
            task_id="task",
            session_id="session",
            run_id="run",
            goal="keep process alive",
            status=RunStatus.READY,
            process_stage=ProcessStage.ACTIVE,
            metadata={
                "state_ledger": [
                    {
                        "item_id": "task-ledger",
                        "item_type": "task_ledger",
                        "authority": "researcher",
                        "scope": "task/task",
                        "mutability": "append_only",
                        "provenance_refs": ["trace://run"],
                        "recoverability": "replayable",
                        "actionability": "audit",
                        "source_refs": ["checkpoint://task"],
                    },
                    {
                        "item_id": "permission-pin",
                        "item_type": "permission",
                        "authority": "harness",
                        "scope": "policy/runtime",
                        "mutability": "immutable",
                        "provenance_refs": ["checkpoint://policy"],
                        "recoverability": "snapshot",
                        "actionability": "read",
                        "source_refs": ["checkpoint://policy"],
                    },
                    {
                        "item_id": "publish-gate",
                        "item_type": "commitment",
                        "authority": "researcher",
                        "scope": "artifact/report",
                        "mutability": "append_only",
                        "provenance_refs": ["artifact://report"],
                        "recoverability": "replayable",
                        "actionability": "publish",
                        "source_refs": ["artifact://report"],
                    },
                ]
            },
        )
        items = state_ledger_items_from_state(state)

        report = ProcessLifecycleVerifier().evaluate(state, items)

        self.assertTrue(report.stage_matches_status)
        self.assertFalse(report.stage_requires_attention)
        self.assertEqual(report.failures, [])
        self.assertEqual(report.missing_axis_item_ids, [])
        self.assertIn("publish-gate", report.effectful_item_ids)
        self.assertEqual(len(report.report_fingerprint), 64)

    def test_process_lifecycle_verifier_flags_stage_mismatch_and_nonrecoverable_effectful_item(self):
        state = RuntimeState(
            task_id="task",
            session_id="session",
            run_id="run",
            goal="mismatch test",
            status=RunStatus.AWAITING_APPROVAL,
            process_stage=ProcessStage.ACTIVE,
        )
        items = [
            StateLedgerItem(
                item_id="external-publish",
                item_type="commitment",
                authority="researcher",
                scope="artifact/report",
                mutability="append_only",
                provenance_refs=["artifact://report"],
                recoverability="none",
                actionability="publish",
                source_refs=["artifact://report"],
            )
        ]

        report = ProcessLifecycleVerifier().evaluate(state, items)

        self.assertFalse(report.stage_matches_status)
        self.assertIn("process stage mismatch: active != waiting", report.failures)
        self.assertIn("external-publish", report.nonrecoverable_effectful_item_ids)
        self.assertIn("effectful item is nonrecoverable: external-publish", report.failures)

    def test_research_session_phase_gate_accepts_evidence_backed_writeup(self):
        session = ResearchSession(
            session_id="research-1",
            runtime_task_id="task",
            goal="test a harness idea",
            policy_snapshot_hash="policy-hash",
        )
        session.advance_to(
            ResearchPhase.PAPER_SCAN,
            artifact_refs=[ArtifactRef(kind="paper_shortlist", uri="artifact://papers.json")],
            evidence_refs=["source://paper-a"],
            transition_labels=["paper_scan"],
        )
        session.advance_to(
            ResearchPhase.HYPOTHESIS,
            artifact_refs=[ArtifactRef(kind="hypothesis", uri="artifact://hypothesis.md")],
            evidence_refs=["artifact://hypothesis.md"],
            transition_labels=["hypothesis"],
        )
        session.advance_to(
            ResearchPhase.EXPERIMENT_PLAN,
            artifact_refs=[ArtifactRef(kind="experiment_plan", uri="artifact://plan.md")],
            transition_labels=["experiment_plan"],
        )
        session.advance_to(
            ResearchPhase.EXPERIMENT_RUN,
            artifact_refs=[ArtifactRef(kind="metric", uri="artifact://metric.json")],
            transition_labels=["run_experiment"],
            memory_record_ids=["metric-belief"],
            validation_receipt_refs=["receipt://metric-check"],
        )
        session.advance_to(
            ResearchPhase.ANALYSIS,
            artifact_refs=[ArtifactRef(kind="analysis_report", uri="artifact://analysis.md")],
            transition_labels=["analysis"],
        )
        session.advance_to(
            ResearchPhase.REVIEW,
            transition_labels=["peer_review"],
            review_refs=["review://virtual-reviewer"],
        )
        session.advance_to(ResearchPhase.WRITEUP)
        gate = ResearchPhaseGate(
            phase=ResearchPhase.WRITEUP,
            required_artifact_kinds=["paper_shortlist", "hypothesis", "metric", "analysis_report"],
            required_transition_labels=["paper_scan", "run_experiment", "peer_review"],
            required_memory_record_ids=["metric-belief"],
            require_validation_receipt=True,
            require_review_ref=True,
        )

        report = ResearchSessionVerifier().evaluate(session, phase_gates=[gate])

        self.assertTrue(report.phase_path_valid)
        self.assertTrue(report.phase_gate_passed)
        self.assertTrue(report.ready_for_phase_exit)
        self.assertEqual(report.failures, [])
        self.assertIn("metric", report.artifact_kinds)
        self.assertEqual(len(report.report_fingerprint), 64)

    def test_research_session_phase_gate_accepts_required_evidence_claims(self):
        session = ResearchSession(
            session_id="research-claims",
            runtime_task_id="task",
            goal="write from evidence-backed claims",
            current_phase=ResearchPhase.WRITEUP,
            phase_history=[
                ResearchPhase.INTAKE,
                ResearchPhase.PAPER_SCAN,
                ResearchPhase.HYPOTHESIS,
                ResearchPhase.EXPERIMENT_PLAN,
                ResearchPhase.EXPERIMENT_RUN,
                ResearchPhase.ANALYSIS,
                ResearchPhase.REVIEW,
                ResearchPhase.WRITEUP,
            ],
            artifact_refs=[ArtifactRef(kind="analysis_report", uri="artifact://analysis.md")],
            evidence_refs=["artifact://analysis.md"],
            policy_snapshot_hash="policy-hash",
        )
        gate = ResearchPhaseGate(
            phase=ResearchPhase.WRITEUP,
            required_artifact_kinds=["analysis_report"],
            required_evidence_claim_ids=["claim-analysis-supported"],
            forbidden_evidence_labels=["misleading"],
        )
        ledger = EvidenceLedger(
            entries=[
                EvidenceEntry(
                    entry_id="analysis-a",
                    kind=EvidenceKind.ARTIFACT,
                    source_ref="artifact://analysis.md",
                    labels=["analysis"],
                )
            ],
            claims=[
                EvidenceClaim(
                    claim_id="claim-analysis-supported",
                    statement="The analysis artifact supports the writeup claim.",
                    cited_entry_ids=["analysis-a"],
                    required_labels=["analysis"],
                )
            ],
        )

        report = ResearchSessionVerifier().evaluate(
            session,
            phase_gates=[gate],
            evidence_ledger=ledger,
        )

        self.assertTrue(report.phase_gate_passed)
        self.assertTrue(report.evidence_ledger_sound)
        self.assertEqual(report.missing_evidence_claim_ids, [])
        self.assertEqual(report.unsupported_evidence_claim_ids, [])

    def test_research_session_phase_gate_blocks_unsupported_evidence_claims(self):
        session = ResearchSession(
            session_id="research-claim-risk",
            runtime_task_id="task",
            goal="block unsupported writeup claim",
            current_phase=ResearchPhase.WRITEUP,
            phase_history=[
                ResearchPhase.INTAKE,
                ResearchPhase.PAPER_SCAN,
                ResearchPhase.HYPOTHESIS,
                ResearchPhase.EXPERIMENT_PLAN,
                ResearchPhase.EXPERIMENT_RUN,
                ResearchPhase.ANALYSIS,
                ResearchPhase.REVIEW,
                ResearchPhase.WRITEUP,
            ],
            artifact_refs=[ArtifactRef(kind="analysis_report", uri="artifact://analysis.md")],
            evidence_refs=["artifact://analysis.md"],
            policy_snapshot_hash="policy-hash",
        )
        gate = ResearchPhaseGate(
            phase=ResearchPhase.WRITEUP,
            required_artifact_kinds=["analysis_report"],
            required_evidence_claim_ids=["claim-safe", "claim-risky"],
            forbidden_evidence_labels=["misleading"],
        )
        ledger = EvidenceLedger(
            entries=[
                EvidenceEntry(
                    entry_id="poisoned",
                    kind=EvidenceKind.SOURCE,
                    source_ref="source://poisoned",
                    status=EvidenceStatus.QUARANTINED,
                    labels=["misleading"],
                )
            ],
            claims=[
                EvidenceClaim(
                    claim_id="claim-risky",
                    statement="This claim is backed by quarantined evidence.",
                    cited_entry_ids=["poisoned"],
                )
            ],
        )

        report = ResearchSessionVerifier().evaluate(
            session,
            phase_gates=[gate],
            evidence_ledger=ledger,
        )

        self.assertFalse(report.phase_gate_passed)
        self.assertFalse(report.evidence_ledger_sound)
        self.assertEqual(report.missing_evidence_claim_ids, ["claim-safe"])
        self.assertIn("claim-risky", report.unsupported_evidence_claim_ids)
        self.assertIn("missing required evidence claim for writeup: claim-safe", report.failures)
        self.assertIn("unsupported evidence claim for writeup: claim-risky", report.failures)

    def test_research_session_verifier_flags_invalid_phase_path_and_missing_evidence(self):
        session = ResearchSession(
            session_id="research-2",
            runtime_task_id="task",
            goal="skip steps",
            current_phase=ResearchPhase.WRITEUP,
            phase_history=[ResearchPhase.INTAKE, ResearchPhase.WRITEUP],
        )
        gate = ResearchPhaseGate(
            phase=ResearchPhase.WRITEUP,
            required_artifact_kinds=["paper_shortlist", "metric"],
            required_transition_labels=["paper_scan", "run_experiment"],
            require_validation_receipt=True,
            require_review_ref=True,
        )

        report = ResearchSessionVerifier().evaluate(session, phase_gates=[gate])

        self.assertFalse(report.phase_path_valid)
        self.assertFalse(report.phase_gate_passed)
        self.assertIn("invalid research phase transition: intake -> writeup", report.failures)
        self.assertEqual(report.missing_artifact_kinds, ["paper_shortlist", "metric"])
        self.assertEqual(report.missing_transition_labels, ["paper_scan", "run_experiment"])
        self.assertTrue(report.missing_validation_receipt)
        self.assertTrue(report.missing_review_ref)

    def test_research_session_from_state_preserves_runtime_artifacts_and_policy_hash(self):
        state = RuntimeState(
            task_id="task",
            session_id="session",
            run_id="run",
            goal="state session",
            policy_snapshot={"allowed_tools": ["paper_scan"]},
            metadata={
                "research_phase": ResearchPhase.PAPER_SCAN,
                "evidence_refs": ["source://paper"],
                "transition_labels": ["paper_scan"],
            },
        )
        state.artifact_refs.append(ArtifactRef(kind="paper_shortlist", uri="artifact://papers.json"))

        session = research_session_from_state(state)

        self.assertEqual(session.runtime_task_id, "task")
        self.assertEqual(session.current_phase, ResearchPhase.PAPER_SCAN)
        self.assertEqual(session.artifact_refs[0].kind, "paper_shortlist")
        self.assertEqual(session.evidence_refs, ["source://paper"])
        self.assertEqual(session.transition_labels, ["paper_scan"])
        self.assertIsNotNone(session.policy_snapshot_hash)

    def test_research_session_audit_bridge_binds_phase_gate_to_obligation_map(self):
        events = [
            TraceEvent(
                event_id="e1",
                task_id="task",
                run_id="run",
                cursor="after:paper_scan",
                kind="tool_completed",
                data={"tool": "paper_scan", "actor": "paper-agent", "artifact_refs": ["artifact://papers.json"]},
            ),
            TraceEvent(
                event_id="e2",
                task_id="task",
                run_id="run",
                cursor="after:run_experiment",
                kind="tool_completed",
                data={"tool": "run_experiment", "actor": "experiment-agent", "artifact_refs": ["artifact://metric.json"]},
            ),
            TraceEvent(
                event_id="e3",
                task_id="task",
                run_id="run",
                cursor="after:peer_review",
                kind="tool_completed",
                data={"tool": "peer_review", "actor": "reviewer-agent", "artifact_refs": ["artifact://analysis.md"]},
            ),
        ]
        graph = TransitionGraph.from_events(events)
        session = ResearchSession(
            session_id="research-bridge",
            runtime_task_id="task",
            goal="bridge phase gate",
            current_phase=ResearchPhase.WRITEUP,
            phase_history=[
                ResearchPhase.INTAKE,
                ResearchPhase.PAPER_SCAN,
                ResearchPhase.HYPOTHESIS,
                ResearchPhase.EXPERIMENT_PLAN,
                ResearchPhase.EXPERIMENT_RUN,
                ResearchPhase.ANALYSIS,
                ResearchPhase.REVIEW,
                ResearchPhase.WRITEUP,
            ],
            artifact_refs=[
                ArtifactRef(kind="paper_shortlist", uri="artifact://papers.json"),
                ArtifactRef(kind="hypothesis", uri="artifact://hypothesis.md"),
                ArtifactRef(kind="metric", uri="artifact://metric.json"),
                ArtifactRef(kind="analysis_report", uri="artifact://analysis.md"),
            ],
            evidence_refs=["source://paper-a"],
            transition_unit_ids=["e1", "e2", "e3"],
            transition_labels=["paper_scan", "run_experiment", "peer_review"],
            memory_record_ids=["metric-belief"],
            validation_receipt_refs=["receipt://metric-check"],
            review_refs=["review://virtual-reviewer"],
            policy_snapshot_hash="policy-hash",
        )
        gate = ResearchPhaseGate(
            phase=ResearchPhase.WRITEUP,
            required_artifact_kinds=["paper_shortlist", "hypothesis", "metric", "analysis_report"],
            required_transition_labels=["paper_scan", "run_experiment", "peer_review"],
            required_memory_record_ids=["metric-belief"],
            required_evidence_claim_ids=["claim-writeup-supported"],
            forbidden_evidence_labels=["misleading"],
            require_validation_receipt=True,
            require_review_ref=True,
        )
        ledger = EvidenceLedger(
            entries=[
                EvidenceEntry(
                    entry_id="analysis-a",
                    kind=EvidenceKind.ARTIFACT,
                    source_ref="artifact://analysis.md",
                    labels=["analysis"],
                )
            ],
            claims=[
                EvidenceClaim(
                    claim_id="claim-writeup-supported",
                    statement="The writeup is backed by analysis evidence.",
                    cited_entry_ids=["analysis-a"],
                    required_labels=["analysis"],
                )
            ],
        )

        report = ResearchSessionAuditBridge().evaluate(
            session,
            graph,
            phase_gates=[gate],
            evidence_ledger=ledger,
            phase_actors={ResearchPhase.WRITEUP: "reviewer-agent"},
            candidate_actor_scores={ResearchPhase.WRITEUP: {"reviewer-agent": 0.9, "paper-agent": 0.4}},
        )

        self.assertTrue(report.session_report.phase_gate_passed)
        self.assertTrue(report.sound)
        self.assertTrue(report.stable)
        self.assertTrue(report.ready_for_phase_exit)
        self.assertEqual(report.actor, "reviewer-agent")
        self.assertEqual(report.transition_unit_id, "e3")
        self.assertEqual(report.obligation_report.actor_load, {"reviewer-agent": 1})
        self.assertIn("artifact://analysis.md", report.bridge_evidence_refs)
        self.assertIn("claim://claim-writeup-supported", report.bridge_evidence_refs)
        self.assertEqual(len(report.bridge_fingerprint), 64)

    def test_research_session_audit_bridge_catches_missing_transition_evidence(self):
        graph = TransitionGraph.from_events(
            [
                TraceEvent(
                    event_id="e1",
                    task_id="task",
                    run_id="run",
                    cursor="after:paper_scan",
                    kind="tool_completed",
                    data={"tool": "paper_scan", "artifact_refs": ["artifact://papers.json"]},
                )
            ]
        )
        session = ResearchSession(
            session_id="research-missing-link",
            runtime_task_id="task",
            goal="bridge missing transition",
            current_phase=ResearchPhase.WRITEUP,
            phase_history=[
                ResearchPhase.INTAKE,
                ResearchPhase.PAPER_SCAN,
                ResearchPhase.HYPOTHESIS,
                ResearchPhase.EXPERIMENT_PLAN,
                ResearchPhase.EXPERIMENT_RUN,
                ResearchPhase.ANALYSIS,
                ResearchPhase.REVIEW,
                ResearchPhase.WRITEUP,
            ],
            artifact_refs=[
                ArtifactRef(kind="paper_shortlist", uri="artifact://papers.json"),
                ArtifactRef(kind="hypothesis", uri="artifact://hypothesis.md"),
                ArtifactRef(kind="metric", uri="artifact://metric.json"),
                ArtifactRef(kind="analysis_report", uri="artifact://analysis.md"),
            ],
            evidence_refs=["source://paper-a"],
            transition_unit_ids=["missing-review-transition"],
            transition_labels=["paper_scan", "run_experiment", "peer_review"],
            memory_record_ids=["metric-belief"],
            validation_receipt_refs=["receipt://metric-check"],
            review_refs=["review://virtual-reviewer"],
            policy_snapshot_hash="policy-hash",
        )
        gate = ResearchPhaseGate(
            phase=ResearchPhase.WRITEUP,
            required_artifact_kinds=["paper_shortlist", "hypothesis", "metric", "analysis_report"],
            required_transition_labels=["paper_scan", "run_experiment", "peer_review"],
            required_memory_record_ids=["metric-belief"],
            require_validation_receipt=True,
            require_review_ref=True,
        )

        report = ResearchSessionAuditBridge().evaluate(session, graph, phase_gates=[gate])

        self.assertTrue(report.session_report.phase_gate_passed)
        self.assertFalse(report.sound)
        self.assertFalse(report.ready_for_phase_exit)
        self.assertIsNone(report.transition_unit_id)
        self.assertIn(
            "satisfied obligation has no satisfying transition: research-missing-link:writeup:phase_gate",
            report.obligation_report.failures,
        )

    def test_evidence_ledger_accepts_source_backed_claims(self):
        ledger = EvidenceLedger(
            entries=[
                EvidenceEntry(
                    entry_id="paper-a",
                    kind=EvidenceKind.SOURCE,
                    source_ref="https://arxiv.org/abs/example",
                    content_hash=hash_payload("paper abstract"),
                    labels=["peer_reviewed", "source"],
                ),
                EvidenceEntry(
                    entry_id="analysis-a",
                    kind=EvidenceKind.DERIVED,
                    source_ref="artifact://analysis.md",
                    content_hash=hash_payload("analysis"),
                    labels=["analysis"],
                    parent_entry_ids=["paper-a"],
                    produced_by_transition_id="unit-analysis",
                ),
            ],
            claims=[
                EvidenceClaim(
                    claim_id="claim-analysis-supported",
                    statement="The writeup claim is supported by a source-backed analysis artifact.",
                    cited_entry_ids=["analysis-a"],
                    required_labels=["analysis"],
                )
            ],
        )

        report = ledger.evaluate(
            required_claim_ids=["claim-analysis-supported"],
            forbidden_evidence_labels=["misleading"],
        )

        self.assertTrue(report.sound)
        self.assertEqual(report.active_entry_count, 2)
        self.assertEqual(ledger.lineage_for("analysis-a"), ["paper-a", "analysis-a"])
        self.assertEqual(len(report.ledger_fingerprint), 64)

    def test_evidence_ledger_catches_missing_quarantined_and_orphaned_evidence(self):
        ledger = EvidenceLedger(
            entries=[
                EvidenceEntry(
                    entry_id="misleading-source",
                    kind=EvidenceKind.SOURCE,
                    source_ref="source://poisoned",
                    status=EvidenceStatus.QUARANTINED,
                    labels=["misleading"],
                ),
                EvidenceEntry(
                    entry_id="orphan-analysis",
                    kind=EvidenceKind.DERIVED,
                    source_ref="artifact://analysis.md",
                    parent_entry_ids=["missing-parent"],
                ),
            ],
            claims=[
                EvidenceClaim(
                    claim_id="claim-risky",
                    statement="A risky claim cites quarantined and missing evidence.",
                    cited_entry_ids=["misleading-source", "missing-source"],
                )
            ],
        )

        report = ledger.evaluate(
            required_claim_ids=["claim-risky", "claim-required"],
            forbidden_evidence_labels=["misleading"],
        )

        self.assertFalse(report.sound)
        self.assertEqual(report.missing_required_claim_ids, ["claim-required"])
        self.assertIn("claim-risky", report.unsupported_claim_ids)
        self.assertIn("missing-source", report.missing_citation_ids)
        self.assertIn("misleading-source", report.inactive_citation_ids)
        self.assertIn("claim-risky", report.forbidden_label_claim_ids)
        self.assertIn("orphan-analysis", report.orphan_derived_entry_ids)

    def test_hydration_manifest_accepts_verifiable_research_scene(self):
        state = RuntimeState(
            task_id="task-hydrate",
            session_id="sess-hydrate",
            run_id="run-hydrate",
            goal="resume a governed research scene",
            execution_cursor="after:analysis",
            active_step="analysis",
            process_stage=ProcessStage.ACTIVE,
            policy_snapshot={"allowed_tools": ["read_note"], "require_validation": True},
            checkpoint_ref="task-hydrate/ckpt_000003.json",
            artifact_refs=[ArtifactRef(kind="analysis_report", uri="artifact://analysis.md")],
            trace_id="trace-hydrate",
        )
        events = [
            TraceEvent(
                event_id="event-analysis",
                task_id=state.task_id,
                run_id=state.run_id,
                cursor=state.execution_cursor,
                kind="tool_completed",
                data={"tool": "analysis", "output_hash": "analysis-hash"},
            )
        ]
        memory_record = MemoryRecord(
            record_id="belief-analysis",
            kind=MemoryKind.BELIEF,
            payload={"claim": "analysis is ready"},
            status=MemoryStatus.COMMITTED,
            source_refs=["artifact://analysis.md"],
        )
        ledger = EvidenceLedger(
            entries=[
                EvidenceEntry(
                    entry_id="analysis-entry",
                    kind=EvidenceKind.ARTIFACT,
                    source_ref="artifact://analysis.md",
                    labels=["analysis"],
                )
            ],
            claims=[
                EvidenceClaim(
                    claim_id="claim-analysis-ready",
                    statement="The analysis is ready for writeup.",
                    cited_entry_ids=["analysis-entry"],
                    required_labels=["analysis"],
                )
            ],
        )
        research_session = ResearchSession(
            session_id="research-hydrate",
            runtime_task_id=state.task_id,
            goal=state.goal,
            current_phase=ResearchPhase.WRITEUP,
            phase_history=[
                ResearchPhase.INTAKE,
                ResearchPhase.PAPER_SCAN,
                ResearchPhase.HYPOTHESIS,
                ResearchPhase.EXPERIMENT_PLAN,
                ResearchPhase.EXPERIMENT_RUN,
                ResearchPhase.ANALYSIS,
                ResearchPhase.REVIEW,
                ResearchPhase.WRITEUP,
            ],
            artifact_refs=[ArtifactRef(kind="analysis_report", uri="artifact://analysis.md")],
            memory_record_ids=["belief-analysis"],
            evidence_refs=["artifact://analysis.md"],
            policy_snapshot_hash=hash_payload(state.policy_snapshot),
        )

        builder = HydrationManifestBuilder()
        manifest = builder.dehydrate(
            state,
            events,
            memory_records=[memory_record],
            evidence_ledger=ledger,
            research_session=research_session,
            required_memory_record_ids=["belief-analysis"],
            required_evidence_claim_ids=["claim-analysis-ready"],
            required_artifact_uris=["artifact://analysis.md"],
            forbidden_evidence_labels=["misleading"],
        )
        report = builder.verify(
            manifest,
            state,
            events,
            memory_records=[memory_record],
            evidence_ledger=ledger,
            research_session=research_session,
        )

        self.assertTrue(report.safe_to_hydrate)
        self.assertIn(HydrationSurface.RUNTIME_STATE, report.retained_surfaces)
        self.assertIn(HydrationSurface.EVIDENCE, report.retained_surfaces)
        self.assertIn(HydrationSurface.RESEARCH_SESSION, report.retained_surfaces)
        self.assertEqual(manifest.required_memory_record_ids, ["belief-analysis"])
        self.assertEqual(manifest.required_evidence_claim_ids, ["claim-analysis-ready"])
        self.assertEqual(len(report.report_fingerprint), 64)

    def test_hydration_manifest_blocks_policy_memory_and_evidence_drift(self):
        state = RuntimeState(
            task_id="task-hydrate-drift",
            session_id="sess-hydrate-drift",
            run_id="run-hydrate-drift",
            goal="detect unsafe hydration drift",
            execution_cursor="after:analysis",
            active_step="analysis",
            process_stage=ProcessStage.ACTIVE,
            policy_snapshot={"allowed_tools": ["read_note"], "require_validation": True},
            checkpoint_ref="task-hydrate-drift/ckpt_000003.json",
            artifact_refs=[ArtifactRef(kind="analysis_report", uri="artifact://analysis.md")],
            trace_id="trace-hydrate-drift",
        )
        events = [
            TraceEvent(
                event_id="event-analysis",
                task_id=state.task_id,
                run_id=state.run_id,
                cursor=state.execution_cursor,
                kind="tool_completed",
                data={"tool": "analysis", "output_hash": "analysis-hash"},
            )
        ]
        committed = MemoryRecord(
            record_id="belief-analysis",
            kind=MemoryKind.BELIEF,
            payload={"claim": "analysis is ready"},
            status=MemoryStatus.COMMITTED,
            source_refs=["artifact://analysis.md"],
        )
        ledger = EvidenceLedger(
            entries=[
                EvidenceEntry(
                    entry_id="analysis-entry",
                    kind=EvidenceKind.ARTIFACT,
                    source_ref="artifact://analysis.md",
                    labels=["analysis"],
                )
            ],
            claims=[
                EvidenceClaim(
                    claim_id="claim-analysis-ready",
                    statement="The analysis is ready for writeup.",
                    cited_entry_ids=["analysis-entry"],
                    required_labels=["analysis"],
                )
            ],
        )
        research_session = ResearchSession(
            session_id="research-hydrate-drift",
            runtime_task_id=state.task_id,
            goal=state.goal,
            current_phase=ResearchPhase.WRITEUP,
            phase_history=[ResearchPhase.INTAKE, ResearchPhase.WRITEUP],
            artifact_refs=[ArtifactRef(kind="analysis_report", uri="artifact://analysis.md")],
        )
        builder = HydrationManifestBuilder()
        manifest = builder.dehydrate(
            state,
            events,
            memory_records=[committed],
            evidence_ledger=ledger,
            research_session=research_session,
            required_memory_record_ids=["belief-analysis"],
            required_evidence_claim_ids=["claim-analysis-ready"],
            required_artifact_uris=["artifact://analysis.md"],
        )
        drifted_state = RuntimeState.from_dict(state.to_dict())
        drifted_state.policy_snapshot = {"allowed_tools": ["read_note", "publish"], "require_validation": False}
        staged = MemoryRecord(
            record_id="belief-analysis",
            kind=MemoryKind.BELIEF,
            payload={"claim": "analysis is ready"},
            status=MemoryStatus.STAGED,
            source_refs=["artifact://analysis.md"],
        )
        missing_claim_ledger = EvidenceLedger(entries=list(ledger.entries.values()), claims=[])

        report = builder.verify(
            manifest,
            drifted_state,
            events,
            memory_records=[staged],
            evidence_ledger=missing_claim_ledger,
            research_session=research_session,
        )

        self.assertFalse(report.safe_to_hydrate)
        self.assertIn(HydrationSurface.POLICY, report.drifted_surfaces)
        self.assertIn("belief-analysis", report.unsafe_required_memory_record_ids)
        self.assertIn("claim-analysis-ready", report.missing_required_evidence_claim_ids)
        self.assertIn("hydration surface drifted: memory", report.failures)
        self.assertIn("hydration surface drifted: evidence", report.failures)

    def test_permission_graph_blocks_tainted_output_until_sanitized(self):
        graph = PermissionGraph(
            grants=[
                PermissionGrant(
                    grant_id="write-report",
                    subject="research-agent",
                    effects=[ToolEffect.WRITE],
                    resource_pattern="artifact://reports/*",
                    forbidden_input_labels=["untrusted"],
                    allowed_input_labels=["trusted", "sanitized"],
                )
            ]
        )
        graph.label_context("paper:web", ["untrusted"])
        graph.label_context("paper:sanitized", ["sanitized"])

        blocked = graph.authorize_action(
            subject="research-agent",
            effect=ToolEffect.WRITE,
            resource="artifact://reports/draft.md",
            input_contexts=["paper:web"],
        )
        allowed = graph.authorize_action(
            subject="research-agent",
            effect=ToolEffect.WRITE,
            resource="artifact://reports/draft.md",
            input_contexts=["paper:sanitized"],
        )

        self.assertFalse(blocked.allowed)
        self.assertIn("grant write-report: forbidden input labels present: untrusted", blocked.failures)
        self.assertTrue(allowed.allowed)
        self.assertEqual(allowed.matched_grant_ids, ["write-report"])
        self.assertEqual(allowed.input_labels, ["sanitized"])

    def test_permission_graph_requires_fresh_authority_witness_for_commit(self):
        graph = PermissionGraph(
            grants=[
                PermissionGrant(
                    grant_id="publish-report",
                    subject="research-agent",
                    effects=[ToolEffect.EXTERNAL],
                    resource_pattern="external://publisher/*",
                    requires_witness=True,
                )
            ],
            witnesses=[
                AuthorityWitness(
                    witness_id="approval-1",
                    subject="research-agent",
                    effect=ToolEffect.EXTERNAL,
                    resource_pattern="external://publisher/*",
                    issued_at_version=2,
                    expires_after_version=3,
                )
            ],
        )

        fresh = graph.authorize_action(
            subject="research-agent",
            effect=ToolEffect.EXTERNAL,
            resource="external://publisher/arxiv",
            checkpoint_version=3,
        )
        expired = graph.authorize_action(
            subject="research-agent",
            effect=ToolEffect.EXTERNAL,
            resource="external://publisher/arxiv",
            checkpoint_version=4,
        )

        self.assertTrue(fresh.allowed)
        self.assertEqual(fresh.witness_ids, ["approval-1"])
        self.assertFalse(expired.allowed)
        self.assertIn("grant publish-report: no valid authority witness for grant: publish-report", expired.failures)
        self.assertIn("fingerprint", fresh.receipt_payload())
        self.assertEqual(len(graph.fingerprint()), 64)

    def test_intervention_replay_injects_fault_and_splits_cached_prefix(self):
        baseline = [
            TraceEvent(
                event_id="e1",
                task_id="task",
                run_id="run",
                cursor="after:read",
                kind="tool_completed",
                data={"tool": "read_note", "args_hash": "args-a", "output_hash": "output-a"},
            ),
            TraceEvent(
                event_id="e2",
                task_id="task",
                run_id="run",
                cursor="after:mcp",
                kind="tool_completed",
                data={"tool": "mcp_search", "args_hash": "args-b", "output_hash": "output-b"},
            ),
        ]
        workbench = InterventionReplayWorkbench()
        spec = InterventionSpec(
            fault_kind="stale_tool_response",
            target_tool="mcp_search",
            response_overrides={"output_hash": "stale-output"},
            metadata={"source": "AgentCheck-style fault"},
        )

        faulted = workbench.inject_fault(baseline, spec)
        report = workbench.evaluate(baseline, spec)

        self.assertEqual(faulted[1].data["output_hash"], "stale-output")
        self.assertEqual(faulted[1].data["intervention_fingerprint"], spec.fingerprint())
        self.assertEqual(report.cached_prefix_count, 1)
        self.assertEqual(report.live_suffix_count, 1)
        self.assertEqual(report.faulted_report.divergence_reason, "output_hash differs")
        self.assertEqual(len(report.faulted_fingerprint), 64)

    def test_intervention_replay_marks_mitigation_effective_when_prefix_recovers(self):
        baseline = [
            TraceEvent(
                event_id="e1",
                task_id="task",
                run_id="run",
                cursor="after:read",
                kind="tool_completed",
                data={"tool": "read_note", "args_hash": "args-a", "output_hash": "output-a"},
            ),
            TraceEvent(
                event_id="e2",
                task_id="task",
                run_id="run",
                cursor="after:mcp",
                kind="tool_completed",
                data={"tool": "mcp_search", "args_hash": "args-b", "output_hash": "output-b"},
            ),
        ]
        spec = InterventionSpec(
            fault_kind="poisoned_description",
            target_tool="mcp_search",
            response_overrides={"output_hash": "poisoned-output"},
        )

        report = InterventionReplayWorkbench().evaluate(baseline, spec, mitigated=baseline)

        self.assertTrue(report.mitigation_effective)
        self.assertIsNone(report.mitigated_report.divergence_index)
        self.assertIn("mitigation recovered more of the baseline prefix", report.notes)

    def test_harness_diagnostic_maps_replay_divergence_to_transition_unit(self):
        baseline = [
            TraceEvent(
                event_id="e1",
                task_id="task",
                run_id="run",
                cursor="after:paper_scan",
                kind="tool_completed",
                data={"tool": "paper_scan", "args_hash": "args-a", "output_hash": "output-a"},
            ),
            TraceEvent(
                event_id="e2",
                task_id="task",
                run_id="run",
                cursor="after:run_experiment",
                kind="tool_completed",
                data={
                    "tool": "run_experiment",
                    "args_hash": "args-b",
                    "output_hash": "output-b",
                    "depends_on": ["e1"],
                    "artifact_refs": ["artifact://metric.json"],
                    "trace_envelope": {
                        "provider_fingerprint": "provider-a",
                        "policy_fingerprint": "policy-a",
                        "tool_contract_fingerprint": "tool-a",
                        "skill_manifest_fingerprint": "skill-a",
                        "input_hash": "input-b",
                        "output_hash": "output-b",
                    },
                },
            ),
        ]
        actual = [
            baseline[0],
            TraceEvent(
                event_id="e2",
                task_id="task",
                run_id="run",
                cursor="after:run_experiment",
                kind="tool_completed",
                data={
                    "tool": "run_experiment",
                    "args_hash": "args-b",
                    "output_hash": "stale-output",
                    "depends_on": ["e1"],
                    "artifact_refs": ["artifact://metric.json"],
                    "trace_envelope": {
                        "provider_fingerprint": "provider-a",
                        "policy_fingerprint": "policy-a",
                        "tool_contract_fingerprint": "tool-a",
                        "skill_manifest_fingerprint": "skill-a",
                        "input_hash": "input-b",
                        "output_hash": "stale-output",
                    },
                },
            ),
        ]

        report = HarnessDiagnosticWorkbench().diagnose(baseline, actual)

        self.assertFalse(report.replay_passed)
        self.assertEqual(report.divergence_unit_id, "e2")
        self.assertEqual(report.divergence_label, "run_experiment")
        self.assertEqual(report.cached_prefix_unit_ids, ["e1"])
        self.assertEqual(report.live_suffix_unit_ids, ["e2"])
        self.assertEqual(report.critical_transition_chain, ["e1", "e2"])
        self.assertIn("tool_output_or_artifact", report.suspect_surfaces)
        self.assertEqual(report.affected_artifact_refs, ["artifact://metric.json"])
        self.assertIn(
            "re-capture the tool output/artifact snapshot and replay from the cached prefix",
            report.repair_hints,
        )
        self.assertEqual(len(report.diagnosis_fingerprint), 64)

    def test_harness_diagnostic_surfaces_policy_and_skill_manifest_drift(self):
        baseline = [
            TraceEvent(
                event_id="e1",
                task_id="task",
                run_id="run",
                cursor="after:publish",
                kind="tool_completed",
                data={
                    "tool": "publish_report",
                    "args_hash": "args-a",
                    "output_hash": "output-a",
                    "trace_envelope_fingerprint": "envelope-a",
                    "trace_envelope": {
                        "provider_fingerprint": "provider-a",
                        "policy_fingerprint": "policy-a",
                        "skill_manifest_fingerprint": "skill-a",
                        "input_hash": "input-a",
                        "output_hash": "output-a",
                    },
                },
            )
        ]
        actual = [
            TraceEvent(
                event_id="e1",
                task_id="task",
                run_id="run",
                cursor="after:publish",
                kind="tool_completed",
                data={
                    "tool": "publish_report",
                    "args_hash": "args-a",
                    "output_hash": "output-a",
                    "trace_envelope_fingerprint": "envelope-b",
                    "trace_envelope": {
                        "provider_fingerprint": "provider-a",
                        "policy_fingerprint": "policy-b",
                        "skill_manifest_fingerprint": "skill-b",
                        "input_hash": "input-a",
                        "output_hash": "output-a",
                    },
                },
            )
        ]

        report = HarnessDiagnosticWorkbench().diagnose(baseline, actual)

        self.assertEqual(report.divergence_unit_id, "e1")
        self.assertIn("trace_contract", report.suspect_surfaces)
        self.assertIn("harness_policy", report.suspect_surfaces)
        self.assertIn("skill_manifest", report.suspect_surfaces)
        self.assertIn("trace_envelope.policy_fingerprint", report.fingerprint_drift)
        self.assertIn("trace_envelope.skill_manifest_fingerprint", report.fingerprint_drift)
        self.assertIn("treat policy snapshot drift as a resume gate before continuing the run", report.repair_hints)
        self.assertIn("hold skill promotion until the manifest fingerprint passes replay regression", report.repair_hints)

    def test_harness_diagnostic_surfaces_evidence_receipt_drift(self):
        baseline = [
            TraceEvent(
                event_id="e1",
                task_id="task",
                run_id="run",
                cursor="after:writeup",
                kind="tool_completed",
                data={
                    "tool": "write_report",
                    "args_hash": "args-a",
                    "output_hash": "output-a",
                    "trace_envelope_fingerprint": "envelope-a",
                    "trace_envelope": {
                        "provider_fingerprint": "provider-a",
                        "policy_fingerprint": "policy-a",
                        "skill_manifest_fingerprint": "skill-a",
                        "evidence_ledger_fingerprint": "evidence-a",
                        "evidence_claim_ids": ["claim-a"],
                        "input_hash": "input-a",
                        "output_hash": "output-a",
                    },
                },
            )
        ]
        actual = [
            TraceEvent(
                event_id="e1",
                task_id="task",
                run_id="run",
                cursor="after:writeup",
                kind="tool_completed",
                data={
                    "tool": "write_report",
                    "args_hash": "args-a",
                    "output_hash": "output-a",
                    "trace_envelope_fingerprint": "envelope-b",
                    "trace_envelope": {
                        "provider_fingerprint": "provider-a",
                        "policy_fingerprint": "policy-a",
                        "skill_manifest_fingerprint": "skill-a",
                        "evidence_ledger_fingerprint": "evidence-b",
                        "evidence_claim_ids": ["claim-b"],
                        "input_hash": "input-a",
                        "output_hash": "output-a",
                    },
                },
            )
        ]

        report = HarnessDiagnosticWorkbench().diagnose(baseline, actual)

        self.assertIn("trace_contract", report.suspect_surfaces)
        self.assertIn("evidence_ledger", report.suspect_surfaces)
        self.assertIn("evidence_claim", report.suspect_surfaces)
        self.assertIn("trace_envelope.evidence_ledger_fingerprint", report.fingerprint_drift)
        self.assertIn("trace_envelope.evidence_claim_ids", report.fingerprint_drift)

    def test_transition_graph_identifies_critical_failure_chain_and_branch_point(self):
        events = [
            TraceEvent(
                event_id="e1",
                task_id="task",
                run_id="run",
                cursor="after:paper_scan",
                kind="tool_completed",
                data={"tool": "paper_scan"},
            ),
            TraceEvent(
                event_id="e2",
                task_id="task",
                run_id="run",
                cursor="after:run_experiment",
                kind="tool_completed",
                data={"tool": "run_experiment", "depends_on": ["e1"]},
            ),
            TraceEvent(
                event_id="e3",
                task_id="task",
                run_id="run",
                cursor="after:parallel_review",
                kind="tool_completed",
                data={"tool": "parallel_review", "depends_on": ["e1"]},
            ),
            TraceEvent(
                event_id="e4",
                task_id="task",
                run_id="run",
                cursor="after:publish_report",
                kind="tool_failed",
                data={"tool": "publish_report", "depends_on": ["e2"], "reason": "missing validation receipt"},
            ),
        ]

        graph = TransitionGraph.from_events(events)
        report = graph.diagnose("e4")

        self.assertEqual(report.critical_transition_chain, ["e1", "e2", "e4"])
        self.assertEqual(report.critical_transition_subgraph, ["e1", "e2", "e4"])
        self.assertIn("e1", report.branch_points)
        self.assertEqual(report.target_status, "failed")
        self.assertEqual(report.target_label, "publish_report")
        self.assertEqual(len(graph.fingerprint()), 64)
        self.assertEqual(len(report.chain_fingerprint), 64)

    def test_transition_verifier_defaults_to_latest_failed_transition(self):
        events = [
            TraceEvent(event_id="e1", task_id="task", run_id="run", cursor="c1", kind="tool_completed", data={"tool": "paper_scan"}),
            TraceEvent(event_id="e2", task_id="task", run_id="run", cursor="c2", kind="tool_blocked", data={"tool": "run_experiment"}),
        ]

        report = TransitionVerifier().compare(events)

        self.assertEqual(report.target_unit_id, "e2")
        self.assertEqual(report.critical_transition_chain, ["e1", "e2"])
        self.assertEqual(report.target_status, "failed")

    def test_obligation_audit_map_accepts_evidence_backed_transition(self):
        events = [
            TraceEvent(
                event_id="e1",
                task_id="task",
                run_id="run",
                cursor="c1",
                kind="tool_completed",
                data={"tool": "metric_check", "actor": "reviewer", "artifact_refs": ["artifact://metric.json"]},
            )
        ]
        graph = TransitionGraph.from_events(events)
        audit = ObligationAuditMap(
            obligations=[
                Obligation(
                    obligation_id="verify_metric",
                    actor="reviewer",
                    description="Verify metric artifact before report.",
                    status=ObligationStatus.SATISFIED,
                    required_transition_labels=["metric_check"],
                )
            ],
            links=[
                AuditLink(
                    obligation_id="verify_metric",
                    transition_unit_id="e1",
                    evidence_refs=["artifact://metric.json"],
                )
            ],
        )

        report = audit.evaluate(graph)

        self.assertTrue(report.sound)
        self.assertTrue(report.stable)
        self.assertEqual(report.actor_load, {"reviewer": 1})
        self.assertEqual(len(report.audit_fingerprint), 64)

    def test_obligation_audit_map_flags_assignment_instability_and_missing_evidence(self):
        events = [
            TraceEvent(event_id="e1", task_id="task", run_id="run", cursor="c1", kind="tool_completed", data={"tool": "metric_check"})
        ]
        graph = TransitionGraph.from_events(events)
        audit = ObligationAuditMap(
            obligations=[
                Obligation(
                    obligation_id="verify_metric",
                    actor="paper_agent",
                    description="Verify metric artifact before report.",
                    status=ObligationStatus.SATISFIED,
                    required_transition_labels=["metric_check"],
                    candidate_actor_scores={"paper_agent": 0.4, "reviewer_agent": 0.9},
                )
            ],
            links=[AuditLink(obligation_id="verify_metric", transition_unit_id="e1")],
        )

        report = audit.evaluate(graph)

        self.assertFalse(report.sound)
        self.assertFalse(report.stable)
        self.assertEqual(report.unsupported_obligation_ids, ["verify_metric"])
        self.assertIn("satisfied obligation lacks evidence refs: verify_metric", report.failures)
        self.assertIn(
            "assignment unstable: verify_metric assigned paper_agent (0.4) but reviewer_agent scores 0.9",
            report.assignment_warnings,
        )

    def test_memory_commit_protocol_blocks_uncommitted_beliefs(self):
        protocol = MemoryCommitProtocol()
        protocol.begin_transaction(transaction_id="tx1", checkpoint_version=1)
        staged = protocol.stage_record(
            "tx1",
            record_id="belief1",
            kind=MemoryKind.BELIEF,
            payload={"claim": "baseline improves metric"},
            source_refs=["trace://event1"],
        )

        safety = protocol.safety_gate([staged.record_id])

        self.assertFalse(safety.safe)
        self.assertEqual(staged.status, MemoryStatus.STAGED)
        self.assertIn("record is not committed: belief1 (staged)", safety.failures)

    def test_memory_commit_protocol_validates_and_commits_belief(self):
        protocol = MemoryCommitProtocol()
        protocol.begin_transaction(transaction_id="tx1", checkpoint_version=1)
        protocol.stage_record(
            "tx1",
            record_id="belief1",
            kind=MemoryKind.BELIEF,
            payload={"claim": "baseline improves metric"},
            source_refs=["trace://event1"],
        )
        protocol.validate_record(
            "belief1",
            ValidationReceipt(
                validator="metric-check",
                passed=True,
                reasons=["metric artifact present"],
                evidence_refs=["artifact://metric.json"],
                checkpoint_version=2,
            ),
        )

        report = protocol.commit("tx1", checkpoint_version=2)
        safety = protocol.safety_gate(["belief1"])

        self.assertTrue(report.committed)
        self.assertEqual(report.committed_record_ids, ["belief1"])
        self.assertTrue(safety.safe)
        self.assertEqual(protocol.records["belief1"].status, MemoryStatus.COMMITTED)
        self.assertEqual(len(report.fingerprint()), 64)

    def test_memory_commit_protocol_rejects_unvalidated_commit(self):
        protocol = MemoryCommitProtocol()
        protocol.begin_transaction(transaction_id="tx1", checkpoint_version=1)
        protocol.stage_record(
            "tx1",
            record_id="belief1",
            kind=MemoryKind.BELIEF,
            payload={"claim": "unverified"},
        )

        report = protocol.commit("tx1", checkpoint_version=1)

        self.assertFalse(report.committed)
        self.assertEqual(report.rejected_record_ids, ["belief1"])
        self.assertIn("record has no passing validation receipt: belief1", report.failures)
        self.assertEqual(protocol.transactions["tx1"].status, "rejected")

    def test_memory_commit_protocol_cascade_retracts_derived_records(self):
        protocol = MemoryCommitProtocol()
        protocol.begin_transaction(transaction_id="tx1", checkpoint_version=1)
        protocol.stage_record(
            "tx1",
            record_id="source",
            kind=MemoryKind.OBSERVATION,
            payload={"paper": "A"},
        )
        protocol.validate_record("source", ValidationReceipt(validator="source-check", passed=True))
        protocol.commit("tx1", checkpoint_version=1)

        protocol.begin_transaction(transaction_id="tx2", checkpoint_version=2)
        protocol.stage_record(
            "tx2",
            record_id="derived",
            kind=MemoryKind.BELIEF,
            payload={"claim": "derived from source"},
            parent_record_ids=["source"],
        )
        protocol.validate_record("derived", ValidationReceipt(validator="derivation-check", passed=True))
        protocol.commit("tx2", checkpoint_version=2)

        retract = protocol.cascade_retract("source", reason="source contradicted")
        safety = protocol.safety_gate(["derived"])

        self.assertEqual(retract.retracted_record_ids, ["source", "derived"])
        self.assertEqual(protocol.records["source"].status, MemoryStatus.RETRACTED)
        self.assertEqual(protocol.records["derived"].status, MemoryStatus.RETRACTED)
        self.assertFalse(safety.safe)
        self.assertIn("record is not committed: derived (retracted)", safety.failures)

    def test_decision_memory_projection_selects_committed_task_relevant_records(self):
        protocol = MemoryCommitProtocol()
        protocol.begin_transaction(transaction_id="tx1", checkpoint_version=1)
        protocol.stage_record(
            "tx1",
            record_id="metric-belief",
            kind=MemoryKind.BELIEF,
            payload={"claim": "experiment metric is ready"},
            source_refs=["artifact://metric.json"],
        )
        protocol.validate_record("metric-belief", ValidationReceipt(validator="metric-check", passed=True))
        protocol.commit("tx1", checkpoint_version=1)

        protocol.begin_transaction(transaction_id="tx2", checkpoint_version=2)
        protocol.stage_record(
            "tx2",
            record_id="draft-belief",
            kind=MemoryKind.BELIEF,
            payload={"claim": "draft report exists"},
            source_refs=["artifact://draft.md"],
        )

        projection = DecisionMemoryProjection().project(
            protocol.records.values(),
            task_context={"goal": "publish metric report", "query_terms": ["metric"]},
            required_kinds=[MemoryKind.BELIEF],
        )

        self.assertEqual(projection.selected_record_ids, ["metric-belief"])
        self.assertEqual(projection.excluded_record_ids, ["draft-belief"])
        self.assertIn("record is not committed: draft-belief (staged)", projection.exclusion_reasons["draft-belief"])
        self.assertEqual(projection.selected_record_count, 1)
        self.assertEqual(len(projection.projection_fingerprint), 64)


if __name__ == "__main__":
    unittest.main()
