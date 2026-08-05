from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any

from .evidence_ledger import EvidenceClaim, EvidenceEntry, EvidenceKind, EvidenceLedger
from .hydration_manifest import HydrationManifestBuilder
from .memory_commit import MemoryCommitProtocol, MemoryKind, ValidationReceipt
from .research_session import ResearchPhase, ResearchPhaseGate, ResearchSession, ResearchSessionVerifier
from .schema import ArtifactRef, RuntimeState, TraceEvent
from .trace_contract import TraceBoundary, hash_payload


JsonDict = dict[str, Any]


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _directory_fingerprint(path: Path) -> str:
    """Hash a small local repo tree for executable benchmark provenance."""
    entries: list[dict[str, str]] = []
    if not path.exists():
        return ""
    for file_path in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        if any(part in {".git", "__pycache__", ".pytest_cache"} for part in file_path.parts):
            continue
        entries.append(
            {
                "path": file_path.relative_to(path).as_posix(),
                "sha256": _sha256_path(file_path),
            }
        )
    return _stable_hash(entries)


def _write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return _sha256_path(path)


def _write_json(path: Path, payload: object) -> str:
    return _write_text(path, json.dumps(payload, indent=2, sort_keys=True, default=str))


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple | set):
        return [str(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return [stripped]
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        return [stripped]
    return [str(value)]


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe[:120] or "swebench_instance"


def _normalize_patch(patch: str) -> str:
    lines = []
    for raw_line in patch.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip()
        if line.startswith("index ") or line.startswith("similarity index "):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _patch_line_set(patch: str) -> set[str]:
    ignored_prefixes = ("index ", "diff --git ", "--- ", "+++ ", "@@")
    return {
        line.strip()
        for line in _normalize_patch(patch).split("\n")
        if line.strip() and not line.startswith(ignored_prefixes)
    }


def _changed_files(patch: str) -> set[str]:
    files: set[str] = set()
    for line in patch.replace("\r\n", "\n").split("\n"):
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                files.add(parts[3].removeprefix("b/"))
            continue
        if line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
            files.add(line.split(maxsplit=1)[1].removeprefix("b/"))
    return {path for path in files if path and path != "/dev/null"}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left.intersection(right)) / len(left.union(right))


@dataclass(frozen=True, slots=True)
class SweBenchInstance:
    """A minimal SWE-bench-style issue-to-patch instance.

    The adapter intentionally accepts a superset of common SWE-bench fields so
    that local smoke fixtures, official JSONL exports, and future model
    prediction files can share the same pipeline.
    """

    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    patch: str
    test_patch: str = ""
    version: str | None = None
    fail_to_pass: list[str] = field(default_factory=list)
    pass_to_pass: list[str] = field(default_factory=list)
    candidate_patch: str | None = None
    source_refs: list[str] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: JsonDict) -> "SweBenchInstance":
        return cls(
            instance_id=str(data.get("instance_id") or data.get("id") or ""),
            repo=str(data.get("repo") or ""),
            base_commit=str(data.get("base_commit") or ""),
            problem_statement=str(data.get("problem_statement") or data.get("problem") or ""),
            patch=str(data.get("patch") or ""),
            test_patch=str(data.get("test_patch") or ""),
            version=str(data["version"]) if data.get("version") is not None else None,
            fail_to_pass=_as_list(data.get("FAIL_TO_PASS") or data.get("fail_to_pass")),
            pass_to_pass=_as_list(data.get("PASS_TO_PASS") or data.get("pass_to_pass")),
            candidate_patch=(
                str(data.get("candidate_patch") or data.get("model_patch") or data.get("prediction"))
                if data.get("candidate_patch") or data.get("model_patch") or data.get("prediction")
                else None
            ),
            source_refs=_as_list(data.get("source_refs")),
            metadata={
                key: value
                for key, value in data.items()
                if key
                not in {
                    "instance_id",
                    "id",
                    "repo",
                    "base_commit",
                    "problem_statement",
                    "problem",
                    "patch",
                    "test_patch",
                    "version",
                    "FAIL_TO_PASS",
                    "fail_to_pass",
                    "PASS_TO_PASS",
                    "pass_to_pass",
                    "candidate_patch",
                    "model_patch",
                    "prediction",
                    "source_refs",
                }
            },
        )

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SweBenchInstanceResult:
    instance_id: str
    repo: str
    success: bool
    workspace_ref: str
    artifact_uris: list[str]
    evidence_claim_ids: list[str]
    committed_memory_record_ids: list[str]
    patch_equal_to_gold: bool
    changed_file_overlap: float
    patch_line_jaccard: float
    behavioral_divergence_score: float
    test_patch_present: bool
    oracle_audit_sound: bool
    evidence_ledger_sound: bool
    phase_gate_passed: bool
    hydration_safe: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    result_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SweBenchAdapterRunReport:
    ready_for_swebench_adapter: bool
    instance_count: int
    success_count: int
    hydration_safe_count: int
    evidence_sound_count: int
    phase_gate_passed_count: int
    candidate_patch_equal_count: int
    test_patch_present_count: int
    oracle_audit_sound_count: int
    artifact_count: int
    mean_patch_line_jaccard: float
    mean_behavioral_divergence_score: float
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    run_fingerprint: str = ""
    instance_results: list[SweBenchInstanceResult] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        data["instance_results"] = [result.to_dict() for result in self.instance_results]
        return data


@dataclass(frozen=True, slots=True)
class SweBenchOracleAuditReport:
    """Provenance and oracle contract for SWE-bench-style evaluation.

    This is intentionally independent from any particular Docker harness. The
    report pins the issue identity, gold/test oracle, candidate patch, test
    lists, and optional executable environment metadata so benchmark drift can
    be detected by artifact review.
    """

    sound: bool
    oracle_fingerprint: str
    instance_id: str
    repo: str
    base_commit: str
    problem_statement_sha256: str
    gold_patch_sha256: str
    candidate_patch_sha256: str
    test_patch_sha256: str
    fail_to_pass_sha256: str
    pass_to_pass_sha256: str
    source_refs: list[str]
    environment: JsonDict = field(default_factory=dict)
    contamination_flags: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SweBenchPrediction:
    """Prediction record accepted by the official SWE-bench harness."""

    instance_id: str
    model_name_or_path: str
    model_patch: str
    metadata: JsonDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: JsonDict) -> "SweBenchPrediction":
        return cls(
            instance_id=str(data.get("instance_id") or ""),
            model_name_or_path=str(data.get("model_name_or_path") or data.get("model") or "unknown-model"),
            model_patch=str(data.get("model_patch") or data.get("prediction") or data.get("candidate_patch") or ""),
            metadata={
                key: value
                for key, value in data.items()
                if key not in {"instance_id", "model_name_or_path", "model", "model_patch", "prediction", "candidate_patch"}
            },
        )

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SweBenchOfficialSubsetItemResult:
    instance_id: str
    repo: str
    base_commit: str
    has_prediction: bool
    prediction_model: str
    oracle_audit_sound: bool
    oracle_fingerprint: str
    official_harness_ready: bool
    local_executor_ready: bool
    artifact_uris: list[str]
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SweBenchOfficialSubsetReport:
    ready_for_official_subset: bool
    dataset_name: str
    instance_count: int
    prediction_count: int
    matched_prediction_count: int
    oracle_audit_sound_count: int
    official_harness_ready_count: int
    local_executor_ready_count: int
    artifact_count: int
    official_harness_command: str
    subset_manifest_ref: str
    predictions_ref: str
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    run_fingerprint: str = ""
    item_results: list[SweBenchOfficialSubsetItemResult] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        data["item_results"] = [result.to_dict() for result in self.item_results]
        return data


@dataclass(frozen=True, slots=True)
class SweBenchOfficialExecutionItemResult:
    """Per-instance receipt after ingesting an official SWE-bench harness result."""

    instance_id: str
    repo: str
    base_commit: str
    evaluation_found: bool
    completed: bool
    resolved: bool
    patch_applied: bool | None
    tests_passed: bool | None
    oracle_fingerprint: str
    execution_receipt_ref: str
    artifact_uris: list[str]
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    result_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SweBenchOfficialExecutionIngestReport:
    """Artifact contract for retaining official SWE-bench Docker harness outputs."""

    ready_for_official_execution_ingest: bool
    dataset_name: str
    run_id: str
    instance_count: int
    evaluation_found_count: int
    completed_count: int
    resolved_count: int
    resolution_rate: float
    evidence_ledger_sound: bool
    hydration_safe_count: int
    artifact_count: int
    official_results_ref: str
    official_instance_results_ref: str | None
    official_run_logs_ref: str | None
    ingest_report_ref: str
    evidence_ledger_ref: str
    hydration_manifest_ref: str
    hydration_report_ref: str
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    run_fingerprint: str = ""
    item_results: list[SweBenchOfficialExecutionItemResult] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        data["item_results"] = [result.to_dict() for result in self.item_results]
        return data


