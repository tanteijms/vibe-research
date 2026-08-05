# Harness Implementation Matrix 2026

> 目标：把最新实现和论文压成工程矩阵，反推 `vibe-research` 的 Harness / Hermes 设计，而不是只保留调研笔记。

## 1. 快速结论

最新实现正在收敛到同一个形状：

- `OpenAI` 代表 managed agent runtime：Agents SDK、Responses API、Sandbox Agents、guardrails、tracing、eval hooks。
- `DeepSeek` 代表 provider/ecosystem adapter：OpenAI-compatible / Anthropic-compatible 接入、context caching、coding-agent integrations。
- `OpenHands` 代表 open-source software-agent runtime：SDK、Agent Server、workspace、remote execution、OpenAI-compatible endpoint。
- `Pi` 代表 minimal harness：小内核、extensions、skills、prompt templates、packages。
- `OpenClaw` 代表 personal control plane：多入口 UI / TUI / terminal、provider support、skills、local-first assistant。
- `LangGraph` 代表 Hermes 侧的 durable execution：checkpoint、state snapshots、interrupt、resume。
- `APPA / FAVA / CommitGuard` 代表 runtime governance 新重点：权限不是单点批准，而是 data-flow、authority witness 和 commit boundary。
- `AgentFootprint / Slipstream / Governance Decay` 代表长期任务新重点：checkpoint 大小、context compaction 和 policy retention 本身要被评测。
- `MemTX / Letta / Mem0` 代表 memory runtime 新重点：memory 写入不能直接等于 belief commit，长期记忆需要 lifecycle、validation、provenance 和 retraction。
- `Filesystem-Based Memory / EvidenceLedger` 代表现场恢复的新重点：恢复的不是整段上下文，而是可搜索、可分层、可验证的 memory/evidence scene。
- `Microsoft Agent Governance Toolkit` 代表实现侧的新重点：policy、identity、sandbox、compliance 可以作为独立治理栈接入 Harness。

对 `vibe-research` 来说，最优路线不是照抄某一家，而是：

```text
Hermes = LangGraph-style durable state + OpenAI/OpenHands-style session/workspace split
Harness = OpenAI-style guardrail/trace/eval + DeepSeek-style provider adapter + Pi-style extension surface
Research Runtime = Sandbox/session/artifact lineage + trace-to-evidence-to-replay-to-skill flywheel
```

## 2. 实现对照

