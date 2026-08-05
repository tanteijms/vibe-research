# FSE 顶会对标审计与 Benchmark 迭代

> 日期：2026-08-02  
> 项目：`vibe-research`  
> 本轮目标：继续调研 FSE 顶会方向，把 “A 会标准难度” 落到可运行 benchmark / verifier / artifact package，而不是只写成论文叙事。

## 1. 本轮外部对标判断

FSE 近几年对 agentic SE 的口味已经很清楚：它不只关心 agent 最终能不能修 bug，而是关心 trajectory cost、execution boundary、privilege/tool use、failure attribution、RAG/evidence component、artifact reproducibility 和真实 oracle provenance。

这对 `vibe-research` 的启发是：

```text
不要投 another agent framework
要投 runtime support for long-horizon software-engineering agents
```

三条创新点继续收敛为：

1. **Hydratable Scene / Context Lifecycle Contract**  
   恢复的不是 transcript，而是带 active frame、policy/evidence/artifact pins、typed context block、authority boundary 的 execution scene。

2. **Evidence-Governed Memory and Data-Quality Commit**  
   memory commit 前必须过 validation receipt、evidence ledger、data-quality predicate，避免 stale metadata、silent evidence defect、unsupported claim 进入长期状态。

3. **Evidence-Retaining Replay Diagnosis**  
   trace envelope 不只保留 tool/action，还保留 evidence scene、oracle provenance、official execution receipts，并提升成 transition graph 做 failure attribution。

## 2. 新增 top-conference alignment audit

本轮新增了一个顶会审计层：

- `src/vibe_research/fse_alignment.py`
- `FseTopConferenceAlignmentAuditor`
- `FseTopConferenceAlignmentReport`

它故意把当前状态拆成三层：

| Gate | 当前值 | 解释 |
|---|---:|---|
| `ready_for_top_conference_positioning` | `true` | 叙事、RQ、baseline、fault、ablation、metric、related-work breadth 已经像 FSE。 |
| `ready_for_artifact_smoke` | `true` | benchmark / local artifacts / SWE-bench-style executor / official ingest contract 能跑。 |
| `ready_for_submission_empirics` | `false` | 还不能投稿级 claim，因为真实 official Docker benchmark 与真实 artifact replication 还没补齐。 |

当前 maturity level：

```text
L3_official_ingest_contract_smoke
```

这句话的含义很具体：我们已经能把 official-shaped SWE-bench 输出接进 evidence / hydration / replay contract，但还没有跑真实 SWE-bench Verified official Docker small subset。

## 3. 本轮 benchmark smoke

输出目录：

```text
yys/all/0802/fse_artifact_smoke/
```

关键产物：

- `reports/benchmark_plan.json`
- `reports/benchmark_matrix.json`
- `reports/synthetic_trace_report.json`
- `reports/local_run_report.json`
- `reports/swebench_executor_report.json`
- `reports/swebench_official_docker_preflight_report.json`
- `reports/swebench_official_execution_ingest_report.json`
- `reports/real_artifact_replication_report.json`
- `reports/real_experiment_slice_plan.json`
- `reports/top_conference_alignment_report.json`
- `reports/summary.json`

本轮命令：

```bash
python scripts/run_fse_local_benchmark.py \
  --output-dir /Users/yishuoyan/projects/frontier-ai/vibe-research/yys/all/0802/fse_artifact_smoke
```

摘要结果：

| 项 | 结果 |
|---|---:|
| ready | true |
| experiment cells | 152 |
| synthetic processed cells | 152 |
| synthetic fault detected | 122 |
| synthetic evidence drift detected | 70 |
| local toy tasks | 3 / 3 |
| local artifact count | 10 |
| local evidence claim count | 5 |
| local committed memory count | 3 |
| SWE-bench-style executor instances | 2 |
| SWE-bench-style tests passed | 1 |
| official Docker preflight ready | false |
| official execution ingest ready | true |
| real artifact replication ready | false |
| real experiment slice ready | false |
| same-task ablation variants | 4 |
| top-conference positioning | true |
| artifact smoke | true |
| submission empirics | false |

