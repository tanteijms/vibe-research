from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from pathlib import Path

from .evidence_ledger import EvidenceClaim, EvidenceEntry, EvidenceKind, EvidenceLedger
from .fse_benchmark import BenchmarkTaskSpec, FseBenchmarkPlan, FseTaskFamily
from .hydration_manifest import HydrationManifestBuilder, HydrationReport
from .memory_commit import MemoryCommitProtocol, MemoryKind, ValidationReceipt
from .research_session import ResearchPhase, ResearchPhaseGate, ResearchSession, ResearchSessionReport, ResearchSessionVerifier
from .schema import ArtifactRef, RuntimeState, TraceEvent
from .trace_contract import TraceBoundary, hash_payload


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return _sha256_path(path)


def _sha256_path(path: Path) -> str:
    digest = sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class FseLocalTaskResult:
    task_id: str
    task_family: str
    success: bool
    workspace_ref: str
    artifact_uris: list[str]
    evidence_claim_ids: list[str]
    committed_memory_record_ids: list[str]
    phase_gate_passed: bool
    hydration_safe: bool
    trace_event_count: int
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    result_fingerprint: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FseLocalRunReport:
    ready_for_local_runner: bool
    task_count: int
    success_count: int
    hydration_safe_count: int
    phase_gate_passed_count: int
    evidence_claim_count: int
    committed_memory_count: int
    artifact_count: int
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    run_fingerprint: str = ""
    task_results: list[FseLocalTaskResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["task_results"] = [result.to_dict() for result in self.task_results]
        return data


class FseLocalToyTaskRunner:
    """Runs a small deterministic local benchmark over three FSE task families.

    This is intentionally not an LLM benchmark. It is an artifact-quality smoke
    layer that proves the proposed evaluation can create real files, evidence,
    committed memory, phase-gated reports, and hydration manifests.
    """

    def __init__(self, plan: FseBenchmarkPlan | None = None):
        self.plan = plan or FseBenchmarkPlan.default()

    def run(self, workspace_root: str | Path) -> FseLocalRunReport:
        root = Path(workspace_root)
        root.mkdir(parents=True, exist_ok=True)
        tasks = self._representative_tasks()
        results = [self._run_task(root, task) for task in tasks]

        failures = [failure for result in results for failure in result.failures]
        warnings = [warning for result in results for warning in result.warnings]
        payload = {
            "workspace_root": str(root),
            "results": [result.to_dict() for result in results],
        }
        return FseLocalRunReport(
            ready_for_local_runner=not failures and bool(results),
            task_count=len(results),
            success_count=sum(1 for result in results if result.success),
            hydration_safe_count=sum(1 for result in results if result.hydration_safe),
            phase_gate_passed_count=sum(1 for result in results if result.phase_gate_passed),
            evidence_claim_count=sum(len(result.evidence_claim_ids) for result in results),
            committed_memory_count=sum(len(result.committed_memory_record_ids) for result in results),
            artifact_count=sum(len(result.artifact_uris) for result in results),
            failures=failures,
            warnings=warnings,
            run_fingerprint=_stable_hash(payload),
            task_results=results,
        )

    def _representative_tasks(self) -> list[BenchmarkTaskSpec]:
        selected: list[BenchmarkTaskSpec] = []
        families = [
            FseTaskFamily.ISSUE_TO_PATCH,
            FseTaskFamily.ARTIFACT_REPLICATION,
            FseTaskFamily.INCIDENT_RCA,
        ]
        for family in families:
            for task in self.plan.tasks:
                if task.family == family:
                    selected.append(task)
                    break
        return selected

    def _run_task(self, workspace_root: Path, task: BenchmarkTaskSpec) -> FseLocalTaskResult:
        task_root = workspace_root / task.task_id
        artifact_refs = self._materialize_task_artifacts(task_root, task)
        trace_events = self._trace_events(task, artifact_refs)
        evidence_ledger = self._evidence_ledger(task, artifact_refs)
        memory_protocol = MemoryCommitProtocol()
        memory_commit = self._commit_memory(task, memory_protocol, artifact_refs)
        research_session = self._research_session(task, artifact_refs, memory_commit.committed_record_ids)
        gate = ResearchPhaseGate(
            phase=ResearchPhase.WRITEUP,
            required_artifact_kinds=list(task.required_artifact_kinds),
            required_transition_labels=list(task.required_transition_labels),
            required_memory_record_ids=list(memory_commit.committed_record_ids),
            required_evidence_claim_ids=list(task.required_evidence_claim_ids),
            require_validation_receipt=True,
            require_review_ref=True,
        )
        research_report = ResearchSessionVerifier().evaluate(
            research_session,
            phase_gates=[gate],
            evidence_ledger=evidence_ledger,
        )
        state = RuntimeState(
            task_id=f"local::{task.task_id}",
            session_id=f"local-session::{task.task_id}",
            run_id=f"local-run::{task.task_id}",
            goal=task.title,
            execution_cursor="after:writeup",
            active_step="writeup",
            process_stage="active",
            policy_snapshot={"allowed_tools": task.steps, "local_runner": True},
            artifact_refs=list(artifact_refs),
            metadata={"workspace_ref": str(task_root)},
        )
        hydration_builder = HydrationManifestBuilder()
        hydration_manifest = hydration_builder.dehydrate(
            state,
            trace_events,
            memory_records=list(memory_protocol.records.values()),
            evidence_ledger=evidence_ledger,
            research_session=research_session,
            required_memory_record_ids=list(memory_commit.committed_record_ids),
            required_evidence_claim_ids=list(task.required_evidence_claim_ids),
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
        failures = list(memory_commit.failures)
        failures.extend(research_report.failures)
        failures.extend(hydration_report.failures)
        success = not failures and research_report.phase_gate_passed and hydration_report.safe_to_hydrate
        payload = {
            "task": task.to_dict(),
            "artifact_refs": [asdict(ref) for ref in artifact_refs],
            "research_report": research_report.to_dict(),
            "hydration_report": hydration_report.to_dict(),
            "memory_commit": memory_commit.to_dict(),
        }

        return FseLocalTaskResult(
            task_id=task.task_id,
            task_family=task.family,
            success=success,
            workspace_ref=str(task_root),
            artifact_uris=[artifact.uri for artifact in artifact_refs],
            evidence_claim_ids=list(task.required_evidence_claim_ids),
            committed_memory_record_ids=list(memory_commit.committed_record_ids),
            phase_gate_passed=research_report.phase_gate_passed,
            hydration_safe=hydration_report.safe_to_hydrate,
            trace_event_count=len(trace_events),
            failures=failures,
            warnings=list(research_report.warnings) + list(hydration_report.warnings),
            result_fingerprint=_stable_hash(payload),
        )

    def _materialize_task_artifacts(self, task_root: Path, task: BenchmarkTaskSpec) -> list[ArtifactRef]:
        writers = {
            FseTaskFamily.ISSUE_TO_PATCH: self._write_issue_to_patch_artifacts,
            FseTaskFamily.ARTIFACT_REPLICATION: self._write_artifact_replication_artifacts,
            FseTaskFamily.INCIDENT_RCA: self._write_incident_rca_artifacts,
        }
        return writers[task.family](task_root, task)

    def _write_issue_to_patch_artifacts(self, task_root: Path, task: BenchmarkTaskSpec) -> list[ArtifactRef]:
        _write_text(task_root / "repo" / "calculator.py", "def add(a, b):\n    return a - b\n")
        patch_hash = _write_text(
            task_root / "patch.diff",
            "--- a/calculator.py\n+++ b/calculator.py\n@@\n-def add(a, b): return a - b\n+def add(a, b): return a + b\n",
        )
        test_hash = _write_text(task_root / "test_report.txt", "test_add: passed\n")
        diagnosis_hash = _write_text(task_root / "diagnosis.md", "Root cause: add used subtraction. Patch changes '-' to '+'.\n")
        return [
            ArtifactRef(kind="patch", uri=str(task_root / "patch.diff"), sha256=patch_hash),
            ArtifactRef(kind="test_report", uri=str(task_root / "test_report.txt"), sha256=test_hash),
            ArtifactRef(kind="diagnosis_note", uri=str(task_root / "diagnosis.md"), sha256=diagnosis_hash),
        ]

    def _write_artifact_replication_artifacts(self, task_root: Path, task: BenchmarkTaskSpec) -> list[ArtifactRef]:
        shortlist_hash = _write_text(task_root / "papers.json", json.dumps({"papers": ["toy-fse-paper"]}, sort_keys=True))
        script_hash = _write_text(task_root / "replicate.py", "print({'metric': 0.91})\n")
        metric_hash = _write_text(task_root / "metric.json", json.dumps({"metric": 0.91, "validated": True}, sort_keys=True))
        note_hash = _write_text(task_root / "reproduction_note.md", "The toy artifact reproduces metric=0.91 with a bounded script.\n")
        return [
            ArtifactRef(kind="paper_shortlist", uri=str(task_root / "papers.json"), sha256=shortlist_hash),
            ArtifactRef(kind="replication_script", uri=str(task_root / "replicate.py"), sha256=script_hash),
            ArtifactRef(kind="metric", uri=str(task_root / "metric.json"), sha256=metric_hash),
            ArtifactRef(kind="reproduction_note", uri=str(task_root / "reproduction_note.md"), sha256=note_hash),
        ]

    def _write_incident_rca_artifacts(self, task_root: Path, task: BenchmarkTaskSpec) -> list[ArtifactRef]:
        _write_text(task_root / "logs.txt", "12:00 alert latency_spike service=checkout cause=cache_miss\n")
        report_hash = _write_text(task_root / "incident_report.md", "Root cause: checkout cache misses triggered latency spike.\n")
        mitigation_hash = _write_text(task_root / "mitigation_plan.md", "Mitigation: warm cache and add miss-rate alert.\n")
        diagnosis_hash = _write_text(task_root / "diagnosis_note.md", "Evidence links logs and metrics to cache miss root cause.\n")
        return [
            ArtifactRef(kind="incident_report", uri=str(task_root / "incident_report.md"), sha256=report_hash),
            ArtifactRef(kind="mitigation_plan", uri=str(task_root / "mitigation_plan.md"), sha256=mitigation_hash),
            ArtifactRef(kind="diagnosis_note", uri=str(task_root / "diagnosis_note.md"), sha256=diagnosis_hash),
        ]

    def _evidence_ledger(self, task: BenchmarkTaskSpec, artifact_refs: list[ArtifactRef]) -> EvidenceLedger:
        entries = [
            EvidenceEntry(
                entry_id=f"entry-{index}",
                kind=EvidenceKind.ARTIFACT,
                source_ref=artifact.uri,
                content_hash=artifact.sha256 or "",
                labels=[artifact.kind, "local-toy"],
            )
            for index, artifact in enumerate(artifact_refs)
        ]
        claims = [
            EvidenceClaim(
                claim_id=claim_id,
                statement=f"{task.title} local runner claim is supported.",
                cited_entry_ids=[entry.entry_id for entry in entries],
                required_labels=["local-toy"],
            )
            for claim_id in task.required_evidence_claim_ids
        ]
        return EvidenceLedger(entries=entries, claims=claims)

    def _commit_memory(
        self,
        task: BenchmarkTaskSpec,
        memory_protocol: MemoryCommitProtocol,
        artifact_refs: list[ArtifactRef],
    ):
        tx = memory_protocol.begin_transaction(transaction_id=f"tx-{task.task_id}", checkpoint_version=1)
        record = memory_protocol.stage_record(
            tx.transaction_id,
            record_id=f"memory-{task.task_id}",
            kind=MemoryKind.BELIEF,
            payload={"task_id": task.task_id, "claim": "local toy task completed with validated artifacts"},
            source_refs=[artifact.uri for artifact in artifact_refs],
        )
        memory_protocol.validate_record(
            record.record_id,
            ValidationReceipt(
                validator="local-toy-runner",
                passed=True,
                reasons=["required artifacts materialized", "evidence claims created"],
                evidence_refs=[artifact.uri for artifact in artifact_refs],
                checkpoint_version=1,
            ),
        )
        return memory_protocol.commit(tx.transaction_id, checkpoint_version=2)

    def _research_session(
        self,
        task: BenchmarkTaskSpec,
        artifact_refs: list[ArtifactRef],
        committed_record_ids: list[str],
    ) -> ResearchSession:
        session = ResearchSession(
            session_id=f"research-local::{task.task_id}",
            runtime_task_id=f"local::{task.task_id}",
            goal=task.title,
            policy_snapshot_hash=_stable_hash({"local_runner": True, "task_id": task.task_id}),
        )
        labels = list(task.required_transition_labels)
        session.advance_to(ResearchPhase.PAPER_SCAN, evidence_refs=[f"source://{task.task_id}"], transition_labels=labels[:1])
        session.advance_to(ResearchPhase.HYPOTHESIS, transition_labels=labels[1:2])
        session.advance_to(ResearchPhase.EXPERIMENT_PLAN, transition_labels=labels[2:3])
        session.advance_to(
            ResearchPhase.EXPERIMENT_RUN,
            artifact_refs=list(artifact_refs),
            transition_labels=labels,
            memory_record_ids=list(committed_record_ids),
            validation_receipt_refs=[f"receipt://{task.task_id}/local-validation"],
        )
        session.advance_to(ResearchPhase.ANALYSIS, transition_labels=labels)
        session.advance_to(ResearchPhase.REVIEW, review_refs=[f"review://{task.task_id}/local-review"], transition_labels=labels)
        session.advance_to(ResearchPhase.WRITEUP, transition_labels=labels)
        return session

    def _trace_events(self, task: BenchmarkTaskSpec, artifact_refs: list[ArtifactRef]) -> list[TraceEvent]:
        events: list[TraceEvent] = []
        for index, label in enumerate(task.required_transition_labels or task.steps[:3]):
            envelope = {
                "schema_version": "trace-envelope-v2",
                "boundary": TraceBoundary.TOOL,
                "task_id": f"local::{task.task_id}",
                "run_id": f"local-run::{task.task_id}",
                "cursor": f"local:{index}",
                "provider_name": "local-toy-runner",
                "provider_fingerprint": _stable_hash({"provider": "local-toy-runner"})[:12],
                "policy_fingerprint": _stable_hash({"task_id": task.task_id, "local": True})[:12],
                "action_name": label,
                "action_effect": "execute",
                "input_hash": hash_payload({"task_id": task.task_id, "label": label}),
                "output_hash": hash_payload({"artifacts": [artifact.uri for artifact in artifact_refs], "label": label}),
                "evidence_ledger_fingerprint": _stable_hash({"claims": task.required_evidence_claim_ids})[:12],
                "evidence_claim_ids": list(task.required_evidence_claim_ids),
                "artifact_refs": [artifact.uri for artifact in artifact_refs],
                "receipts": [],
            }
            envelope["trace_envelope_fingerprint"] = hash_payload(envelope)
            events.append(
                TraceEvent(
                    event_id=f"local-{task.task_id}-{index}",
                    task_id=f"local::{task.task_id}",
                    run_id=f"local-run::{task.task_id}",
                    cursor=f"local:{index}",
                    kind="tool_completed",
                    data={
                        "tool": label,
                        "args_hash": envelope["input_hash"],
                        "output_hash": envelope["output_hash"],
                        "artifact_refs": [artifact.uri for artifact in artifact_refs],
                        "evidence_refs": [f"claim://{claim_id}" for claim_id in task.required_evidence_claim_ids],
                        "trace_envelope": envelope,
                        "trace_envelope_fingerprint": envelope["trace_envelope_fingerprint"],
                    },
                )
            )
        return events
