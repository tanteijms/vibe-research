from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


JsonDict = dict[str, Any]


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


class EvidenceKind:
    SOURCE = "source"
    ARTIFACT = "artifact"
    OBSERVATION = "observation"
    DERIVED = "derived"
    REVIEW = "review"


class EvidenceStatus:
    ACTIVE = "active"
    QUARANTINED = "quarantined"
    RETRACTED = "retracted"


@dataclass(frozen=True, slots=True)
class EvidenceEntry:
    """A durable, provenance-bearing item that can support research claims."""

    entry_id: str
    kind: str
    source_ref: str
    content_hash: str = ""
    status: str = EvidenceStatus.ACTIVE
    labels: list[str] = field(default_factory=list)
    parent_entry_ids: list[str] = field(default_factory=list)
    produced_by_transition_id: str | None = None
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    """A claim that may only become actionable through ledger-backed evidence."""

    claim_id: str
    statement: str
    cited_entry_ids: list[str] = field(default_factory=list)
    required_labels: list[str] = field(default_factory=list)
    status: str = "accepted"
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class EvidenceLedgerReport:
    """Soundness report for source-backed claims and derived evidence lineage."""

    sound: bool
    active_entry_count: int
    claim_count: int
    missing_required_claim_ids: list[str] = field(default_factory=list)
    unsupported_claim_ids: list[str] = field(default_factory=list)
    missing_citation_ids: list[str] = field(default_factory=list)
    inactive_citation_ids: list[str] = field(default_factory=list)
    forbidden_label_claim_ids: list[str] = field(default_factory=list)
    orphan_derived_entry_ids: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ledger_fingerprint: str = ""

    def to_dict(self) -> JsonDict:
        return asdict(self)


class EvidenceLedger:
    """Structured evidence ledger for research-session claims and citations."""

    def __init__(
        self,
        *,
        entries: list[EvidenceEntry] | None = None,
        claims: list[EvidenceClaim] | None = None,
    ):
        self.entries: dict[str, EvidenceEntry] = {}
        self.claims: dict[str, EvidenceClaim] = {}
        for entry in entries or []:
            self.add_entry(entry)
        for claim in claims or []:
            self.add_claim(claim)

    def add_entry(self, entry: EvidenceEntry) -> None:
        if entry.entry_id in self.entries:
            raise ValueError(f"duplicate evidence entry: {entry.entry_id}")
        self.entries[entry.entry_id] = entry

    def add_claim(self, claim: EvidenceClaim) -> None:
        if claim.claim_id in self.claims:
            raise ValueError(f"duplicate evidence claim: {claim.claim_id}")
        self.claims[claim.claim_id] = claim

    def active_entries(self) -> list[EvidenceEntry]:
        return [entry for entry in self.entries.values() if entry.status == EvidenceStatus.ACTIVE]

    def lineage_for(self, entry_id: str) -> list[str]:
        if entry_id not in self.entries:
            return []

        lineage: list[str] = []
        seen: set[str] = set()

        def visit(current_id: str) -> None:
            if current_id in seen or current_id not in self.entries:
                return
            seen.add(current_id)
            entry = self.entries[current_id]
            for parent_id in entry.parent_entry_ids:
                visit(parent_id)
            lineage.append(current_id)

        visit(entry_id)
        return lineage

    def evaluate(
        self,
        *,
        required_claim_ids: list[str] | None = None,
        forbidden_evidence_labels: list[str] | None = None,
    ) -> EvidenceLedgerReport:
        required = set(required_claim_ids or [])
        forbidden_labels = set(forbidden_evidence_labels or [])
        failures: list[str] = []
        warnings: list[str] = []
        missing_required_claim_ids = sorted(required.difference(self.claims))
        unsupported_claim_ids: list[str] = []
        missing_citation_ids: list[str] = []
        inactive_citation_ids: list[str] = []
        forbidden_label_claim_ids: list[str] = []
        orphan_derived_entry_ids: list[str] = []

        for claim_id in missing_required_claim_ids:
            failures.append(f"missing required claim: {claim_id}")

        for entry in self.entries.values():
            parent_failures = self._entry_parent_failures(entry)
            if parent_failures:
                orphan_derived_entry_ids.append(entry.entry_id)
                failures.extend(parent_failures)

        for claim in self.claims.values():
            claim_failures: list[str] = []
            if claim.status == "accepted" and not claim.cited_entry_ids:
                claim_failures.append(f"accepted claim has no citations: {claim.claim_id}")

            cited_labels: set[str] = set()
            for entry_id in claim.cited_entry_ids:
                entry = self.entries.get(entry_id)
                if entry is None:
                    missing_citation_ids.append(entry_id)
                    claim_failures.append(f"claim cites missing evidence: {claim.claim_id} -> {entry_id}")
                    continue
                if entry.status != EvidenceStatus.ACTIVE:
                    inactive_citation_ids.append(entry_id)
                    claim_failures.append(
                        f"claim cites inactive evidence: {claim.claim_id} -> {entry_id}:{entry.status}"
                    )
                cited_labels.update(entry.labels)

            missing_labels = sorted(set(claim.required_labels).difference(cited_labels))
            if missing_labels:
                claim_failures.append(
                    f"claim missing required evidence labels: {claim.claim_id}:{', '.join(missing_labels)}"
                )

            forbidden_present = sorted(forbidden_labels.intersection(cited_labels))
            if forbidden_present:
                forbidden_label_claim_ids.append(claim.claim_id)
                claim_failures.append(
                    f"claim cites forbidden evidence labels: {claim.claim_id}:{', '.join(forbidden_present)}"
                )

            if claim_failures:
                unsupported_claim_ids.append(claim.claim_id)
                failures.extend(claim_failures)

        if not self.entries:
            warnings.append("evidence ledger has no entries")
        if not self.claims:
            warnings.append("evidence ledger has no claims")

        return EvidenceLedgerReport(
            sound=not failures,
            active_entry_count=len(self.active_entries()),
            claim_count=len(self.claims),
            missing_required_claim_ids=missing_required_claim_ids,
            unsupported_claim_ids=sorted(set(unsupported_claim_ids)),
            missing_citation_ids=sorted(set(missing_citation_ids)),
            inactive_citation_ids=sorted(set(inactive_citation_ids)),
            forbidden_label_claim_ids=sorted(set(forbidden_label_claim_ids)),
            orphan_derived_entry_ids=sorted(set(orphan_derived_entry_ids)),
            failures=failures,
            warnings=warnings,
            ledger_fingerprint=self.fingerprint(),
        )

    def to_dict(self) -> JsonDict:
        return {
            "entries": [entry.to_dict() for entry in sorted(self.entries.values(), key=lambda item: item.entry_id)],
            "claims": [claim.to_dict() for claim in sorted(self.claims.values(), key=lambda item: item.claim_id)],
        }

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def _entry_parent_failures(self, entry: EvidenceEntry) -> list[str]:
        if entry.kind != EvidenceKind.DERIVED and not entry.parent_entry_ids:
            return []

        failures: list[str] = []
        if entry.kind == EvidenceKind.DERIVED and not entry.parent_entry_ids:
            failures.append(f"derived evidence has no parent entries: {entry.entry_id}")

        for parent_id in entry.parent_entry_ids:
            parent = self.entries.get(parent_id)
            if parent is None:
                failures.append(f"evidence parent missing: {entry.entry_id} -> {parent_id}")
            elif parent.status != EvidenceStatus.ACTIVE:
                failures.append(f"evidence parent inactive: {entry.entry_id} -> {parent_id}:{parent.status}")
        return failures