| 实现 | 它实际在管什么 | 可借鉴的 harness 面 | 对科研 runtime 的改造 |
|---|---|---|---|
| OpenAI Agents SDK | agent loop、tools、handoffs、guardrails、sessions、tracing、人审中断 | 控制面和执行面高度集成；SDK 适合 managed workflows，Responses API 适合自己拥有 loop | 我们保留自己的 loop，但借鉴 guardrail、trace、tool envelope、session/approval 边界 |
| OpenAI Sandbox Agents | filesystem、shell、packages、ports、snapshots、resumable state；SDK sandbox orchestration 与 execution 可分离 | sandbox session 与 agent session 分离；workspace-heavy task 才进 sandbox | 科研实验必须绑定 sandbox id、snapshot ref、artifact refs，而不是只保存 chat state |
| OpenAI Evals / Graders | legacy eval API、graders、prompt optimizer、agent workflow eval | eval 应该贴近 trace 和 workflow，不只是离线问答集 | 我们把 replay drift、policy violation、artifact quality 都转成 graders |
| OpenAI next evolution of the Agents SDK / AgentKit | 更完整的 build/deploy/optimize 叙事、可视化 workflow、tracing、evaluation、tooling 组合 | 把 agent 生命周期做成产品化工作流，而不是仅 SDK 片段 | 我们可以借它的 workflow/product surface，但保留自有 harness policy 与 research runtime |
| DeepSeek integrations | Claude Code、OpenCode、OpenClaw、Pi/Oh My Pi、Hermes、Reasonix、Copilot 等 coding agent 接入 | provider adapter 是一等能力；相同模型可以服务不同 harness；thinking/tool-call 兼容性不能假设 | 我们把 DeepSeek 接成 cost-efficient reasoning provider，并记录 adapter capability snapshot、ignored parameter 和 cache accounting |
| OpenHands SDK | code agent SDK、tools、workspace、MCP、security/action confirmation、metrics、tracing、conversation persistence | 开源 runtime 把 SDK 和 Agent Server 分开，支持远程执行和 OpenAI-compatible endpoint；direct tool execution 可能绕过 loop safeguards | 我们可以仿照 SDK/Server 分层，把 core runtime 与 UI / API / worker 解耦；所有 bypass path 也必须进入 Harness trace |
| Claude Agent SDK | Claude Code 的 agent loop、内置工具、MCP、permissions、sessions、hooks、skills/plugins、OpenTelemetry 被 SDK 化 | 单 agent 工具循环和权限系统已经产品化；Managed Agents 与 Agent SDK 要分开理解；hook 顺序是治理语义的一部分 | 我们可借它的 permissions/hooks/session adapter 形状，但 durable execution 仍要自建或外接 |
| Google ADK / Agent Platform | ADK 2.0、Agent Runtime、A2A、MCP、Agent Gateway、Memory Bank、Sandbox、Evaluation、Observability | 企业平台把开发、运行、治理、反馈、沙箱放在一个平面；graph/dynamic/collaborative workflow 成为默认叙事 | 我们应保留薄 adapter，重点学习 governance/sandbox/eval surfaces |
| Microsoft Agent Governance Toolkit | policy engine、identity、sandbox、compliance、reliability hooks | framework-agnostic governance layer；适合在任何 agent loop 外包一层运行时安全 | 新增 `microsoft-agent-governance-toolkit` profile，把 policy/identity/sandbox evidence 映射成 Harness evidence refs |
| Temporal LangGraph Plugin | workflows、activities、signals、durable waits、continue-as-new、cross-worker recovery | 明确指出 checkpoint 不是 durable execution；human review 应由 durable orchestrator 接管 | Hermes 未来可以把 durable approval/wait/retry 交给 Temporal，LangGraph 保持状态机表达 |
| LangGraph persistence / interrupts | checkpointer、store、time travel、interrupt/resume | durable state 和 human-in-loop 形状成熟，但 memory fact lifecycle 需要额外协议 | 用 LangGraph 管状态机和 store，用 `MemoryCommitProtocol` 管 belief commit 与 retraction |
| Letta memory | memory blocks / archival memory 分层 | agent memory 已经产品化为可读写长期状态 | 借鉴 core/archival 分层，但科研 belief 晋升前必须有 validation receipt |
| Mem0 | 跨 sessions/tools/runs 的 long-term memory service | 外部 memory provider 可以托管存储，但不能替代本地 governance | provider-native memory id 映射成 `MemoryRecord.source_refs` / `metadata`，本地保留 commit gate |
| Pi | minimal harness、extensions、skills、prompt templates、packages、RPC/SDK | harness 可以极简，把变化放在 extension/package 层 | 我们的 skill 不要只是 prompt，应当是可安装、可测、可回放的 harness package |
| OpenClaw | personal AI assistant、Web UI/TUI/terminal、Skills、provider onboarding | local-first control plane 和多入口交互 | 适合参考 approval inbox、goal/session dashboard、provider onboarding |
| LangGraph | persistence、checkpointer、threads、state snapshots、human-in-loop | Hermes 侧最适合承接 durable execution / resume | 用 LangGraph 管状态机，但 Harness 自己管 policy、trace、provider capability |

## 3. 论文信号到工程决策

