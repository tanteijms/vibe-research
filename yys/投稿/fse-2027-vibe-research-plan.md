# FSE 2027 投稿对标方案：Harness x Hermes

> 目标会议：FSE 2027 Research Track  
> 官方 deadline：2026-10-02  
> 当前日期：2026-08-02  
> 剩余时间：约 61 天  
> 推荐投稿定位：Software Engineering for Agentic Systems / AI for Software Engineering / Dependable Agent Runtime

## 1. 会议口味判断

FSE 2027 Research Track 明确欢迎 theoretical、empirical、conceptual、experimental software engineering research，并强调 originality、importance、soundness、evaluation、presentation 和 related-work comparison。官方 topics 里和本项目最强相关的是：

- Artificial intelligence and machine learning for software engineering
- Debugging and fault localization
- Dependability, safety, and reliability
- Empirical software engineering
- Program comprehension
- Software engineering for machine learning and artificial intelligence
- Software security
- Software testing
- Software traceability
- Tools and environments

这说明 `vibe-research` 不能按“我们做了一个 Agent 框架”去投。FSE 更吃的是：

```text
一个新兴 SE 问题
  -> 一个可解释 runtime model
  -> 一个可复现实验基准
  -> 和强 baseline 的 empirical comparison
  -> artifact / replication package
```

所以推荐论文主线是：

```text
Long-horizon AI agents are becoming software systems,
but current agent frameworks lack reliable hydration/dehydration,
governed memory commit, and replayable failure diagnosis.
```

中文理解：

```text
长期 Agent 已经是软件系统了，
但现在缺少一套能恢复现场、控制记忆污染、诊断长链路失败的 SE runtime 方法。
```

### 1.1 近三年 FSE 相关趋势

近三年 FSE 对 agent / assistant 的口味其实越来越清楚：

- FSE 2025 的 `Demystifying LLM-based Software Engineering Agents` 说明 reviewer 已经开始认真看“SE agents 到底是什么、能做什么”。
- FSE 2026 的 `Reducing Cost of LLM Agents with Trajectory Reduction` 说明单纯堆 trajectory 已经不行，成本与冗余必须被系统化治理。
- FSE 2026 的 `AgentBound: Securing Execution Boundaries of AI Agents` 和 `Evaluating Privilege Usage of Agents on Real-World Tools` 说明权限、执行边界、真实工具上的 privilege usage 已经进入主流研究视野。
- FSE 2026 的 `RocketMQ-A2A: Reliable Session-Level Replayable Event Streams for Large-Scale Multi-Agent Collaboration` 说明 replayable event streams 和 session-level collaboration 也是认可方向。
- FSE 2026 的 `AgentReputation: A Decentralized Agentic AI Reputation Framework` 说明 verification metadata、risk-conditioned policy engine 和 tamper-proof persistence 可以成为 agent 研究的主对象。
- FSE 2026 的 `Event-B Agent: Towards LLM Agent for Formal Model Synthesis and Repair` 说明 FSE 已经接受“LLM agent + verification feedback + repair loop”的范式，但它更偏 formal synthesis/repair；我们这边补 runtime 与 evidence/replay 语义。
- 2025/2026 的 in-IDE HAX 系统性综述指出 verification overhead、automation bias、over-reliance、长期评估和 governance framework 是关键缺口，这和我们的治理型 runtime 方向完全一致。

这对我们非常有利，因为 `Harness x Hermes` 正好覆盖了：

```text
boundary / privilege / replay / trajectory / resume / evidence / runtime governance
```

也就是说，这不是泛泛的 AI Agent 话题，而是 FSE 正在形成共识的一条 SE 研究线。

## 2. 推荐论文题目

优先推荐：

```text
Hermes: Hydratable and Evidence-Governed Runtime Support for Long-Horizon Software Engineering Agents
```

备选：

```text
Harness x Hermes: Replayable Runtime Governance for Long-Horizon Agentic Software Engineering
```

更偏科研 Agent：

```text
VibeResearch: Evidence-Aware Hydration and Replay for Long-Horizon Research Agents
```

我建议主标题不要太像产品名。FSE reviewer 更容易接受 “runtime support / empirical study / software engineering agents” 这种措辞。

## 3. 三个核心创新点

### 创新点 1：Hydratable Research Scene，而不是 transcript checkpoint

现有 Agent 框架常见恢复方式是：

```text
conversation transcript
  + tool logs
  + checkpoint state
```

我们提出的是：

```text
research scene manifest
  + RuntimeState
  + policy/provider/tool/skill fingerprints
  + pending approval / authority witness
  + committed memory projection
  + evidence ledger
  + research phase gate
  + trace envelope
```

核心 claim：

> Long-horizon agents should dehydrate and hydrate verifiable execution scenes, not raw conversation histories.

对应实现：

- `RuntimeState`
- `HermesRuntime`
- `HydrationManifest`
- `CompactionVerifier`
- `ProcessLifecycleVerifier`
- `ResearchSession`
- `EvidenceLedger`

和已有工作的区别：

- 比 LangGraph checkpoint 多了 policy/evidence/authority/research phase gate；
- 比 AgentDiet / trajectory reduction 更强调“安全恢复”和“证据保真”，而不是只降 token；
- 比普通 session persistence 多了恢复前 verifier。

### 创新点 2：Evidence-Governed Memory Commit Protocol

现有 Agent 往往是：

```text
observation -> memory
```

我们提出：

```text
observation
  -> staged memory
  -> validation receipt
  -> committed memory
  -> decision projection
  -> evidence-backed claim
```

核心 claim：

> Agent memory should be treated as a governed software artifact with commit, validation, provenance, and retraction semantics.

对应实现：

- `MemoryCommitProtocol`
- `ValidationReceipt`
- `DecisionMemoryProjection`
- `EvidenceLedger`
- `EvidenceClaim`
- `EvidenceEntry`
- `ResearchPhaseGate.required_evidence_claim_ids`

FSE 角度的价值：

- 这是 software engineering 的“状态一致性 / provenance / artifact lifecycle”问题；
- 可以实验衡量 memory pollution；
- 可以和长期 Agent 的 hallucination / unsupported claim 直接挂钩。

### 创新点 3：Replayable Failure Diagnosis via TraceEnvelope + TransitionGraph

现有 Agent debug 常见是读 log：

```text
tool call log
  -> human manually inspect
```

我们提出：

```text
TraceEnvelope
  -> TransitionGraph
  -> InterventionReplay
  -> HarnessDiagnosticReport
  -> repair / eval seed
```

核心 claim：

> Long-horizon agent failures can be localized and reproduced by lifting traces into governed transition graphs.

