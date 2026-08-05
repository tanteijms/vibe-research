# Research Watchlist 2026

> 用途：持续追踪 agent runtime / harness / protocol / benchmark 的最新信号，并把它们翻译成 `vibe-research` 的实现任务。

## 1. Protocol Watch

| 协议 | 最新信号 | 我们要做什么 |
|---|---|---|
| MCP 2026-07-28 | 新 spec 变成 stateless core，引入 MRTR、header-based routing、cacheable list results、Tasks extension、authorization hardening。 | `mcp/` 层不要依赖 transport session；tool call trace 必须记录 method/name/schema hash/cache policy/task handle。 |
| A2A | 官方定位是不同框架/厂商 agent 之间的开放互操作协议，强调 opaque agent collaboration。 | 先把远端 agent 当成 governed tool；等 proof receipt 和 artifact boundary 稳定后再做多 agent delegation。 |
| AG-UI | 把 agent backend 和 user-facing frontend 之间的事件流标准化，覆盖 shared state、interrupt、approve/edit/retry、agent steering。 | 将 Harness approval inbox 设计成 event stream；Hermes cursor/pending approval 作为 typed state 暴露。 |
| OpenTelemetry GenAI | GenAI semantic conventions 正在外移到独立规范仓库，同时 agent/tool/MCP 相关属性进入统一观测语义。 | `TraceEnvelope` 后续映射到 OTel spans/log events，provider-native trace id 只作为 metadata。 |
| OpenAI Agents SDK next evolution / AgentKit | OpenAI 正在把 agent 生命周期、workflow 可视化、tracing、evaluation、deploy 一体化。 | 参考其产品化工作流形状，但不要丢掉我们的 harness policy 和研究态 trace。 |

## 2. Paper Watch

