# Research Log 2026-08-02

> 目的：把本轮“最新论文 + 最新实现”核验结果压缩成可执行的 `harness x hermes` 设计增量。只记录已经找到原始页面或官方文档的材料。

## 1. 本轮结论

### 1.1 Harness 正在从 tool permission 走向 authority graph

新的治理论文不再满足于“某个 tool 是否允许执行”，而是在建模：

- 数据读入后是否污染上下文；
- 什么时候需要 fork branch；
- approval 是否仍然新鲜；
- effect commit 前 authority witness 是否仍然有效；
- 自然语言任务如何降成可检查的 permission graph。

对 `vibe-research` 的含义：

```text
ToolCall allow/deny
  -> ActionPathPolicy
  -> PermissionGraph
  -> CommitTimeVerifier
```

也就是说，未来 Harness 的主对象不应只是 `HarnessPolicy`，而应包括 `permission label`、`branch token`、`authority witness`、`commit boundary` 和 `counterexample`。

### 1.2 Hermes 的风险不只是“丢状态”，还包括 context compaction governance decay

长期任务一定会压缩上下文或状态摘要。新材料指出，compaction 可能悄悄丢掉 standing instructions、safety policy、memory rule 或 artifact dependency。

对 `vibe-research` 的含义：

- `policy_snapshot` 必须是 pinned object，不应只藏在 prompt/summary 里；
- resume 前要检查 summary 是否保留关键约束；
- checkpoint diff 不只比较 bytes，还要比较 policy/goal/artifact lineage；
- replay failure 可以归因为 compaction drift。

### 1.3 Footprint 已经是 runtime 评估面

AgentFootprint、durable intermediate artifacts、execution provenance 这条线都说明：长期 agent runtime 的成本不只是 token 和美元，还包括 checkpoint、trace、artifact、sandbox snapshot、memory graph 的增长速度。

本轮已落地：

- 新增 `FootprintMeter`
- 新增 `FootprintReport`
- 单测覆盖 state/events/artifacts/metadata/skill manifest/trace envelope footprint

下一步建议：

- 把 footprint report 写入 checkpoint metadata；
- 做 `footprint_budget`，避免 run 产生无法长期 replay 的状态膨胀；
- 在 nightly regression 里比较 footprint delta。

### 1.4 MCP 安全正在转向 lifecycle evidence

MCP 相关论文和规范共同指向一个结论：只看 tool schema 或 description 不够。真实风险发生在整个生命周期：

```text
discovery -> schema/description -> invocation -> process/file/network side effects -> output -> downstream action
```

对 `vibe-research` 的含义：

- `ToolDescriptionContract` 是必要起点，但不够；
- MCP adapter 应记录静态 risk summary；
- sandbox wrapper 应记录动态 effect signals；
- `TraceEnvelope` 后续应支持 `mcp_lifecycle_evidence_ref`。

### 1.5 Skill 要同时防 dilution 和 leakage

最新 skill 方向出现两个相反但都重要的问题：

- skill mixture 能提升能力，但不是越多越好，存在 dilution；
- skill 可能通过执行轨迹泄漏其隐藏程序性知识。

对 `vibe-research` 的含义：

- `SkillManifest` 需要 routing budget 和 anti-dilution gate；
- trace export 要分 public/private 视图；
- skill promotion 不只看成功率，还要看泄漏风险和 footprint 成本。

## 2. 本轮工程落点

| 改动 | 状态 | 原因 |
|---|---|---|
| `src/vibe_research/footprint.py` | 已新增 | 开始把 checkpoint/state/trace/artifact 成本变成可测指标。 |
| `FootprintMeter` export | 已新增 | 让 runtime / eval / scripts 后续能统一调用。 |
| footprint unit tests | 已新增 | 防止未来 state schema 改动时 footprint 静默失真。 |
| watchlist source correction | 已更新 | 修正 AgentFootprint / durable artifacts / evidence provenance 的 source ID。 |
| implementation matrix | 已更新 | 把 APPA/FAVA/MTGuard/Commit-Time Authorization/compaction/skill leakage 压成工程任务。 |

## 3. 下一轮建议任务

1. `PermissionGraph`
   - 输入：natural-language goal、policy snapshot、tool contract、skill manifest。
   - 输出：allowed data-flow / allowed effects / counterexample。

2. `CommitTimeVerifier`
   - 输入：pending durable action、approval receipt、artifact versions、branch label。
   - 输出：commit allowed/blocked + proof receipt。

3. `CompactionVerifier`
   - 输入：old state、compacted state、required pins。
   - 输出：goal/policy/artifact/skill retention report。

4. `McpLifecycleEvidence`
   - 输入：MCP schema、tool call、sandbox/process/network/file observations。
   - 输出：static + dynamic risk digest。

5. `SkillTraceView`
   - 输出 public audit trace 和 private replay trace 两种视图，降低 skill leakage 风险。

## 4. Source corrections

本轮修正了之前 watchlist/matrix 中几个来源 ID：

- AgentFootprint：改为 `2607.11149`
- A Data Model for Durable Intermediate Artifacts：改为 `2605.12087`
- Evidence Tracing and Execution Provenance：改为 `2606.04990`

## 4.1 Continuation pass: FSE-facing evidence-retaining replay

继续对标 FSE 2027 后，一个更清晰的判断是：`TraceEnvelope` 不能只证明 action / provider / policy 没漂移，还要证明 action 当时依赖的 evidence scene 没漂移。

这和 FSE 近几年的方向对得上：

- Agent trajectory reduction 说明成本和长轨迹冗余已经是 A 会问题。
- Agent execution boundary / privilege usage 说明权限和真实工具 effect 已经是 A 会问题。
- Replayable A2A event stream 说明 session-level replay 已经进入软件工程系统视角。
- AgentReputation / Event-B Agent / IDE HAX SLR 进一步说明 verification metadata、feedback repair loop、human verification overhead 都是近期 FSE 接受的 agentic SE 切口。

本轮工程吸收：

```text
EvidenceLedger
  -> RuntimeState.metadata.active_evidence_ledger
  -> TraceEnvelope.evidence_ledger_fingerprint
  -> TraceEnvelope.evidence_claim_ids
  -> evidence_ledger ProofReceipt
  -> ReplayVerifier evidence drift check
```

这把创新点 2（Evidence-Governed Memory Commit）和创新点 3（Replayable Failure Diagnosis）接在一起。论文里可以把它叫做：

```text
evidence-retaining replay
```

后续实验可以新增两个指标：

- evidence-receipt drift detection rate
- claim-preserving replay fidelity

## 4.2 Continuation pass: FSE benchmark scaffold

为了把 FSE 对标从“叙事上像”推进到“实验上真的能跑”，本轮新增了一个结构化 benchmark scaffold：

```text
FseBenchmarkPlan
  -> 3 task families
  -> 6 concrete task specs
  -> 5 baselines
  -> 16 fault scenarios
  -> 7 ablations
  -> 23 metrics
  -> 4 RQs
  -> 8 related-work clusters
  -> SyntheticFseBenchmarkRunner
  -> 152 planned experiment cells
  -> SyntheticFseTraceRunner
  -> deterministic replay / diagnosis / evidence-drift results
  -> FseLocalToyTaskRunner
  -> real local toy artifacts + hydration/evidence/memory checks
```

这一步的意义很简单：FSE 论文不能只讲 runtime model，还得讲它怎么在真实 SE 任务上被审稿人检查。这个 scaffold 让后续实验能直接挂在：

- issue-to-patch / repo maintenance
- artifact replication
- incident RCA

三个 task family 上，同时把三条创新点分别对齐到：

- RQ1: scene-based hydration
- RQ2: governed memory/evidence commit
- RQ3: evidence-retaining replay
- RQ4: practical cost

也就是说，后面的 runner、fault injector、ablation runner 都可以直接沿这份 plan 长出来，而不必重新发明实验结构。

本轮已新增：

- `src/vibe_research/fse_benchmark_runner.py`
- `FseBenchmarkExperimentCell`
- `FseBenchmarkMatrix`
- `SyntheticFseBenchmarkRunner`
- `SyntheticFseTraceRunner`
- `FseLocalToyTaskRunner`
- `scripts/verify_fse_benchmark.py` 的 matrix readiness 输出

当前 smoke 输出显示：

- processed synthetic trace cells: 152
- fault detected cells: 122
- evidence drift detected cells: 70
- replay-passed cells: 30
- local toy task success count: 3 / 3
- local toy artifact count: 10
- local toy evidence claim count: 5
- local toy committed memory count: 3
- failures: 0

## 4.3 Continuation pass: local toy artifact runner

为了让 FSE artifact evaluation 方向更有抓手，本轮新增 `FseLocalToyTaskRunner`。它不是模型评测，而是本地 artifact smoke：