对应实现：

- `TraceEnvelope`
- `TraceEnvelope.evidence_ledger_fingerprint`
- `TraceEnvelope.evidence_claim_ids`
- `InterventionReplayWorkbench`
- `TransitionGraph`
- `HarnessDiagnosticWorkbench`
- `ObligationAuditMap`
- `ResearchSessionAuditBridge`

FSE 角度的价值：

- 对应 debugging / fault localization / software traceability；
- 可以做 fault injection；
- 可以衡量 fault localization accuracy、replay fidelity、repair success。

## 4. 论文贡献写法

建议写成 3 + 1：

1. A runtime model for hydratable agent execution scenes.
2. A governed memory/evidence protocol for long-horizon agents.
3. A replayable failure-diagnosis mechanism based on trace envelopes and transition graphs.
4. An empirical evaluation on long-horizon software-engineering agent tasks with artifact release.

注意：第 4 个贡献必须做扎实。FSE 不会只收架构 proposal。

## 5. Research Questions

### RQ1：Hydration Correctness

> Does scene-based hydration improve correct task resumption compared with transcript-based or checkpoint-only baselines?

指标：

- resume success rate
- state reconstruction accuracy
- phase gate correctness
- missing policy/evidence pin rate
- cost/token overhead

扰动：

- context compaction
- interruption / pending approval
- provider switch
- tool schema drift
- stale artifact

### RQ2：Memory and Evidence Safety

> Does governed memory commit reduce invalid memory use and unsupported claims in long-horizon agent tasks?

指标：

- invalid memory commit rate
- unsupported claim rate
- quarantined evidence citation rate
- retraction cascade correctness
- downstream action blocked/allowed precision

扰动：

- misleading paper abstract
- outdated experiment result
- contradictory metric
- poisoned tool output
- retracted source evidence

### RQ3：Failure Diagnosis and Replay

> Can trace-envelope-driven transition graphs localize and reproduce long-horizon agent failures more accurately than raw logs?

指标：

- replay fidelity
- fault localization accuracy / MRR
- diagnosis precision by surface:
  - tool output
  - policy drift
  - memory drift
  - evidence drift
  - compaction drift
- evidence-receipt drift detection rate
- claim-preserving replay fidelity
- mitigation success rate
- human debugging time

扰动：

- tool timeout
- stale RAG result
- missing artifact
- approval expiry
- wrong memory commit
- context summary drops safety instruction

### RQ4：Practical Cost

> What is the overhead of scene-based governance, and can it remain practical for software-engineering agents?

指标：

- token cost
- checkpoint size
- trace size
- runtime overhead
- number of extra verifier calls
- task success/cost tradeoff

这个 RQ 很重要，因为 FSE 2026 已经有 AgentDiet 这种 trajectory reduction 方向。我们必须承认成本问题，并证明 governance 不是不可承受。

## 6. Baseline 设计

建议至少四类：

| Baseline | 对标目的 |
|---|---|
| ReAct + raw transcript | 最基础 agent loop。 |
| LangGraph checkpoint / interrupt | 对标 durable state / resume。 |
| OpenHands-style coding agent | 对标真实 SE agent runtime。 |
| Agentless / simple staged pipeline | 对标 FSE 2025 对复杂 agent 的质疑。 |
| AgentDiet-style trajectory reduction | 对标 FSE 2026 agent trajectory cost 方向。 |

注意：Agentless 和 AgentDiet 不一定能完整跑我们的所有任务，但必须在 related work 和可比子任务里正面回应。

## 7. Benchmark / Dataset 设计

建议不要只做“科研任务”，要把它包装成 Software Engineering Agent Tasks。

### Task Family A：Issue-to-Patch / Repo Maintenance

来源：

- SWE-bench Lite / Verified 子集
- 小型真实 repo issue
- 自建可控 bug tasks

长链路：

```text
read issue
  -> inspect repo
  -> localize fault
  -> propose patch
  -> run tests
  -> write report
```

适合测：

- replay fidelity
- fault localization
- checkpoint resume
- tool failure recovery

### Task Family B：Research Artifact Replication

来源：

- FSE / ICSE / ASE 论文 artifact
- 小型 benchmark replication package
- 自建 toy replication tasks

长链路：

```text
read paper/artifact
  -> identify assumptions
  -> run script
  -> collect metric
  -> validate result
  -> write reproduction note
```

适合测：

- evidence ledger
- memory commit
- unsupported claim rate
- phase gate correctness

### Task Family C：Incident / RCA Agent Tasks

来源：

- synthetic logs
- open incident reports
- self-constructed microservice failure traces

长链路：

```text
read alert
  -> query logs
  -> inspect metric
  -> identify root cause
  -> cite evidence
  -> propose mitigation
```

适合测：

- diagnostic trace
- evidence-backed claims
- tool fault injection
- stale / missing evidence handling

## 8. 关键实验矩阵

| 实验 | 目的 | 方法 | 预期结果 |
|---|---|---|---|
| E1 Resume under interruption | 验证 hydration | 在任务不同阶段中断，再恢复 | Hermes scene 恢复率高于 transcript/checkpoint-only |
| E2 Compaction drift | 验证 context governance | 删除/压缩 policy/evidence pins | `CompactionVerifier` 能阻止危险恢复 |
| E3 Memory pollution | 验证 commit protocol | 注入错误观察和冲突 metric | invalid memory commit 明显下降 |
| E4 Unsupported claims | 验证 evidence ledger | 要求 agent 写 report 并引用证据 | unsupported claim rate 下降 |
| E5 Tool fault replay | 验证 intervention replay | 注入 timeout/stale/missing field | replay fidelity 和 mitigation success 提升 |
| E6 Failure localization | 验证 transition graph | 标注 ground-truth failure step | localization accuracy/MRR 高于 raw log |
| E7 Cost/overhead | 回应 FSE 成本关切 | 统计 token/checkpoint/runtime overhead | 证明治理成本可控 |
| E8 Ablation | 证明每个模块必要 | 去掉 Memory/Evidence/Trace/Compaction | 每个模块对不同 failure class 有贡献 |

## 9. Reviewer 可能质疑与防守

### 质疑 1：这是不是 another agent framework？

防守：

不是。论文贡献是 runtime model + failure/evidence semantics + empirical evaluation，不是框架拼装。

文中应该弱化：

- UI
- prompt
- 多 provider demo
- “AI Scientist”营销词

强化：

- formal state model
- verifier
- trace/replay
- empirical benchmark
- replication package

### 质疑 2：为什么投 FSE，不是 AI/agent 会议？

防守：

