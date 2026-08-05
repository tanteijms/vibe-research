from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from .evidence_ledger import EvidenceLedger
from .memory_commit import MemoryRecord, MemoryStatus
from .research_session import ResearchSession
from .schema import RuntimeState, TraceEvent


JsonDict = dict[str, Any]


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _trace_payload(events: list[TraceEvent]) -> list[JsonDict]:
    return [event.to_dict() for event in events]


def _artifact_payload(state: RuntimeState, research_session: ResearchSession | None = None) -> list[JsonDict]:
    refs = [ref for ref in state.artifact_refs]
    if research_session is not None:
        refs.extend(research_session.artifact_refs)
    return sorted(
        [asdict(ref) for ref in refs],
        key=lambda item: (str(item.get("uri")), str(item.get("kind"))),
    )


def _memory_payload(memory_records: list[MemoryRecord] | None) -> list[JsonDict]:
    return [
        record.to_dict()
        for record in sorted(memory_records or [], key=lambda item: item.record_id)
    ]


def _memory_record_ids(memory_records: list[MemoryRecord] | None) -> list[str]:
    return [record.record_id for record in sorted(memory_records or [], key=lambda item: item.record_id)]


def _artifact_uris(state: RuntimeState, research_session: ResearchSession | None = None) -> list[str]:
    payload = _artifact_payload(state, research_session)
    return sorted({str(item.get("uri")) for item in payload if item.get("uri")})


class HydrationSurface:
    RUNTIME_STATE = "runtime_state"
    POLICY = "policy"
    TRACE = "trace"
    ARTIFACT = "artifact"
    MEMORY = "memory"
    EVIDENCE = "evidence"
    RESEARCH_SESSION = "research_session"


@dataclass(frozen=True, slots=True)
class HydrationManifest:
    """A replayable contract for dehydrating and hydrating a research-agent scene."""

    manifest_id: str
    task_id: str
    session_id: str
    run_id: str
    checkpoint_ref: str | None
    cursor: str
    active_step: str
    process_stage: str
    required_surfaces: list[str]
    state_fingerprint: str
    policy_fingerprint: str
    trace_fingerprint: str
    artifact_fingerprint: str
    trace_event_count: int = 0
    artifact_uris: list[str] = field(default_factory=list)
    memory_fingerprint: str | None = None
    memory_record_ids: list[str] = field(default_factory=list)
    evidence_fingerprint: str | None = None
    evidence_entry_ids: list[str] = field(default_factory=list)
    evidence_claim_ids: list[str] = field(default_factory=list)
    research_session_fingerprint: str | None = None
    research_phase: str | None = None
    required_memory_record_ids: list[str] = field(default_factory=list)
    required_evidence_claim_ids: list[str] = field(default_factory=list)
    required_artifact_uris: list[str] = field(default_factory=list)
    forbidden_evidence_labels: list[str] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class HydrationReport:
    """Hydration preflight result for deciding whether a scene is safe to resume."""

    safe_to_hydrate: bool
    retained_surfaces: list[str]
    missing_surfaces: list[str] = field(default_factory=list)
    drifted_surfaces: list[str] = field(default_factory=list)
    missing_required_memory_record_ids: list[str] = field(default_factory=list)
    unsafe_required_memory_record_ids: list[str] = field(default_factory=list)
    missing_required_evidence_claim_ids: list[str] = field(default_factory=list)
    unsupported_evidence_claim_ids: list[str] = field(default_factory=list)
    missing_required_artifact_uris: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest_fingerprint: str = ""
    report_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return asdict(self)


