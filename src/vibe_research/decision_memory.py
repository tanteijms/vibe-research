from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any, Iterable

from .memory_commit import MemoryRecord, MemoryStatus


JsonDict = dict[str, Any]


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _normalized_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


@dataclass(frozen=True, slots=True)
class DecisionMemoryProjectionReport:
    """A task-conditioned view projected from an append-only memory log."""

    task_context: JsonDict
    selected_record_ids: list[str]
    excluded_record_ids: list[str]
    exclusion_reasons: dict[str, list[str]]
    source_log_fingerprint: str
    projection_fingerprint: str
    selected_record_count: int
    source_record_count: int

    def to_dict(self) -> JsonDict:
        return asdict(self)


class DecisionMemoryProjection:
    """Stateless Decision Memory-style projection over committed records."""

    def project(
        self,
        records: Iterable[MemoryRecord],
        *,
        task_context: JsonDict | None = None,
        required_kinds: list[str] | None = None,
        required_source_refs: list[str] | None = None,
        query_terms: list[str] | None = None,
        include_retracted: bool = False,
    ) -> DecisionMemoryProjectionReport:
        task_context = dict(task_context or {})
        required_kinds = list(required_kinds or [])
        required_source_refs = list(required_source_refs or [])
        query_terms = list(query_terms or _normalized_terms(task_context.get("query_terms")))
        record_list = list(records)
        selected_record_ids: list[str] = []
        excluded_record_ids: list[str] = []
        exclusion_reasons: dict[str, list[str]] = {}

        for record in record_list:
            reasons: list[str] = []
            if record.status != MemoryStatus.COMMITTED:
                if record.status == MemoryStatus.RETRACTED and include_retracted:
                    pass
                else:
                    reasons.append(f"record is not committed: {record.record_id} ({record.status})")

            if required_kinds and record.kind not in required_kinds:
                reasons.append(f"kind mismatch: {record.kind}")

            if required_source_refs:
                source_refs = set(record.source_refs)
                missing = [ref for ref in required_source_refs if ref not in source_refs]
                if missing:
                    reasons.append(f"missing source refs: {', '.join(missing)}")

            if query_terms:
                haystack = json.dumps(record.to_dict(), ensure_ascii=True, sort_keys=True, default=str).lower()
                if not any(term.lower() in haystack for term in query_terms):
                    reasons.append(f"query terms not found: {', '.join(query_terms)}")

            if reasons:
                excluded_record_ids.append(record.record_id)
                exclusion_reasons[record.record_id] = reasons
            else:
                selected_record_ids.append(record.record_id)

        source_log_fingerprint = _stable_hash([record.to_dict() for record in record_list])
        projection_fingerprint = _stable_hash(
            {
                "task_context": task_context,
                "selected_record_ids": selected_record_ids,
                "excluded_record_ids": excluded_record_ids,
                "exclusion_reasons": exclusion_reasons,
            }
        )

        return DecisionMemoryProjectionReport(
            task_context=task_context,
            selected_record_ids=selected_record_ids,
            excluded_record_ids=excluded_record_ids,
            exclusion_reasons=exclusion_reasons,
            source_log_fingerprint=source_log_fingerprint,
            projection_fingerprint=projection_fingerprint,
            selected_record_count=len(selected_record_ids),
            source_record_count=len(record_list),
        )