因为我们研究的是 agentic systems as software systems：

- state management
- failure diagnosis
- traceability
- reproducibility
- artifact lifecycle
- software process
- tool/environment reliability

这些都是 FSE 核心 SE 问题。

### 质疑 3：实验任务是不是太小？

防守：

任务必须覆盖真实 SE primitives：

- repo navigation
- test execution
- artifact reproduction
- RCA
- report writing
- evidence citation

同时给出开放 artifact 和 fault injection scripts。

### 质疑 4：LLM 变化太快，结果会不会过期？

防守：

我们评估的是 model-agnostic runtime properties：

- hydration correctness
- evidence safety
- replay fidelity
- diagnosis accuracy

模型只是 executor，runtime 指标不依赖单一模型。

## 10. 61 天执行计划

### Week 1：定题和 benchmark 定义

- 固定论文 title / abstract / contribution
- 选 30-50 个初始任务
- 定义 failure injection taxonomy
- 写 `hydration manifest` 数据结构草案

### Week 2-3：实现可评估 runtime

- 把 `EvidenceLedger` 接入 `ResearchSession`
- 把 evidence fingerprint / claim ids / evidence receipt 写进 `TraceEnvelope`
- 做 `HydrationManifest`
- 做 task runner CLI
- 做 baseline runner

### Week 4-5：跑主实验

- RQ1 resume
- RQ2 memory/evidence
- RQ3 replay diagnosis
- 初步跑 2-3 个模型/provider

### Week 6：补 ablation 和 cost

- no-compaction-verifier
- no-memory-commit
- no-evidence-ledger
- no-transition-graph
- cost/token/checkpoint overhead

### Week 7：写论文

- Introduction
- Motivating example
- Model/design
- Evaluation
- Related work

### Week 8：打磨 FSE 标准

- threat to validity
- Data Availability
- artifact anonymization
- result table polish
- rebuttal checklist

## 11. 当前项目下一步工程任务

优先级从高到低：

1. `HydrationManifest`
   - 状态：已新增第一版原型。
   - 当前能力：明确 state / trace / memory / evidence / artifact / policy 哪些必须恢复，并在 hydration preflight 中检查 fingerprint、required memory、required evidence claim 和 required artifact。
   - 下一步：接入 benchmark runner 的 resume preflight 和 task-family fault injector。

2. `ResearchSession` 接 `EvidenceLedger`
   - 状态：已新增第一版原型。
   - 当前能力：phase gate 不只检查 artifact kind，还检查 required claim id，并可阻断 missing / unsupported / quarantined evidence claim。
   - 下一步：把 claim-level report 接入 benchmark 指标。

3. `TraceEnvelope` 接 evidence fingerprint
   - 状态：已新增第一版原型。
   - 当前能力：profiled tool event 可从 `RuntimeState.metadata.active_evidence_ledger` 读取 evidence ledger fingerprint / claim ids，写入 `TraceEnvelope`，并生成 `evidence_ledger` proof receipt；`ReplayVerifier` 会比对 evidence fingerprint 和 claim ids。
   - 下一步：做 receipt-level diff，把 evidence drift 映射到 `HarnessDiagnosticReport.suspect_surfaces`。

4. `BenchmarkRunner`
   - 状态：已新增 `FseBenchmarkPlan` scaffold、`SyntheticFseBenchmarkRunner`、`SyntheticFseTraceRunner`、`FseLocalToyTaskRunner`、`SweBenchSmallSubsetAdapter`、`SweBenchLocalPatchExecutor`、`SweBenchOfficialSubsetBridge`、`SweBenchOfficialExecutionIngestor` 和 artifact-package smoke CLI。
   - 当前能力：结构化定义 issue-to-patch / artifact replication / incident RCA 三类 task family，5 个 baseline、16 个 fault scenario、7 个 ablation、23 个 metric、4 个 RQ 和 8 个 related-work cluster，并可展开成 152 个 synthetic experiment cells，再生成 deterministic synthetic trace results；三类 local toy task 已能生成真实本地 artifacts 并通过 evidence / memory / phase gate / hydration 检查；SWE-bench-style adapter 已能接受 JSONL 或 demo subset，生成 problem / gold patch / candidate patch / test patch / correctness report artifacts，并报告 patch divergence、evidence、memory 和 hydration；SWE-bench-style local executor 已能复制本地 repo、应用 test/candidate patch、运行 tests，并保留 stdout/stderr/execution report；official subset bridge 已能生成 predictions JSONL、official harness command、subset manifest 和 oracle-audit receipts；official execution ingestor 已能接住 `results.json` / `instance_results.jsonl` / `run_logs` 并写入 evidence / hydration / replay contract；`scripts/run_fse_local_benchmark.py` 可生成 plan / readiness / matrix / synthetic trace / local run / SWE-bench adapter / SWE-bench executor / SWE-bench official subset / official execution ingest / artifact manifest / summary JSON。
   - 下一步：把 official subset bridge 接到真实 SWE-bench Verified small subset Docker execution，并把官方结果目录直接喂给 official execution ingestor；同时继续补真实 artifact-replication package adapter 和 incident RCA trace adapter。

5. `FaultInjector`
   - 状态：已新增 FSE fault taxonomy。
   - 当前覆盖：interruption、compaction drift、stale tool output、missing artifact、quarantined evidence、expired approval、wrong memory commit、provider switch、tool schema drift、evidence receipt drift。
   - 下一步：把 taxonomy 映射到 `InterventionReplayWorkbench` 和 `HydrationManifest.verify` 的实际注入器。

6. Baseline adapters
   - 状态：已新增 baseline spec。
   - 当前覆盖：raw ReAct、checkpoint-only、LangGraph-style、OpenHands-style、AgentDiet-style。
   - 下一步：实现 raw transcript / checkpoint-only / no-governance ablation 的本地可运行 adapter。

## 12. 推荐摘要草稿

Long-horizon LLM agents are increasingly used to perform software-engineering tasks such as repository maintenance, artifact reproduction, and incident diagnosis. However, existing agent frameworks typically persist raw transcripts or coarse checkpoints, making it difficult to safely resume interrupted tasks, prevent memory pollution, and reproduce failures. This paper presents Hermes, a hydratable runtime model for long-horizon software-engineering agents. Hermes dehydrates agent execution into verifiable research scenes containing runtime state, policy and provider fingerprints, authority witnesses, committed memory projections, evidence ledgers, phase gates, and trace envelopes. On hydration, Hermes verifies scene integrity before rendering the active execution frame. We further introduce governed memory commits and replayable transition-graph diagnosis to reduce unsupported claims and localize long-horizon failures. An empirical evaluation on issue-resolution, artifact-replication, and incident-diagnosis tasks shows that scene-based hydration improves resume correctness, reduces invalid memory use, and improves failure localization compared with transcript-based and checkpoint-only baselines, with practical runtime overhead.

