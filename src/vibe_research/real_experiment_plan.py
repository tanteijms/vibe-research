from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _get(report: Any, name: str, default: Any = None) -> Any:
    if isinstance(report, dict):
        return report.get(name, default)
    return getattr(report, name, default)


@dataclass(frozen=True, slots=True)
class FseRealExperimentCommand:
    command_id: str
    purpose: str
    command: str
    expected_outputs: list[str]
    ready_to_run: bool
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FseRealAblationVariant:
    variant_id: str
    disabled_modules: list[str]
    target_claim: str
    key_metrics: list[str]
    applies_to_task_slices: list[str]
    expected_regression: str

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FseRealExperimentSlicePlan:
    plan_id: str
    ready_to_collect_submission_empirics: bool
    ready_to_run_official_swebench: bool
    ready_to_run_real_artifact_replication: bool
    same_task_ablation_variant_count: int
    missing_dependencies: list[str]
    commands: list[FseRealExperimentCommand]
    ablation_variants: list[FseRealAblationVariant]
    recommended_execution_order: list[str]
    source_refs: list[str] = field(default_factory=list)
    plan_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        data["commands"] = [
            command.to_dict() if hasattr(command, "to_dict") else dict(command)
            for command in self.commands
        ]
        data["ablation_variants"] = [
            variant.to_dict() if hasattr(variant, "to_dict") else dict(variant)
            for variant in self.ablation_variants
        ]
        if not data["plan_fingerprint"]:
            data["plan_fingerprint"] = self.fingerprint()
        return data

    def fingerprint(self) -> str:
        data = asdict(self)
        data["plan_fingerprint"] = ""
        return _stable_hash(data)