class SweBenchOfficialExecutionIngestor:
    """Ingests official SWE-bench harness outputs into the Hermes evidence contract.

    This class intentionally does not run Docker. It starts after the official
    `swebench.harness.run_evaluation` command has produced `results.json`,
    optional `instance_results.jsonl`, and logs. The goal is to make those
    outputs replay/audit-ready for FSE artifact review instead of leaving them
    as ad hoc benchmark files.
    """

    RESULT_FILENAME_CANDIDATES = ["results.json", "evaluation_results.json"]
    INSTANCE_RESULT_FILENAME_CANDIDATES = ["instance_results.jsonl", "instances_results.jsonl"]

    def __init__(
        self,
        *,
        subset_manifest_path: str | Path,
        evaluation_results_path: str | Path,
        instance_results_path: str | Path | None = None,
        run_logs_path: str | Path | None = None,
    ):
        self.subset_manifest_path = Path(subset_manifest_path)
        self.evaluation_results_path = Path(evaluation_results_path)
        self.instance_results_path = Path(instance_results_path) if instance_results_path else None
        self.run_logs_path = Path(run_logs_path) if run_logs_path else None

    @classmethod
    def demo_evaluation_results(
        cls,
        official_subset_report: SweBenchOfficialSubsetReport,
        output_dir: str | Path,
        *,
        resolved_instance_ids: list[str] | None = None,
    ) -> Path:
        """Writes a tiny official-shaped result directory for ingest smoke tests.

        The generated directory mirrors the official file contract but is marked
        as a demo artifact. It should not be reported as real SWE-bench Docker
        execution in a paper.
        """

        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        resolved = set(resolved_instance_ids or [official_subset_report.item_results[0].instance_id])
        submitted_ids = [item.instance_id for item in official_subset_report.item_results]
        unresolved_ids = [instance_id for instance_id in submitted_ids if instance_id not in resolved]
        instance_results = [
            {
                "instance_id": item.instance_id,
                "resolved": item.instance_id in resolved,
                "completed": True,
                "patch_successfully_applied": True,
                "tests_passed": item.instance_id in resolved,
                "oracle_fingerprint": item.oracle_fingerprint,
                "demo": True,
            }
            for item in official_subset_report.item_results
        ]
        results = {
            "run_id": "demo-official-execution-ingest",
            "dataset_name": official_subset_report.dataset_name,
            "submitted_instances": submitted_ids,
            "completed_instances": submitted_ids,
            "resolved_instances": sorted(resolved),
            "unresolved_instances": unresolved_ids,
            "total_instances": len(submitted_ids),
            "instances_submitted": len(submitted_ids),
            "instances_completed": len(submitted_ids),
            "instances_resolved": len(resolved),
            "resolution_rate": round(len(resolved) / len(submitted_ids), 4) if submitted_ids else 0.0,
            "demo": True,
        }
        _write_json(root / "results.json", results)
        cls._write_jsonl(root / "instance_results.jsonl", instance_results)
        (root / "run_logs").mkdir(exist_ok=True)
        _write_text(
            root / "run_logs" / "README.txt",
            "Demo official-shaped SWE-bench execution output for ingest-contract smoke tests.\n",
        )
        return root

    def run(self, output_dir: str | Path) -> SweBenchOfficialExecutionIngestReport:
        output_root = Path(output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        subset_manifest = self._read_json(self.subset_manifest_path)
        results_path, instance_results_path, run_logs_path = self._resolve_official_paths()
        results_payload = self._read_json(results_path)
        instance_payloads = self._read_instance_results(instance_results_path)
        instance_payloads_by_id = {
            str(payload.get("instance_id") or payload.get("id") or ""): payload
            for payload in instance_payloads
            if payload.get("instance_id") or payload.get("id")
        }
        manifest_items = list(subset_manifest.get("items") or [])
        dataset_name = str(results_payload.get("dataset_name") or subset_manifest.get("dataset_name") or "")
        run_id = str(results_payload.get("run_id") or subset_manifest.get("run_id") or "unknown-run")
        submitted_ids = self._ids_from_payload(
            results_payload,
            "submitted_instances",
            "submitted_ids",
            "submitted",
            "instances_submitted_ids",
        )
        completed_ids = self._ids_from_payload(
            results_payload,
            "completed_instances",
            "completed_ids",
            "completed",
            "instances_completed_ids",
        )
        resolved_ids = self._ids_from_payload(
            results_payload,
            "resolved_instances",
            "resolved_ids",
            "resolved",
            "instances_resolved_ids",
        )
        unresolved_ids = self._ids_from_payload(results_payload, "unresolved_instances", "unresolved_ids", "unresolved")

        evidence_entries = [
            EvidenceEntry(
                entry_id="official-subset-manifest",
                kind=EvidenceKind.ARTIFACT,
                source_ref=str(self.subset_manifest_path),
                content_hash=_sha256_path(self.subset_manifest_path),
                labels=["swebench_official_manifest"],
            ),
            EvidenceEntry(
                entry_id="official-results-json",
                kind=EvidenceKind.ARTIFACT,
                source_ref=str(results_path),
                content_hash=_sha256_path(results_path),
                labels=["swebench_official_results"],
            ),
        ]
        if instance_results_path is not None and instance_results_path.exists():
            evidence_entries.append(
                EvidenceEntry(
                    entry_id="official-instance-results-jsonl",
                    kind=EvidenceKind.ARTIFACT,
                    source_ref=str(instance_results_path),
                    content_hash=_sha256_path(instance_results_path),
                    labels=["swebench_official_instance_results"],
                )
            )
        if run_logs_path is not None and run_logs_path.exists():
            evidence_entries.append(
                EvidenceEntry(
                    entry_id="official-run-logs",
                    kind=EvidenceKind.ARTIFACT,
                    source_ref=str(run_logs_path),
                    content_hash=_directory_fingerprint(run_logs_path),
                    labels=["swebench_official_run_logs"],
                )
            )

        item_results: list[SweBenchOfficialExecutionItemResult] = []
        failures: list[str] = []
        warnings: list[str] = []
        for item in manifest_items:
            item_result = self._ingest_item(
                output_root,
                item,
                instance_payloads_by_id.get(str(item.get("instance_id") or "")),
                submitted_ids=submitted_ids,
                completed_ids=completed_ids,
                resolved_ids=resolved_ids,
                unresolved_ids=unresolved_ids,
                results_payload=results_payload,
            )
            item_results.append(item_result)
            failures.extend(item_result.failures)
            warnings.extend(item_result.warnings)
            evidence_entries.append(
                EvidenceEntry(
                    entry_id=f"official-execution-{_safe_name(item_result.instance_id)}",
                    kind=EvidenceKind.ARTIFACT,
                    source_ref=item_result.execution_receipt_ref,
                    content_hash=_sha256_path(Path(item_result.execution_receipt_ref)),
                    labels=["swebench_official_execution_receipt"],
                    parent_entry_ids=[
                        "official-subset-manifest",
                        "official-results-json",
                    ],
                )
            )

        claims = [
            EvidenceClaim(
                claim_id="claim-official-swebench-execution-retained",
                statement=(
                    "Official SWE-bench harness outputs are retained with subset manifest, "
                    "overall results, per-instance receipts, and optional run logs."
                ),
                cited_entry_ids=[
                    "official-subset-manifest",
                    "official-results-json",
                    *[f"official-execution-{_safe_name(result.instance_id)}" for result in item_results],
                ],
                required_labels=[
                    "swebench_official_manifest",
                    "swebench_official_results",
                    "swebench_official_execution_receipt",
                ],
            )
        ]
        evidence_ledger = EvidenceLedger(entries=evidence_entries, claims=claims)
        evidence_report = evidence_ledger.evaluate(required_claim_ids=["claim-official-swebench-execution-retained"])

        artifact_refs = [
            ArtifactRef(kind="swebench_official_subset_manifest", uri=str(self.subset_manifest_path)),
            ArtifactRef(kind="swebench_official_results", uri=str(results_path)),
            *(
                [ArtifactRef(kind="swebench_official_instance_results", uri=str(instance_results_path))]
                if instance_results_path is not None and instance_results_path.exists()
                else []
            ),
            *(
                [ArtifactRef(kind="swebench_official_run_logs", uri=str(run_logs_path))]
                if run_logs_path is not None and run_logs_path.exists()
                else []
            ),
            *[
                ArtifactRef(kind="swebench_official_execution_receipt", uri=result.execution_receipt_ref)
                for result in item_results
            ],
        ]
        state = RuntimeState(
            task_id=f"swebench_official_execution_{_safe_name(run_id)}",
            session_id=f"sess_{_stable_hash(str(self.subset_manifest_path))[:12]}",
            run_id=f"run_{_stable_hash(str(results_path))[:12]}",
            goal="Ingest official SWE-bench execution results into evidence-retaining replay contract.",
            execution_cursor="after:swebench_official_execution_ingest",
            active_step="swebench_official_execution_ingest",
            policy_snapshot={
                "surface": "official_swebench_execution_ingest",
                "requires": ["subset_manifest", "results_json", "per_instance_receipts"],
            },
            artifact_refs=artifact_refs,
            metadata={
                "dataset_name": dataset_name,
                "official_run_id": run_id,
                "source_refs": SweBenchOfficialSubsetBridge.SOURCE_REFS,
            },
        )
        events = [
            TraceEvent(
                event_id=f"event_{_safe_name(result.instance_id)}",
                task_id=state.task_id,
                run_id=state.run_id,
                cursor=state.execution_cursor,
                kind="swebench_official_execution_ingested",
                data={
                    "instance_id": result.instance_id,
                    "resolved": result.resolved,
                    "completed": result.completed,
                    "oracle_fingerprint": result.oracle_fingerprint,
                    "execution_receipt_ref": result.execution_receipt_ref,
                    "boundary": TraceBoundary.TOOL,
                },
            )
            for result in item_results
        ]
        manifest_builder = HydrationManifestBuilder()
        hydration_manifest = manifest_builder.dehydrate(
            state,
            events,
            evidence_ledger=evidence_ledger,
            required_evidence_claim_ids=["claim-official-swebench-execution-retained"],
            required_artifact_uris=[ref.uri for ref in artifact_refs],
            metadata={"ingest": "official_swebench_execution"},
        )
        hydration_report = manifest_builder.verify(
            hydration_manifest,
            state,
            events,
            evidence_ledger=evidence_ledger,
        )

        evidence_ledger_ref = output_root / "official_execution_evidence_ledger.json"
        hydration_manifest_ref = output_root / "official_execution_hydration_manifest.json"
        hydration_report_ref = output_root / "official_execution_hydration_report.json"
        ingest_report_ref = output_root / "official_execution_ingest_report.json"
        _write_json(evidence_ledger_ref, evidence_ledger.to_dict())
        _write_json(hydration_manifest_ref, hydration_manifest.to_dict())
        _write_json(hydration_report_ref, hydration_report.to_dict())

        failures.extend(evidence_report.failures)
        warnings.extend(evidence_report.warnings)
        failures.extend(hydration_report.failures)
        warnings.extend(hydration_report.warnings)
        evaluation_found_count = sum(1 for result in item_results if result.evaluation_found)
        completed_count = sum(1 for result in item_results if result.completed)
        resolved_count = sum(1 for result in item_results if result.resolved)
        resolution_rate = round(resolved_count / len(item_results), 4) if item_results else 0.0
        all_artifact_uris = [
            str(self.subset_manifest_path),
            str(results_path),
            *( [str(instance_results_path)] if instance_results_path is not None and instance_results_path.exists() else [] ),
            *( [str(run_logs_path)] if run_logs_path is not None and run_logs_path.exists() else [] ),
            str(evidence_ledger_ref),
            str(hydration_manifest_ref),
            str(hydration_report_ref),
            *[uri for result in item_results for uri in result.artifact_uris],
        ]
        report_payload = {
            "dataset_name": dataset_name,
            "run_id": run_id,
            "item_results": [result.to_dict() for result in item_results],
            "evidence_ledger_fingerprint": evidence_ledger.fingerprint(),
            "hydration_report_fingerprint": hydration_report.report_fingerprint,
            "official_results_sha256": _sha256_path(results_path),
        }
        ready = (
            bool(item_results)
            and not failures
            and evaluation_found_count == len(item_results)
            and evidence_report.sound
            and hydration_report.safe_to_hydrate
        )
        report = SweBenchOfficialExecutionIngestReport(
            ready_for_official_execution_ingest=ready,
            dataset_name=dataset_name,
            run_id=run_id,
            instance_count=len(item_results),
            evaluation_found_count=evaluation_found_count,
            completed_count=completed_count,
            resolved_count=resolved_count,
            resolution_rate=resolution_rate,
            evidence_ledger_sound=evidence_report.sound,
            hydration_safe_count=len(item_results) if hydration_report.safe_to_hydrate else 0,
            artifact_count=len(all_artifact_uris),
            official_results_ref=str(results_path),
            official_instance_results_ref=str(instance_results_path) if instance_results_path is not None else None,
            official_run_logs_ref=str(run_logs_path) if run_logs_path is not None else None,
            ingest_report_ref=str(ingest_report_ref),
            evidence_ledger_ref=str(evidence_ledger_ref),
            hydration_manifest_ref=str(hydration_manifest_ref),
            hydration_report_ref=str(hydration_report_ref),
            failures=failures,
            warnings=warnings,
            run_fingerprint=_stable_hash(report_payload),
            item_results=item_results,
        )
        _write_json(ingest_report_ref, report.to_dict())
        return report

    def _ingest_item(
        self,
        output_root: Path,
        item: JsonDict,
        instance_payload: JsonDict | None,
        *,
        submitted_ids: set[str],
        completed_ids: set[str],
        resolved_ids: set[str],
        unresolved_ids: set[str],
        results_payload: JsonDict,
    ) -> SweBenchOfficialExecutionItemResult:
        instance_id = str(item.get("instance_id") or "")
        failures: list[str] = []
        warnings: list[str] = []
        evaluation_found = bool(instance_payload) or instance_id in submitted_ids or instance_id in completed_ids or instance_id in resolved_ids or instance_id in unresolved_ids
        if not evaluation_found:
            failures.append(f"{instance_id}: missing official evaluation result")
        resolved = self._bool_from_payload(instance_payload, "resolved", "tests_passed")
        if resolved is None:
            resolved = instance_id in resolved_ids
        completed = self._bool_from_payload(instance_payload, "completed", "evaluation_completed")
        if completed is None:
            completed = instance_id in completed_ids or instance_id in resolved_ids or instance_id in unresolved_ids
        patch_applied = self._bool_from_payload(instance_payload, "patch_successfully_applied", "patch_applied")
        tests_passed = self._bool_from_payload(instance_payload, "tests_passed", "all_tests_passed")
        if tests_passed is None and resolved:
            tests_passed = True
        if instance_id not in submitted_ids and submitted_ids:
            warnings.append(f"{instance_id}: not listed in submitted_instances")
        expected_oracle = str(item.get("oracle_fingerprint") or "")
        observed_oracle = str((instance_payload or {}).get("oracle_fingerprint") or expected_oracle)
        if expected_oracle and observed_oracle and expected_oracle != observed_oracle:
            failures.append(f"{instance_id}: oracle fingerprint drifted after execution")
        receipt = {
            "instance_id": instance_id,
            "repo": item.get("repo"),
            "base_commit": item.get("base_commit"),
            "evaluation_found": evaluation_found,
            "completed": completed,
            "resolved": resolved,
            "patch_applied": patch_applied,
            "tests_passed": tests_passed,
            "oracle_fingerprint": expected_oracle,
            "official_payload": instance_payload or {},
            "result_membership": {
                "submitted": instance_id in submitted_ids,
                "completed": instance_id in completed_ids,
                "resolved": instance_id in resolved_ids,
                "unresolved": instance_id in unresolved_ids,
            },
            "summary_keys": sorted(results_payload),
        }
        receipt_ref = output_root / _safe_name(instance_id) / "official_execution_receipt.json"
        _write_json(receipt_ref, receipt)
        artifact_uris = [str(receipt_ref)]
        result_payload = {
            "receipt": receipt,
            "failures": failures,
            "warnings": warnings,
        }
        return SweBenchOfficialExecutionItemResult(
            instance_id=instance_id,
            repo=str(item.get("repo") or ""),
            base_commit=str(item.get("base_commit") or ""),
            evaluation_found=evaluation_found,
            completed=bool(completed),
            resolved=bool(resolved),
            patch_applied=patch_applied,
            tests_passed=tests_passed,
            oracle_fingerprint=expected_oracle,
            execution_receipt_ref=str(receipt_ref),
            artifact_uris=artifact_uris,
            failures=failures,
            warnings=warnings,
            result_fingerprint=_stable_hash(result_payload),
        )

    def _resolve_official_paths(self) -> tuple[Path, Path | None, Path | None]:
        path = self.evaluation_results_path
        results_path: Path | None = None
        instance_results_path = self.instance_results_path
        run_logs_path = self.run_logs_path
        if path.is_dir():
            for filename in self.RESULT_FILENAME_CANDIDATES:
                candidate = path / filename
                if candidate.exists():
                    results_path = candidate
                    break
            if instance_results_path is None:
                for filename in self.INSTANCE_RESULT_FILENAME_CANDIDATES:
                    candidate = path / filename
                    if candidate.exists():
                        instance_results_path = candidate
                        break
            if run_logs_path is None and (path / "run_logs").exists():
                run_logs_path = path / "run_logs"
        else:
            results_path = path

        if results_path is None or not results_path.exists():
            raise FileNotFoundError(f"official SWE-bench results.json not found under: {path}")
        return results_path, instance_results_path, run_logs_path

    @staticmethod
    def _read_json(path: Path) -> JsonDict:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"expected JSON object: {path}")
        return payload

    @staticmethod
    def _read_instance_results(path: Path | None) -> list[JsonDict]:
        if path is None or not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    @staticmethod
    def _write_jsonl(path: Path, payloads: list[JsonDict]) -> None:
        path.write_text("\n".join(json.dumps(payload, sort_keys=True, default=str) for payload in payloads), encoding="utf-8")

    @staticmethod
    def _ids_from_payload(payload: JsonDict, *keys: str) -> set[str]:
        for key in keys:
            if key not in payload:
                continue
            value = payload[key]
            if isinstance(value, dict):
                return {str(item) for item, enabled in value.items() if enabled}
            return set(_as_list(value))
        return set()

    @staticmethod
    def _bool_from_payload(payload: JsonDict | None, *keys: str) -> bool | None:
        if not payload:
            return None
        for key in keys:
            if key not in payload:
                continue
            value = payload[key]
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "yes", "pass", "passed", "resolved", "success"}:
                    return True
                if lowered in {"false", "no", "fail", "failed", "unresolved", "error"}:
                    return False
            if isinstance(value, int | float):
                return bool(value)
        return None


