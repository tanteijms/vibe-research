from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research import (
    AblationKind,
    BaselineKind,
    FaultKind,
    FseBenchmarkPlan,
    FseTopConferenceAlignmentAuditor,
    FseTaskFamily,
    MetricKind,
    SyntheticFseBenchmarkRunner,
    SyntheticFseTraceRunner,
)


class FseBenchmarkPlanTests(unittest.TestCase):
    def test_default_plan_covers_fse_task_baseline_fault_and_ablation_matrix(self):
        plan = FseBenchmarkPlan.default()
        report = plan.evaluate()

        self.assertTrue(report.ready_for_fse)
        self.assertEqual(report.failures, [])
        self.assertEqual(
            set(report.covered_task_families),
            {
                FseTaskFamily.ISSUE_TO_PATCH,
                FseTaskFamily.ARTIFACT_REPLICATION,
                FseTaskFamily.INCIDENT_RCA,
            },
        )
        self.assertEqual(report.baseline_count, 5)
        self.assertEqual(report.fault_count, 16)
        self.assertEqual(report.ablation_count, 7)
        self.assertEqual(report.related_work_cluster_count, 8)
        self.assertEqual(set(report.rq_ids), {"RQ1", "RQ2", "RQ3", "RQ4"})
        self.assertIn("replay_fidelity", report.metrics_by_kind[MetricKind.REPLAY])
        self.assertIn("token_cost", report.metrics_by_kind[MetricKind.COST])
        self.assertIn("memory_interference_block_rate", report.metrics_by_kind[MetricKind.SAFETY])
        self.assertIn("retrieval_evidence_stability", report.metrics_by_kind[MetricKind.SAFETY])
        self.assertIn("context_pin_recall", report.metrics_by_kind[MetricKind.SAFETY])
        self.assertIn("silent_evidence_defect_block_rate", report.metrics_by_kind[MetricKind.SAFETY])
        self.assertIn("active_frame_retention", report.metrics_by_kind[MetricKind.EFFECTIVENESS])
        self.assertIn("artifact_provenance_completeness", report.metrics_by_kind[MetricKind.REPLAY])
        self.assertIn("official_execution_ingest_soundness", report.metrics_by_kind[MetricKind.REPLAY])
        self.assertIn("benchmark_oracle_provenance_rate", report.metrics_by_kind[MetricKind.COST])
        self.assertEqual(len(plan.fingerprint()), 64)
        self.assertEqual(len(report.plan_fingerprint), 64)

    def test_readiness_report_flags_missing_family_and_missing_replication_plan(self):
        plan = FseBenchmarkPlan.default()
        reduced = replace(
            plan,
            tasks=[task for task in plan.tasks if task.family != FseTaskFamily.INCIDENT_RCA],
            data_availability_statement="",
        )

        report = reduced.evaluate()

        self.assertFalse(report.ready_for_fse)
        self.assertIn(FseTaskFamily.INCIDENT_RCA, report.missing_task_families)
        self.assertIn("missing task families: incident_rca", report.failures)
        self.assertIn("missing data availability statement", report.failures)

    def test_evidence_retaining_replay_is_explicit_in_rq3_faults_and_ablations(self):
        plan = FseBenchmarkPlan.default()
        fault_ids = {fault.fault_id for fault in plan.fault_scenarios}
        ablation_ids = {ablation.ablation_id for ablation in plan.ablations}
        rq3 = next(rq for rq in plan.research_questions if rq.rq_id == "RQ3")

        self.assertIn(FaultKind.EVIDENCE_RECEIPT_DRIFT, fault_ids)
        self.assertIn(FaultKind.MEMORY_INTERFERENCE, fault_ids)
        self.assertIn(FaultKind.RETRIEVAL_COMPONENT_SHIFT, fault_ids)
        self.assertIn(FaultKind.CONTEXT_MANAGER_DROPPED_PIN, fault_ids)
        self.assertIn(FaultKind.BENCHMARK_ORACLE_DRIFT, fault_ids)
        self.assertIn(FaultKind.SILENT_EVIDENCE_DEFECT, fault_ids)
        self.assertIn(FaultKind.OFFICIAL_EXECUTION_RECEIPT_DRIFT, fault_ids)
        self.assertIn(AblationKind.NO_TRACE_RECEIPT, ablation_ids)
        self.assertIn(FaultKind.EVIDENCE_RECEIPT_DRIFT, rq3.suggested_faults)
        self.assertIn(FaultKind.RETRIEVAL_COMPONENT_SHIFT, rq3.suggested_faults)
        self.assertIn(AblationKind.NO_TRACE_RECEIPT, rq3.suggested_ablations)
        self.assertIn("claim_preserving_replay_fidelity", rq3.key_metrics)
        self.assertIn("artifact_provenance_completeness", rq3.key_metrics)
        self.assertIn("official_execution_ingest_soundness", rq3.key_metrics)
        self.assertIn(FaultKind.BENCHMARK_ORACLE_DRIFT, rq3.suggested_faults)
        self.assertIn(FaultKind.OFFICIAL_EXECUTION_RECEIPT_DRIFT, rq3.suggested_faults)
        rq2 = next(rq for rq in plan.research_questions if rq.rq_id == "RQ2")
        self.assertIn("memory_interference_block_rate", rq2.key_metrics)
        self.assertIn("retrieval_evidence_stability", rq2.key_metrics)
        self.assertIn("silent_evidence_defect_block_rate", rq2.key_metrics)
        rq1 = next(rq for rq in plan.research_questions if rq.rq_id == "RQ1")
        self.assertIn("context_pin_recall", rq1.key_metrics)
        self.assertIn("active_frame_retention", rq1.key_metrics)
        self.assertIn(FaultKind.CONTEXT_MANAGER_DROPPED_PIN, rq1.suggested_faults)

    def test_synthetic_runner_expands_plan_into_fse_experiment_matrix(self):
        plan = FseBenchmarkPlan.default()
        matrix = SyntheticFseBenchmarkRunner(plan).build_matrix()
        report = matrix.report(plan)

        self.assertTrue(report.ready_for_runner)
        self.assertEqual(report.failures, [])
        self.assertGreaterEqual(report.total_cell_count, 50)
        self.assertGreater(report.main_cell_count, 0)
        self.assertGreater(report.ablation_cell_count, 0)
        self.assertEqual(report.missing_task_ids, [])
        self.assertEqual(report.missing_baseline_ids, [])
        self.assertEqual(report.missing_fault_ids, [])
        self.assertEqual(report.missing_ablation_ids, [])
        self.assertEqual(report.missing_rq_ids, [])
        self.assertIn("RQ3", report.cells_by_rq)
        self.assertGreater(report.cells_by_rq["RQ3"], 0)
        self.assertIn("claim_preserving_replay_fidelity", report.covered_metric_ids)
        self.assertIn("official_execution_ingest_soundness", report.covered_metric_ids)
        self.assertIn("silent_evidence_defect_block_rate", report.covered_metric_ids)
        self.assertIn("active_frame_retention", report.covered_metric_ids)
        self.assertEqual(len(matrix.fingerprint()), 64)

    def test_synthetic_runner_can_build_main_matrix_without_ablations(self):
        plan = FseBenchmarkPlan.default()
        matrix = SyntheticFseBenchmarkRunner(plan).build_matrix(include_ablations=False)
        report = matrix.report(plan)

        self.assertFalse(report.ready_for_runner)
        self.assertEqual(report.ablation_cell_count, 0)
        self.assertIn("experiment matrix contains no ablation cells", report.failures)

    def test_synthetic_trace_runner_produces_result_report_for_fse_matrix(self):
        plan = FseBenchmarkPlan.default()
        matrix = SyntheticFseBenchmarkRunner(plan).build_matrix()
        trace_report = SyntheticFseTraceRunner(plan, matrix).run()

        self.assertTrue(trace_report.ready_for_synthetic_trace)
        self.assertEqual(trace_report.processed_cell_count, trace_report.total_cell_count)
        self.assertEqual(len(trace_report.cell_results), trace_report.total_cell_count)
        self.assertGreaterEqual(trace_report.fault_detected_count, 1)
        self.assertGreaterEqual(trace_report.evidence_drift_detected_count, 1)
        self.assertLess(trace_report.evidence_drift_detected_count, trace_report.fault_detected_count)
        self.assertIn("replay_fidelity", trace_report.metric_averages)
        self.assertIn(FaultKind.EVIDENCE_RECEIPT_DRIFT, trace_report.cells_by_fault)
        self.assertIn(BaselineKind.CHECKPOINT_ONLY, trace_report.cells_by_baseline)
        self.assertEqual(len(trace_report.run_fingerprint), 64)

    def test_top_conference_alignment_separates_smoke_readiness_from_submission_empirics(self):
        plan = FseBenchmarkPlan.default()
        plan_report = plan.evaluate()
        matrix = SyntheticFseBenchmarkRunner(plan).build_matrix()
        matrix_report = matrix.report(plan)
        trace_report = SyntheticFseTraceRunner(plan, matrix).run()

        class Report:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        alignment = FseTopConferenceAlignmentAuditor(source_refs=plan.source_refs).audit(
            plan_report=plan_report,
            matrix_report=matrix_report,
            trace_report=trace_report,
            local_report=Report(ready_for_local_runner=True, success_count=3),
            swebench_report=Report(ready_for_swebench_adapter=True),
            swebench_executor_report=Report(ready_for_swebench_executor=True),
            swebench_official_report=Report(ready_for_official_subset=True),
            swebench_official_execution_report=Report(
                ready_for_official_execution_ingest=True,
                completed_count=2,
            ),
            real_official_execution_confirmed=False,
            real_artifact_replication_count=0,
        )

        self.assertTrue(alignment.ready_for_top_conference_positioning)
        self.assertTrue(alignment.ready_for_artifact_smoke)
        self.assertFalse(alignment.ready_for_submission_empirics)
        self.assertEqual(alignment.empirical_maturity_level, "L3_official_ingest_contract_smoke")
        self.assertIn(
            "run at least 5 SWE-bench Verified instances through the official Docker harness",
            alignment.missing_submission_gates,
        )

        submission_ready = FseTopConferenceAlignmentAuditor(source_refs=plan.source_refs).audit(
            plan_report=plan_report,
            matrix_report=matrix_report,
            trace_report=trace_report,
            local_report=Report(ready_for_local_runner=True, success_count=3),
            swebench_report=Report(ready_for_swebench_adapter=True),
            swebench_executor_report=Report(ready_for_swebench_executor=True),
            swebench_official_report=Report(ready_for_official_subset=True),
            swebench_official_execution_report=Report(
                ready_for_official_execution_ingest=True,
                completed_count=5,
            ),
            real_official_execution_confirmed=True,
            real_artifact_replication_count=1,
        )

        self.assertTrue(submission_ready.ready_for_submission_empirics)
        self.assertEqual(submission_ready.empirical_maturity_level, "L5_submission_empirics_ready")
        self.assertEqual(submission_ready.missing_submission_gates, [])
        self.assertEqual(len(submission_ready.report_fingerprint), 64)


if __name__ == "__main__":
    unittest.main()
