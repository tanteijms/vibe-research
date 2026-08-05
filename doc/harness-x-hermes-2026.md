# Harness x Hermes 2026 迭代设计

> 目标：把 5 月份的 `Persistent Research Runtime` 设计升级成更贴近 2026 agent runtime 方向的版本。这里按用户口径把 `dpsk` 理解为 DeepSeek。

## 1. 新判断

5 月版本把 Harness 主要理解成预算、安全、沙箱和审计，这是对的，但现在可以再往前推一步：

**Harness 不只是 guardrail，而是 agent runtime 的控制平面。**

它应该同时覆盖：

- policy：预算、权限、审批、超时、重试、输出脱敏
- capability：不同模型/provider 的工具调用、reasoning、context、cache 能力差异
- trace：每一次 LLM/tool/sandbox 边界都可审计
- eval：用真实 trace 反推 regression case
- replay：失败和成功都能复现
- trace-receipt：evidence ledger fingerprint / claim ids / proof receipt 跟着 trace 一起落盘
- promotion：只有通过 eval 的 workflow 才能进入 skill registry

Hermes 仍然是状态连续性层，但它不能只是 checkpoint 存储。它应该记录“下一次如何安全继续”，也就是把 Harness 的 policy snapshot、provider capability snapshot、budget state、pending approval 一起持久化。

## 2. 外部调研结论

### 2.1 OpenAI 方向

OpenAI 当前的 agent harness 思路大致是：

- Agents SDK 把 agent、handoff、guardrails、sessions 和 tracing 组合成标准运行框架。
- Guardrails 分成 input guardrails 和 output guardrails，可以和 agent 并行运行，也可以在输出后校验。
- Tracing 变成一等公民，agent runs、LLM generations、tool calls、handoffs、guardrails、custom spans 都能进入 trace。
- Responses API 已经成为 tool-using agent 的统一接口，内置 tools 包括 web search、file search、computer use、code interpreter、image generation、remote MCP 等。
- Sandbox Agents 把远程 sandbox session、workspace、snapshot、resume 做成标准能力；这对长期科研任务非常关键。
- Evals/graders 方向更偏“trace -> dataset -> grader -> regression”，OpenAI 的旧 Evals API 已标注为 legacy，新的重点是 graders、datasets、prompt optimization 和 trace grading。

对本项目的启发：Harness 应该把 `tool authorization`、`trace schema`、`eval case generation`、`sandbox session binding` 做成核心接口，而不是只做 token 计数器。

### 2.2 DeepSeek / dpsk 方向

DeepSeek 当前最值得关注的是 agent 能力和成本效率：

- DeepSeek V4-Flash 已在 API public beta 中，官方配置里强调更高的 max reasoning effort、较低延迟和 agentic use case。
- 官方 Codex 集成文档推荐 OpenAI-compatible profile，并提到 DeepSeek Harness minimal mode 会发布，用于 sandboxed coding benchmark、agent tool use benchmark、frontend app build、repair 和 visual testing。
- DeepSeek 的 Pi 集成页把 Pi 直接定义成一个 minimal terminal coding harness，并且支持 DeepSeek-V4-Pro / DeepSeek-V4-Flash 作为后端模型。
- API 文档仍强调 context caching、function calling、JSON output、FIM completion 等基础能力。

对本项目的启发：DeepSeek 更适合作为 `cost-efficient reasoning/provider` 接入 Harness，而不是直接照搬 OpenAI 的 Agent SDK。需要做 provider capability adapter，记录哪些参数被支持、哪些参数会被忽略、工具调用 schema 是否严格、context cache 如何计费。

## 3. 新的模块关系

```text
------------------------+
| Human Researcher      |
+-----------+------------+
            |
            v
+------------------------+        +--------------------------+
| Hermes Runtime         | <----> | Checkpoint Store         |
| task/session/run       |        | state + policy snapshot  |
| cursor/rehydration     |        | provider snapshot        |
| pending approval       |        | artifact refs            |
+-----------+------------+        +--------------------------+
            |
            v
+------------------------+
| Harness Control Plane  |
| policy/capability      |
| approval/budget        |
| trace/eval/replay      |
+-----------+------------+
            |
            v
+------------------------+        +--------------------------+
| Tool / MCP / Sandbox   | -----> | Artifact Store           |
| file/code/web/search   |        | logs/metrics/snapshots   |
+------------------------+        +--------------------------+
```

## 4. Harness 应该新增的深层能力

### 4.1 Provider Capability Adapter

不要在业务代码里散落 `if provider == openai/deepseek`。

应该统一成：

- supported APIs：responses/chat/openai-compatible
- tool mode：native/strict/function_call/manual JSON
- reasoning control：none/effort/tokens
- context policy：context window、cache hit、cache cost
- unsupported parameter policy：fail-fast 或 audit warning
- output contract：JSON/schema/markdown/artifact

每个 checkpoint 里保存 provider snapshot，避免今天恢复昨天的任务时 provider 行为已经变了。