| 论文/方向 | 信号 | 工程决策 |
|---|---|---|
| Harness-1 | 让 harness 维护候选池、证据链、verification record、context rendering | Hermes state 不存大对象，但要存 artifact refs、evidence refs、render policy |
| EvidenceLedger / Filesystem-Based Memory | 现场恢复需要可搜索、可分层、可验证的 evidence scene，而不只是 transcript snapshot | `TraceEnvelope` 需要记录 evidence fingerprint / claim ids / receipt，回放时先校验证据场景 |
| MemoHarness | harness 可沿 context/tool/generation/orchestration/memory/output 六维优化 | Skill schema 拆成六个可 diff 的部分，eval 逐项归因 |
| Harness-Bench | agent 能力要在 model-harness configuration 层评估 | 每条 eval result 必须带 provider fingerprint 和 policy fingerprint |
| Harness Updating Is Not Harness Benefit | 更新能力和受益能力是两件事 | self-evo 评估要拆成 evolver 能力、executor 受益、held-out transfer |
| Long-Horizon-Terminal-Bench | 中间子任务和验证器比最终答案更能说明长期能力 | Hermes checkpoint 需要 step-level verifier，不只 final report |
| MCPAgentBench / MCP-Atlas | MCP server 定义本身成为 benchmark 对象 | MCP tool registry 要保存 schema hash、effect、permission、failure branch |
| DynamicMCPBench / LiveMCPBench / MCP-Bench | benchmark 开始覆盖真实 MCP server、动态服务发现、长链路任务和任务 handle | TraceEnvelope 要记录 protocol/tool contract hash，eval 要记录 service discovery trail |
| MCP Tool Descriptions Are Smelly | tool description 是 requirement + prompt 的混合规范；质量修复有收益也有成本 | tool 上线前需要 quality gate，并按任务选择 compact/rich description |
| Runtime Governance for AI Agents | policy 约束应该覆盖 action path，而不是只覆盖单步 action | Harness policy 后续增加 path-level verifier |
| SkillGuard / SKILL.nb | skill 是 permission-bearing、可复用、可执行 workflow artifact | SkillManifest 要进入 checkpoint/replay/promotion gate |
| Aris / OpenRath | 科研工作流越来越依赖 typed session、evaluation loop 和 artifact assembly | 已新增 `ResearchSession`，把科研 workflow 升级成 phase/evidence gate。 |
| MCP-SandboxScan / AgentFootprint / durable artifacts | MCP security、storage footprint、durable intermediate artifacts、execution provenance 变成核心指标 | checkpoint / trace / artifact reporting 要支持 sandbox evidence、footprint 和 provenance graph |
| Filesystem-Based Memory for LLM Agents | memory 可以作为 filesystem-like runtime surface，由管理、搜索、执行过程共同维护 | 已新增 `EvidenceLedger` 原型；后续把 memory/evidence organization 作为 hydration manifest 的一部分 |
| APPA | 通过 permission labels / taint / branch control 限制 agent 读写传播 | Harness policy 要从 tool-level 升级到 data-flow-level；不可信读取可以 fork branch，不直接污染主上下文 |
| FAVA | 自然语言任务经 Permission IR 生成 permission graph，在执行前寻找 violation path | Approval gate 可以返回 counterexample 和 proof bundle；权限审查要成为可回放对象 |
| Commit-Time Authorization | effect commit 边界要求 witness fresh / causally-before / effect-bound / qualified | 写入、发布、外部调用需要 commit-time verifier，不能只依赖早期人审 |
| MTGuard / Hybrid MCP Analysis | 静态风险分析 + 运行时监控联合治理 MCP lifecycle | MCP adapter 需要记录进程、文件、DNS、tool result 等 effect evidence |
| Governance Decay / Slipstream | compaction 会伤害 policy retention；compaction 质量可用后续轨迹检验 | Hermes checkpoint/resume 前要评估 summary 是否保留 policy、goal、artifact dependency |
| Agent Skills Matter / SKIMIX | skill 能力可能通过轨迹泄漏；skill mixture 的收益非单调 | Skill trace 要分 public/private 视图；skill routing 要有 budget 和 anti-dilution gate |
| AgentCheck | MCP fault-injection workbench 能复现 timeout、stale、poisoned-description 等真实工具故障，并用 cached prefix/live suffix 验证 mitigation | 已新增 `InterventionReplayWorkbench` 原型；后续接真实 MCP snapshot store、fault injector 和 mitigation regression |
| AgentTether | 将轨迹拆成 transition unit 和 critical transition graph，用图定位关键失败点并注入修复记忆 | 已新增 `TransitionGraph` 原型；failure attribution 支持 critical chain / critical subgraph / branch points |
| Structured Graph Harness / SGH | 把 agent loop 转成静态 DAG、immutable plan、分离 planning/recovery、严格升级路径 | Transition graph 后续区分 planned edge、runtime edge、recovery edge，成为可执行 scheduler harness 的中间层 |
| Harness-G | search agent harness 可以图结构表达状态、动作和检索路径 | `TransitionGraph` 后续可与 evidence/search frontier 绑定，支持 graph-shaped hydration 而不是线性 context restore |
| iCORE / obligation coupling | 用 cooperation graph、obligation graph、audit map 分析多 agent 协作责任 | Transition graph 后续加入 actor / obligation / audit responsibility 字段 |
| Obligation audit maps | multi-agent collaboration correctness 需要同时检查 work soundness 和 assignment stability | 已新增 `ObligationAuditMap`：evidence-backed obligation、actor load、assignment instability |
| MemTX | memory write 不是 belief commit；记录 evidence/permissions/provenance/validity，并用 staged transaction 防 downstream harm | 已新增 `MemoryCommitProtocol` 原型；Hermes memory/artifact 写入要 staged/validated/committed；不可逆 tool call 前检查 in-flight belief |
| Stateless Decision Memory | append-only event log + task-conditioned projection，避免可变记忆在 decision-time 悄悄漂移 | 已新增 `DecisionMemoryProjection`：只从 committed memory log 投影当前决策视图 |
| Reliability-contagion feasibility | multi-agent graph 连接度提升覆盖率，但也放大错误传播 | A2A/sub-agent topology 后续要加 reliability budget 和 contagion-aware routing |
| Compile, Then Page | 长 SOP 可以编译成可执行伪代码，runtime 通过 capability gate 和 active-frame paging 控制可见过程 | Natural-language policy 可以编译为 `PermissionGraph` / cursor frame；模型只看当前 active frame |
| AgentRadio / SWE Atlas | 长代码库理解受益于 clean contexts + asynchronous mid-course communication | A2A/sub-agent 层要分 clean local context、shared evidence graph、passive awareness channel |
| Self-Improving Behavioral Rules | 人审反馈可沉淀成 versioned rules 和 self-review checklist，跨 session 降低复发 | Self-Evo 先做 rule artifact + replay gate，再做 prompt rewrite |

