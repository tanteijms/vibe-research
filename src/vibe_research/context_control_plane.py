from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from .schema import RuntimeState


JsonDict = dict[str, Any]


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _json_size(value: object) -> int:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return len(payload.encode("utf-8"))


def _get_path(payload: JsonDict, path: str) -> object:
    current: object = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


class ContextActionKind:
    RETAIN = "retain"
    DROP = "drop"
    COMPRESS = "compress"
    PIN = "pin"
    BRANCH = "branch"
    REHYDRATE = "rehydrate"


@dataclass(frozen=True, slots=True)
class ContextPinState:
    pin_id: str
    surface: str
    value: object
    required: bool = True
    description: str = ""
    source_path: str | None = None
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class ContextBranchState:
    branch_id: str
    parent_branch_id: str | None = None
    inherited_pin_ids: list[str] = field(default_factory=list)
    created_at_version: int = 0
    reason: str = ""
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class ContextActionReceipt:
    action_id: str
    kind: str
    state_version: int
    before_fingerprint: str
    after_fingerprint: str
    active_pin_ids: list[str] = field(default_factory=list)
    dropped_pin_ids: list[str] = field(default_factory=list)
    branch_id: str | None = None
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class ContextDashboard:
    task_id: str
    session_id: str
    run_id: str
    execution_cursor: str
    active_step: str
    branch_id: str | None
    parent_branch_id: str | None
    summary: str | None
    pinned_pin_ids: list[str]
    required_pin_ids: list[str]
    dropped_pin_ids: list[str]
    artifact_uris: list[str]
    memory_segment_pin_ids: list[str]
    retention_budget_bytes: int
    action_count: int
    warnings: list[str] = field(default_factory=list)
    dashboard_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return asdict(self)


