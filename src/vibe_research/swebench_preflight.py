from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _get(report: Any, name: str, default: Any = None) -> Any:
    if isinstance(report, dict):
        return report.get(name, default)
    return getattr(report, name, default)


@dataclass(frozen=True, slots=True)
class SweBenchOfficialDockerPreflightReport:
    ready_for_swebench_official_docker_run: bool
    docker_available: bool
    docker_version: str | None
    swebench_module_available: bool
    predictions_path_exists: bool
    subset_manifest_path_exists: bool
    official_harness_command_present: bool
    official_harness_command: str
    predictions_ref: str
    subset_manifest_ref: str
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommended_next_steps: list[str] = field(default_factory=list)
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


class SweBenchOfficialDockerPreflight:
    """Checks whether the local environment can run the official SWE-bench harness."""

    def run(self, official_subset_report: Any) -> SweBenchOfficialDockerPreflightReport:
        command = str(_get(official_subset_report, "official_harness_command", "") or "")
        predictions_ref = str(_get(official_subset_report, "predictions_ref", "") or "")
        subset_manifest_ref = str(_get(official_subset_report, "subset_manifest_ref", "") or "")
        docker_path = shutil.which("docker")
        docker_available = docker_path is not None
        docker_version = self._docker_version() if docker_available else None
        swebench_module_available = importlib.util.find_spec("swebench") is not None
        predictions_path_exists = bool(predictions_ref and Path(predictions_ref).exists())
        subset_manifest_path_exists = bool(subset_manifest_ref and Path(subset_manifest_ref).exists())
        official_harness_command_present = bool(command.strip())

        failures: list[str] = []
        if not docker_available:
            failures.append("docker command is not available; official SWE-bench evaluation cannot run locally")
        if not swebench_module_available:
            failures.append("Python module 'swebench' is not installed")
        if not predictions_path_exists:
            failures.append(f"predictions JSONL is missing: {predictions_ref or '<empty>'}")
        if not subset_manifest_path_exists:
            failures.append(f"official subset manifest is missing: {subset_manifest_ref or '<empty>'}")
        if not official_harness_command_present:
            failures.append("official SWE-bench harness command is missing")

        recommended_next_steps = [
            "Install Docker and verify `docker --version` works.",
            "Install the official SWE-bench package in an isolated environment.",
            "Run the generated official_harness_command.txt for 5-10 SWE-bench Verified instances.",
            "Feed the resulting results.json / instance_results.jsonl / run_logs back into SweBenchOfficialExecutionIngestor.",
        ]
        report = SweBenchOfficialDockerPreflightReport(
            ready_for_swebench_official_docker_run=not failures,
            docker_available=docker_available,
            docker_version=docker_version,
            swebench_module_available=swebench_module_available,
            predictions_path_exists=predictions_path_exists,
            subset_manifest_path_exists=subset_manifest_path_exists,
            official_harness_command_present=official_harness_command_present,
            official_harness_command=command,
            predictions_ref=predictions_ref,
            subset_manifest_ref=subset_manifest_ref,
            failures=failures,
            warnings=[],
            recommended_next_steps=recommended_next_steps,
        )
        return SweBenchOfficialDockerPreflightReport(
            **{
                **report.to_dict(),
                "report_fingerprint": report.fingerprint(),
            }
        )

    @staticmethod
    def _docker_version() -> str | None:
        completed = subprocess.run(
            ["docker", "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            return None
        return completed.stdout.strip() or None