class HydrationManifestBuilder:
    """Builds and verifies hydratable research-scene manifests."""

    def dehydrate(
        self,
        state: RuntimeState,
        events: list[TraceEvent],
        *,
        memory_records: list[MemoryRecord] | None = None,
        evidence_ledger: EvidenceLedger | None = None,
        research_session: ResearchSession | None = None,
        required_memory_record_ids: list[str] | None = None,
        required_evidence_claim_ids: list[str] | None = None,
        required_artifact_uris: list[str] | None = None,
        forbidden_evidence_labels: list[str] | None = None,
        required_surfaces: list[str] | None = None,
        metadata: JsonDict | None = None,
    ) -> HydrationManifest:
        selected_surfaces = list(required_surfaces or self._default_required_surfaces(
            memory_records=memory_records,
            evidence_ledger=evidence_ledger,
            research_session=research_session,
        ))
        artifact_payload = _artifact_payload(state, research_session)
        memory_payload = _memory_payload(memory_records)
        evidence_payload = evidence_ledger.to_dict() if evidence_ledger is not None else None
        research_payload = research_session.to_dict() if research_session is not None else None

        return HydrationManifest(
            manifest_id=f"hydrate_{uuid4().hex[:12]}",
            task_id=state.task_id,
            session_id=state.session_id,
            run_id=state.run_id,
            checkpoint_ref=state.checkpoint_ref,
            cursor=state.execution_cursor,
            active_step=state.active_step,
            process_stage=state.process_stage,
            required_surfaces=selected_surfaces,
            state_fingerprint=_stable_hash(state.to_dict()),
            policy_fingerprint=_stable_hash(state.policy_snapshot),
            trace_fingerprint=_stable_hash(_trace_payload(events)),
            artifact_fingerprint=_stable_hash(artifact_payload),
            trace_event_count=len(events),
            artifact_uris=_artifact_uris(state, research_session),
            memory_fingerprint=_stable_hash(memory_payload) if memory_records is not None else None,
            memory_record_ids=_memory_record_ids(memory_records),
            evidence_fingerprint=_stable_hash(evidence_payload) if evidence_payload is not None else None,
            evidence_entry_ids=sorted(evidence_ledger.entries) if evidence_ledger is not None else [],
            evidence_claim_ids=sorted(evidence_ledger.claims) if evidence_ledger is not None else [],
            research_session_fingerprint=_stable_hash(research_payload) if research_payload is not None else None,
            research_phase=research_session.current_phase if research_session is not None else None,
            required_memory_record_ids=sorted(required_memory_record_ids or []),
            required_evidence_claim_ids=sorted(required_evidence_claim_ids or []),
            required_artifact_uris=sorted(required_artifact_uris or []),
            forbidden_evidence_labels=sorted(forbidden_evidence_labels or []),
            metadata=dict(metadata or {}),
        )

    def verify(
        self,
        manifest: HydrationManifest,
        state: RuntimeState,
        events: list[TraceEvent],
        *,
        memory_records: list[MemoryRecord] | None = None,
        evidence_ledger: EvidenceLedger | None = None,
        research_session: ResearchSession | None = None,
    ) -> HydrationReport:
        failures: list[str] = []
        warnings: list[str] = []
        missing_surfaces: list[str] = []
        drifted_surfaces: list[str] = []
        retained_surfaces: list[str] = []
        required_surfaces = set(manifest.required_surfaces)

        surface_fingerprints = {
            HydrationSurface.RUNTIME_STATE: _stable_hash(state.to_dict()),
            HydrationSurface.POLICY: _stable_hash(state.policy_snapshot),
            HydrationSurface.TRACE: _stable_hash(_trace_payload(events)),
            HydrationSurface.ARTIFACT: _stable_hash(_artifact_payload(state, research_session)),
            HydrationSurface.MEMORY: _stable_hash(_memory_payload(memory_records)) if memory_records is not None else None,
            HydrationSurface.EVIDENCE: _stable_hash(evidence_ledger.to_dict()) if evidence_ledger is not None else None,
            HydrationSurface.RESEARCH_SESSION: _stable_hash(research_session.to_dict()) if research_session is not None else None,
        }
        expected_fingerprints = {
            HydrationSurface.RUNTIME_STATE: manifest.state_fingerprint,
            HydrationSurface.POLICY: manifest.policy_fingerprint,
            HydrationSurface.TRACE: manifest.trace_fingerprint,
            HydrationSurface.ARTIFACT: manifest.artifact_fingerprint,
            HydrationSurface.MEMORY: manifest.memory_fingerprint,
            HydrationSurface.EVIDENCE: manifest.evidence_fingerprint,
            HydrationSurface.RESEARCH_SESSION: manifest.research_session_fingerprint,
        }

        for surface in manifest.required_surfaces:
            actual = surface_fingerprints.get(surface)
            expected = expected_fingerprints.get(surface)
            if expected is None:
                warnings.append(f"required surface has no manifest fingerprint: {surface}")
                continue
            if actual is None:
                missing_surfaces.append(surface)
                failures.append(f"missing hydration surface: {surface}")
                continue
            if actual != expected:
                drifted_surfaces.append(surface)
                failures.append(f"hydration surface drifted: {surface}")
                continue
            retained_surfaces.append(surface)

        missing_required_memory_record_ids: list[str] = []
        unsafe_required_memory_record_ids: list[str] = []
        records_by_id = {record.record_id: record for record in memory_records or []}
        for record_id in manifest.required_memory_record_ids:
            record = records_by_id.get(record_id)
            if record is None:
                missing_required_memory_record_ids.append(record_id)
                failures.append(f"missing required memory record: {record_id}")
            elif record.status != MemoryStatus.COMMITTED:
                unsafe_required_memory_record_ids.append(record_id)
                failures.append(f"required memory record is not committed: {record_id}:{record.status}")

        missing_required_evidence_claim_ids: list[str] = []
        unsupported_evidence_claim_ids: list[str] = []
        if manifest.required_evidence_claim_ids:
            if evidence_ledger is None:
                missing_surfaces.append(HydrationSurface.EVIDENCE)
                failures.append("missing evidence ledger for required claims")
                missing_required_evidence_claim_ids.extend(manifest.required_evidence_claim_ids)
            else:
                evidence_report = evidence_ledger.evaluate(
                    required_claim_ids=manifest.required_evidence_claim_ids,
                    forbidden_evidence_labels=manifest.forbidden_evidence_labels,
                )
                missing_required_evidence_claim_ids.extend(evidence_report.missing_required_claim_ids)
                unsupported_evidence_claim_ids.extend(evidence_report.unsupported_claim_ids)
                failures.extend(evidence_report.failures)
                warnings.extend(evidence_report.warnings)

        current_artifact_uris = set(_artifact_uris(state, research_session))
        missing_required_artifact_uris = [
            uri for uri in manifest.required_artifact_uris if uri not in current_artifact_uris
        ]
        for uri in missing_required_artifact_uris:
            failures.append(f"missing required artifact uri: {uri}")

        if len(events) != manifest.trace_event_count and HydrationSurface.TRACE in required_surfaces:
            warnings.append(
                f"trace event count differs from manifest: {len(events)} != {manifest.trace_event_count}"
            )

        payload = {
            "manifest_fingerprint": manifest.fingerprint(),
            "retained_surfaces": sorted(set(retained_surfaces)),
            "missing_surfaces": sorted(set(missing_surfaces)),
            "drifted_surfaces": sorted(set(drifted_surfaces)),
            "missing_required_memory_record_ids": sorted(set(missing_required_memory_record_ids)),
            "unsafe_required_memory_record_ids": sorted(set(unsafe_required_memory_record_ids)),
            "missing_required_evidence_claim_ids": sorted(set(missing_required_evidence_claim_ids)),
            "unsupported_evidence_claim_ids": sorted(set(unsupported_evidence_claim_ids)),
            "missing_required_artifact_uris": missing_required_artifact_uris,
            "failures": failures,
        }

        return HydrationReport(
            safe_to_hydrate=not failures,
            retained_surfaces=sorted(set(retained_surfaces)),
            missing_surfaces=sorted(set(missing_surfaces)),
            drifted_surfaces=sorted(set(drifted_surfaces)),
            missing_required_memory_record_ids=sorted(set(missing_required_memory_record_ids)),
            unsafe_required_memory_record_ids=sorted(set(unsafe_required_memory_record_ids)),
            missing_required_evidence_claim_ids=sorted(set(missing_required_evidence_claim_ids)),
            unsupported_evidence_claim_ids=sorted(set(unsupported_evidence_claim_ids)),
            missing_required_artifact_uris=missing_required_artifact_uris,
            failures=failures,
            warnings=warnings,
            manifest_fingerprint=manifest.fingerprint(),
            report_fingerprint=_stable_hash(payload),
        )

    @staticmethod
    def _default_required_surfaces(
        *,
        memory_records: list[MemoryRecord] | None,
        evidence_ledger: EvidenceLedger | None,
        research_session: ResearchSession | None,
    ) -> list[str]:
        surfaces = [
            HydrationSurface.RUNTIME_STATE,
            HydrationSurface.POLICY,
            HydrationSurface.TRACE,
            HydrationSurface.ARTIFACT,
        ]
        if memory_records is not None:
            surfaces.append(HydrationSurface.MEMORY)
        if evidence_ledger is not None:
            surfaces.append(HydrationSurface.EVIDENCE)
        if research_session is not None:
            surfaces.append(HydrationSurface.RESEARCH_SESSION)
        return surfaces
