from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class SkillManifest:
    """Permission-bearing description of a reusable agent skill."""

    name: str
    version: str
    purpose: str
    context_influence: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    evidence_gates: list[str] = field(default_factory=list)
    fallback_paths: list[str] = field(default_factory=list)
    action_effects: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=True, sort_keys=True, default=str)
        return sha256(payload.encode("utf-8")).hexdigest()

    def permission_summary(self) -> JsonDict:
        return {
            "name": self.name,
            "version": self.version,
            "fingerprint": self.fingerprint(),
            "required_tools": list(self.required_tools),
            "required_capabilities": list(self.required_capabilities),
            "action_effects": list(self.action_effects),
        }

    def quality_warnings(self) -> list[str]:
        warnings: list[str] = []
        if not self.purpose.strip():
            warnings.append("missing:purpose")
        if not self.context_influence:
            warnings.append("missing:context_influence")
        if not self.required_tools:
            warnings.append("missing:required_tools")
        if not self.required_capabilities:
            warnings.append("missing:required_capabilities")
        if not self.evidence_gates:
            warnings.append("missing:evidence_gates")
        if not self.fallback_paths:
            warnings.append("missing:fallback_paths")
        if not self.action_effects:
            warnings.append("missing:action_effects")
        return warnings

    def to_skill_guard_manifest(self) -> JsonDict:
        return {
            "name": self.name,
            "version": self.version,
            "purpose": self.purpose,
            "permissions": {
                "context_influence": list(self.context_influence),
                "required_tools": list(self.required_tools),
                "required_capabilities": list(self.required_capabilities),
                "action_effects": list(self.action_effects),
            },
            "evidence_gates": list(self.evidence_gates),
            "fallback_paths": list(self.fallback_paths),
            "_meta": {
                "vibe_research/skillManifestHash": self.fingerprint(),
                "vibe_research/qualityWarnings": self.quality_warnings(),
                "vibe_research/dependencies": list(self.dependencies),
            },
        }

