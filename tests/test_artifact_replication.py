from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research import ArtifactReplicationPackageIngestor


class ArtifactReplicationPackageIngestorTests(unittest.TestCase):
    def test_manifest_driven_artifact_package_runs_and_retains_hydration_evidence(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "paper_artifact"
            package.mkdir()
            (package / "README.md").write_text("Demo paper artifact.\n", encoding="utf-8")
            (package / "run_replication.py").write_text(
                "from pathlib import Path\n"
                "import json\n"
                "Path('results').mkdir(exist_ok=True)\n"
                "Path('results/metrics.json').write_text(json.dumps({'accuracy': 0.91, 'replicated': True}, sort_keys=True))\n"
                "print('replicated accuracy=0.91')\n",
                encoding="utf-8",
            )
            manifest = root / "artifact_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "package_id": "real_artifact_demo",
                        "paper_title": "Demo FSE Artifact Package",
                        "artifact_root": str(package),
                        "run_command": [sys.executable, "run_replication.py"],
                        "expected_artifacts": ["results/metrics.json"],
                        "expected_metric_files": ["results/metrics.json"],
                        "source_refs": ["https://example.org/demo-fse-artifact"],
                        "timeout_s": 10,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            report = ArtifactReplicationPackageIngestor.from_manifest_paths([manifest]).run(root / "runs")

            self.assertTrue(report.ready_for_real_artifact_replication)
            self.assertEqual(report.failures, [])
            self.assertEqual(report.package_count, 1)
            self.assertEqual(report.success_count, 1)
            self.assertEqual(report.command_completed_count, 1)
            self.assertEqual(report.hydration_safe_count, 1)
            self.assertEqual(report.evidence_sound_count, 1)
            self.assertEqual(report.phase_gate_passed_count, 1)
            self.assertEqual(report.metric_file_count, 1)
            self.assertEqual(len(report.run_fingerprint), 64)
            result = report.package_results[0]
            self.assertTrue(result.success)
            self.assertEqual(result.command_exit_code, 0)
            self.assertEqual(result.expected_artifact_found_count, 1)
            self.assertEqual(result.missing_expected_artifacts, [])
            self.assertTrue(result.hydration_safe)
            self.assertTrue(result.evidence_ledger_sound)
            self.assertTrue(result.phase_gate_passed)
            for artifact_uri in result.artifact_uris:
                path = Path(artifact_uri)
                if path.suffix:
                    self.assertTrue(path.exists(), artifact_uri)

    def test_empty_report_keeps_submission_gate_honest_when_no_manifest_is_supplied(self):
        report = ArtifactReplicationPackageIngestor([]).run("unused")

        self.assertFalse(report.ready_for_real_artifact_replication)
        self.assertEqual(report.package_count, 0)
        self.assertIn("no real artifact replication manifest supplied", report.warnings)


if __name__ == "__main__":
    unittest.main()