```text
temporary workspace
  -> issue-to-patch toy repo
  -> artifact replication toy package
  -> incident RCA toy logs/report
  -> EvidenceLedger
  -> MemoryCommitProtocol
  -> ResearchSessionGate
  -> HydrationManifest
```

这一步证明了三个核心 claim 可以在真实文件上跑通：

- Hydratable scene：真实 artifact refs 能进入 HydrationManifest，并通过 verify。
- Evidence-governed memory：每个 local task 都有 evidence-backed claims 和 committed memory。
- Replayable diagnosis 的前置条件：每个 local task 都生成 trace events 和 trace envelope refs。

后续可以把 toy task 替换成小型真实任务，而不用重写评测骨架。

## 4.4 Continuation pass: artifact-package smoke CLI

为了让 FSE submission 不只停在 benchmark scaffold，本轮新增 `scripts/run_fse_local_benchmark.py`，把当前实验骨架打包成一个可复现的 artifact smoke：

```text
output_dir
  -> reports/benchmark_plan.json
  -> reports/benchmark_readiness.json
  -> reports/benchmark_matrix.json
  -> reports/benchmark_matrix_report.json
  -> reports/synthetic_trace_report.json
  -> reports/local_run_report.json
  -> reports/swebench_adapter_report.json
  -> reports/swebench_executor_report.json
  -> reports/artifact_manifest.json
  -> reports/summary.json
  -> local_artifacts/
  -> swebench_adapter/
  -> swebench_executor/
```

这一步对 FSE artifact evaluation 很关键：reviewer 需要的不只是“我们设计了实验”，而是能下载、运行、看到可检查输出。当前 CLI 已支持限制 synthetic cells 做快速 smoke，也支持完整 140-cell synthetic matrix；新增 `tests/test_fse_artifact_cli.py` 会真实调用 CLI，检查 generated reports、artifact manifest、local workspace、SWE-bench adapter workspace、SWE-bench executor workspace、artifact refs、hydration safe 和 phase gate。

下一步工程目标变成：

- 把 demo SWE-bench-style adapter/executor 接到真实 SWE-bench Verified / SWE-bench Pro small subset checkout 和 Docker harness；
- 把 toy artifact replication task 替换成真实论文 artifact package adapter；
- 把 toy incident RCA task 替换成 synthetic/real incident trace adapter；
- 把 artifact manifest 升级成匿名审稿版 replication package index。

## 4.5 Continuation pass: SWE-bench-style small subset adapter

本轮把 `issue_to_patch` 的真实 benchmark 接口向前推进了一步：新增 `src/vibe_research/swebench_adapter.py`。

它现在不是完整 Docker SWE-bench executor，而是一个 FSE artifact/evidence adapter：

```text
SWE-bench-style JSONL / demo subset
  -> problem_statement.md
  -> gold.patch
  -> candidate.patch
  -> test.patch
  -> patch_correctness_report.json
  -> EvidenceLedger
  -> MemoryCommitProtocol
  -> ResearchSessionGate
  -> HydrationManifest
```

为什么这一步重要：SWE-bench Verified 可以做 issue-to-patch 任务来源，但最近 SWE-bench correctness critique 已经说明，单纯 test-pass rate 不够。adapter 因此额外记录：

- candidate patch 是否等于 gold patch；
- changed-file overlap；
- patch-line Jaccard；
- behavioral divergence proxy；
- test patch 是否存在；
- evidence ledger / hydration / phase gate 是否通过。

当前 `scripts/run_fse_local_benchmark.py` 会默认跑一个两实例 SWE-bench-style demo subset，并在 `reports/swebench_adapter_report.json` 中输出：

- `ready_for_swebench_adapter`
- `swebench_instance_count`
- `swebench_success_count`
- `swebench_candidate_patch_equal_count`
- `swebench_mean_patch_line_jaccard`
- `swebench_mean_behavioral_divergence_score`

后续接真实 SWE-bench Verified small subset 时，只需要传入 JSONL 或替换 executor 层，不需要重写 evidence/hydration/reporting contract。

## 4.6 Continuation pass: SWE-bench-style local patch executor

本轮继续把 `issue_to_patch` 从“patch/evidence adapter”推进到“可执行本地 patch harness”：新增 `SweBenchLocalPatchExecutor`。

它仍然不是官方 Docker SWE-bench harness，但已经跑通了最小真实执行链：

```text
local repo
  -> copy workspace
  -> git apply test.patch
  -> git apply candidate.patch
  -> run test_command
  -> stdout / stderr / execution_report
  -> EvidenceLedger
  -> MemoryCommitProtocol
  -> ResearchSessionGate
  -> HydrationManifest
```

当前默认 demo 有两个 instance：

- `executor__calculator-001`：candidate patch 等于 gold patch，测试通过。
- `executor__parser-002`：candidate patch 与 gold patch 不同，测试失败，但 runner 成功捕获执行证据。

这一步的设计重点是把两类结果分开：

- `success_count` 表示执行链成功，不表示 patch 正确；
- `tests_passed_count` 表示 candidate patch 是否通过 regression tests。

当前 smoke 输出：

- `ready_for_swebench_executor`: true
- executor instances: 2
- executor success: 2 / 2
- executor tests passed: 1 / 2
- executor hydration safe: 2 / 2
- executor evidence sound: 2 / 2
- executor candidate patch equal to gold: 1 / 2

这让后续接真实 SWE-bench Verified small subset 时，可以把官方 Docker executor 或轻量 repo executor 替换到同一 reporting contract 上。

## 4.7 Continuation pass: FSE / CCF / SWE-bench 外部校准

本轮重新核对了 FSE 2027 Research Track、CCF 2026 推荐目录、SWE-bench family 和近两年 FSE agent 论文，得到一个更硬的投稿判断：

```text
FSE 可投，但必须按 empirical software engineering paper 写，
不能按 agent framework demo 写。
```

外部信号：

- FSE 2027 Research Track 明确欢迎 theoretical / empirical / conceptual / experimental SE research，鼓励 reproducibility、replication package、available datasets 和 tools。
- FSE 2027 evaluation basis 包括 originality、importance、soundness、evaluation、presentation 和 related-work comparison。
- FSE 2027 topics 中与本项目强相关的包括 AI/ML for SE、debugging and fault localization、dependability/safety/reliability、empirical SE、program comprehension、program repair、software engineering for ML/AI、software security、software testing、software traceability、tools and environments。
- CCF 2026 目录中，FSE、ASE、ICSE、ISSTA 均位于“软件工程/系统软件/程序设计语言”A 类会议；这支持继续把 FSE 作为主目标，同时保留 ASE/ICSE/ISSTA 作为相邻备选。
- SWE-bench Verified 仍适合做 issue-to-patch 基础子集，但 SWE-Bench Pro 和 ICSE 2026 对 SWE-bench correctness 的批评说明：只用 pass/fail tests 不够，必须加入 patch correctness、behavioral divergence、evidence/replay 和 human inspection/secondary tests。
- FSE 2025 Agentless、FSE 2026 AgentDiet、AgentBound、privilege usage、RocketMQ-A2A 和 FSE 2024 RCA agents 共同说明，FSE 已经接受 software agents，但 reviewer 会追问：成本、权限边界、replay、真实工具、failure diagnosis 和 empirical rigor。

对当前设计的直接行动：

1. `Artifact-Package Smoke CLI` 要继续升级成匿名 review replication package。
2. `issue_to_patch` 不能只报告 SWE-bench pass rate，要加 differential / behavioral checks，至少记录 patch-vs-ground-truth divergence。
3. `artifact_replication` 要有真实 paper artifact package，不然创新点 1/2 会显得像 synthetic-only。
4. `incident_rca` 是非常好的第三 task family，因为 FSE 已有 RCA agent paper，且它天然需要动态证据收集、evidence ledger 和 replay diagnosis。
5. Related work 需要正面对标 Agentless / AgentDiet / AgentBound / SWE-bench Pro / PatchDiff-style benchmark critique，而不是只写 LangGraph/OpenHands。

## 4.8 Continuation pass: runtime enforcement / trace failure / memory interference

本轮继续追了几篇更贴近 runtime、trace 和 memory 的新材料。它们共同把三条创新点又压实了一层：

