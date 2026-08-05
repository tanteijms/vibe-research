from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research import FseLocalToyTaskRunner, FseTaskFamily


class FseLocalToyTaskRunnerTests(unittest.TestCase):
    def test_local_toy_runner_executes_three_fse_task_families(self):
        with TemporaryDirectory() as temp_dir:
            report = FseLocalToyTaskRunner().run(temp_dir)

            self.assertTrue(report.ready_for_local_runner)
            self.assertEqual(report.failures, [])
            self.assertEqual(report.task_count, 3)
            self.assertEqual(report.success_count, 3)
            self.assertEqual(report.hydration_safe_count, 3)
            self.assertEqual(report.phase_gate_passed_count, 3)
            self.assertGreaterEqual(report.evidence_claim_count, 3)
            self.assertGreaterEqual(report.committed_memory_count, 3)
            self.assertGreaterEqual(report.artifact_count, 9)
            self.assertEqual(len(report.run_fingerprint), 64)
            self.assertEqual(
                {result.task_family for result in report.task_results},
                {
                    FseTaskFamily.ISSUE_TO_PATCH,
                    FseTaskFamily.ARTIFACT_REPLICATION,
                    FseTaskFamily.INCIDENT_RCA,
                },
            )
            for result in report.task_results:
                self.assertTrue(result.success)
                self.assertTrue(result.hydration_safe)
                self.assertTrue(result.phase_gate_passed)
                self.assertGreater(result.trace_event_count, 0)
                for artifact_uri in result.artifact_uris:
                    self.assertTrue(Path(artifact_uri).exists())


if __name__ == "__main__":
    unittest.main()
