# 0802 当前进度：LLM 实跑、Harness x Hermes 状态与 FSE 对标

> 日期：2026-08-02  
> 最新复跑时间：2026-08-02 21:26 CST  
> 项目：`vibe-research`  
> 目标会议：FSE 2027 Research Track / CCF-A Software Engineering  
> 当前主线：不是做 another agent framework，而是做 long-horizon software-engineering agents 的 hydratable / evidence-governed / replayable runtime support。

## 1. 这次最重要的变化

这轮已经把 `secrets.txt` 真正用于模型实跑，而不是只做 ignore / loader 单测。

原先的问题是：`secrets.txt` 里是“裸 base URL + 裸 sk key”的形式，旧版 `load_secret_file()` 只会识别裸 key，不会把裸 URL 识别成 `OPENAI_BASE_URL`。所以第一次请求打到了默认 OpenAI 地址，返回了 `invalid_api_key`。

现在已经修正为：

```text
裸 http(s) URL -> OPENAI_BASE_URL
裸 sk-* key    -> OPENAI_API_KEY
```

同时保留原来的安全语义：URL 不会被误判成 API key。

对应变更：

- `src/vibe_research/secrets.py`
- `tests/test_harness_hermes.py`

## 2. 真实模型实跑结果

### 2.1 API 连通性

命令：

```bash
python scripts/smoke_openai_response.py --model gpt-5.4
```

结果：

```json
{
  "model": "gpt-5.4",
  "text": "OK"
}
```

说明：`secrets.txt` 里的 base URL 和 key 已经能成功调用 OpenAI-compatible Responses API。

### 2.2 LLM-driven Harness x Hermes agent smoke

新增脚本：

```text
scripts/smoke_llm_agent_runtime.py
```

命令：

```bash
python scripts/smoke_llm_agent_runtime.py \
  --model gpt-5.4 \
  --output-dir /Users/yishuoyan/projects/frontier-ai/vibe-research/yys/all/0802
```

这不是简单 ping API，而是让真实模型进入一个最小 agent loop：

```text
LLM planning brain
  -> 输出 tool call JSON
  -> Harness 检查 policy / effect / budget / approval
  -> Hermes checkpoint
  -> 执行 READ tool
  -> LLM 再选择 EXECUTE tool
  -> Harness 触发 approval pause
  -> Hermes resume
  -> 执行 tool
  -> TraceEnvelope / EvidenceReceipt 落盘
  -> MemoryCommitProtocol commit
  -> HydrationManifest verify
  -> LLM 输出最终判断
```

本次实跑摘要：

| 项 | 结果 |
|---|---:|
| ready | true |
| model | gpt-5.4 |
| LLM calls | 3 |
| JSON tool parse success | 2 / 2 |
| selected tools | `scan_fse_position`, `design_fse_experiment` |
| approval pause observed | true |
| final runtime status | ready |
| checkpoint ref | `task_03da3de1193b/ckpt_000004.json` |
| trace events | 5 |
| trace envelopes | 5 |
| evidence receipts | 5 |
| artifacts | 2 |
| committed memory | `belief-llm-fse-next-step` |
| hydration safe | true |

产物：

- `yys/all/0802/llm_agent_smoke_report.json`
- `yys/all/0802/llm_agent_smoke_summary.md`

### 2.3 这次效果如何

效果是正向的，但要明确它还是 smoke，不是主实验。

正向信号：

1. 模型能按约束输出工具调用 JSON，没有跑飞到自由文本。
2. 模型第一步选择 READ evidence scan，第二步选择 experiment design，决策顺序合理。
3. `EXECUTE` effect 被 Harness 正确拦截，进入 approval pause。
4. Hermes 能从 checkpoint 恢复 pending tool call 并继续执行。
5. TraceEnvelope / evidence receipt / memory commit / hydration verify 都能串起来。
6. 模型最终判断没有吹过头，明确指出“不能声称已跑真实 SWE-bench Docker”，并把下一步压到 5-10 个 SWE-bench Verified 小子集。

