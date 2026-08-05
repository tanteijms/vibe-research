from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research import (
    FseBenchmarkPlan,
    FseLocalToyTaskRunner,
    FseTopConferenceAlignmentAuditor,
    SweBenchLocalPatchExecutor,
    SweBenchOfficialDockerPreflight,
    SweBenchOfficialExecutionIngestor,
    SweBenchOfficialSubsetBridge,
    SweBenchSmallSubsetAdapter,
    SyntheticFseBenchmarkRunner,
    SyntheticFseTraceRunner,
)


def main() -> int:
    plan = FseBenchmarkPlan.default()
    report = plan.evaluate()
    matrix = SyntheticFseBenchmarkRunner(plan).build_matrix()
    matrix_report = matrix.report(plan)
    trace_report = SyntheticFseTraceRunner(plan, matrix).run()
    with TemporaryDirectory() as temp_dir:
        local_report = FseLocalToyTaskRunner(plan).run(temp_dir)
    with TemporaryDirectory() as temp_dir:
        swebench_report = SweBenchSmallSubsetAdapter().run(temp_dir)
    with TemporaryDirectory() as temp_dir:
        swebench_executor_report = SweBenchLocalPatchExecutor.demo(Path(temp_dir) / "source_repos").run(
            Path(temp_dir) / "runs"
        )
    with TemporaryDirectory() as temp_dir:
        swebench_official_report = SweBenchOfficialSubsetBridge.demo().run(temp_dir)
        swebench_official_docker_preflight_report = SweBenchOfficialDockerPreflight().run(
            swebench_official_report
        )
    with TemporaryDirectory() as temp_dir:
        official_root = Path(temp_dir) / "official"
        ingest_root = Path(temp_dir) / "ingest"
        bridge_report = SweBenchOfficialSubsetBridge.demo().run(official_root)
        evaluation_root = SweBenchOfficialExecutionIngestor.demo_evaluation_results(
            bridge_report,
            Path(temp_dir) / "evaluation_results",
        )
        swebench_official_execution_report = SweBenchOfficialExecutionIngestor(
            subset_manifest_path=bridge_report.subset_manifest_ref,
            evaluation_results_path=evaluation_root,
        ).run(ingest_root)
    alignment_report = FseTopConferenceAlignmentAuditor(source_refs=plan.source_refs).audit(
        plan_report=report,
        matrix_report=matrix_report,
        trace_report=trace_report,
        local_report=local_report,
        swebench_report=swebench_report,
        swebench_executor_report=swebench_executor_report,
        swebench_official_report=swebench_official_report,
        swebench_official_execution_report=swebench_official_execution_report,
        real_official_execution_confirmed=False,
        real_artifact_replication_count=0,
    )
    summary = {
        "plan_fingerprint": plan.fingerprint(),
        "matrix_fingerprint": matrix.fingerprint(),
        "trace_run_fingerprint": trace_report.run_fingerprint,
        "ready_for_fse": report.ready_for_fse,
        "ready_for_runner": matrix_report.ready_for_runner,
        "ready_for_synthetic_trace": trace_report.ready_for_synthetic_trace,
        "ready_for_local_runner": local_report.ready_for_local_runner,
        "ready_for_swebench_adapter": swebench_report.ready_for_swebench_adapter,
        "ready_for_swebench_executor": swebench_executor_report.ready_for_swebench_executor,
        "ready_for_swebench_official_subset": swebench_official_report.ready_for_official_subset,
        "ready_for_swebench_official_docker_run": (
            swebench_official_docker_preflight_report.ready_for_swebench_official_docker_run
        ),
        "swebench_official_docker_available": swebench_official_docker_preflight_report.docker_available,
        "swebench_official_swebench_module_available": (
            swebench_official_docker_preflight_report.swebench_module_available
        ),
        "swebench_official_docker_preflight_failures": swebench_official_docker_preflight_report.failures,
        "ready_for_swebench_official_execution_ingest": swebench_official_execution_report.ready_for_official_execution_ingest,
        "ready_for_top_conference_positioning": alignment_report.ready_for_top_conference_positioning,
        "ready_for_artifact_smoke": alignment_report.ready_for_artifact_smoke,
        "ready_for_submission_empirics": alignment_report.ready_for_submission_empirics,
        "empirical_maturity_level": alignment_report.empirical_maturity_level,
        "missing_submission_gates": alignment_report.missing_submission_gates,
        "recommended_next_experiments": alignment_report.recommended_next_experiments,
        "covered_task_families": report.covered_task_families,
        "baseline_count": report.baseline_count,
        "fault_count": report.fault_count,
        "ablation_count": report.ablation_count,
        "related_work_cluster_count": report.related_work_cluster_count,
        "experiment_cell_count": matrix_report.total_cell_count,
        "main_cell_count": matrix_report.main_cell_count,
        "ablation_cell_count": matrix_report.ablation_cell_count,
        "processed_cell_count": trace_report.processed_cell_count,
        "fault_detected_count": trace_report.fault_detected_count,
        "evidence_drift_detected_count": trace_report.evidence_drift_detected_count,
        "replay_passed_count": trace_report.replay_passed_count,
        "local_task_count": local_report.task_count,
        "local_success_count": local_report.success_count,
        "local_hydration_safe_count": local_report.hydration_safe_count,
        "local_phase_gate_passed_count": local_report.phase_gate_passed_count,
        "local_artifact_count": local_report.artifact_count,
        "local_evidence_claim_count": local_report.evidence_claim_count,
        "local_committed_memory_count": local_report.committed_memory_count,
        "swebench_instance_count": swebench_report.instance_count,
        "swebench_success_count": swebench_report.success_count,
        "swebench_hydration_safe_count": swebench_report.hydration_safe_count,
        "swebench_evidence_sound_count": swebench_report.evidence_sound_count,
        "swebench_oracle_audit_sound_count": swebench_report.oracle_audit_sound_count,
        "swebench_candidate_patch_equal_count": swebench_report.candidate_patch_equal_count,
        "swebench_mean_patch_line_jaccard": swebench_report.mean_patch_line_jaccard,
        "swebench_mean_behavioral_divergence_score": swebench_report.mean_behavioral_divergence_score,
        "swebench_executor_instance_count": swebench_executor_report.instance_count,
        "swebench_executor_success_count": swebench_executor_report.success_count,
        "swebench_executor_tests_passed_count": swebench_executor_report.tests_passed_count,
        "swebench_executor_hydration_safe_count": swebench_executor_report.hydration_safe_count,
        "swebench_executor_evidence_sound_count": swebench_executor_report.evidence_sound_count,
        "swebench_executor_oracle_audit_sound_count": swebench_executor_report.oracle_audit_sound_count,
        "swebench_executor_candidate_patch_equal_count": swebench_executor_report.candidate_patch_equal_count,
        "swebench_executor_mean_patch_line_jaccard": swebench_executor_report.mean_patch_line_jaccard,
        "swebench_executor_mean_behavioral_divergence_score": swebench_executor_report.mean_behavioral_divergence_score,
        "swebench_official_instance_count": swebench_official_report.instance_count,
        "swebench_official_matched_prediction_count": swebench_official_report.matched_prediction_count,
        "swebench_official_oracle_audit_sound_count": swebench_official_report.oracle_audit_sound_count,
        "swebench_official_harness_ready_count": swebench_official_report.official_harness_ready_count,
        "swebench_official_local_executor_ready_count": swebench_official_report.local_executor_ready_count,
        "swebench_official_artifact_count": swebench_official_report.artifact_count,
        "ready_for_swebench_official_subset": swebench_official_report.ready_for_official_subset,
        "swebench_official_execution_evaluation_found_count": swebench_official_execution_report.evaluation_found_count,
        "swebench_official_execution_completed_count": swebench_official_execution_report.completed_count,
        "swebench_official_execution_resolved_count": swebench_official_execution_report.resolved_count,
        "swebench_official_execution_resolution_rate": swebench_official_execution_report.resolution_rate,
        "swebench_official_execution_evidence_ledger_sound": swebench_official_execution_report.evidence_ledger_sound,
        "swebench_official_execution_hydration_safe_count": swebench_official_execution_report.hydration_safe_count,
        "swebench_official_execution_artifact_count": swebench_official_execution_report.artifact_count,
        "ready_for_swebench_official_execution_ingest": swebench_official_execution_report.ready_for_official_execution_ingest,
        "rq_ids": report.rq_ids,
        "cells_by_rq": matrix_report.cells_by_rq,
        "cells_by_family": matrix_report.cells_by_family,
        "cells_by_baseline": matrix_report.cells_by_baseline,
        "trace_cells_by_rq": trace_report.cells_by_rq,
        "trace_cells_by_baseline": trace_report.cells_by_baseline,
        "missing_task_families": report.missing_task_families,
        "missing_task_ids": matrix_report.missing_task_ids,
        "missing_baseline_ids": matrix_report.missing_baseline_ids,
        "missing_fault_ids": matrix_report.missing_fault_ids,
        "missing_ablation_ids": matrix_report.missing_ablation_ids,
        "missing_rqs": report.missing_rqs,
        "missing_matrix_rqs": matrix_report.missing_rq_ids,
        "metrics_by_kind": report.metrics_by_kind,
        "trace_metric_averages": trace_report.metric_averages,
        "failures": (
            report.failures
            + matrix_report.failures
            + trace_report.failures
            + local_report.failures
            + swebench_report.failures
            + swebench_executor_report.failures
            + swebench_official_report.failures
            + swebench_official_execution_report.failures
        ),
        "warnings": (
            report.warnings
            + matrix_report.warnings
            + trace_report.warnings
            + local_report.warnings
            + swebench_report.warnings
            + swebench_executor_report.warnings
            + swebench_official_report.warnings
            + swebench_official_execution_report.warnings
        ),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
