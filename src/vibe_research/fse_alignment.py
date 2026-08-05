from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _get(report: Any, name: str, default: Any = None) -> Any:
    if isinstance(report, dict):
        return report.get(name, default)
    return getattr(report, name, default)


@dataclass(frozen=True, slots=True)
class FseTopConferenceAlignmentReport:
    """A top-conference-style audit over the current FSE benchmark evidence.

    This report deliberately separates three gates:

    - positioning: whether the story/RQs/benchmark shape look like a FSE paper;
    - artifact smoke: whether the current replication package scaffold is runnable;
    - submission empirics: whether current evidence is strong enough to support a
      Research Track empirical claim.
    """

    ready_for_top_conference_positioning: bool
    ready_for_artifact_smoke: bool
    ready_for_submission_empirics: bool
    empirical_maturity_level: str
    passed_gates: list[str]
    missing_submission_gates: list[str]
    benchmark_strengths: list[str]
    recommended_next_experiments: list[str]
    min_real_swebench_instances_required: int
    real_swebench_instances: int
    real_official_execution_confirmed: bool
    real_artifact_replication_count: int
    source_refs: list[str] = field(default_factory=list)
    report_fingerprint: str = ""

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        if not data["report_fingerprint"]:
            data["report_fingerprint"] = self.fingerprint()
        return data

    def fingerprint(self) -> str:
        data = asdict(self)
        data["report_fingerprint"] = ""
        return _stable_hash(data)