| 论文 | 为什么继续盯 | 对本项目的任务 |
|---|---|---|
| Harness-Bench | 证明 model-harness configuration 才是评估单位。 | eval result 带 provider/policy/protocol/tool-contract fingerprints。 |
| Harness-1 | 把 working memory、候选池、证据链、verification records 放到 harness/environment。 | Hermes state 外置 evidence/artifact refs；模型只管 semantic decision。 |
| MemoHarness | 把 harness 编辑拆成 context/tool/generation/orchestration/memory/output 六个面。 | Skill schema v2 拆成六个可 diff、可 eval 的 section。 |
| MCP Tool Descriptions Are Smelly | 856 tools / 103 MCP servers 的研究显示 tool description 质量问题非常普遍，修复也有 accuracy-cost trade-off。 | 新增 `ToolDescriptionContract`，上线前做 quality warning 和 compact context 策略。 |
| DynamicMCPBench / LiveMCPBench / MCP-Bench | MCP 评测正在从静态 tool-use case 转向真实 MCP server、动态服务发现、长链路多工具任务。 | eval harness 要保存 MCP server/tool schema hash、任务 handle、cache policy、服务发现轨迹。 |
| MCP-SandboxScan | 真实 MCP tools 开始与 sandbox 安全执行、scan-based security benchmark 结合。 | MCP tool execution 不能脱离 sandbox policy 和安全扫描。 |
| Long-Horizon-Terminal-Bench | 强调 terminal 长任务的中间步骤和 verifier。 | checkpoint 要附 step-level verifier，不只看 final report。 |
| Runtime Governance for AI Agents | 把安全策略提升为 runtime path constraints，关注 agent action sequence 是否满足路径级约束。 | Harness policy 不能只看单步 tool permission，还要能检查 action path。 |
| Layered Translation Method for Runtime Guardrails | 把自然语言 policy 翻译成可运行 guardrail，并保持 human-readable 与 runtime-checkable 两层。 | policy artifact 要保留 natural-language source、compiled rule、rule hash。 |
| SkillGuard / SKILL.nb | skill 已经被看成有权限、上下文影响和生命周期的 runtime artifact，而不是 prompt snippet。 | 新增 `SkillManifest`，skill promote 前检查权限、evidence gate、fallback path。 |
| Aris / OpenRath | 研究 workflow runtime 开始引入 evaluator agent、session object、artifact assembly 和 structured feedback。 | 科研 agent 不应直接写 final answer，应围绕 session/evidence/review object 推进。 |
| AgentFootprint / durable artifacts / evidence tracing | storage footprint、durable intermediate artifacts、execution provenance 正在成为 agent runtime 的评估面。 | checkpoint、artifact、trace 要支持 footprint reporting 和 provenance graph。 |
| Filesystem-Based Memory for LLM Agents | memory 更像 filesystem-like surface，而不是单一黑盒 memory blob。 | 让 `EvidenceLedger` / `MemoryCommitProtocol` 保持可搜索、可分层、可恢复。 |
| SEAGym / harness evolution papers | self-evo 要区分 harness update、executor benefit、held-out transfer。 | self-evo 不直接 promote，必须通过 replay + held-out regression。 |
| APPA | 把 agent 权限约束建模成带 context branching 的信息流控制，避免读取不可信数据后永久污染主轨迹。 | `RuntimeState` 后续需要 label / branch / sanitizer receipt，而不是只存单一全局上下文。 |
| FAVA | 把自然语言任务降成 Permission IR，再变成 evidence-backed permission graph，并在 effectful action 前做形式化授权。 | Approval receipt 可以升级成 permission graph + counterexample，而不是单一 approve token。 |
| MTGuard / Hybrid MCP Analysis | MCP 工具安全从静态 prompt/output 检查转向 lifecycle-aware static-dynamic co-analysis。 | MCP adapter 要记录 process/DNS/file/tool-result 等运行时证据摘要，供 post-execution verifier 使用。 |
| Commit-Time Authorization | durable effect 必须在提交边界重新证明 authority witness 仍然新鲜、因果先行、绑定同一效果且仍有资格。 | 写文件、发布报告、外部 API commit 前要二次校验 approval epoch / artifact version / branch token。 |
| Governance Decay | context compaction 可能把安全策略、standing instruction、memory policy 静默压掉。 | Harness policy 不能只活在上下文里；需要 pinned policy snapshot + compaction verifier。 |
| Slipstream | 用后续轨迹验证 context compaction 是否保留 forward intent 和关键事实约束。 | Hermes resume 前可以验证 summary/checkpoint 是否保留 policy、goal、artifact dependency。 |
| Agent Skills Matter / SigLeak | skill 即使隐藏，执行轨迹也可能泄漏其程序性知识。 | trace export 要区分公开审计字段与私有 skill-signature 字段，避免 skill marketplace 侧信道。 |
| SKIMIX | skill mixture / harness-time scaling 有非单调收益，第一轮 refinement 往往贡献最大。 | skill registry 不要默认越多越好；需要 anti-dilution routing 和 per-task skill budget。 |
| Long-Context Instruction Following Benchmark | 长指令基准把 OpenHands harness、MCP endpoint、容器环境合在一起测试。 | 我们自己的 long-horizon eval 要固定 harness、MCP schema 和容器环境，避免只测模型。 |
| AgentCheck | 把 MCP server 变成 fault-injection surface：记录真实工具响应，再注入 timeout/stale/poisoned-description 等故障并复跑确认 mitigation。 | 已新增 `InterventionReplayWorkbench` 原型；后续接真实 MCP response snapshot 和 fault injector。 |
| AgentTether | 用 Transition Unit / Critical Transition Graph 定位失败关键子轨迹，并把修复记忆注入下一次运行。 | 已新增 `TransitionGraph` 原型，支持关键链、关键子图、分叉点和失败目标定位。 |
| Structured Graph Harness / SGH | 把 agent loop 转成 scheduler-theoretic graph：静态 DAG、immutable plan、分离 planning/recovery、严格升级路径。 | `TransitionGraph` 后续可升级成可执行 workflow graph，区分 planned edge、runtime edge、recovery edge。 |
| Harness-G | graph-structured harness 用图来表达 search agent 的上下文和动作边。 | `TransitionGraph` / `ActionPathPolicy` / `EvidenceLedger` 可以一起解释 search-flow 的可恢复、可审计和可约束性。 |
| iCORE / obligation coupling | 用 cooperation graph、obligation graph 和 audit map 审计多 agent 协作。 | Transition graph 后续增加 actor / obligation / audit responsibility 维度。 |
| Obligation audit maps | iCORE 把 multi-agent collaboration 的 correctness 拆成 work soundness 和 assignment stability。 | 已新增 `ObligationAuditMap`，支持 evidence-backed obligation、actor load、assignment instability。 |
| MemTX | 把 memory write 和 belief commit 分开，记录 evidence、permissions、provenance、validity，并对不可逆 tool call 做 in-flight belief gating。 | Hermes memory/artifact 写入要有 staged/validated/committed 生命周期，不能一写入就进入可行动事实。 |
| Agent memory lifecycle / provenance | LangGraph persistence、Letta memory blocks/archival memory、Mem0 long-term memory 都说明 memory 已经是 agent runtime 的一等工程面。 | 记忆层不能只做 vector store；要记录 source refs、validation receipts、parent records、commit status 和 retraction cascade。 |
| Stateless Decision Memory | 用 append-only event log + task-conditioned projection 替代可变黑盒 memory，降低 decision-time drift。 | 已新增 `DecisionMemoryProjection`，只从 committed memory log 投影当前决策视图。 |
| Reliability-contagion feasibility | 多 agent 拓扑存在连接度收益与错误传播风险的 trade-off。 | A2A/sub-agent topology 后续要做 reliability budget，不默认“越多 agent 越好”。 |
| Compile, Then Page | 将长 SOP 编译成可执行伪代码，用 capability-gated runtime 和 active-frame paging 约束 procedural agent。 | Natural-language policy 后续可以编译成 `PermissionGraph` / cursor frame，而不是整篇塞上下文。 |
| AgentRadio / SWE-Atlas QnA | 大代码库理解任务显示单 agent clean context 不够，异步被动感知和多 agent 分工能缓解长上下文限制。 | 科研 runtime 的 subtask/fork 应该保留 clean context + shared evidence graph，而不是共享一个膨胀上下文。 |
| Self-Improving Behavioral Rules | review feedback 可以沉淀为版本化行为规则和自检 checklist，跨 session 避免同类错误复发。 | Self-Evo 不应直接改 prompt；应把人审反馈变成 versioned rule artifact，并通过 replay/eval gate。 |