class FseRealExperimentSlicePlanner:
    """Builds a concrete next-experiment plan from the current artifact reports."""

    def __init__(self, *, source_refs: list[str] | None = None):
        self.source_refs = list(source_refs or [])

    def plan(
        self,
        *,
        output_dir: str | Path,
        official_subset_report: Any,
        official_docker_preflight_report: Any,
        real_artifact_report: Any,
        real_artifact_manifest_template: str | Path,
    ) -> FseRealExperimentSlicePlan:
        output = Path(output_dir)
        template_ref = str(Path(real_artifact_manifest_template))
        ready_official = bool(_get(official_docker_preflight_report, "ready_for_swebench_official_docker_run", False))
        ready_artifact = bool(_get(real_artifact_report, "ready_for_real_artifact_replication", False))
        official_command = str(_get(official_subset_report, "official_harness_command", "") or "")
        official_blockers = list(_get(official_docker_preflight_report, "failures", []) or [])
        artifact_blockers = list(_get(real_artifact_report, "warnings", []) or []) + list(
            _get(real_artifact_report, "failures", []) or []
        )

        commands = [
            FseRealExperimentCommand(
                command_id="preflight_official_swebench",
                purpose="Check whether the local environment can run the official SWE-bench Docker harness.",
                command=(
                    "python scripts/preflight_swebench_official.py "
                    f"--official-subset-report {output / 'reports' / 'swebench_official_subset_report.json'}"
                ),
                expected_outputs=[
                    str(output / "reports" / "swebench_official_docker_preflight_report.json"),
                ],
                ready_to_run=True,
            ),
            FseRealExperimentCommand(
                command_id="run_official_swebench",
                purpose="Run 5-10 SWE-bench Verified instances through the official Docker harness.",
                command=official_command or "<missing official_harness_command>",
                expected_outputs=["results.json", "instance_results.jsonl", "run_logs/"],
                ready_to_run=ready_official,
                blockers=official_blockers,
            ),
            FseRealExperimentCommand(
                command_id="ingest_official_swebench_results",
                purpose="Ingest official SWE-bench Docker outputs into evidence, hydration, and replay contracts.",
                command=(
                    "python scripts/run_fse_local_benchmark.py "
                    f"--output-dir {output} "
                    "--swebench-official-evaluation-dir /path/to/official/evaluation_results"
                ),
                expected_outputs=[
                    str(output / "reports" / "swebench_official_execution_ingest_report.json"),
                    str(output / "reports" / "top_conference_alignment_report.json"),
                ],
                ready_to_run=ready_official,
                blockers=official_blockers,
            ),
            FseRealExperimentCommand(
                command_id="run_real_artifact_replication",
                purpose="Run one real paper artifact package through the artifact-replication ingestor.",
                command=(
                    "python scripts/run_fse_local_benchmark.py "
                    f"--output-dir {output} "
                    f"--real-artifact-manifest {template_ref}"
                ),
                expected_outputs=[
                    str(output / "reports" / "real_artifact_replication_report.json"),
                    str(output / "reports" / "top_conference_alignment_report.json"),
                ],
                ready_to_run=ready_artifact,
                blockers=artifact_blockers
                or [
                    "replace the manifest template with a real artifact_root, run_command, expected_artifacts, and source_refs"
                ],
            ),
        ]
        variants = self._ablation_variants()
        missing_dependencies = []
        if not ready_official:
            missing_dependencies.extend(official_blockers or ["official SWE-bench Docker preflight is not ready"])
        if not ready_artifact:
            missing_dependencies.extend(artifact_blockers or ["real artifact replication manifest has not been supplied"])
        report = FseRealExperimentSlicePlan(
            plan_id="fse-2027-real-experiment-slice-plan",
            ready_to_collect_submission_empirics=ready_official and ready_artifact,
            ready_to_run_official_swebench=ready_official,
            ready_to_run_real_artifact_replication=ready_artifact,
            same_task_ablation_variant_count=len(variants),
            missing_dependencies=list(dict.fromkeys(str(item) for item in missing_dependencies)),
            commands=commands,
            ablation_variants=variants,
            recommended_execution_order=[
                "preflight_official_swebench",
                "run_official_swebench",
                "ingest_official_swebench_results",
                "run_real_artifact_replication",
                "rerun same-task ablations on the exact same official/artifact slices",
            ],
            source_refs=self.source_refs,
        )
        return replace(report, plan_fingerprint=report.fingerprint())

    @staticmethod
    def _ablation_variants() -> list[FseRealAblationVariant]:
        return [
            FseRealAblationVariant(
                variant_id="hermes_full",
                disabled_modules=[],
                target_claim="Full Harness x Hermes runtime support.",
                key_metrics=[
                    "resume_success_rate",
                    "invalid_memory_commit_rate",
                    "claim_preserving_replay_fidelity",
                    "artifact_provenance_completeness",
                ],
                applies_to_task_slices=["swebench_verified_official", "real_artifact_replication"],
                expected_regression="none; this is the reference condition.",
            ),
            FseRealAblationVariant(
                variant_id="no_hydration_manifest",
                disabled_modules=["HydrationManifest", "CompactionVerifier"],
                target_claim="Hydratable Scene / Context Lifecycle Contract.",
                key_metrics=["resume_success_rate", "state_reconstruction_accuracy", "context_pin_recall"],
                applies_to_task_slices=["swebench_verified_official", "real_artifact_replication"],
                expected_regression="resume correctness and active-frame retention should drop under interruption or compaction.",
            ),
            FseRealAblationVariant(
                variant_id="no_memory_commit",
                disabled_modules=["MemoryCommitProtocol", "DecisionMemoryProjection"],
                target_claim="Evidence-Governed Memory and Data-Quality Commit.",
                key_metrics=["invalid_memory_commit_rate", "unsupported_claim_rate", "memory_interference_block_rate"],
                applies_to_task_slices=["swebench_verified_official", "real_artifact_replication"],
                expected_regression="unsupported or stale memory should more often reach writeup/action decisions.",
            ),
            FseRealAblationVariant(
                variant_id="no_trace_receipt",
                disabled_modules=["TraceEnvelope.evidence_ledger_fingerprint", "TraceEnvelope.evidence_claim_ids"],
                target_claim="Evidence-Retaining Replay Diagnosis.",
                key_metrics=[
                    "claim_preserving_replay_fidelity",
                    "evidence_receipt_drift_detection_rate",
                    "fault_localization_mrr",
                ],
                applies_to_task_slices=["swebench_verified_official", "real_artifact_replication"],
                expected_regression="replay should become less sensitive to evidence/oracle drift.",
            ),
        ]