class SweBenchOfficialSubsetBridge:
    """Prepares official SWE-bench-style subsets for artifact-reviewed runs.

    The bridge does not execute Docker. It validates official-style instances
    and predictions, emits a runnable predictions JSONL, pins oracle/provenance
    fingerprints, and records the exact harness command that a later Docker
    execution should use.
    """

    DEFAULT_DATASET_NAME = "princeton-nlp/SWE-bench_Verified"
    SOURCE_REFS = [
        "https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/evaluation.md",
        "https://www.swebench.com/SWE-bench/faq/",
        "https://openai.com/index/introducing-swe-bench-verified/",
        "https://labs.scale.com/leaderboard/swe_bench_pro_public",
    ]

    def __init__(
        self,
        instances: list[SweBenchInstance],
        predictions: list[SweBenchPrediction] | None = None,
        *,
        dataset_name: str = DEFAULT_DATASET_NAME,
        run_id: str = "harness-x-hermes-small-subset",
        max_workers: int = 1,
    ):
        self.instances = list(instances)
        self.predictions = list(predictions or [])
        self.dataset_name = dataset_name
        self.run_id = run_id
        self.max_workers = max_workers

    @classmethod
    def demo(cls) -> "SweBenchOfficialSubsetBridge":
        instances = SweBenchSmallSubsetAdapter.demo_instances()
        predictions = [
            SweBenchPrediction(
                instance_id=instance.instance_id,
                model_name_or_path="demo-oracle-provenance-agent",
                model_patch=instance.candidate_patch or instance.patch,
            )
            for instance in instances
        ]
        return cls(instances, predictions)

    @classmethod
    def from_jsonl(
        cls,
        instances_path: str | Path,
        *,
        predictions_path: str | Path | None = None,
        limit: int | None = None,
        dataset_name: str = DEFAULT_DATASET_NAME,
        run_id: str = "harness-x-hermes-small-subset",
        max_workers: int = 1,
    ) -> "SweBenchOfficialSubsetBridge":
        instances = [
            SweBenchInstance.from_dict(payload)
            for payload in cls._read_jsonl(instances_path, limit=limit)
        ]
        predictions = [
            SweBenchPrediction.from_dict(payload)
            for payload in cls._read_jsonl(predictions_path, limit=None)
        ] if predictions_path else []
        return cls(
            instances,
            predictions,
            dataset_name=dataset_name,
            run_id=run_id,
            max_workers=max_workers,
        )

    def run(self, workspace_root: str | Path) -> SweBenchOfficialSubsetReport:
        root = Path(workspace_root)
        root.mkdir(parents=True, exist_ok=True)
        predictions_by_id = {prediction.instance_id: prediction for prediction in self.predictions}
        item_results = [
            self._run_instance(root, instance, predictions_by_id.get(instance.instance_id))
            for instance in self.instances
        ]
        predictions_payload = [
            predictions_by_id[instance.instance_id].to_dict()
            for instance in self.instances
            if instance.instance_id in predictions_by_id
        ]
        subset_instances_path = root / "official_subset_instances.jsonl"
        predictions_path = root / "official_predictions.jsonl"
        command_path = root / "official_harness_command.txt"
        manifest_path = root / "official_subset_manifest.json"
        self._write_jsonl(subset_instances_path, [instance.to_dict() for instance in self.instances])
        self._write_jsonl(predictions_path, predictions_payload)
        command = self._official_harness_command(predictions_path)
        _write_text(command_path, command + "\n")
        failures = [failure for result in item_results for failure in result.failures]
        warnings = [warning for result in item_results for warning in result.warnings]
        manifest_payload = {
            "dataset_name": self.dataset_name,
            "run_id": self.run_id,
            "max_workers": self.max_workers,
            "source_refs": self.SOURCE_REFS,
            "subset_instances_ref": str(subset_instances_path),
            "predictions_ref": str(predictions_path),
            "official_harness_command": command,
            "items": [result.to_dict() for result in item_results],
        }
        _write_json(manifest_path, manifest_payload)
        artifact_uris = [
            str(subset_instances_path),
            str(predictions_path),
            str(command_path),
            str(manifest_path),
            *[uri for result in item_results for uri in result.artifact_uris],
        ]
        ready = bool(item_results) and not failures and all(result.official_harness_ready for result in item_results)
        payload = {
            "manifest": manifest_payload,
            "artifact_uris": artifact_uris,
            "predictions": predictions_payload,
        }
        return SweBenchOfficialSubsetReport(
            ready_for_official_subset=ready,
            dataset_name=self.dataset_name,
            instance_count=len(item_results),
            prediction_count=len(self.predictions),
            matched_prediction_count=sum(1 for result in item_results if result.has_prediction),
            oracle_audit_sound_count=sum(1 for result in item_results if result.oracle_audit_sound),
            official_harness_ready_count=sum(1 for result in item_results if result.official_harness_ready),
            local_executor_ready_count=sum(1 for result in item_results if result.local_executor_ready),
            artifact_count=len(artifact_uris),
            official_harness_command=command,
            subset_manifest_ref=str(manifest_path),
            predictions_ref=str(predictions_path),
            failures=failures,
            warnings=warnings,
            run_fingerprint=_stable_hash(payload),
            item_results=item_results,
        )

    def _run_instance(
        self,
        workspace_root: Path,
        instance: SweBenchInstance,
        prediction: SweBenchPrediction | None,
    ) -> SweBenchOfficialSubsetItemResult:
        item_root = workspace_root / _safe_name(instance.instance_id)
        failures = SweBenchSmallSubsetAdapter([instance])._instance_failures(instance)
        warnings: list[str] = []
        if prediction is None or not prediction.model_patch.strip():
            failures.append(f"{instance.instance_id}: missing prediction model_patch for official harness")
        candidate_patch = prediction.model_patch if prediction is not None else ""
        local_repo_path = instance.metadata.get("local_repo_path") or instance.metadata.get("repo_path")
        test_command = instance.metadata.get("test_command")
        local_executor_ready = bool(local_repo_path and Path(str(local_repo_path)).exists() and test_command)
        environment = {
            "dataset_name": self.dataset_name,
            "official_harness": "swebench.harness.run_evaluation",
            "prediction_model": prediction.model_name_or_path if prediction else "",
            "local_repo_path": str(local_repo_path or ""),
            "local_executor_ready": local_executor_ready,
        }
        oracle_audit = SweBenchSmallSubsetAdapter([instance])._oracle_audit_report(
            instance,
            candidate_patch=candidate_patch,
            environment=environment,
        )
        oracle_path = item_root / "oracle_audit_report.json"
        instance_path = item_root / "instance.json"
        prediction_path = item_root / "prediction.json"
        _write_json(oracle_path, oracle_audit.to_dict())
        _write_json(instance_path, instance.to_dict())
        _write_json(prediction_path, prediction.to_dict() if prediction else {})
        failures.extend(oracle_audit.failures)
        warnings.extend(oracle_audit.warnings)
        official_ready = not failures and oracle_audit.sound and prediction is not None and bool(prediction.model_patch.strip())
        return SweBenchOfficialSubsetItemResult(
            instance_id=instance.instance_id,
            repo=instance.repo,
            base_commit=instance.base_commit,
            has_prediction=prediction is not None and bool(prediction.model_patch.strip()),
            prediction_model=prediction.model_name_or_path if prediction else "",
            oracle_audit_sound=oracle_audit.sound,
            oracle_fingerprint=oracle_audit.oracle_fingerprint,
            official_harness_ready=official_ready,
            local_executor_ready=local_executor_ready,
            artifact_uris=[str(instance_path), str(prediction_path), str(oracle_path)],
            failures=failures,
            warnings=warnings,
        )

    def _official_harness_command(self, predictions_path: Path) -> str:
        return (
            "python -m swebench.harness.run_evaluation "
            f"--dataset_name {self.dataset_name} "
            f"--predictions_path {predictions_path} "
            f"--max_workers {self.max_workers} "
            f"--run_id {self.run_id}"
        )

    @staticmethod
    def _read_jsonl(path: str | Path | None, *, limit: int | None = None) -> list[JsonDict]:
        if path is None:
            return []
        payloads: list[JsonDict] = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payloads.append(json.loads(line))
            if limit is not None and len(payloads) >= limit:
                break
        return payloads

    @staticmethod
    def _write_jsonl(path: Path, records: list[JsonDict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(record, sort_keys=True, default=str) for record in records) + ("\n" if records else ""),
            encoding="utf-8",
        )