## 3. Implementation Watch

| 实现 | 该看什么 | 我们怎么吸收 |
|---|---|---|
| OpenAI Agents / Sandbox Agents | SDK 负责 loop/state/guardrails/tracing/resumable approvals；sandbox 文档明确 orchestration 和 execution boundary 可分离。 | 我们保留自有 loop，但按 control plane / execution plane 分离 sandbox，并把 approval interruption 序列化进 Hermes。 |
| Claude Agent SDK | Claude Code 的 agent loop、内置工具、MCP、sessions、permissions、hooks、skills/plugins、OpenTelemetry 被开放成 Python/TypeScript SDK。 | 可以参考 permissions/hooks/session/skills 的 API 形状，但不要把 session persistence 当 durable execution；hook 顺序要显式记录。 |
| Google ADK / Agent Platform | ADK 2.0 强调 graph-based / dynamic / collaborative workflows，企业平台连接 A2A、MCP、sandbox、eval、observability、governance。 | 后续企业版 adapter 可从 governance/sandbox/eval 三个面切入，不要 MVP 就吞掉整个平台。 |
| Temporal LangGraph Plugin | 2026-07 public preview 明确区分 checkpoint 和 durable execution；approval wait 可以通过 signal 免费等待数天。 | Hermes 后续要把“等待”和“恢复”从普通 checkpoint 升级成 durable orchestration contract。 |
| DeepSeek integrations | 官方把 DeepSeek 接进 Codex、Claude Code、OpenCode、OpenClaw、Hermes、Reasonix、Pi/Oh My Pi、Copilot 等 coding agents，并暴露 provider compatibility caveats。 | DeepSeek 作为 provider adapter，不假设它等价 OpenAI，必须记录 capability snapshot、thinking/tool-call 兼容性和 cache budget。 |
| OpenHands SDK / Agent Server | 开源 software-agent runtime 把 SDK、REST server、workspace、security confirmation、MCP、metrics/tracing 分开；direct tool execution 会绕过 loop safeguard。 | 借鉴 core runtime 和 API/worker/UI 解耦；任何 bypass path 都要进 Harness policy。 |
| LangGraph persistence / interrupts | persistence 提供 checkpoint/store/time-travel，interrupts 支持人类参与和恢复。 | Hermes 可以借 checkpoint/store 形状，但 memory commit/status/provenance 仍由 Harness 自己治理。 |
| Letta memory | core memory blocks 与 archival memory 分层，强调 agent 可长期维护和检索记忆。 | Research memory 应拆成 working/core/archival，但每次晋升都走 validation receipt。 |
| Mem0 | 官方定位是跨 sessions/tools/runs 持久化 agent long-term memory。 | 外接记忆服务时要把 provider-native memory id 映射成 `MemoryRecord`，保留本地 commit gate。 |
| Pi | minimal agent harness，extensions/skills/prompt templates/packages 成为主要扩展面。 | skill 不做单纯 prompt 文件，做可安装、可测、可回放的 package。 |
| OpenClaw | personal assistant + local-first control plane + provider onboarding。 | 后续 UI 参考 goal/session/provider dashboard，而不是普通聊天页。 |
| OpenRath | session-centered research runtime，把 input、goal、output、artifact、policy、version、evaluation 都放进可追踪 session。 | 已新增 typed `ResearchSession`；后续再补 actor/obligation linkage。 |
| AWS Bedrock AgentCore | 官方把 Runtime、Memory、Identity、Gateway、Browser、Code Interpreter、Observability、Evaluations 组合成 managed agent runtime services。 | 新增 `aws-bedrock-agentcore` profile；后续可把 managed runtime 记录映射成 Hermes session refs、identity witness 和 eval evidence refs。 |
| Microsoft Agent Framework | 新框架强调把多 agent orchestration、workflow、enterprise connectors、observability 和 eval 统一起来。 | 新增 `microsoft-agent-framework` profile；重点学习 workflow trace adapter 与 connector permission adapter。 |
| Microsoft Agent Governance Toolkit | policy、identity、sandbox、compliance、reliability 被明确拆成独立治理栈。 | 新增 `microsoft-agent-governance-toolkit` profile；后续把 policy decisions、identity assertions、sandbox evidence 作为 checkpoint evidence refs。 |
| Pydantic AI durable execution | Python typed-agent 框架显式支持 durable execution，并可接 Temporal / DBOS 等后端。 | 新增 `pydantic-ai-durable` profile；适合作为 typed tool contract 和 durable wait 的轻量接入形状。 |
| Mistral durable agents | workflow 中把 agent calls、handoff、approval request、parallel step 做成 durable primitives。 | 新增 `mistral-durable-agents` profile；后续参考 approval state adapter 与 handoff receipt adapter。 |