局限：

1. 这次 tool 是本地 deterministic smoke tool，不是真实 SWE-bench Docker execution。
2. 它验证的是“真实模型能驱动 runtime 控制闭环”，不是验证 agent 解决真实 issue 的能力。
3. 当前输出更像 pilot evidence，FSE 主实验还必须接真实任务、真实 oracle、真实 baseline。

一句话判断：

```text
现在已经从“runtime 原型可测”推进到“真实 LLM 可以进入 Harness x Hermes 闭环”，
但还没有到“真实 SE benchmark empirical result 足以投稿”的阶段。
```

### 2.4 最新补强：官方 SWE-bench execution ingest

这轮还补上了官方执行结果的 ingest / audit / hydration contract。

新增：

- `SweBenchOfficialExecutionIngestor`
- `official_execution_ingest_report.json`
- `official_execution_evidence_ledger.json`
- `official_execution_hydration_manifest.json`
- `official_execution_hydration_report.json`

它不替代 Docker，而是专门接住官方 harness 的：

- `results.json`
- `instance_results.jsonl`
- `run_logs/`

然后把它们收束成 evidence / hydration / replay-ready 产物。这个接口对 FSE 很关键，因为官方 benchmark 的结果如果不能被审计和复水，就还是“跑完了一个脚本”，不是“可投稿的实验资产”。

## 3. 当前项目总体状态

全量测试：

```bash
python -m pytest -q
```

结果：

```text
67 passed
```

Runtime verifier：

```bash
python scripts/verify_runtime.py
```

关键结果：

- final_status: `ready`
- compaction_safe_to_resume: `true`
- hydration_manifest_safe_to_hydrate: `true`
- evidence_ledger_sound: `true`
- memory_safety_gate_safe: `true`
- permission_external_allowed: `true`
- paused_before_approval: `true`
- fse_benchmark_ready: `true`
- fse_local_runner_ready: `true`
- fse_benchmark_fault_count: `16`
- fse_benchmark_experiment_cell_count: `152`
- fse_benchmark_trace_fault_detected_count: `122`
- fse_benchmark_trace_evidence_drift_detected_count: `70`

FSE benchmark verifier：

```bash
python scripts/verify_fse_benchmark.py
```

关键结果：

- ready_for_fse: `true`
- ready_for_runner: `true`
- ready_for_synthetic_trace: `true`
- ready_for_local_runner: `true`
- ready_for_swebench_adapter: `true`
- ready_for_swebench_executor: `true`
- ready_for_swebench_official_subset: `true`
- ready_for_swebench_official_execution_ingest: `true`
- failures: `[]`
- warnings: `[]`

当前 benchmark scaffold：

| 维度 | 数量 |
|---|---:|
| task families | 3 |
| baselines | 5 |
| fault scenarios | 16 |
| ablations | 7 |
| metrics | 23 |
| RQs | 4 |
| related-work clusters | 8 |
| synthetic experiment cells | 152 |

三类 task family：

- issue-to-patch
- artifact replication
- incident RCA

## 4. 当前最稳的三个创新点

### 创新点 1：Hydratable Scene，而不是 transcript checkpoint

核心句子：

```text
Long-horizon agents should dehydrate and hydrate verifiable execution scenes,
not raw conversation histories.
```

当前实现对应：

- `RuntimeState`
- `HermesRuntime`
- `HydrationManifest`
- `CompactionVerifier`
- `ResearchSession`
- `ProcessLifecycleVerifier`
- `EvidenceLedger`

FSE 价值：

- 对齐 software traceability / dependability / program comprehension / tools and environments。
- 可以量化 resume correctness、state reconstruction accuracy、context pin recall。

### 创新点 2：Evidence-Governed Memory Commit

核心句子：

```text
Agent memory should be treated as a governed software artifact with
staging, validation, commit, provenance, and retraction semantics.
```

当前实现对应：

- `MemoryCommitProtocol`
- `ValidationReceipt`
- `DecisionMemoryProjection`
- `EvidenceLedger`
- `ResearchPhaseGate.required_evidence_claim_ids`

