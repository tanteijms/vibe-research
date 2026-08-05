from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolDescriptionContract:
    """Structured tool description used before exposing a tool to an agent."""

    name: str
    purpose: str = ""
    input_schema: JsonDict = field(default_factory=dict)
    output_schema: JsonDict = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=True, sort_keys=True, default=str)
        return sha256(payload.encode("utf-8")).hexdigest()

    def missing_components(self) -> list[str]:
        missing: list[str] = []
        if not self.purpose.strip():
            missing.append("purpose")
        if not self.input_schema:
            missing.append("input_schema")
        if not self.output_schema:
            missing.append("output_schema")
        if not self.limitations:
            missing.append("limitations")
        if not self.side_effects:
            missing.append("side_effects")
        if not self.failure_modes:
            missing.append("failure_modes")
        return missing

    def quality_warnings(self) -> list[str]:
        warnings = [f"missing:{component}" for component in self.missing_components()]
        if len(self.purpose.split()) < 4:
            warnings.append("purpose_too_short")
        if self.examples and len(json.dumps(self.examples, ensure_ascii=True)) > 1200:
            warnings.append("examples_too_large_for_default_context")
        return warnings

    def compact_context(self, *, include_examples: bool = False) -> str:
        parts = [
            f"Tool: {self.name}",
            f"Purpose: {self.purpose or 'UNSPECIFIED'}",
            f"Inputs: {json.dumps(self.input_schema, ensure_ascii=True, sort_keys=True)}",
            f"Outputs: {json.dumps(self.output_schema, ensure_ascii=True, sort_keys=True)}",
            f"Limitations: {'; '.join(self.limitations) or 'UNSPECIFIED'}",
            f"Side effects: {'; '.join(self.side_effects) or 'UNSPECIFIED'}",
            f"Failure modes: {'; '.join(self.failure_modes) or 'UNSPECIFIED'}",
        ]
        if include_examples and self.examples:
            parts.append(f"Examples: {' | '.join(self.examples)}")
        return "\n".join(parts)

    def to_mcp_metadata(self, *, include_examples: bool = False) -> JsonDict:
        description = self.compact_context(include_examples=include_examples)
        return {
            "name": self.name,
            "description": description,
            "inputSchema": self.input_schema,
            "_meta": {
                "vibe_research/toolContractHash": self.fingerprint(),
                "vibe_research/qualityWarnings": self.quality_warnings(),
            },
        }

