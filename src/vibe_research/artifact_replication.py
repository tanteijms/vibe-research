from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
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


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value).strip("_") or "artifact"


def _write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return _sha256_path(path)


def _write_json(path: Path, payload: object) -> str:
    return _write_text(path, json.dumps(payload, indent=2, sort_keys=True, default=str))


def _directory_fingerprint(path: Path) -> str:
    if not path.exists():
        return ""
    files: list[dict[str, str]] = []
    for child in sorted(p for p in path.rglob("*") if p.is_file()):
        relative = child.relative_to(path).as_posix()
        if "__pycache__" in child.parts or ".git" in child.parts:
            continue
        files.append({"path": relative, "sha256": _sha256_path(child)})
    return _stable_hash(files)


@dataclass(frozen=True, slots=True)
class ArtifactReplicationPackageSpec:
    package_id: str
    paper_title: str
    artifact_root: str
    run_command: list[str] | str
    expected_artifacts: list[str]
    expected_metric_files: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    timeout_s: int = 60
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_manifest(cls, path: str | Path) -> "ArtifactReplicationPackageSpec":
        manifest_path = Path(path).resolve()
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("artifact replication manifest must contain a JSON object")
        artifact_root = Path(str(payload.get("artifact_root", "")))
        if not artifact_root.is_absolute():
            artifact_root = manifest_path.parent / artifact_root
        run_command = payload.get("run_command")
        if not isinstance(run_command, (list, str)):
            raise ValueError("artifact replication manifest must define run_command as a list or string")
        return cls(
            package_id=str(payload.get("package_id") or manifest_path.stem),
            paper_title=str(payload.get("paper_title") or "Untitled artifact package"),
            artifact_root=str(artifact_root.resolve()),
            run_command=[str(part) for part in run_command] if isinstance(run_command, list) else str(run_command),
            expected_artifacts=[str(item) for item in payload.get("expected_artifacts", [])],
            expected_metric_files=[str(item) for item in payload.get("expected_metric_files", [])],
            source_refs=[str(item) for item in payload.get("source_refs", [])],
            timeout_s=int(payload.get("timeout_s") or 60),
            notes=[str(item) for item in payload.get("notes", [])],
        )


@dataclass(frozen=True, slots=True)
class ArtifactReplicationResult:
    package_id: str
    paper_title: str
    success: bool
    command_exit_code: int | None
    command: list[str] | str
    duration_s: float
    workspace_ref: str
    package_workspace_ref: str
    expected_artifact_count: int
    expected_artifact_found_count: int
    missing_expected_artifacts: list[str]
    metric_file_count: int
    artifact_uris: list[str]
    evidence_claim_ids: list[str]
    committed_memory_record_ids: list[str]
    evidence_ledger_sound: bool
    phase_gate_passed: bool
    hydration_safe: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    result_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ArtifactReplicationRunReport:
    ready_for_real_artifact_replication: bool
    package_count: int
    success_count: int
    command_completed_count: int
    hydration_safe_count: int
    evidence_sound_count: int
    phase_gate_passed_count: int
    artifact_count: int
    metric_file_count: int
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    run_fingerprint: str = ""
    package_results: list[ArtifactReplicationResult] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        data["package_results"] = [result.to_dict() for result in self.package_results]
        return data

    @classmethod
    def empty(cls) -> "ArtifactReplicationRunReport":
        return cls(
            ready_for_real_artifact_replication=False,
            package_count=0,
            success_count=0,
            command_completed_count=0,
            hydration_safe_count=0,
            evidence_sound_count=0,
            phase_gate_passed_count=0,
            artifact_count=0,
            metric_file_count=0,
            warnings=["no real artifact replication manifest supplied"],
            run_fingerprint=_stable_hash({"package_results": []}),
            package_results=[],
        )