FSE 价值：

- 把 memory pollution 变成 SE 里的 state consistency / provenance / artifact lifecycle 问题。
- 可以量化 invalid memory commit rate、unsupported claim rate、memory interference block rate。

### 创新点 3：Evidence-Retaining Replay Diagnosis

核心句子：

```text
Long-horizon agent failures can be localized and reproduced by lifting
trace envelopes into governed transition graphs while retaining evidence-scene receipts.
```

当前实现对应：

- `TraceEnvelope`
- `TraceEnvelope.evidence_ledger_fingerprint`
- `TraceEnvelope.evidence_claim_ids`
- `InterventionReplayWorkbench`
- `TransitionGraph`
- `HarnessDiagnosticWorkbench`
- `ObligationAuditMap`
- `ResearchSessionAuditBridge`

FSE 价值：

- 对齐 debugging / fault localization / replay / software traceability。
- 可以量化 replay fidelity、evidence drift detection、fault localization MRR、claim-preserving replay fidelity。

## 5. 现在最该补的实验

真实模型 smoke 已经证明 runtime 闭环能跑。下一步不要继续只扩文档，应该把真实 empirical evidence 拉起来。

优先级最高：

```text
SWE-bench Verified small subset
  -> official subset bridge
  -> predictions JSONL
  -> official Docker harness execution
  -> oracle/provenance audit
  -> evidence-retaining replay report
```

建议先做 5-10 个实例，不要一上来贪全量。

需要产出的报告：

- `official_subset_manifest.json`
- `official_predictions.jsonl`
- `official_harness_command.txt`
- Docker execution report
- `oracle_audit_report.json`
- hydration report
- evidence ledger report
- replay diagnosis report

主实验的最小对照：

- transcript-only / raw ReAct
- checkpoint-only
- LangGraph-style
- OpenHands-style
- AgentDiet-style
- Hermes full
- no-hydration / no-memory / no-evidence / no-trace ablations

### 5.1 本轮新增：顶会对标审计 gate

后续 benchmark verifier 现在会额外输出：

```text
ready_for_top_conference_positioning = true
ready_for_artifact_smoke = true
ready_for_submission_empirics = false
empirical_maturity_level = L3_official_ingest_contract_smoke
```

这层 gate 的作用是把 “FSE 叙事和 artifact smoke 已经成型” 与 “真实投稿实证已经足够” 分开。当前缺口被明确记录为：

- 还需要跑至少 5 个 SWE-bench Verified official Docker instances；
- 还需要接入至少 1 个真实 paper artifact replication package。

本轮 artifact-package smoke 输出见：

- `yys/all/0802/fse_artifact_smoke/reports/top_conference_alignment_report.json`
- `yys/all/0802/fse_artifact_smoke/reports/summary.json`
- `yys/all/0802/fse_artifact_smoke/reports/swebench_official_docker_preflight_report.json`
- `yys/all/0802/fse_artifact_smoke/reports/real_artifact_replication_report.json`
- `yys/all/0802/fse_artifact_smoke/reports/real_experiment_slice_plan.json`
- `yys/all/0802/FSE顶会对标审计与Benchmark迭代.md`

本轮还修了一个 benchmark 可信度问题：`git apply` 在嵌套 workspace 内可能向上发现父仓库并跳过 patch，但返回码仍为 0。现在 `SweBenchLocalPatchExecutor` 会隔离父仓库并校验 patch 后 workspace fingerprint，防止 regression test 没真正进入工作区却被当成通过。

同时，真实 artifact replication 也有了 manifest-driven 入口：

```bash
python scripts/run_fse_local_benchmark.py \
  --output-dir yys/all/0802/fse_artifact_smoke \
  --real-artifact-manifest /path/to/real_artifact_manifest.json
```

模板见：

- `yys/all/0802/real_artifact_replication_manifest_template.json`

官方 SWE-bench Docker run 也有了 preflight：

