from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


class FseTaskFamily:
    ISSUE_TO_PATCH = "issue_to_patch"
    ARTIFACT_REPLICATION = "artifact_replication"
    INCIDENT_RCA = "incident_rca"


class BaselineKind:
    RAW_REACT = "raw_react"
    CHECKPOINT_ONLY = "checkpoint_only"
    LANGGRAPH_STYLE = "langgraph_style"
    OPENHANDS_STYLE = "openhands_style"
    AGENTDIET_STYLE = "agentdiet_style"


class FaultKind:
    INTERRUPTION = "interruption"
    COMPACTION_DRIFT = "compaction_drift"
    CONTEXT_MANAGER_DROPPED_PIN = "context_manager_dropped_pin"
    STALE_TOOL_OUTPUT = "stale_tool_output"
    MISSING_ARTIFACT = "missing_artifact"
    BENCHMARK_ORACLE_DRIFT = "benchmark_oracle_drift"
    QUARANTINED_EVIDENCE = "quarantined_evidence"
    EXPIRED_APPROVAL = "expired_approval"
    WRONG_MEMORY_COMMIT = "wrong_memory_commit"
    MEMORY_INTERFERENCE = "memory_interference"
    RETRIEVAL_COMPONENT_SHIFT = "retrieval_component_shift"
    SILENT_EVIDENCE_DEFECT = "silent_evidence_defect"
    OFFICIAL_EXECUTION_RECEIPT_DRIFT = "official_execution_receipt_drift"
    PROVIDER_SWITCH = "provider_switch"
    TOOL_SCHEMA_DRIFT = "tool_schema_drift"
    EVIDENCE_RECEIPT_DRIFT = "evidence_receipt_drift"


class AblationKind:
    NO_HYDRATION_MANIFEST = "no_hydration_manifest"
    NO_MEMORY_COMMIT = "no_memory_commit"
    NO_EVIDENCE_LEDGER = "no_evidence_ledger"
    NO_TRANSITION_GRAPH = "no_transition_graph"
    NO_COMPACTION_VERIFIER = "no_compaction_verifier"
    NO_TRACE_RECEIPT = "no_trace_receipt"
    NO_PERMISSION_GRAPH = "no_permission_graph"


class MetricKind:
    EFFECTIVENESS = "effectiveness"
    SAFETY = "safety"
    REPLAY = "replay"
    LOCALIZATION = "localization"
    COST = "cost"
    USABILITY = "usability"


