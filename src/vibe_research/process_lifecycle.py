from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any, Iterable

from .schema import RunStatus, RuntimeState


JsonDict = dict[str, Any]


class ProcessStage:
    DORMANT = "dormant"
    ACTIVE = "active"
    WAITING = "waiting"
    SUSPENDED = "suspended"
    RECOVERING = "recovering"
    REVIEWING = "reviewing"
    ARCHIVING = "archiving"


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _state_dict(state: RuntimeState | JsonDict) -> JsonDict:
    if isinstance(state, RuntimeState):
        return state.to_dict()
    return dict(state)


def _normalize_refs(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _derive_stage_from_status(status: str) -> str:
    mapping = {
        RunStatus.READY: ProcessStage.ACTIVE,
        RunStatus.RUNNING: ProcessStage.ACTIVE,
        RunStatus.AWAITING_APPROVAL: ProcessStage.WAITING,
        RunStatus.BLOCKED: ProcessStage.SUSPENDED,
        RunStatus.FAILED: ProcessStage.SUSPENDED,
        RunStatus.COMPLETED: ProcessStage.ARCHIVING,
    }
    return mapping.get(status, ProcessStage.DORMANT)


@dataclass(frozen=True, slots=True)
class StateLedgerItem:
    """A persistent state item inspected by an always-on runtime."""

    item_id: str
    item_type: str
    authority: str
    scope: str
    mutability: str
    provenance_refs: list[str] = field(default_factory=list)
    recoverability: str = "replayable"
    actionability: str = "read_only"
    source_refs: list[str] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def axis_gaps(self) -> list[str]:
        gaps: list[str] = []
        if not self.authority.strip():
            gaps.append("authority")
        if not self.scope.strip():
            gaps.append("scope")
        if not self.mutability.strip():
            gaps.append("mutability")
        if not self.provenance_refs:
            gaps.append("provenance")
        if not self.recoverability.strip():
            gaps.append("recoverability")
        if not self.actionability.strip():
            gaps.append("actionability")
        return gaps

    def action_risk(self) -> str:
        if self.actionability in {"external", "publish", "write"}:
            return "effectful"
        if self.actionability in {"audit", "read"}:
            return "observational"
        return "mixed"


@dataclass(frozen=True, slots=True)
class ProcessLifecycleReport:
    """Always-on runtime audit over persistent state items and lifecycle stage."""

    lifecycle_stage: str
    derived_stage: str
    stage_matches_status: bool
    stage_requires_attention: bool
    state_item_ids: list[str] = field(default_factory=list)
    recoverable_item_ids: list[str] = field(default_factory=list)
    effectful_item_ids: list[str] = field(default_factory=list)
    missing_axis_item_ids: list[str] = field(default_factory=list)
    nonrecoverable_effectful_item_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    state_fingerprint: str = ""
    item_fingerprint: str = ""
    report_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return asdict(self)


class ProcessLifecycleVerifier:
    """Audits always-on process state against lifecycle and persistence axes."""

    def evaluate(
        self,
        state: RuntimeState | JsonDict,
        items: Iterable[StateLedgerItem],
        *,
        lifecycle_stage: str | None = None,
    ) -> ProcessLifecycleReport:
        payload = _state_dict(state)
        item_list = list(items)
        status = str(payload.get("status") or RunStatus.READY)
        derived_stage = _derive_stage_from_status(status)
        stage = lifecycle_stage or str(payload.get("process_stage") or derived_stage)

        state_item_ids: list[str] = []
        recoverable_item_ids: list[str] = []
        effectful_item_ids: list[str] = []
        missing_axis_item_ids: list[str] = []
        nonrecoverable_effectful_item_ids: list[str] = []
        warnings: list[str] = []
        failures: list[str] = []

        for item in item_list:
            state_item_ids.append(item.item_id)
            gaps = item.axis_gaps()
            if gaps:
                missing_axis_item_ids.append(item.item_id)
                failures.append(f"item missing lifecycle axes: {item.item_id} ({', '.join(gaps)})")

            if item.recoverability not in {"none", "lost"}:
                recoverable_item_ids.append(item.item_id)

            if item.action_risk() == "effectful":
                effectful_item_ids.append(item.item_id)
                if item.recoverability in {"none", "lost"}:
                    nonrecoverable_effectful_item_ids.append(item.item_id)
                    failures.append(f"effectful item is nonrecoverable: {item.item_id}")

            if not item.provenance_refs:
                warnings.append(f"item has no provenance refs: {item.item_id}")
            if not item.source_refs:
                warnings.append(f"item has no source refs: {item.item_id}")
            if item.authority == "*":
                warnings.append(f"item authority is wildcard: {item.item_id}")

        if stage != derived_stage:
            failures.append(f"process stage mismatch: {stage} != {derived_stage}")

        stage_requires_attention = stage in {
            ProcessStage.WAITING,
            ProcessStage.SUSPENDED,
            ProcessStage.RECOVERING,
        }

        if stage == ProcessStage.ACTIVE and not item_list:
            warnings.append("active process has no ledger items")
        if stage == ProcessStage.WAITING and not any(item.action_risk() == "effectful" for item in item_list):
            warnings.append("waiting process has no effectful item to gate")
        if stage == ProcessStage.ARCHIVING:
            mutable_items = [item.item_id for item in item_list if item.mutability not in {"immutable", "append_only"}]
            if mutable_items:
                warnings.append(f"archiving process still has mutable items: {', '.join(mutable_items)}")

        state_fingerprint = _stable_hash(payload)
        item_fingerprint = _stable_hash([item.to_dict() for item in item_list])
        report_payload = {
            "lifecycle_stage": stage,
            "derived_stage": derived_stage,
            "state_item_ids": state_item_ids,
            "recoverable_item_ids": recoverable_item_ids,
            "effectful_item_ids": effectful_item_ids,
            "missing_axis_item_ids": missing_axis_item_ids,
            "nonrecoverable_effectful_item_ids": nonrecoverable_effectful_item_ids,
            "warnings": warnings,
            "failures": failures,
            "state_fingerprint": state_fingerprint,
            "item_fingerprint": item_fingerprint,
        }

        return ProcessLifecycleReport(
            lifecycle_stage=stage,
            derived_stage=derived_stage,
            stage_matches_status=stage == derived_stage,
            stage_requires_attention=stage_requires_attention,
            state_item_ids=state_item_ids,
            recoverable_item_ids=recoverable_item_ids,
            effectful_item_ids=effectful_item_ids,
            missing_axis_item_ids=missing_axis_item_ids,
            nonrecoverable_effectful_item_ids=nonrecoverable_effectful_item_ids,
            warnings=warnings,
            failures=failures,
            state_fingerprint=state_fingerprint,
            item_fingerprint=item_fingerprint,
            report_fingerprint=_stable_hash(report_payload),
        )


def state_ledger_items_from_state(state: RuntimeState | JsonDict) -> list[StateLedgerItem]:
    payload = _state_dict(state)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    raw_items = metadata.get("state_ledger", [])
    items: list[StateLedgerItem] = []

    for index, item in enumerate(raw_items):
        if isinstance(item, StateLedgerItem):
            items.append(item)
            continue

        if isinstance(item, dict):
            item_id = str(item.get("item_id") or item.get("id") or f"ledger-{index}")
            items.append(
                StateLedgerItem(
                    item_id=item_id,
                    item_type=str(item.get("item_type") or item.get("type") or "state_item"),
                    authority=str(item.get("authority") or "agent"),
                    scope=str(item.get("scope") or payload.get("task_id") or "*"),
                    mutability=str(item.get("mutability") or "append_only"),
                    provenance_refs=_normalize_refs(item.get("provenance_refs") or item.get("source_refs")),
                    recoverability=str(item.get("recoverability") or "replayable"),
                    actionability=str(item.get("actionability") or "read_only"),
                    source_refs=_normalize_refs(item.get("source_refs")),
                    metadata=dict(item.get("metadata") or {}),
                )
            )
    return items
