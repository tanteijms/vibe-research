# vibe-research 🧠🔬

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![Agent Infrastructure](https://img.shields.io/badge/Infra-Agent%20Runtime-red.svg)]()
[![Framework](https://img.shields.io/badge/Orchestration-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Protocol](https://img.shields.io/badge/Protocol-MCP-green.svg)](https://modelcontextprotocol.io)

> **Let humans vibe, while AI automates the science.** > `vibe-research` 是一款面向自动化科学研究的**持久化、自进化 Agent 运行时 (Persistent Agent Runtime)**。它彻底解耦了人类的"科研灵感 (Vibe)"与繁琐的"科研执行"。

---

## 🚀 项目愿景 (Vision)

当前的科研类 Agent 大多属于"无状态"的线性 RAG 管道（PDF 上传 -> 向量检索 -> 总结聊天）。在长达数月的科研周期中，它们无法累积实验经验、无法保持断点状态，更无法自我演进。

`vibe-research` 旨在重构这一范式，打造一个**有状态、带工程治理护栏（Harness Engineering）的硅基科学家 Runtime**：
1. **跨 Session 长效记忆**：不仅能读论文，还能将研究轨迹沉淀为动态研究知识图谱（Research KG）。
2. **确定性沙箱与流控**：利用 Harness 规约拦截高危代码，流控 Token/Cost 预算，避免 Agent 因陷入推理死循环而产生巨额账单。
3. **Eval 反馈自进化**：基于自动化 Peer Review 评测，动态优化 Prompt、检索和工具策略（借鉴 Hermes 思想），越用越聪明。

---

## 🏗️ 架构设计 (System Architecture)

`vibe-research` 的底层架构由三层核心驱动：

```text
       +--------------------------------------------------------+
       |             Human Researcher (Provides "Vibe")         |
       +----------------------------+---------------------------|
                                    | (High-level Guidance)
                                    ▼
+-----------------------------------------------------------------------+
| 1. HARNESS GOVERNANCE LAYER (安全、预算与流控拦截器)                     |
|    - [Token/Cost Guardrails] 拦截 Tool Call，超出预算自动"脱水"挂起    |
|    - [Secure Sandbox] 对接 MCP Server (Docker/Daytona Backend)        |
+-----------------------------------------------------------------------+
                                    | (Regulated State)
                                    ▼
+-----------------------------------------------------------------------+
| 2. PERSISTENT RUNTIME ENGINE (基于 LangGraph 的有状态编排)            |
|    - [State Hydration] 支持长周期中断与断点续传 (Checkpointer)         |
|    - [Sub-Agent Forking] 并行派发论文精读与代码 Debug 子任务            |
+-----------------------------------------------------------------------+
                                    | (Data Trajectory)
                                    ▼
+-----------------------------------------------------------------------+
| 3. EVOLUTIONARY MEMORY & EVAL LAYER (记忆合并与自演进闭环)             |
|    - [Memory Consolidation] 异步后台任务，将向量 RAG 提取升华为 Neo4j KG|
|    - [Continuous Regression Test] 自动化回归评测集驱动 Prompt 自调优    |
+-----------------------------------------------------------------------+

```

---

## 🗺️ 路线图与开发规划 (Roadmap)

我们采用敏捷迭代的方式，优先构建 **Infra 骨架（State & Harness）**，逐步演进至完全自动化的 AI Scientist。

### 2026 Harness 迭代

当前 Harness 方向不再只是预算和 sandbox，而是：

- `policy`：预算、权限、审批、超时、脱敏
- `trace`：每次 tool / sandbox / model 边界都可回放
- `provider`：OpenAI / DeepSeek 等模型能力差异被抽象成 capability profile
- `eval`：trace 直接转 regression case
- `intervention`：支持 fault injection / cached prefix / live suffix / mitigation replay
- `resume`：checkpoint 不只是状态快照，还携带 pending approval 和 provider snapshot
- `authority`：approval token 继续升级成 permission graph、authority witness 和 commit-time receipt
- `memory`：memory write 先 staged/validated，再 committed，避免错误事实直接进入长期记忆
- `transition`：state-changing trace 可以提升成 critical transition graph，定位失败关键链和分叉点
- `obligation`：多 agent transition 绑定 actor obligation、evidence link 和 assignment stability audit
- `decision-memory`：从 committed memory log 投影 task-conditioned 决策视图
- `compaction`：压缩后的 state 必须保留 policy pins、goal、process stage、artifact lineage 和 approval boundary
- `diagnosis`：replay divergence 映射到 transition unit、trace envelope drift、suspect harness surface 和 repair hint
- `trace-receipt`：TraceEnvelope 记录 evidence ledger fingerprint / claim ids / proof receipt，回放时能发现证据 scene 漂移
- `process-lifecycle`：always-on task 的 process stage 与 state ledger 六轴审计
- `research-session`：paper scan / hypothesis / experiment / analysis / review / writeup 的 typed phase gate，支持 required evidence claim
- `research-session-audit`：把 phase gate 绑定到 actor obligation、transition evidence 和 audit map
- `hydration-manifest`：把 state / trace / memory / evidence / artifact / policy 收束成可恢复现场
- `evidence-ledger`：source-backed claims、lineage、quarantine / retraction 和 claim citation
- `fse-benchmark`：把 issue-to-patch / artifact replication / incident RCA 三类任务、baseline、fault taxonomy、ablation 和 FSE RQ 结构化成可检查计划，并可展开成 synthetic experiment matrix、deterministic trace result report、local toy artifact run、SWE-bench-style patch/evidence adapter、local patch executor、official subset bridge 和 artifact-package smoke CLI

对应的详细迭代笔记见 [doc/harness-x-hermes-2026.md](doc/harness-x-hermes-2026.md)。

更偏工程落地的实现对照矩阵见 [doc/harness-implementation-matrix-2026.md](doc/harness-implementation-matrix-2026.md)。

持续追踪论文、协议和实现动态的 watchlist 见 [doc/research-watchlist-2026.md](doc/research-watchlist-2026.md)。

最近一轮带日期的调研增量见 [doc/research-log-2026-08-02.md](doc/research-log-2026-08-02.md)，重点是 permission graph、commit-time authorization、MCP lifecycle evidence、context compaction governance、checkpoint footprint 和 evidence ledger。

### 📅 Phase 1: MVP 骨架搭建 (当前阶段)

* [ ] **Core State Schema**: 实现支持系统脱水与复水（Dehydration/Rehydration）的全局状态总线、HydrationManifest 与证据账本 (`src/schema.py`)。
* [ ] **Harness Guardrail Router**: 编写 LangGraph 控制流，实现大模型调用前的 Token 计数器、费用超标熔断挂起器。
* [ ] **MCP Connection**: 接入 Model Context Protocol 协议，让 Agent 能够安全读写本地 Workspace 的文件及代码。

### 📅 Phase 2: 实验追踪与记忆升华 (Memory & Tracking)

* [ ] **Experiment Tracker**: 构建代码执行沙箱（Docker），拦截并结构化捕获代码运行指标、Loss 曲线及 Failure 堆栈。
* [ ] **Memory Consolidation Pipeline**: 编写定时 Cron 任务，增量对齐实验日志，向 Neo4j 拓扑图谱中插入"方法A 改进了 算法B 的 Loss 曲线"等强逻辑边。

### 📅 Phase 3: 闭环评测与自进化 (Harness Eval & Self-Improvement)

* [ ] **Harness Evaluator**: 建立 `tests/harness_eval` 自动化测试集（包含创新点提取一致性、Tool 路由准确度等 50 个基准测试 case）。
* [ ] **Auto-Tuning Loop**: 引入"虚拟审稿人（Virtual Reviewer）"评测反馈，当基准测试得分劣化时，触发 Prompt 自动重写与 Skill 固化。

---

## 🛠️ 快速开始 (Getting Started - For Contributors)

*(随着代码推进，此处将丰富运行指南)*

### 1. 克隆仓库

```bash
git clone [https://github.com/your-username/vibe-research.git](https://github.com/your-username/vibe-research.git)
cd vibe-research

```

### 2. 环境初始化

项目使用 Python 11+，推荐使用 `uv` 或 `poetry` 管理依赖：

```bash
pip install uv
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

```

### 3. 项目目录结构

```text
vibe-research/
├── src/
│   ├── __init__.py
│   ├── schema.py          # 核心有状态 Runtime 状态定义 (State Bus)
│   ├── graph.py           # LangGraph 状态机拓扑控制流
│   ├── harness/           # Harness 工程治理层 (流控、脱敏、沙箱拦截)
│   ├── memory/            # 记忆管理 (Neo4j Graph-RAG + Vector DB)
│   └── agents/            # 具体执行层 (Paper Agent, Experiment Agent)
├── tests/
│   └── harness_eval/      # 回归评测数据集与评测器
├── README.md
└── requirements.txt

```