## 4. Protocol Layer

| 协议 | 位置 | 新信号 | 工程含义 |
|---|---|---|---|
| MCP 2026-07-28 | agent ↔ tools/data | stateless core、MRTR、header routing、cacheable list、Tasks extension | tool state 必须显式化为 handle；trace 要记录 method/name/schema/cache/task |
| A2A | agent ↔ agent | opaque agents 跨框架协作 | 远程 agent 先作为 governed tool 接入，等待 delegation receipt 稳定后再开放多 agent |
| AG-UI | agent ↔ user interface | event-based UI state、interrupt、approve/edit/retry、steering | approval inbox 和 Hermes cursor 应该走 typed event stream |
| OpenTelemetry GenAI | observability | agent framework semantic conventions 正在标准化 | TraceEnvelope 要预留 OTel 映射，不锁死到某个 vendor trace |

## 5. 我们下一版 schema 应该长这样

```text
RuntimeState
  task/session/run ids
  cursor + active step
  budget state
  policy snapshot hash
  provider capability snapshot hash
  active skill manifest
  pending approval
  artifact refs
  sandbox/session refs
  trace id

TraceEnvelope
  boundary: llm/tool/sandbox/approval/checkpoint/eval
  provider fingerprint
  protocol fingerprint
  tool contract fingerprint
  skill manifest fingerprint
  policy fingerprint
  action effect
  input/output hash
  artifact refs
  proof receipts

ProviderProfile
  api style
  tool modes
  state surfaces
  governance surfaces
  trace/eval/sandbox surfaces
  caveats
  source refs
  fingerprint

ProtocolProfile
  layer
  primitives
  state policy
  governance hooks
  trace hooks
  runtime implications
  fingerprint

ToolDescriptionContract
  purpose
  input/output schema
  limitations
  side effects
  failure modes
  examples
  compact/rich context strategy

SkillManifest
  purpose
  context influence
  required tools/capabilities
  evidence gates
  fallback paths
  action effects
  fingerprint
```