### 4.2 Trace-First Harness

trace 不是日志，是未来 replay/eval/skill mining 的原始材料。

每个事件至少要记录：

- task/session/run id
- node/cursor
- model/provider snapshot
- policy snapshot hash
- tool name + args hash
- output hash
- artifact refs
- budget delta
- failure attribution
- approval record
- evidence receipt / claim ids

### 4.3 Approval-Gated Execution

科研 runtime 里，高危动作不是“永远禁止”，而是进入 `awaiting_approval`：

- 写文件
- 执行 shell/python
- 联网下载
- 调用外部 API
- 长时间训练任务
- 产生高成本 LLM 调用

Hermes 保存 pending tool call；人类批准后恢复继续。

### 4.4 Trace-to-Eval Flywheel

不要一开始追求自动 prompt rewrite。更稳的是：

```text
trace
  -> failure attribution
  -> eval case
  -> regression run
  -> skill candidate
  -> promotion gate
```

也就是说，Self-Evo 的入口不是 prompt，而是 Harness trace。

现在这个 trace 还要进一步带上 evidence scene：回放要能判断同一 action 是否仍然依赖同一版证据账本，而不是只判断 tool 输出 hash 是否一致。

### 4.5 Sandbox Session Binding

长期科研任务一定会涉及代码、环境、实验日志、metrics 和中间 artifact。

因此 checkpoint 不能只保存 `state.json`，还要保存：

- sandbox session id
- workspace snapshot ref
- git commit
- env lockfile hash
- dataset/artifact refs
- metrics/log refs

## 5. 与科研业务结合

推荐第一条业务链路不要做“大而全 AI Scientist”，而是做：

```text
research question
  -> paper scan
  -> baseline selection
  -> sandbox setup
  -> experiment run
  -> metric collection
  -> checkpoint
  -> replay
  -> eval
  -> skill distillation
```

最先沉淀的 skill：

- `paper_scan`
- `baseline_reproduce`
- `experiment_debug`
- `metric_report`

## 6. MVP 开发顺序

1. 最小 state schema：只存 task cursor、budget、policy snapshot、artifact refs、pending approval。
2. Harness policy：allowlist、budget、approval、timeout、redaction。
3. Hermes checkpoint：保存和恢复 state + trace。
4. Replay verifier：先校验 tool sequence、args hash、output hash。
5. Provider profile：先抽象 OpenAI/DeepSeek 的 capability，而不是立刻接完整 SDK。
6. Eval seeds：从 replay failure 自动生成 regression case。

更新后的实现对照矩阵见 `doc/harness-implementation-matrix-2026.md`。这份矩阵把 OpenAI、DeepSeek、OpenHands、Pi、OpenClaw、LangGraph 和几篇近期论文映射到具体工程决策。

持续追踪协议、论文和实现动态的 watchlist 见 `doc/research-watchlist-2026.md`。

## 7. 本轮落地

本仓库已经新增一个纯 Python 最小原型：

- `src/vibe_research/schema.py`
- `src/vibe_research/harness.py`
- `src/vibe_research/hermes.py`
- `src/vibe_research/runtime.py`
- `src/vibe_research/eval.py`
- `src/vibe_research/provider_profiles.py`
- `src/vibe_research/footprint.py`
- `src/vibe_research/fse_benchmark.py`
- `src/vibe_research/fse_benchmark_runner.py`
- `src/vibe_research/fse_local_runner.py`
- `src/vibe_research/swebench_adapter.py`
- `scripts/verify_runtime.py`
- `scripts/verify_fse_benchmark.py`
- `scripts/run_fse_local_benchmark.py`
- `tests/test_harness_hermes.py`
- `tests/test_fse_benchmark.py`
- `tests/test_fse_local_runner.py`
- `tests/test_fse_artifact_cli.py`
- `tests/test_swebench_adapter.py`

验证内容：

- `secrets.txt` 被 ignore
- 超预算工具不会执行
- 高风险工具进入 approval checkpoint
- resume 后可以审批继续
- 输出会做 secret redaction
- replay verifier 可以发现 drift
- footprint reporter 可以量化 checkpoint/state/event/artifact/skill manifest 膨胀
- FSE benchmark scaffold 可以检查 task family / baseline / fault / ablation / RQ / metrics coverage
- synthetic trace runner 可以把 152 个 planned experiment cells 变成 deterministic replay / diagnosis / evidence-drift result report
- local toy runner 可以在临时目录里跑 issue-to-patch / artifact replication / incident RCA 三类真实文件 artifact smoke，并验证 evidence / memory / phase gate / hydration
- SWE-bench-style adapter 可以把 issue-to-patch JSONL 转成 problem / gold patch / candidate patch / test patch / correctness report artifacts，并生成 patch divergence、evidence、memory 和 hydration 报告
- SWE-bench-style local patch executor 可以复制本地 repo、应用 test/candidate patches、运行测试，并把 stdout/stderr/execution report 纳入 evidence / memory / hydration
- artifact-package smoke CLI 可以生成 FSE 复现包雏形：benchmark plan、readiness、matrix、synthetic trace、local run、SWE-bench adapter、SWE-bench executor、artifact manifest 和 summary JSON