| 新材料 | 关键信号 | 对本项目的实验影响 |
|---|---|---|
| AgentSpec | LLM agent 需要 customizable runtime enforcement，而不是只靠 prompt 或事后审计。 | RQ1 的 hydration preflight 要明确比较 “checkpoint-only” 与 “runtime-enforced scene” 的恢复正确性。 |
| EAGER | multi-agent failure management 可以利用 reasoning trace representation 和历史失败模式。 | RQ3 不应只看 raw logs，要比较 trace representation / transition graph 是否提升 localization。 |
| FAMAS | FSE 2026 已经把 multi-agent 轨迹 replay、abstraction 和 spectrum-based failure attribution 当成 SE 问题。 | `TransitionGraph + HarnessDiagnosticWorkbench` 的定位指标应写成 fault attribution，而不是普通日志分析。 |
| Externalization in LLM Agents | memory、tool、skill、workflow 正在外置成可管理 runtime surfaces。 | 创新点 1 的 hydratable scene 需要强调 externalized runtime surfaces，而不是 transcript 压缩。 |
| FORGET-SE | 软件工程知识追踪中存在 memory decay / interference，且需要可控数据集分析。 | RQ2 要加入 memory interference / stale belief 场景，而不只是 “wrong memory commit”。 |
| Not All RAGs Are Created Equal | RAG 在 SE 任务中要做 component-wise 分析，不同检索/生成组件影响明显。 | evidence ledger 前面的 retrieval/evidence intake 不能只押 dense retrieval；实验要保留 lexical/structured retrieval baseline。 |
| Harness Engineering for Auditable Enterprise LLM Agents | harness 可以从 prompt contract 升级成 audit-ready enterprise runtime。 | 论文定位应坚持 “auditable runtime support”，不要退回 “agent app framework”。 |

折回到三条创新点后，当前最稳的表述是：

1. **Hydratable Scene**：把 externalized runtime surfaces 作为恢复对象，恢复前执行 runtime enforcement / preflight。
2. **Evidence-Governed Memory Commit**：把 memory decay、interference 和 unsupported retrieval evidence 纳入 memory commit / claim gate。
3. **Evidence-Retaining Replay Diagnosis**：把 trace envelope 提升成 failure attribution substrate，对标 EAGER/FAMAS，而不是只做 replay log。

对 benchmark 的直接修改：

- `FseBenchmarkPlan` 的 related-work cluster 已加入 AgentSpec、EAGER、FAMAS、Externalization、FORGET-SE 和 RAG component-wise study。
- fault taxonomy 已从 10 类扩展到 12 类，新增 `memory_interference` 和 `retrieval_component_shift`。
- metric set 已从 15 个扩展到 17 个，新增 `memory_interference_block_rate` 和 `retrieval_evidence_stability`。
- 上一轮 synthetic matrix 已从 102 cells 扩展到 120 cells，其中 main cells 72、ablation cells 48。
- 当前 deterministic trace smoke：fault detected 102、evidence drift detected 44、replay-passed 18。

## 4.9 Continuation pass: context management and benchmark validity

这轮继续追最新 SE-agent benchmark / runtime 材料后，新增两个 FSE reviewer 很可能会问的问题：

1. 长任务 agent 的 context management 不是普通压缩问题。Agentic context management、MemAct、AgentProg 等方向都在把 context selection / editing / offloading 作为可优化 runtime 面；如果 active frame 或 policy/evidence/artifact pin 被丢掉，checkpoint 看起来完整但 hydration 其实不安全。
2. SWE-bench 系实验不能只报 pass rate。SWE-bench Verified / SWE-bench Pro / SWE-Lancer 以及 SWE-bench correctness critique 都在逼近同一个要求：task oracle、gold patch、test patch、execution environment 和 contamination/provenance audit 要能被 artifact package 复核。

本轮工程吸收：

```text
FaultKind.CONTEXT_MANAGER_DROPPED_PIN
FaultKind.BENCHMARK_ORACLE_DRIFT

context_pin_recall
artifact_provenance_completeness
benchmark_oracle_provenance_rate
oracle_audit_report.json
```

当前 benchmark matrix 从 120 cells 扩展到 152 cells：

- main cells: 104
- ablation cells: 48
- fault scenarios: 16
- metrics: 23
- related-work clusters: 8
- synthetic fault detected: 122
- evidence drift detected: 70
- replay-passed: 30

对论文结构的影响：

- RQ1 现在能测 context manager 是否保留 hydration pins，而不只测 interruption resume。
- RQ3 现在能把 artifact/oracle provenance 纳入 evidence-retaining replay。
- RQ4 现在不只是 cost overhead，还包括为了通过 FSE artifact/reproducibility 标准所需的 provenance cost。

## 4.10 Continuation pass: official SWE-bench subset bridge

上一轮的 `oracle_audit_report.json` 解决了“我们如何证明 task oracle / patch / test / environment 没漂移”的问题，但离真实 SWE-bench Verified / Pro 还有一步：官方 harness 需要一个 predictions JSONL 和明确的 evaluation command。直接把 Docker execution 硬塞进 smoke CLI 风险太高，所以这轮新增一个前置桥：

```text
SweBenchOfficialSubsetBridge
  -> official-style instances JSONL
  -> predictions JSONL
  -> official_harness_command.txt
  -> official_subset_manifest.json
  -> per-instance oracle_audit_report.json
```

它不会执行 Docker；它的作用是把真实实验前置条件变成可审稿 artifact：

- 每个 instance 是否有 `repo / base_commit / problem_statement / patch / test_patch / FAIL_TO_PASS`；
- 每个 instance 是否匹配到 `instance_id / model_name_or_path / model_patch` prediction；
- 每个 instance 的 oracle fingerprint 是否 sound；
- 是否具备本地 executor 所需的 `local_repo_path / test_command`；
- 之后要跑的官方命令是否固定，例如 `python -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Verified --predictions_path ...`。

本轮工程吸收：

- 新增 `SweBenchPrediction`；
- 新增 `SweBenchOfficialSubsetBridge`；
- 新增 `SweBenchOfficialSubsetReport`；
- `scripts/run_fse_local_benchmark.py` 现在额外输出 `reports/swebench_official_subset_report.json`；
- `scripts/verify_fse_benchmark.py` 现在报告 `ready_for_swebench_official_subset` 和 official subset oracle/harness readiness；
- tests 覆盖 JSONL + predictions manifest，以及 missing prediction 阻断。

当前 smoke：

- official subset instances: 2
- matched predictions: 2
- oracle-audit sound: 2
- official-harness ready: 2
- local-executor ready: 0（预期如此，因为 demo official subset 只生成官方 harness 前置 manifest，不绑定本地 checkout）

这一步让下一轮可以安全接真实 SWE-bench Verified / Pro small subset checkout 或 Docker harness，而不需要重写 reporting contract。

## 5. Sources

### Official specs and implementations

- OpenAI Agents guide: https://developers.openai.com/api/docs/guides/agents
- OpenAI guardrails and human review: https://developers.openai.com/api/docs/guides/agents/guardrails-approvals
- OpenAI tracing and observability: https://developers.openai.com/api/docs/guides/agents/integrations-observability
- OpenAI Sandbox Agents: https://developers.openai.com/api/docs/guides/agents/sandboxes
- MCP 2026-07-28 release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP 2026-07-28 changelog: https://modelcontextprotocol.io/specification/2026-07-28/changelog
- A2A protocol: https://a2a-protocol.org/latest/
- AG-UI: https://docs.ag-ui.com/introduction
- OpenTelemetry GenAI observability: https://opentelemetry.io/blog/2026/genai-observability/
- Claude Agent SDK overview: https://code.claude.com/docs/en/agent-sdk/overview
- Claude Agent SDK permissions: https://code.claude.com/docs/en/agent-sdk/permissions
- Claude Agent SDK hooks: https://code.claude.com/docs/en/agent-sdk/hooks
- Google ADK 2.0: https://adk.dev/2.0/
- Google ADK in Gemini Enterprise Agent Platform: https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk
- Temporal LangGraph plugin: https://temporal.io/blog/temporal-langgraph-plugin-durable-execution
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- Letta archival memory: https://docs.letta.com/v1-sdk/memory/archival-memory
- Letta memory blocks: https://docs.letta.com/v1-sdk/memory/memory-blocks
- Mem0 introduction: https://docs.mem0.ai/introduction
- DeepSeek coding agents: https://api-docs.deepseek.com/guides/coding_agents/
- DeepSeek Hermes integration: https://api-docs.deepseek.com/quick_start/agent_integrations/hermes/
- OpenHands SDK: https://docs.openhands.dev/sdk
- OpenHands conversation persistence: https://docs.openhands.dev/sdk/guides/convo-persistence

### Papers