## 12.1 本轮实现增量：HydrationManifest

本轮已把创新点 1 的核心对象落成可测试代码：

```text
HydrationManifest
  task/session/run identity
  cursor / active step / process stage
  state fingerprint
  policy fingerprint
  trace fingerprint
  artifact fingerprint
  memory fingerprint + required memory ids
  evidence ledger fingerprint + required claim ids
  research session fingerprint
```

恢复前检查：

```text
manifest + current scene
  -> retained / missing / drifted surfaces
  -> unsafe staged memory detection
  -> missing evidence claim detection
  -> missing artifact detection
  -> safe_to_hydrate
```

这让 RQ1 可以从“概念性恢复”变成可量化实验：

- manifest retained surface rate
- drifted surface detection rate
- unsafe hydration block rate
- resume success after manifest verification

## 12.2 本轮实现增量：EvidenceClaim-Gated ResearchSession

本轮已把创新点 2 接入科研生命周期：

```text
ResearchPhaseGate
  required_artifact_kinds
  required_transition_labels
  required_memory_record_ids
  required_evidence_refs
  required_evidence_claim_ids
  forbidden_evidence_labels
```

也就是说，writeup / archive 不再只要求“有一个 analysis artifact”，而是要求：

```text
analysis artifact exists
  + committed memory exists
  + validation receipt exists
  + review ref exists
  + required evidence claim is active and supported
```

这让 RQ2 可以直接落成可量化实验：

- missing required evidence claim rate
- unsupported evidence claim rate
- quarantined evidence citation block rate
- writeup gate false-positive / false-negative

## 12.3 本轮实现增量：Evidence-Retaining TraceEnvelope

本轮把创新点 2 和创新点 3 的连接处补齐了：

```text
EvidenceLedger
  -> active_evidence_ledger snapshot
  -> TraceEnvelope.evidence_ledger_fingerprint
  -> TraceEnvelope.evidence_claim_ids
  -> evidence_ledger proof receipt
  -> ReplayVerifier evidence drift check
```

这意味着回放不再只比较 tool/action，而是比较“当时这次 action 所依赖的 evidence scene”。这对 FSE 很重要，因为 long-horizon agent 的失败经常不是动作错，而是证据链漂移、旧 claim 被复用、或 writeup 在恢复后引用了已失效的证据。

对应 RQ3 可以新增两个指标：

- evidence-receipt drift detection rate
- claim-preserving replay fidelity

对应实现：

- `src/vibe_research/trace_contract.py`
- `src/vibe_research/runtime.py`
- `src/vibe_research/eval.py`
- `tests/test_harness_hermes.py`
- `scripts/verify_runtime.py`

## 12.4 本轮实现增量：FSE Benchmark Scaffold

本轮把 FSE 论文最容易被 reviewer 卡住的“实验设计是否扎实”先结构化落地了。

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
  -> data availability / replication package plan
  -> SyntheticFseBenchmarkRunner
  -> 152 planned experiment cells
  -> SyntheticFseTraceRunner
  -> deterministic replay / diagnosis / evidence-drift result report
  -> FseLocalToyTaskRunner
  -> local issue-to-patch / artifact-replication / incident-RCA artifact smoke
```

这解决的是一个很实际的问题：FSE 不会因为 runtime 设计漂亮就收，必须能证明它对软件工程任务有可复现实验价值。这个 scaffold 把后续实验固定为：

- Task Family A：Issue-to-Patch / Repo Maintenance
- Task Family B：Research Artifact Replication
- Task Family C：Incident / RCA Agent Tasks

并把三条创新点映射到实验：

| 创新点 | 对应 RQ | 关键 fault | 关键 ablation |
|---|---|---|---|
| Hydratable Research Scene | RQ1 | interruption / compaction drift / context manager dropped pin / provider switch | no hydration manifest / no compaction verifier |
| Evidence-Governed Memory Commit | RQ2 | wrong memory commit / quarantined evidence / missing artifact | no memory commit / no evidence ledger |
| Evidence-Retaining Replay | RQ3 | stale tool output / evidence receipt drift / tool schema drift / benchmark oracle drift | no transition graph / no trace receipt |

对应实现：

- `src/vibe_research/fse_benchmark.py`
- `src/vibe_research/fse_benchmark_runner.py`
- `tests/test_fse_benchmark.py`
- `scripts/verify_runtime.py`
- `scripts/verify_fse_benchmark.py`

当前 smoke 结果：

- synthetic trace processed cells: 152
- fault detected cells: 122
- evidence drift detected cells: 70
- replay-passed cells: 30
- failures: 0

## 12.5 本轮实现增量：Local Toy Artifact Runner

本轮把 benchmark 从 pure synthetic trace 往真实 artifact 方向推进了一步：

```text
FseLocalToyTaskRunner
  -> issue-to-patch toy repo
  -> artifact replication toy package
  -> incident RCA toy logs
  -> real local files / artifacts
  -> EvidenceLedger
  -> MemoryCommitProtocol
  -> ResearchSessionGate
  -> HydrationManifest
