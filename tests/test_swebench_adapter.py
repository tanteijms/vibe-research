from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from vibe_research import (
    SweBenchInstance,
    SweBenchLocalPatchExecutor,
    SweBenchOfficialExecutionIngestor,
    SweBenchOfficialSubsetBridge,
    SweBenchSmallSubsetAdapter,
)


def _patch(path: str, before: str, after: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@\n"
        f"-{before}\n"
        f"+{after}\n"
    )


class SweBenchSmallSubsetAdapterTests(unittest.TestCase):
    def test_adapter_materializes_jsonl_subset_with_patch_divergence_evidence(self):
        matching_patch = _patch("pkg/calc.py", "return a - b", "return a + b")
        divergent_gold = _patch("pkg/parser.py", "return token == expected", "return token.strip() == expected")
        divergent_candidate = _patch("pkg/parser.py", "return token == expected", "return token.lower() == expected")
        records = [
            {
                "instance_id": "demo__calc-001",
                "repo": "demo/calc",
                "base_commit": "abc123",
                "problem_statement": "add subtracts the second argument",
                "patch": matching_patch,
                "test_patch": _patch("tests/test_calc.py", "pass", "assert add(1, 2) == 3"),
                "candidate_patch": matching_patch,
                "FAIL_TO_PASS": ["tests/test_calc.py::test_add"],
            },
            {
                "instance_id": "demo__parser-002",
                "repo": "demo/parser",
                "base_commit": "def456",
                "problem_statement": "parser should strip whitespace",
                "patch": divergent_gold,
                "test_patch": _patch("tests/test_parser.py", "pass", "assert parse(' ok ') == 'ok'"),
                "candidate_patch": divergent_candidate,
                "FAIL_TO_PASS": "[\"tests/test_parser.py::test_strip\"]",
            },
        ]

        with TemporaryDirectory() as temp_dir:
            jsonl_path = Path(temp_dir) / "swebench_subset.jsonl"
            jsonl_path.write_text(
                "\n".join(json.dumps(record, sort_keys=True) for record in records),
                encoding="utf-8",
            )

            adapter = SweBenchSmallSubsetAdapter.from_jsonl(jsonl_path)
            report = adapter.run(Path(temp_dir) / "out")

            self.assertTrue(report.ready_for_swebench_adapter)
            self.assertEqual(report.failures, [])
            self.assertEqual(report.instance_count, 2)
            self.assertEqual(report.success_count, 2)
            self.assertEqual(report.hydration_safe_count, 2)
            self.assertEqual(report.evidence_sound_count, 2)
            self.assertEqual(report.phase_gate_passed_count, 2)
            self.assertEqual(report.test_patch_present_count, 2)
            self.assertEqual(report.oracle_audit_sound_count, 2)
            self.assertEqual(report.candidate_patch_equal_count, 1)
            self.assertGreaterEqual(report.artifact_count, 14)
            self.assertGreater(report.mean_patch_line_jaccard, 0.0)
            self.assertLess(report.mean_behavioral_divergence_score, 1.0)
            self.assertEqual(len(report.run_fingerprint), 64)

            divergent = next(result for result in report.instance_results if result.instance_id == "demo__parser-002")
            self.assertFalse(divergent.patch_equal_to_gold)
            self.assertEqual(divergent.changed_file_overlap, 1.0)
            self.assertGreater(divergent.behavioral_divergence_score, 0.0)
            self.assertTrue(divergent.hydration_safe)
            for artifact_uri in divergent.artifact_uris:
                self.assertTrue(Path(artifact_uri).exists(), artifact_uri)

            correctness_report = Path(divergent.workspace_ref) / "patch_correctness_report.json"
            payload = json.loads(correctness_report.read_text(encoding="utf-8"))
            self.assertIn("behavioral_divergence_score", payload)
            self.assertIn("oracle_audit_fingerprint", payload)
            self.assertEqual(payload["repo"], "demo/parser")

            oracle_report = Path(divergent.workspace_ref) / "oracle_audit_report.json"
            oracle_payload = json.loads(oracle_report.read_text(encoding="utf-8"))
            self.assertTrue(oracle_payload["sound"])
            self.assertEqual(oracle_payload["missing_fields"], [])
            self.assertEqual(len(oracle_payload["oracle_fingerprint"]), 64)
            self.assertIn("gold_patch_sha256", oracle_payload)

    def test_adapter_blocks_instance_without_test_patch(self):
        instance = SweBenchInstance(
            instance_id="demo__missing-test",
            repo="demo/repo",
            base_commit="abc123",
            problem_statement="missing regression test",
            patch=_patch("pkg/mod.py", "return False", "return True"),
            test_patch="",
            candidate_patch=_patch("pkg/mod.py", "return False", "return True"),
        )

        with TemporaryDirectory() as temp_dir:
            report = SweBenchSmallSubsetAdapter([instance]).run(temp_dir)

            self.assertFalse(report.ready_for_swebench_adapter)
            self.assertEqual(report.instance_count, 1)
            self.assertEqual(report.success_count, 0)
            self.assertIn("demo__missing-test: missing test_patch", report.failures)

    def test_local_patch_executor_applies_patches_runs_tests_and_retains_hydration_evidence(self):
        with TemporaryDirectory() as temp_dir:
            executor = SweBenchLocalPatchExecutor.demo(Path(temp_dir) / "source_repos")
            report = executor.run(Path(temp_dir) / "runs")

            self.assertTrue(report.ready_for_swebench_executor)
            self.assertEqual(report.failures, [])
            self.assertEqual(report.instance_count, 2)
            self.assertEqual(report.success_count, 2)
            self.assertEqual(report.tests_passed_count, 1)
            self.assertEqual(report.hydration_safe_count, 2)
            self.assertEqual(report.evidence_sound_count, 2)
            self.assertEqual(report.phase_gate_passed_count, 2)
            self.assertEqual(report.oracle_audit_sound_count, 2)
            self.assertEqual(report.candidate_patch_equal_count, 1)
            self.assertGreaterEqual(report.artifact_count, 18)
            self.assertGreater(report.mean_patch_line_jaccard, 0.0)
            self.assertGreaterEqual(report.mean_behavioral_divergence_score, 0.0)
            self.assertEqual(len(report.run_fingerprint), 64)

            passing = next(result for result in report.instance_results if result.instance_id == "executor__calculator-001")
            failing = next(result for result in report.instance_results if result.instance_id == "executor__parser-002")

            self.assertTrue(passing.tests_passed)
            self.assertEqual(passing.test_exit_code, 0)
            self.assertFalse(failing.tests_passed)
            self.assertNotEqual(failing.test_exit_code, 0)
            self.assertTrue(failing.success)
            self.assertEqual(failing.warnings, [])

            for result in report.instance_results:
                self.assertTrue(result.applied_test_patch)
                self.assertTrue(result.applied_candidate_patch)
                self.assertTrue(result.hydration_safe)
                self.assertTrue(Path(result.repo_workspace_ref).exists())
                for artifact_uri in result.artifact_uris:
                    self.assertTrue(Path(artifact_uri).exists(), artifact_uri)

            execution_report = Path(failing.workspace_ref) / "artifacts" / "execution_report.json"
            payload = json.loads(execution_report.read_text(encoding="utf-8"))
            self.assertFalse(payload["tests_passed"])
            self.assertIn("behavioral_divergence_score", payload)
            self.assertIn("oracle_audit_fingerprint", payload)

            oracle_report = Path(passing.workspace_ref) / "artifacts" / "oracle_audit_report.json"
            oracle_payload = json.loads(oracle_report.read_text(encoding="utf-8"))
            self.assertTrue(oracle_payload["sound"])
            self.assertEqual(len(oracle_payload["oracle_fingerprint"]), 64)
            self.assertIn("repo_workspace_fingerprint", oracle_payload["environment"])

    def test_official_subset_bridge_prepares_predictions_manifest_and_harness_command(self):
        matching_patch = _patch("pkg/calc.py", "return a - b", "return a + b")
        divergent_gold = _patch("pkg/parser.py", "return token == expected", "return token.strip() == expected")
        divergent_candidate = _patch("pkg/parser.py", "return token == expected", "return token.lower() == expected")
        records = [
            {
                "instance_id": "verified__calc-001",
                "repo": "demo/calc",
                "base_commit": "abc123",
                "problem_statement": "add subtracts the second argument",
                "patch": matching_patch,
                "test_patch": _patch("tests/test_calc.py", "pass", "assert add(1, 2) == 3"),
                "FAIL_TO_PASS": ["tests/test_calc.py::test_add"],
                "source_refs": ["https://openai.com/index/introducing-swe-bench-verified/"],
            },
            {
                "instance_id": "verified__parser-002",
                "repo": "demo/parser",
                "base_commit": "def456",
                "problem_statement": "parser should strip whitespace",
                "patch": divergent_gold,
                "test_patch": _patch("tests/test_parser.py", "pass", "assert parse(' ok ') == 'ok'"),
                "FAIL_TO_PASS": ["tests/test_parser.py::test_strip"],
                "source_refs": ["https://labs.scale.com/leaderboard/swe_bench_pro_public"],
            },
        ]
        predictions = [
            {
                "instance_id": "verified__calc-001",
                "model_name_or_path": "hermes-demo-agent",
                "model_patch": matching_patch,
            },
            {
                "instance_id": "verified__parser-002",
                "model_name_or_path": "hermes-demo-agent",
                "model_patch": divergent_candidate,
            },
        ]

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instances_path = root / "instances.jsonl"
            predictions_path = root / "predictions.jsonl"
            instances_path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in records), encoding="utf-8")
            predictions_path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in predictions), encoding="utf-8")

            bridge = SweBenchOfficialSubsetBridge.from_jsonl(
                instances_path,
                predictions_path=predictions_path,
                dataset_name="SWE-bench/SWE-bench_Verified",
            )
            report = bridge.run(root / "official")

            self.assertTrue(report.ready_for_official_subset)
            self.assertEqual(report.failures, [])
            self.assertEqual(report.instance_count, 2)
            self.assertEqual(report.prediction_count, 2)
            self.assertEqual(report.matched_prediction_count, 2)
            self.assertEqual(report.oracle_audit_sound_count, 2)
            self.assertEqual(report.official_harness_ready_count, 2)
            self.assertIn("swebench.harness.run_evaluation", report.official_harness_command)
            self.assertIn("--predictions_path", report.official_harness_command)
            self.assertTrue(Path(report.subset_manifest_ref).exists())
            self.assertTrue(Path(report.predictions_ref).exists())
            self.assertGreaterEqual(report.artifact_count, 10)
            self.assertEqual(len(report.run_fingerprint), 64)

            manifest = json.loads(Path(report.subset_manifest_ref).read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_name"], "SWE-bench/SWE-bench_Verified")
            self.assertEqual(len(manifest["items"]), 2)
            self.assertIn("official_harness_command", manifest)

    def test_official_subset_bridge_blocks_missing_prediction(self):
        instance = SweBenchInstance(
            instance_id="verified__missing-prediction",
            repo="demo/repo",
            base_commit="abc123",
            problem_statement="missing prediction",
            patch=_patch("pkg/mod.py", "return False", "return True"),
            test_patch=_patch("tests/test_mod.py", "pass", "assert mod()"),
            fail_to_pass=["tests/test_mod.py::test_mod"],
            source_refs=["https://www.swebench.com/swebench-verified.html"],
        )

        with TemporaryDirectory() as temp_dir:
            report = SweBenchOfficialSubsetBridge([instance], []).run(temp_dir)

            self.assertFalse(report.ready_for_official_subset)
            self.assertEqual(report.instance_count, 1)
            self.assertEqual(report.matched_prediction_count, 0)
            self.assertIn(
                "verified__missing-prediction: missing prediction model_patch for official harness",
                report.failures,
            )

    def test_official_execution_ingestor_retains_results_evidence_and_hydration(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bridge_report = SweBenchOfficialSubsetBridge.demo().run(root / "official_subset")
            evaluation_root = SweBenchOfficialExecutionIngestor.demo_evaluation_results(
                bridge_report,
                root / "evaluation_results" / "demo-run",
            )

            ingest_report = SweBenchOfficialExecutionIngestor(
                subset_manifest_path=bridge_report.subset_manifest_ref,
                evaluation_results_path=evaluation_root,
            ).run(root / "ingest")

            self.assertTrue(ingest_report.ready_for_official_execution_ingest)
            self.assertEqual(ingest_report.failures, [])
            self.assertEqual(ingest_report.instance_count, 2)
            self.assertEqual(ingest_report.evaluation_found_count, 2)
            self.assertEqual(ingest_report.completed_count, 2)
            self.assertEqual(ingest_report.resolved_count, 1)
            self.assertEqual(ingest_report.resolution_rate, 0.5)
            self.assertTrue(ingest_report.evidence_ledger_sound)
            self.assertEqual(ingest_report.hydration_safe_count, 2)
            self.assertGreaterEqual(ingest_report.artifact_count, 8)
            self.assertEqual(len(ingest_report.run_fingerprint), 64)
            self.assertTrue(Path(ingest_report.ingest_report_ref).exists())
            self.assertTrue(Path(ingest_report.evidence_ledger_ref).exists())
            self.assertTrue(Path(ingest_report.hydration_manifest_ref).exists())
            self.assertTrue(Path(ingest_report.hydration_report_ref).exists())

            for result in ingest_report.item_results:
                self.assertTrue(result.evaluation_found)
                self.assertTrue(result.completed)
                self.assertTrue(Path(result.execution_receipt_ref).exists())

            hydration_payload = json.loads(Path(ingest_report.hydration_report_ref).read_text(encoding="utf-8"))
            self.assertTrue(hydration_payload["safe_to_hydrate"])
            self.assertIn("evidence", hydration_payload["retained_surfaces"])
            evidence_payload = json.loads(Path(ingest_report.evidence_ledger_ref).read_text(encoding="utf-8"))
            self.assertEqual(len(evidence_payload["claims"]), 1)


if __name__ == "__main__":
    unittest.main()