- FSE 2027 Research Track CFP: https://conf.researchr.org/track/fse-2027/fse-2027-papers
- CCF 2026 recommended conference directory: https://ccf.atom.im/
- FSE 2026 AgentDiet: https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/137/Reducing-Cost-of-LLM-Agents-with-Trajectory-Reduction
- FSE 2026 AgentBound: https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/14/AgentBound-Securing-Execution-Boundaries-of-AI-Agents
- FSE 2026 privilege usage: https://conf.researchr.org/details/fse-2026/fse-2026-ideas-papers/15/Evaluating-Privilege-Usage-of-Agents-on-Real-World-Tools
- FSE 2026 RocketMQ-A2A: https://conf.researchr.org/details/fse-2026/fse-2026-industry-papers/29/RocketMQ-A2A-Reliable-Session-Level-Replayable-Event-Streams-for-Large-Scale-Multi-Age
- AgentReputation: https://arxiv.org/abs/2605.00073
- Event-B Agent: https://arxiv.org/abs/2605.17475
- Human-AI experience in IDEs SLR: https://arxiv.org/abs/2503.06195
- AgentFootprint: https://arxiv.org/abs/2607.11149
- A Data Model for Durable Intermediate Artifacts: https://arxiv.org/abs/2605.12087
- Evidence Tracing and Execution Provenance: https://arxiv.org/abs/2606.04990
- SWE-bench: https://www.swebench.com/
- SWE-bench Verified: https://www.swebench.com/swebench-verified.html
- SWE-bench Pro: https://www.swebench.com/swebench-pro.html
- SWE-bench evaluation guide: https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/evaluation.md
- OpenAI SWE-bench Verified: https://openai.com/index/introducing-swe-bench-verified/
- SWE-bench Pro public leaderboard: https://labs.scale.com/leaderboard/swe_bench_pro_public
- SWE-bench repository / harness: https://github.com/swe-bench/SWE-bench
- ICSE 2026 SWE-bench correctness critique: https://software-lab.org/publications/icse2026_SWE-bench-correctness.pdf
- mini-SWE-agent: https://github.com/SWE-agent/mini-swe-agent
- AgentSpec: https://arxiv.org/abs/2503.18666
- EAGER: https://arxiv.org/abs/2603.21522
- Externalization in LLM Agents: https://arxiv.org/abs/2604.08224
- FORGET-SE: https://arxiv.org/abs/2605.14503
- FORGET-SE repository: https://github.com/alyssa-sha/FORGET-SE
- FSE 2026 FAMAS: https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/205/Spectrum-based-Failure-Attribution-for-Multi-Agent-Systems
- FSE 2026 Not All RAGs Are Created Equal: https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/159/Not-All-RAGs-Are-Created-Equal-A-Component-Wise-Empirical-Study-for-Software-Enginee
- Agentic Context Management for Long-Horizon Tasks: https://arxiv.org/abs/2607.23809
- TrajAudit: https://arxiv.org/abs/2605.26563
- Trajectory Structure Diagnostics for Coding Agents: https://arxiv.org/abs/2607.06184
- MemAct: https://arxiv.org/abs/2510.12635
- AgentProg: https://arxiv.org/abs/2512.10371
- Filesystem-Based Memory for LLM Agents: https://arxiv.org/abs/2607.26637
- From Prompts to Contracts: Harness Engineering for Auditable Enterprise LLM Agents: https://arxiv.org/abs/2607.08028
- Natural-Language Agent Harnesses: https://arxiv.org/abs/2603.25723
- Slipstream: https://arxiv.org/abs/2605.08580
- Governance Decay: https://arxiv.org/abs/2606.22528
- Commit-Time Authorization: https://arxiv.org/abs/2607.10487
- Agentic Permissions Policy Algebra: https://arxiv.org/abs/2607.24625
- Hybrid Analysis for Secure MCP Tool Use: https://arxiv.org/abs/2607.25297
- Long-Context Agentic Instruction Following Benchmark: https://arxiv.org/abs/2607.25398
- Agent Skills Matter / SigLeak: https://arxiv.org/abs/2607.25560
- FAVA: https://arxiv.org/abs/2607.27267
- SKIMIX: https://arxiv.org/abs/2607.27994

## 6. Continuation pass: PermissionGraph 原型

本轮在前一轮 `FootprintMeter` 的基础上继续推进，把 authority graph 方向落成代码。

### 6.1 为什么先做 PermissionGraph

上轮判断里，Harness 的风险已经从单步 tool permission 上升到 data-flow / authority witness / commit boundary。新的材料进一步强化了这个判断：

- APPA 说明传统 taint tracking 会永久污染主上下文，因此需要 engine-managed context branching 和 sanitizer derivative。
- Commit-Time Authorization 说明用户批准、DOM snapshot、branch token、worker result 等 authority evidence 可能在 effect commit 时已经失效。
- FAVA 说明自然语言任务可以降成 Permission IR / permission graph，并输出 violation path。
- OpenAI Agents 官方文档也把 guardrails、人审 approval、MCP ownership、tracing/eval 串成了 runtime boundary，而不是单纯 prompt 约束。

因此本轮新增：

- `PermissionGrant`：描述 subject 可以对哪些 resource 执行哪些 effect，以及是否需要 witness。
- `AuthorityWitness`：描述某个 effect 的授权证据，带 checkpoint version freshness。
- `PermissionGraph`：把 context labels、grant、witness 放到一个可 fingerprint 的 graph。
- `PermissionDecision`：返回 allowed/failures/counterexamples/receipt payload。

### 6.2 当前能覆盖的治理语义

```text
untrusted web input
  -> context label: untrusted
  -> write report 被阻断
  -> sanitizer 产生 sanitized derivative
  -> sanitized branch 可写入 report artifact

human approval / branch token
  -> AuthorityWitness
  -> checkpoint_version freshness check
  -> expired witness 阻断 external commit
```

这还不是完整形式化权限系统，但已经比 `approved=True` 强一层：决策能保存、能哈希、能回放，也能在未来接入 `TraceEnvelope.receipts`。

### 6.3 新增 implementation signals

| 来源 | 信号 | 设计吸收 |
|---|---|---|
| AgentCheck | MCP 工具故障可以通过 reproduce/intervene/mitigate workbench 系统复现。 | 后续做 `InterventionReplay`：cached prefix + live suffix + fault injector fingerprint。 |
| AgentTether | 通过 Transition Unit / Critical Transition Graph 定位失败子轨迹。 | 后续把线性 trace 升级成 transition graph，用于 failure attribution 和 repair memory。 |
| MemTX | memory write 不是 belief commit，需要 staged transaction、validation、cascade repair。 | 后续做 `MemoryCommitProtocol`，把 Hermes memory/artifact 写入拆成 staged/validated/committed。 |
| Compile, Then Page | 长 SOP 编译成可执行伪代码，再按 active frame paging 执行。 | Natural-language policy 后续编译成 permission graph / cursor frame。 |
| AgentRadio / SWE Atlas | 长代码库理解受益于 clean contexts 和异步消息层。 | 未来 sub-agent/fork 不共享膨胀上下文，而共享 evidence graph + passive awareness channel。 |
| Self-Improving Behavioral Rules | 人审反馈可以积累成 versioned rule artifact 和 self-review checklist。 | Self-Evo 优先沉淀 rule artifact，通过 replay/eval gate 后再影响 prompt/skill。 |

### 6.4 本轮新增代码

- `src/vibe_research/permission_graph.py`
- `src/vibe_research/intervention_replay.py`
- `AuthorityWitness`
- `PermissionGrant`
- `PermissionGraph`
- `PermissionDecision`
- `InterventionSpec`
- `InterventionReplayWorkbench`
- `InterventionReplayReport`
- tests:
  - tainted input blocks write until sanitized
  - external commit requires fresh authority witness
  - fault injection splits cached prefix and live suffix
  - mitigation is marked effective when it recovers more baseline prefix

### 6.5 新增 sources

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
- Microsoft Agent Governance Toolkit: https://microsoft.github.io/agent-governance-toolkit/
- Microsoft Agent Governance Toolkit repo: https://github.com/microsoft/agent-governance-toolkit

### 6.6 InterventionReplayWorkbench 原型

AgentCheck 的核心价值不是“又一个 benchmark”，而是把 MCP 工具响应变成可注入故障的 replay surface。它要求我们区分：

```text
cached prefix
  -> first injected divergence
  -> live suffix
  -> mitigation rerun
```

本轮新增的 `InterventionReplayWorkbench` 先覆盖最小可测语义：

- `InterventionSpec`：记录 fault kind、目标 tool、目标事件、response overrides 和 metadata。
- `inject_fault()`：对第一条匹配的 `tool_completed` event 注入故障，并写入 `intervention_fingerprint`。
- `compare()`：按 tool、args hash、output hash、trace envelope fingerprint 比较两条 tool trace 的共同前缀。
- `evaluate()`：生成 cached prefix / live suffix / mitigation effectiveness 报告。

这让 `ReplayVerifier` 旁边多了一种更适合长期 agent runtime 的验证模式：

```text
exact replay
  -> intervention replay
  -> mitigation replay
  -> regression seed
```

