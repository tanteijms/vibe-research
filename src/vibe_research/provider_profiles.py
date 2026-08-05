from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    """Capability snapshot for a model/runtime provider at a harness boundary."""

    name: str
    api_style: str
    tool_modes: list[str]
    state_surfaces: list[str]
    governance_surfaces: list[str]
    trace_surfaces: list[str]
    eval_surfaces: list[str]
    sandbox_surfaces: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    harness_hooks: list[str] = field(default_factory=list)
    runtime_caveats: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=True, sort_keys=True)
        return sha256(payload.encode("utf-8")).hexdigest()

    def checkpoint_snapshot(self) -> dict[str, object]:
        data = self.to_dict()
        data["fingerprint"] = self.fingerprint()
        return data


OPENAI_PROFILE = ProviderProfile(
    name="openai",
    api_style="responses-api + agents-sdk + sandbox-agents",
    tool_modes=[
        "function tools",
        "hosted tools",
        "MCP tools",
        "programmatic tool calling",
        "agents-as-tools",
    ],
    state_surfaces=[
        "Responses conversation state",
        "Agents SDK sessions",
        "sandbox session state",
        "sandbox memory files",
    ],
    governance_surfaces=[
        "input guardrails",
        "output guardrails",
        "human-in-the-loop",
        "tool approval hooks",
        "sandbox access boundary",
    ],
    trace_surfaces=[
        "Agents SDK tracing",
        "tool call spans",
        "guardrail spans",
        "sandbox run metadata",
    ],
    eval_surfaces=[
        "trace-driven workflow evaluation",
        "graders",
        "distillation/fine-tuning hooks",
    ],
    sandbox_surfaces=[
        "manifest-defined workspace",
        "files and shell",
        "ports",
        "snapshots",
        "resumable sandbox sessions",
    ],
    strengths=[
        "native tool use",
        "guardrails",
        "tracing",
        "sandbox agents",
        "managed agent loop",
    ],
    harness_hooks=[
        "input guardrail",
        "output guardrail",
        "tool approval",
        "trace export",
        "sandbox session resume",
        "artifact inspection",
    ],
    runtime_caveats=[
        "decide per workflow whether the app or SDK owns the loop",
        "persist sandbox identifiers separately from conversational session state",
    ],
    source_refs=[
        "https://developers.openai.com/api/docs/guides/agents",
        "https://openai.github.io/openai-agents-python/",
        "https://developers.openai.com/api/docs/guides/agents/sandboxes",
    ],
)


DEEPSEEK_PROFILE = ProviderProfile(
    name="deepseek",
    api_style="openai-compatible api + anthropic-compatible coding-agent integrations",
    tool_modes=[
        "function calling",
        "JSON output",
        "OpenAI-compatible tool payloads",
        "coding-agent terminal harnesses",
    ],
    state_surfaces=[
        "model context cache",
        "coding-agent session state",
        "provider adapter settings",
    ],
    governance_surfaces=[
        "provider capability adapter",
        "ignored-parameter detection",
        "model/effort routing policy",
        "cache-aware budget accounting",
    ],
    trace_surfaces=[
        "adapter-level request/response envelopes",
        "tool schema normalization records",
        "cache hit/miss accounting",
    ],
    eval_surfaces=[
        "full-trace regression across provider switches",
        "cost/latency/quality comparison",
        "terminal harness benchmarks",
    ],
    sandbox_surfaces=[
        "external coding agents such as Claude Code, OpenCode, OpenClaw, Pi, Hermes, and Reasonix",
    ],
    strengths=[
        "cost-efficient reasoning",
        "large-context model profiles",
        "context caching",
        "function calling",
        "coding-agent ecosystem integrations",
    ],
    harness_hooks=[
        "provider capability adapter",
        "tool schema normalization",
        "reasoning-effort policy",
        "cache-aware budget accounting",
        "full-trace regression",
    ],
    runtime_caveats=[
        "treat provider-specific ignored parameters as policy risks",
        "record provider capability snapshots in every checkpoint",
        "prefer explicit adapter contracts over assuming OpenAI parity",
    ],
    source_refs=[
        "https://api-docs.deepseek.com/guides/coding_agents/",
        "https://api-docs.deepseek.com/quick_start/agent_integrations/openclaw/",
        "https://api-docs.deepseek.com/quick_start/agent_integrations/hermes/",
    ],
)


