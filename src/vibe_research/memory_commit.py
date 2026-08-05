from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4


JsonDict = dict[str, Any]


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


class MemoryStatus:
    STAGED = "staged"
    VALIDATED = "validated"
    COMMITTED = "committed"
    REJECTED = "rejected"
    RETRACTED = "retracted"


class MemoryKind:
    OBSERVATION = "observation"
    BELIEF = "belief"
    ARTIFACT = "artifact"
    RULE = "rule"


@dataclass(frozen=True, slots=True)
class ValidationReceipt:
    """Evidence that a staged memory record is safe to commit."""

    validator: str
    passed: bool
    reasons: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    checkpoint_version: int = 0
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(slots=True)
class MemoryRecord:
    """A durable-but-not-necessarily-committed memory or artifact fact."""

    record_id: str
    kind: str
    payload: JsonDict
    status: str = MemoryStatus.STAGED
    source_refs: list[str] = field(default_factory=list)
    parent_record_ids: list[str] = field(default_factory=list)
    permission_decision_ref: str | None = None
    created_in_transaction: str | None = None
    committed_in_transaction: str | None = None
    validation_receipts: list[ValidationReceipt] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        data["validation_receipts"] = [receipt.to_dict() for receipt in self.validation_receipts]
        return data

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def has_failed_validation(self) -> bool:
        return any(not receipt.passed for receipt in self.validation_receipts)

    def has_passing_validation(self) -> bool:
        return any(receipt.passed for receipt in self.validation_receipts)


@dataclass(slots=True)
class MemoryTransaction:
    """A staged memory-write unit that can be validated, committed, or aborted."""

    transaction_id: str
    status: str = "open"
    staged_record_ids: list[str] = field(default_factory=list)
    created_at_version: int = 0
    closed_at_version: int | None = None
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class MemoryCommitReport:
    transaction_id: str
    committed_record_ids: list[str] = field(default_factory=list)
    rejected_record_ids: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def committed(self) -> bool:
        return not self.failures and bool(self.committed_record_ids)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class MemorySafetyReport:
    safe: bool
    record_ids: list[str]
    unsafe_record_ids: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CascadeRetractReport:
    root_record_id: str
    retracted_record_ids: list[str]
    reason: str

    def to_dict(self) -> JsonDict:
        return asdict(self)