```

当前 smoke 结果：

- local task count: 3
- local success count: 3
- local artifact count: 10
- local evidence claim count: 5
- local committed memory count: 3
- local hydration safe count: 3
- local phase gate passed count: 3

这一步对 FSE 很重要：它把实验从“我们有一个 runtime 设计和合成 trace”推进到“artifact package 里可以真的创建文件、验证证据、提交记忆、恢复现场”。下一步就可以把这三个 toy task 替换成：

- SWE-bench Verified / small issue-to-patch subset；
- 真实论文 artifact replication package；
- synthetic/real incident RCA traces。

## 12.6 本轮实现增量：Artifact-Package Smoke CLI

本轮新增 `scripts/run_fse_local_benchmark.py`，把当前 FSE benchmark scaffold 变成可运行的 replication-package 雏形：

```text
python scripts/run_fse_local_benchmark.py --output-dir <artifact-dir>
```

它会生成：

```text
reports/benchmark_plan.json
reports/benchmark_readiness.json
reports/benchmark_matrix.json
reports/benchmark_matrix_report.json
reports/synthetic_trace_report.json
reports/local_run_report.json
reports/swebench_adapter_report.json
reports/swebench_executor_report.json
reports/artifact_manifest.json
reports/summary.json
local_artifacts/
swebench_adapter/
swebench_executor/
```

这一步的论文价值是把 data availability / artifact evaluation 提前工程化：现在不仅能说明有哪些 RQ、baseline、fault 和 metrics，还能让 reviewer 运行一个稳定 CLI，看到 synthetic replay/evidence-drift 结果、三类 local artifact smoke、SWE-bench-style issue-to-patch adapter smoke 和 local patch executor smoke。新增 `tests/test_fse_artifact_cli.py` 会真实调用 CLI，并验证 generated files、artifact manifest、local artifact refs、SWE-bench adapter refs、SWE-bench executor refs、hydration safety 和 phase gate。

当前 CLI 默认使用一个两实例 SWE-bench-style demo subset；后续真实实验可以沿同一 CLI 接入：

- `issue_to_patch`: SWE-bench Verified 小子集 JSONL / local executor / Docker harness；
- `artifact_replication`: 真实 FSE/ICSE/ASE artifact package；
- `incident_rca`: synthetic/real incident trace benchmark；
- `baselines`: raw transcript、checkpoint-only、LangGraph-style、OpenHands-style、AgentDiet-style 和 no-evidence/no-memory/no-hydration ablation。

## 12.7 本轮实现增量：SWE-bench-style Small Subset Adapter

本轮新增 `src/vibe_research/swebench_adapter.py`，把 `issue_to_patch` 真实 benchmark 接口先固定下来：

```text
SweBenchSmallSubsetAdapter
  -> load SWE-bench-style JSONL / demo instances
  -> materialize problem_statement.md
  -> materialize gold.patch
  -> materialize candidate.patch
  -> materialize test.patch
  -> emit patch_correctness_report.json
  -> EvidenceLedger
  -> MemoryCommitProtocol
  -> ResearchSessionGate
  -> HydrationManifest
```

注意边界：它目前不是完整 Docker SWE-bench executor，而是 patch/evidence/hydration adapter。这个边界是刻意的，因为 FSE 论文首先需要稳定的 reporting contract；之后真实 executor 可以接到同一 contract 上。

它新增的指标包括：

- `patch_equal_to_gold`
- `changed_file_overlap`
- `patch_line_jaccard`
- `behavioral_divergence_score`
- `test_patch_present`
- `evidence_ledger_sound`
- `hydration_safe`
- `phase_gate_passed`

这正好回应 SWE-bench / SWE-bench Verified 的风险：A 会 reviewer 不会只看 tests passed，还会问 patch 是否真的正确、有没有行为差异、证据是否可复查、恢复后是否仍引用同一证据。

当前 smoke 能力：

- demo SWE-bench-style instances: 2
- success: 2 / 2
- candidate patch equal to gold: 1 / 2
- mean patch-line Jaccard: 0.6666
- mean behavioral divergence score: 0.2334
- hydration safe: 2 / 2
- evidence sound: 2 / 2

## 12.8 本轮实现增量：SWE-bench-style Local Patch Executor

本轮在 adapter 基础上继续新增 `SweBenchLocalPatchExecutor`。它不是官方 Docker SWE-bench harness，但已经把最小执行链跑通：

```text
local repo
  -> copy workspace
  -> git apply test.patch
  -> git apply candidate.patch
  -> run test_command
  -> capture stdout / stderr / execution_report
  -> EvidenceLedger
  -> MemoryCommitProtocol
  -> ResearchSessionGate
  -> HydrationManifest
```

这里有一个重要语义：executor success 和 candidate patch correctness 被分开记录。

```text
success_count = executor 是否完成复制、patch、测试和证据保留
tests_passed_count = candidate patch 是否通过 regression tests
```

当前 demo smoke：

- executor instances: 2
- executor success: 2 / 2
- executor tests passed: 1 / 2
- executor hydration safe: 2 / 2
- executor evidence sound: 2 / 2
- executor candidate patch equal to gold: 1 / 2
- executor mean patch-line Jaccard: 0.75
- executor mean behavioral divergence score: 0.175

这一步对 FSE 很关键：`issue_to_patch` 不再只是 materialized patch artifacts，而是已经开始保留真实执行证据。后续可以把 demo source repos 替换成 SWE-bench Verified small subset 的 checkout / Docker workspace。

## 12.9 本轮外部校准：为什么还是 FSE 主投

重新核对 FSE 2027 官方 CFP、CCF 2026 推荐目录和 SWE-bench family 后，结论更明确：

```text
主投仍然应该是 FSE 2027 Research Track。
但论文必须像 empirical SE + runtime model，
不能像 “we built an agent framework”。
```

关键依据：

- FSE 2027 Research Track 鼓励 original theoretical / empirical / conceptual / experimental software engineering research，也鼓励 replication packages、available datasets 和 tools。
- FSE 2027 的评价标准明确覆盖 originality、importance、soundness、evaluation、presentation 和 related-work comparison。
- FSE topic list 里，当前项目直接命中 AI/ML for SE、debugging and fault localization、dependability / safety / reliability、empirical SE、program repair、software engineering for ML/AI、software security、software testing、software traceability、tools and environments。
- CCF 2026 第七版目录中，FSE、ASE、ICSE、ISSTA 都是“软件工程/系统软件/程序设计语言”A 类会议；FSE 与本项目的 runtime + debugging + traceability 组合最贴。
- SWE-bench / SWE-bench Verified 适合做 issue-to-patch 基础任务，但 SWE-Bench Pro 和 ICSE 2026 的 SWE-bench correctness critique 表明：A 会 reviewer 不会只满足于 test-pass rate，必须加入更强 correctness / behavioral divergence / trace evidence 指标。

这意味着实验路线要从：

```text
agent solves task or not
```

升级为：

```text
agent scene can be safely resumed
+ memory/evidence claims remain governed
+ replay can detect drift and localize failure
+ cost/footprint overhead remains practical
+ artifacts are reproducible by reviewer
```

最应该优先补的不是 UI，而是三个真实 adapter：

1. SWE-bench Verified small subset adapter：验证 issue-to-patch 下的 hydration / replay / evidence claims。
2. Real artifact replication adapter：验证 paper artifact、script、metric、writeup 之间的 lineage 和 memory commit。
3. Incident RCA adapter：验证动态 evidence collection、root cause claim、diagnosis replay 和 mitigation report。

## 12.10 本轮外部校准：runtime enforcement / failure attribution / memory interference

继续追最新论文后，三条创新点的边界更清楚了。

### 对创新点 1 的加强：Hydratable Scene = externalized runtime surfaces

AgentSpec 和 Externalization in LLM Agents 都说明，agent runtime 正在把 memory、tools、skills、workflow、policy 和 enforcement 外置成可管理 surfaces。我们的 `HydrationManifest` 正好可以把这些 surfaces 变成恢复前必须验证的 scene contract。

所以创新点 1 不要写成：

```text
we save better checkpoints
```

而要写成：

```text
we dehydrate and hydrate externalized runtime surfaces with enforcement-ready fingerprints
```

对应实验：

- checkpoint-only vs scene-hydration；
- summary-only compaction vs policy/evidence-pinned compaction；
- provider/tool/schema drift 下的恢复正确性；
- pending approval / authority witness 恢复正确性。

### 对创新点 2 的加强：Evidence-Governed Memory 要测 interference

FORGET-SE 和 SWE-bench correctness critique 都提醒我们：长期 agent 的 memory 问题不只是“写错一条事实”，还包括：

- memory decay；
- similar-task interference；
- stale belief 被后续任务复用；
- retrieval component 引入不稳定 evidence；
- test-pass 但 patch behavior 有偏差。

所以 RQ2 要从：

```text
does memory commit reduce unsupported claims?
```

扩成：

```text
does evidence-governed memory commit reduce invalid, stale, and interference-induced memory use?
```

对应实验：

- wrong memory commit；
- memory interference / stale belief；
- quarantined evidence；
- retrieval component shift；
- candidate patch vs gold patch divergence；
- writeup 使用失效 claim 的阻断率。

### 对创新点 3 的加强：Replay Diagnosis 要对标 failure attribution

EAGER 和 FAMAS 说明，FSE/SE 社区已经开始接受：

```text
agent trajectory
  -> replay / abstraction / reasoning trace representation
  -> failure attribution
  -> repair guidance