OPENHANDS_PROFILE = ProviderProfile(
    name="openhands",
    api_style="software-agent-sdk + rest-agent-server",
    tool_modes=[
        "bash",
        "file editing",
        "browser",
        "MCP tools",
        "custom tools",
    ],
    state_surfaces=[
        "conversation records",
        "workspace files",
        "agent server runtime files",
        "persistent memory",
        "skills and context",
    ],
    governance_surfaces=[
        "security and action confirmation",
        "secret registry",
        "agent settings",
        "remote server session key",
    ],
    trace_surfaces=[
        "event stream",
        "observability and tracing",
        "metrics tracking",
    ],
    eval_surfaces=[
        "coding benchmarks",
        "agent workflow metrics",
    ],
    sandbox_surfaces=[
        "local workspace",
        "Docker/Kubernetes agent server",
        "remote execution",
    ],
    strengths=[
        "code-first software agent SDK",
        "REST agent server",
        "OpenAI-compatible endpoint",
        "model-agnostic runtime",
    ],
    harness_hooks=[
        "workspace boundary",
        "security confirmation",
        "server API authentication",
        "event stream adapter",
    ],
    source_refs=[
        "https://docs.openhands.dev/sdk",
        "https://docs.openhands.dev/sdk/arch/agent-server",
    ],
)


PI_PROFILE = ProviderProfile(
    name="pi",
    api_style="minimal terminal agent harness",
    tool_modes=[
        "extensions",
        "skills",
        "prompt templates",
        "RPC",
        "SDK",
    ],
    state_surfaces=[
        "tree sessions",
        "packages",
        "prompt/theme/extension files",
    ],
    governance_surfaces=[
        "harness customization surface",
        "steer versus follow-up workflow control",
    ],
    trace_surfaces=[
        "terminal session transcript",
        "JSON mode output",
    ],
    eval_surfaces=[
        "package-level reproducibility",
        "terminal workflow regression",
    ],
    strengths=[
        "small core",
        "customizable harness",
        "extensions and skills as first-class artifacts",
    ],
    harness_hooks=[
        "extension loader",
        "skill loader",
        "prompt template package",
        "session tree export",
    ],
    runtime_caveats=[
        "good model for extensibility patterns, not a complete research runtime by itself",
    ],
    source_refs=[
        "https://pi.dev/",
    ],
)


LANGGRAPH_PROFILE = ProviderProfile(
    name="langgraph",
    api_style="durable graph runtime",
    tool_modes=[
        "graph nodes",
        "interrupts",
        "tools inside nodes",
    ],
    state_surfaces=[
        "checkpointer",
        "threads",
        "state snapshots",
        "memory stores",
    ],
    governance_surfaces=[
        "interrupt-before-action",
        "human-in-the-loop",
        "node-level retry policy",
    ],
    trace_surfaces=[
        "state transition history",
        "graph execution traces",
    ],
    eval_surfaces=[
        "replay consistency",
        "node-level regression",
    ],
    strengths=[
        "durable execution",
        "checkpointing",
        "interrupt/resume",
        "explicit state machine",
    ],
    harness_hooks=[
        "checkpoint adapter",
        "resume cursor",
        "approval interrupt",
        "state hydration",
    ],
    source_refs=[
        "https://docs.langchain.com/oss/python/langgraph/persistence",
    ],
)


ANTHROPIC_AGENT_SDK_PROFILE = ProviderProfile(
    name="anthropic-agent-sdk",
    api_style="claude-code-agent-sdk",
    tool_modes=[
        "built-in file tools",
        "command execution",
        "web search",
        "custom tools",
        "MCP tools",
        "subagents",
    ],
    state_surfaces=[
        "sessions",
        "external session storage",
        "skills",
        "commands",
        "memory",
        "file-change checkpoints",
    ],
    governance_surfaces=[
        "permissions",
        "approvals",
        "hooks",
        "usage and cost tracking",
        "secure deployment guidance",
    ],
    trace_surfaces=[
        "OpenTelemetry observability",
        "agent lifecycle hooks",
        "streamed responses",
    ],
    eval_surfaces=[
        "tool-loop evals through external harnesses",
        "cost and usage comparisons",
        "permission-mode regression",
    ],
    sandbox_surfaces=[
        "local process execution",
        "managed agents as hosted sandbox/session product",
    ],
    strengths=[
        "Claude Code agent loop as a library",
        "sessions resume/fork",
        "MCP integration",
        "permissions and hooks",
        "skills/plugins surface",
    ],
    harness_hooks=[
        "permission prompt adapter",
        "hook bridge",
        "session persistence adapter",
        "OpenTelemetry trace export",
    ],
    runtime_caveats=[
        "separate Agent SDK from Managed Agents when reasoning about hosted sandbox/session ownership",
        "do not assume durable execution from session persistence alone",
    ],
    source_refs=[
        "https://code.claude.com/docs/en/agent-sdk/overview",
    ],
)


