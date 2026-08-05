from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any

from .schema import RuntimeState


JsonDict = dict[str, Any]


_DEFAULT_PIN_PATHS: tuple[tuple[str, str], ...] = (
    ("identity", "task_id"),
    ("identity", "session_id"),
    ("identity", "run_id"),
    ("goal", "goal"),
    ("cursor", "execution_cursor"),
    ("cursor", "active_step"),
    ("status", "status"),
    ("process_lifecycle", "process_stage"),
    ("budget", "budget_state"),
    ("harness_policy", "policy_snapshot"),
    ("trace", "trace_id"),
    ("approval_boundary", "pending_tool_call"),
    ("approval_boundary", "approval_token"),
    ("skill_manifest", "active_skill_manifest"),
    ("failure_state", "failure_state"),
    ("artifact_lineage", "artifact_refs"),
)


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _json_size(value: object) -> int:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return len(payload.encode("utf-8"))


def _state_dict(state: RuntimeState | JsonDict) -> JsonDict:
    if isinstance(state, RuntimeState):
        return state.to_dict()
    return dict(state)


def _get_path(payload: JsonDict, path: str) -> object:
    current: object = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _is_empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


@dataclass(frozen=True, slots=True)
class CompactionPin:
    """A must-retain constraint when a state/context is compacted."""

    pin_id: str
    surface: str
    source_path: str | None = None
    expected_hash: str | None = None
    expected_payload: object | None = None
    required: bool = True
    description: str = ""
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def resolved_hash(self, source_state: JsonDict) -> str | None:
        if self.expected_hash is not None:
            return self.expected_hash
        if self.expected_payload is not None:
            return _stable_hash(self.expected_payload)
        if self.source_path is not None:
            value = _get_path(source_state, self.source_path)
            if _is_empty(value) and not self.required:
                return None
            return _stable_hash(value)
        return None


@dataclass(frozen=True, slots=True)
class CompactionDrift:
    """A missing or changed compaction pin."""

    pin_id: str
    surface: str
    reason: str
    expected_hash: str | None = None
    actual_hash: str | None = None
    source_path: str | None = None
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CompactionReport:
    """Governance-retention report for compacted Hermes state."""

    safe_to_resume: bool
    retained_pin_ids: list[str]
    missing_pin_ids: list[str]
    drifted_pin_ids: list[str]
    optional_missing_pin_ids: list[str]
    context_pin_ids: list[str]
    surfaces_at_risk: list[str]
    failures: list[str]
    warnings: list[str]
    drifts: list[CompactionDrift]
    original_bytes: int
    compacted_bytes: int
    compaction_ratio: float
    retained_pin_count: int
    required_pin_count: int
    original_fingerprint: str
    compacted_fingerprint: str
    report_fingerprint: str

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        data["drifts"] = [drift.to_dict() for drift in self.drifts]
        return data