class SweBenchSmallSubsetAdapter:
    """Materializes SWE-bench-style issue-to-patch tasks into Hermes scenes.

    This adapter is an evaluation bridge, not a Docker-based SWE-bench executor.
    It makes patch, test, evidence, memory-commit, and hydration artifacts
    explicit so that a later real SWE-bench runner can plug into the same FSE
    reporting contract.
    """

    def __init__(self, instances: list[SweBenchInstance] | None = None):
        self.instances = list(instances or self.demo_instances())

    @classmethod
    def from_jsonl(cls, path: str | Path, *, limit: int | None = None) -> "SweBenchSmallSubsetAdapter":
        instances: list[SweBenchInstance] = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            instances.append(SweBenchInstance.from_dict(json.loads(line)))
            if limit is not None and len(instances) >= limit:
                break
        return cls(instances)

    @staticmethod
    def demo_instances() -> list[SweBenchInstance]:
        return [
            SweBenchInstance(
                instance_id="demo__calculator-001",
                repo="demo/calculator",
                base_commit="abc123",
                problem_statement="The add helper subtracts its second argument.",
                patch=(
                    "diff --git a/calculator.py b/calculator.py\n"
                    "--- a/calculator.py\n"
                    "+++ b/calculator.py\n"
                    "@@\n"
                    "-    return a - b\n"
                    "+    return a + b\n"
                ),
                test_patch=(
                    "diff --git a/test_calculator.py b/test_calculator.py\n"
                    "+++ b/test_calculator.py\n"
                    "@@\n"
                    "+def test_add():\n"
                    "+    assert add(1, 2) == 3\n"
                ),
                candidate_patch=(
                    "diff --git a/calculator.py b/calculator.py\n"
                    "--- a/calculator.py\n"
                    "+++ b/calculator.py\n"
                    "@@\n"
                    "-    return a - b\n"
                    "+    return a + b\n"
                ),
                fail_to_pass=["test_calculator.py::test_add"],
                source_refs=[
                    "https://www.swebench.com/swebench-verified.html",
                    "https://github.com/swe-bench/SWE-bench",
                    "https://labs.scale.com/leaderboard/swe_bench_pro_public",
                ],
            ),
            SweBenchInstance(
                instance_id="demo__parser-002",
                repo="demo/parser",
                base_commit="def456",
                problem_statement="The parser should strip whitespace before comparing tokens.",
                patch=(
                    "diff --git a/parser.py b/parser.py\n"
                    "--- a/parser.py\n"
                    "+++ b/parser.py\n"
                    "@@\n"
                    "-    return token == expected\n"
                    "+    return token.strip() == expected\n"
                ),
                test_patch=(
                    "diff --git a/test_parser.py b/test_parser.py\n"
                    "+++ b/test_parser.py\n"
                    "@@\n"
                    "+def test_token_strip():\n"
                    "+    assert parse(' ok ') == 'ok'\n"
                ),
                candidate_patch=(
                    "diff --git a/parser.py b/parser.py\n"
                    "--- a/parser.py\n"
                    "+++ b/parser.py\n"
                    "@@\n"
                    "-    return token == expected\n"
                    "+    return token.lower() == expected\n"
                ),
                fail_to_pass=["test_parser.py::test_token_strip"],
                source_refs=[
                    "https://www.swebench.com/swebench-verified.html",
                    "https://software-lab.org/publications/icse2026_SWE-bench-correctness.pdf",
                    "https://labs.scale.com/leaderboard/swe_bench_pro_public",
                ],
            ),
        ]

    def run(self, workspace_root: str | Path) -> SweBenchAdapterRunReport:
        root = Path(workspace_root)
        root.mkdir(parents=True, exist_ok=True)
        results = [self._run_instance(root, instance) for instance in self.instances]
        failures = [failure for result in results for failure in result.failures]
        warnings = [warning for result in results for warning in result.warnings]
        mean_patch_line_jaccard = self._mean([result.patch_line_jaccard for result in results])
        mean_behavioral_divergence_score = self._mean(
            [result.behavioral_divergence_score for result in results]
        )
        payload = {
            "workspace_root": str(root),
            "instances": [instance.to_dict() for instance in self.instances],
            "results": [result.to_dict() for result in results],
        }

        return SweBenchAdapterRunReport(
            ready_for_swebench_adapter=not failures and bool(results),
            instance_count=len(results),
            success_count=sum(1 for result in results if result.success),
            hydration_safe_count=sum(1 for result in results if result.hydration_safe),
            evidence_sound_count=sum(1 for result in results if result.evidence_ledger_sound),
            phase_gate_passed_count=sum(1 for result in results if result.phase_gate_passed),
            candidate_patch_equal_count=sum(1 for result in results if result.patch_equal_to_gold),
            test_patch_present_count=sum(1 for result in results if result.test_patch_present),
            oracle_audit_sound_count=sum(1 for result in results if result.oracle_audit_sound),
            artifact_count=sum(len(result.artifact_uris) for result in results),
            mean_patch_line_jaccard=mean_patch_line_jaccard,
            mean_behavioral_divergence_score=mean_behavioral_divergence_score,
            failures=failures,
            warnings=warnings,
            run_fingerprint=_stable_hash(payload),
            instance_results=results,
        )

    def _run_instance(self, workspace_root: Path, instance: SweBenchInstance) -> SweBenchInstanceResult:
        task_root = workspace_root / _safe_name(instance.instance_id)
        warnings: list[str] = []
        failures = self._instance_failures(instance)
        candidate_patch = instance.candidate_patch
        if candidate_patch is None:
            candidate_patch = instance.patch
            warnings.append(f"{instance.instance_id}: no candidate patch provided; using gold patch for adapter smoke")

        patch_equal_to_gold = _normalize_patch(candidate_patch) == _normalize_patch(instance.patch)
        patch_line_jaccard = round(_jaccard(_patch_line_set(candidate_patch), _patch_line_set(instance.patch)), 4)
        changed_file_overlap = round(_jaccard(_changed_files(candidate_patch), _changed_files(instance.patch)), 4)
        behavioral_divergence_score = round(1.0 - ((0.7 * patch_line_jaccard) + (0.3 * changed_file_overlap)), 4)
        correctness_payload = {
            "instance_id": instance.instance_id,
            "repo": instance.repo,
            "base_commit": instance.base_commit,
            "patch_equal_to_gold": patch_equal_to_gold,
            "changed_file_overlap": changed_file_overlap,
            "patch_line_jaccard": patch_line_jaccard,
            "behavioral_divergence_score": behavioral_divergence_score,
            "behavioral_divergence_note": (
                "Patch-level proxy until the adapter is connected to a full SWE-bench execution harness."
            ),
            "test_patch_present": bool(instance.test_patch.strip()),
            "fail_to_pass": list(instance.fail_to_pass),
            "pass_to_pass": list(instance.pass_to_pass),
        }
        oracle_audit = self._oracle_audit_report(instance, candidate_patch=candidate_patch)
        correctness_payload["oracle_audit_fingerprint"] = oracle_audit.oracle_fingerprint
        artifact_refs = self._materialize_artifacts(
            task_root,
            instance=instance,
            candidate_patch=candidate_patch,
            correctness_payload=correctness_payload,
            oracle_audit=oracle_audit,
        )
        evidence_ledger = self._evidence_ledger(instance, artifact_refs)
        evidence_report = evidence_ledger.evaluate(
            required_claim_ids=self._claim_ids(instance),
        )
        memory_protocol = MemoryCommitProtocol()
        memory_commit = self._commit_memory(
            instance,
            memory_protocol,
            artifact_refs,
            correctness_payload=correctness_payload,
            evidence_sound=evidence_report.sound,
        )
        research_session = self._research_session(instance, artifact_refs, memory_commit.committed_record_ids)
        phase_gate = ResearchPhaseGate(
            phase=ResearchPhase.WRITEUP,
            required_artifact_kinds=[
                "swebench_candidate_patch",
                "swebench_test_patch",
                "swebench_correctness_report",
                "swebench_oracle_audit",
            ],
            required_transition_labels=[
                "load_swebench_instance",
                "materialize_patch_artifacts",
                "compute_patch_divergence",
            ],
            required_memory_record_ids=list(memory_commit.committed_record_ids),
            required_evidence_claim_ids=self._claim_ids(instance),
            require_validation_receipt=True,
            require_review_ref=True,
        )
        research_report = ResearchSessionVerifier().evaluate(
            research_session,
            phase_gates=[phase_gate],
            evidence_ledger=evidence_ledger,
        )
        trace_events = self._trace_events(instance, artifact_refs, correctness_payload)
        state = RuntimeState(
            task_id=f"swebench::{instance.instance_id}",
            session_id=f"swebench-session::{instance.instance_id}",
            run_id=f"swebench-run::{instance.instance_id}",
            goal=instance.problem_statement,
            execution_cursor="after:swebench_patch_report",
            active_step="writeup",
            process_stage="active",
            policy_snapshot={
                "dataset": "swe-bench-style",
                "adapter": "small-subset",
                "requires_patch_correctness_evidence": True,
            },
            artifact_refs=list(artifact_refs),
            metadata={
                "repo": instance.repo,
                "base_commit": instance.base_commit,
                "behavioral_divergence_score": behavioral_divergence_score,
                "active_evidence_ledger": {
                    "name": "swebench-adapter-ledger",
                    "fingerprint": evidence_ledger.fingerprint(),
                    "claim_ids": self._claim_ids(instance),
                },
            },
        )
        hydration_builder = HydrationManifestBuilder()
        hydration_manifest = hydration_builder.dehydrate(
            state,
            trace_events,
            memory_records=list(memory_protocol.records.values()),
            evidence_ledger=evidence_ledger,
            research_session=research_session,
            required_memory_record_ids=list(memory_commit.committed_record_ids),
            required_evidence_claim_ids=self._claim_ids(instance),
            required_artifact_uris=[artifact.uri for artifact in artifact_refs],
        )
        hydration_report = hydration_builder.verify(
            hydration_manifest,
            state,
            trace_events,
            memory_records=list(memory_protocol.records.values()),
            evidence_ledger=evidence_ledger,
            research_session=research_session,
        )
        failures.extend(evidence_report.failures)
        failures.extend(oracle_audit.failures)
        failures.extend(memory_commit.failures)
        failures.extend(research_report.failures)
        failures.extend(hydration_report.failures)
        warnings.extend(evidence_report.warnings)
        warnings.extend(oracle_audit.warnings)
        warnings.extend(research_report.warnings)
        warnings.extend(hydration_report.warnings)

        success = (
            not failures
            and oracle_audit.sound
            and evidence_report.sound
            and research_report.phase_gate_passed
            and hydration_report.safe_to_hydrate
        )
        payload = {
            "instance": instance.to_dict(),
            "correctness": correctness_payload,
            "oracle_audit": oracle_audit.to_dict(),
            "artifacts": [asdict(ref) for ref in artifact_refs],
            "evidence_report": evidence_report.to_dict(),
            "memory_commit": memory_commit.to_dict(),
            "research_report": research_report.to_dict(),
            "hydration_report": hydration_report.to_dict(),
        }

        return SweBenchInstanceResult(
            instance_id=instance.instance_id,
            repo=instance.repo,
            success=success,
            workspace_ref=str(task_root),
            artifact_uris=[artifact.uri for artifact in artifact_refs],
            evidence_claim_ids=self._claim_ids(instance),
            committed_memory_record_ids=list(memory_commit.committed_record_ids),
            patch_equal_to_gold=patch_equal_to_gold,
            changed_file_overlap=changed_file_overlap,
            patch_line_jaccard=patch_line_jaccard,
            behavioral_divergence_score=behavioral_divergence_score,
            test_patch_present=bool(instance.test_patch.strip()),
            oracle_audit_sound=oracle_audit.sound,
            evidence_ledger_sound=evidence_report.sound,
            phase_gate_passed=research_report.phase_gate_passed,
            hydration_safe=hydration_report.safe_to_hydrate,
            failures=failures,
            warnings=warnings,
            result_fingerprint=_stable_hash(payload),
        )

    def _materialize_artifacts(
        self,
        task_root: Path,
        *,
        instance: SweBenchInstance,
        candidate_patch: str,
        correctness_payload: JsonDict,
        oracle_audit: SweBenchOracleAuditReport,
    ) -> list[ArtifactRef]:
        instance_hash = _write_json(task_root / "swebench_instance.json", instance.to_dict())
        problem_hash = _write_text(task_root / "problem_statement.md", instance.problem_statement)
        gold_hash = _write_text(task_root / "gold.patch", instance.patch)
        candidate_hash = _write_text(task_root / "candidate.patch", candidate_patch)
        test_hash = _write_text(task_root / "test.patch", instance.test_patch)
        report_hash = _write_json(task_root / "patch_correctness_report.json", correctness_payload)
        oracle_hash = _write_json(task_root / "oracle_audit_report.json", oracle_audit.to_dict())
        return [
            ArtifactRef(kind="swebench_instance", uri=str(task_root / "swebench_instance.json"), sha256=instance_hash),
            ArtifactRef(kind="swebench_problem_statement", uri=str(task_root / "problem_statement.md"), sha256=problem_hash),
            ArtifactRef(kind="swebench_gold_patch", uri=str(task_root / "gold.patch"), sha256=gold_hash),
            ArtifactRef(kind="swebench_candidate_patch", uri=str(task_root / "candidate.patch"), sha256=candidate_hash),
            ArtifactRef(kind="swebench_test_patch", uri=str(task_root / "test.patch"), sha256=test_hash),
            ArtifactRef(
                kind="swebench_correctness_report",
                uri=str(task_root / "patch_correctness_report.json"),
                sha256=report_hash,
                metadata={"metric_source": "patch-level-adapter-smoke"},
            ),
            ArtifactRef(
                kind="swebench_oracle_audit",
                uri=str(task_root / "oracle_audit_report.json"),
                sha256=oracle_hash,
                metadata={"oracle_fingerprint": oracle_audit.oracle_fingerprint},
            ),
        ]

    def _evidence_ledger(self, instance: SweBenchInstance, artifact_refs: list[ArtifactRef]) -> EvidenceLedger:
        entries = [
            EvidenceEntry(
                entry_id=f"{self._entry_prefix(instance)}-{index}",
                kind=EvidenceKind.ARTIFACT,
                source_ref=artifact.uri,
                content_hash=artifact.sha256 or "",
                labels=[artifact.kind, "swebench-style", "issue-to-patch"],
                metadata={"instance_id": instance.instance_id, "repo": instance.repo},
            )
            for index, artifact in enumerate(artifact_refs)
        ]
        by_kind = {
            artifact.kind: entries[index].entry_id
            for index, artifact in enumerate(artifact_refs)
        }
        claims = [
            EvidenceClaim(
                claim_id=self._claim_ids(instance)[0],
                statement="The SWE-bench issue is bound to a repository, base commit, and problem statement.",
                cited_entry_ids=[
                    by_kind["swebench_instance"],
                    by_kind["swebench_problem_statement"],
                ],
                required_labels=["swebench_instance", "swebench_problem_statement"],
            ),
            EvidenceClaim(
                claim_id=self._claim_ids(instance)[1],
                statement="The candidate patch and test patch were materialized as reviewable artifacts.",
                cited_entry_ids=[
                    by_kind["swebench_candidate_patch"],
                    by_kind["swebench_test_patch"],
                ],
                required_labels=["swebench_candidate_patch", "swebench_test_patch"],
            ),
            EvidenceClaim(
                claim_id=self._claim_ids(instance)[2],
                statement="Patch-level correctness and divergence evidence was produced for this instance.",
                cited_entry_ids=[
                    by_kind["swebench_gold_patch"],
                    by_kind["swebench_candidate_patch"],
                    by_kind["swebench_correctness_report"],
                ],
                required_labels=["swebench_correctness_report"],
            ),
            EvidenceClaim(
                claim_id=self._claim_ids(instance)[3],
                statement="The SWE-bench-style task oracle and provenance metadata were audited and fingerprinted.",
                cited_entry_ids=[
                    by_kind["swebench_instance"],
                    by_kind["swebench_gold_patch"],
                    by_kind["swebench_test_patch"],
                    by_kind["swebench_oracle_audit"],
                ],
                required_labels=["swebench_oracle_audit"],
            ),
        ]
        return EvidenceLedger(entries=entries, claims=claims)

    def _commit_memory(
        self,
        instance: SweBenchInstance,
        memory_protocol: MemoryCommitProtocol,
        artifact_refs: list[ArtifactRef],
        *,
        correctness_payload: JsonDict,
        evidence_sound: bool,
    ):
        tx = memory_protocol.begin_transaction(
            transaction_id=f"tx-swebench-{_safe_name(instance.instance_id)}",
            checkpoint_version=1,
            metadata={"dataset": "swe-bench-style", "instance_id": instance.instance_id},
        )
        record = memory_protocol.stage_record(
            tx.transaction_id,
            record_id=f"memory-swebench-{_safe_name(instance.instance_id)}",
            kind=MemoryKind.BELIEF,
            payload={
                "instance_id": instance.instance_id,
                "repo": instance.repo,
                "base_commit": instance.base_commit,
                "patch_equal_to_gold": correctness_payload["patch_equal_to_gold"],
                "patch_line_jaccard": correctness_payload["patch_line_jaccard"],
                "behavioral_divergence_score": correctness_payload["behavioral_divergence_score"],
                "claim": "SWE-bench adapter materialized patch correctness evidence.",
            },
            source_refs=[artifact.uri for artifact in artifact_refs],
        )
        memory_protocol.validate_record(
            record.record_id,
            ValidationReceipt(
                validator="swebench-small-subset-adapter",
                passed=evidence_sound and bool(instance.test_patch.strip()),
                reasons=[
                    "evidence ledger sound" if evidence_sound else "evidence ledger failed",
                    "test patch present" if instance.test_patch.strip() else "test patch missing",
                    "patch divergence proxy computed",
                ],
                evidence_refs=[artifact.uri for artifact in artifact_refs],
                checkpoint_version=1,
                metadata={"instance_id": instance.instance_id},
            ),
        )
        return memory_protocol.commit(tx.transaction_id, checkpoint_version=2)

    def _research_session(
        self,
        instance: SweBenchInstance,
        artifact_refs: list[ArtifactRef],
        committed_record_ids: list[str],
    ) -> ResearchSession:
        session = ResearchSession(
            session_id=f"swebench-research::{instance.instance_id}",
            runtime_task_id=f"swebench::{instance.instance_id}",
            goal=instance.problem_statement,
            policy_snapshot_hash=_stable_hash({"adapter": "swebench-small-subset", "instance_id": instance.instance_id}),
            metadata={"repo": instance.repo, "base_commit": instance.base_commit},
        )
        labels = [
            "load_swebench_instance",
            "materialize_patch_artifacts",
            "compute_patch_divergence",
        ]
        claim_refs = [f"claim://{claim_id}" for claim_id in self._claim_ids(instance)]
        session.advance_to(
            ResearchPhase.PAPER_SCAN,
            evidence_refs=claim_refs[:1],
            transition_labels=[labels[0]],
        )
        session.advance_to(ResearchPhase.HYPOTHESIS)
        session.advance_to(ResearchPhase.EXPERIMENT_PLAN, transition_labels=[labels[1]])
        session.advance_to(
            ResearchPhase.EXPERIMENT_RUN,
            artifact_refs=list(artifact_refs),
            evidence_refs=claim_refs,
            transition_labels=labels,
            memory_record_ids=list(committed_record_ids),
            validation_receipt_refs=[f"receipt://swebench/{instance.instance_id}/patch-correctness"],
        )
        session.advance_to(ResearchPhase.ANALYSIS, transition_labels=[labels[2]])
        session.advance_to(ResearchPhase.REVIEW, review_refs=[f"review://swebench/{instance.instance_id}/adapter-smoke"])
        session.advance_to(ResearchPhase.WRITEUP)
        return session

    def _trace_events(
        self,
        instance: SweBenchInstance,
        artifact_refs: list[ArtifactRef],
        correctness_payload: JsonDict,
    ) -> list[TraceEvent]:
        events: list[TraceEvent] = []
        labels = [
            "load_swebench_instance",
            "materialize_patch_artifacts",
            "compute_patch_divergence",
        ]
        for index, label in enumerate(labels):
            envelope = {
                "schema_version": "trace-envelope-v2",
                "boundary": TraceBoundary.TOOL,
                "task_id": f"swebench::{instance.instance_id}",
                "run_id": f"swebench-run::{instance.instance_id}",
                "cursor": f"swebench:{index}",
                "provider_name": "swebench-small-subset-adapter",
                "provider_fingerprint": _stable_hash({"provider": "swebench-small-subset-adapter"})[:12],
                "policy_fingerprint": _stable_hash({"dataset": "swe-bench-style", "adapter": "small-subset"})[:12],
                "action_name": label,
                "action_effect": "execute",
                "input_hash": hash_payload({"instance_id": instance.instance_id, "label": label}),
                "output_hash": hash_payload({"artifacts": [artifact.uri for artifact in artifact_refs], "label": label}),
                "evidence_ledger_fingerprint": _stable_hash({"claim_ids": self._claim_ids(instance)})[:12],
                "evidence_claim_ids": self._claim_ids(instance),
                "artifact_refs": [artifact.uri for artifact in artifact_refs],
                "receipts": [],
            }
            envelope["trace_envelope_fingerprint"] = hash_payload(envelope)
            events.append(
                TraceEvent(
                    event_id=f"swebench-{_safe_name(instance.instance_id)}-{index}",
                    task_id=f"swebench::{instance.instance_id}",
                    run_id=f"swebench-run::{instance.instance_id}",
                    cursor=f"swebench:{index}",
                    kind="tool_completed",
                    data={
                        "tool": label,
                        "args_hash": envelope["input_hash"],
                        "output_hash": envelope["output_hash"],
                        "artifact_refs": [artifact.uri for artifact in artifact_refs],
                        "correctness": correctness_payload,
                        "trace_envelope": envelope,
                        "trace_envelope_fingerprint": envelope["trace_envelope_fingerprint"],
                    },
                )
            )
        return events

    def _oracle_audit_report(
        self,
        instance: SweBenchInstance,
        *,
        candidate_patch: str,
        environment: JsonDict | None = None,
    ) -> SweBenchOracleAuditReport:
        required_fields = {
            "instance_id": instance.instance_id,
            "repo": instance.repo,
            "base_commit": instance.base_commit,
            "problem_statement": instance.problem_statement,
            "patch": instance.patch,
            "test_patch": instance.test_patch,
        }
        missing_fields = [field_name for field_name, value in required_fields.items() if not str(value).strip()]
        contamination_flags = _as_list(instance.metadata.get("contamination_flags"))
        warnings: list[str] = []
        if not instance.source_refs:
            warnings.append(f"{instance.instance_id}: no source_refs supplied for benchmark provenance")
        if not instance.fail_to_pass:
            warnings.append(f"{instance.instance_id}: no fail_to_pass tests supplied")

        audit_payload = {
            "instance_id": instance.instance_id,
            "repo": instance.repo,
            "base_commit": instance.base_commit,
            "problem_statement_sha256": _sha256_text(instance.problem_statement),
            "gold_patch_sha256": _sha256_text(instance.patch),
            "candidate_patch_sha256": _sha256_text(candidate_patch),
            "test_patch_sha256": _sha256_text(instance.test_patch),
            "fail_to_pass_sha256": _stable_hash(list(instance.fail_to_pass)),
            "pass_to_pass_sha256": _stable_hash(list(instance.pass_to_pass)),
            "source_refs": list(instance.source_refs),
            "environment": dict(environment or {}),
            "contamination_flags": contamination_flags,
        }
        failures = [
            f"{instance.instance_id}: oracle audit missing {field_name}"
            for field_name in missing_fields
        ]
        if contamination_flags:
            failures.append(f"{instance.instance_id}: contamination flags present: {', '.join(contamination_flags)}")

        return SweBenchOracleAuditReport(
            sound=not failures,
            oracle_fingerprint=_stable_hash(audit_payload),
            instance_id=instance.instance_id,
            repo=instance.repo,
            base_commit=instance.base_commit,
            problem_statement_sha256=audit_payload["problem_statement_sha256"],
            gold_patch_sha256=audit_payload["gold_patch_sha256"],
            candidate_patch_sha256=audit_payload["candidate_patch_sha256"],
            test_patch_sha256=audit_payload["test_patch_sha256"],
            fail_to_pass_sha256=audit_payload["fail_to_pass_sha256"],
            pass_to_pass_sha256=audit_payload["pass_to_pass_sha256"],
            source_refs=list(instance.source_refs),
            environment=dict(environment or {}),
            contamination_flags=contamination_flags,
            missing_fields=missing_fields,
            failures=failures,
            warnings=warnings,
        )

    def _instance_failures(self, instance: SweBenchInstance) -> list[str]:
        failures: list[str] = []
        if not instance.instance_id.strip():
            failures.append("missing SWE-bench instance_id")
        if not instance.repo.strip():
            failures.append(f"{instance.instance_id}: missing repo")
        if not instance.base_commit.strip():
            failures.append(f"{instance.instance_id}: missing base_commit")
        if not instance.problem_statement.strip():
            failures.append(f"{instance.instance_id}: missing problem_statement")
        if not instance.patch.strip():
            failures.append(f"{instance.instance_id}: missing gold patch")
        if not instance.test_patch.strip():
            failures.append(f"{instance.instance_id}: missing test_patch")
        return failures

    def _claim_ids(self, instance: SweBenchInstance) -> list[str]:
        prefix = self._entry_prefix(instance)
        return [
            f"claim-{prefix}-issue-bound",
            f"claim-{prefix}-candidate-tested",
            f"claim-{prefix}-divergence-measured",
            f"claim-{prefix}-oracle-audited",
        ]

    def _entry_prefix(self, instance: SweBenchInstance) -> str:
        return _safe_name(instance.instance_id).lower()

    def _mean(self, values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)