```

这和我们的 `TraceEnvelope + TransitionGraph + HarnessDiagnosticWorkbench` 非常贴，但也意味着论文里不能把第三点写成“我们记录 trace”。要写成：

```text
evidence-retaining replay for long-horizon failure attribution
```

对应实验：

- raw log inspection；
- trace-only replay；
- trace + transition graph；
- trace + transition graph + evidence receipt；
- fault localization MRR；
- evidence-receipt drift detection rate；
- human debugging time。

### 当前 benchmark plan 的更新

本轮已经把这些材料加入 `FseBenchmarkPlan` 的 related-work clusters：

- AgentSpec；
- EAGER；
- FAMAS；
- Externalization in LLM Agents；
- FORGET-SE；
- Not All RAGs Are Created Equal；
- Harness Engineering for Auditable Enterprise LLM Agents。

本轮也已经把两个最关键的新 fault 落进 benchmark：

```text
memory_interference
retrieval_component_shift
```

对应新增指标：

```text
memory_interference_block_rate
retrieval_evidence_stability
```

上一轮矩阵从 102 cells 扩展为 120 cells：

- main cells: 72
- ablation cells: 48
- fault scenarios: 12
- metrics: 17
- synthetic fault detected: 102
- evidence drift detected: 44
- replay-passed: 18

这个扩展使 RQ2 可以直接测 memory decay / interference / stale belief，RQ3 可以直接测 retrieval/evidence-intake shift 对 evidence-retaining replay 的影响。

## 12.11 本轮外部校准：context management / benchmark validity

继续查最新材料后，FSE 对标里又出现两个必须提前防守的问题：

1. **Agentic Context Management**：长任务 agent 不再只是“上下文够不够长”的问题，而是 context selection、editing、offloading、active-frame retention 是否会丢掉 policy/evidence/artifact pins。  
2. **Benchmark Validity / Oracle Provenance**：SWE-bench Verified 适合做基础 issue-to-patch 子集，但近期 SWE-bench Pro、SWE-Lancer 和 SWE-bench correctness critique 都在提醒：只报 pass rate 不够，要证明 test oracle、gold patch、environment 和 task provenance 没漂移、没污染。

对应代码已吸收为两个新增 fault：

```text
context_manager_dropped_pin
benchmark_oracle_drift
```

对应新增指标：

```text
context_pin_recall
artifact_provenance_completeness
benchmark_oracle_provenance_rate
oracle_audit_report.json
```

当前矩阵从 120 cells 扩展为 152 cells：

- main cells: 104
- ablation cells: 48
- fault scenarios: 16
- metrics: 23
- related-work clusters: 8
- synthetic fault detected: 122
- evidence drift detected: 70
- replay-passed: 30

这次扩展的意义是：RQ4 不再只是 token/checkpoint/runtime overhead，而是加入“为了让 FSE reviewer 相信实验有效，需要付出的 provenance / oracle / context-retention 成本”。这会让论文更像 empirical SE，而不是 agent framework demo。

## 12.12 本轮实现增量：SWE-bench Official Subset Bridge

为了从 demo executor 走向真实 SWE-bench Verified / Pro，这轮新增了 `SweBenchOfficialSubsetBridge`。它不是 Docker executor，而是官方 harness 前置 artifact bridge：

```text
official SWE-bench-style instances JSONL
  + predictions JSONL
  -> official_predictions.jsonl
  -> official_harness_command.txt
  -> official_subset_manifest.json
  -> per-instance oracle_audit_report.json
```

它检查：

- instance 是否有 `repo / base_commit / problem_statement / patch / test_patch / FAIL_TO_PASS`；
- prediction 是否有 `instance_id / model_name_or_path / model_patch`；
- oracle audit fingerprint 是否 sound；
- 是否有可选的 `local_repo_path / test_command` 以进入 local executor；
- 官方 harness command 是否固定。

当前 smoke 结果：

- ready_for_swebench_official_subset: true
- official subset instances: 2
- matched predictions: 2
- oracle-audit sound: 2
- official-harness ready: 2
- generated report: `reports/swebench_official_subset_report.json`

论文里的作用：这让 `benchmark_oracle_drift` 不只是 synthetic fault，而是有一个可落地 artifact contract。下一步只需要把 `official_predictions.jsonl` 交给官方 Docker harness，再把 `results.json` / `instance_results.jsonl` / `run_logs` 接回同一 evidence / hydration / replay contract。

### 12.12.1 本轮新增：SWE-bench Official Execution Ingest

为了把官方 Docker 执行结果接回研究 runtime，这轮新增了 `SweBenchOfficialExecutionIngestor`。它不是 Docker executor，而是官方 harness 输出的 ingest / audit 层：

```text
official results.json
  + instance_results.jsonl
  + optional run_logs/
  -> execution receipts per instance
  -> official_execution_ingest_report.json
  -> official_execution_evidence_ledger.json
  -> official_execution_hydration_manifest.json
  -> official_execution_hydration_report.json