## 6. Immediate Build Tasks

1. `provider_profiles.py` 从简单备注升级成可 checkpoint 的 capability profile。
2. 新增 `trace_contract.py`，定义 trace v2 envelope 和 proof receipt。
3. 新增 `protocol_profiles.py`，定义 MCP/A2A/AG-UI/OTel 的协议定位。
4. 新增 `tool_contracts.py`，定义 tool description quality gate。
5. `HarnessHermesRuntime` 已能在 profiled tool event 中写入 provider/protocol/policy/tool-contract fingerprints。
6. `ReplayVerifier` 已能比对 trace envelope 的 boundary/effect/fingerprint 漂移；后续再补 receipt-level diff。
7. `SkillManifest` 已作为 permission-bearing artifact 接入 trace envelope；后续再做 skill registry/promote gate。
8. `ActionPathPolicy` 已作为 path-level verifier 原型接入 replay/eval。
9. `Skill` 后续拆成 context/tool/generation/orchestration/memory/output 六个可测试面。
10. `FootprintMeter` 已落地为 checkpoint footprint reporter，后续接 nightly regression。
11. `PermissionGraph` 后续建模 authority witness、data-flow label、commit-time authorization。
12. `CompactionVerifier` 已新增：检查 summary/checkpoint 是否保留 policy pins、goal、cursor、process stage、artifact lineage、approval boundary 和 active skill constraints。
13. `McpLifecycleEvidence` 后续记录静态 schema risk + 动态 effect signals。
14. `PermissionGraph` 已新增轻量原型：context labels、permission grants、authority witnesses、decision fingerprint、counterexamples。
15. `InterventionReplayWorkbench` 已新增：支持 fault injection、cached prefix / live suffix 分析、mitigation effectiveness。
16. `MemoryCommitProtocol` 已新增：支持 staged memory write、validation receipt、commit report、safety gate、cascade retraction。
17. `TransitionGraph` 已新增：支持 state-changing transition units、critical chain、critical subgraph、branch points、transition verifier。
18. `ObligationAuditMap` 已新增：支持 obligation soundness、evidence links、actor load、assignment instability。
19. `DecisionMemoryProjection` 已新增：支持 committed memory log 的 task-conditioned projection。
20. `HarnessDiagnosticWorkbench` 已新增：把 replay divergence 映射到 transition graph、trace envelope drift、suspect harness surface 和 repair hint。
21. `ProviderProfile` 已扩展：AWS AgentCore、Microsoft Agent Framework、Pydantic AI durable execution、Mistral durable agents、Cloudflare Agents、Vercel WorkflowAgent、Mastra durable agents 都能作为 checkpoint capability snapshot。
22. `ProcessLifecycleVerifier` 已新增：把 always-on persistent state 的 authority/scope/mutability/provenance/recoverability/actionability 六轴审计接入 Hermes state。
23. `ResearchSession` 已新增：支持 paper_scan / hypothesis / experiment_plan / experiment_run / analysis / review / writeup / archive 的 phase topology 和 evidence gate。
24. `EvidenceLedger` 已新增：支持 source-backed claim lineage、quarantine/retraction、derived evidence parent chain；后续接 `ResearchSession`、`TraceEnvelope` 和 compaction freshness。
25. `ProviderProfile` 已新增 Microsoft Agent Governance Toolkit：后续把 framework-agnostic policy/identity/sandbox/compliance 记录映射成 Harness receipts。
26. `HydrationManifest` 已新增：把 state / policy / trace / artifact / memory / evidence / research-session fingerprints 组成可验证 research scene；后续接 benchmark runner 的 resume preflight。
27. `ResearchSession` 已接 `EvidenceLedger`：phase gate 可要求 evidence claim ids 并阻断 missing / unsupported / quarantined claims；后续把 claim-level gate 指标接进 FSE benchmark runner。
28. `FseBenchmarkPlan` / `SyntheticFseBenchmarkRunner` / `SyntheticFseTraceRunner` / `FseLocalToyTaskRunner` 已新增：把 issue-to-patch / artifact-replication / incident-RCA 三类 task family、baseline、fault taxonomy、ablation、metric、RQ、related work 和 data availability 结构化，展开成 140 个 synthetic experiment cells，生成 deterministic replay / diagnosis / evidence-drift result report，并跑通三类 local toy artifact task；最新矩阵已吸收 context manager dropped pin 与 benchmark oracle drift 两类 FSE-validity fault。
29. `scripts/run_fse_local_benchmark.py` 已新增：生成 FSE artifact-package smoke 输出，包括 plan / readiness / matrix / synthetic trace / local run / SWE-bench adapter / SWE-bench executor / artifact manifest / summary JSON 报告，并由 `tests/test_fse_artifact_cli.py` 验证可复现输出。
30. `SweBenchSmallSubsetAdapter` 已新增：接受 SWE-bench-style JSONL 或内置 demo subset，生成 problem / gold patch / candidate patch / test patch / correctness report artifacts，并把 patch divergence、evidence ledger、memory commit、ResearchSession gate 和 HydrationManifest 串起来。
31. `SweBenchLocalPatchExecutor` 已新增：复制本地 repo，应用 regression-test patch 与 candidate patch，运行测试命令，捕获 stdout/stderr/execution report，并把执行证据接进 EvidenceLedger、MemoryCommitProtocol、ResearchSession gate 和 HydrationManifest；后续替换为真实 SWE-bench Verified small subset executor / Docker harness。
32. `SweBenchOfficialSubsetBridge` 已新增：把 official-style instances JSONL、predictions JSONL、official harness command、subset manifest 和 per-instance oracle-audit receipts 打包成可审稿前置 artifact；后续把 Docker execution report 接回同一 evidence / hydration / replay contract。