class MemoryCommitProtocol:
    """MemTX-inspired staged memory write and belief commit protocol."""

    def __init__(self):
        self.records: dict[str, MemoryRecord] = {}
        self.transactions: dict[str, MemoryTransaction] = {}

    def begin_transaction(
        self,
        *,
        transaction_id: str | None = None,
        checkpoint_version: int = 0,
        metadata: JsonDict | None = None,
    ) -> MemoryTransaction:
        tx_id = transaction_id or f"memtx_{uuid4().hex[:12]}"
        if tx_id in self.transactions:
            raise ValueError(f"memory transaction already exists: {tx_id}")
        transaction = MemoryTransaction(
            transaction_id=tx_id,
            created_at_version=checkpoint_version,
            metadata=dict(metadata or {}),
        )
        self.transactions[tx_id] = transaction
        return transaction

    def stage_record(
        self,
        transaction_id: str,
        *,
        record_id: str | None = None,
        kind: str = MemoryKind.BELIEF,
        payload: JsonDict | None = None,
        source_refs: list[str] | None = None,
        parent_record_ids: list[str] | None = None,
        permission_decision_ref: str | None = None,
        metadata: JsonDict | None = None,
    ) -> MemoryRecord:
        transaction = self._open_transaction(transaction_id)
        selected_id = record_id or f"mem_{uuid4().hex[:12]}"
        if selected_id in self.records:
            raise ValueError(f"memory record already exists: {selected_id}")

        record = MemoryRecord(
            record_id=selected_id,
            kind=kind,
            payload=dict(payload or {}),
            source_refs=list(source_refs or []),
            parent_record_ids=list(parent_record_ids or []),
            permission_decision_ref=permission_decision_ref,
            created_in_transaction=transaction_id,
            metadata=dict(metadata or {}),
        )
        self.records[selected_id] = record
        transaction.staged_record_ids.append(selected_id)
        return record

    def validate_record(self, record_id: str, receipt: ValidationReceipt) -> MemoryRecord:
        record = self._record(record_id)
        if record.status in (MemoryStatus.COMMITTED, MemoryStatus.RETRACTED):
            raise ValueError(f"cannot validate {record.status} memory record: {record_id}")
        record.validation_receipts.append(receipt)
        record.status = MemoryStatus.VALIDATED if receipt.passed else MemoryStatus.REJECTED
        return record

    def commit(self, transaction_id: str, *, checkpoint_version: int = 0) -> MemoryCommitReport:
        transaction = self._open_transaction(transaction_id)
        committed: list[str] = []
        rejected: list[str] = []
        failures: list[str] = []

        for record_id in transaction.staged_record_ids:
            record = self._record(record_id)
            if record.status == MemoryStatus.REJECTED or record.has_failed_validation():
                rejected.append(record_id)
                failures.append(f"record rejected by validation: {record_id}")
                continue

            if not record.has_passing_validation():
                rejected.append(record_id)
                failures.append(f"record has no passing validation receipt: {record_id}")
                continue

            missing_parents = [
                parent_id
                for parent_id in record.parent_record_ids
                if self.records.get(parent_id) is None or self.records[parent_id].status != MemoryStatus.COMMITTED
            ]
            if missing_parents:
                rejected.append(record_id)
                failures.append(f"record has uncommitted parent(s): {record_id} <- {', '.join(missing_parents)}")
                continue

            record.status = MemoryStatus.COMMITTED
            record.committed_in_transaction = transaction_id
            committed.append(record_id)

        transaction.status = "committed" if committed and not failures else "rejected"
        transaction.closed_at_version = checkpoint_version
        return MemoryCommitReport(
            transaction_id=transaction_id,
            committed_record_ids=committed,
            rejected_record_ids=rejected,
            failures=failures,
        )

    def abort(self, transaction_id: str, *, reason: str = "") -> MemoryCommitReport:
        transaction = self._open_transaction(transaction_id)
        rejected: list[str] = []
        for record_id in transaction.staged_record_ids:
            record = self._record(record_id)
            if record.status not in (MemoryStatus.COMMITTED, MemoryStatus.RETRACTED):
                record.status = MemoryStatus.REJECTED
                record.metadata["abort_reason"] = reason
                rejected.append(record_id)

        transaction.status = "aborted"
        return MemoryCommitReport(
            transaction_id=transaction_id,
            rejected_record_ids=rejected,
            failures=[reason] if reason else [],
        )

    def safety_gate(self, record_ids: list[str]) -> MemorySafetyReport:
        failures: list[str] = []
        unsafe: list[str] = []
        for record_id in record_ids:
            record = self.records.get(record_id)
            if record is None:
                unsafe.append(record_id)
                failures.append(f"unknown memory record: {record_id}")
                continue
            if record.status != MemoryStatus.COMMITTED:
                unsafe.append(record_id)
                failures.append(f"record is not committed: {record_id} ({record.status})")

        return MemorySafetyReport(
            safe=not failures,
            record_ids=list(record_ids),
            unsafe_record_ids=unsafe,
            failures=failures,
        )

    def cascade_retract(self, root_record_id: str, *, reason: str) -> CascadeRetractReport:
        if root_record_id not in self.records:
            raise KeyError(f"unknown memory record: {root_record_id}")

        to_visit = [root_record_id]
        retracted: list[str] = []
        while to_visit:
            record_id = to_visit.pop(0)
            record = self.records[record_id]
            if record.status == MemoryStatus.RETRACTED:
                continue
            record.status = MemoryStatus.RETRACTED
            record.metadata["retract_reason"] = reason
            retracted.append(record_id)
            for candidate in self.records.values():
                if record_id in candidate.parent_record_ids:
                    to_visit.append(candidate.record_id)

        return CascadeRetractReport(
            root_record_id=root_record_id,
            retracted_record_ids=retracted,
            reason=reason,
        )

    def to_dict(self) -> JsonDict:
        return {
            "records": {key: record.to_dict() for key, record in sorted(self.records.items())},
            "transactions": {key: transaction.to_dict() for key, transaction in sorted(self.transactions.items())},
        }

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def _record(self, record_id: str) -> MemoryRecord:
        if record_id not in self.records:
            raise KeyError(f"unknown memory record: {record_id}")
        return self.records[record_id]

    def _open_transaction(self, transaction_id: str) -> MemoryTransaction:
        if transaction_id not in self.transactions:
            raise KeyError(f"unknown memory transaction: {transaction_id}")
        transaction = self.transactions[transaction_id]
        if transaction.status != "open":
            raise ValueError(f"memory transaction is not open: {transaction_id} ({transaction.status})")
        return transaction