```

它解决的是 FSE 审稿会盯住的那个问题：

```text
官方执行结果
  -> 能不能审计
  -> 能不能复水
  -> 能不能和 evidence / replay contract 同步
```

当前 smoke 已经能验证 demo-shaped official execution results ingestion；真实实验时只要把官方结果目录接入同一个 ingest contract 即可。

## 12.13 最新外部校准：context lifecycle / data-quality gate / always-on governance

继续查 2026 年 6-7 月的新论文后，三条创新点可以再收紧一版。新的信号不是“agent 更会写代码了”，而是“长期 agent 的 context、memory、evidence、approval、sandbox 和 execution result 都变成需要治理的 runtime surfaces”。

| 最新信号 | 对本项目的直接含义 | 实验要怎么对标 |
|---|---|---|
| ACM / VISTA / context-file ablation | context 不是长窗口问题，而是生命周期问题：acquire / retain / compress / archive / recover。 | RQ1 不只测 interruption resume，还要测 context pin / active frame 是否被保留。 |
| SARC-DQ | 证据缺陷可能藏在 metadata、freshness、lineage 里；模型能力不会自动发现 silent evidence defect。 | RQ2 要加入 metadata-borne stale evidence 和 silent evidence defect 注入。 |
| Always-OnAgents survey | 长期 agent state 包含 task ledger、permission、credential、commitment、provenance、audit record、shared state 和 external effects。 | process-lifecycle / hydration manifest 要按 authority、scope、mutability、provenance、recoverability、actionability 六轴解释。 |
| Harness-G / TrajAudit | harness/search/trajectory 可以变成 graph 和 audit substrate，raw log 不是充分 baseline。 | RQ3 要比较 raw log、trace-only、transition graph、transition graph + evidence receipts。 |
| OpenAI Sandbox Agents / DeepSeek coding agents / OpenHands Agent Server / Microsoft AGT | 主流实现已经把 sandbox session、resume、approval、tracing、agent server、governance/compliance 产品化。 | 论文叙事继续坚持 runtime support，而不是 “another agent framework”。 |

因此，三条创新点现在最好写成：

1. **Hydratable Scene as Context Lifecycle Contract**  
   恢复的不是 transcript，而是带 active-frame、policy/evidence/artifact pins、typed context block 和 authority boundary 的 execution scene。

2. **Evidence-Governed Memory and Data-Quality Commit**  
   memory commit 前必须过 validation receipt / evidence ledger / data-quality predicate，避免 stale metadata、silent evidence defect 和 unsupported claim 进入长期状态。

3. **Evidence-Retaining Replay Diagnosis**  
   trace envelope 不只保留 tool/action，还保留 evidence scene、oracle provenance、official execution receipts，并提升成 transition graph 做 failure attribution。

下一轮实验应该新增三个更像 FSE 的硬指标：

- `active_frame_retention`：恢复后模型是否拿到正确当前工作帧，而不是一堆历史摘要。
- `silent_evidence_defect_block_rate`：metadata/freshness/lineage 缺陷被 EvidenceLedger / MemoryCommitProtocol 阻断的比例。
- `official_execution_ingest_soundness`：官方 SWE-bench 执行结果进入 evidence / hydration / replay contract 后是否仍然可审计、可复水、可对照。

## 12.14 本轮工程迭代：Top-conference alignment audit

这轮补了一个非常关键的顶会对标层：`FseTopConferenceAlignmentAuditor`。

它解决的是一个投稿前很容易犯的错误：把 “artifact smoke 能跑” 错认为 “FSE empirical evidence 已经够”。FSE reviewer 关心的是研究结论是否被真实任务、强 baseline、ablation、oracle provenance 和可复现 artifact 支撑；所以现在 verifier 会把状态拆成三层：

| Gate | 当前状态 | 含义 |
|---|---:|---|
| `ready_for_top_conference_positioning` | `true` | 叙事、RQ、baseline、fault taxonomy、ablation、metric 和 related-work breadth 已经像 FSE Research Track。 |
| `ready_for_artifact_smoke` | `true` | plan / synthetic matrix / local toy artifact / SWE-bench-style executor / official ingest contract 都能跑通。 |
| `ready_for_submission_empirics` | `false` | 还不能声称 empirical evidence 足以投稿，因为真实 official Docker benchmark 和真实 artifact replication 还没补齐。 |

当前 maturity level：

```text
L3_official_ingest_contract_smoke
```

这表示我们已经不只是 synthetic plan：官方 SWE-bench-shaped 输出可以进入 evidence / hydration / replay contract；但它仍然是 demo-shaped ingest，不是 5-10 个真实 SWE-bench Verified official Docker execution。

新增实现：

- `src/vibe_research/fse_alignment.py`
- `FseTopConferenceAlignmentAuditor`
- `FseTopConferenceAlignmentReport`
- `scripts/verify_fse_benchmark.py` 输出 top-conference audit
- `scripts/run_fse_local_benchmark.py` 生成 `top_conference_alignment_report.json`

当前 verifier 摘要：

```text
ready_for_top_conference_positioning = true
ready_for_artifact_smoke = true
ready_for_submission_empirics = false
empirical_maturity_level = L3_official_ingest_contract_smoke
missing_submission_gates =
  - run at least 5 SWE-bench Verified instances through the official Docker harness
  - replace toy artifact replication with at least 1 real paper artifact package
