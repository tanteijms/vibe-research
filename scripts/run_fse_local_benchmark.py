from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research import (
    ArtifactReplicationPackageIngestor,
    ArtifactReplicationRunReport,
    FseBenchmarkPlan,
    FseLocalToyTaskRunner,
    FseRealExperimentSlicePlanner,
    FseTopConferenceAlignmentAuditor,
    SweBenchLocalPatchExecutor,
    SweBenchOfficialExecutionIngestor,
    SweBenchOfficialDockerPreflight,
    SweBenchOfficialSubsetBridge,
    SweBenchSmallSubsetAdapter,
    SyntheticFseBenchmarkRunner,
    SyntheticFseTraceRunner,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _artifact_manifest(
    *,
    output_dir: Path,
    local_workspace: Path,
    swebench_workspace: Path,
    swebench_executor_workspace: Path,
    swebench_official_workspace: Path,
    swebench_official_execution_workspace: Path,
    generated_files: list[Path],
    source_refs: list[str],
) -> dict[str, object]:
    return {
        "name": "Harness x Hermes FSE benchmark artifact package",
        "purpose": "Reproduce the current plan/matrix/synthetic/local-run smoke for the FSE 2027 submission direction.",
        "output_dir": str(output_dir),
        "local_workspace": str(local_workspace),
        "swebench_workspace": str(swebench_workspace),
        "swebench_executor_workspace": str(swebench_executor_workspace),
        "swebench_official_workspace": str(swebench_official_workspace),
        "swebench_official_execution_workspace": str(swebench_official_execution_workspace),
        "generated_files": [str(path) for path in generated_files],
        "reproduction_commands": [
            "python scripts/verify_fse_benchmark.py",
            f"python scripts/run_fse_local_benchmark.py --output-dir {output_dir}",
            "python -m pytest -q",
        ],
        "artifact_badge_targets": [
            "Artifacts Evaluated - Functional",
            "Artifacts Evaluated - Reusable",
            "Artifacts Available",
        ],
        "data_availability_section_seed": (
            "The replication package contains benchmark task specifications, a deterministic synthetic trace "
            "runner, a local toy artifact runner, generated JSON reports, and scripts for rerunning all smoke "
            "checks, plus a SWE-bench-style adapter smoke for issue-to-patch patch correctness evidence. "
            "It also includes a local SWE-bench-style patch executor smoke that copies toy repos, applies "
            "test/candidate patches, runs tests, and retains execution artifacts, oracle provenance, and "
            "execution receipts. The official-subset bridge emits a SWE-bench harness command, predictions "
            "JSONL, subset manifest, and oracle-audit receipts for later Docker execution. "
            "The official-execution ingest smoke then retains official-shaped results.json, "
            "instance_results.jsonl, run logs, evidence ledger, and hydration reports; real Docker "
            "outputs can be supplied through --swebench-official-evaluation-dir. "
            "The package will be anonymized during review and made public upon acceptance."
        ),
        "anonymization_notes": [
            "Avoid embedding author names or non-anonymous repository URLs in generated reports.",
            "Use temporary or submission-managed paths for local workspaces during review.",
            "Publish final artifacts through an archival service such as Zenodo after acceptance.",
        ],
        "source_refs": source_refs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the FSE local benchmark artifact smoke.")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where JSON reports and local toy artifacts should be written.",
    )
    parser.add_argument(
        "--max-synthetic-cells",
        type=int,
        default=None,
        help="Optionally limit synthetic trace result cells for a faster smoke. Default: all cells.",
    )
    parser.add_argument(
        "--swebench-jsonl",
        default=None,
        help=(
            "Optional SWE-bench-style JSONL file. If omitted, a deterministic two-instance "
            "SWE-bench-style demo subset is used."
        ),
    )
    parser.add_argument(
        "--max-swebench-instances",
        type=int,
        default=None,
        help="Optionally limit instances loaded from --swebench-jsonl.",
    )
    parser.add_argument(
        "--swebench-executor-jsonl",
        default=None,
        help=(
            "Optional executable SWE-bench-style JSONL. Instances must include local_repo_path/repo_path "
            "and test_command metadata. If omitted, a deterministic local executable demo is used."
        ),
    )
    parser.add_argument(
        "--max-swebench-executor-instances",
        type=int,
        default=None,
        help="Optionally limit instances loaded from --swebench-executor-jsonl.",
    )
    parser.add_argument(
        "--swebench-official-jsonl",
        default=None,
        help="Optional official SWE-bench-style subset JSONL. If omitted, a deterministic demo subset is used.",
    )
    parser.add_argument(
        "--swebench-predictions-jsonl",
        default=None,
        help="Optional official SWE-bench predictions JSONL with instance_id/model_patch/model_name_or_path.",
    )
    parser.add_argument(
        "--max-swebench-official-instances",
        type=int,
        default=None,
        help="Optionally limit instances loaded from --swebench-official-jsonl.",
    )
    parser.add_argument(
        "--swebench-official-dataset-name",
        default=SweBenchOfficialSubsetBridge.DEFAULT_DATASET_NAME,
        help="Dataset name to include in the generated official SWE-bench harness command.",
    )
    parser.add_argument(
        "--swebench-official-evaluation-dir",
        default=None,
        help=(
            "Optional official SWE-bench evaluation output directory or results.json. "
            "If omitted, a demo-shaped execution result is generated only to verify the ingest contract."
        ),
    )
    parser.add_argument(
        "--real-artifact-replication-count",
        type=int,
        default=0,
        help=(
            "Number of real non-toy artifact-replication packages connected to this run. "
            "Default 0 keeps the top-conference submission gate honest."
        ),
    )
    parser.add_argument(
        "--real-artifact-manifest",
        action="append",
        default=[],
        help=(
            "Path to a real paper artifact replication manifest JSON. Can be supplied multiple times. "
            "When present, the package is copied, executed, audited, and counted toward the real-artifact gate."
        ),
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = output_dir / "reports"
    local_workspace = output_dir / "local_artifacts"
    swebench_workspace = output_dir / "swebench_adapter"
    swebench_executor_workspace = output_dir / "swebench_executor"
    swebench_official_workspace = output_dir / "swebench_official_subset"
    swebench_official_execution_workspace = output_dir / "swebench_official_execution_ingest"

    plan = FseBenchmarkPlan.default()
    plan_report = plan.evaluate()
    matrix = SyntheticFseBenchmarkRunner(plan).build_matrix()
    matrix_report = matrix.report(plan)
    trace_report = SyntheticFseTraceRunner(plan, matrix).run(max_cells=args.max_synthetic_cells)
    local_report = FseLocalToyTaskRunner(plan).run(local_workspace)
    swebench_adapter = (
        SweBenchSmallSubsetAdapter.from_jsonl(
            args.swebench_jsonl,
            limit=args.max_swebench_instances,
        )
        if args.swebench_jsonl
        else SweBenchSmallSubsetAdapter()
    )
    swebench_report = swebench_adapter.run(swebench_workspace)
    swebench_executor = (
        SweBenchLocalPatchExecutor.from_jsonl(
            args.swebench_executor_jsonl,
            limit=args.max_swebench_executor_instances,
        )
        if args.swebench_executor_jsonl
        else SweBenchLocalPatchExecutor.demo(swebench_executor_workspace / "source_repos")
    )
    swebench_executor_report = swebench_executor.run(swebench_executor_workspace / "runs")
    swebench_official_bridge = (
        SweBenchOfficialSubsetBridge.from_jsonl(
            args.swebench_official_jsonl,
            predictions_path=args.swebench_predictions_jsonl,
            limit=args.max_swebench_official_instances,
            dataset_name=args.swebench_official_dataset_name,
        )
        if args.swebench_official_jsonl
        else SweBenchOfficialSubsetBridge.demo()
    )
    swebench_official_report = swebench_official_bridge.run(swebench_official_workspace)
    swebench_official_docker_preflight_report = SweBenchOfficialDockerPreflight().run(
        swebench_official_report
    )
    evaluation_root = (
        Path(args.swebench_official_evaluation_dir).resolve()
        if args.swebench_official_evaluation_dir
        else SweBenchOfficialExecutionIngestor.demo_evaluation_results(
            swebench_official_report,
            swebench_official_execution_workspace / "demo_evaluation_results",
        )
    )
    swebench_official_execution_report = SweBenchOfficialExecutionIngestor(
        subset_manifest_path=swebench_official_report.subset_manifest_ref,
        evaluation_results_path=evaluation_root,
    ).run(swebench_official_execution_workspace / "ingest")
    real_artifact_workspace = output_dir / "real_artifact_replication"
    real_artifact_report = (
        ArtifactReplicationPackageIngestor.from_manifest_paths(args.real_artifact_manifest).run(
            real_artifact_workspace
        )
        if args.real_artifact_manifest
        else ArtifactReplicationRunReport.empty()
    )
    real_artifact_count = max(args.real_artifact_replication_count, real_artifact_report.success_count)
    alignment_report = FseTopConferenceAlignmentAuditor(source_refs=plan.source_refs).audit(
        plan_report=plan_report,
        matrix_report=matrix_report,
        trace_report=trace_report,
        local_report=local_report,
        swebench_report=swebench_report,
        swebench_executor_report=swebench_executor_report,
        swebench_official_report=swebench_official_report,
        swebench_official_execution_report=swebench_official_execution_report,
        real_official_execution_confirmed=args.swebench_official_evaluation_dir is not None,
        real_artifact_replication_count=real_artifact_count,
    )
    real_experiment_plan = FseRealExperimentSlicePlanner(source_refs=plan.source_refs).plan(
        output_dir=output_dir,
        official_subset_report=swebench_official_report,
        official_docker_preflight_report=swebench_official_docker_preflight_report,
        real_artifact_report=real_artifact_report,
        real_artifact_manifest_template=(
            Path(__file__).resolve().parents[1]
            / "yys"
            / "all"
            / "0802"
            / "real_artifact_replication_manifest_template.json"
        ),
    )

    generated_files = [
        reports_dir / "benchmark_plan.json",
        reports_dir / "benchmark_readiness.json",
        reports_dir / "benchmark_matrix.json",
        reports_dir / "benchmark_matrix_report.json",
        reports_dir / "synthetic_trace_report.json",
        reports_dir / "local_run_report.json",
        reports_dir / "swebench_adapter_report.json",
        reports_dir / "swebench_executor_report.json",
        reports_dir / "swebench_official_subset_report.json",
        reports_dir / "swebench_official_docker_preflight_report.json",
        reports_dir / "swebench_official_execution_ingest_report.json",
        reports_dir / "real_artifact_replication_report.json",
        reports_dir / "real_experiment_slice_plan.json",
        reports_dir / "top_conference_alignment_report.json",
        reports_dir / "artifact_manifest.json",
        reports_dir / "summary.json",
    ]

    manifest = _artifact_manifest(
        output_dir=output_dir,
        local_workspace=local_workspace,
        swebench_workspace=swebench_workspace,
        swebench_executor_workspace=swebench_executor_workspace,
        swebench_official_workspace=swebench_official_workspace,
        swebench_official_execution_workspace=swebench_official_execution_workspace,
        generated_files=generated_files,
        source_refs=plan.source_refs,
    )
    summary = {
        "ready": (
            plan_report.ready_for_fse
            and matrix_report.ready_for_runner
            and trace_report.ready_for_synthetic_trace
            and local_report.ready_for_local_runner
            and swebench_report.ready_for_swebench_adapter
            and swebench_executor_report.ready_for_swebench_executor
            and swebench_official_report.ready_for_official_subset
            and swebench_official_execution_report.ready_for_official_execution_ingest
        ),
        "output_dir": str(output_dir),
        "plan_fingerprint": plan.fingerprint(),
        "matrix_fingerprint": matrix.fingerprint(),
        "trace_run_fingerprint": trace_report.run_fingerprint,
        "local_run_fingerprint": local_report.run_fingerprint,
        "task_family_count": len(plan.task_families),
        "experiment_cell_count": matrix_report.total_cell_count,
        "synthetic_processed_cell_count": trace_report.processed_cell_count,
        "synthetic_fault_detected_count": trace_report.fault_detected_count,
        "synthetic_evidence_drift_detected_count": trace_report.evidence_drift_detected_count,
        "local_task_count": local_report.task_count,
        "local_success_count": local_report.success_count,
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
        "swebench_official_ready": swebench_official_report.ready_for_official_subset,
        "swebench_official_predictions_ref": swebench_official_report.predictions_ref,
        "swebench_official_subset_manifest_ref": swebench_official_report.subset_manifest_ref,
        "swebench_official_docker_preflight_ready": (
            swebench_official_docker_preflight_report.ready_for_swebench_official_docker_run
        ),
        "swebench_official_docker_available": swebench_official_docker_preflight_report.docker_available,
        "swebench_official_swebench_module_available": (
            swebench_official_docker_preflight_report.swebench_module_available
        ),
        "swebench_official_docker_preflight_failures": swebench_official_docker_preflight_report.failures,
        "swebench_official_execution_ingest_ready": swebench_official_execution_report.ready_for_official_execution_ingest,
        "swebench_official_execution_evaluation_found_count": swebench_official_execution_report.evaluation_found_count,
        "swebench_official_execution_completed_count": swebench_official_execution_report.completed_count,
        "swebench_official_execution_resolved_count": swebench_official_execution_report.resolved_count,
        "swebench_official_execution_resolution_rate": swebench_official_execution_report.resolution_rate,
        "swebench_official_execution_evidence_ledger_sound": swebench_official_execution_report.evidence_ledger_sound,
        "swebench_official_execution_hydration_safe_count": swebench_official_execution_report.hydration_safe_count,
        "swebench_official_execution_artifact_count": swebench_official_execution_report.artifact_count,
        "swebench_official_execution_ingest_report_ref": swebench_official_execution_report.ingest_report_ref,
        "real_artifact_replication_ready": real_artifact_report.ready_for_real_artifact_replication,
        "real_artifact_replication_package_count": real_artifact_report.package_count,
        "real_artifact_replication_success_count": real_artifact_report.success_count,
        "real_artifact_replication_artifact_count": real_artifact_report.artifact_count,
        "real_artifact_replication_metric_file_count": real_artifact_report.metric_file_count,
        "real_artifact_replication_count_for_submission_gate": real_artifact_count,
        "real_experiment_slice_ready": real_experiment_plan.ready_to_collect_submission_empirics,
        "real_experiment_same_task_ablation_variant_count": real_experiment_plan.same_task_ablation_variant_count,
        "real_experiment_missing_dependencies": real_experiment_plan.missing_dependencies,
        "ready_for_top_conference_positioning": alignment_report.ready_for_top_conference_positioning,
        "ready_for_artifact_smoke": alignment_report.ready_for_artifact_smoke,
        "ready_for_submission_empirics": alignment_report.ready_for_submission_empirics,
        "empirical_maturity_level": alignment_report.empirical_maturity_level,
        "missing_submission_gates": alignment_report.missing_submission_gates,
        "recommended_next_experiments": alignment_report.recommended_next_experiments,
        "failures": (
            plan_report.failures
            + matrix_report.failures
            + trace_report.failures
            + local_report.failures
            + swebench_report.failures
            + swebench_executor_report.failures
            + swebench_official_report.failures
            + real_artifact_report.failures
            + swebench_official_execution_report.failures
        ),
        "warnings": (
            plan_report.warnings
            + matrix_report.warnings
            + trace_report.warnings
            + local_report.warnings
            + swebench_report.warnings
            + swebench_executor_report.warnings
            + swebench_official_report.warnings
            + swebench_official_docker_preflight_report.warnings
            + swebench_official_execution_report.warnings
            + real_artifact_report.warnings
        ),
        "generated_files": [str(path) for path in generated_files],
    }

    _write_json(reports_dir / "benchmark_plan.json", plan.to_dict())
    _write_json(reports_dir / "benchmark_readiness.json", plan_report.to_dict())
    _write_json(reports_dir / "benchmark_matrix.json", matrix.to_dict())
    _write_json(reports_dir / "benchmark_matrix_report.json", matrix_report.to_dict())
    _write_json(reports_dir / "synthetic_trace_report.json", trace_report.to_dict())
    _write_json(reports_dir / "local_run_report.json", local_report.to_dict())
    _write_json(reports_dir / "swebench_adapter_report.json", swebench_report.to_dict())
    _write_json(reports_dir / "swebench_executor_report.json", swebench_executor_report.to_dict())
    _write_json(reports_dir / "swebench_official_subset_report.json", swebench_official_report.to_dict())
    _write_json(
        reports_dir / "swebench_official_docker_preflight_report.json",
        swebench_official_docker_preflight_report.to_dict(),
    )
    _write_json(reports_dir / "swebench_official_execution_ingest_report.json", swebench_official_execution_report.to_dict())
    _write_json(reports_dir / "real_artifact_replication_report.json", real_artifact_report.to_dict())
    _write_json(reports_dir / "real_experiment_slice_plan.json", real_experiment_plan.to_dict())
    _write_json(reports_dir / "top_conference_alignment_report.json", alignment_report.to_dict())
    _write_json(reports_dir / "artifact_manifest.json", manifest)
    _write_json(reports_dir / "summary.json", summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