## 8. 最新论文与实现快照

这批新材料最关键的信号不是“又多了几个 benchmark”，而是整个行业开始把 harness 当成一等公民。

| 方向 | 代表材料 | 关键结论 | 对本项目的启发 |
|---|---|---|---|
| Harness 综述 | *From Question Answering to Task Completion: A Survey on Agent System and Harness Design* | 把 harness 拆成 `observation / context / control / action / state / verification-governance` 六个责任面。 | 我们的 state / policy / replay / eval 应该按 runtime 责任分层，而不是按功能页面堆代码。 |
| 代码即 harness | *Code as Agent Harness* | 代码不只是输出物，而是可执行、可验证、可持久化的 agent medium。 | 应该把临时脚本、测试、workflow、skill 都看成 harness 的一部分。 |
| 真实长链路 benchmark | *WildClawBench* | 真实 CLI harness、真实工具、混合评分；同一个模型换 harness 最多能差 18 分。 | harness 不是外壳，是真正影响能力的变量，必须纳入 eval。 |
| 研究型 harness | *ToFu* | 白盒、可修改、低 token 成本的 agent harness，适合研究者直接 inspect 和调 orchestration。 | 我们应该把 runtime 做成可观察、可改、可测的研究对象。 |
| 自进化评测 | *SEAGym* | self-evolving agent 更新的是 persistent harness state，评估重点在更新过程、回退和遗忘。 | self-evo 不应先改 prompt，而应先改可持久化的 workflow / skill / state。 |
| 行为证明 | *Proof-Carrying Agent Actions* | 通过证书、approval receipt、proof bundle、replay bundle 让高价值动作可审计。 | 适合我们把审批、replay、provenance 做成统一证据链。 |
| Terminal 工具链 | *Terminal-Bench 2.0* / *Long-Horizon-Terminal-Bench* | 长时 CLI 任务必须看中间子任务和验证器，而不是只看最终答案。 | 我们需要 step-level checkpoint 和 graded subtasks。 |
| MCP 工具基准 | *MCP-Atlas* / *DynamicMCPBench* / *LiveMCPBench* | 真实 MCP server、跨 server 组合、effect-level scoring、动态服务发现逐渐成为新基准。 | 未来我们的 tool registry 要和 MCP 语义对齐，并记录 effect、service discovery、任务 handle，而不只是调用次数。 |
| OpenAI 实现 | Agents SDK + Sandbox Agents + Programmatic Tool Calling | tracing、guardrails、sandbox、session resume、capability binding、programmatic tool calling 已经合在一套 runtime 里；Evals 方向正在退役，Datasets/Grader 更像新的迭代入口。 | OpenAI 已经把控制面、执行面、追踪面做成产品化范式，我们可以直接借这个形状，并把评测从单次 eval 转成 trace-driven 迭代。 |
| DeepSeek 实现 | V4-Flash / Responses API / Pi / OpenCode / Claude Code / OpenClaw | 重点在 agentic coding、context caching、JSON output、OpenAI-compatible 接入、terminal harness。 | DeepSeek 更像成本效率和 terminal harness 的 provider 候选，不是单纯聊天模型。 |
| Open-source 实现 | OpenHands Agent Canvas / SDK / Agent Server / OpenClaw / Reasonix | current V1 把 UI、SDK、Agent Server 明确拆开；OpenClaw 和 Reasonix 则继续强化 local-first control plane 和 cache-first terminal loop。 | 我们的 runtime 可以借鉴“核心引擎和 UI/app 解耦”的结构。 |

### 8.1 这轮调研得到的三个硬结论

1. `model` 和 `harness` 已经不能分开看，agent 能不能干活，越来越取决于 runtime 设计。
2. `trace -> eval -> replay -> promotion` 正在变成新的闭环，而不是单次对话式体验。
3. `pause / resume / approval / proof bundle` 这类能力，已经是长期任务型 agent 的标配，不再是高级选项。

### 8.2 追更：更近的论文和实现

下面这批材料更贴近“现在业内到底怎么做”，也更接近我们这个科研 runtime 的落点。