下一步可以把它接入真实 MCP adapter：记录真实 tool response snapshots，再用 AgentCheck-style fault injector 做 timeout、stale response、poisoned description、missing field、schema drift 等故障复跑。

### 6.7 MemoryCommitProtocol 原型

MemTX 和当前 memory 平台的共同信号很清楚：长期记忆不是“写进去就算了”，而是一个可验证提交协议。

本轮新增的 `MemoryCommitProtocol` 先覆盖最小可测语义：

- `MemoryTransaction`：把 memory write 包成事务，带 `open / committed / aborted` 状态。
- `MemoryRecord`：记录 staged / validated / committed / rejected / retracted 的记录生命周期。
- `ValidationReceipt`：验证 evidence、validator、checkpoint version。
- `MemoryCommitReport`：记录 committed / rejected / failures。
- `MemorySafetyReport`：确认一组 memory records 是否已经可以驱动后续 action。
- `cascade_retract()`：当源事实失效时，沿 parent linkage 回收派生事实。

这对应的 runtime 语义是：

```text
observation
  -> staged memory record
  -> validation receipt
  -> commit
  -> safety gate
  -> retraction cascade if contradicted
```

也就是说，`belief` 不应在 stage 时就进入主上下文；只有通过 validation receipt 和 commit 才能成为可行动事实。

这让 Hermes 的记忆层能同时兼容两类实现：

- LangGraph-style checkpoint/store：负责 durable state 和恢复；
- Letta/Mem0-style long-term memory：负责长期存储和跨 session 检索；
- 但真正的科研 runtime 仍保留本地 `MemoryCommitProtocol`，防止外部记忆服务绕过治理。

下一步如果接外部 memory provider，可以把 provider-native memory id 写入 `source_refs` / `metadata`，再由本地 commit gate 决定是否晋升为 belief。

### 6.8 TransitionGraph 原型

AgentTether、Structured Graph Harness 和 iCORE 共同指向同一个方向：长期 agent 的 trace 不应只是一串 event，而应能被提升成图。

这张图至少要回答：

- 哪些 transition 是 state-changing boundary？
- 当前失败目标依赖哪些上游 transition？
- 哪个 transition 是 branch point？
- 失败修复应该回写到哪一段 critical chain？
- 多 agent / 多 actor 场景下，谁对哪个 transition 有 obligation？

本轮新增：

- `TransitionUnit`：从 state-changing `TraceEvent` 提取 action / checkpoint / feedback / observation 单元。
- `TransitionEdge`：记录 sequence / dependency relation。
- `TransitionGraph`：从事件流构建 transition graph。
- `TransitionGraphReport`：输出 target unit、critical chain、critical subgraph、branch points、roots/leaves 和 fingerprints。
- `TransitionVerifier`：在 eval 层把 event stream 转成 critical transition diagnosis。

最小语义：

```text
TraceEvent list
  -> state-changing transition units
  -> sequence/dependency edges
  -> failed/latest target
  -> critical chain
  -> branch point report
```

这让 failure attribution 从：

```text
event 7 failed
```

升级为：

```text
paper_scan -> run_experiment -> publish_report failed
branch point: paper_scan
failure target: publish_report
```

下一步可以把 `InterventionReplayWorkbench` 的 divergence index 映射进 `TransitionGraph`，形成：

```text
fault injection
  -> divergent transition
  -> critical transition graph
  -> repair memory / rule / skill candidate
```

### 6.9 ObligationAuditMap 与 DecisionMemoryProjection

这轮继续把 graph 化 runtime 往协作审计和决策记忆推进。

新增两个信号：

- iCORE：多 agent 协作不能只看最终产物，要检查 cooperation graph、obligation graph 和 audit map；重点是 work soundness 与 assignment stability。
- Stateless Decision Memory：memory 不应是会被原地改写的黑盒，而应保留 append-only log，并在 decision time 做 task-conditioned projection。

本轮新增：

- `ObligationAuditMap`
  - `Obligation`
  - `AuditLink`
  - `ObligationAuditReport`
  - 检查 satisfied obligation 是否有真实 transition + evidence 支撑。
  - 报告 actor load 和 assignment instability。

- `DecisionMemoryProjection`
  - 从 `MemoryCommitProtocol` 的 records 中投影一次决策视图。
  - 默认只选择 committed memory。
  - 支持 kind / source refs / query terms 过滤。
  - 输出 projection fingerprint，便于 replay 和 eval 固化。

这让多 agent / 长记忆 runtime 形成更完整的控制面：

```text
TransitionGraph
  -> ObligationAuditMap
  -> MemoryCommitProtocol
  -> DecisionMemoryProjection
```

对应的工程含义：

- sub-agent 不只是“谁做了什么”，还要记录“谁应该做什么、证据在哪”；
- memory 不只是“存了什么”，还要记录“这次决策实际看了哪些 committed memory”；
- 多 agent topology 后续还要考虑 reliability-contagion：连接越多不一定越可靠，错误传播也会变快。

### 6.10 Continuation pass: HarnessDiagnosisWorkbench 与 runtime profile 扩展

本轮继续追最新论文和实现，新增一个判断：

**失败轨迹诊断正在从“模型答错了”升级成“harness 哪个控制面漂移了”。**

新的 HarnessFix / HTIR 方向把失败轨迹分解成可诊断中间表示；MCPEvol-Bench 说明 MCP server 和 tool schema 会演化；Agentic Context Management / Always-On Agents 说明长期 agent 的 context、memory、process 都会持续变化；Syll 说明自然语言任务可以编译成 runtime monitor；这些信号合起来指向同一个工程需求：

```text
replay divergence
  -> transition unit
  -> trace envelope fingerprint drift
  -> suspect harness surface
  -> repair hint / resume gate
```

因此本轮新增：

- `src/vibe_research/harness_diagnostics.py`
  - `HarnessDiagnosticWorkbench`
  - `HarnessDiagnosisReport`
  - 将 replay divergence index 映射到 `TransitionGraph` 的 `TransitionUnit`
  - 抽取 trace envelope 中的 provider / protocol / policy / tool-contract / skill-manifest drift
  - 输出 suspect surfaces 与 repair hints
- `scripts/verify_runtime.py`
  - 新增 `harness_diagnosis_divergence_unit_id`
  - 新增 `harness_diagnosis_suspect_surfaces`
  - 新增 `harness_diagnosis_replay_passed`
- `provider_profiles.py`
  - 新增 AWS Bedrock AgentCore profile
  - 新增 Microsoft Agent Framework profile
  - 新增 Pydantic AI durable execution profile
  - 新增 Mistral durable agents profile

这次新增的 runtime 诊断面把前几轮的四个原型串起来：

```text
InterventionReplayWorkbench
  -> first divergence
  -> HarnessDiagnosticWorkbench
  -> TransitionGraph critical chain
  -> TraceEnvelope fingerprint drift
  -> repair/eval gate
```

当前最小语义：

- `output_hash differs`：归因为 `tool_output_or_artifact`，建议重抓 tool output / artifact snapshot，并从 cached prefix replay。
- `args_hash differs`：归因为 `planning_or_context_rendering`，建议检查 context compaction 和 planner inputs。
- `trace_envelope_fingerprint differs`：归因为 `trace_contract`，再进一步比较 provider/policy/tool/skill fingerprint。
- `trace length differs`：归因为 `action_path_policy`，建议检查缺失/多余 tool transition。

这让 `harness x hermes` 的诊断链条更像：

```text
Hermes tells us where the run can resume.
Harness tells us whether it may resume.
HarnessDiagnosis tells us what changed since the last trustworthy run.
```

### 6.11 新增验证过的论文/实现信号

