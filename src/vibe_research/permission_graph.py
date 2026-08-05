from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


JsonDict = dict[str, Any]


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _matches_resource(pattern: str, resource: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith("*"):
        return resource.startswith(pattern[:-1])
    return resource == pattern


@dataclass(frozen=True, slots=True)
class AuthorityWitness:
    """Evidence that a subject is allowed to commit a bounded effect."""

    witness_id: str
    subject: str
    effect: str
    resource_pattern: str = "*"
    issued_at_version: int = 0
    expires_after_version: int | None = None
    revoked: bool = False
    evidence_refs: list[str] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def validation_failures(self, *, subject: str, effect: str, resource: str, checkpoint_version: int) -> list[str]:
        failures: list[str] = []
        if self.revoked:
            failures.append(f"witness revoked: {self.witness_id}")
        if self.subject not in (subject, "*"):
            failures.append(f"witness subject mismatch: {self.subject} != {subject}")
        if self.effect != effect:
            failures.append(f"witness effect mismatch: {self.effect} != {effect}")
        if not _matches_resource(self.resource_pattern, resource):
            failures.append(f"witness resource mismatch: {self.resource_pattern} !~ {resource}")
        if self.issued_at_version > checkpoint_version:
            failures.append(f"witness is from the future: {self.issued_at_version} > {checkpoint_version}")
        if self.expires_after_version is not None and checkpoint_version > self.expires_after_version:
            failures.append(f"witness expired at version {self.expires_after_version}")
        return failures


@dataclass(frozen=True, slots=True)
class PermissionGrant:
    """A reusable policy edge from subject to effectful resource access."""

    grant_id: str
    subject: str
    effects: list[str]
    resource_pattern: str = "*"
    requires_witness: bool = False
    allowed_input_labels: list[str] = field(default_factory=list)
    forbidden_input_labels: list[str] = field(default_factory=list)
    purpose: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def matches_action(self, *, subject: str, effect: str, resource: str) -> bool:
        return (
            self.subject in (subject, "*")
            and effect in self.effects
            and _matches_resource(self.resource_pattern, resource)
        )

    def label_failures(self, input_labels: list[str]) -> list[str]:
        failures: list[str] = []
        forbidden = sorted(set(input_labels).intersection(self.forbidden_input_labels))
        if forbidden:
            failures.append(f"forbidden input labels present: {', '.join(forbidden)}")

        if self.allowed_input_labels:
            allowed = set(self.allowed_input_labels)
            unexpected = sorted(label for label in set(input_labels) if label not in allowed)
            if unexpected:
                failures.append(f"input labels outside allowlist: {', '.join(unexpected)}")

        return failures


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    """Authorization result with replayable counterexamples."""

    allowed: bool
    subject: str
    effect: str
    resource: str
    input_labels: list[str]
    matched_grant_ids: list[str] = field(default_factory=list)
    witness_ids: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    counterexamples: list[JsonDict] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def receipt_payload(self) -> JsonDict:
        return {
            "allowed": self.allowed,
            "subject": self.subject,
            "effect": self.effect,
            "resource": self.resource,
            "input_labels": list(self.input_labels),
            "matched_grant_ids": list(self.matched_grant_ids),
            "witness_ids": list(self.witness_ids),
            "failures_hash": _stable_hash(self.failures),
            "counterexamples_hash": _stable_hash(self.counterexamples),
            "fingerprint": self.fingerprint(),
        }


@dataclass(slots=True)
class PermissionGraph:
    """Small permission graph for data-flow-aware Harness authorization."""

    grants: list[PermissionGrant] = field(default_factory=list)
    witnesses: list[AuthorityWitness] = field(default_factory=list)
    context_labels: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return {
            "grants": [grant.to_dict() for grant in self.grants],
            "witnesses": [witness.to_dict() for witness in self.witnesses],
            "context_labels": {key: list(value) for key, value in sorted(self.context_labels.items())},
        }

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def label_context(self, context_id: str, labels: list[str]) -> None:
        self.context_labels[context_id] = sorted(set(labels))

    def labels_for(self, context_ids: list[str] | tuple[str, ...]) -> list[str]:
        labels: set[str] = set()
        for context_id in context_ids:
            labels.update(self.context_labels.get(context_id, []))
        return sorted(labels)

    def authorize_action(
        self,
        *,
        subject: str,
        effect: str,
        resource: str,
        input_contexts: list[str] | tuple[str, ...] = (),
        checkpoint_version: int = 0,
    ) -> PermissionDecision:
        input_labels = self.labels_for(input_contexts)
        matching_grants = [
            grant
            for grant in self.grants
            if grant.matches_action(subject=subject, effect=effect, resource=resource)
        ]

        if not matching_grants:
            return PermissionDecision(
                allowed=False,
                subject=subject,
                effect=effect,
                resource=resource,
                input_labels=input_labels,
                failures=[f"no permission grant for {subject}:{effect}:{resource}"],
            )

        failures: list[str] = []
        counterexamples: list[JsonDict] = []
        for grant in matching_grants:
            grant_failures = grant.label_failures(input_labels)
            witness_ids: list[str] = []

            if grant.requires_witness:
                valid_witnesses = []
                witness_counterexamples = []
                for witness in self.witnesses:
                    witness_failures = witness.validation_failures(
                        subject=subject,
                        effect=effect,
                        resource=resource,
                        checkpoint_version=checkpoint_version,
                    )
                    if not witness_failures:
                        valid_witnesses.append(witness)
                    elif witness.subject in (subject, "*") and witness.effect == effect:
                        witness_counterexamples.append(
                            {
                                "witness_id": witness.witness_id,
                                "failures": witness_failures,
                            }
                        )

                if valid_witnesses:
                    witness_ids = [witness.witness_id for witness in valid_witnesses]
                else:
                    grant_failures.append(f"no valid authority witness for grant: {grant.grant_id}")
                    counterexamples.extend(witness_counterexamples)

            if not grant_failures:
                return PermissionDecision(
                    allowed=True,
                    subject=subject,
                    effect=effect,
                    resource=resource,
                    input_labels=input_labels,
                    matched_grant_ids=[grant.grant_id],
                    witness_ids=witness_ids,
                )

            failures.extend(f"grant {grant.grant_id}: {failure}" for failure in grant_failures)
            counterexamples.append(
                {
                    "grant_id": grant.grant_id,
                    "failures": grant_failures,
                    "input_labels": input_labels,
                }
            )

        return PermissionDecision(
            allowed=False,
            subject=subject,
            effect=effect,
            resource=resource,
            input_labels=input_labels,
            matched_grant_ids=[grant.grant_id for grant in matching_grants],
            failures=failures,
            counterexamples=counterexamples,
        )