| 方向 | 最新信号 | 我们该怎么吸收 |
|---|---|---|
| Harness-Bench | 明确把 benchmark 设计成 model-harness configuration level，而不是只比 base model。 | 以后自己的 eval 不能只记模型名，要把 harness 配置、budget、sandbox、trace 一起存。 |
| Is Grep All You Need? | 同样的数据，在不同 harness 和 tool-calling 风格下，grep 和向量检索的结果会显著变化。 | 检索层不要先入为主地押宝向量库，科研 runtime 里 lexical + structured retrieval 要保留。 |
| NLAH / IHR | 可以把 harness policy 外化成可编辑自然语言，再由 shared runtime 执行。 | 我们的 skill / policy 可以考虑“文本化规则 + 可执行 runtime”双层结构。 |
| PCAA | 用 action certificate、approval receipt、replay-ready proof，把治理从 vendor session record 提升成可移植证据链。 | 审批、证明、回放这三件事最好做成统一对象，而不是散落日志。 |
| SEAGym | self-evolving agent 的评估应覆盖训练、验证、测试、replay 和 cost records。 | self-evo 层必须看回放和成本，不要只看单次分数。 |
| MCPAgentBench | real-world MCP definitions 正在成为 MCP tool use 的主流评测对象。 | 我们的 MCP 接入层应该能直接挂 benchmark / regression case。 |
| Long-Horizon-Terminal-Bench | 任务被拆成 graded subtasks，强调中间验证和容器内 terminal 过程。 | 长任务不能只看最终答案，要看每个中间 checkpoint。 |
| Pi | minimal agent harness，强调 extensions / skills / prompt templates / themes / tree sessions / steer vs follow-up。 | 说明 harness 也可以走极简、可编排、可扩展的路线，不一定要把能力全塞进内核。 |
| OpenHands Agent Canvas / SDK / Agent Server | current V1 把 UI、SDK、Agent Server 明确拆开；OpenHands 的主线已经转向这个结构。 | 我们的 runtime 可以借鉴“核心引擎和 UI/app 解耦”的结构。 |
| OpenClaw | 2026.7.1 release 强化了 control UI、provider support、sessions、goals、Codex/connected coding-agent workflows。 | 开源 assistant 方向正在把 goal/session/control plane 做成产品化能力。 |
| DeepSeek docs | 官方把 Claude Code、OpenCode、OpenClaw、Pi、Deep Code、Hermes 都列进 agent integrations。 | DeepSeek 现在更像“可直接接入的 coding-agent provider 生态”，不是单一聊天 API。 |

### 8.3 对我们项目的直接改动建议

- 把 `harness` 的一级概念从“安全和预算”升级成“控制平面 + 可回放证据链”。
- 把 `hermes` 的一级概念从“checkpoint 存储”升级成“session / approval / provenance / resume 协议”。
- 把 `eval` 的一级概念从“单测”升级成“trace 驱动的 harness regression”。
- 把 `retrieval` 的一级概念从“向量检索”升级成“lexical / structured / cache-aware 组合策略”。
- 把 `skill` 的一级概念从“prompt 模板”升级成“可执行 harness skill + policy artifact”。

### 8.4 Hydration / Dehydration 的新版定义

最早的设计重点是“上下文现场”：Agent 做到一半能脱水，之后再复水继续。现在这个想法可以更精确地落成 `research scene manifest`。

Dehydration 不应该保存一整坨聊天历史，而应该保存：

```text
RuntimeState
  task/session/run id
  cursor + active step
  run status + process stage
  budget state
  policy/provider/protocol/tool/skill fingerprints
  pending approval + authority witness
  artifact refs
  trace envelope refs
  memory record ids
  evidence ledger fingerprint
  research phase + phase gate report
```

当前代码里这个对象已经落成 `HydrationManifest` 原型，用来把可恢复现场固定成一份 manifest，而不是依赖隐式上下文。

Hydration 也不是简单把上下文塞回模型，而是：

```text
checkpoint
  -> verify compaction pins
  -> restore pending action / approval boundary
  -> re-project committed memory
  -> validate active evidence claims
  -> restore current research phase
  -> render only the active frame
  -> continue under current Harness policy
```

这让 `vibe-research` 的恢复语义从：

```text
恢复对话
```

升级成：

```text
恢复一个可验证、可审计、可继续执行的科研现场
```

本轮新增的 `EvidenceLedger` 就是这个现场里的证据层。它和 `MemoryCommitProtocol` 的区别是：

- `MemoryCommitProtocol` 判断某条观察能不能成为 committed belief；
- `EvidenceLedger` 判断某条科研 claim 还有没有 active / source-backed / non-quarantined evidence 支撑。

当前 `ResearchSession` 已经可以在 phase gate 里要求 `required_evidence_claim_ids`。这意味着 `writeup` 这类阶段不再只看 artifact 是否存在，还要看 claim 是否由 active evidence ledger 支撑。

外部新信号也支持这个方向：

- *Filesystem-Based Memory for LLM Agents* 把长期记忆看成可管理、可搜索、可执行的 filesystem-like surface；
- *Harness-G* 把 search agent harness 做成图结构，说明 context/action/evidence surface 不必是线性 prompt；
- Microsoft Agent Governance Toolkit 则说明 policy、identity、sandbox、compliance 可以成为 framework-agnostic governance layer。

所以当前架构可以理解成：

```text
Hermes 负责把现场带回来
Harness 负责判断现场能不能继续
EvidenceLedger 负责证明现场为什么可信
ResearchSession 负责决定科研流程能不能进入下一阶段
```
### 8.4 2026-08-02 追更：治理、压缩、footprint

