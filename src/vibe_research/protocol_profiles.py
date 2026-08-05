from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json


@dataclass(frozen=True, slots=True)
class ProtocolProfile:
    """Protocol-level capability snapshot for agent runtime integration."""

    name: str
    layer: str
    purpose: str
    primitives: list[str]
    state_policy: str
    governance_hooks: list[str]
    trace_hooks: list[str]
    runtime_implications: list[str]
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=True, sort_keys=True)
        return sha256(payload.encode("utf-8")).hexdigest()


MCP_2026_PROFILE = ProtocolProfile(
    name="mcp-2026-07-28",
    layer="agent-to-tools-and-data",
    purpose="Expose external tools, resources, prompts, and long-running tasks to agent runtimes.",
    primitives=[
        "tools/list",
        "tools/call",
        "resources/read",
        "prompts/list",
        "stateless request core",
        "multi round-trip requests",
        "cacheable list results",
        "tasks extension",
    ],
    state_policy=(
        "Do not rely on hidden transport sessions; stateful tools should mint explicit handles "
        "that the model can pass back."
    ),
    governance_hooks=[
        "header-based routing",
        "header-based rate limiting",
        "authorization issuer validation",
        "human confirmation for tool invocations",
        "input_required mid-call approvals",
    ],
    trace_hooks=[
        "tool schema fingerprint",
        "tool name and method headers",
        "input_required receipts",
        "cache ttl/scope",
        "task id and status",
    ],
    runtime_implications=[
        "Treat MCP tool metadata as a cached capability surface.",
        "Move long-running tool work into explicit task handles.",
        "Store tool schema hashes in replay records.",
        "Never hide resumable state only inside a transport session.",
    ],
    source_refs=[
        "https://blog.modelcontextprotocol.io/posts/2026-07-28/",
        "https://modelcontextprotocol.io/specification/2026-07-28/server/tools",
    ],
)


A2A_PROFILE = ProtocolProfile(
    name="a2a",
    layer="agent-to-agent",
    purpose="Let opaque agents from different frameworks delegate work and coordinate securely.",
    primitives=[
        "agent cards",
        "tasks",
        "messages",
        "artifacts",
        "extensions",
    ],
    state_policy="Remote agents keep their own memory and tools opaque; shared state crosses as tasks, messages, and artifacts.",
    governance_hooks=[
        "agent identity",
        "task delegation policy",
        "artifact boundary",
        "opaque capability contract",
    ],
    trace_hooks=[
        "remote agent id",
        "task id",
        "delegation receipt",
        "artifact refs",
    ],
    runtime_implications=[
        "Use A2A for specialist research agents only after the local harness can prove tool and artifact boundaries.",
        "Treat remote agents as governed tools until delegation receipts are reliable.",
    ],
    source_refs=[
        "https://a2a-protocol.org/latest/",
    ],
)


AG_UI_PROFILE = ProtocolProfile(
    name="ag-ui",
    layer="agent-to-user-interface",
    purpose="Stream structured agent state, UI intents, tool events, and human-in-the-loop controls to frontends.",
    primitives=[
        "events",
        "state diffs",
        "frontend tool calls",
        "interrupts",
        "agent steering",
        "sub-agent composition",
    ],
    state_policy="Frontend and runtime exchange event-sourced state updates rather than ad hoc chat-only messages.",
    governance_hooks=[
        "pause",
        "approve",
        "edit",
        "retry",
        "escalate",
        "cancel",
    ],
    trace_hooks=[
        "event id",
        "state patch",
        "tool event",
        "user steering event",
    ],
    runtime_implications=[
        "Design Harness approval inbox as an event stream, not a modal-only UI.",
        "Expose Hermes cursor and pending approval as typed frontend state.",
    ],
    source_refs=[
        "https://docs.ag-ui.com/introduction",
        "https://docs.ag-ui.com/concepts/events",
    ],
)


OTEL_GENAI_PROFILE = ProtocolProfile(
    name="opentelemetry-genai",
    layer="observability",
    purpose="Standardize traces, metrics, and logs for LLM calls, tools, retrieval, and agent workflows.",
    primitives=[
        "spans",
        "metrics",
        "logs",
        "semantic attributes",
        "agent framework conventions",
    ],
    state_policy="Runtime-owned observability should be decoupled from provider-specific trace formats.",
    governance_hooks=[
        "trace export policy",
        "redaction policy",
        "vendor-neutral span mapping",
    ],
    trace_hooks=[
        "model span",
        "retrieval span",
        "tool span",
        "agent task span",
        "artifact refs",
    ],
    runtime_implications=[
        "Map TraceEnvelope to OpenTelemetry later instead of inventing an isolated trace universe.",
        "Keep provider-native trace ids as metadata, not as the canonical trace contract.",
    ],
    source_refs=[
        "https://opentelemetry.io/blog/2025/ai-agent-observability/",
        "https://github.com/open-telemetry/semantic-conventions-genai",
    ],
)


PROTOCOL_PROFILES = {
    profile.name: profile
    for profile in [
        MCP_2026_PROFILE,
        A2A_PROFILE,
        AG_UI_PROFILE,
        OTEL_GENAI_PROFILE,
    ]
}


def get_protocol_profile(name: str) -> ProtocolProfile:
    aliases = {
        "mcp": "mcp-2026-07-28",
        "mcp-2026": "mcp-2026-07-28",
        "agent2agent": "a2a",
        "agent-to-agent": "a2a",
        "agui": "ag-ui",
        "otel": "opentelemetry-genai",
        "opentelemetry": "opentelemetry-genai",
    }
    key = aliases.get(name.lower(), name.lower())
    if key in PROTOCOL_PROFILES:
        return PROTOCOL_PROFILES[key]
    raise KeyError(f"unknown protocol profile: {name}")