## 4. Continuation Delta: 新增重点追踪

| 新来源 | 为什么值得追 | 下一步落点 |
|---|---|---|
| HarnessFix / HTIR | 失败轨迹诊断不再只比较最终结果，而是抽取 harness flaw、repair plan 和 evaluation loop。 | 已新增 `HarnessDiagnosticWorkbench`；后续把 report 变成 eval case 和 skill/rule promotion gate。 |
| Governed Evolution of Agent Runtimes | agent runtime 自我演化需要 versioned entity、operation、knowledge store 和 evolution platform，而不是临时 prompt rewrite。 | Self-Evo 层升级成 versioned artifact evolution：policy/skill/rule/workflow 都要能 diff、replay、rollback。 |
| Always-On Agents | persistent agents 的关键问题是长期 process、privacy、autonomy、interruptibility 和 memory，不只是 checkpoint。 | 已新增 `ProcessLifecycleVerifier` 和 `RuntimeState.process_stage`；后续升级成 typed `ResearchSession`。 |
| Agentic Context Management | context rot / collapse / overload 说明上下文管理需要中间层，而不是靠超长上下文硬塞。 | 已新增 `CompactionVerifier` 检查 policy pins、artifact refs 和 approval boundary；后续扩展 active frame 与 decision-memory projection。 |
| Harness-MU | multi-turn tool-use benchmark 要记录完整 tool-call signal，harness 本身会影响 strategic behavior。 | eval result 继续强制绑定 provider/profile/policy/tool-contract fingerprints。 |
| MCPEvol-Bench | MCP server 会演化，tool discovery 和 schema drift 本身需要 benchmark。 | `ToolDescriptionContract` 后续支持 version lineage、deprecated tools、schema migration 和 discovery trace。 |
| Syll | 自然语言任务可编译为 runtime monitor 约束，跨 agent 执行时持续检查 correctness。 | 把 natural-language policy 编译到 `ActionPathPolicy` / `PermissionGraph` / monitor receipt。 |
| ByteRover | coding-agent memory 需要 hierarchy、retrieval efficiency 和安全边界，不能直接把所有代码上下文注入主上下文。 | Research memory 后续做 source-aware / artifact-aware projection，和 `MemoryCommitProtocol` 绑定。 |
| AI Runtime Infrastructures | agentic AI runtime 已经成为模型推理之外的基础设施层，挑战集中在 interoperability、scalability、security、state。 | `ProviderProfile` 不只描述模型，也描述 runtime/orchestrator/service capability。 |
| ACM: Agentic Context Management for Long Horizon Tasks | context selection/retention/compression 已经成为长任务 agent 的可优化 runtime 面。 | 已新增 `CompactionVerifier`；后续把 context pin retention 接入 replay/eval。 |
| SmoothAgent | long-horizon serving 里的 lookahead context engineering 会影响 cache、latency 和运行成本。 | context transformation 后续纳入 `FootprintMeter` 和 compaction budget。 |
| Cloudflare Agents | Durable Objects、state、SQLite-backed storage、scheduled tasks、RPC/MCP 组成 stateful agent runtime。 | 新增 `cloudflare-agents` profile；后续记录 durable-object/session refs。 |
| Vercel WorkflowAgent | AI SDK 把 durable/resumable agent 放进 workflow primitive。 | 新增 `vercel-workflow-agent` profile；后续把 workflow state 映射为 Hermes cursor。 |
| Mastra durable agents | suspend/resume、approval、background tasks、workflow snapshots/state 是显式 runtime primitives。 | 新增 `mastra-durable-agents` profile；后续对接 approval suspend/resume receipts。 |

