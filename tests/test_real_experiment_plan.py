from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research import FseRealExperimentSlicePlanner


class RealExperimentSlicePlannerTests(unittest.TestCase):
    def test_slice_plan_defines_same_task_ablation_variants_and_missing_dependencies(self):
        official_subset_report = {
            "official_harness_command": "python -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Verified",
            "predictions_ref": "/tmp/predictions.jsonl",
            "subset_manifest_ref": "/tmp/subset.json",
        }
        official_preflight = {
            "ready_for_swebench_official_docker_run": False,
            "failures": ["docker command is not available", "Python module 'swebench' is not installed"],
        }
        real_artifact_report = {
            "ready_for_real_artifact_replication": False,
            "warnings": ["no real artifact replication manifest supplied"],
            "failures": [],
        }

        plan = FseRealExperimentSlicePlanner().plan(
            output_dir="/tmp/fse-out",
            official_subset_report=official_subset_report,
            official_docker_preflight_report=official_preflight,
            real_artifact_report=real_artifact_report,
            real_artifact_manifest_template="/tmp/template.json",
        )

        self.assertFalse(plan.ready_to_collect_submission_empirics)
        self.assertFalse(plan.ready_to_run_official_swebench)
        self.assertFalse(plan.ready_to_run_real_artifact_replication)
        self.assertEqual(plan.same_task_ablation_variant_count, 4)
        self.assertEqual(
            {variant.variant_id for variant in plan.ablation_variants},
            {"hermes_full", "no_hydration_manifest", "no_memory_commit", "no_trace_receipt"},
        )
        self.assertIn("docker command is not available", plan.missing_dependencies)
        self.assertIn("no real artifact replication manifest supplied", plan.missing_dependencies)
        self.assertIn("run_official_swebench", {command.command_id for command in plan.commands})
        self.assertEqual(len(plan.plan_fingerprint), 64)


if __name__ == "__main__":
    unittest.main()