这轮新增材料进一步把方向压实了：下一代 agent runtime 的核心风险不是“模型会不会调用工具”，而是“读入什么数据后，哪些权力还有效；压缩/恢复后，哪些约束还存在；长期执行后，状态足迹是否还能被治理和回放”。

本轮新增判断：

| 新信号 | 对 Harness x Hermes 的含义 |
|---|---|
| APPA / FAVA | 权限应从 tool-level allow/deny 升级到 data-flow label、permission graph、counterexample 和 proof bundle。 |
| Commit-Time Authorization | 高价值 effect 不能只在 action 开始前审批，还要在 commit boundary 校验 authority witness 是否仍然新鲜且绑定同一效果。 |
| MTGuard / Hybrid MCP Analysis | MCP 工具安全要覆盖 discovery、schema、invocation、process/file/network side effects、output 和 downstream action。 |
| Governance Decay / Slipstream | context compaction 是治理面：summary/checkpoint 必须证明保留 policy、goal、artifact dependency 和 active skill constraints。 |
| AgentFootprint / durable artifacts / provenance | checkpoint、trace、artifact、sandbox snapshot 的 storage footprint 是长期 runtime 的可测成本。 |
| Agent Skills Matter / SKIMIX | skill registry 既要避免 skill mixture dilution，也要防 execution trace 泄漏私有 skill 知识。 |

本轮已经落地的工程增量：

- `FootprintMeter`：度量 `RuntimeState`、`TraceEvent`、artifact refs、metadata、active skill manifest 和 trace envelope 的可持久化足迹。
- `FootprintReport`：给 nightly regression / replay / checkpoint budget 提供稳定报告对象。
- docs source correction：修正 AgentFootprint、durable intermediate artifacts、execution provenance 相关 source ID。

下一步推荐把 approval 从 token 升级成更强的对象：

```text
approval_token
  -> authority_witness
  -> permission_graph
  -> commit_time_receipt
  -> replayable proof bundle
```

同时，Hermes 的 checkpoint 应该从“保存状态”升级成：

```text
state snapshot
  + policy pins
  + artifact lineage
  + context compaction proof
  + footprint report
  + resume preflight verifier
```

这会让 `harness x hermes` 更接近真正的长期科研 runtime：不仅能继续跑，还能证明“继续跑”这件事本身是安全和可信的。

### 8.5 继续落地：PermissionGraph

本轮已把 authority graph 的第一版压成轻量代码原型：

- `PermissionGrant`：subject / effect / resource pattern / input label policy。
- `AuthorityWitness`：带 checkpoint version freshness 的授权证据。
- `PermissionGraph`：把 context label、grant、witness 统一成可 fingerprint 的治理图。
- `PermissionDecision`：输出 allowed、failures、counterexamples、receipt payload。

它对应的设计升级是：

```text
approved=True
  -> approval_token
  -> AuthorityWitness
  -> PermissionGraph decision
  -> commit-time receipt
```

当前它已经能表达两类 runtime 风险：

1. 数据流风险：读入 `untrusted` web / MCP / external data 后，不能直接写入报告或触发外部 effect；必须先形成 `sanitized` derivative。
2. 授权新鲜度风险：external / publish / irreversible action 不仅需要曾经审批过，还需要在当前 checkpoint version 下 witness 没有过期。

这和 Hermes 的关系也很直接：Hermes 后续不只保存 pending tool call，而要保存 permission graph snapshot、authority witness、context labels 和 commit-time decision receipt。

### 8.6 继续落地：Intervention Replay

`ReplayVerifier` 解决的是“同一条 trace 能不能精确复现”。但真实 runtime 还需要回答另一个问题：

> 如果某个 MCP/tool response 出现 timeout、stale data、poisoned description 或 schema drift，我们能否复现失败，并验证 mitigation 是否真的有效？

这就是 AgentCheck-style intervention replay 的位置。

本轮新增 `InterventionReplayWorkbench`，把 replay 拆成：

```text
baseline trace
  -> inject fault at tool boundary
  -> cached prefix
  -> divergent/live suffix
  -> mitigation trace
  -> prefix recovery report
```

当前原型覆盖：

- `InterventionSpec`：fault kind、target tool、target event、response overrides、metadata。
- `inject_fault()`：在匹配的 `tool_completed` event 上写入 fault 和 fingerprint。
- `compare()`：按 tool、args hash、output hash、trace envelope fingerprint 比较 tool trace。
- `evaluate()`：输出 cached prefix、live suffix、divergence reason 和 mitigation effectiveness。

这会把 `trace -> eval` 飞轮推进一层：

```text
trace
  -> exact replay
  -> intervention replay
  -> mitigation replay
  -> regression case
  -> skill / policy / adapter promotion gate
```

后续接真实 MCP adapter 时，可以把 server response snapshots、fault injector hash、service discovery trail 和 mitigation report 一起进 `TraceEnvelope` / eval dataset。

### 8.7 继续落地：Memory Commit