`submission empirics=false` 是正确且必要的：它提醒我们现在还不能把 smoke 包装成 FSE empirical result。

## 4. 本轮发现并修复的 benchmark 可信度问题

本轮在项目树内跑 artifact smoke 时发现一个很像真实 SE benchmark 会踩的坑：

```text
git apply 在嵌套 toy repo 内运行时，会向上发现父仓库 .git，
patch 可能被 skip，但返回码仍然是 0。
```

这会造成一个坏结果：

```text
test command passed
但 regression test 根本没有被 patch 进工作区
```

已修复：

- `SweBenchLocalPatchExecutor._apply_patch()` 设置 `GIT_CEILING_DIRECTORIES`，隔离父仓库；
- patch apply 后比较 workspace fingerprint；
- 如果返回码为 0 但 workspace 没变化，判定为 patch 未生效。

这个修复很关键，因为它直接支撑论文里 “oracle/provenance/execution receipts 必须验证 effect 真实发生” 这个观点。

## 5. 当前最该补的真实实验

下一轮不要继续扩 synthetic 为主，应该优先补真实任务证据：

1. **5-10 个 SWE-bench Verified official Docker instances**
   - 保存 `results.json`
   - 保存 `instance_results.jsonl`
   - 保存 `run_logs`
   - 通过 `SweBenchOfficialExecutionIngestor` 接回 evidence / hydration / replay contract

   本轮新增了 preflight：

   ```bash
   python scripts/preflight_swebench_official.py \
     --official-subset-report yys/all/0802/fse_artifact_smoke/reports/swebench_official_subset_report.json
   ```

   当前机器检查结果：

   ```text
   docker_available = false
   swebench_module_available = false
   ready_for_swebench_official_docker_run = false
   ```

2. **至少 1 个真实 artifact-replication package**
   - 替换 toy artifact replication
   - 报告 `unsupported_claim_rate`
   - 报告 `artifact_provenance_completeness`
   - 报告 `active_frame_retention`

   本轮已经新增 manifest-driven 入口：

   ```bash
   python scripts/run_fse_local_benchmark.py \
     --output-dir /path/to/out \
     --real-artifact-manifest /path/to/manifest.json
   ```

   模板见：

   ```text
   yys/all/0802/real_artifact_replication_manifest_template.json
   ```

3. **真实任务上的 same-task ablation**
   - `no_hydration_manifest`
   - `no_memory_commit`
   - `no_trace_receipt`

   本轮已经新增 `real_experiment_slice_plan.json`，固定四个变体：

   ```text
   hermes_full
   no_hydration_manifest
   no_memory_commit
   no_trace_receipt
   ```

   当前计划未 ready 的原因是：

   ```text
   docker command is not available
   Python module 'swebench' is not installed
   no real artifact replication manifest supplied
   ```

如果这三项跑通，这个方向就从 “FSE-shaped runtime prototype” 进入 “可以认真写 FSE Research Track empirical paper”。

## 6. 本轮验证

- `python -m pytest tests/test_fse_benchmark.py tests/test_fse_artifact_cli.py -q` -> 8 passed
- `python -m pytest tests/test_artifact_replication.py tests/test_fse_artifact_cli.py -q` -> 4 passed
- `python -m pytest tests/test_real_experiment_plan.py tests/test_fse_artifact_cli.py -q` -> 3 passed
- `python scripts/preflight_swebench_official.py --official-subset-report ...` -> preflight_exit=1 because Docker/SWE-bench package are missing
- `python scripts/verify_fse_benchmark.py` -> positioning ready / artifact smoke ready / submission empirics not ready
- `python scripts/run_fse_local_benchmark.py --output-dir ...` -> ready true
