from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class FseArtifactCliTests(unittest.TestCase):
    def test_run_fse_local_benchmark_emits_reproducible_artifact_package(self):
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "scripts" / "run_fse_local_benchmark.py"

        with TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--output-dir",
                    temp_dir,
                    "--max-synthetic-cells",
                    "8",
                ],
                cwd=repo_root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
            )

            output_dir = Path(temp_dir)
            reports_dir = output_dir / "reports"
            expected_reports = [
                "benchmark_plan.json",
                "benchmark_readiness.json",
                "benchmark_matrix.json",
                "benchmark_matrix_report.json",
                "synthetic_trace_report.json",
                "local_run_report.json",
                "swebench_adapter_report.json",
                "swebench_executor_report.json",
                "swebench_official_subset_report.json",
                "swebench_official_docker_preflight_report.json",
                "swebench_official_execution_ingest_report.json",
                "real_artifact_replication_report.json",
                "real_experiment_slice_plan.json",
                "top_conference_alignment_report.json",
                "artifact_manifest.json",
                "summary.json",
            ]
            for filename in expected_reports:
                self.assertTrue((reports_dir / filename).exists(), filename)

            summary = json.loads((reports_dir / "summary.json").read_text(encoding="utf-8"))
            manifest = json.loads((reports_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
            local_report = json.loads((reports_dir / "local_run_report.json").read_text(encoding="utf-8"))

            self.assertTrue(summary["ready"])
            self.assertEqual(summary["failures"], [])
            self.assertIn("synthetic trace run truncated to 8 cells", summary["warnings"])
            self.assertIn("no real artifact replication manifest supplied", summary["warnings"])
            self.assertEqual(summary["experiment_cell_count"], 152)
            self.assertEqual(summary["synthetic_processed_cell_count"], 8)
            self.assertEqual(summary["local_task_count"], 3)
            self.assertEqual(summary["local_success_count"], 3)
            self.assertGreaterEqual(summary["local_artifact_count"], 9)
            self.assertGreaterEqual(summary["local_evidence_claim_count"], 3)
            self.assertGreaterEqual(summary["local_committed_memory_count"], 3)
            self.assertEqual(summary["swebench_instance_count"], 2)
            self.assertEqual(summary["swebench_success_count"], 2)
            self.assertEqual(summary["swebench_hydration_safe_count"], 2)
            self.assertEqual(summary["swebench_evidence_sound_count"], 2)
            self.assertEqual(summary["swebench_oracle_audit_sound_count"], 2)
            self.assertEqual(summary["swebench_candidate_patch_equal_count"], 1)
            self.assertEqual(summary["swebench_executor_instance_count"], 2)
            self.assertEqual(summary["swebench_executor_success_count"], 2)
            self.assertEqual(summary["swebench_executor_tests_passed_count"], 1)
            self.assertEqual(summary["swebench_executor_hydration_safe_count"], 2)
            self.assertEqual(summary["swebench_executor_evidence_sound_count"], 2)
            self.assertEqual(summary["swebench_executor_oracle_audit_sound_count"], 2)
            self.assertEqual(summary["swebench_executor_candidate_patch_equal_count"], 1)
            self.assertEqual(summary["swebench_official_instance_count"], 2)
            self.assertEqual(summary["swebench_official_matched_prediction_count"], 2)
            self.assertEqual(summary["swebench_official_oracle_audit_sound_count"], 2)
            self.assertEqual(summary["swebench_official_harness_ready_count"], 2)
            self.assertEqual(summary["swebench_official_local_executor_ready_count"], 0)
            self.assertEqual(summary["swebench_official_artifact_count"], 10)
            self.assertTrue(summary["swebench_official_ready"])
            self.assertIsInstance(summary["swebench_official_docker_preflight_ready"], bool)
            self.assertIsInstance(summary["swebench_official_docker_available"], bool)
            self.assertIsInstance(summary["swebench_official_swebench_module_available"], bool)
            self.assertIsInstance(summary["swebench_official_docker_preflight_failures"], list)
            self.assertTrue(summary["swebench_official_execution_ingest_ready"])
            self.assertEqual(summary["swebench_official_execution_evaluation_found_count"], 2)
            self.assertEqual(summary["swebench_official_execution_completed_count"], 2)
            self.assertEqual(summary["swebench_official_execution_resolved_count"], 1)
            self.assertEqual(summary["swebench_official_execution_resolution_rate"], 0.5)
            self.assertTrue(summary["swebench_official_execution_evidence_ledger_sound"])
            self.assertEqual(summary["swebench_official_execution_hydration_safe_count"], 2)
            self.assertGreaterEqual(summary["swebench_official_execution_artifact_count"], 8)
            self.assertFalse(summary["real_artifact_replication_ready"])
            self.assertEqual(summary["real_artifact_replication_package_count"], 0)
            self.assertEqual(summary["real_artifact_replication_success_count"], 0)
            self.assertEqual(summary["real_artifact_replication_count_for_submission_gate"], 0)
            self.assertFalse(summary["real_experiment_slice_ready"])
            self.assertEqual(summary["real_experiment_same_task_ablation_variant_count"], 4)
            self.assertIn("no real artifact replication manifest supplied", summary["real_experiment_missing_dependencies"])
            self.assertTrue(summary["ready_for_top_conference_positioning"])
            self.assertTrue(summary["ready_for_artifact_smoke"])
            self.assertFalse(summary["ready_for_submission_empirics"])
            self.assertEqual(summary["empirical_maturity_level"], "L3_official_ingest_contract_smoke")
            self.assertIn(
                "run at least 5 SWE-bench Verified instances through the official Docker harness",
                summary["missing_submission_gates"],
            )

            self.assertEqual(manifest["output_dir"], str(output_dir.resolve()))
            self.assertEqual(manifest["local_workspace"], str((output_dir / "local_artifacts").resolve()))
            self.assertEqual(manifest["swebench_workspace"], str((output_dir / "swebench_adapter").resolve()))
            self.assertEqual(manifest["swebench_executor_workspace"], str((output_dir / "swebench_executor").resolve()))
            self.assertEqual(
                manifest["swebench_official_execution_workspace"],
                str((output_dir / "swebench_official_execution_ingest").resolve()),
            )
            self.assertIn("Artifacts Evaluated - Functional", manifest["artifact_badge_targets"])
            for generated_file in manifest["generated_files"]:
                self.assertTrue(Path(generated_file).exists(), generated_file)

            self.assertTrue(local_report["ready_for_local_runner"])
            self.assertEqual(local_report["success_count"], 3)
            for result in local_report["task_results"]:
                self.assertTrue(Path(result["workspace_ref"]).exists())
                self.assertTrue(result["hydration_safe"])
                self.assertTrue(result["phase_gate_passed"])
                for artifact_uri in result["artifact_uris"]:
                    self.assertTrue(Path(artifact_uri).exists(), artifact_uri)

    def test_run_fse_local_benchmark_counts_real_artifact_manifest_for_submission_gate(self):
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "scripts" / "run_fse_local_benchmark.py"

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "real_artifact"
            package.mkdir()
            (package / "run.py").write_text(
                "from pathlib import Path\n"
                "Path('results').mkdir(exist_ok=True)\n"
                "Path('results/metrics.json').write_text('{\"metric\": 0.91}')\n"
                "print('done')\n",
                encoding="utf-8",
            )
            manifest = root / "real_artifact_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "package_id": "real_artifact_cli_demo",
                        "paper_title": "Real Artifact CLI Demo",
                        "artifact_root": str(package),
                        "run_command": [sys.executable, "run.py"],
                        "expected_artifacts": ["results/metrics.json"],
                        "expected_metric_files": ["results/metrics.json"],
                        "source_refs": ["https://example.org/real-artifact-cli-demo"],
                        "timeout_s": 10,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            output_dir = root / "out"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--output-dir",
                    str(output_dir),
                    "--max-synthetic-cells",
                    "8",
                    "--real-artifact-manifest",
                    str(manifest),
                ],
                cwd=repo_root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
            )
            summary = json.loads((output_dir / "reports" / "summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["real_artifact_replication_ready"])
            self.assertEqual(summary["real_artifact_replication_package_count"], 1)
            self.assertEqual(summary["real_artifact_replication_success_count"], 1)
            self.assertEqual(summary["real_artifact_replication_metric_file_count"], 1)
            self.assertEqual(summary["real_artifact_replication_count_for_submission_gate"], 1)
            self.assertFalse(summary["ready_for_submission_empirics"])
            self.assertIn(
                "run at least 5 SWE-bench Verified instances through the official Docker harness",
                summary["missing_submission_gates"],
            )
            self.assertNotIn(
                "replace toy artifact replication with at least 1 real paper artifact package",
                summary["missing_submission_gates"],
            )


if __name__ == "__main__":
    unittest.main()