class FseTopConferenceAlignmentAuditor:
    """Checks whether the current work is merely runnable or actually FSE-ready."""

    def __init__(
        self,
        *,
        min_real_swebench_instances_required: int = 5,
        min_real_artifact_replications_required: int = 1,
        source_refs: list[str] | None = None,
    ):
        self.min_real_swebench_instances_required = min_real_swebench_instances_required
        self.min_real_artifact_replications_required = min_real_artifact_replications_required
        self.source_refs = list(source_refs or [])

    def audit(
        self,
        *,
        plan_report: Any,
        matrix_report: Any,
        trace_report: Any,
        local_report: Any,
        swebench_report: Any,
        swebench_executor_report: Any,
        swebench_official_report: Any,
        swebench_official_execution_report: Any,
        real_official_execution_confirmed: bool = False,
        real_artifact_replication_count: int = 0,
    ) -> FseTopConferenceAlignmentReport:
        passed_gates: list[str] = []
        missing_submission_gates: list[str] = []
        strengths: list[str] = []
        next_experiments: list[str] = []

        plan_ready = bool(_get(plan_report, "ready_for_fse", False))
        matrix_ready = bool(_get(matrix_report, "ready_for_runner", False))
        trace_ready = bool(_get(trace_report, "ready_for_synthetic_trace", False))
        local_ready = bool(_get(local_report, "ready_for_local_runner", False))
        swebench_adapter_ready = bool(_get(swebench_report, "ready_for_swebench_adapter", False))
        swebench_executor_ready = bool(_get(swebench_executor_report, "ready_for_swebench_executor", False))
        official_subset_ready = bool(_get(swebench_official_report, "ready_for_official_subset", False))
        official_execution_ingest_ready = bool(
            _get(swebench_official_execution_report, "ready_for_official_execution_ingest", False)
        )

        baseline_count = int(_get(plan_report, "baseline_count", 0) or 0)
        fault_count = int(_get(plan_report, "fault_count", 0) or 0)
        ablation_count = int(_get(plan_report, "ablation_count", 0) or 0)
        related_work_cluster_count = int(_get(plan_report, "related_work_cluster_count", 0) or 0)
        rq_ids = set(_get(plan_report, "rq_ids", []) or [])
        experiment_cell_count = int(_get(matrix_report, "total_cell_count", 0) or 0)
        processed_cell_count = int(_get(trace_report, "processed_cell_count", 0) or 0)
        local_success_count = int(_get(local_report, "success_count", 0) or 0)
        real_swebench_instances = (
            int(_get(swebench_official_execution_report, "completed_count", 0) or 0)
            if real_official_execution_confirmed
            else 0
        )

        top_conference_shape = (
            plan_ready
            and baseline_count >= 5
            and fault_count >= 15
            and ablation_count >= 7
            and related_work_cluster_count >= 8
            and {"RQ1", "RQ2", "RQ3", "RQ4"}.issubset(rq_ids)
            and experiment_cell_count >= 100
        )
        if top_conference_shape:
            passed_gates.append("fse_shape: RQs, baselines, faults, ablations, metrics, and related-work clusters are broad enough")
            strengths.append("The benchmark scaffold now looks like an empirical SE paper scaffold, not just a runtime demo.")
        else:
            missing_submission_gates.append("expand RQ/baseline/fault/ablation/related-work coverage until it reaches FSE empirical breadth")

        if trace_ready and processed_cell_count >= 100:
            passed_gates.append("synthetic_matrix: deterministic trace matrix exercises at least 100 cells")
            strengths.append("The deterministic trace runner can stress hydration, memory, replay, provenance, and cost metrics.")
        else:
            missing_submission_gates.append("run the full synthetic trace matrix rather than a tiny smoke subset")

        artifact_smoke_ready = (
            plan_ready
            and matrix_ready
            and trace_ready
            and local_ready
            and swebench_adapter_ready
            and swebench_executor_ready
            and official_subset_ready
            and official_execution_ingest_ready
        )
        if artifact_smoke_ready:
            passed_gates.append("artifact_smoke: local artifact, SWE-bench-style, official-subset, and official-ingest contracts run")
            strengths.append("The current artifact package is functionally smoke-testable and already retains evidence/hydration outputs.")
        else:
            missing_submission_gates.append("make the artifact-package smoke fully runnable before expanding experiments")

        if local_success_count >= 3:
            passed_gates.append("local_tasks: all three local toy task families currently pass")

        real_swebench_enough = (
            real_official_execution_confirmed
            and real_swebench_instances >= self.min_real_swebench_instances_required
        )
        if real_swebench_enough:
            passed_gates.append("real_swebench: official Docker execution evidence reaches the minimum small-subset threshold")
        else:
            missing_submission_gates.append(
                f"run at least {self.min_real_swebench_instances_required} SWE-bench Verified instances through the official Docker harness"
            )
            next_experiments.append(
                "Run 5-10 SWE-bench Verified instances with official Docker evaluation, then ingest results.json, instance_results.jsonl, run_logs, and execution receipts."
            )

        real_artifacts_enough = real_artifact_replication_count >= self.min_real_artifact_replications_required
        if real_artifacts_enough:
            passed_gates.append("real_artifact_replication: at least one real artifact replication task is connected")
        else:
            missing_submission_gates.append(
                f"replace toy artifact replication with at least {self.min_real_artifact_replications_required} real paper artifact package"
            )
            next_experiments.append(
                "Add one small real artifact-replication package and measure hydration safety, unsupported claim rate, and artifact provenance completeness."
            )

        next_experiments.extend(
            [
                "Run ablations no_hydration_manifest / no_memory_commit / no_trace_receipt on the same real-task slice.",
                "Report FSE-facing overhead: token_cost, checkpoint_size, runtime_overhead, and provenance/context-retention cost.",
                "Prepare an anonymized artifact README that separates synthetic smoke, local toy tasks, and real official benchmark evidence.",
            ]
        )

        maturity = self._maturity_level(
            artifact_smoke_ready=artifact_smoke_ready,
            trace_ready=trace_ready,
            processed_cell_count=processed_cell_count,
            local_success_count=local_success_count,
            swebench_executor_ready=swebench_executor_ready,
            official_execution_ingest_ready=official_execution_ingest_ready,
            real_swebench_enough=real_swebench_enough,
            real_artifacts_enough=real_artifacts_enough,
        )
        ready_for_positioning = top_conference_shape
        ready_for_submission_empirics = top_conference_shape and artifact_smoke_ready and real_swebench_enough and real_artifacts_enough

        report = FseTopConferenceAlignmentReport(
            ready_for_top_conference_positioning=ready_for_positioning,
            ready_for_artifact_smoke=artifact_smoke_ready,
            ready_for_submission_empirics=ready_for_submission_empirics,
            empirical_maturity_level=maturity,
            passed_gates=passed_gates,
            missing_submission_gates=missing_submission_gates,
            benchmark_strengths=strengths,
            recommended_next_experiments=list(dict.fromkeys(next_experiments)),
            min_real_swebench_instances_required=self.min_real_swebench_instances_required,
            real_swebench_instances=real_swebench_instances,
            real_official_execution_confirmed=real_official_execution_confirmed,
            real_artifact_replication_count=real_artifact_replication_count,
            source_refs=self.source_refs,
        )
        return FseTopConferenceAlignmentReport(
            **{
                **report.to_dict(),
                "report_fingerprint": report.fingerprint(),
            }
        )

    @staticmethod
    def _maturity_level(
        *,
        artifact_smoke_ready: bool,
        trace_ready: bool,
        processed_cell_count: int,
        local_success_count: int,
        swebench_executor_ready: bool,
        official_execution_ingest_ready: bool,
        real_swebench_enough: bool,
        real_artifacts_enough: bool,
    ) -> str:
        if real_swebench_enough and real_artifacts_enough:
            return "L5_submission_empirics_ready"
        if real_swebench_enough:
            return "L4_real_official_swebench_subset"
        if artifact_smoke_ready and official_execution_ingest_ready:
            return "L3_official_ingest_contract_smoke"
        if swebench_executor_ready:
            return "L2_swebench_style_local_executor"
        if local_success_count >= 3:
            return "L1_local_artifact_smoke"
        if trace_ready and processed_cell_count > 0:
            return "L0_synthetic_trace_matrix"
        return "L0_plan_only"
