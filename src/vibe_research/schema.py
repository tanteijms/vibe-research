from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


JsonDict = dict[str, Any]


class RunStatus:
    READY = "ready"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"


class ToolEffect:
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"
    EXTERNAL = "external"


@dataclass(slots=True)
class BudgetState:
    token_limit: int = 50_000
    tokens_used: int = 0
    cost_limit_usd: float = 5.0
    cost_used_usd: float = 0.0

    def can_spend(self, *, tokens: int = 0, cost_usd: float = 0.0) -> bool:
        return (
            self.tokens_used + tokens <= self.token_limit
            and self.cost_used_usd + cost_usd <= self.cost_limit_usd
        )

    def spend(self, *, tokens: int = 0, cost_usd: float = 0.0) -> None:
        if not self.can_spend(tokens=tokens, cost_usd=cost_usd):
            raise ValueError("budget exceeded")
        self.tokens_used += tokens
        self.cost_used_usd = round(self.cost_used_usd + cost_usd, 8)

    @classmethod
    def from_dict(cls, data: JsonDict | None) -> "BudgetState":
        return cls(**(data or {}))


@dataclass(slots=True)
class HarnessPolicy:
    allowed_tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)
    require_approval_for_effects: list[str] = field(
        default_factory=lambda: [ToolEffect.WRITE, ToolEffect.EXECUTE, ToolEffect.NETWORK, ToolEffect.EXTERNAL]
    )
    max_tool_tokens: int = 8_000
    max_tool_cost_usd: float = 1.0
    timeout_s_default: int = 30
    timeout_s_limit: int = 300
    redact_output: bool = True
    secret_patterns: list[str] = field(
        default_factory=lambda: [
            r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"]?[^'\"\s]+",
            r"sk-[A-Za-z0-9_\-]{16,}",
        ]
    )

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: JsonDict | None) -> "HarnessPolicy":
        return cls(**(data or {}))


@dataclass(slots=True)
class ToolCall:
    tool_name: str
    args: JsonDict = field(default_factory=dict)
    effect: str = ToolEffect.READ
    estimated_tokens: int = 0
    estimated_cost_usd: float = 0.0
    timeout_s: int | None = None
    reason: str = ""

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: JsonDict) -> "ToolCall":
        return cls(**data)


@dataclass(slots=True)
class ArtifactRef:
    kind: str
    uri: str
    sha256: str | None = None
    metadata: JsonDict = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeState:
    task_id: str
    session_id: str
    run_id: str
    goal: str
    execution_cursor: str = "intake"
    active_step: str = "intake"
    status: str = RunStatus.READY
    process_stage: str = "dormant"
    budget_state: BudgetState = field(default_factory=BudgetState)
    policy_snapshot: JsonDict = field(default_factory=dict)
    checkpoint_ref: str | None = None
    artifact_refs: list[ArtifactRef] = field(default_factory=list)
    trace_id: str | None = None
    pending_tool_call: JsonDict | None = None
    active_skill_manifest: JsonDict | None = None
    approval_token: str | None = None
    failure_state: JsonDict | None = None
    version: int = 0
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        data["budget_state"] = asdict(self.budget_state)
        data["artifact_refs"] = [asdict(ref) for ref in self.artifact_refs]
        return data

    @classmethod
    def from_dict(cls, data: JsonDict) -> "RuntimeState":
        payload = dict(data)
        payload["budget_state"] = BudgetState.from_dict(payload.get("budget_state"))
        payload["artifact_refs"] = [ArtifactRef(**item) for item in payload.get("artifact_refs", [])]
        return cls(**payload)


@dataclass(slots=True)
class TraceEvent:
    event_id: str
    task_id: str
    run_id: str
    cursor: str
    kind: str
    data: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: JsonDict) -> "TraceEvent":
        return cls(**data)