GOOGLE_ADK_PROFILE = ProviderProfile(
    name="google-adk",
    api_style="agent-development-kit + gemini-enterprise-agent-runtime",
    tool_modes=[
        "tools and integrations",
        "workflow agents",
        "dynamic routing",
        "multi-agent delegation",
        "A2A",
        "MCP",
    ],
    state_surfaces=[
        "sessions",
        "memory bank",
        "example store",
        "sandbox snapshots",
        "agent runtime revisions",
    ],
    governance_surfaces=[
        "IAM policies",
        "semantic governance policies",
        "agent gateway",
        "model armor spans",
        "auth manager",
    ],
    trace_surfaces=[
        "observability",
        "feedback service",
        "evaluation trajectories",
        "agent relationship graph",
    ],
    eval_surfaces=[
        "built-in and partner evaluation tools",
        "trajectory evaluation",
        "feedback service",
        "example store",
    ],
    sandbox_surfaces=[
        "code execution sandbox",
        "computer use sandbox",
        "custom containers",
        "sandbox templates and snapshots",
    ],
    strengths=[
        "enterprise-scale agent platform",
        "model-agnostic ADK",
        "governance and gateway surfaces",
        "multi-language SDKs",
    ],
    harness_hooks=[
        "A2A bridge",
        "MCP gateway",
        "policy adapter",
        "feedback/eval export",
        "sandbox snapshot binding",
    ],
    runtime_caveats=[
        "large platform surface; keep MVP adapter thin",
        "treat enterprise governance primitives as future integration targets",
    ],
    source_refs=[
        "https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk",
    ],
)


TEMPORAL_ORCHESTRATOR_PROFILE = ProviderProfile(
    name="temporal",
    api_style="durable-execution-agent-orchestrator",
    tool_modes=[
        "workflows",
        "activities",
        "signals",
        "timers",
        "LangGraph plugin",
    ],
    state_surfaces=[
        "workflow history",
        "durable waits",
        "continue-as-new",
        "large payload support",
        "cross-worker recovery",
    ],
    governance_surfaces=[
        "durable human review",
        "retry policies",
        "timeouts",
        "worker isolation",
        "audit history",
    ],
    trace_surfaces=[
        "workflow/activity traces",
        "LangSmith trace propagation",
        "retry and signal history",
    ],
    eval_surfaces=[
        "durable replay boundaries",
        "failure recovery regression",
        "human-review wait semantics",
    ],
    sandbox_surfaces=[
        "external worker fleet",
        "activity execution boundary",
    ],
    strengths=[
        "durable execution",
        "human-in-the-loop waits without held compute",
        "crash recovery",
        "long-running workflows",
    ],
    harness_hooks=[
        "approval signal adapter",
        "retry policy adapter",
        "activity boundary trace",
        "continue-as-new compaction",
    ],
    runtime_caveats=[
        "orchestrator rather than model/tool provider",
        "best used under Hermes once prototype needs production durability",
    ],
    source_refs=[
        "https://temporal.io/blog/temporal-langgraph-plugin-durable-execution",
    ],
)


AWS_AGENTCORE_PROFILE = ProviderProfile(
    name="aws-bedrock-agentcore",
    api_style="managed-agent-runtime-services",
    tool_modes=[
        "agent runtime endpoint",
        "gateway tools",
        "browser tool",
        "code interpreter",
        "memory service",
    ],
    state_surfaces=[
        "runtime sessions",
        "memory",
        "identity context",
        "gateway configuration",
        "observability records",
    ],
    governance_surfaces=[
        "identity",
        "gateway policy",
        "runtime isolation",
        "evaluation",
        "observability",
    ],
    trace_surfaces=[
        "agent execution observability",
        "runtime session events",
        "gateway/tool invocation records",
    ],
    eval_surfaces=[
        "agent evaluation service",
        "quality/safety/trajectory checks",
    ],
    sandbox_surfaces=[
        "managed runtime",
        "browser",
        "code interpreter",
    ],
    strengths=[
        "enterprise managed runtime",
        "identity and gateway surfaces",
        "long-running session support",
        "tooling bundled as runtime services",
    ],
    harness_hooks=[
        "runtime session binding",
        "identity witness adapter",
        "gateway tool contract adapter",
        "observability export",
        "evaluation export",
    ],
    runtime_caveats=[
        "treat managed service records as external evidence refs, not as the only replay source",
        "map provider memory into local MemoryCommitProtocol before decision use",
    ],
    source_refs=[
        "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html",
    ],
)


