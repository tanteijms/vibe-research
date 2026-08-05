from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any

from .schema import RuntimeState, TraceEvent


JsonDict = dict[str, Any]


def _serialized_bytes(value: object) -> int:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return len(payload.encode("utf-8"))


def _stable_digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FootprintReport:
    """Storage and replay footprint for a checkpointable runtime slice."""

    state_bytes: int
    events_bytes: int
    artifact_refs_bytes: int
    metadata_bytes: int
    active_skill_manifest_bytes: int
    trace_envelope_bytes: int
    total_checkpoint_bytes: int
    event_count: int
    artifact_count: int
    trace_envelope_count: int
    state_fingerprint: str
    events_fingerprint: str
    channel_bytes: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)


class FootprintMeter:
    """Measures the durable state surface that Hermes must keep replayable."""

    def measure(self, state: RuntimeState, events: list[TraceEvent]) -> FootprintReport:
        state_payload = state.to_dict()
        events_payload = [event.to_dict() for event in events]
        artifact_payload = state_payload.get("artifact_refs", [])
        metadata_payload = state_payload.get("metadata", {})
        skill_payload = state_payload.get("active_skill_manifest") or {}
        trace_envelopes = [
            event.data["trace_envelope"]
            for event in events
            if isinstance(event.data, dict) and isinstance(event.data.get("trace_envelope"), dict)
        ]

        state_bytes = _serialized_bytes(state_payload)
        events_bytes = _serialized_bytes(events_payload)
        artifact_refs_bytes = _serialized_bytes(artifact_payload)
        metadata_bytes = _serialized_bytes(metadata_payload)
        active_skill_manifest_bytes = _serialized_bytes(skill_payload) if skill_payload else 0
        trace_envelope_bytes = _serialized_bytes(trace_envelopes) if trace_envelopes else 0

        channel_bytes = {
            "state": state_bytes,
            "events": events_bytes,
            "artifact_refs": artifact_refs_bytes,
            "metadata": metadata_bytes,
            "active_skill_manifest": active_skill_manifest_bytes,
            "trace_envelopes": trace_envelope_bytes,
        }

        return FootprintReport(
            state_bytes=state_bytes,
            events_bytes=events_bytes,
            artifact_refs_bytes=artifact_refs_bytes,
            metadata_bytes=metadata_bytes,
            active_skill_manifest_bytes=active_skill_manifest_bytes,
            trace_envelope_bytes=trace_envelope_bytes,
            total_checkpoint_bytes=state_bytes + events_bytes,
            event_count=len(events),
            artifact_count=len(artifact_payload),
            trace_envelope_count=len(trace_envelopes),
            state_fingerprint=_stable_digest(state_payload),
            events_fingerprint=_stable_digest(events_payload),
            channel_bytes=channel_bytes,
        )