| 来源 | 关键新信号 | 对本项目的吸收 |
|---|---|---|
| HarnessFix / HTIR | 从失败轨迹中诊断 harness flaw，并用中间表示驱动 repair/evaluation。 | 新增 `HarnessDiagnosticWorkbench`，把 divergence 映射到 transition graph 与 trace envelope drift。 |
| Governed Evolution of Agent Runtimes | agent runtime 自我演化需要 policy、operation、knowledge store 与 evolution platform 分层。 | Self-Evo 后续不要直接改 prompt，而是改 versioned runtime artifact，并通过 replay/promotion gate。 |
| Always-On Agents | 持续 agent 需要长期 memory、process、privacy、autonomy 和 interruptible assistance。 | Hermes session 已开始记录 `process_stage`；后续扩展成完整 `ResearchSession` lifecycle。 |
| Agentic Context Management | context 管理正在成为模型和 agent 之间的中间层，负责选择、压缩、结构化和反腐化。 | 已新增 `CompactionVerifier`；后续再扩展 active frame、artifact dependency 和 memory projection。 |
| Harness-MU | multi-turn strategic tool use 强依赖 harness 记录完整 tool-call 信号。 | eval case 需要保存 harness config 和 tool boundary，不只保存最终答案。 |
| MCPEvol-Bench | MCP server/tool 会演化，benchmark 需要覆盖 evolving MCP server 与 tool discovery。 | `ToolDescriptionContract` 后续要支持 schema evolution / deprecation / discovery trail。 |
| Syll | 自然语言任务可编译成 runtime constraints，并在分布式 agent 中持续监控。 | natural-language policy 后续可编译成 `ActionPathPolicy` / `PermissionGraph` / monitor receipt。 |
| ByteRover | coding agent memory 需要兼顾有效性、效率和安全，且要和代码库上下文结构绑定。 | Research memory 不只做向量检索；要结合 artifact/source refs、validation receipt、task-conditioned projection。 |
| AWS Bedrock AgentCore | 官方把 Runtime、Memory、Identity、Gateway、Browser、Code Interpreter、Observability、Evaluations 打包成 agent runtime services。 | 新增 `aws-bedrock-agentcore` capability profile；未来可作为 managed runtime adapter。 |
| Microsoft Agent Framework | 官方将多 agent orchestration 与企业集成/观测/eval 统一成 framework 方向。 | 新增 `microsoft-agent-framework` profile；强调 workflow trace 与 connector permission adapter。 |
| Pydantic AI durable execution | Python typed agent 框架开始内建 durable execution，支持 Temporal/DBOS 等后端。 | 新增 `pydantic-ai-durable` profile；适合对接 typed tool contract 与 durable wait adapter。 |
| Mistral durable agents | workflow 中把 parallel calls、handoff、approval request、agent/tool step 做成显式 durable primitives。 | 新增 `mistral-durable-agents` profile；用于参考 approval state / handoff receipt adapter。 |

### 6.12 本轮新增 sources

- HarnessFix: https://arxiv.org/abs/2606.06324
- Governed Evolution of Agent Runtimes: https://arxiv.org/abs/2605.27328
- Always-On Agents: https://arxiv.org/abs/2606.30306
- Agentic Context Management: https://arxiv.org/abs/2607.21503
- Harness-MU: https://arxiv.org/abs/2606.21856
- MCPEvol-Bench: https://arxiv.org/abs/2607.14642
- Syll: https://arxiv.org/abs/2606.07594
- ByteRover: https://arxiv.org/abs/2604.01599
- AI Runtime Infrastructures: https://arxiv.org/abs/2603.00495
- AWS Bedrock AgentCore: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html
- Microsoft Agent Framework: https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-at-build-2026-announce/
- Pydantic AI durable execution: https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/
- Mistral durable agents: https://docs.mistral.ai/studio-api/workflows/building-workflows/durable_agents

### 6.13 Continuation pass: context compaction, always-on runtime, and framework state surfaces

This round adds one more strong conclusion:

**context compaction is now a first-class governance and replay problem, not a mere token-saving trick.**

The new evidence points in the same direction from different angles:

- Governance Decay shows that compaction can silently drop safety constraints and that the harness, not just the model, is the vulnerable surface.
- Agentic Context Management treats context as a lifecycle object with acquisition, retention, compression, and retirement.
- SmoothAgent shows that lookahead context engineering and cache/routing overhead are part of long-horizon serving.
- Cloudflare Agents, Vercel WorkflowAgent, and Mastra durable agents all expose durable state, resume, snapshots, approvals, and workflow persistence as explicit runtime surfaces.

Engineering consequence for `vibe-research`:

```text
context-management / summary generation
  -> CompactionVerifier
  -> resume gate
  -> replay / eval / policy retention check
```

This is why `CompactionVerifier` now exists in code:

- it checks the retention of runtime identity, goal, cursor, status, process stage, policy, trace, approval boundary, skill manifest, and artifact lineage;
- it reports drifted or missing pins instead of silently accepting a compacted state;
- it can turn `metadata.context_pins` into a resumability contract.

### 6.14 New verified sources

- Governance Decay: https://arxiv.org/abs/2606.22528
- Agentic Context Management: https://arxiv.org/abs/2607.21503
- ACM: Agentic Context Management for Long Horizon Tasks: https://arxiv.org/abs/2607.23809
- SmoothAgent: https://arxiv.org/abs/2607.00151
- Cloudflare Agent class internals: https://developers.cloudflare.com/agents/runtime/lifecycle/agent-class/
- Vercel AI SDK WorkflowAgent: https://ai-sdk.dev/docs/agents/workflow-agent
- Mastra durable agents: https://mastra.ai/docs/long-running-agents/durable-agents
- Mastra suspend and resume: https://mastra.ai/docs/workflows/suspend-and-resume
- Mastra human-in-the-loop: https://mastra.ai/docs/workflows/human-in-the-loop
- Mastra workflow state: https://mastra.ai/docs/workflows/workflow-state
- Mastra snapshots: https://mastra.ai/docs/workflows/snapshots

### 6.15 Continuation pass: ProcessLifecycleVerifier

Always-On Agents gives a useful frame for persistent agents: the hard part is not merely keeping a process alive, but knowing which state item can affect which future action. The paper frames persistent state through six diagnostic axes:

```text
authority / scope / mutability / provenance / recoverability / actionability
```

The implementation trend says the same thing in product form:

- Cloudflare Agents model agents as stateful Durable Object-backed runtime objects.
- Vercel WorkflowAgent puts a durable/resumable agent inside a workflow primitive.
- Mastra durable agents expose suspend/resume, human approval, background tasks, snapshots, and workflow state as explicit primitives.

This round adds the corresponding runtime primitive:

- `src/vibe_research/process_lifecycle.py`
  - `ProcessStage`
  - `StateLedgerItem`
  - `ProcessLifecycleVerifier`
  - `ProcessLifecycleReport`
  - `state_ledger_items_from_state()`
- `RuntimeState.process_stage`
- `HermesRuntime.start_task()` now starts tasks at `process_stage=active`.
- `HarnessHermesRuntime.run_tool()` moves stages through:

```text
ready/running -> active
awaiting_approval -> waiting
blocked/failed -> suspended
completed -> archiving
```

The new verifier checks:

- whether the runtime process stage matches `RunStatus`;
- whether every persistent state item has the six always-on axes;
- whether effectful state items are recoverable;
- whether the ledger can be fingerprinted for replay/audit.

Smoke output now includes:

- `process_lifecycle_stage`
- `process_lifecycle_stage_matches_status`
- `process_lifecycle_effectful_item_ids`
- `process_lifecycle_failures`

This extends the previous chain:

```text
Hermes checkpoint
  -> CompactionVerifier
  -> ProcessLifecycleVerifier
  -> HarnessDiagnosticWorkbench
  -> replay/eval/skill gate
```

Next useful step: turn `ProcessLifecycleReport` into a `ResearchSession` object so paper scan / experiment / review / writeup are lifecycle-aware phases, not just free-form tool calls.

### 6.16 Continuation pass: ResearchSession

This round follows the research-agent systems thread rather than the generic runtime thread.

Signals from Aris, OpenRath, and the broader AI-scientist-style workflow literature all point to the same missing object:

```text
research task
  -> typed research session
  -> phase topology
  -> evidence gate
  -> artifact/review/writeup lifecycle
```

The important shift is that `vibe-research` should not treat scientific work as one flat action path. A research run has domain phases:

```text
intake
  -> paper_scan
  -> hypothesis
  -> experiment_plan
  -> experiment_run
  -> analysis
  -> review
  -> writeup
  -> archive
```

This round adds:

- `src/vibe_research/research_session.py`
  - `ResearchPhase`
  - `ResearchPhaseGate`
  - `ResearchSession`
  - `ResearchSessionVerifier`
  - `ResearchSessionReport`
  - `research_session_from_state()`
- `scripts/verify_runtime.py`
  - `research_session_current_phase`
  - `research_session_phase_gate_passed`
  - `research_session_ready_for_phase_exit`
  - `research_session_artifact_kinds`

Current gate semantics:

- phase topology must be valid;
- writeup can require paper shortlist, hypothesis, metric, analysis report;
- writeup can require experiment transition, peer review transition, committed memory record, validation receipt, and review ref;
- report is fingerprinted for replay/eval.

The new chain is:

```text
RuntimeState
  -> ResearchSession
  -> ResearchPhaseGate
  -> ResearchSessionReport
  -> eval / writeup / archive promotion gate
```

This connects the lower-level runtime primitives to the scientific workflow:

```text
MemoryCommitProtocol
  -> committed metric belief
  -> ResearchSession phase gate
  -> writeup allowed
```

Next useful step: connect `ResearchSessionReport` to `ObligationAuditMap`, so every phase gate can also say who/what actor was responsible for satisfying it.

