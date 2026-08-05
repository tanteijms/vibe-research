from __future__ import annotations

from dataclasses import dataclass
import re

from .schema import HarnessPolicy, RuntimeState, ToolCall


@dataclass(frozen=True, slots=True)
class HarnessDecision:
    allowed: bool
    reason: str
    pause_for_approval: bool = False
    checkpoint_before_execute: bool = False


class PolicyHarness:
    """Runtime governance before and after every tool boundary."""

    def __init__(self, policy: HarnessPolicy | None = None):
        self.policy = policy or HarnessPolicy()

    def authorize_tool(self, state: RuntimeState, call: ToolCall, *, approved: bool = False) -> HarnessDecision:
        policy = self.policy
        if call.tool_name in policy.blocked_tools:
            return HarnessDecision(False, f"tool blocked by policy: {call.tool_name}")

        if policy.allowed_tools and call.tool_name not in policy.allowed_tools:
            return HarnessDecision(False, f"tool not in allowlist: {call.tool_name}")

        estimated_tokens = max(call.estimated_tokens, 0)
        estimated_cost = max(call.estimated_cost_usd, 0.0)

        if estimated_tokens > policy.max_tool_tokens:
            return HarnessDecision(False, f"tool token estimate exceeds per-call limit: {estimated_tokens}")

        if estimated_cost > policy.max_tool_cost_usd:
            return HarnessDecision(False, f"tool cost estimate exceeds per-call limit: {estimated_cost}")

        if not state.budget_state.can_spend(tokens=estimated_tokens, cost_usd=estimated_cost):
            return HarnessDecision(False, "task budget would be exceeded")

        timeout_s = call.timeout_s or policy.timeout_s_default
        if timeout_s > policy.timeout_s_limit:
            return HarnessDecision(False, f"timeout exceeds policy limit: {timeout_s}s")

        if call.effect in policy.require_approval_for_effects and not approved:
            return HarnessDecision(
                False,
                f"approval required for {call.effect} tool: {call.tool_name}",
                pause_for_approval=True,
                checkpoint_before_execute=True,
            )

        return HarnessDecision(True, "allowed")

    def spend_budget(self, state: RuntimeState, *, tokens: int, cost_usd: float) -> None:
        state.budget_state.spend(tokens=max(tokens, 0), cost_usd=max(cost_usd, 0.0))

    def sanitize_output(self, text: str) -> str:
        if not self.policy.redact_output:
            return text

        redacted = text
        for pattern in self.policy.secret_patterns:
            redacted = re.sub(pattern, "[REDACTED]", redacted)
        return redacted