Hermes 负责长期状态，但长期状态里最危险的不是“保存失败”，而是“错误事实保存成功”。

因此 memory write 不能直接等价于 belief commit。本轮新增 `MemoryCommitProtocol`，把记忆写入拆成：

```text
stage
  -> validate
  -> commit
  -> safety gate
  -> cascade retract
```

当前原型覆盖：

- `MemoryRecord`：observation / belief / artifact / rule，带 source refs、parent records、status、validation receipts。
- `ValidationReceipt`：validator、pass/fail、reasons、evidence refs、checkpoint version。
- `MemoryTransaction`：把一组 memory writes 放入事务。
- `MemoryCommitReport`：记录 committed / rejected / failures。
- `MemorySafetyReport`：阻止未提交或已撤回记忆驱动后续 action。
- `cascade_retract()`：源事实被推翻时，递归撤回派生事实。

这让 Hermes memory 从：

```text
append memory
```

升级为：

```text
staged fact
  + evidence
  + validation receipt
  + commit decision
  + retraction lineage
```

和外部 memory 实现的关系也更清楚：LangGraph / Letta / Mem0 可以作为状态与长期记忆 provider，但本项目自己的 Harness 仍要保留 commit gate，避免 provider-native memory 直接污染科研 belief。

### 8.8 继续落地：Transition Graph

线性 trace 适合审计“发生了什么”，但不擅长回答“失败为什么发生、该修哪里”。因此本轮新增 `TransitionGraph`，把 state-changing `TraceEvent` 提升为可诊断图。

当前原型覆盖：

- `TransitionUnit`：从 tool / checkpoint / approval 等 state-changing event 中抽出 transition unit。
- `TransitionEdge`：记录 sequence / dependency relation。
- `TransitionGraph`：构建 roots、leaves、branch points、critical chain、critical subgraph。
- `TransitionGraphReport`：输出 target unit、target status、critical path fingerprints。
- `TransitionVerifier`：在 eval 层从 event stream 生成 transition diagnosis。

这让 failure attribution 从：

```text
tool_failed at event e4
```

升级为：

```text
paper_scan
  -> run_experiment
  -> publish_report failed

branch point:
  paper_scan -> parallel_review
```

和前几层模块的关系：

```text
TraceEnvelope
  -> ReplayVerifier
  -> InterventionReplayWorkbench
  -> TransitionGraph
  -> MemoryCommitProtocol / Skill promotion
```

也就是说，未来 replay 发现 drift 或 intervention replay 找到 divergent suffix 后，可以把 divergence 映射回 critical transition chain，再决定是更新 memory、policy、tool contract 还是 skill。

### 8.9 继续落地：Obligation Audit 与 Decision Memory Projection

`TransitionGraph` 能回答“失败链在哪里”，但多 agent runtime 还要回答两个问题：

1. 谁本该负责这个 transition？
2. 这次决策实际使用了哪些已提交记忆？

因此本轮新增两个轻量原型。

#### ObligationAuditMap

`ObligationAuditMap` 把 iCORE-style cooperation / obligation / audit map 压成可测试对象：

- `Obligation`：actor、description、required transition labels、status、candidate actor scores。
- `AuditLink`：obligation 到 transition unit 的 evidence-backed link。
- `ObligationAuditReport`：soundness、assignment stability、actor load、unsupported obligations。

它能发现：

- obligation 标记为 satisfied，但没有 transition evidence；
- 指派给了较弱 actor，而另一个 actor 明显更适合；
- obligation 仍 open 或 violated。

#### DecisionMemoryProjection

`MemoryCommitProtocol` 解决“记忆是否可以成为 belief”，但一次决策还需要记录“到底看了哪些 belief”。

`DecisionMemoryProjection` 采用 Stateless Decision Memory 的思路：

```text
append-only committed memory log
  -> task-conditioned projection
  -> decision memory view
  -> projection fingerprint
```

默认只从 committed records 里投影，支持按 kind、source refs 和 query terms 过滤。这样 replay 时不仅知道 memory store 里有什么，还知道某次决策实际被哪些记忆影响。

新的链路变成：

```text
TransitionGraph
  -> ObligationAuditMap
  -> MemoryCommitProtocol
  -> DecisionMemoryProjection
  -> replay/eval/skill promotion
```

### 8.4 最近更近的一组自优化论文

| 方向 | 代表材料 | 关键结论 | 对本项目的启发 |
|---|---|---|---|
| 状态外置训练 | *Harness-1* | 用 state-externalizing harness 训练搜索 agent，把候选池、证据链、verification record、context rendering 放到环境侧。 | 我们的 Hermes 也应该替 agent 承担可恢复状态，而不是把一切都喂给模型。 |
| 六维 harness 优化 | *MemoHarness* | harness 可以沿 context / tool / generation / orchestration / memory / output 六个控制面做结构化编辑。 | `policy` 和 `skill` 可以做成可组合的六维 artifact，而不是单个 prompt 文件。 |
| 自进化能力拆分 | *Harness Updating Is Not Harness Benefit* | harness-updating 和 harness-benefit 是两种不同能力，强模型不一定最会吃 harness 改动。 | self-evo 不要默认用最强模型做 evolver，要单独评估“更新能力”和“受益能力”。 |
| 评估方法反思 | *Rethinking the Evaluation of Harness Evolution for Agents* | harness evolution 的收益要和 test-time scaling 区分，还要做 held-out generalization。 | 我们未来的 eval 必须把 search budget 和 harness improvement budget 拆开算。 |