class CompactionVerifier:
    """Checks whether compaction preserved resume-critical Harness/Hermes pins."""

    def verify(
        self,
        original: RuntimeState | JsonDict,
        compacted: RuntimeState | JsonDict,
        *,
        required_pins: list[CompactionPin] | None = None,
        include_default_pins: bool = True,
        include_context_pins: bool = True,
    ) -> CompactionReport:
        source = _state_dict(original)
        target = _state_dict(compacted)
        pins: list[CompactionPin] = []

        if include_default_pins:
            pins.extend(self._default_pins(source))
        pins.extend(required_pins or [])
        if include_context_pins:
            pins.extend(self._context_pins(source))

        retained: list[str] = []
        missing: list[str] = []
        drifted: list[str] = []
        optional_missing: list[str] = []
        drifts: list[CompactionDrift] = []
        failures: list[str] = []
        warnings: list[str] = []

        for pin in pins:
            expected_hash = pin.resolved_hash(source)
            actual_value = _get_path(target, pin.source_path) if pin.source_path else None
            actual_hash = _stable_hash(actual_value) if not _is_empty(actual_value) else None

            if pin.source_path is None:
                actual_hash = self._resolve_context_pin_hash(target, pin)

            if expected_hash is None:
                continue

            if actual_hash is None:
                reason = f"required pin missing: {pin.pin_id}" if pin.required else f"optional pin missing: {pin.pin_id}"
                if pin.required:
                    missing.append(pin.pin_id)
                    failures.append(reason)
                else:
                    optional_missing.append(pin.pin_id)
                    warnings.append(reason)
                drifts.append(
                    CompactionDrift(
                        pin_id=pin.pin_id,
                        surface=pin.surface,
                        reason=reason,
                        expected_hash=expected_hash,
                        actual_hash=None,
                        source_path=pin.source_path,
                        metadata=dict(pin.metadata),
                    )
                )
                continue

            if actual_hash != expected_hash:
                reason = f"pin drifted: {pin.pin_id}"
                if pin.required:
                    drifted.append(pin.pin_id)
                    failures.append(reason)
                else:
                    warnings.append(reason)
                drifts.append(
                    CompactionDrift(
                        pin_id=pin.pin_id,
                        surface=pin.surface,
                        reason=reason,
                        expected_hash=expected_hash,
                        actual_hash=actual_hash,
                        source_path=pin.source_path,
                        metadata=dict(pin.metadata),
                    )
                )
                continue

            retained.append(pin.pin_id)

        surfaces_at_risk = sorted({drift.surface for drift in drifts if drift.pin_id in set(missing + drifted)})
        original_bytes = _json_size(source)
        compacted_bytes = _json_size(target)
        required_pin_count = sum(1 for pin in pins if pin.required and pin.resolved_hash(source) is not None)
        compacted_ratio = round(compacted_bytes / original_bytes, 6) if original_bytes else 0.0
        payload = {
            "retained_pin_ids": retained,
            "missing_pin_ids": missing,
            "drifted_pin_ids": drifted,
            "optional_missing_pin_ids": optional_missing,
            "surfaces_at_risk": surfaces_at_risk,
            "original_fingerprint": _stable_hash(source),
            "compacted_fingerprint": _stable_hash(target),
        }

        return CompactionReport(
            safe_to_resume=not failures,
            retained_pin_ids=retained,
            missing_pin_ids=missing,
            drifted_pin_ids=drifted,
            optional_missing_pin_ids=optional_missing,
            context_pin_ids=[pin.pin_id for pin in pins if pin.metadata.get("pin_kind") == "context"],
            surfaces_at_risk=surfaces_at_risk,
            failures=failures,
            warnings=warnings,
            drifts=drifts,
            original_bytes=original_bytes,
            compacted_bytes=compacted_bytes,
            compaction_ratio=compacted_ratio,
            retained_pin_count=len(retained),
            required_pin_count=required_pin_count,
            original_fingerprint=_stable_hash(source),
            compacted_fingerprint=_stable_hash(target),
            report_fingerprint=_stable_hash(payload),
        )

    def _default_pins(self, source: JsonDict) -> list[CompactionPin]:
        pins: list[CompactionPin] = []
        for surface, path in _DEFAULT_PIN_PATHS:
            value = _get_path(source, path)
            if _is_empty(value):
                continue
            pins.append(
                CompactionPin(
                    pin_id=f"{surface}:{path}",
                    surface=surface,
                    source_path=path,
                    description=f"retain RuntimeState.{path}",
                )
            )
        return pins

    def _context_pins(self, source: JsonDict) -> list[CompactionPin]:
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        raw_pins = metadata.get("context_pins", [])
        pins: list[CompactionPin] = []
        for index, item in enumerate(raw_pins):
            if isinstance(item, dict):
                pin_id = str(item.get("pin_id") or item.get("id") or f"context-pin-{index}")
                value = item.get("value", item.get("text"))
                surface = str(item.get("surface") or "context")
                required = bool(item.get("required", True))
                description = str(item.get("description") or "")
            else:
                pin_id = f"context-pin-{index}"
                value = item
                surface = "context"
                required = True
                description = ""

            if _is_empty(value):
                continue

            pins.append(
                CompactionPin(
                    pin_id=f"context:{pin_id}",
                    surface=surface,
                    expected_payload=value,
                    required=required,
                    description=description,
                    metadata={"pin_kind": "context", "raw_pin_id": pin_id},
                )
            )
        return pins

    @staticmethod
    def _resolve_context_pin_hash(target: JsonDict, pin: CompactionPin) -> str | None:
        expected = pin.expected_payload
        metadata = target.get("metadata") if isinstance(target.get("metadata"), dict) else {}
        raw_pins = metadata.get("context_pins", [])

        for item in raw_pins:
            if isinstance(item, dict):
                item_id = str(item.get("pin_id") or item.get("id") or "")
                value = item.get("value", item.get("text"))
                if (
                    item_id == pin.metadata.get("raw_pin_id")
                    and not _is_empty(value)
                ):
                    return _stable_hash(value)

        summary = metadata.get("summary")
        if isinstance(expected, str) and isinstance(summary, str) and expected in summary:
            return _stable_hash(expected)

        retained_pin_hashes = metadata.get("retained_pin_hashes", [])
        if isinstance(retained_pin_hashes, list):
            expected_hash = _stable_hash(expected)
            if expected_hash in retained_pin_hashes:
                return expected_hash

        return None
