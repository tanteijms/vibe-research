# vibe-research 设计与开发指南

> 目标：把 `vibe-research` 做成一个面向长期科研任务的 `Persistent Research Runtime`，核心组合是 `harness + hermes + self-evo + skill`。

## 1. 项目定位

`vibe-research` 不是普通聊天机器人，也不是一次性的 RAG demo。它要解决的是长期科研任务在跨天、跨周执行时的状态保持、工具治理、实验追踪、回放和演进。

核心目标：

- 持久化运行：支持 checkpoint / rehydration / replay
- 工具治理：支持权限、预算、超时、失败归因、审计
- 研究执行：支持论文阅读、实验运行、代码调试、结果总结
- 自我演进：从成功轨迹中蒸馏 skill，而不是直接自动改 prompt

## 2. 总体架构

建议按四层设计：

### 2.1 Harness Layer

负责“运行时治理”。

功能点：

- token / cost budget
- tool permission
- timeout / retry policy
- sandbox quota
- output sanitization
- failure attribution
- trace replay

### 2.2 Hermes Layer

负责“长时任务 agent 形态”。

功能点：

- session 持久化
- checkpoint / resume
- 多轮任务分解
- 人类插话后继续执行
- 跨任务上下文继承

### 2.3 Self-Evo Layer

负责“从轨迹中学习”。

功能点：

- 失败轨迹归因
- 成功轨迹提炼
- prompt / strategy / tool sequence 版本化
- eval regression
- skill candidate 生成

### 2.4 Skill Layer

负责“可复用策略包”。

建议把 skill 定义成：

- 适用场景
- 输入输出契约
- 推荐工具序列
- 失败回退策略
- 评测标准

## 3. 模块划分

### 3.1 `src/schema.py`

Runtime state 的最小定义。

只放轻量字段：

- `task_id`
- `execution_cursor`
- `active_step`
- `budget_state`
- `checkpoint_ref`
- `artifact_refs`
- `trace_id`

不要放：

- 全量 history
- 大段推理过程
- 原始实验日志
- 大文件内容

### 3.2 `src/graph.py`

LangGraph 主流程编排。

推荐节点：

- intake
- plan
- route_tool
- execute_tool
- observe
- checkpoint
- eval
- decide_continue

### 3.3 `src/harness/`

建议拆成这些子模块：

- `budget.py`
- `policy.py`
- `sandbox.py`
- `checkpoint.py`
- `replay.py`
- `audit.py`

### 3.4 `src/mcp/`

MCP 接入层。

优先支持的能力：

- 文件读写
- 目录扫描
- shell/python 执行
- 搜索/检索
- artifact 导出

### 3.5 `src/agents/`

Agent 任务层。

建议先做：

- `research_agent`
- `paper_agent`
- `experiment_agent`
- `debug_agent`

### 3.6 `src/skills/`

Skill 仓库。

建议初版先有：

- `paper_scan`
- `related_work_map`
- `experiment_plan`
- `baseline_reproduce`
- `error_debug`
- `result_writeup`

### 3.7 `src/eval/`

评测与回归层。

建议覆盖：

- tool routing accuracy
- checkpoint recovery
- budget adherence
- replay consistency
- skill usefulness

## 4. 推荐开源栈

优先使用现成能力，不重复造轮子。

- Runtime: `LangGraph`
- Tool protocol: `MCP`
- Sandbox: `Docker` 或 `Daytona`
- Storage: `PostgreSQL`
- Trace: `Langfuse`
- Retrieval: `Qdrant`
- Eval: `promptfoo` / `OpenAI Evals` 风格自定义 harness

说明：

- `Neo4j` 不建议 MVP 就上
- 先做结构化元数据 + 向量检索 + lineage
- graph memory 放到后期

## 5. 功能路线图

### Phase 1: MVP Runtime

目标：跑通最小闭环。

链路：

`Research Task -> MCP Tool Execution -> Sandbox Run -> Checkpoint -> Replay -> Eval`

交付物：

- 状态 schema
- 主 graph
- harness 基础策略
- MCP 最小工具集
- checkpoint / replay
- 第一版 eval

### Phase 2: Persistent Research

目标：支持长期科研任务。

交付物：

- 任务分层
- artifact 管理
- experiment lineage
- retrieval memory
- skill registry

### Phase 3: Self-Evo

目标：从成功轨迹生成更好的执行策略。

交付物：

- skill distillation
- trace mining
- eval regression
- skill versioning
- candidate promotion

### Phase 4: Advanced Memory

目标：再考虑 graph memory。

交付物：

- entity canonicalization
- relation extraction
- knowledge graph
- consolidation pipeline

## 6. 开发规范

### 6.1 状态设计

原则：

- state 只保留“可恢复最小集”
- 大对象外置到 artifact store
- 每次节点执行都可复现

### 6.2 工具设计

原则：

- 每个工具都有明确 schema
- 每个工具都能审计
- 每个工具都能限额
- 每个工具都要有失败分支

### 6.3 Skill 设计

原则：

- 一个 skill 只解决一个稳定模式
- skill 必须可测
- skill 必须可回放
- skill 不能依赖隐式上下文

### 6.4 Self-Evo 设计

原则：

- 不直接自动 rewrite prompt
- 先做轨迹蒸馏
- 再做 skill 候选
- 最后由 eval 决定是否晋升

## 7. 分支策略

建议采用 `main + feature/* + experiment/* + eval/*`。

### 7.1 `main`

- 只保留稳定可运行版本
- 只合并通过 eval 的内容

### 7.2 `feature/*`

用于功能开发。

示例：

- `feature/harness-budget`
- `feature/mcp-tooling`
- `feature/checkpoint-replay`
- `feature/skill-registry`

### 7.3 `experiment/*`

用于探索性实现。

示例：

- `experiment/hermes-loop`
- `experiment/self-evo-skill-mining`
- `experiment/qdrant-memory`

### 7.4 `eval/*`

用于评测集和回归规则。

示例：

- `eval/tool-routing`
- `eval/replay-consistency`
- `eval/skill-promotion`

### 7.5 合并规则

- 先有 eval，再合并
- 先有 replay，再扩功能
- 先能恢复，再谈自进化

## 8. 仓库建议结构

```text
vibe-research/
├── src/
│   ├── agents/
│   ├── eval/
│   ├── harness/
│   ├── mcp/
│   ├── skills/
│   ├── schema.py
│   └── graph.py
├── tests/
│   ├── harness_eval/
│   ├── replay/
│   └── skills/
├── doc/
│   ├── tips.md
│   └── design/
└── README.md
```

## 9. 近期开发顺序

1. 先定 `state` 和 `graph`
2. 再做 `harness`
3. 再接 `MCP`
4. 再补 `checkpoint/replay`
5. 再做 `eval`
6. 再做 `skill`
7. 最后才做 `self-evo`

## 10. 最终原则

- 先做闭环，不做大而全
- 先做可恢复，不做炫技
- 先做可测，不做空想
- 先做 skill 固化，再做自进化
- 先做 harness，再做规模