这组论文基本把一个判断钉死了：未来的 agent 优化，不是单点 prompt tuning，而是对 harness 的分层编辑、证据外置、再评估。

### 8.5 Continuation: 失败轨迹诊断和 durable runtime profile

最新一轮材料又把方向往前推了一点：runtime 不只要能 replay，还要能解释“为什么 replay 漂移”。

| 方向 | 新信号 | 对本项目的吸收 |
|---|---|---|
| HarnessFix / HTIR | 从 failed trajectory 抽取 harness flaw，并把诊断、修复和评估接成闭环。 | 新增 `HarnessDiagnosticWorkbench`：把 replay divergence 映射到 transition unit、trace envelope drift、suspect surface 和 repair hint。 |
| MCPEvol-Bench | MCP server/tool 会演化，tool discovery 和 schema drift 会影响 agent。 | `ToolDescriptionContract` 后续要记录 schema version lineage 和 discovery trail。 |
| Agentic Context Management | context 管理成为 agent 与模型之间的中间层，负责压缩、选择、结构化和 drift 检查。 | 已新增 `CompactionVerifier` 作为 resume gate；后续接 `planning_or_context_rendering` 诊断面。 |
| Governance Decay | compaction 可能静默擦除安全约束。 | `CompactionVerifier` 已落地为 resume gate，检查 policy pins、goal、process stage、artifact lineage、approval boundary。 |
| SmoothAgent | lookahead context engineering 也是 runtime 与 serving 成本的一部分。 | context transformation 后续应纳入 footprint / compaction budget。 |
| Syll | 自然语言任务可以编译为 runtime constraints，并在执行中持续监控。 | `ActionPathPolicy` / `PermissionGraph` 后续可成为 NL policy 的编译目标。 |
| Always-On Agents | 长期 agent 需要 process lifecycle、autonomy、privacy 和 interruptibility。 | 已新增 `RuntimeState.process_stage` 与 `ProcessLifecycleVerifier`；后续升级成 typed `ResearchSession`。 |
| AWS / Microsoft / Pydantic / Mistral durable runtime | 官方实现都在把 runtime、memory、approval、workflow、observability/eval 做成显式 surface。 | `ProviderProfile` 已扩展这些 runtime profile，checkpoint 后续可记录外部 runtime capability snapshot。 |
| Cloudflare / Vercel / Mastra runtime | Durable Objects、WorkflowAgent、suspend/resume、approval、background tasks 把“持久执行”做成框架原语。 | 新增 `cloudflare-agents`、`vercel-workflow-agent`、`mastra-durable-agents` profile。 |

这一轮的代码落点：

- `src/vibe_research/harness_diagnostics.py`
- `HarnessDiagnosticWorkbench`
- `HarnessDiagnosisReport`
- `provider_profiles.py` 新增 AWS/Microsoft/Pydantic/Mistral runtime implementation profile
- `compaction.py`
- `CompactionVerifier`
- `process_lifecycle.py`
- `ProcessLifecycleVerifier`
- `RuntimeState.process_stage`
- `research_session.py`
- `ResearchSession`
- `ResearchSessionVerifier`
- `provider_profiles.py` 新增 Cloudflare/Vercel/Mastra runtime profile
- `scripts/verify_runtime.py` 新增 diagnosis smoke metrics
- `scripts/verify_runtime.py` 新增 research session smoke metrics
- 测试从 30 个增加到 39 个

新的诊断链路：

```text
InterventionReplayWorkbench
  -> first divergent tool boundary
  -> HarnessDiagnosticWorkbench
  -> TransitionGraph critical chain
  -> TraceEnvelope fingerprint drift
  -> repair hint / eval case / skill gate
```

### 8.6 Continuation: ResearchSession

Process lifecycle 解决“agent task 是不是还活着、状态能不能审计”，但科研 runtime 还需要一个更业务化的对象：typed research session。

最新研究型 agent 实现共同指向这个结构：

```text
research goal
  -> paper scan
  -> hypothesis
  -> experiment plan
  -> experiment run
  -> analysis
  -> review
  -> writeup
  -> archive
```

本轮新增：

- `ResearchPhase`
- `ResearchPhaseGate`
- `ResearchSession`
- `ResearchSessionVerifier`
- `ResearchSessionReport`
- `research_session_from_state()`

它的意义是把科研任务从：

```text
goal string + tool calls
```

升级成：

```text
typed phase topology + artifact/evidence/review gate
```