### 6.17 Continuation pass: EvidenceLedger and hydratable research scenes

这轮把“上下文现场”从 checkpoint 再往前推了一层：不是只恢复聊天上下文，也不是只恢复 `RuntimeState`，而是恢复一个可验证的 research scene。

新的 mental model 是：

```text
dehydrate
  -> RuntimeState snapshot
  -> TraceEnvelope / receipts
  -> MemoryCommitProtocol records
  -> EvidenceLedger
  -> ResearchSession phase gate

hydrate
  -> restore cursor / pending approval
  -> verify policy pins / process stage
  -> re-project committed memory
  -> validate active evidence claims
  -> resume only the active research frame
```

这轮新增的 `EvidenceLedger` 原型覆盖：

- `EvidenceEntry`：source / artifact / observation / derived / review；
- `EvidenceClaim`：科研声明与 citation；
- `EvidenceStatus`：active / quarantined / retracted；
- parent lineage：derived evidence 必须有可追溯 parent；
- claim soundness：accepted claim 不能引用 missing / inactive / forbidden evidence。

和前面几个模块的分工变成：

| 模块 | 管什么 |
|---|---|
| `HermesRuntime` | 任务身份、cursor、checkpoint、resume。 |
| `CompactionVerifier` | dehydration 后 summary 是否保留 policy / goal / artifact / approval pins。 |
| `MemoryCommitProtocol` | 观察能不能晋升成 committed belief。 |
| `EvidenceLedger` | claim 是否由 active source-backed evidence 支撑。 |
| `ResearchSessionAuditBridge` | phase gate 是否有 actor / transition / obligation 证据。 |

新论文/实现信号也支持这条线：

- *Filesystem-Based Memory for LLM Agents*：把 agent memory 看成一个由管理、搜索、执行过程共同维护的文件系统式空间，而不是一坨聊天历史。
- *Harness-G*：把 search agent 的 harness 做成图结构，说明 context/action surface 本身可以是图，而不只是线性 prompt。
- Microsoft Agent Governance Toolkit：把 policy、identity、sandbox、compliance 和 SRE/reliability 做成独立治理栈，适合映射成 Harness profile。

本轮新增代码和验证：

- `src/vibe_research/evidence_ledger.py`
- `EvidenceClaim` / `EvidenceEntry` / `EvidenceLedger` / `EvidenceLedgerReport`
- `scripts/verify_runtime.py` 输出 `evidence_ledger_sound`
- tests 覆盖 source-backed claim、quarantined evidence、missing citation、orphan derived evidence

下一步建议：

1. 把 `EvidenceLedger` 挂到 `ResearchSession`，让每个 phase gate 可要求 claim id。
2. 把 evidence fingerprint 写进 `TraceEnvelope` receipt。
3. 做 hydration manifest：明确哪些 state / memory / evidence / artifact 在恢复时必须重建。

### 6.18 Continuation pass: EvidenceClaim-gated phase exit

这轮把上一节的第 1 个建议落成代码：`ResearchSession` 的 phase gate 现在可以直接要求 evidence claim。

新的 gate 语义是：

```text
ResearchPhaseGate
  -> required_artifact_kinds
  -> required_transition_labels
  -> required_memory_record_ids
  -> required_evidence_refs
  -> required_evidence_claim_ids
  -> forbidden_evidence_labels
```

这意味着 writeup / archive promotion 不再只检查“有没有 analysis artifact”，而是检查：

```text
artifact exists
  + committed memory exists
  + validation receipt exists
  + review ref exists
  + evidence claim exists
  + evidence claim is supported by active evidence
  + evidence claim does not cite forbidden/quarantined labels
```

对 FSE 投稿线的价值：

- RQ2 不再只是 memory commit safety，而是能直接评估 unsupported claim rate；
- ablation 可以去掉 `EvidenceLedger` 或 claim gate，观察 writeup false-positive；
- failure taxonomy 可以加入 `missing_evidence_claim`、`unsupported_evidence_claim`、`quarantined_evidence_citation`。

本轮新增/更新：

- `ResearchPhaseGate.required_evidence_claim_ids`
- `ResearchPhaseGate.forbidden_evidence_labels`
- `ResearchSessionReport.missing_evidence_claim_ids`
- `ResearchSessionReport.unsupported_evidence_claim_ids`
- `ResearchSessionAuditBridge.evaluate(..., evidence_ledger=...)`
- `scripts/verify_runtime.py` 输出 research-session claim-gate 状态

### 6.19 Continuation pass: context lifecycle / data-quality gating / always-on governance

这轮继续查了 2026 年 6-7 月的新材料，结论是：`hydration / memory / replay` 三条线不能只写成工程模块，而要写成长期 agent 的 runtime lifecycle contract。

| 新材料 | 关键信号 | 对 Harness x Hermes 的影响 |
|---|---|---|
| ACM / VISTA / context-file ablation | context 不是“越多越好”，也不是放一个 `AGENTS.md` 就解决；长任务需要 typed block、usage/recency/access dashboard、archive/recover 和 active-frame retention。 | 创新点 1 要写成 `Hydratable Scene as context lifecycle contract`，实验要比较 checkpoint-only / context-file / runtime-scene hydration。 |
| SARC-DQ | 最危险的证据缺陷可能是 metadata-borne：payload 看起来正常，但 freshness / lineage / provenance 已坏；模型能力不会自动买来怀疑能力。 | 创新点 2 要从 memory commit 扩成 evidence/data-quality gate，RQ2 增加 silent evidence defect、stale metadata、predicate coverage。 |
| Always-OnAgents survey | persistent agent state 不只包括 memory，还包括 task ledger、permission、credential、commitment、provenance、audit record、shared state 和 externally committed effects；评估应看 state mutation / recovery obligations。 | Hermes 的 scene manifest 和 process lifecycle 要强调 authority / scope / mutability / provenance / recoverability / actionability 六轴。 |
| Harness-G / TrajAudit | search/harness 可以是图结构，trajectory audit 可以自动定位轨迹失败；raw log inspection 已经不是充分对照。 | 创新点 3 要强调 transition graph + evidence-retaining replay，并把 official execution ingest 作为 benchmark replay substrate。 |
| OpenAI Sandbox Agents / DeepSeek coding agents / OpenHands Agent Server / Microsoft AGT | 主流实现正在把 sandbox session、resume、approval、tracing、agent server、governance/compliance 做成产品化 runtime surface。 | FSE 论文定位应继续坚持 “runtime support for SE agents”，而不是 “another framework”。 |

折回三条创新点，当前更稳的表述是：

1. **Hydratable Scene / Context Lifecycle Contract**：恢复的不是 transcript，而是带 active-frame、policy/evidence/artifact pins、typed context block 和 authority boundary 的 execution scene。
2. **Evidence-Governed Memory and Data-Quality Commit**：memory commit 前必须过 validation receipt / evidence ledger / data-quality predicate，避免 stale metadata、silent evidence defect 和 unsupported claim 进入长期状态。
3. **Evidence-Retaining Replay Diagnosis**：trace envelope 不只保留 tool/action，还保留 evidence scene、oracle provenance、official execution receipts，并提升成 transition graph 做 failure attribution。

实验上下一轮应该增加三个更硬的检查：

- RQ1：加入 context-file / context-dashboard / scene-hydration 的对照，报告 `context_pin_recall`、`active_frame_retention`、`state_reconstruction_accuracy`。
- RQ2：加入 metadata-borne stale evidence 和 downstream-only remediation，报告 `silent_evidence_defect_block_rate`、`unsupported_claim_rate`、`memory_interference_block_rate`。
- RQ3：把 `SweBenchOfficialExecutionIngestor` 产生的 official execution receipts 纳入 replay，报告 `official_execution_ingest_soundness`、`artifact_provenance_completeness`、`fault_localization_mrr`。

本轮 source refs：

- Agentic Context Management for Long-Horizon Tasks: https://arxiv.org/abs/2607.23809
- LLM Agents Are Latent Context Managers: https://arxiv.org/abs/2606.30005
- Do Context Files Help Coding Agents?: https://arxiv.org/abs/2607.27250
- SARC-DQ: https://arxiv.org/abs/2607.26313
- Always-OnAgents survey: https://arxiv.org/abs/2606.30306
- Harness-G: https://arxiv.org/abs/2607.27652
- TrajAudit: https://arxiv.org/abs/2605.26563

### 6.20 Continuation pass: FSE top-conference alignment audit

这轮把 “A 会标准难度” 从文档口号变成了一个可运行的 audit gate。

新增：