## 5. Next Build Tasks

1. `protocol_profiles.py`：记录 MCP/A2A/AG-UI/OTel 的协议层定位和 fingerprint。
2. `tool_contracts.py`：把 tool description quality gate 编码，避免 MCP tool smell 直接进生产 harness。
3. `TraceEnvelope`：已增加 `protocol_fingerprint` 和 `tool_contract_fingerprint`，并由 profiled runtime tool event 写入。
4. `TraceEnvelope`：已增加 `skill_manifest_fingerprint`，profiled runtime tool event 可从 `active_skill_manifest` 写入。
5. `ReplayVerifier`：已比对 trace boundary、effect、protocol/tool contract/skill manifest hash；后续补 receipt-level diff。
6. `ActionPathPolicy`：已新增 path-level verifier 原型；后续接 Harness policy runtime check。
7. `SkillManifest`：已新增 permission-bearing skill artifact；后续和 skill registry/promote gate 接上。
8. `FootprintMeter`：已新增 checkpoint footprint reporting；后续接 nightly regression，追踪 state/events/artifacts 是否膨胀。
9. `PermissionGraph`：后续把 approval token 升级成 authority witness / data-flow / commit boundary 可验证对象。
10. `CompactionVerifier`：已新增，检查 summary/checkpoint 是否保留 policy pins、goal、process stage、artifact lineage、approval boundary 和 active skill constraints。
11. `PermissionGraph`：已新增轻量原型，支持 context labels、permission grants、authority witnesses、counterexamples 和 decision fingerprint。
12. `InterventionReplayWorkbench`：已新增 AgentCheck-style 原型，记录 fault injector / cached prefix / live suffix / mitigation effectiveness。
13. `MemoryCommitProtocol`：已新增 MemTX-style 原型，支持 staged/validated/committed/rejected/retracted、validation receipt、safety gate、cascade retract；后续接外部 memory provider。
14. `TransitionGraph`：已新增 AgentTether-style 原型，支持 state-changing transition units、critical chain、critical subgraph、branch points、transition verifier。
15. `ObligationAuditMap`：已新增 iCORE-style 原型，检查 evidence-backed obligation soundness、actor load 和 assignment stability。
16. `DecisionMemoryProjection`：已新增 stateless decision memory-style 原型，从 append-only committed log 投影任务相关记忆。
17. `HarnessDiagnosticWorkbench`：已新增 HTIR/HarnessFix-style 原型，把 replay divergence 映射到 transition unit、trace envelope drift、suspect surface 和 repair hint。
18. `ProviderProfile`：已扩展 AWS AgentCore、Microsoft Agent Framework、Pydantic AI durable execution、Mistral durable agents、Cloudflare Agents、Vercel WorkflowAgent、Mastra durable agents；后续给每个 profile 加 source verification metadata。
19. `ProcessLifecycleVerifier`：已新增 always-on state ledger 六轴审计，检查 process stage 与 persistent state authority/scope/mutability/provenance/recoverability/actionability。
20. `ResearchSession`：已新增 paper scan / hypothesis / experiment / analysis / review / writeup 的 typed lifecycle phases 与 evidence gate。
21. `EvidenceLedger`：已新增 source-backed claims、lineage、quarantine / retraction 和 claim citation；后续接 `ResearchSession` gate。
22. `ProviderProfile`：已新增 Microsoft Agent Governance Toolkit profile；后续把 policy/identity/sandbox/compliance 作为外部 governance evidence refs。

