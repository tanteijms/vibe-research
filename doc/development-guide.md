# vibe-research 开发指南

> 目标：围绕 `harness + hermes + self-evo + skill`，构建一个支持长期科研任务的持久化 Agent Runtime。

## 1. 设计目标

这个项目要解决的不是“能不能问答”，而是“能不能长期稳定做研究任务”。

核心能力：

- 长期运行
- 可恢复
- 可回放
- 可治理
- 可评测
- 可演进

## 2. 总体原则

- 先做最小闭环，再扩展
- 先做治理，再做能力
- 先做 replay，再做自进化
- 先做 skill 固化，再做 prompt 自动化
- 先做结构化轨迹，再做知识图谱

## 3. 模块总览

### 3.1 Harness

职责：控制运行风险和资源消耗。

功能点：

- token 预算
- cost 预算
- tool 权限
- 超时控制
- 重试策略
- sandbox 限额
- failure attribution
- trace 审计

### 3.2 Hermes

职责：让 agent 能跨 session 持续做事。

功能点：

- checkpoint
- rehydration
- resume
- 人工干预后继续执行
- 任务状态继承

### 3.3 Self-Evo

职责：从运行轨迹中提炼更好的策略。

功能点：

- 成功轨迹挖掘
- 失败轨迹归因
- skill 候选生成
- eval 回归
- 版本晋升

### 3.4 Skill

职责：把稳定成功模式沉淀为可复用策略包。

功能点：

- 论文扫描
- 相关工作梳理
- 实验计划生成
- baseline 复现
- debug 分析
- 结果撰写

## 4. 推荐仓库结构

```text
vibe-research/
├── src/
│   ├── agents/
│   ├── eval/
│   ├── harness/
│   ├── mcp/
│   ├── skills/
│   ├── graph.py
│   └── schema.py
├── tests/
│   ├── harness_eval/
│   ├── replay/
│   └── skills/
└── doc/
    ├── idea.md
    ├── tips.md
    ├── development-guide.md
    └── modules/
```

## 5. 模块开发顺序

### Phase 1: Runtime 骨架

- 定义 state
- 实现 graph
- 接入最小 MCP 工具
- 设计 harness policy
- 支持 checkpoint/replay

### Phase 2: 研究执行

- 论文阅读
- 实验执行
- artifact 记录
- lineage 追踪

### Phase 3: Skill 化

- 从成功轨迹提炼 skill
- skill registry
- skill 评测

### Phase 4: Self-Evo

- 自动生成 skill 候选
- regression 驱动晋升
- 失败轨迹反哺策略

## 6. 开源组件建议

优先复用：

- `LangGraph` 负责 runtime 编排
- `MCP` 负责 tool 协议
- `Docker` 或 `Daytona` 负责 sandbox
- `PostgreSQL` 负责结构化状态
- `Langfuse` 负责 trace
- `Qdrant` 负责检索
- `promptfoo` 风格评测框架负责 regression

不建议 MVP 就上：

- `Neo4j`
- 大而全的多智能体框架
- 自动 prompt rewrite

## 7. 分支策略

建议使用以下分支类型：

- `main`：稳定版本
- `feature/*`：新功能
- `experiment/*`：探索性实现
- `eval/*`：评测集与回归
- `docs/*`：文档改动

示例：

- `feature/harness-budget`
- `feature/mcp-tools`
- `feature/checkpoint-replay`
- `experiment/hermes-loop`
- `experiment/skill-mining`
- `eval/tool-routing`
- `docs/runtime-design`

合并原则：

- feature 必须先有最小 eval
- experiment 不直接进 main
- docs 和代码可以分开迭代

## 8. 里程碑

### M1

跑通一条链路：

`task -> tool -> sandbox -> checkpoint -> replay -> eval`

### M2

支持长期任务：

- session 持久化
- artifact 管理
- 任务中断恢复

### M3

支持 skill：

- 轨迹提炼
- skill registry
- skill 回归测试

### M4

支持 self-evo：

- 自动生成候选 skill
- eval 通过后晋升
- 失败轨迹反哺

## 9. 终极原则

- 先让系统活着，再让它变聪明
- 先让任务可恢复，再让任务可优化
- 先让 skill 稳定，再让 self-evo 自动化

## 10. 2026 Harness 迭代补充

结合最近的 OpenAI / DeepSeek 方向，Harness 的重点建议再往前推一层：

- 不只管 budget / sandbox，还要管 provider capability
- 不只管执行成功，还要管 trace 能不能 replay 和 grade
- 不只管 resume 状态，还要管 pending approval、policy snapshot 和 artifact refs
- 不只管单次 tool 调用，还要把成功轨迹沉淀成 skill 和 regression case

对应的落地笔记可参考 `doc/harness-x-hermes-2026.md`。