- `src/vibe_research/fse_alignment.py`
- `FseTopConferenceAlignmentAuditor`
- `FseTopConferenceAlignmentReport`
- `scripts/verify_fse_benchmark.py` 输出：
  - `ready_for_top_conference_positioning`
  - `ready_for_artifact_smoke`
  - `ready_for_submission_empirics`
  - `empirical_maturity_level`
  - `missing_submission_gates`
  - `recommended_next_experiments`
- `scripts/run_fse_local_benchmark.py` 输出 `top_conference_alignment_report.json`

核心思想是把当前进展拆成三层：

```text
FSE positioning readiness
  != artifact smoke readiness
  != submission empirical readiness
```

本轮 verifier 结果：

```text
ready_for_top_conference_positioning = true
ready_for_artifact_smoke = true
ready_for_submission_empirics = false
empirical_maturity_level = L3_official_ingest_contract_smoke
```

这个结果很符合当前真实状态：

- 计划形状已经足够像 FSE：3 task families、5 baselines、16 faults、7 ablations、23 metrics、4 RQs、8 related-work clusters、152 synthetic cells。
- Artifact smoke 已经能跑：local toy artifacts、SWE-bench-style adapter、local patch executor、official-subset bridge、official execution ingest contract。
- 但投稿实证还不够：真实 SWE-bench Verified official Docker small subset 没跑，真实 paper artifact replication adapter 还没有接。

这个 audit gate 是故意严格的。它会防止我们把 “demo-shaped official execution ingest” 包装成 “真实官方 benchmark 结果”。对于 FSE，这个差别非常大：前者证明 runtime contract 设计合理，后者才支撑 empirical claim。

下一步最有效的实验路线：

1. 跑 5-10 个 SWE-bench Verified official Docker instances；
2. 把官方 `results.json` / `instance_results.jsonl` / `run_logs` 接回 `SweBenchOfficialExecutionIngestor`；
3. 找 1 个小型真实 artifact replication package；
4. 在同一真实任务切片上跑 `no_hydration_manifest` / `no_memory_commit` / `no_trace_receipt` ablations；
5. 把 `top_conference_alignment_report.json` 放进 artifact package，让每次迭代都明确 “我们离投稿还差什么”。

本轮验证：

- `python -m pytest tests/test_fse_benchmark.py tests/test_fse_artifact_cli.py -q` -> 8 passed
- `python scripts/verify_fse_benchmark.py` -> top-conference positioning ready, artifact smoke ready, submission empirics not ready

补充发现：在把 artifact smoke 输出放到项目树内部时，`SweBenchLocalPatchExecutor` 暴露了一个真实 benchmark 风险：`git apply` 会向上发现父仓库 `.git`，导致嵌套 toy repo 的 patch 被跳过但返回码仍为 0。这会让测试看起来通过，但 regression test 实际没有进入工作区。

本轮修复：

- `SweBenchLocalPatchExecutor._apply_patch()` 设置 `GIT_CEILING_DIRECTORIES`，阻止 patch 子进程向上捕获父仓库；
- patch apply 后比较 workspace fingerprint；
- 返回码为 0 但 workspace 未变化时，判定为 patch 未生效。

这个小修复正好印证了 FSE 论文里的一个核心观点：benchmark result 不能只看命令返回码，必须保留 oracle/provenance/execution receipts，并验证 effect 是否真实发生。

### 6.21 Continuation pass: real artifact-replication package ingestor

这轮把 submission gate 里的第二个缺口也工程化了：真实论文 artifact replication 不再只是 TODO，而是有了 manifest-driven ingest/execute/audit 入口。

新增：

- `src/vibe_research/artifact_replication.py`
- `ArtifactReplicationPackageSpec`
- `ArtifactReplicationPackageIngestor`
- `ArtifactReplicationRunReport`
- `tests/test_artifact_replication.py`
- `scripts/run_fse_local_benchmark.py --real-artifact-manifest <manifest.json>`
- `yys/all/0802/real_artifact_replication_manifest_template.json`

Manifest 最小语义：

```json
{
  "package_id": "artifact-id",
  "paper_title": "Paper title",
  "artifact_root": "/path/to/unpacked/artifact",
  "run_command": ["python", "run_replication.py"],
  "expected_artifacts": ["results/metrics.json"],
  "expected_metric_files": ["results/metrics.json"],
  "source_refs": ["paper-or-artifact-url"],
  "timeout_s": 600
}
```

执行流程：

```text
manifest
  -> copy artifact_root to isolated workspace
  -> run command
  -> collect stdout/stderr
  -> check expected artifacts and metric files
  -> execution_report.json
  -> EvidenceLedger
  -> MemoryCommitProtocol
  -> ResearchSession phase gate
  -> HydrationManifest verify
  -> real_artifact_replication_report.json
```

这一步的重要性在于：下一轮只要找到一个真实 FSE/ICSE/ASE artifact package，就可以直接接进现有 benchmark，不需要再重写 `artifact_replication` family 的 evidence/hydration/reporting contract。

当前 artifact smoke 默认没有传入真实 manifest，所以：

```text
real_artifact_replication_ready = false
real_artifact_replication_count_for_submission_gate = 0
ready_for_submission_empirics = false
```

如果传入 manifest 且跑通，`real_artifact_replication_count_for_submission_gate` 会自动提升；top-conference audit 将不再报告 “replace toy artifact replication” 这个缺口，但仍会保留 SWE-bench official Docker 缺口。

本轮验证：

- `python -m pytest tests/test_artifact_replication.py tests/test_fse_artifact_cli.py -q` -> 4 passed
- `python scripts/run_fse_local_benchmark.py --output-dir yys/all/0802/fse_artifact_smoke` -> ready true, full 152 synthetic cells, real artifact manifest missing warning retained

### 6.22 Continuation pass: official SWE-bench Docker preflight

这轮也把第一个 submission gate 的环境检查显式化了。真实 official SWE-bench Docker run 当前不能直接执行，因为本机缺少：

```text
docker command
Python module swebench
```

新增：

- `src/vibe_research/swebench_preflight.py`
- `SweBenchOfficialDockerPreflight`
- `SweBenchOfficialDockerPreflightReport`
- `scripts/preflight_swebench_official.py`
- `reports/swebench_official_docker_preflight_report.json`

当前 preflight 输出：

```text
ready_for_swebench_official_docker_run = false
docker_available = false
swebench_module_available = false
predictions_path_exists = true
subset_manifest_path_exists = true
official_harness_command_present = true
```

这说明我们的 official subset / predictions / command artifact 已经生成，但还不能 claim “official Docker execution completed”。下一步需要在有 Docker 的环境里安装 SWE-bench，并执行：

```bash
python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Verified \
  --predictions_path yys/all/0802/fse_artifact_smoke/swebench_official_subset/official_predictions.jsonl \
  --max_workers 1 \
  --run_id harness-x-hermes-small-subset
```

跑完后，把官方输出目录喂给：

```bash
python scripts/run_fse_local_benchmark.py \
  --output-dir yys/all/0802/fse_artifact_smoke \
  --swebench-official-evaluation-dir /path/to/official/evaluation_results
```

这一步会让 `SweBenchOfficialExecutionIngestor` 接住真实 `results.json` / `instance_results.jsonl` / `run_logs`，并更新 top-conference audit。

### 6.23 Continuation pass: real experiment slice and same-task ablation plan

这轮继续把 “真实任务 + 同任务 ablation” 变成可机器读取的计划，而不是只写在论文计划里。

新增：

- `src/vibe_research/real_experiment_plan.py`
- `FseRealExperimentSlicePlanner`
- `FseRealExperimentSlicePlan`
- `FseRealAblationVariant`
- `reports/real_experiment_slice_plan.json`
- `tests/test_real_experiment_plan.py`

计划里固定四个 same-task variants：

```text
hermes_full
no_hydration_manifest
no_memory_commit
no_trace_receipt
```

这四个变体分别对应：

- full runtime reference；
- 创新点 1：Hydratable Scene / Context Lifecycle Contract；
- 创新点 2：Evidence-Governed Memory and Data-Quality Commit；
- 创新点 3：Evidence-Retaining Replay Diagnosis。

当前 `real_experiment_slice_plan.json` 输出：

```text
real_experiment_slice_ready = false
real_experiment_same_task_ablation_variant_count = 4
missing_dependencies =
  - docker command is not available; official SWE-bench evaluation cannot run locally
  - Python module 'swebench' is not installed
  - no real artifact replication manifest supplied
```

这个文件的作用是给下一轮真实实验一个明确执行顺序：

1. preflight official SWE-bench；
2. run official SWE-bench Docker；
3. ingest official results；
4. run real artifact replication manifest；
5. 在同一批真实任务 slice 上跑 full / no-hydration / no-memory / no-trace-receipt。

这一步让 FSE 实验部分更像 A 会论文：不是只跑一个 full system，而是对同一任务切片做 ablation-backed causal evidence。