```

这层 audit 对论文写作非常重要：我们可以在内部继续说 “方向和框架已成型”，但对外投稿时必须等真实实证补齐。顶会最怕的是 claim 比 evidence 快一步；这层 gate 就是防这个。

下一步最值得做的实验不再是扩更多 synthetic fault，而是：

1. **SWE-bench Verified official Docker small subset**
   - 先跑 5-10 个实例；
   - 保留 `results.json`、`instance_results.jsonl`、`run_logs`；
   - 通过 `SweBenchOfficialExecutionIngestor` 接回 evidence / hydration / replay contract。

2. **Real artifact-replication task**
   - 找 1 个小型真实论文 artifact package；
   - 用 `artifact_replication` family 跑 hydration、memory commit、evidence gate；
   - 报告 unsupported claim rate、artifact provenance completeness、active frame retention。

3. **Same-task ablation**
   - 在同一批真实任务上跑 `no_hydration_manifest`、`no_memory_commit`、`no_trace_receipt`；
   - 对应三条创新点分别给出增益，而不是只报告 Hermes full 的表现。

## 12.15 本轮工程迭代：real experiment entrypoints

上一节的 audit 已经把 submission 缺口压成两个 gate：

```text
1. official SWE-bench Verified Docker small subset
2. real paper artifact replication package
```

这轮把两个 gate 都做成了可执行入口。

### 12.15.1 Real artifact replication ingestor

新增：

- `ArtifactReplicationPackageIngestor`
- `ArtifactReplicationRunReport`
- `scripts/run_fse_local_benchmark.py --real-artifact-manifest <manifest.json>`
- `yys/all/0802/real_artifact_replication_manifest_template.json`

Manifest 示例：

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

这个 ingestor 会复制 artifact、运行命令、收集 stdout/stderr、检查 expected artifacts 和 metric files，然后接入：

```text
EvidenceLedger
MemoryCommitProtocol
ResearchSession phase gate
HydrationManifest
```

因此，一旦找到真实 paper artifact package，就可以直接从 toy artifact 进入真实 artifact replication evidence。

### 12.15.2 Official SWE-bench Docker preflight

新增：

- `SweBenchOfficialDockerPreflight`
- `scripts/preflight_swebench_official.py`
- `swebench_official_docker_preflight_report.json`

当前机器 preflight：

```text
docker_available = false
swebench_module_available = false
predictions_path_exists = true
subset_manifest_path_exists = true
official_harness_command_present = true
ready_for_swebench_official_docker_run = false
```

这意味着 official subset / predictions / command 已经准备好，但真实 Docker execution 还不能在当前环境直接跑。下一步需要在有 Docker 和 SWE-bench 包的环境执行官方 command，然后把结果目录喂回 `SweBenchOfficialExecutionIngestor`。

这两个 entrypoint 的意义是：后续不再只是说 “要补真实实验”，而是已经把真实实验入口、报告格式和 top-conference gate 接好了。

## 13. Sources

- FSE 2027 Research Track CFP: https://conf.researchr.org/track/fse-2027/fse-2027-papers
- FSE 2027 Important Dates: https://conf.researchr.org/dates/fse-2027
- CCF 2026 recommended conference directory: https://ccf.atom.im/
- AgentSpec: https://arxiv.org/abs/2503.18666
- EAGER: https://arxiv.org/abs/2603.21522
- Externalization in LLM Agents: https://arxiv.org/abs/2604.08224
- FORGET-SE: https://arxiv.org/abs/2605.14503
- FORGET-SE repository: https://github.com/alyssa-sha/FORGET-SE
- FSE 2026 FAMAS: https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/205/Spectrum-based-Failure-Attribution-for-Multi-Agent-Systems
- FSE 2026 Not All RAGs Are Created Equal: https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/159/Not-All-RAGs-Are-Created-Equal-A-Component-Wise-Empirical-Study-for-Software-Enginee
- FSE 2026 AgentDiet: https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/137/Reducing-Cost-of-LLM-Agents-with-Trajectory-Reduction
- FSE 2026 AgentBound: https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/14/AgentBound-Securing-Execution-Boundaries-of-AI-Agents
- FSE 2026 privilege usage: https://conf.researchr.org/details/fse-2026/fse-2026-ideas-papers/15/Evaluating-Privilege-Usage-of-Agents-on-Real-World-Tools
- FSE 2026 RocketMQ-A2A: https://conf.researchr.org/details/fse-2026/fse-2026-industry-papers/29/RocketMQ-A2A-Reliable-Session-Level-Replayable-Event-Streams-for-Large-Scale-Multi-Age
- FSE 2026 AgentReputation: https://arxiv.org/abs/2605.00073
- FSE 2026 Event-B Agent: https://conf.researchr.org/details/fse-2026/fse-2026-research-papers/211/Event-B-Agent-Towards-LLM-Agent-for-Formal-Model-Synthesis-and-Repair
- Human-AI experience in IDEs SLR: https://arxiv.org/abs/2503.06195
- SWE-bench: https://www.swebench.com/
- SWE-bench Verified: https://www.swebench.com/swebench-verified.html
- SWE-bench Pro: https://www.swebench.com/swebench-pro.html
- SWE-bench evaluation guide: https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/evaluation.md
- OpenAI SWE-bench Verified: https://openai.com/index/introducing-swe-bench-verified/
- SWE-bench Pro public leaderboard: https://labs.scale.com/leaderboard/swe_bench_pro_public
- SWE-bench repository / harness: https://github.com/swe-bench/SWE-bench
- ICSE 2026 SWE-bench correctness critique: https://software-lab.org/publications/icse2026_SWE-bench-correctness.pdf
- Agentic Context Management for Long-Horizon Tasks: https://arxiv.org/abs/2607.23809
- LLM Agents Are Latent Context Managers: https://arxiv.org/abs/2606.30005
- Do Context Files Help Coding Agents?: https://arxiv.org/abs/2607.27250
- SARC-DQ: https://arxiv.org/abs/2607.26313
- Always-OnAgents survey: https://arxiv.org/abs/2606.30306
- TrajAudit: https://arxiv.org/abs/2605.26563
- Trajectory Structure Diagnostics for Coding Agents: https://arxiv.org/abs/2607.06184
- MemAct: https://arxiv.org/abs/2510.12635
- AgentProg: https://arxiv.org/abs/2512.10371
- mini-SWE-agent: https://github.com/SWE-agent/mini-swe-agent
- FSE 2025 Agentless: https://conf.researchr.org/details/fse-2025/fse-2025-research-papers/85/Demystifying-LLM-based-Software-Engineering-Agents
- FSE 2024 RCA agents: https://2024.esec-fse.org/details/fse-2024-industry/20/Exploring-LLM-based-Agents-for-Root-Cause-Analysis
- Microsoft Agent Governance Toolkit: https://microsoft.github.io/agent-governance-toolkit/
- Filesystem-Based Memory for LLM Agents: https://arxiv.org/abs/2607.26637
- From Prompts to Contracts: Harness Engineering for Auditable Enterprise LLM Agents: https://arxiv.org/abs/2607.08028
- Harness-G: https://arxiv.org/abs/2607.27652
- LLM Agents Are Latent Context Managers: https://arxiv.org/abs/2606.30005
- Do Context Files Help Coding Agents?: https://arxiv.org/abs/2607.27250
- SARC-DQ: https://arxiv.org/abs/2607.26313
- Always-OnAgents survey: https://arxiv.org/abs/2606.30306
- OpenAI Sandbox Agents: https://developers.openai.com/api/docs/guides/agents/sandboxes
- DeepSeek coding agents: https://api-docs.deepseek.com/guides/coding_agents/
- OpenHands Agent Server: https://docs.openhands.dev/sdk/arch/agent-server
- Microsoft Agent Governance Toolkit: https://microsoft.github.io/agent-governance-toolkit/