@dataclass(frozen=True, slots=True)
class SweBenchExecutionResult:
    instance_id: str
    repo: str
    success: bool
    tests_passed: bool
    test_exit_code: int | None
    command: list[str] | str
    duration_s: float
    workspace_ref: str
    repo_workspace_ref: str
    artifact_uris: list[str]
    evidence_claim_ids: list[str]
    committed_memory_record_ids: list[str]
    applied_test_patch: bool
    applied_candidate_patch: bool
    patch_equal_to_gold: bool
    changed_file_overlap: float
    patch_line_jaccard: float
    behavioral_divergence_score: float
    oracle_audit_sound: bool
    evidence_ledger_sound: bool
    phase_gate_passed: bool
    hydration_safe: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    result_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SweBenchExecutorRunReport:
    ready_for_swebench_executor: bool
    instance_count: int
    success_count: int
    tests_passed_count: int
    hydration_safe_count: int
    evidence_sound_count: int
    phase_gate_passed_count: int
    candidate_patch_equal_count: int
    oracle_audit_sound_count: int
    artifact_count: int
    mean_patch_line_jaccard: float
    mean_behavioral_divergence_score: float
    mean_duration_s: float
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    run_fingerprint: str = ""
    instance_results: list[SweBenchExecutionResult] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        data["instance_results"] = [result.to_dict() for result in self.instance_results]
        return data