@dataclass(frozen=True, slots=True)
class BenchmarkMetricSpec:
    metric_id: str
    name: str
    kind: str
    rqs: list[str]
    description: str
    higher_is_better: bool = True
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchmarkTaskSpec:
    task_id: str
    family: str
    title: str
    description: str
    steps: list[str]
    required_artifact_kinds: list[str]
    required_evidence_claim_ids: list[str]
    required_memory_record_ids: list[str] = field(default_factory=list)
    required_transition_labels: list[str] = field(default_factory=list)
    recommended_metrics: list[str] = field(default_factory=list)
    recommended_baselines: list[str] = field(default_factory=list)
    recommended_faults: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BaselineSpec:
    baseline_id: str
    name: str
    comparison_role: str
    strengths: list[str]
    caveats: list[str]
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FaultScenarioSpec:
    fault_id: str
    kind: str
    title: str
    description: str
    affected_surfaces: list[str]
    expected_detector: str
    mitigation_hint: str
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AblationSpec:
    ablation_id: str
    disabled_modules: list[str]
    expected_regression: str
    related_rqs: list[str]
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RelatedWorkCluster:
    cluster_id: str
    title: str
    papers: list[str]
    design_implication: str
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchmarkRQ:
    rq_id: str
    question: str
    supported_task_families: list[str]
    key_metrics: list[str]
    suggested_baselines: list[str]
    suggested_faults: list[str]
    suggested_ablations: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FseBenchmarkPlan:
    plan_id: str
    title: str
    target_venue: str
    deadline: str
    paper_positioning: str
    task_families: list[str]
    tasks: list[BenchmarkTaskSpec]
    baselines: list[BaselineSpec]
    fault_scenarios: list[FaultScenarioSpec]
    ablations: list[AblationSpec]
    metrics: list[BenchmarkMetricSpec]
    related_work_clusters: list[RelatedWorkCluster]
    research_questions: list[BenchmarkRQ]
    data_availability_statement: str
    replication_package_plan: str
    open_science_notes: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def evaluate(self) -> "FseBenchmarkReadinessReport":
        failures: list[str] = []
        warnings: list[str] = []
        covered_task_families = sorted({task.family for task in self.tasks})
        missing_task_families = sorted(set(self.task_families).difference(covered_task_families))
        if missing_task_families:
            failures.append(f"missing task families: {', '.join(missing_task_families)}")

        rq_ids = [rq.rq_id for rq in self.research_questions]
        required_rqs = ["RQ1", "RQ2", "RQ3", "RQ4"]
        missing_rqs = [rq for rq in required_rqs if rq not in rq_ids]
        if missing_rqs:
            failures.append(f"missing research questions: {', '.join(missing_rqs)}")

        if not self.baselines:
            failures.append("no baselines configured")
        if not self.fault_scenarios:
            failures.append("no fault scenarios configured")
        if not self.ablations:
            failures.append("no ablations configured")
        if not self.related_work_clusters:
            failures.append("no related work clusters configured")
        if not self.data_availability_statement.strip():
            failures.append("missing data availability statement")
        if not self.replication_package_plan.strip():
            failures.append("missing replication package plan")

        if len(self.baselines) < 5:
            warnings.append("baseline set is smaller than FSE-style comparison coverage")
        if len(self.fault_scenarios) < 6:
            warnings.append("fault taxonomy is small for long-horizon agent evaluation")
        if len(self.ablations) < 5:
            warnings.append("ablation matrix is smaller than ideal for FSE soundness")
        if len(self.related_work_clusters) < 5:
            warnings.append("related work coverage is still thin")

        metrics_by_kind = {
            kind: sorted({metric.metric_id for metric in self.metrics if metric.kind == kind})
            for kind in {
                MetricKind.EFFECTIVENESS,
                MetricKind.SAFETY,
                MetricKind.REPLAY,
                MetricKind.LOCALIZATION,
                MetricKind.COST,
                MetricKind.USABILITY,
            }
        }
        if not metrics_by_kind[MetricKind.COST]:
            warnings.append("cost metrics are missing even though FSE trajectory-reduction work makes them relevant")
        if not metrics_by_kind[MetricKind.REPLAY]:
            warnings.append("replay metrics are missing from the benchmark plan")

        ready_for_fse = not failures and len(self.tasks) >= 6 and len(self.metrics) >= 8
        return FseBenchmarkReadinessReport(
            ready_for_fse=ready_for_fse,
            covered_task_families=covered_task_families,
            missing_task_families=missing_task_families,
            baseline_count=len(self.baselines),
            fault_count=len(self.fault_scenarios),
            ablation_count=len(self.ablations),
            related_work_cluster_count=len(self.related_work_clusters),
            rq_ids=rq_ids,
            missing_rqs=missing_rqs,
            metrics_by_kind=metrics_by_kind,
            failures=failures,
            warnings=warnings,
            plan_fingerprint=self.fingerprint(),
        )

    @classmethod
    def default(cls) -> "FseBenchmarkPlan":
        source_refs = [
            "https://conf.researchr.org/track/fse-2027/fse-2027-papers",
            "https://conf.researchr.org/dates/fse-2027",
            "https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/137/Reducing-Cost-of-LLM-Agents-with-Trajectory-Reduction",
            "https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/14/AgentBound-Securing-Execution-Boundaries-of-AI-Agents",
            "https://conf.researchr.org/details/fse-2026/fse-2026-ideas-papers/15/Evaluating-Privilege-Usage-of-Agents-on-Real-World-Tools",
            "https://conf.researchr.org/details/fse-2026/fse-2026-industry-papers/29/RocketMQ-A2A-Reliable-Session-Level-Replayable-Event-Streams-for-Large-Scale-Multi-Age",
            "https://conf.researchr.org/details/fse-2026/fse-2026-ideas-visions-and-reflections/28/AgentReputation-A-Decentralized-Agentic-AI-Reputation-Framework",
            "https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/211/Event-B-Agent-Towards-LLM-Agent-for-Formal-Model-Synthesis-and-Repair",
            "https://conf.researchr.org/details/fse-2026/fse-2026-journal-first/4/Human-AI-experience-in-integrated-development-environments-a-systematic-literature-r",
            "https://www.swebench.com/",
            "https://www.swebench.com/swebench-verified.html",
            "https://www.swebench.com/swebench-pro.html",
            "https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/evaluation.md",
            "https://openai.com/index/introducing-swe-bench-verified/",
            "https://labs.scale.com/leaderboard/swe_bench_pro_public",
            "https://arxiv.org/abs/2607.23809",
            "https://arxiv.org/abs/2605.26563",
            "https://arxiv.org/abs/2607.06184",
            "https://arxiv.org/abs/2510.12635",
            "https://arxiv.org/abs/2512.10371",
            "https://github.com/SWE-agent/mini-swe-agent",
            "https://arxiv.org/abs/2503.18666",
            "https://arxiv.org/abs/2603.21522",
            "https://arxiv.org/abs/2604.08224",
            "https://arxiv.org/abs/2605.14503",
            "https://arxiv.org/abs/2607.26637",
            "https://arxiv.org/abs/2607.08028",
            "https://arxiv.org/abs/2607.27652",
            "https://arxiv.org/abs/2606.30005",
            "https://arxiv.org/abs/2607.27250",
            "https://arxiv.org/abs/2607.26313",
            "https://arxiv.org/abs/2606.30306",
            "https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/159/Not-All-RAGs-Are-Created-Equal-A-Component-Wise-Empirical-Study-for-Software-Enginee",
            "https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/205/Spectrum-based-Failure-Attribution-for-Multi-Agent-Systems",
            "https://github.com/alyssa-sha/FORGET-SE",
        ]

        tasks = [
            BenchmarkTaskSpec(
                task_id="issue_to_patch_repo_navigation",
                family=FseTaskFamily.ISSUE_TO_PATCH,
                title="Issue-to-patch repo navigation",
                description="Read an issue, inspect a repository, localize the fault, patch it, and explain the repair.",
                steps=[
                    "read issue",
                    "inspect repo",
                    "localize fault",
                    "edit patch",
                    "run tests",
                    "write report",
                ],
                required_artifact_kinds=["patch", "test_report", "diagnosis_note"],
                required_evidence_claim_ids=["claim-fault-localized", "claim-patch-validated"],
                required_transition_labels=["read_issue", "run_tests"],
                recommended_metrics=[
                    "replay_fidelity",
                    "fault_localization_mrr",
                    "resume_success_rate",
                    "runtime_overhead",
                    "retrieval_evidence_stability",
                    "context_pin_recall",
                    "active_frame_retention",
                    "benchmark_oracle_provenance_rate",
                    "official_execution_ingest_soundness",
                ],
                recommended_baselines=[
                    BaselineKind.RAW_REACT,
                    BaselineKind.CHECKPOINT_ONLY,
                    BaselineKind.LANGGRAPH_STYLE,
                ],
                recommended_faults=[
                    FaultKind.INTERRUPTION,
                    FaultKind.CONTEXT_MANAGER_DROPPED_PIN,
                    FaultKind.STALE_TOOL_OUTPUT,
                    FaultKind.RETRIEVAL_COMPONENT_SHIFT,
                    FaultKind.BENCHMARK_ORACLE_DRIFT,
                    FaultKind.OFFICIAL_EXECUTION_RECEIPT_DRIFT,
                    FaultKind.PROVIDER_SWITCH,
                    FaultKind.TOOL_SCHEMA_DRIFT,
                ],
                source_refs=source_refs,
                notes=["This family maps to the FSE debugging / fault localization topic cluster."],
            ),
            BenchmarkTaskSpec(
                task_id="issue_to_patch_writeup_gate",
                family=FseTaskFamily.ISSUE_TO_PATCH,
                title="Issue-to-patch writeup gate",
                description="Continue a repair task after interruption and verify that the writeup only commits supported claims.",
                steps=[
                    "resume checkpoint",
                    "recover scene",
                    "revalidate evidence",
                    "finalize writeup",
                ],
                required_artifact_kinds=["patch", "analysis_report", "writeup_note"],
                required_evidence_claim_ids=["claim-analysis-backed", "claim-writeup-supported"],
                required_transition_labels=["resume", "analysis", "writeup"],
                recommended_metrics=[
                    "missing_evidence_claim_rate",
                    "unsupported_claim_rate",
                    "claim_preserving_replay_fidelity",
                    "memory_interference_block_rate",
                    "context_pin_recall",
                    "silent_evidence_defect_block_rate",
                ],
                recommended_baselines=[
                    BaselineKind.CHECKPOINT_ONLY,
                    BaselineKind.LANGGRAPH_STYLE,
                    BaselineKind.OPENHANDS_STYLE,
                ],
                recommended_faults=[
                    FaultKind.COMPACTION_DRIFT,
                    FaultKind.CONTEXT_MANAGER_DROPPED_PIN,
                    FaultKind.WRONG_MEMORY_COMMIT,
                    FaultKind.MEMORY_INTERFERENCE,
                    FaultKind.SILENT_EVIDENCE_DEFECT,
                    FaultKind.EVIDENCE_RECEIPT_DRIFT,
                ],
                source_refs=source_refs,
            ),
            BenchmarkTaskSpec(
                task_id="artifact_replication_bounded",
                family=FseTaskFamily.ARTIFACT_REPLICATION,
                title="Bounded artifact replication",
                description="Replicate a paper artifact, commit only validated evidence, and write a reproducible note.",
                steps=[
                    "read paper",
                    "identify assumptions",
                    "run script",
                    "collect metrics",
                    "validate results",
                    "write reproduction note",
                ],
                required_artifact_kinds=["paper_shortlist", "replication_script", "metric", "reproduction_note"],
                required_evidence_claim_ids=["claim-result-validated"],
                required_transition_labels=["paper_scan", "run_script", "validate_result"],
                recommended_metrics=[
                    "unsupported_claim_rate",
                    "invalid_memory_commit_rate",
                    "memory_interference_block_rate",
                    "retrieval_evidence_stability",
                    "phase_gate_correctness",
                    "task_success_cost_tradeoff",
                    "artifact_provenance_completeness",
                    "benchmark_oracle_provenance_rate",
                    "silent_evidence_defect_block_rate",
                ],
                recommended_baselines=[
                    BaselineKind.RAW_REACT,
                    BaselineKind.CHECKPOINT_ONLY,
                    BaselineKind.AGENTDIET_STYLE,
                ],
                recommended_faults=[
                    FaultKind.MISSING_ARTIFACT,
                    FaultKind.BENCHMARK_ORACLE_DRIFT,
                    FaultKind.SILENT_EVIDENCE_DEFECT,
                    FaultKind.QUARANTINED_EVIDENCE,
                    FaultKind.MEMORY_INTERFERENCE,
                    FaultKind.RETRIEVAL_COMPONENT_SHIFT,
                    FaultKind.EXPIRED_APPROVAL,
                ],
                source_refs=source_refs,
                notes=["This family is the cleanest fit for the research-session / evidence-ledger story."],
            ),
            BenchmarkTaskSpec(
                task_id="artifact_replication_interrupt_resume",
                family=FseTaskFamily.ARTIFACT_REPLICATION,
                title="Artifact replication under interruption",
                description="Pause a replication run midway and verify hydration correctness after resume.",
                steps=[
                    "checkpoint task",
                    "interrupt execution",
                    "hydrate scene",
                    "resume replication",
                    "compare outputs",
                ],
                required_artifact_kinds=["metric", "analysis_report"],
                required_evidence_claim_ids=["claim-resume-safe", "claim-evidence-retained"],
                required_transition_labels=["interrupt", "resume", "compare_outputs"],
                recommended_metrics=[
                    "state_reconstruction_accuracy",
                    "resume_success_rate",
                    "hydration_retained_surface_rate",
                    "context_pin_recall",
                    "active_frame_retention",
                    "artifact_provenance_completeness",
                ],
                recommended_baselines=[
                    BaselineKind.CHECKPOINT_ONLY,
                    BaselineKind.LANGGRAPH_STYLE,
                ],
                recommended_faults=[
                    FaultKind.INTERRUPTION,
                    FaultKind.COMPACTION_DRIFT,
                    FaultKind.CONTEXT_MANAGER_DROPPED_PIN,
                    FaultKind.EVIDENCE_RECEIPT_DRIFT,
                ],
                source_refs=source_refs,
            ),
            BenchmarkTaskSpec(
                task_id="incident_rca_synthetic_logs",
                family=FseTaskFamily.INCIDENT_RCA,
                title="Incident RCA on synthetic logs",
                description="Diagnose a multi-step incident from logs, cite evidence, and propose a mitigation plan.",
                steps=[
                    "read alert",
                    "query logs",
                    "inspect metrics",
                    "localize cause",
                    "cite evidence",
                    "propose mitigation",
                ],
                required_artifact_kinds=["incident_report", "mitigation_plan", "diagnosis_note"],
                required_evidence_claim_ids=["claim-root-cause", "claim-mitigation-supported"],
                required_transition_labels=["read_alert", "inspect_metrics", "propose_mitigation"],
                recommended_metrics=[
                    "fault_localization_mrr",
                    "evidence_backed_claim_rate",
                    "memory_interference_block_rate",
                    "retrieval_evidence_stability",
                    "context_pin_recall",
                    "silent_evidence_defect_block_rate",
                    "human_debugging_time",
                ],
                recommended_baselines=[
                    BaselineKind.RAW_REACT,
                    BaselineKind.OPENHANDS_STYLE,
                    BaselineKind.LANGGRAPH_STYLE,
                ],
                recommended_faults=[
                    FaultKind.STALE_TOOL_OUTPUT,
                    FaultKind.CONTEXT_MANAGER_DROPPED_PIN,
                    FaultKind.WRONG_MEMORY_COMMIT,
                    FaultKind.MEMORY_INTERFERENCE,
                    FaultKind.RETRIEVAL_COMPONENT_SHIFT,
                    FaultKind.SILENT_EVIDENCE_DEFECT,
                    FaultKind.QUARANTINED_EVIDENCE,
                ],
                source_refs=source_refs,
            ),
            BenchmarkTaskSpec(
                task_id="incident_rca_recovery_with_policy",
                family=FseTaskFamily.INCIDENT_RCA,
                title="Incident RCA with policy recovery",
                description="Recover from approval expiry and compaction drift while preserving safety policy and evidence lineage.",
                steps=[
                    "review policy",
                    "resume after approval expiry",
                    "recheck evidence",
                    "recover lineage",
                    "write postmortem",
                ],
                required_artifact_kinds=["postmortem", "analysis_report"],
                required_evidence_claim_ids=["claim-policy-retained", "claim-postmortem-supported"],
                required_transition_labels=["policy_review", "resume_after_approval", "postmortem"],
                recommended_metrics=[
                    "policy_retention_rate",
                    "compaction_drift_detection_rate",
                    "diagnosis_precision",
                    "context_pin_recall",
                    "artifact_provenance_completeness",
                    "active_frame_retention",
                ],
                recommended_baselines=[
                    BaselineKind.CHECKPOINT_ONLY,
                    BaselineKind.LANGGRAPH_STYLE,
                    BaselineKind.OPENHANDS_STYLE,
                ],
                recommended_faults=[
                    FaultKind.EXPIRED_APPROVAL,
                    FaultKind.COMPACTION_DRIFT,
                    FaultKind.CONTEXT_MANAGER_DROPPED_PIN,
                    FaultKind.EVIDENCE_RECEIPT_DRIFT,
                ],
                source_refs=source_refs,
            ),
        ]

        baselines = [
            BaselineSpec(
                baseline_id=BaselineKind.RAW_REACT,
                name="Raw ReAct",
                comparison_role="minimum viable transcript-only agent",
                strengths=["simple", "cheap", "well-known"],
                caveats=["no durable state", "no governed memory", "no replay contract"],
                source_refs=source_refs[:2],
            ),
            BaselineSpec(
                baseline_id=BaselineKind.CHECKPOINT_ONLY,
                name="Checkpoint-only resume",
                comparison_role="state persistence without evidence governance",
                strengths=["simple resume path", "lightweight state recovery"],
                caveats=["transcript drift", "memory pollution", "no evidence contract"],
                source_refs=source_refs[:2],
            ),
            BaselineSpec(
                baseline_id=BaselineKind.LANGGRAPH_STYLE,
                name="LangGraph-style durable execution",
                comparison_role="durable state and interrupt/resume baseline",
                strengths=["state snapshots", "interrupt/resume", "graph orchestration"],
                caveats=["not a full evidence ledger", "not a governed claim commit protocol"],
                source_refs=["https://docs.langchain.com/oss/python/langgraph/persistence"],
            ),
            BaselineSpec(
                baseline_id=BaselineKind.OPENHANDS_STYLE,
                name="OpenHands-style coding agent",
                comparison_role="real software-agent runtime baseline",
                strengths=["workspace integration", "tool-rich coding workflow", "server-backed execution"],
                caveats=["workflow-specific governance still needed", "session persistence is not proof of scene integrity"],
                source_refs=["https://docs.openhands.dev/sdk"],
            ),
            BaselineSpec(
                baseline_id=BaselineKind.AGENTDIET_STYLE,
                name="AgentDiet-style trajectory reduction",
                comparison_role="efficiency-focused long-horizon baseline",
                strengths=["lower token cost", "trajectory pruning", "agent performance retention"],
                caveats=["cost-first, not evidence-first", "may not preserve replay semantics"],
                source_refs=["https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/137/Reducing-Cost-of-LLM-Agents-with-Trajectory-Reduction"],
            ),
        ]

        faults = [
            FaultScenarioSpec(
                fault_id=FaultKind.INTERRUPTION,
                kind=FaultKind.INTERRUPTION,
                title="Mid-run interruption",
                description="Pause execution between major steps and require hydration before resumption.",
                affected_surfaces=["runtime_state", "trace", "checkpoint"],
                expected_detector="HydrationManifest.verify",
                mitigation_hint="resume from a retained scene manifest instead of a raw transcript.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.COMPACTION_DRIFT,
                kind=FaultKind.COMPACTION_DRIFT,
                title="Compaction drift",
                description="Remove policy or artifact lineage from a compressed state summary.",
                affected_surfaces=["policy", "artifact", "approval_boundary"],
                expected_detector="CompactionVerifier",
                mitigation_hint="pin policy and artifact lineage in the checkpoint summary.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.CONTEXT_MANAGER_DROPPED_PIN,
                kind=FaultKind.CONTEXT_MANAGER_DROPPED_PIN,
                title="Context manager dropped pin",
                description="Offload or edit active context while losing a required policy, evidence, or artifact pin needed for safe hydration.",
                affected_surfaces=["context", "memory", "evidence", "hydration"],
                expected_detector="CompactionVerifier + HydrationManifest.verify",
                mitigation_hint="treat context editing as a governed action that must retain pinned claims and active execution frame refs.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.STALE_TOOL_OUTPUT,
                kind=FaultKind.STALE_TOOL_OUTPUT,
                title="Stale tool output",
                description="Return an outdated or contradicted tool result and measure recovery.",
                affected_surfaces=["tool_output", "diagnosis"],
                expected_detector="InterventionReplayWorkbench",
                mitigation_hint="compare cached prefix and live suffix against the baseline trace.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.MISSING_ARTIFACT,
                kind=FaultKind.MISSING_ARTIFACT,
                title="Missing artifact",
                description="Delete a required artifact reference before phase exit or report write-up.",
                affected_surfaces=["artifact", "research_session", "hydration"],
                expected_detector="HydrationManifest.verify",
                mitigation_hint="refuse phase exit until required artifacts are restored.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.BENCHMARK_ORACLE_DRIFT,
                kind=FaultKind.BENCHMARK_ORACLE_DRIFT,
                title="Benchmark oracle drift",
                description="Change or contaminate the task oracle, gold patch, test patch, or executable environment metadata used to score an issue-to-patch task.",
                affected_surfaces=["benchmark", "test_oracle", "artifact_provenance", "execution_environment"],
                expected_detector="SweBenchLocalPatchExecutor + artifact provenance audit",
                mitigation_hint="record task provenance, test oracle fingerprints, environment metadata, and contamination/audit receipts in the artifact package.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.QUARANTINED_EVIDENCE,
                kind=FaultKind.QUARANTINED_EVIDENCE,
                title="Quarantined evidence citation",
                description="Attempt to cite quarantined or inactive evidence in a claim or report.",
                affected_surfaces=["evidence", "writeup", "decision_memory"],
                expected_detector="EvidenceLedger.evaluate",
                mitigation_hint="require an active evidence claim before commit.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.EXPIRED_APPROVAL,
                kind=FaultKind.EXPIRED_APPROVAL,
                title="Expired approval",
                description="Let authority evidence expire before a privileged effect commit.",
                affected_surfaces=["approval", "authority", "commit_boundary"],
                expected_detector="PermissionGraph.authorize_action",
                mitigation_hint="reattach a fresh witness before commit.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.WRONG_MEMORY_COMMIT,
                kind=FaultKind.WRONG_MEMORY_COMMIT,
                title="Wrong memory commit",
                description="Commit a belief that is unsupported by the active evidence ledger.",
                affected_surfaces=["memory", "evidence", "decision"],
                expected_detector="MemoryCommitProtocol.safety_gate",
                mitigation_hint="stage, validate, and only then commit memory.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.MEMORY_INTERFERENCE,
                kind=FaultKind.MEMORY_INTERFERENCE,
                title="Memory interference",
                description="Reuse a stale or similar-task belief that conflicts with the current evidence scene.",
                affected_surfaces=["memory", "decision_memory", "evidence", "writeup"],
                expected_detector="MemoryCommitProtocol + DecisionMemoryProjection",
                mitigation_hint="block decision projection until stale or conflicting memory is revalidated against active evidence.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.RETRIEVAL_COMPONENT_SHIFT,
                kind=FaultKind.RETRIEVAL_COMPONENT_SHIFT,
                title="Retrieval component shift",
                description="Change the evidence intake component, such as lexical versus dense retrieval, and observe claim support drift.",
                affected_surfaces=["retrieval", "evidence", "trace", "claim_support"],
                expected_detector="EvidenceLedger.evaluate + ReplayVerifier",
                mitigation_hint="record retrieval component fingerprints and require active evidence claims before memory/writeup commit.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.SILENT_EVIDENCE_DEFECT,
                kind=FaultKind.SILENT_EVIDENCE_DEFECT,
                title="Silent evidence defect",
                description="Keep the evidence payload plausible while corrupting freshness, lineage, source, or metadata predicates.",
                affected_surfaces=["evidence_metadata", "lineage", "memory", "writeup"],
                expected_detector="EvidenceLedger.evaluate + MemoryCommitProtocol",
                mitigation_hint="gate memory/writeup commit on data-quality predicates, freshness receipts, and lineage checks.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.OFFICIAL_EXECUTION_RECEIPT_DRIFT,
                kind=FaultKind.OFFICIAL_EXECUTION_RECEIPT_DRIFT,
                title="Official execution receipt drift",
                description="Change official SWE-bench results, per-instance receipts, run logs, or oracle fingerprints after Docker execution.",
                affected_surfaces=["official_execution", "oracle_provenance", "artifact_package", "replay"],
                expected_detector="SweBenchOfficialExecutionIngestor + HydrationManifest.verify",
                mitigation_hint="retain official results.json, instance_results.jsonl, run logs, execution receipts, and hydration reports together.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.PROVIDER_SWITCH,
                kind=FaultKind.PROVIDER_SWITCH,
                title="Provider switch drift",
                description="Swap model/provider capability snapshots mid-run and check if trace contracts still match.",
                affected_surfaces=["provider", "trace", "protocol"],
                expected_detector="ReplayVerifier",
                mitigation_hint="checkpoint provider capability snapshots together with the scene.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.TOOL_SCHEMA_DRIFT,
                kind=FaultKind.TOOL_SCHEMA_DRIFT,
                title="Tool schema drift",
                description="Change the tool contract hash or normalization rules between runs.",
                affected_surfaces=["tool_contract", "trace", "eval"],
                expected_detector="ReplayVerifier",
                mitigation_hint="persist tool contract fingerprints alongside traces.",
                source_refs=source_refs,
            ),
            FaultScenarioSpec(
                fault_id=FaultKind.EVIDENCE_RECEIPT_DRIFT,
                kind=FaultKind.EVIDENCE_RECEIPT_DRIFT,
                title="Evidence receipt drift",
                description="Keep the action the same but change the evidence ledger fingerprint or claim ids.",
                affected_surfaces=["trace", "evidence", "replay"],
                expected_detector="ReplayVerifier + evidence receipt diff",
                mitigation_hint="treat the evidence scene as part of the replay contract.",
                source_refs=source_refs,
            ),
        ]

        ablations = [
            AblationSpec(
                ablation_id=AblationKind.NO_HYDRATION_MANIFEST,
                disabled_modules=["HydrationManifest"],
                expected_regression="resume correctness should fall because scene integrity is no longer checked.",
                related_rqs=["RQ1"],
                source_refs=source_refs,
            ),
            AblationSpec(
                ablation_id=AblationKind.NO_MEMORY_COMMIT,
                disabled_modules=["MemoryCommitProtocol", "DecisionMemoryProjection"],
                expected_regression="unsupported and invalid memory use should increase.",
                related_rqs=["RQ2"],
                source_refs=source_refs,
            ),
            AblationSpec(
                ablation_id=AblationKind.NO_EVIDENCE_LEDGER,
                disabled_modules=["EvidenceLedger"],
                expected_regression="claim support and evidence citation quality should degrade.",
                related_rqs=["RQ2", "RQ3"],
                source_refs=source_refs,
            ),
            AblationSpec(
                ablation_id=AblationKind.NO_TRANSITION_GRAPH,
                disabled_modules=["TransitionGraph", "HarnessDiagnosticWorkbench"],
                expected_regression="fault localization should revert toward raw-log inspection.",
                related_rqs=["RQ3"],
                source_refs=source_refs,
            ),
            AblationSpec(
                ablation_id=AblationKind.NO_COMPACTION_VERIFIER,
                disabled_modules=["CompactionVerifier"],
                expected_regression="policy and artifact lineage drift should slip through resume.",
                related_rqs=["RQ1", "RQ4"],
                source_refs=source_refs,
            ),
            AblationSpec(
                ablation_id=AblationKind.NO_TRACE_RECEIPT,
                disabled_modules=["TraceEnvelope.evidence_ledger_fingerprint", "TraceEnvelope.evidence_claim_ids", "evidence_ledger receipt"],
                expected_regression="evidence-retaining replay should lose sensitivity to evidence drift.",
                related_rqs=["RQ3"],
                source_refs=source_refs,
            ),
            AblationSpec(
                ablation_id=AblationKind.NO_PERMISSION_GRAPH,
                disabled_modules=["PermissionGraph", "AuthorityWitness"],
                expected_regression="authorization and commit-time evidence should become weaker.",
                related_rqs=["RQ1", "RQ4"],
                source_refs=source_refs,
            ),
        ]

        metrics = [
            BenchmarkMetricSpec(
                metric_id="resume_success_rate",
                name="Resume success rate",
                kind=MetricKind.EFFECTIVENESS,
                rqs=["RQ1"],
                description="Whether a task can be resumed after interruption and still finish correctly.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="state_reconstruction_accuracy",
                name="State reconstruction accuracy",
                kind=MetricKind.EFFECTIVENESS,
                rqs=["RQ1"],
                description="How accurately the resumed state matches the pre-interruption scene.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="phase_gate_correctness",
                name="Phase gate correctness",
                kind=MetricKind.SAFETY,
                rqs=["RQ1", "RQ2"],
                description="Whether the runtime allows or blocks phase transitions correctly.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="missing_policy_evidence_pin_rate",
                name="Missing policy/evidence pin rate",
                kind=MetricKind.SAFETY,
                rqs=["RQ1", "RQ4"],
                description="How often a checkpoint loses key policy or evidence constraints.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="invalid_memory_commit_rate",
                name="Invalid memory commit rate",
                kind=MetricKind.SAFETY,
                rqs=["RQ2"],
                description="How often unsupported memory is incorrectly committed.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="unsupported_claim_rate",
                name="Unsupported claim rate",
                kind=MetricKind.SAFETY,
                rqs=["RQ2"],
                description="How often a report or claim lacks active evidence support.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="memory_interference_block_rate",
                name="Memory interference block rate",
                kind=MetricKind.SAFETY,
                rqs=["RQ2"],
                description="How often stale or similar-task memory interference is blocked before decision or writeup use.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="retrieval_evidence_stability",
                name="Retrieval evidence stability",
                kind=MetricKind.SAFETY,
                rqs=["RQ2", "RQ3"],
                description="Whether evidence claims remain stable when retrieval or evidence-intake components shift.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="context_pin_recall",
                name="Context pin recall",
                kind=MetricKind.SAFETY,
                rqs=["RQ1", "RQ4"],
                description="Whether context editing, compression, or offloading preserves pinned policy, evidence, artifact, and active-frame references needed for safe hydration.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="active_frame_retention",
                name="Active frame retention",
                kind=MetricKind.EFFECTIVENESS,
                rqs=["RQ1"],
                description="Whether hydration restores the current active execution frame instead of only a passive summary.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="replay_fidelity",
                name="Replay fidelity",
                kind=MetricKind.REPLAY,
                rqs=["RQ3"],
                description="Whether a replay reproduces the baseline trace envelope and effects.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="claim_preserving_replay_fidelity",
                name="Claim-preserving replay fidelity",
                kind=MetricKind.REPLAY,
                rqs=["RQ3"],
                description="Whether replay preserves evidence claims, not only tool actions.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="evidence_receipt_drift_detection_rate",
                name="Evidence receipt drift detection rate",
                kind=MetricKind.REPLAY,
                rqs=["RQ3"],
                description="How well the replay stack notices evidence ledger drift.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="artifact_provenance_completeness",
                name="Artifact provenance completeness",
                kind=MetricKind.REPLAY,
                rqs=["RQ3", "RQ4"],
                description="How completely a replay or artifact package retains task provenance, oracle fingerprints, execution reports, and evidence receipts.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="official_execution_ingest_soundness",
                name="Official execution ingest soundness",
                kind=MetricKind.REPLAY,
                rqs=["RQ3", "RQ4"],
                description="Whether official SWE-bench execution outputs can be ingested into a replay-ready evidence and hydration contract without provenance drift.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="fault_localization_mrr",
                name="Fault localization MRR",
                kind=MetricKind.LOCALIZATION,
                rqs=["RQ3"],
                description="How well the diagnosis stack ranks the true failure surface.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="human_debugging_time",
                name="Human debugging time",
                kind=MetricKind.USABILITY,
                rqs=["RQ3"],
                description="How much time the human needs to inspect and repair a failure.",
                higher_is_better=False,
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="token_cost",
                name="Token cost",
                kind=MetricKind.COST,
                rqs=["RQ4"],
                description="Token overhead of governance and replay infrastructure.",
                higher_is_better=False,
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="checkpoint_size",
                name="Checkpoint size",
                kind=MetricKind.COST,
                rqs=["RQ4"],
                description="Serialized scene size after hydration and governance metadata.",
                higher_is_better=False,
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="runtime_overhead",
                name="Runtime overhead",
                kind=MetricKind.COST,
                rqs=["RQ4"],
                description="Time overhead introduced by governance and verification.",
                higher_is_better=False,
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="task_success_cost_tradeoff",
                name="Task success/cost tradeoff",
                kind=MetricKind.COST,
                rqs=["RQ4"],
                description="How much performance is retained for each unit of governance overhead.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="benchmark_oracle_provenance_rate",
                name="Benchmark oracle provenance rate",
                kind=MetricKind.COST,
                rqs=["RQ4"],
                description="How often issue-to-patch and artifact-replication evaluations retain non-contaminated task provenance, gold/test oracle hashes, and executable-environment metadata.",
                source_refs=source_refs,
            ),
            BenchmarkMetricSpec(
                metric_id="silent_evidence_defect_block_rate",
                name="Silent evidence defect block rate",
                kind=MetricKind.SAFETY,
                rqs=["RQ2", "RQ4"],
                description="How often freshness, lineage, or metadata-borne evidence defects are blocked before memory or report commit.",
                source_refs=source_refs,
            ),
        ]

        related_work_clusters = [
            RelatedWorkCluster(
                cluster_id="harness_control_plane",
                title="Harness as control plane",
                papers=[
                    "FSE 2027 CFP",
                    "AgentSpec",
                    "Externalization in LLM Agents",
                    "From Prompts to Contracts: Harness Engineering for Auditable Enterprise LLM Agents",
                    "Harness-G",
                ],
                design_implication="Treat harness metadata, runtime enforcement, externalized state, verification, and replay as first-class runtime objects.",
                source_refs=source_refs,
            ),
            RelatedWorkCluster(
                cluster_id="privilege_boundaries",
                title="Privilege and execution boundaries",
                papers=[
                    "AgentBound",
                    "Evaluating Privilege Usage of Agents on Real-World Tools",
                    "AgentReputation",
                ],
                design_implication="Model authority, witness freshness, and commit boundaries explicitly.",
                source_refs=source_refs,
            ),
            RelatedWorkCluster(
                cluster_id="replay_streams",
                title="Replayable session streams",
                papers=[
                    "RocketMQ-A2A",
                    "EAGER",
                    "FAMAS",
                    "TrajAudit",
                    "FALAT",
                    "TraceSynth",
                    "LiveMCPBench",
                ],
                design_implication="Treat replayable streams, reasoning-trace representations, and failure-attribution traces as part of the research artifact.",
                source_refs=source_refs,
            ),
            RelatedWorkCluster(
                cluster_id="memory_provenance",
                title="Memory and provenance governance",
                papers=[
                    "Filesystem-Based Memory for LLM Agents",
                    "MemTX",
                    "Evidence Tracing and Execution Provenance",
                    "FORGET-SE",
                    "Not All RAGs Are Created Equal",
                ],
                design_implication="Memory and retrieval evidence must be committed through validation, traceable lineage, and interference-aware checks.",
                source_refs=source_refs,
            ),
            RelatedWorkCluster(
                cluster_id="context_management",
                title="Agentic context management",
                papers=[
                    "ACM: Agentic Context Management for Long Horizon Tasks",
                    "AgentProg",
                    "MemAct",
                    "Overcoming Context Limitations in Long-Horizon Agentic Search",
                ],
                design_implication="Treat context editing/offloading as a governed runtime action whose retained pins and retrieval path can be measured.",
                source_refs=source_refs,
            ),
            RelatedWorkCluster(
                cluster_id="benchmark_validity",
                title="Benchmark validity and oracle provenance",
                papers=[
                    "SWE-bench Verified",
                    "SWE-bench Pro",
                    "SWE-Lancer",
                    "Trajectory Structure Diagnostics for Coding Agents",
                ],
                design_implication="FSE evaluation must retain task oracle, environment, and contamination-audit provenance rather than relying only on aggregate pass rates.",
                source_refs=source_refs,
            ),
            RelatedWorkCluster(
                cluster_id="verification_feedback",
                title="Verification and repair loops",
                papers=[
                    "Event-B Agent",
                    "FAVA",
                    "Commit-Time Authorization",
                ],
                design_implication="Verification metadata should drive repair and replay, not just safety checks.",
                source_refs=source_refs,
            ),
            RelatedWorkCluster(
                cluster_id="human_ai_experience",
                title="Human-AI experience in IDEs",
                papers=[
                    "Human-AI experience in integrated development environments: a systematic literature review",
                    "Agentic coding assistant studies",
                ],
                design_implication="Explainability, verification overhead, and over-reliance belong in the evaluation.",
                source_refs=source_refs,
            ),
        ]

        research_questions = [
            BenchmarkRQ(
                rq_id="RQ1",
                question="Does scene-based hydration improve correct task resumption compared with transcript-based or checkpoint-only baselines?",
                supported_task_families=[FseTaskFamily.ISSUE_TO_PATCH, FseTaskFamily.ARTIFACT_REPLICATION],
                key_metrics=[
                    "resume_success_rate",
                    "state_reconstruction_accuracy",
                    "phase_gate_correctness",
                    "missing_policy_evidence_pin_rate",
                    "context_pin_recall",
                    "active_frame_retention",
                ],
                suggested_baselines=[BaselineKind.RAW_REACT, BaselineKind.CHECKPOINT_ONLY, BaselineKind.LANGGRAPH_STYLE],
                suggested_faults=[
                    FaultKind.INTERRUPTION,
                    FaultKind.COMPACTION_DRIFT,
                    FaultKind.CONTEXT_MANAGER_DROPPED_PIN,
                    FaultKind.PROVIDER_SWITCH,
                ],
                suggested_ablations=[AblationKind.NO_HYDRATION_MANIFEST, AblationKind.NO_COMPACTION_VERIFIER],
            ),
            BenchmarkRQ(
                rq_id="RQ2",
                question="Does governed memory commit reduce invalid, stale, and interference-induced memory use and unsupported claims in long-horizon agent tasks?",
                supported_task_families=[FseTaskFamily.ARTIFACT_REPLICATION, FseTaskFamily.INCIDENT_RCA],
                key_metrics=[
                    "invalid_memory_commit_rate",
                    "unsupported_claim_rate",
                    "memory_interference_block_rate",
                    "silent_evidence_defect_block_rate",
                    "retrieval_evidence_stability",
                    "phase_gate_correctness",
                ],
                suggested_baselines=[BaselineKind.RAW_REACT, BaselineKind.OPENHANDS_STYLE],
                suggested_faults=[
                    FaultKind.WRONG_MEMORY_COMMIT,
                    FaultKind.MEMORY_INTERFERENCE,
                    FaultKind.SILENT_EVIDENCE_DEFECT,
                    FaultKind.RETRIEVAL_COMPONENT_SHIFT,
                    FaultKind.QUARANTINED_EVIDENCE,
                    FaultKind.MISSING_ARTIFACT,
                ],
                suggested_ablations=[AblationKind.NO_MEMORY_COMMIT, AblationKind.NO_EVIDENCE_LEDGER],
            ),
            BenchmarkRQ(
                rq_id="RQ3",
                question="Can trace-envelope-driven transition graphs localize and reproduce long-horizon agent failures more accurately than raw logs?",
                supported_task_families=[FseTaskFamily.ISSUE_TO_PATCH, FseTaskFamily.ARTIFACT_REPLICATION, FseTaskFamily.INCIDENT_RCA],
                key_metrics=[
                    "replay_fidelity",
                    "claim_preserving_replay_fidelity",
                    "fault_localization_mrr",
                    "evidence_receipt_drift_detection_rate",
                    "retrieval_evidence_stability",
                    "artifact_provenance_completeness",
                    "official_execution_ingest_soundness",
                ],
                suggested_baselines=[BaselineKind.CHECKPOINT_ONLY, BaselineKind.OPENHANDS_STYLE],
                suggested_faults=[
                    FaultKind.STALE_TOOL_OUTPUT,
                    FaultKind.EVIDENCE_RECEIPT_DRIFT,
                    FaultKind.RETRIEVAL_COMPONENT_SHIFT,
                    FaultKind.TOOL_SCHEMA_DRIFT,
                    FaultKind.BENCHMARK_ORACLE_DRIFT,
                    FaultKind.OFFICIAL_EXECUTION_RECEIPT_DRIFT,
                ],
                suggested_ablations=[AblationKind.NO_TRANSITION_GRAPH, AblationKind.NO_TRACE_RECEIPT],
            ),
            BenchmarkRQ(
                rq_id="RQ4",
                question="What is the overhead of scene-based governance, and can it remain practical for software-engineering agents?",
                supported_task_families=[FseTaskFamily.ISSUE_TO_PATCH, FseTaskFamily.ARTIFACT_REPLICATION, FseTaskFamily.INCIDENT_RCA],
                key_metrics=[
                    "token_cost",
                    "checkpoint_size",
                    "runtime_overhead",
                    "task_success_cost_tradeoff",
                    "context_pin_recall",
                    "artifact_provenance_completeness",
                    "benchmark_oracle_provenance_rate",
                    "official_execution_ingest_soundness",
                    "silent_evidence_defect_block_rate",
                ],
                suggested_baselines=[BaselineKind.RAW_REACT, BaselineKind.CHECKPOINT_ONLY, BaselineKind.AGENTDIET_STYLE],
                suggested_faults=[
                    FaultKind.COMPACTION_DRIFT,
                    FaultKind.CONTEXT_MANAGER_DROPPED_PIN,
                    FaultKind.BENCHMARK_ORACLE_DRIFT,
                    FaultKind.OFFICIAL_EXECUTION_RECEIPT_DRIFT,
                    FaultKind.EXPIRED_APPROVAL,
                    FaultKind.PROVIDER_SWITCH,
                ],
                suggested_ablations=[AblationKind.NO_COMPACTION_VERIFIER, AblationKind.NO_PERMISSION_GRAPH],
            ),
        ]

        return cls(
            plan_id="fse-2027-harness-x-hermes-benchmark-plan",
            title="FSE 2027 Harness x Hermes benchmark scaffold",
            target_venue="FSE 2027 Research Track",
            deadline="2026-10-02",
            paper_positioning="Hydratable and evidence-governed runtime support for long-horizon software-engineering agents.",
            task_families=[
                FseTaskFamily.ISSUE_TO_PATCH,
                FseTaskFamily.ARTIFACT_REPLICATION,
                FseTaskFamily.INCIDENT_RCA,
            ],
            tasks=tasks,
            baselines=baselines,
            fault_scenarios=faults,
            ablations=ablations,
            metrics=metrics,
            related_work_clusters=related_work_clusters,
            research_questions=research_questions,
            data_availability_statement=(
                "A replication package should include anonymized task specs, fault injection scripts, "
                "baseline adapters, ablation toggles, provenance/oracle audit receipts, and evaluation notebooks."
            ),
            replication_package_plan=(
                "Publish anonymized task families, fault taxonomy, benchmark runner, and replay/diagnosis outputs "
                "with an artifact-evaluation-friendly README and executable oracle/provenance checks."
            ),
            open_science_notes=[
                "Provide a Data Availability section after the Conclusion.",
                "Keep the evaluation artifact anonymized for double-anonymous review.",
                "Release scripts that reconstruct the benchmark and replay the evidence-retaining traces.",
            ],
            source_refs=source_refs,
        )


@dataclass(frozen=True, slots=True)
class FseBenchmarkReadinessReport:
    ready_for_fse: bool
    covered_task_families: list[str]
    missing_task_families: list[str]
    baseline_count: int
    fault_count: int
    ablation_count: int
    related_work_cluster_count: int
    rq_ids: list[str]
    missing_rqs: list[str]
    metrics_by_kind: dict[str, list[str]]
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    plan_fingerprint: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