## 6. Continuation Matrix: failure diagnosis and runtime profiles

| 新材料 | 关键判断 | 已吸收 / 下一步 |
|---|---|---|
| HarnessFix / HTIR | 失败轨迹要转成中间诊断表示，区分 planner/tool/context/policy/harness flaw，再驱动 repair/eval。 | 已新增 `HarnessDiagnosticWorkbench`；下一步把 diagnosis report 自动转 eval case。 |
| Agentic Context Management / ACM | context 需要独立管理层处理选择、压缩、结构化和退化检测。 | 已新增 `CompactionVerifier`，把 context drift 映射到 resume gate；后续接 `planning_or_context_rendering` suspect surface。 |
| Governance Decay | compaction 会静默擦除 safety constraints。 | `CompactionVerifier` 把 policy pins、approval boundary、artifact lineage 变成必须保留的 hash pins。 |
| SmoothAgent | lookahead context engineering 会影响 long-horizon serving 的 cache 和 runtime cost。 | context transform 后续进入 `FootprintMeter` 和 compaction budget。 |
| MCPEvol-Bench | MCP server/tool 会演化，工具发现和 schema drift 会影响 agent 表现。 | `ToolDescriptionContract` 后续加 version lineage、schema migration、deprecated tool warning。 |
| Syll | NL task 可编译成 runtime monitor/LTL-like constraint，执行时持续检查。 | `ActionPathPolicy` / `PermissionGraph` 后续可作为 natural-language policy compilation target。 |
| Always-On Agents | persistent agent 的核心是长期 process lifecycle，不只是 message persistence。 | 已新增 `RuntimeState.process_stage`、`ProcessLifecycleVerifier` 和 state ledger 六轴审计；后续升级 `ResearchSession`。 |
| Governed Evolution of Agent Runtimes | runtime 自演化需要 versioned entity/operation/knowledge/evolution platform。 | Self-Evo 后续改成 runtime artifact evolution：skill/rule/policy/workflow 都要 replay gate。 |
| ByteRover | coding-agent memory 需要有效、低成本、安全，和代码结构/任务上下文绑定。 | `DecisionMemoryProjection` 后续增加 code/artifact/source-aware projection。 |
| AWS Bedrock AgentCore | managed runtime 把 memory、identity、gateway、browser/code tools、observability/eval 打包。 | 新增 `aws-bedrock-agentcore` profile；未来接 identity witness / gateway evidence adapter。 |
| Microsoft Agent Framework | 多 agent orchestration、workflow、enterprise integration、observability/eval 正在被统一。 | 新增 `microsoft-agent-framework` profile；未来接 workflow trace 和 connector permission adapter。 |
| Pydantic AI durable execution | typed Python agents 正在接 durable execution backend。 | 新增 `pydantic-ai-durable` profile；未来可导入 typed tool schema 到 `ToolDescriptionContract`。 |
| Mistral durable agents | approval、handoff、parallel agent step 已成为 workflow primitive。 | 新增 `mistral-durable-agents` profile；未来接 approval state / handoff receipt。 |
| Cloudflare Agents | Durable Objects / state / scheduling / RPC / MCP 是 stateful agent 的平台原语。 | 新增 `cloudflare-agents` profile；未来接 durable-object session refs 与 scheduler trace。 |
| Vercel WorkflowAgent | durable/resumable agent 被建模成 workflow agent。 | 新增 `vercel-workflow-agent` profile；未来把 workflow state 映射为 Hermes cursor。 |
| Mastra durable agents | suspend/resume、approval、background tasks、workflow snapshots/state 是一等对象。 | 新增 `mastra-durable-agents` profile；未来接 approval suspend/resume receipts。 |