## 6. Sources

- MCP 2026-07-28 release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP 2026-07-28 changelog: https://modelcontextprotocol.io/specification/2026-07-28/changelog
- MCP tools spec: https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- A2A protocol: https://a2a-protocol.org/latest/
- AG-UI overview: https://docs.ag-ui.com/introduction
- OpenTelemetry AI agent observability: https://opentelemetry.io/blog/2025/ai-agent-observability/
- OpenTelemetry GenAI observability 2026: https://opentelemetry.io/blog/2026/genai-observability/
- OpenAI Agents: https://developers.openai.com/api/docs/guides/agents
- OpenAI Agents guardrails and human review: https://developers.openai.com/api/docs/guides/agents/guardrails-approvals
- OpenAI Agents tracing/observability: https://developers.openai.com/api/docs/guides/agents/integrations-observability
- OpenAI Sandbox Agents: https://developers.openai.com/api/docs/guides/agents/sandboxes
- OpenAI next evolution of the Agents SDK: https://openai.com/index/the-next-evolution-of-the-agents-sdk/
- Claude Agent SDK: https://code.claude.com/docs/en/agent-sdk/overview
- Claude Agent SDK permissions: https://code.claude.com/docs/en/agent-sdk/permissions
- Claude Agent SDK hooks: https://code.claude.com/docs/en/agent-sdk/hooks
- Claude Agent SDK observability: https://code.claude.com/docs/en/agent-sdk/observability
- Google ADK: https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk
- Google ADK 2.0: https://adk.dev/2.0/
- Temporal LangGraph plugin: https://temporal.io/blog/temporal-langgraph-plugin-durable-execution
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- Letta archival memory: https://docs.letta.com/v1-sdk/memory/archival-memory
- Letta memory blocks: https://docs.letta.com/v1-sdk/memory/memory-blocks
- Mem0 introduction: https://docs.mem0.ai/introduction
- OpenHands conversation persistence: https://docs.openhands.dev/sdk/guides/convo-persistence
- OpenHands direct tool execution caveat: https://docs.openhands.dev/sdk/api-reference/openhands.sdk.conversation
- DeepSeek Hermes integration: https://api-docs.deepseek.com/quick_start/agent_integrations/hermes/
- DeepSeek Reasonix integration: https://api-docs.deepseek.com/quick_start/agent_integrations/reasonix/
- MCP Tool Descriptions Are Smelly: https://arxiv.org/html/2602.14878v1
- DynamicMCPBench: https://arxiv.org/html/2607.20531v1
- LiveMCPBench: https://arxiv.org/abs/2508.01780
- MCP-Bench: https://arxiv.org/abs/2508.20453
- MCP-SandboxScan: https://arxiv.org/abs/2508.14322
- Runtime Governance for AI Agents: https://arxiv.org/abs/2603.16586
- Layered Translation Method for Runtime Guardrails: https://arxiv.org/abs/2604.05229
- SkillGuard: https://arxiv.org/abs/2606.03024
- SKILL.nb: https://arxiv.org/abs/2606.08049
- Aris: https://arxiv.org/abs/2605.03042
- OpenRath: https://arxiv.org/abs/2606.19409
- AgentFootprint: https://arxiv.org/abs/2607.11149
- A Data Model for Durable Intermediate Artifacts: https://arxiv.org/abs/2605.12087
- Evidence Tracing and Execution Provenance: https://arxiv.org/abs/2606.04990
- Filesystem-Based Memory for LLM Agents: https://arxiv.org/abs/2607.26637
- From Prompts to Contracts: Harness Engineering for Auditable Enterprise LLM Agents: https://arxiv.org/abs/2607.08028
- Harness-Bench: https://arxiv.org/abs/2605.27922
- Harness-1: https://arxiv.org/abs/2606.02373
- MemoHarness: https://arxiv.org/abs/2607.14159
- Natural-Language Agent Harnesses: https://arxiv.org/abs/2603.25723
- Slipstream: https://arxiv.org/abs/2605.08580
- Governance Decay: https://arxiv.org/abs/2606.22528
- Commit-Time Authorization: https://arxiv.org/abs/2607.10487
- Agentic Permissions Policy Algebra: https://arxiv.org/abs/2607.24625
- Hybrid Analysis for Secure MCP Tool Use: https://arxiv.org/abs/2607.25297
- Agent Skills Matter / SigLeak: https://arxiv.org/abs/2607.25560
- FAVA: https://arxiv.org/abs/2607.27267
- SKIMIX: https://arxiv.org/abs/2607.27994
- Long-Context Agentic Instruction Following Benchmark: https://arxiv.org/abs/2607.25398
- AgentCheck: https://arxiv.org/abs/2607.11098
- AgentTether: https://arxiv.org/abs/2607.06273
- Structured Graph Harness: https://arxiv.org/abs/2604.11378
- Harness-G: https://arxiv.org/abs/2607.27652
- iCORE: https://arxiv.org/abs/2607.27429
- MemTX: https://arxiv.org/abs/2607.23929
- Stateless Decision Memory: https://arxiv.org/abs/2604.20158
- Reliability-contagion feasibility: https://arxiv.org/abs/2607.21912
- Compile, Then Page: https://arxiv.org/abs/2607.11346
- AgentRadio: https://arxiv.org/abs/2607.28430
- SWE Atlas: https://arxiv.org/abs/2605.08366
- Self-Improving AI Coding Agents Through Accumulated Behavioral Rules: https://arxiv.org/abs/2607.13091
- HarnessFix: https://arxiv.org/abs/2606.06324
- Governed Evolution of Agent Runtimes: https://arxiv.org/abs/2605.27328
- Always-On Agents: https://arxiv.org/abs/2606.30306
- Agentic Context Management: https://arxiv.org/abs/2607.21503
- ACM: Agentic Context Management for Long Horizon Tasks: https://arxiv.org/abs/2607.23809
- SmoothAgent: https://arxiv.org/abs/2607.00151
- Harness-MU: https://arxiv.org/abs/2606.21856
- MCPEvol-Bench: https://arxiv.org/abs/2607.14642
- Syll: https://arxiv.org/abs/2606.07594
- ByteRover: https://arxiv.org/abs/2604.01599
- AI Runtime Infrastructures: https://arxiv.org/abs/2603.00495
- AWS Bedrock AgentCore: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html
- Microsoft Agent Framework: https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-at-build-2026-announce/
- Microsoft Agent Governance Toolkit: https://microsoft.github.io/agent-governance-toolkit/
- Microsoft Agent Governance Toolkit repo: https://github.com/microsoft/agent-governance-toolkit
- Pydantic AI durable execution: https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/
- Mistral durable agents: https://docs.mistral.ai/studio-api/workflows/building-workflows/durable_agents
- Cloudflare Agent class internals: https://developers.cloudflare.com/agents/runtime/lifecycle/agent-class/
- Vercel AI SDK WorkflowAgent: https://ai-sdk.dev/docs/agents/workflow-agent
- Mastra durable agents: https://mastra.ai/docs/long-running-agents/durable-agents
- Mastra suspend and resume: https://mastra.ai/docs/workflows/suspend-and-resume
- Mastra human-in-the-loop: https://mastra.ai/docs/workflows/human-in-the-loop
- Mastra workflow state: https://mastra.ai/docs/workflows/workflow-state
- Mastra snapshots: https://mastra.ai/docs/workflows/snapshots