例如 `writeup` 阶段可以要求：

- paper shortlist artifact；
- hypothesis artifact；
- metric artifact；
- analysis report；
- `paper_scan / run_experiment / peer_review` transitions；
- committed memory record；
- validation receipt；
- review ref。

这会让 `vibe-research` 的主链路变成：

```text
Hermes RuntimeState
  -> ProcessLifecycleVerifier
  -> ResearchSession
  -> ResearchPhaseGate
  -> MemoryCommitProtocol / ObligationAuditMap / TransitionGraph
  -> writeup / archive promotion
```

## 9. 资料来源

- OpenAI Agents SDK: https://developers.openai.com/api/docs/guides/agents
- OpenAI Agents SDK docs: https://openai.github.io/openai-agents-python/
- OpenAI Agents guardrails: https://openai.github.io/openai-agents-python/guardrails/
- OpenAI Agents tracing: https://openai.github.io/openai-agents-python/tracing/
- OpenAI Responses tools: https://developers.openai.com/api/docs/guides/tools
- OpenAI tool search: https://developers.openai.com/api/docs/guides/tools-tool-search
- OpenAI programmatic tool calling: https://developers.openai.com/api/docs/guides/tools-programmatic-tool-calling
- OpenAI function calling: https://developers.openai.com/api/docs/guides/function-calling
- OpenAI connectors and MCP: https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- OpenAI sandbox agents: https://developers.openai.com/api/docs/guides/agents/sandboxes
- OpenAI Evals: https://developers.openai.com/api/docs/guides/evals
- OpenAI skills: https://developers.openai.com/api/docs/guides/tools-skills
- OpenAI latest model/model guidance: https://developers.openai.com/api/docs/guides/latest-model
- DeepSeek Codex integration: https://api-docs.deepseek.com/quick_start/agent_integrations/codex/
- DeepSeek OpenCode: https://api-docs.deepseek.com/quick_start/agent_integrations/opencode/
- DeepSeek OpenClaw: https://api-docs.deepseek.com/quick_start/agent_integrations/openclaw/
- DeepSeek Hermes: https://api-docs.deepseek.com/quick_start/agent_integrations/hermes/
- DeepSeek Reasonix: https://api-docs.deepseek.com/quick_start/agent_integrations/reasonix/
- DeepSeek GitHub Copilot: https://api-docs.deepseek.com/quick_start/agent_integrations/github_copilot/
- DeepSeek Pi: https://api-docs.deepseek.com/quick_start/agent_integrations/pi/
- DeepSeek API docs: https://api-docs.deepseek.com/
- Harness-Bench: https://arxiv.org/abs/2605.27922
- Code as Agent Harness: https://arxiv.org/abs/2605.18747
- Harness-1: https://arxiv.org/abs/2606.02373
- MemoHarness: https://arxiv.org/abs/2607.14159
- Harness Updating Is Not Harness Benefit: https://arxiv.org/abs/2605.30621
- Rethinking the Evaluation of Harness Evolution for Agents: https://arxiv.org/abs/2607.12227
- Harness survey: https://arxiv.org/abs/2606.20683
- Harnesses reshape search: https://arxiv.org/abs/2605.15184
- Natural-Language Agent Harnesses: https://arxiv.org/abs/2603.25723
- Proof-Carrying Agent Actions: https://arxiv.org/abs/2606.04104
- Terminal-Bench 2.0: https://arxiv.org/abs/2601.11868
- Long-Horizon-Terminal-Bench: https://arxiv.org/abs/2607.08964
- MCPAgentBench: https://arxiv.org/abs/2512.24565
- SEAGym: https://arxiv.org/abs/2606.17546
- OpenHands SDK docs: https://docs.openhands.dev/sdk
- OpenHands introduction: https://docs.openhands.dev/overview/introduction
- OpenHands Agent Server: https://docs.openhands.dev/sdk/arch/agent-server
- OpenHands persistence / skills: https://docs.openhands.dev/sdk/guides/skill
- Pi harness: https://pi.dev/
- OpenClaw repo: https://github.com/openclaw/openclaw
- OpenClaw release feed: https://github.com/openclaw/openclaw/releases
- HarnessFix: https://arxiv.org/abs/2606.06324
- MCPEvol-Bench: https://arxiv.org/abs/2607.14642
- Agentic Context Management: https://arxiv.org/abs/2607.21503
- ACM: Agentic Context Management for Long Horizon Tasks: https://arxiv.org/abs/2607.23809
- SmoothAgent: https://arxiv.org/abs/2607.00151
- Filesystem-Based Memory for LLM Agents: https://arxiv.org/abs/2607.26637
- From Prompts to Contracts: Harness Engineering for Auditable Enterprise LLM Agents: https://arxiv.org/abs/2607.08028
- Syll: https://arxiv.org/abs/2606.07594
- Harness-G: https://arxiv.org/abs/2607.27652
- Always-On Agents: https://arxiv.org/abs/2606.30306
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