MICROSOFT_AGENT_FRAMEWORK_PROFILE = ProviderProfile(
    name="microsoft-agent-framework",
    api_style="open-source-agent-framework-with-enterprise-runtime",
    tool_modes=[
        "agent orchestration",
        "multi-agent workflows",
        "connectors",
        "tools",
        "evaluation hooks",
    ],
    state_surfaces=[
        "workflow state",
        "conversation state",
        "enterprise integration state",
        "observability records",
    ],
    governance_surfaces=[
        "enterprise governance",
        "observability",
        "evaluation",
        "connector policy",
    ],
    trace_surfaces=[
        "workflow execution traces",
        "agent orchestration traces",
        "observability integrations",
    ],
    eval_surfaces=[
        "agent workflow evaluation",
        "enterprise regression pipelines",
    ],
    strengths=[
        "unifies AutoGen-style multi-agent orchestration and Semantic Kernel-style enterprise integration",
        "open-source SDK surface",
        "visual workflow/orchestration direction",
    ],
    harness_hooks=[
        "workflow trace adapter",
        "connector permission adapter",
        "eval export",
        "enterprise policy snapshot",
    ],
    runtime_caveats=[
        "use as an integration profile rather than replacing the local Harness/Hermes control plane",
    ],
    source_refs=[
        "https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-at-build-2026-announce/",
    ],
)


MICROSOFT_AGENT_GOVERNANCE_TOOLKIT_PROFILE = ProviderProfile(
    name="microsoft-agent-governance-toolkit",
    api_style="framework-agnostic-agent-governance-runtime",
    tool_modes=[
        "policy engine",
        "identity-aware tool calls",
        "sandboxed execution",
        "compliance checks",
        "SRE/reliability hooks",
    ],
    state_surfaces=[
        "policy specs",
        "identity assertions",
        "sandbox execution records",
        "governance violation reports",
        "reliability telemetry",
    ],
    governance_surfaces=[
        "deterministic policy enforcement",
        "zero-trust identity",
        "execution sandboxing",
        "OWASP Agentic Top 10 coverage",
        "compliance reporting",
    ],
    trace_surfaces=[
        "policy decision records",
        "identity binding events",
        "sandbox/audit logs",
        "violation traces",
    ],
    eval_surfaces=[
        "governance regression",
        "policy violation replay",
        "compliance readiness checks",
    ],
    sandbox_surfaces=[
        "execution sandbox",
        "network and environment boundaries",
    ],
    strengths=[
        "framework-agnostic governance layer",
        "policy, identity, sandboxing, and reliability in one toolkit",
        "fits enterprise deployment hardening",
    ],
    harness_hooks=[
        "policy artifact adapter",
        "identity witness adapter",
        "sandbox evidence adapter",
        "compliance report export",
        "governance violation replay",
    ],
    runtime_caveats=[
        "treat toolkit decisions as external governance evidence, not as a replacement for local trace envelopes",
        "map policy specs into local PermissionGraph/ActionPathPolicy fingerprints before resume",
    ],
    source_refs=[
        "https://github.com/microsoft/agent-governance-toolkit",
        "https://microsoft.github.io/agent-governance-toolkit/",
        "https://opensource.microsoft.com/blog/2026/04/02/introducing-the-agent-governance-toolkit-open-source-runtime-security-for-ai-agents/",
    ],
)