```bash
python scripts/preflight_swebench_official.py \
  --official-subset-report yys/all/0802/fse_artifact_smoke/reports/swebench_official_subset_report.json
```

当前机器结果：

```text
docker_available = false
swebench_module_available = false
ready_for_swebench_official_docker_run = false
```

也就是说：official subset / predictions / command 已经准备好，但还不能声称官方 Docker 实验已跑。

同一任务 ablation 也有了机器可读计划：

```text
hermes_full
no_hydration_manifest
no_memory_commit
no_trace_receipt
```

计划文件：

- `yys/all/0802/fse_artifact_smoke/reports/real_experiment_slice_plan.json`

## 6. 当前投稿判断

我认为 FSE 2027 仍然是最匹配目标。

但论文叙事必须死守这条线：

```text
不是：we built an agent framework
而是：we identify and evaluate runtime support required for long-horizon SE agents
```

现在的成熟度：

```text
设计主线：强
代码原型：已可测
真实 LLM runtime smoke：已跑通
benchmark scaffold：完整
artifact package smoke：已有
真实 SWE-bench / Docker empirical evidence：下一步核心缺口
```

如果后面 2-3 周能把真实 SWE-bench Verified small subset + official Docker execution + oracle audit 跑起来，这个方向就会从“很像 FSE”变成“真的能按 FSE Research Track 写”。

## 7. 本轮文件变化

新增：

- `scripts/smoke_llm_agent_runtime.py`
- `scripts/run_fse_local_benchmark.py`
- `scripts/verify_fse_benchmark.py`
- `scripts/preflight_swebench_official.py`
- `src/vibe_research/artifact_replication.py`
- `src/vibe_research/fse_alignment.py`
- `src/vibe_research/real_experiment_plan.py`
- `src/vibe_research/swebench_preflight.py`
- `yys/all/0802/llm_agent_smoke_report.json`
- `yys/all/0802/llm_agent_smoke_summary.md`
- `yys/all/0802/当前进度-LLM实跑与FSE对标.md`
- `yys/all/0802/FSE顶会对标审计与Benchmark迭代.md`
- `yys/all/0802/real_artifact_replication_manifest_template.json`
- `yys/all/0802/fse_artifact_smoke/reports/top_conference_alignment_report.json`
- `yys/all/0802/fse_artifact_smoke/reports/swebench_official_docker_preflight_report.json`
- `yys/all/0802/fse_artifact_smoke/reports/real_artifact_replication_report.json`
- `yys/all/0802/fse_artifact_smoke/reports/real_experiment_slice_plan.json`
- `yys/all/0802/fse_artifact_smoke/reports/summary.json`

修改：

- `src/vibe_research/secrets.py`
- `src/vibe_research/swebench_adapter.py`
- `src/vibe_research/__init__.py`
- `scripts/run_fse_local_benchmark.py`
- `scripts/verify_fse_benchmark.py`
- `tests/test_fse_benchmark.py`
- `tests/test_fse_artifact_cli.py`
- `tests/test_artifact_replication.py`
- `tests/test_real_experiment_plan.py`
- `tests/test_harness_hermes.py`
- `doc/research-log-2026-08-02.md`
- `yys/投稿/fse-2027-vibe-research-plan.md`

验证：

- `python scripts/smoke_openai_response.py --model gpt-5.4` -> OK
- `python scripts/smoke_llm_agent_runtime.py --model gpt-5.4 --output-dir yys/all/0802` -> ready true
- `python scripts/verify_runtime.py` -> ready
- `python scripts/verify_fse_benchmark.py` -> positioning ready / artifact smoke ready / submission empirics false
- `python scripts/run_fse_local_benchmark.py --output-dir yys/all/0802/fse_artifact_smoke` -> ready true
- `python scripts/preflight_swebench_official.py --official-subset-report yys/all/0802/fse_artifact_smoke/reports/swebench_official_subset_report.json` -> exit 1, because Docker/SWE-bench are missing
- `python -m pytest -q` -> 67 passed