class ArtifactReplicationPackageIngestor:
    """Runs real paper artifact packages through the same evidence/hydration contract.

    The ingestor is manifest-driven so a future FSE/ICSE/ASE artifact can be
    connected without rewriting the benchmark scaffold. It does not mark a run
    as submission-grade unless an actual manifest is supplied and the package
    executes successfully.
    """

    def __init__(self, packages: list[ArtifactReplicationPackageSpec]):
        self.packages = list(packages)

    @classmethod
    def from_manifest_paths(cls, paths: list[str | Path]) -> "ArtifactReplicationPackageIngestor":
        return cls([ArtifactReplicationPackageSpec.from_manifest(path) for path in paths])

    def run(self, workspace_root: str | Path) -> ArtifactReplicationRunReport:
        if not self.packages:
            return ArtifactReplicationRunReport.empty()
        root = Path(workspace_root)
        root.mkdir(parents=True, exist_ok=True)
        results = [self._run_package(root, package) for package in self.packages]
        failures = [failure for result in results for failure in result.failures]
        warnings = [warning for result in results for warning in result.warnings]
        payload = {
            "workspace_root": str(root),
            "packages": [package.to_dict() for package in self.packages],
            "results": [
                {
                    key: value
                    for key, value in result.to_dict().items()
                    if key != "duration_s"
                }
                for result in results
            ],
        }
        return ArtifactReplicationRunReport(
            ready_for_real_artifact_replication=not failures and bool(results),
            package_count=len(results),
            success_count=sum(1 for result in results if result.success),
            command_completed_count=sum(1 for result in results if result.command_exit_code == 0),
            hydration_safe_count=sum(1 for result in results if result.hydration_safe),
            evidence_sound_count=sum(1 for result in results if result.evidence_ledger_sound),
            phase_gate_passed_count=sum(1 for result in results if result.phase_gate_passed),
            artifact_count=sum(len(result.artifact_uris) for result in results),
            metric_file_count=sum(result.metric_file_count for result in results),
            failures=failures,
            warnings=warnings,
            run_fingerprint=_stable_hash(payload),
            package_results=results,
        )

    def _run_package(self, workspace_root: Path, package: ArtifactReplicationPackageSpec) -> ArtifactReplicationResult:
        package_root = Path(package.artifact_root)
        task_root = workspace_root / _safe_name(package.package_id)
        package_workspace = task_root / "package"
        artifact_root = task_root / "artifacts"
        failures: list[str] = []
        warnings: list[str] = []
        if not package.package_id.strip():
            failures.append("missing package_id")
        if not package_root.is_dir():
            failures.append(f"{package.package_id}: artifact_root does not exist: {package_root}")
        if not package.expected_artifacts:
            warnings.append(f"{package.package_id}: no expected_artifacts listed")
        if not package.source_refs:
            warnings.append(f"{package.package_id}: no source_refs listed for paper/artifact provenance")

        if not failures:
            if package_workspace.exists():
                shutil.rmtree(package_workspace)
            shutil.copytree(package_root, package_workspace, ignore=shutil.ignore_patterns(".git", "__pycache__"))

        manifest_hash = _write_json(artifact_root / "artifact_replication_manifest.json", package.to_dict())
        stdout_text = ""
        stderr_text = ""
        command_exit_code: int | None = None
        duration_s = 0.0
        before_fingerprint = _directory_fingerprint(package_workspace)
        after_fingerprint = before_fingerprint
        if not failures:
            started = time.perf_counter()
            try:
                completed = subprocess.run(
                    package.run_command,
                    cwd=package_workspace,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=package.timeout_s,
                    check=False,
                    shell=isinstance(package.run_command, str),
                )
                duration_s = round(time.perf_counter() - started, 4)
                command_exit_code = completed.returncode
                stdout_text = completed.stdout
                stderr_text = completed.stderr
                after_fingerprint = _directory_fingerprint(package_workspace)
                if command_exit_code != 0:
                    failures.append(f"{package.package_id}: run_command exited with {command_exit_code}")
            except subprocess.TimeoutExpired as exc:
                duration_s = round(time.perf_counter() - started, 4)
                stdout_text = str(exc.stdout or "")
                stderr_text = str(exc.stderr or "")
                failures.append(f"{package.package_id}: run_command timed out after {package.timeout_s}s")

        stdout_hash = _write_text(artifact_root / "stdout.txt", stdout_text)
        stderr_hash = _write_text(artifact_root / "stderr.txt", stderr_text)
        missing_expected_artifacts: list[str] = []
        expected_refs: list[ArtifactRef] = []
        for expected in package.expected_artifacts:
            expected_path = package_workspace / expected
            if expected_path.exists() and expected_path.is_file():
                expected_refs.append(
                    ArtifactRef(
                        kind="replicated_artifact",
                        uri=str(expected_path),
                        sha256=_sha256_path(expected_path),
                        metadata={"relative_path": expected},
                    )
                )
            else:
                missing_expected_artifacts.append(expected)
        if missing_expected_artifacts:
            failures.append(
                f"{package.package_id}: missing expected artifacts: {', '.join(missing_expected_artifacts)}"
            )
        metric_file_count = sum(1 for relative in package.expected_metric_files if (package_workspace / relative).is_file())
        execution_payload = {
            "package_id": package.package_id,
            "paper_title": package.paper_title,
            "command": package.run_command,
            "command_exit_code": command_exit_code,
            "duration_s": duration_s,
            "before_workspace_fingerprint": before_fingerprint,
            "after_workspace_fingerprint": after_fingerprint,
            "expected_artifacts": list(package.expected_artifacts),
            "missing_expected_artifacts": list(missing_expected_artifacts),
            "metric_file_count": metric_file_count,
            "source_refs": list(package.source_refs),
        }
        execution_hash = _write_json(artifact_root / "execution_report.json", execution_payload)
        artifact_refs = [
            ArtifactRef(kind="artifact_replication_manifest", uri=str(artifact_root / "artifact_replication_manifest.json"), sha256=manifest_hash),
            ArtifactRef(kind="replication_stdout", uri=str(artifact_root / "stdout.txt"), sha256=stdout_hash),
            ArtifactRef(kind="replication_stderr", uri=str(artifact_root / "stderr.txt"), sha256=stderr_hash),
            ArtifactRef(kind="replication_execution_report", uri=str(artifact_root / "execution_report.json"), sha256=execution_hash),
            ArtifactRef(kind="replication_package_workspace", uri=str(package_workspace), metadata={"directory": True, "fingerprint": after_fingerprint}),
            *expected_refs,
        ]

        evidence_ledger = self._evidence_ledger(package, artifact_refs, execution_payload)
        evidence_report = evidence_ledger.evaluate(required_claim_ids=self._claim_ids(package))
        memory_protocol = MemoryCommitProtocol()
        memory_commit = self._commit_memory(package, memory_protocol, artifact_refs, command_exit_code == 0)
        research_session = self._research_session(package, artifact_refs, memory_commit.committed_record_ids)
        phase_gate = ResearchPhaseGate(
            phase=ResearchPhase.WRITEUP,
            required_artifact_kinds=["replication_execution_report", "replication_package_workspace"],
            required_memory_record_ids=list(memory_commit.committed_record_ids),
            required_evidence_claim_ids=self._claim_ids(package),
            require_validation_receipt=True,
            require_review_ref=True,
        )
        research_report = ResearchSessionVerifier().evaluate(
            research_session,
            phase_gates=[phase_gate],
            evidence_ledger=evidence_ledger,
        )
        trace_events = self._trace_events(package, artifact_refs, execution_payload)
        state = RuntimeState(
            task_id=f"artifact-replication::{package.package_id}",
            session_id=f"artifact-replication-session::{package.package_id}",
            run_id=f"artifact-replication-run::{package.package_id}",
            goal=f"Replicate artifact for {package.paper_title}",
            execution_cursor="after:replication",
            active_step="replication",
            process_stage="active",
            policy_snapshot={"artifact_replication": True, "timeout_s": package.timeout_s},
            artifact_refs=list(artifact_refs),
            metadata={
                "package_id": package.package_id,
                "paper_title": package.paper_title,
                "source_refs": list(package.source_refs),
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
            required_evidence_claim_ids=self._claim_ids(package),
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
        failures.extend(memory_commit.failures)
        failures.extend(research_report.failures)
        failures.extend(hydration_report.failures)
        warnings.extend(evidence_report.warnings)
        warnings.extend(research_report.warnings)
        warnings.extend(hydration_report.warnings)
        success = (
            not failures
            and command_exit_code == 0
            and evidence_report.sound
            and research_report.phase_gate_passed
            and hydration_report.safe_to_hydrate
        )
        payload = {
            "package": package.to_dict(),
            "execution": execution_payload,
            "artifact_refs": [asdict(ref) for ref in artifact_refs],
            "evidence_report": evidence_report.to_dict(),
            "memory_commit": memory_commit.to_dict(),
            "research_report": research_report.to_dict(),
            "hydration_report": hydration_report.to_dict(),
        }
        return ArtifactReplicationResult(
            package_id=package.package_id,
            paper_title=package.paper_title,
            success=success,
            command_exit_code=command_exit_code,
            command=package.run_command,
            duration_s=duration_s,
            workspace_ref=str(task_root),
            package_workspace_ref=str(package_workspace),
            expected_artifact_count=len(package.expected_artifacts),
            expected_artifact_found_count=len(expected_refs),
            missing_expected_artifacts=missing_expected_artifacts,
            metric_file_count=metric_file_count,
            artifact_uris=[artifact.uri for artifact in artifact_refs],
            evidence_claim_ids=self._claim_ids(package),
            committed_memory_record_ids=list(memory_commit.committed_record_ids),
            evidence_ledger_sound=evidence_report.sound,
            phase_gate_passed=research_report.phase_gate_passed,
            hydration_safe=hydration_report.safe_to_hydrate,
            failures=failures,
            warnings=warnings,
            result_fingerprint=_stable_hash(payload),
        )

    def _evidence_ledger(
        self,
        package: ArtifactReplicationPackageSpec,
        artifact_refs: list[ArtifactRef],
        execution_payload: JsonDict,
    ) -> EvidenceLedger:
        entries = [
            EvidenceEntry(
                entry_id=f"entry-{_safe_name(package.package_id)}-{index}",
                kind=EvidenceKind.ARTIFACT,
                source_ref=artifact.uri,
                content_hash=artifact.sha256 or artifact.metadata.get("fingerprint", ""),
                labels=[artifact.kind, "real-artifact-replication"],
            )
            for index, artifact in enumerate(artifact_refs)
        ]
        if package.source_refs:
            for index, source_ref in enumerate(package.source_refs):
                entries.append(
                    EvidenceEntry(
                        entry_id=f"source-{_safe_name(package.package_id)}-{index}",
                        kind=EvidenceKind.SOURCE,
                        source_ref=source_ref,
                        labels=["paper-artifact-source", "real-artifact-replication"],
                    )
                )
        entry_ids = [entry.entry_id for entry in entries]
        claims = [
            EvidenceClaim(
                claim_id=self._claim_ids(package)[0],
                statement=f"{package.paper_title} artifact package was materialized in an isolated workspace.",
                cited_entry_ids=entry_ids,
                required_labels=["real-artifact-replication"],
            ),
            EvidenceClaim(
                claim_id=self._claim_ids(package)[1],
                statement=f"{package.paper_title} reproduction command completed with exit_code={execution_payload['command_exit_code']}.",
                cited_entry_ids=entry_ids,
                required_labels=["real-artifact-replication"],
            ),
            EvidenceClaim(
                claim_id=self._claim_ids(package)[2],
                statement=f"{package.paper_title} expected artifacts and metric files were checked.",
                cited_entry_ids=entry_ids,
                required_labels=["real-artifact-replication"],
            ),
        ]
        return EvidenceLedger(entries=entries, claims=claims)

    def _commit_memory(
        self,
        package: ArtifactReplicationPackageSpec,
        memory_protocol: MemoryCommitProtocol,
        artifact_refs: list[ArtifactRef],
        command_completed: bool,
    ):
        tx = memory_protocol.begin_transaction(
            transaction_id=f"tx-artifact-{_safe_name(package.package_id)}",
            checkpoint_version=1,
        )
        record = memory_protocol.stage_record(
            tx.transaction_id,
            record_id=f"memory-artifact-{_safe_name(package.package_id)}",
            kind=MemoryKind.BELIEF,
            payload={
                "package_id": package.package_id,
                "paper_title": package.paper_title,
                "command_completed": command_completed,
                "claim": "real artifact replication package was executed and audited",
            },
            source_refs=[artifact.uri for artifact in artifact_refs],
        )
        memory_protocol.validate_record(
            record.record_id,
            ValidationReceipt(
                validator="artifact-replication-ingestor",
                passed=command_completed,
                reasons=[
                    "replication command completed" if command_completed else "replication command failed",
                    "artifacts and evidence ledger materialized",
                ],
                evidence_refs=[artifact.uri for artifact in artifact_refs],
                checkpoint_version=1,
            ),
        )
        return memory_protocol.commit(tx.transaction_id, checkpoint_version=2)

    def _research_session(
        self,
        package: ArtifactReplicationPackageSpec,
        artifact_refs: list[ArtifactRef],
        committed_record_ids: list[str],
    ) -> ResearchSession:
        session = ResearchSession(
            session_id=f"artifact-replication::{package.package_id}",
            runtime_task_id=f"artifact-replication::{package.package_id}",
            goal=f"Replicate artifact for {package.paper_title}",
            policy_snapshot_hash=_stable_hash({"package_id": package.package_id, "timeout_s": package.timeout_s}),
        )
        labels = ["load_artifact_manifest", "run_replication_command", "collect_replication_outputs"]
        session.advance_to(ResearchPhase.PAPER_SCAN, evidence_refs=list(package.source_refs), transition_labels=labels[:1])
        session.advance_to(ResearchPhase.HYPOTHESIS, transition_labels=labels[:1])
        session.advance_to(ResearchPhase.EXPERIMENT_PLAN, artifact_refs=artifact_refs[:1], transition_labels=labels[:2])
        session.advance_to(
            ResearchPhase.EXPERIMENT_RUN,
            artifact_refs=list(artifact_refs),
            transition_labels=labels,
            memory_record_ids=list(committed_record_ids),
            validation_receipt_refs=[f"receipt://artifact-replication/{package.package_id}/command"],
        )
        session.advance_to(ResearchPhase.ANALYSIS, transition_labels=labels)
        session.advance_to(ResearchPhase.REVIEW, review_refs=[f"review://artifact-replication/{package.package_id}/ingest"])
        session.advance_to(ResearchPhase.WRITEUP, transition_labels=labels)
        return session

    def _trace_events(
        self,
        package: ArtifactReplicationPackageSpec,
        artifact_refs: list[ArtifactRef],
        execution_payload: JsonDict,
    ) -> list[TraceEvent]:
        labels = ["load_artifact_manifest", "run_replication_command", "collect_replication_outputs"]
        events: list[TraceEvent] = []
        for index, label in enumerate(labels):
            envelope = {
                "schema_version": "trace-envelope-v2",
                "boundary": TraceBoundary.TOOL,
                "task_id": f"artifact-replication::{package.package_id}",
                "run_id": f"artifact-replication-run::{package.package_id}",
                "cursor": f"artifact-replication:{index}",
                "provider_name": "artifact-replication-ingestor",
                "provider_fingerprint": _stable_hash({"provider": "artifact-replication-ingestor"})[:12],
                "policy_fingerprint": _stable_hash({"package_id": package.package_id, "timeout_s": package.timeout_s})[:12],
                "action_name": label,
                "action_effect": "execute",
                "input_hash": hash_payload({"package_id": package.package_id, "label": label}),
                "output_hash": hash_payload({"execution": execution_payload, "label": label}),
                "evidence_ledger_fingerprint": _stable_hash({"claims": self._claim_ids(package)})[:12],
                "evidence_claim_ids": self._claim_ids(package),
                "artifact_refs": [artifact.uri for artifact in artifact_refs],
                "receipts": [],
                "metadata": {"package_id": package.package_id, "real_artifact_replication": True},
            }
            envelope["trace_envelope_fingerprint"] = hash_payload(envelope)
            events.append(
                TraceEvent(
                    event_id=f"artifact-replication-{_safe_name(package.package_id)}-{index}",
                    task_id=f"artifact-replication::{package.package_id}",
                    run_id=f"artifact-replication-run::{package.package_id}",
                    cursor=f"artifact-replication:{index}",
                    kind="tool_completed",
                    data={
                        "tool": label,
                        "args_hash": envelope["input_hash"],
                        "output_hash": envelope["output_hash"],
                        "artifact_refs": [artifact.uri for artifact in artifact_refs],
                        "trace_envelope": envelope,
                        "trace_envelope_fingerprint": envelope["trace_envelope_fingerprint"],
                    },
                )
            )
        return events

    def _claim_ids(self, package: ArtifactReplicationPackageSpec) -> list[str]:
        prefix = _safe_name(package.package_id).lower()
        return [
            f"claim-{prefix}-artifact-materialized",
            f"claim-{prefix}-replication-executed",
            f"claim-{prefix}-outputs-audited",
        ]