PYDANTIC_DURABLE_PROFILE = ProviderProfile(
    name="pydantic-ai-durable",
    api_style="python-agent-framework-with-durable-execution",
    tool_modes=[
        "typed tools",
        "agent graph nodes",
        "human input waits",
        "external durable backends",
    ],
    state_surfaces=[
        "typed agent state",
        "graph execution state",
        "Temporal backend",
        "DBOS backend",
        "durable control-flow checkpoints",
    ],
    governance_surfaces=[
        "typed tool schemas",
        "human-in-the-loop waits",
        "durable retry boundary",
    ],
    trace_surfaces=[
        "graph execution events",
        "durable backend history",
    ],
    eval_surfaces=[
        "typed-agent regression",
        "resume/retry regression",
    ],
    strengths=[
        "Python-native typed agent surface",
        "durable execution adapters",
        "fits small self-owned runtime prototypes",
    ],
    harness_hooks=[
        "typed tool contract import",
        "durable wait adapter",
        "graph-state snapshot adapter",
    ],
    runtime_caveats=[
        "durability backend choice should be fingerprinted in checkpoints",
        "typed schemas still need effect labels and authority witnesses",
    ],
    source_refs=[
        "https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/",
    ],
)


MISTRAL_DURABLE_AGENTS_PROFILE = ProviderProfile(
    name="mistral-durable-agents",
    api_style="workflow-api-with-durable-agent-steps",
    tool_modes=[
        "agents as workflow steps",
        "parallel agent calls",
        "handoffs",
        "approval requests",
        "MCP/tool connectors",
    ],
    state_surfaces=[
        "workflow inputs/outputs",
        "agent step state",
        "approval state",
        "tool call artifacts",
    ],
    governance_surfaces=[
        "approval step",
        "tool/agent routing policy",
        "workflow boundary",
    ],
    trace_surfaces=[
        "workflow step trace",
        "agent invocation trace",
        "approval/handoff events",
    ],
    eval_surfaces=[
        "workflow regression",
        "handoff and approval path checks",
    ],
    strengths=[
        "durable workflow framing",
        "approval and handoff as explicit workflow concepts",
        "parallel agent/tool composition",
    ],
    harness_hooks=[
        "workflow step trace adapter",
        "approval state adapter",
        "handoff receipt adapter",
    ],
    runtime_caveats=[
        "map workflow-step state back into Hermes cursor rather than treating it as chat history",
    ],
    source_refs=[
        "https://docs.mistral.ai/studio-api/workflows/building-workflows/durable_agents",
    ],
)


CLOUDFLARE_AGENTS_PROFILE = ProviderProfile(
    name="cloudflare-agents",
    api_style="durable-object-agent-runtime",
    tool_modes=[
        "RPC",
        "WebSockets",
        "scheduled tasks",
        "custom tools",
        "MCP adapters",
    ],
    state_surfaces=[
        "Durable Objects state",
        "agent class instance state",
        "SQLite-backed storage",
        "scheduled task state",
    ],
    governance_surfaces=[
        "durable lifecycle",
        "runtime scheduling",
        "RPC boundary",
        "worker isolation",
    ],
    trace_surfaces=[
        "agent lifecycle events",
        "RPC calls",
        "scheduling history",
    ],
    eval_surfaces=[
        "durable runtime regression",
        "scheduler/state replay",
    ],
    strengths=[
        "Cloudflare-native stateful agent base",
        "Durable Objects abstraction",
        "scheduling and RPC included in the runtime shape",
    ],
    harness_hooks=[
        "durable object state adapter",
        "scheduler trace adapter",
        "RPC policy adapter",
    ],
    runtime_caveats=[
        "agent state is coupled to the runtime object lifecycle; keep checkpoint snapshots externalized for replay",
    ],
    source_refs=[
        "https://developers.cloudflare.com/agents/runtime/lifecycle/agent-class/",
    ],
)


VERCEL_WORKFLOW_AGENT_PROFILE = ProviderProfile(
    name="vercel-workflow-agent",
    api_style="workflow-native-durable-agent",
    tool_modes=[
        "workflow steps",
        "streaming tool calls",
        "resume-from-workflow",
        "message conversion",
    ],
    state_surfaces=[
        "workflow state",
        "workflow agent context",
        "tool call stream state",
    ],
    governance_surfaces=[
        "workflow boundary",
        "resumable execution",
        "typed message conversion",
    ],
    trace_surfaces=[
        "workflow stream",
        "step-level execution trace",
    ],
    eval_surfaces=[
        "durable resumability regression",
        "workflow-step correctness",
    ],
    strengths=[
        "durable and resumable agent loop",
        "workflow-first execution model",
        "clean integration with AI SDK message conversion",
    ],
    harness_hooks=[
        "workflow resume adapter",
        "workflow trace export",
        "message conversion gate",
    ],
    runtime_caveats=[
        "workflow agent state should be checkpointed separately from chat UI state",
    ],
    source_refs=[
        "https://ai-sdk.dev/docs/agents/workflow-agent",
    ],
)