## 7. Sources

- OpenAI Agents: https://developers.openai.com/api/docs/guides/agents
- OpenAI Agents SDK: https://openai.github.io/openai-agents-python/
- OpenAI Agents guardrails and human approval: https://developers.openai.com/api/docs/guides/agents/guardrails-approvals
- OpenAI Agents tracing/observability: https://developers.openai.com/api/docs/guides/agents/integrations-observability
- OpenAI Sandbox Agents: https://developers.openai.com/api/docs/guides/agents/sandboxes
- OpenAI Evals: https://developers.openai.com/api/docs/guides/evals
- OpenAI next evolution of the Agents SDK: https://openai.com/index/the-next-evolution-of-the-agents-sdk/
- DeepSeek coding agents: https://api-docs.deepseek.com/guides/coding_agents/
- DeepSeek Hermes integration: https://api-docs.deepseek.com/quick_start/agent_integrations/hermes/
- DeepSeek Reasonix integration: https://api-docs.deepseek.com/quick_start/agent_integrations/reasonix/
- OpenHands SDK: https://docs.openhands.dev/sdk
- OpenHands Agent Server: https://docs.openhands.dev/sdk/arch/agent-server
- OpenHands conversation persistence: https://docs.openhands.dev/sdk/guides/convo-persistence
- OpenHands direct tool execution caveat: https://docs.openhands.dev/sdk/api-reference/openhands.sdk.conversation
- Pi harness: https://pi.dev/
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
- MCP 2026-07-28: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP tools spec: https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- A2A: https://a2a-protocol.org/latest/
- AG-UI: https://docs.ag-ui.com/introduction
- OpenTelemetry AI agent observability: https://opentelemetry.io/blog/2025/ai-agent-observability/
- OpenTelemetry GenAI observability 2026: https://opentelemetry.io/blog/2026/genai-observability/
- Harness-1: https://arxiv.org/abs/2606.02373
- MemoHarness: https://arxiv.org/abs/2607.14159
- Harness-Bench: https://arxiv.org/abs/2605.27922
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