class ContextControlPlane:
    """Makes context editing explicit and replayable inside RuntimeState metadata."""

    def __init__(self, state: RuntimeState):
        self.state = state
        self._ensure_metadata()

    def retain(
        self,
        *,
        pin_id: str,
        surface: str = "context",
        value: object | None = None,
        source_path: str | None = None,
        required: bool = True,
        description: str = "",
        reason: str = "",
        metadata: JsonDict | None = None,
    ) -> ContextActionReceipt:
        selected_value = value
        if selected_value is None and source_path is not None:
            selected_value = _get_path(self.state.to_dict(), source_path)
        if selected_value is None:
            existing = self._find_pin(pin_id)
            if existing is not None:
                selected_value = existing.get("value", existing.get("text"))
                surface = str(existing.get("surface") or surface)
                required = bool(existing.get("required", required))
                description = str(existing.get("description") or description)
        if selected_value is None:
            raise ValueError(f"no value available to retain for pin: {pin_id}")

        return self._upsert_pin(
            kind=ContextActionKind.RETAIN,
            pin_id=pin_id,
            surface=surface,
            value=selected_value,
            required=required,
            description=description,
            source_path=source_path,
            reason=reason,
            metadata=metadata,
        )

    def pin(
        self,
        *,
        pin_id: str,
        surface: str,
        value: object,
        required: bool = True,
        description: str = "",
        source_path: str | None = None,
        reason: str = "",
        metadata: JsonDict | None = None,
    ) -> ContextActionReceipt:
        return self._upsert_pin(
            kind=ContextActionKind.PIN,
            pin_id=pin_id,
            surface=surface,
            value=value,
            required=required,
            description=description,
            source_path=source_path,
            reason=reason,
            metadata=metadata,
        )

    def drop(self, pin_id: str, *, reason: str = "", metadata: JsonDict | None = None) -> ContextActionReceipt:
        before_fingerprint = self._context_fingerprint()
        pins = [pin for pin in self._context_pins() if str(pin.get("pin_id")) != pin_id]
        self.state.metadata["context_pins"] = pins
        dropped_ids = _dedupe(list(self.state.metadata.get("dropped_context_pin_ids", [])) + [pin_id])
        self.state.metadata["dropped_context_pin_ids"] = dropped_ids
        self._refresh_retained_pin_hashes()
        return self._record_action(
            kind=ContextActionKind.DROP,
            before_fingerprint=before_fingerprint,
            reason=reason,
            metadata=metadata,
            dropped_pin_ids=[pin_id],
        )

    def compress(
        self,
        summary: str,
        *,
        retained_pin_ids: list[str] | None = None,
        dropped_pin_ids: list[str] | None = None,
        reason: str = "",
        metadata: JsonDict | None = None,
    ) -> ContextActionReceipt:
        before_fingerprint = self._context_fingerprint()
        active_pin_ids = self._active_pin_ids()
        selected_retained = retained_pin_ids or active_pin_ids
        if dropped_pin_ids:
            for pin_id in dropped_pin_ids:
                self.state.metadata["context_pins"] = [
                    pin for pin in self._context_pins() if str(pin.get("pin_id")) != pin_id
                ]
            self.state.metadata["dropped_context_pin_ids"] = _dedupe(
                list(self.state.metadata.get("dropped_context_pin_ids", [])) + list(dropped_pin_ids)
            )

        self.state.metadata["summary"] = summary
        self.state.metadata["context_summary"] = summary
        self.state.metadata["context_compaction"] = {
            "summary_fingerprint": _stable_hash(summary),
            "retained_pin_ids": list(selected_retained),
            "dropped_pin_ids": list(dropped_pin_ids or []),
        }
        self._refresh_retained_pin_hashes(selected_retained)
        return self._record_action(
            kind=ContextActionKind.COMPRESS,
            before_fingerprint=before_fingerprint,
            reason=reason,
            metadata={
                **dict(metadata or {}),
                "summary_fingerprint": _stable_hash(summary),
                "retained_pin_ids": list(selected_retained),
            },
            dropped_pin_ids=list(dropped_pin_ids or []),
        )

    def branch(
        self,
        *,
        branch_id: str | None = None,
        parent_branch_id: str | None = None,
        inherited_pin_ids: list[str] | None = None,
        reason: str = "",
        metadata: JsonDict | None = None,
    ) -> ContextActionReceipt:
        before_fingerprint = self._context_fingerprint()
        selected_branch_id = branch_id or f"branch_{uuid4().hex[:10]}"
        current_branch = self._current_branch()
        branch = ContextBranchState(
            branch_id=selected_branch_id,
            parent_branch_id=parent_branch_id or (current_branch.get("branch_id") if current_branch else None),
            inherited_pin_ids=list(inherited_pin_ids or self._active_pin_ids()),
            created_at_version=self.state.version,
            reason=reason,
            metadata=dict(metadata or {}),
        )
        branches = [item for item in self._branches() if str(item.get("branch_id")) != selected_branch_id]
        branches.append(branch.to_dict())
        self.state.metadata["context_branches"] = branches
        self.state.metadata["context_branch"] = branch.to_dict()
        self.state.metadata["current_context_branch_id"] = selected_branch_id
        return self._record_action(
            kind=ContextActionKind.BRANCH,
            before_fingerprint=before_fingerprint,
            reason=reason,
            metadata={"branch": branch.to_dict()},
            branch_id=selected_branch_id,
        )

    def rehydrate(
        self,
        *,
        source_ref: str,
        branch_id: str | None = None,
        restored_pin_ids: list[str] | None = None,
        summary: str | None = None,
        reason: str = "",
        metadata: JsonDict | None = None,
    ) -> ContextActionReceipt:
        before_fingerprint = self._context_fingerprint()
        if summary is not None:
            self.state.metadata["summary"] = summary
            self.state.metadata["context_summary"] = summary
        if branch_id is not None:
            self.state.metadata["current_context_branch_id"] = branch_id
        selected_pin_ids = list(restored_pin_ids or self._active_pin_ids())
        self._refresh_retained_pin_hashes(selected_pin_ids)
        self.state.metadata["context_rehydration"] = {
            "source_ref": source_ref,
            "branch_id": branch_id,
            "restored_pin_ids": selected_pin_ids,
            "summary_fingerprint": _stable_hash(summary) if summary is not None else None,
        }
        return self._record_action(
            kind=ContextActionKind.REHYDRATE,
            before_fingerprint=before_fingerprint,
            reason=reason,
            metadata={
                **dict(metadata or {}),
                "source_ref": source_ref,
                "restored_pin_ids": selected_pin_ids,
            },
            branch_id=branch_id,
        )

    def dashboard(self) -> ContextDashboard:
        current_branch = self._current_branch()
        pins = self._context_pins()
        dropped_pin_ids = [str(item) for item in self.state.metadata.get("dropped_context_pin_ids", [])]
        required_pin_ids = [
            str(pin.get("pin_id"))
            for pin in pins
            if bool(pin.get("required", True))
        ]
        artifact_uris = sorted({ref.uri for ref in self.state.artifact_refs})
        memory_segment_pin_ids = [
            str(pin.get("pin_id"))
            for pin in pins
            if str(pin.get("surface") or "") == "memory"
        ]
        warnings: list[str] = []
        if not pins:
            warnings.append("context has no active pins")
        if not self.state.metadata.get("summary"):
            warnings.append("context summary is not set")
        payload = {
            "summary": self.state.metadata.get("summary"),
            "context_pins": pins,
            "context_actions": self.state.metadata.get("context_actions", []),
            "context_branch": current_branch,
            "artifact_uris": artifact_uris,
            "dropped_context_pin_ids": dropped_pin_ids,
        }
        dashboard = ContextDashboard(
            task_id=self.state.task_id,
            session_id=self.state.session_id,
            run_id=self.state.run_id,
            execution_cursor=self.state.execution_cursor,
            active_step=self.state.active_step,
            branch_id=str(current_branch.get("branch_id")) if current_branch else None,
            parent_branch_id=str(current_branch.get("parent_branch_id")) if current_branch and current_branch.get("parent_branch_id") else None,
            summary=str(self.state.metadata.get("summary")) if self.state.metadata.get("summary") is not None else None,
            pinned_pin_ids=self._active_pin_ids(),
            required_pin_ids=required_pin_ids,
            dropped_pin_ids=dropped_pin_ids,
            artifact_uris=artifact_uris,
            memory_segment_pin_ids=memory_segment_pin_ids,
            retention_budget_bytes=_json_size(payload),
            action_count=len(self.state.metadata.get("context_actions", [])),
            warnings=warnings,
            dashboard_fingerprint=_stable_hash(payload),
        )
        return dashboard

    def _upsert_pin(
        self,
        *,
        kind: str,
        pin_id: str,
        surface: str,
        value: object,
        required: bool,
        description: str,
        source_path: str | None,
        reason: str,
        metadata: JsonDict | None,
    ) -> ContextActionReceipt:
        before_fingerprint = self._context_fingerprint()
        normalized = ContextPinState(
            pin_id=pin_id,
            surface=surface,
            value=value,
            required=required,
            description=description,
            source_path=source_path,
            metadata=dict(metadata or {}),
        ).to_dict()
        pins = [pin for pin in self._context_pins() if str(pin.get("pin_id")) != pin_id]
        pins.append(normalized)
        self.state.metadata["context_pins"] = pins
        self.state.metadata["dropped_context_pin_ids"] = [
            item for item in self.state.metadata.get("dropped_context_pin_ids", [])
            if str(item) != pin_id
        ]
        self._refresh_retained_pin_hashes()
        return self._record_action(
            kind=kind,
            before_fingerprint=before_fingerprint,
            reason=reason,
            metadata={
                "pin": normalized,
            },
        )

    def _record_action(
        self,
        *,
        kind: str,
        before_fingerprint: str,
        reason: str,
        metadata: JsonDict | None = None,
        dropped_pin_ids: list[str] | None = None,
        branch_id: str | None = None,
    ) -> ContextActionReceipt:
        receipt = ContextActionReceipt(
            action_id=f"ctx_{uuid4().hex[:12]}",
            kind=kind,
            state_version=self.state.version,
            before_fingerprint=before_fingerprint,
            after_fingerprint=self._context_fingerprint(),
            active_pin_ids=self._active_pin_ids(),
            dropped_pin_ids=list(dropped_pin_ids or []),
            branch_id=branch_id or self.state.metadata.get("current_context_branch_id"),
            reason=reason,
            warnings=self.dashboard().warnings,
            metadata=dict(metadata or {}),
        )
        actions = list(self.state.metadata.get("context_actions", []))
        actions.append(receipt.to_dict())
        self.state.metadata["context_actions"] = actions
        return receipt

    def _ensure_metadata(self) -> None:
        if not isinstance(self.state.metadata, dict):
            self.state.metadata = {}
        self.state.metadata.setdefault("context_pins", [])
        self.state.metadata.setdefault("context_actions", [])
        self.state.metadata.setdefault("context_branches", [])
        self.state.metadata.setdefault("dropped_context_pin_ids", [])
        self.state.metadata.setdefault("retained_pin_hashes", [])

    def _context_fingerprint(self) -> str:
        payload = {
            "summary": self.state.metadata.get("summary"),
            "context_pins": self._context_pins(),
            "context_actions": self.state.metadata.get("context_actions", []),
            "context_branches": self._branches(),
            "current_context_branch_id": self.state.metadata.get("current_context_branch_id"),
            "artifact_refs": [asdict(ref) for ref in self.state.artifact_refs],
            "active_step": self.state.active_step,
            "execution_cursor": self.state.execution_cursor,
        }
        return _stable_hash(payload)

    def _context_pins(self) -> list[JsonDict]:
        raw = self.state.metadata.get("context_pins", [])
        return [dict(item) for item in raw if isinstance(item, dict)]

    def _branches(self) -> list[JsonDict]:
        raw = self.state.metadata.get("context_branches", [])
        return [dict(item) for item in raw if isinstance(item, dict)]

    def _current_branch(self) -> JsonDict | None:
        raw = self.state.metadata.get("context_branch")
        if isinstance(raw, dict):
            return dict(raw)
        branch_id = self.state.metadata.get("current_context_branch_id")
        if branch_id is None:
            return None
        for branch in self._branches():
            if str(branch.get("branch_id")) == str(branch_id):
                return branch
        return None

    def _active_pin_ids(self) -> list[str]:
        return [str(pin.get("pin_id")) for pin in self._context_pins()]

    def _find_pin(self, pin_id: str) -> JsonDict | None:
        for pin in self._context_pins():
            if str(pin.get("pin_id")) == pin_id:
                return pin
        return None

    def _refresh_retained_pin_hashes(self, selected_pin_ids: list[str] | None = None) -> None:
        selected = set(selected_pin_ids or self._active_pin_ids())
        hashes = [
            _stable_hash(pin.get("value"))
            for pin in self._context_pins()
            if str(pin.get("pin_id")) in selected
        ]
        self.state.metadata["retained_pin_hashes"] = hashes
