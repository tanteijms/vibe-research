from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


JsonDict = dict[str, Any]


class TraceBoundary:
    LLM = "llm"
    TOOL = "tool"
    SANDBOX = "sandbox"
    APPROVAL = "approval"
    CHECKPOINT = "checkpoint"
    EVAL = "eval"


class ReceiptKind:
    ACTION = "action"
    APPROVAL = "approval"
    REPLAY = "replay"
    PROVIDER_CAPABILITY = "provider_capability"
    PROTOCOL_CAPABILITY = "protocol_capability"
    TOOL_CONTRACT = "tool_contract"
    SKILL_MANIFEST = "skill_manifest"
    EVIDENCE_LEDGER = "evidence_ledger"


@dataclass(frozen=True, slots=True)
class ProofReceipt:
    """Portable evidence attached to a trace event."""

    kind: str
    subject: str
    payload_hash: str
    issuer: str = "vibe-research"
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TraceEnvelope:
    """Trace v2 envelope for replayable, provider-aware harness events."""

    boundary: str
    task_id: str
    run_id: str
    cursor: str
    provider_name: str
    provider_fingerprint: str
    policy_fingerprint: str
    action_name: str
    action_effect: str
    input_hash: str
    schema_version: str = "trace-envelope-v2"
    protocol_name: str | None = None
    protocol_fingerprint: str | None = None
    tool_contract_fingerprint: str | None = None
    skill_name: str | None = None
    skill_manifest_fingerprint: str | None = None
    evidence_ledger_fingerprint: str | None = None
    evidence_claim_ids: list[str] = field(default_factory=list)
    output_hash: str | None = None
    artifact_refs: list[str] = field(default_factory=list)
    receipts: list[ProofReceipt] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        data["receipts"] = [receipt.to_dict() for receipt in self.receipts]
        return data

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=True, sort_keys=True, default=str)
        return sha256(payload.encode("utf-8")).hexdigest()


def hash_payload(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def make_action_receipt(*, action_name: str, input_payload: object, output_payload: object | None = None) -> ProofReceipt:
    payload = {
        "action_name": action_name,
        "input_hash": hash_payload(input_payload),
        "output_hash": hash_payload(output_payload) if output_payload is not None else None,
    }
    return ProofReceipt(kind=ReceiptKind.ACTION, subject=action_name, payload_hash=hash_payload(payload), metadata=payload)


def make_capability_receipt(*, kind: str, name: str, fingerprint: str) -> ProofReceipt:
    payload = {
        "name": name,
        "fingerprint": fingerprint,
    }
    return ProofReceipt(kind=kind, subject=name, payload_hash=hash_payload(payload), metadata=payload)


def make_skill_receipt(*, skill_name: str, fingerprint: str) -> ProofReceipt:
    payload = {
        "name": skill_name,
        "fingerprint": fingerprint,
    }
    return ProofReceipt(kind=ReceiptKind.SKILL_MANIFEST, subject=skill_name, payload_hash=hash_payload(payload), metadata=payload)


def make_evidence_receipt(*, ledger_name: str, fingerprint: str, claim_ids: list[str] | None = None) -> ProofReceipt:
    payload = {
        "name": ledger_name,
        "fingerprint": fingerprint,
        "claim_ids": sorted(claim_ids or []),
    }
    return ProofReceipt(kind=ReceiptKind.EVIDENCE_LEDGER, subject=ledger_name, payload_hash=hash_payload(payload), metadata=payload)