MASTRA_DURABLE_AGENTS_PROFILE = ProviderProfile(
    name="mastra-durable-agents",
    api_style="workflow-and-agent-runtime-with-suspend-resume",
    tool_modes=[
        "suspend/resume",
        "human approval",
        "background tasks",
        "subagents",
        "schedules",
    ],
    state_surfaces=[
        "workflow snapshots",
        "agent state",
        "resume data",
        "background task state",
    ],
    governance_surfaces=[
        "tool approval",
        "human-in-the-loop",
        "durable suspend/resume",
        "scheduled workflows",
    ],
    trace_surfaces=[
        "suspend/resume events",
        "tool-call-suspended events",
        "background task events",
    ],
    eval_surfaces=[
        "approval-path regression",
        "resume consistency",
        "background task continuation",
    ],
    strengths=[
        "durable agents with snapshot-based state",
        "explicit approval and suspension primitives",
        "background task orchestration",
    ],
    harness_hooks=[
        "approval suspend adapter",
        "snapshot resume adapter",
        "background task trace adapter",
        "schedule pause/resume adapter",
    ],
    runtime_caveats=[
        "workflow snapshots are the durable source of truth; agent UI should only mirror them",
    ],
    source_refs=[
        "https://mastra.ai/docs/long-running-agents/durable-agents",
        "https://mastra.ai/docs/workflows/suspend-and-resume",
        "https://mastra.ai/docs/workflows/human-in-the-loop",
        "https://mastra.ai/docs/long-running-agents/background-tasks",
        "https://mastra.ai/docs/workflows/workflow-state",
    ],
)


PROVIDER_PROFILES = {
    profile.name: profile
    for profile in [
        OPENAI_PROFILE,
        DEEPSEEK_PROFILE,
        OPENHANDS_PROFILE,
        PI_PROFILE,
        LANGGRAPH_PROFILE,
        ANTHROPIC_AGENT_SDK_PROFILE,
        GOOGLE_ADK_PROFILE,
        TEMPORAL_ORCHESTRATOR_PROFILE,
        AWS_AGENTCORE_PROFILE,
        MICROSOFT_AGENT_FRAMEWORK_PROFILE,
        MICROSOFT_AGENT_GOVERNANCE_TOOLKIT_PROFILE,
        PYDANTIC_DURABLE_PROFILE,
        MISTRAL_DURABLE_AGENTS_PROFILE,
        CLOUDFLARE_AGENTS_PROFILE,
        VERCEL_WORKFLOW_AGENT_PROFILE,
        MASTRA_DURABLE_AGENTS_PROFILE,
    ]
}


def get_provider_profile(name: str) -> ProviderProfile:
    normalized = name.lower()
    aliases = {
        "oai": "openai",
        "dpsk": "deepseek",
        "deepseek-ai": "deepseek",
        "oh": "openhands",
        "open-hands": "openhands",
        "lang-graph": "langgraph",
        "anthropic": "anthropic-agent-sdk",
        "claude": "anthropic-agent-sdk",
        "claude-agent-sdk": "anthropic-agent-sdk",
        "adk": "google-adk",
        "google": "google-adk",
        "google-agent-development-kit": "google-adk",
        "temporal-langgraph": "temporal",
        "agentcore": "aws-bedrock-agentcore",
        "aws-agentcore": "aws-bedrock-agentcore",
        "bedrock-agentcore": "aws-bedrock-agentcore",
        "maf": "microsoft-agent-framework",
        "microsoft": "microsoft-agent-framework",
        "agt": "microsoft-agent-governance-toolkit",
        "microsoft-agt": "microsoft-agent-governance-toolkit",
        "agent-governance-toolkit": "microsoft-agent-governance-toolkit",
        "pydantic": "pydantic-ai-durable",
        "pydantic-ai": "pydantic-ai-durable",
        "mistral": "mistral-durable-agents",
        "mistral-agents": "mistral-durable-agents",
        "cloudflare": "cloudflare-agents",
        "cf-agents": "cloudflare-agents",
        "vercel": "vercel-workflow-agent",
        "workflowagent": "vercel-workflow-agent",
        "mastra": "mastra-durable-agents",
    }
    key = aliases.get(normalized, normalized)
    if key in PROVIDER_PROFILES:
        return PROVIDER_PROFILES[key]
    raise KeyError(f"unknown provider profile: {name}")