class SweBenchLocalPatchExecutor:
    """Executes SWE-bench-style local patch tasks in a bounded workspace.

    This is still not the official Docker SWE-bench harness. It is the smallest
    local executor that exercises the same evaluation contract: copy a repo,
    apply the regression-test patch, apply a candidate patch, run tests, and
    retain execution evidence for hydration/replay.
    """

    def __init__(self, instances: list[SweBenchInstance]):
        self.instances = list(instances)

    @classmethod
    def demo(cls, source_repo_root: str | Path) -> "SweBenchLocalPatchExecutor":
        return cls(cls.demo_instances(source_repo_root))

    @classmethod
    def from_jsonl(cls, path: str | Path, *, limit: int | None = None) -> "SweBenchLocalPatchExecutor":
        return cls(SweBenchSmallSubsetAdapter.from_jsonl(path, limit=limit).instances)

    @staticmethod
    def demo_instances(source_repo_root: str | Path) -> list[SweBenchInstance]:
        root = Path(source_repo_root)
        calc_repo = root / "calculator_repo"
        parser_repo = root / "parser_repo"
        SweBenchLocalPatchExecutor._write_demo_repo(
            calc_repo,
            files={
                "calculator.py": "def add(a, b):\n    return a - b\n",
                "test_calculator.py": (
                    "import unittest\n"
                    "from calculator import add\n\n"
                    "class CalculatorTests(unittest.TestCase):\n"
                    "    def test_identity(self):\n"
                    "        self.assertEqual(add(2, 0), 2)\n\n"
                    "if __name__ == '__main__':\n"
                    "    unittest.main()\n"
                ),
            },
        )
        SweBenchLocalPatchExecutor._write_demo_repo(
            parser_repo,
            files={
                "parser.py": "def matches(token, expected):\n    return token == expected\n",
                "test_parser.py": (
                    "import unittest\n"
                    "from parser import matches\n\n"
                    "class ParserTests(unittest.TestCase):\n"
                    "    def test_exact(self):\n"
                    "        self.assertTrue(matches('ok', 'ok'))\n\n"
                    "if __name__ == '__main__':\n"
                    "    unittest.main()\n"
                ),
            },
        )

        command = [sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"]
        return [
            SweBenchInstance(
                instance_id="executor__calculator-001",
                repo="local/calculator",
                base_commit="local-demo-calc",
                problem_statement="The add helper subtracts its second argument.",
                patch=(
                    "diff --git a/calculator.py b/calculator.py\n"
                    "--- a/calculator.py\n"
                    "+++ b/calculator.py\n"
                    "@@ -1,2 +1,2 @@\n"
                    " def add(a, b):\n"
                    "-    return a - b\n"
                    "+    return a + b\n"
                ),
                test_patch=(
                    "diff --git a/test_calculator.py b/test_calculator.py\n"
                    "--- a/test_calculator.py\n"
                    "+++ b/test_calculator.py\n"
                    "@@ -4,6 +4,9 @@\n"
                    " class CalculatorTests(unittest.TestCase):\n"
                    "     def test_identity(self):\n"
                    "         self.assertEqual(add(2, 0), 2)\n"
                    " \n"
                    "+    def test_add_regression(self):\n"
                    "+        self.assertEqual(add(1, 2), 3)\n"
                    "+\n"
                    " if __name__ == '__main__':\n"
                    "     unittest.main()\n"
                ),
                candidate_patch=(
                    "diff --git a/calculator.py b/calculator.py\n"
                    "--- a/calculator.py\n"
                    "+++ b/calculator.py\n"
                    "@@ -1,2 +1,2 @@\n"
                    " def add(a, b):\n"
                    "-    return a - b\n"
                    "+    return a + b\n"
                ),
                fail_to_pass=["test_calculator.py::CalculatorTests::test_add_regression"],
                source_refs=[
                    "https://www.swebench.com/swebench-verified.html",
                    "https://labs.scale.com/leaderboard/swe_bench_pro_public",
                ],
                metadata={
                    "local_repo_path": str(calc_repo),
                    "test_command": command,
                    "execution_timeout_s": 10,
                },
            ),
            SweBenchInstance(
                instance_id="executor__parser-002",
                repo="local/parser",
                base_commit="local-demo-parser",
                problem_statement="The parser should strip whitespace before comparing tokens.",
                patch=(
                    "diff --git a/parser.py b/parser.py\n"
                    "--- a/parser.py\n"
                    "+++ b/parser.py\n"
                    "@@ -1,2 +1,2 @@\n"
                    " def matches(token, expected):\n"
                    "-    return token == expected\n"
                    "+    return token.strip() == expected\n"
                ),
                test_patch=(
                    "diff --git a/test_parser.py b/test_parser.py\n"
                    "--- a/test_parser.py\n"
                    "+++ b/test_parser.py\n"
                    "@@ -4,6 +4,9 @@\n"
                    " class ParserTests(unittest.TestCase):\n"
                    "     def test_exact(self):\n"
                    "         self.assertTrue(matches('ok', 'ok'))\n"
                    " \n"
                    "+    def test_strip_regression(self):\n"
                    "+        self.assertTrue(matches(' ok ', 'ok'))\n"
                    "+\n"
                    " if __name__ == '__main__':\n"
                    "     unittest.main()\n"
                ),
                candidate_patch=(
                    "diff --git a/parser.py b/parser.py\n"
                    "--- a/parser.py\n"
                    "+++ b/parser.py\n"
                    "@@ -1,2 +1,2 @@\n"
                    " def matches(token, expected):\n"
                    "-    return token == expected\n"
                    "+    return token.lower() == expected\n"
                ),
                fail_to_pass=["test_parser.py::ParserTests::test_strip_regression"],
                source_refs=[
                    "https://www.swebench.com/swebench-verified.html",
                    "https://labs.scale.com/leaderboard/swe_bench_pro_public",
                    "https://software-lab.org/publications/icse2026_SWE-bench-correctness.pdf",
                ],
                metadata={
                    "local_repo_path": str(parser_repo),
                    "test_command": command,
                    "execution_timeout_s": 10,
                },
            ),
        ]

    def run(self, workspace_root: str | Path) -> SweBenchExecutorRunReport:
        root = Path(workspace_root)
        root.mkdir(parents=True, exist_ok=True)
        results = [self._run_instance(root, instance) for instance in self.instances]
        failures = [failure for result in results for failure in result.failures]
        warnings = [warning for result in results for warning in result.warnings]
        payload = {
            "workspace_root": str(root),
            "instances": [instance.to_dict() for instance in self.instances],
            "results": [
                {
                    key: value
                    for key, value in result.to_dict().items()
                    if key not in {"duration_s"}
                }
                for result in results
            ],
        }
        return SweBenchExecutorRunReport(
            ready_for_swebench_executor=not failures and bool(results),
            instance_count=len(results),
            success_count=sum(1 for result in results if result.success),
            tests_passed_count=sum(1 for result in results if result.tests_passed),
            hydration_safe_count=sum(1 for result in results if result.hydration_safe),
            evidence_sound_count=sum(1 for result in results if result.evidence_ledger_sound),
            phase_gate_passed_count=sum(1 for result in results if result.phase_gate_passed),
            candidate_patch_equal_count=sum(1 for result in results if result.patch_equal_to_gold),
            oracle_audit_sound_count=sum(1 for result in results if result.oracle_audit_sound),
            artifact_count=sum(len(result.artifact_uris) for result in results),
            mean_patch_line_jaccard=self._mean([result.patch_line_jaccard for result in results]),
            mean_behavioral_divergence_score=self._mean(
                [result.behavioral_divergence_score for result in results]
            ),
            mean_duration_s=self._mean([result.duration_s for result in results]),
            failures=failures,
            warnings=warnings,
            run_fingerprint=_stable_hash(payload),
            instance_results=results,
        )

    def _run_instance(self, workspace_root: Path, instance: SweBenchInstance) -> SweBenchExecutionResult:
        task_root = workspace_root / _safe_name(instance.instance_id)
        artifact_root = task_root / "artifacts"
        repo_workspace = task_root / "repo"
        failures = self._instance_failures(instance)
        warnings: list[str] = []
        repo_source = self._repo_source(instance)
        command = self._test_command(instance)
        timeout_s = int(instance.metadata.get("execution_timeout_s") or 30)
        candidate_patch = instance.candidate_patch or instance.patch
        patch_equal_to_gold = _normalize_patch(candidate_patch) == _normalize_patch(instance.patch)
        patch_line_jaccard = round(_jaccard(_patch_line_set(candidate_patch), _patch_line_set(instance.patch)), 4)
        changed_file_overlap = round(_jaccard(_changed_files(candidate_patch), _changed_files(instance.patch)), 4)
        behavioral_divergence_score = round(1.0 - ((0.7 * patch_line_jaccard) + (0.3 * changed_file_overlap)), 4)

        if repo_source is None:
            failures.append(f"{instance.instance_id}: missing local_repo_path metadata")
        elif not repo_source.is_dir():
            failures.append(f"{instance.instance_id}: local repo path does not exist: {repo_source}")
        if command is None:
            failures.append(f"{instance.instance_id}: missing test_command metadata")

        if not failures:
            if repo_workspace.exists():
                shutil.rmtree(repo_workspace)
            shutil.copytree(
                repo_source,
                repo_workspace,
                ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"),
            )

        instance_hash = _write_json(artifact_root / "swebench_instance.json", instance.to_dict())
        gold_hash = _write_text(artifact_root / "gold.patch", instance.patch)
        candidate_hash = _write_text(artifact_root / "candidate.patch", candidate_patch)
        test_patch_hash = _write_text(artifact_root / "test.patch", instance.test_patch)
        applied_test_patch = False
        applied_candidate_patch = False
        test_exit_code: int | None = None
        stdout_text = ""
        stderr_text = ""
        duration_s = 0.0

        if not failures:
            applied_test_patch, test_apply_stdout, test_apply_stderr = self._apply_patch(
                repo_workspace,
                artifact_root / "test.patch",
            )
            stdout_text += test_apply_stdout
            stderr_text += test_apply_stderr
            if not applied_test_patch:
                failures.append(f"{instance.instance_id}: failed to apply test_patch")

        if not failures:
            applied_candidate_patch, candidate_apply_stdout, candidate_apply_stderr = self._apply_patch(
                repo_workspace,
                artifact_root / "candidate.patch",
            )
            stdout_text += candidate_apply_stdout
            stderr_text += candidate_apply_stderr
            if not applied_candidate_patch:
                failures.append(f"{instance.instance_id}: failed to apply candidate_patch")

        if not failures and command is not None:
            started = time.perf_counter()
            try:
                completed = subprocess.run(
                    command,
                    cwd=repo_workspace,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout_s,
                    check=False,
                    shell=isinstance(command, str),
                )
                duration_s = round(time.perf_counter() - started, 4)
                test_exit_code = completed.returncode
                stdout_text += completed.stdout
                stderr_text += completed.stderr
            except subprocess.TimeoutExpired as exc:
                duration_s = round(time.perf_counter() - started, 4)
                test_exit_code = None
                stdout_text += str(exc.stdout or "")
                stderr_text += str(exc.stderr or "")
                failures.append(f"{instance.instance_id}: test command timed out after {timeout_s}s")

        tests_passed = test_exit_code == 0

        oracle_environment = {
            "local_repo_path": str(repo_source) if repo_source is not None else "",
            "repo_workspace_fingerprint": _directory_fingerprint(repo_workspace),
            "command": command,
            "timeout_s": timeout_s,
            "applied_test_patch": applied_test_patch,
            "applied_candidate_patch": applied_candidate_patch,
            "tests_passed": tests_passed,
        }
        oracle_audit = self._oracle_audit_report(
            instance,
            candidate_patch=candidate_patch,
            environment=oracle_environment,
        )

        stdout_hash = _write_text(artifact_root / "stdout.txt", stdout_text)
        stderr_hash = _write_text(artifact_root / "stderr.txt", stderr_text)
        execution_payload = {
            "instance_id": instance.instance_id,
            "repo": instance.repo,
            "base_commit": instance.base_commit,
            "command": command,
            "test_exit_code": test_exit_code,
            "tests_passed": tests_passed,
            "applied_test_patch": applied_test_patch,
            "applied_candidate_patch": applied_candidate_patch,
            "patch_equal_to_gold": patch_equal_to_gold,
            "changed_file_overlap": changed_file_overlap,
            "patch_line_jaccard": patch_line_jaccard,
            "behavioral_divergence_score": behavioral_divergence_score,
            "fail_to_pass": list(instance.fail_to_pass),
            "pass_to_pass": list(instance.pass_to_pass),
            "duration_s": duration_s,
            "oracle_audit_fingerprint": oracle_audit.oracle_fingerprint,
        }
        execution_hash = _write_json(artifact_root / "execution_report.json", execution_payload)
        oracle_hash = _write_json(artifact_root / "oracle_audit_report.json", oracle_audit.to_dict())
        artifact_refs = [
            ArtifactRef(kind="swebench_executor_instance", uri=str(artifact_root / "swebench_instance.json"), sha256=instance_hash),
            ArtifactRef(kind="swebench_executor_gold_patch", uri=str(artifact_root / "gold.patch"), sha256=gold_hash),
            ArtifactRef(kind="swebench_executor_candidate_patch", uri=str(artifact_root / "candidate.patch"), sha256=candidate_hash),
            ArtifactRef(kind="swebench_executor_test_patch", uri=str(artifact_root / "test.patch"), sha256=test_patch_hash),
            ArtifactRef(kind="swebench_executor_stdout", uri=str(artifact_root / "stdout.txt"), sha256=stdout_hash),
            ArtifactRef(kind="swebench_executor_stderr", uri=str(artifact_root / "stderr.txt"), sha256=stderr_hash),
            ArtifactRef(kind="swebench_executor_report", uri=str(artifact_root / "execution_report.json"), sha256=execution_hash),
            ArtifactRef(kind="swebench_executor_oracle_audit", uri=str(artifact_root / "oracle_audit_report.json"), sha256=oracle_hash),
            ArtifactRef(kind="swebench_executor_repo_workspace", uri=str(repo_workspace), metadata={"directory": True}),
        ]
        evidence_ledger = self._evidence_ledger(instance, artifact_refs)
        evidence_report = evidence_ledger.evaluate(required_claim_ids=self._claim_ids(instance))
        memory_protocol = MemoryCommitProtocol()
        memory_commit = self._commit_memory(
            instance,
            memory_protocol,
            artifact_refs,
            evidence_sound=evidence_report.sound,
            execution_payload=execution_payload,
        )
        research_session = self._research_session(instance, artifact_refs, memory_commit.committed_record_ids)
        research_report = ResearchSessionVerifier().evaluate(
            research_session,
            phase_gates=[
                ResearchPhaseGate(
                    phase=ResearchPhase.WRITEUP,
                    required_artifact_kinds=[
                        "swebench_executor_candidate_patch",
                        "swebench_executor_test_patch",
                        "swebench_executor_report",
                        "swebench_executor_oracle_audit",
                    ],
                    required_transition_labels=[
                        "copy_repo",
                        "apply_test_patch",
                        "apply_candidate_patch",
                        "run_tests",
                    ],
                    required_memory_record_ids=list(memory_commit.committed_record_ids),
                    required_evidence_claim_ids=self._claim_ids(instance),
                    require_validation_receipt=True,
                    require_review_ref=True,
                )
            ],
            evidence_ledger=evidence_ledger,
        )
        trace_events = self._trace_events(instance, artifact_refs, execution_payload)
        state = RuntimeState(
            task_id=f"swebench-executor::{instance.instance_id}",
            session_id=f"swebench-executor-session::{instance.instance_id}",
            run_id=f"swebench-executor-run::{instance.instance_id}",
            goal=instance.problem_statement,
            execution_cursor="after:swebench_local_execution",
            active_step="writeup",
            process_stage="active",
            policy_snapshot={
                "dataset": "swe-bench-style",
                "executor": "local-patch",
                "test_command": command,
                "timeout_s": timeout_s,
            },
            artifact_refs=list(artifact_refs),
            metadata={
                "repo": instance.repo,
                "base_commit": instance.base_commit,
                "tests_passed": tests_passed,
                "test_exit_code": test_exit_code,
                "active_evidence_ledger": {
                    "name": "swebench-local-executor-ledger",
                    "fingerprint": evidence_ledger.fingerprint(),
                    "claim_ids": self._claim_ids(instance),
                },
            },
        )
        hydration_builder = HydrationManifestBuilder()
        hydration_manifest = hydration_builder.dehydrate(
            state,
            trace_events,
            memory_records=list(memory_protocol.records.values()),
            evidence_ledger=evidence_ledger,
            research_session=research_session,
            required_memory_record_ids=list(memory_commit.committed_record_ids),
            required_evidence_claim_ids=self._claim_ids(instance),
            required_artifact_uris=[artifact.uri for artifact in artifact_refs],
        )
        hydration_report = hydration_builder.verify(
            hydration_manifest,
            state,
            trace_events,
            memory_records=list(memory_protocol.records.values()),
            evidence_ledger=evidence_ledger,
            research_session=research_session,
        )
        failures.extend(evidence_report.failures)
        failures.extend(oracle_audit.failures)
        failures.extend(memory_commit.failures)
        failures.extend(research_report.failures)
        failures.extend(hydration_report.failures)
        warnings.extend(evidence_report.warnings)
        warnings.extend(oracle_audit.warnings)
        warnings.extend(research_report.warnings)
        warnings.extend(hydration_report.warnings)
        success = (
            not failures
            and applied_test_patch
            and applied_candidate_patch
            and oracle_audit.sound
            and evidence_report.sound
            and research_report.phase_gate_passed
            and hydration_report.safe_to_hydrate
        )
        payload = {
            "instance": instance.to_dict(),
            "execution": {
                key: value
                for key, value in execution_payload.items()
                if key != "duration_s"
            },
            "oracle_audit": oracle_audit.to_dict(),
            "artifacts": [asdict(ref) for ref in artifact_refs],
            "evidence_report": evidence_report.to_dict(),
            "memory_commit": memory_commit.to_dict(),
            "research_report": research_report.to_dict(),
            "hydration_report": hydration_report.to_dict(),
        }
        return SweBenchExecutionResult(
            instance_id=instance.instance_id,
            repo=instance.repo,
            success=success,
            tests_passed=tests_passed,
            test_exit_code=test_exit_code,
            command=command or [],
            duration_s=duration_s,
            workspace_ref=str(task_root),
            repo_workspace_ref=str(repo_workspace),
            artifact_uris=[artifact.uri for artifact in artifact_refs],
            evidence_claim_ids=self._claim_ids(instance),
            committed_memory_record_ids=list(memory_commit.committed_record_ids),
            applied_test_patch=applied_test_patch,
            applied_candidate_patch=applied_candidate_patch,
            patch_equal_to_gold=patch_equal_to_gold,
            changed_file_overlap=changed_file_overlap,
            patch_line_jaccard=patch_line_jaccard,
            behavioral_divergence_score=behavioral_divergence_score,
            oracle_audit_sound=oracle_audit.sound,
            evidence_ledger_sound=evidence_report.sound,
            phase_gate_passed=research_report.phase_gate_passed,
            hydration_safe=hydration_report.safe_to_hydrate,
            failures=failures,
            warnings=warnings,
            result_fingerprint=_stable_hash(payload),
        )

    @staticmethod
    def _write_demo_repo(repo_root: Path, *, files: dict[str, str]) -> None:
        if repo_root.exists():
            shutil.rmtree(repo_root)
        for relative_path, content in files.items():
            _write_text(repo_root / relative_path, content)

    @staticmethod
    def _apply_patch(repo_workspace: Path, patch_path: Path) -> tuple[bool, str, str]:
        before_fingerprint = _directory_fingerprint(repo_workspace)
        env = os.environ.copy()
        env["GIT_CEILING_DIRECTORIES"] = str(repo_workspace.parent)
        completed = subprocess.run(
            ["git", "apply", str(patch_path)],
            cwd=repo_workspace,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        after_fingerprint = _directory_fingerprint(repo_workspace)
        changed = before_fingerprint != after_fingerprint
        if completed.returncode == 0 and not changed:
            return (
                False,
                completed.stdout,
                completed.stderr + f"\npatch produced no workspace changes: {patch_path}",
            )
        return completed.returncode == 0 and changed, completed.stdout, completed.stderr

    @staticmethod
    def _repo_source(instance: SweBenchInstance) -> Path | None:
        raw = instance.metadata.get("local_repo_path") or instance.metadata.get("repo_path")
        return Path(str(raw)).resolve() if raw else None

    @staticmethod
    def _test_command(instance: SweBenchInstance) -> list[str] | str | None:
        command = instance.metadata.get("test_command")
        if command is None:
            return None
        if isinstance(command, list):
            return [str(part) for part in command]
        return str(command)

    def _oracle_audit_report(
        self,
        instance: SweBenchInstance,
        *,
        candidate_patch: str,
        environment: JsonDict | None = None,
    ) -> SweBenchOracleAuditReport:
        return SweBenchSmallSubsetAdapter([instance])._oracle_audit_report(
            instance,
            candidate_patch=candidate_patch,
            environment=environment,
        )

    def _instance_failures(self, instance: SweBenchInstance) -> list[str]:
        return SweBenchSmallSubsetAdapter([instance])._instance_failures(instance)

    def _evidence_ledger(self, instance: SweBenchInstance, artifact_refs: list[ArtifactRef]) -> EvidenceLedger:
        entries = [
            EvidenceEntry(
                entry_id=f"{self._entry_prefix(instance)}-exec-{index}",
                kind=EvidenceKind.ARTIFACT,
                source_ref=artifact.uri,
                content_hash=artifact.sha256 or "",
                labels=[artifact.kind, "swebench-style", "local-executor"],
                metadata={"instance_id": instance.instance_id, "repo": instance.repo},
            )
            for index, artifact in enumerate(artifact_refs)
        ]
        by_kind = {
            artifact.kind: entries[index].entry_id
            for index, artifact in enumerate(artifact_refs)
        }
        claims = [
            EvidenceClaim(
                claim_id=self._claim_ids(instance)[0],
                statement="The local executor copied a repository workspace for this SWE-bench-style instance.",
                cited_entry_ids=[
                    by_kind["swebench_executor_instance"],
                    by_kind["swebench_executor_repo_workspace"],
                ],
                required_labels=["swebench_executor_instance", "swebench_executor_repo_workspace"],
            ),
            EvidenceClaim(
                claim_id=self._claim_ids(instance)[1],
                statement="The regression-test patch and candidate patch were materialized for local execution.",
                cited_entry_ids=[
                    by_kind["swebench_executor_test_patch"],
                    by_kind["swebench_executor_candidate_patch"],
                ],
                required_labels=["swebench_executor_test_patch", "swebench_executor_candidate_patch"],
            ),
            EvidenceClaim(
                claim_id=self._claim_ids(instance)[2],
                statement="The local executor captured command output and an execution report.",
                cited_entry_ids=[
                    by_kind["swebench_executor_stdout"],
                    by_kind["swebench_executor_stderr"],
                    by_kind["swebench_executor_report"],
                ],
                required_labels=["swebench_executor_report"],
            ),
            EvidenceClaim(
                claim_id=self._claim_ids(instance)[3],
                statement="The executable benchmark oracle, repo workspace, and test environment were audited and fingerprinted.",
                cited_entry_ids=[
                    by_kind["swebench_executor_instance"],
                    by_kind["swebench_executor_test_patch"],
                    by_kind["swebench_executor_report"],
                    by_kind["swebench_executor_oracle_audit"],
                    by_kind["swebench_executor_repo_workspace"],
                ],
                required_labels=["swebench_executor_oracle_audit", "swebench_executor_repo_workspace"],
            ),
        ]
        return EvidenceLedger(entries=entries, claims=claims)

    def _commit_memory(
        self,
        instance: SweBenchInstance,
        memory_protocol: MemoryCommitProtocol,
        artifact_refs: list[ArtifactRef],
        *,
        evidence_sound: bool,
        execution_payload: JsonDict,
    ):
        tx = memory_protocol.begin_transaction(
            transaction_id=f"tx-swebench-executor-{_safe_name(instance.instance_id)}",
            checkpoint_version=1,
            metadata={"dataset": "swe-bench-style", "executor": "local-patch"},
        )
        record = memory_protocol.stage_record(
            tx.transaction_id,
            record_id=f"memory-swebench-executor-{_safe_name(instance.instance_id)}",
            kind=MemoryKind.ARTIFACT,
            payload={
                "instance_id": instance.instance_id,
                "repo": instance.repo,
                "test_exit_code": execution_payload["test_exit_code"],
                "tests_passed": execution_payload["tests_passed"],
                "patch_line_jaccard": execution_payload["patch_line_jaccard"],
                "behavioral_divergence_score": execution_payload["behavioral_divergence_score"],
                "claim": "SWE-bench-style local executor produced test execution evidence.",
            },
            source_refs=[artifact.uri for artifact in artifact_refs],
        )
        memory_protocol.validate_record(
            record.record_id,
            ValidationReceipt(
                validator="swebench-local-patch-executor",
                passed=evidence_sound and execution_payload["applied_test_patch"] and execution_payload["applied_candidate_patch"],
                reasons=[
                    "evidence ledger sound" if evidence_sound else "evidence ledger failed",
                    "test patch applied" if execution_payload["applied_test_patch"] else "test patch failed",
                    "candidate patch applied" if execution_payload["applied_candidate_patch"] else "candidate patch failed",
                    "test command completed" if execution_payload["test_exit_code"] is not None else "test command did not complete",
                ],
                evidence_refs=[artifact.uri for artifact in artifact_refs],
                checkpoint_version=1,
                metadata={
                    "instance_id": instance.instance_id,
                    "tests_passed": execution_payload["tests_passed"],
                    "test_exit_code": execution_payload["test_exit_code"],
                },
            ),
        )
        return memory_protocol.commit(tx.transaction_id, checkpoint_version=2)

    def _research_session(
        self,
        instance: SweBenchInstance,
        artifact_refs: list[ArtifactRef],
        committed_record_ids: list[str],
    ) -> ResearchSession:
        session = ResearchSession(
            session_id=f"swebench-executor-research::{instance.instance_id}",
            runtime_task_id=f"swebench-executor::{instance.instance_id}",
            goal=instance.problem_statement,
            policy_snapshot_hash=_stable_hash({"executor": "swebench-local-patch", "instance_id": instance.instance_id}),
            metadata={"repo": instance.repo, "base_commit": instance.base_commit},
        )
        labels = ["copy_repo", "apply_test_patch", "apply_candidate_patch", "run_tests"]
        claim_refs = [f"claim://{claim_id}" for claim_id in self._claim_ids(instance)]
        session.advance_to(ResearchPhase.PAPER_SCAN, evidence_refs=claim_refs[:1], transition_labels=[labels[0]])
        session.advance_to(ResearchPhase.HYPOTHESIS)
        session.advance_to(ResearchPhase.EXPERIMENT_PLAN, transition_labels=labels[:2])
        session.advance_to(
            ResearchPhase.EXPERIMENT_RUN,
            artifact_refs=list(artifact_refs),
            evidence_refs=claim_refs,
            transition_labels=labels,
            memory_record_ids=list(committed_record_ids),
            validation_receipt_refs=[f"receipt://swebench-executor/{instance.instance_id}/local-execution"],
        )
        session.advance_to(ResearchPhase.ANALYSIS, transition_labels=[labels[-1]])
        session.advance_to(ResearchPhase.REVIEW, review_refs=[f"review://swebench-executor/{instance.instance_id}/local-execution"])
        session.advance_to(ResearchPhase.WRITEUP)
        return session

    def _trace_events(
        self,
        instance: SweBenchInstance,
        artifact_refs: list[ArtifactRef],
        execution_payload: JsonDict,
    ) -> list[TraceEvent]:
        events: list[TraceEvent] = []
        labels = ["copy_repo", "apply_test_patch", "apply_candidate_patch", "run_tests"]
        for index, label in enumerate(labels):
            envelope = {
                "schema_version": "trace-envelope-v2",
                "boundary": TraceBoundary.TOOL,
                "task_id": f"swebench-executor::{instance.instance_id}",
                "run_id": f"swebench-executor-run::{instance.instance_id}",
                "cursor": f"swebench-executor:{index}",
                "provider_name": "swebench-local-patch-executor",
                "provider_fingerprint": _stable_hash({"provider": "swebench-local-patch-executor"})[:12],
                "policy_fingerprint": _stable_hash({"dataset": "swe-bench-style", "executor": "local-patch"})[:12],
                "action_name": label,
                "action_effect": "execute",
                "input_hash": hash_payload({"instance_id": instance.instance_id, "label": label}),
                "output_hash": hash_payload({
                    "instance_id": instance.instance_id,
                    "label": label,
                    "tests_passed": execution_payload["tests_passed"],
                    "test_exit_code": execution_payload["test_exit_code"],
                }),
                "evidence_ledger_fingerprint": _stable_hash({"claim_ids": self._claim_ids(instance)})[:12],
                "evidence_claim_ids": self._claim_ids(instance),
                "artifact_refs": [artifact.uri for artifact in artifact_refs],
                "receipts": [],
            }
            envelope["trace_envelope_fingerprint"] = hash_payload(envelope)
            events.append(
                TraceEvent(
                    event_id=f"swebench-executor-{_safe_name(instance.instance_id)}-{index}",
                    task_id=f"swebench-executor::{instance.instance_id}",
                    run_id=f"swebench-executor-run::{instance.instance_id}",
                    cursor=f"swebench-executor:{index}",
                    kind="tool_completed",
                    data={
                        "tool": label,
                        "args_hash": envelope["input_hash"],
                        "output_hash": envelope["output_hash"],
                        "artifact_refs": [artifact.uri for artifact in artifact_refs],
                        "execution": execution_payload,
                        "trace_envelope": envelope,
                        "trace_envelope_fingerprint": envelope["trace_envelope_fingerprint"],
                    },
                )
            )
        return events

    def _claim_ids(self, instance: SweBenchInstance) -> list[str]:
        prefix = self._entry_prefix(instance)
        return [
            f"claim-{prefix}-executor-repo-bound",
            f"claim-{prefix}-executor-patches-applied",
            f"claim-{prefix}-executor-tests-captured",
            f"claim-{prefix}-executor-oracle-audited",
        ]

    def _entry_prefix(self, instance: SweBenchInstance) -> str:
        return _safe_name(instance.instance_id).lower()

    def _mean(self, values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)
