vibe-research 项目最终建议总结

一、总体结论

这个方向是值得做的，而且方向判断非常前沿。

相比传统：

* RAG Assistant
* Multi-Agent Demo
* AI Chatbot

vibe-research 已经进入：

* Agent Runtime
* Harness Engineering
* Persistent AI Agent
* AI Scientist Infrastructure

这一层。

尤其是：

* LangGraph Checkpoint/Rehydration
* MCP Tool Runtime
* Harness Governance
* Eval-driven Evolution
* Persistent Research Memory

这些概念，本质上已经非常接近：

* OpenAI Deep Research
* Claude Research
* Hermes Agent
* Sakana AI Scientist

这一代系统的设计思想。

从“简历价值”和“技术成长”角度，这个项目远强于普通 AI 应用项目。

⸻

二、项目真正应该聚焦的核心

当前最大的风险：

不是技术做不出来。

而是：

Scope Explosion（范围爆炸）

即：

什么都想做：

* KG
* Self-Evolution
* Memory
* Agent
* Replay
* Sandbox
* Eval
* Workflow
* MCP
* RAG

最后每个都浅。

⸻

真正正确的路线应该是：

把项目定位成：

「Persistent Research Runtime」

而不是：
“AI 科研平台”。

核心重点：

Research Task
→ Tool Execution
→ Experiment Tracking
→ Eval
→ Replay
→ Memory Consolidation

只把这一条链路做深。

⸻

三、我最推荐的最终定位

不要强调：

* AI 会读论文
* AI 自动总结
* AI 帮你科研

这些已经太泛滥。

⸻

真正应该强调：

“支持长期科研任务的 Agent Runtime Infrastructure”

即：

支持科研任务跨天/跨周持续执行、
断点恢复、
实验回放、
研究记忆沉淀、
自动化评测、
技能演进

这个才是真正高级的点。

⸻

四、最值得保留的核心卖点（强烈推荐）

1. Rehydration（断点恢复）

这是非常强的 Infra 点。

因为大部分 Agent：

* 页面刷新就死
* 无状态
* 无法跨周运行

而你：

Persistent Runtime

这是高级 Runtime 思维。

但必须做到：

* deterministic recovery
* state consistency
* replayability

否则只是“恢复聊天记录”。

⸻

2. Harness Governance（强烈建议保留）

这是整个项目最有 Infra 味道的地方。

建议：

不要只做：

* token budget
* safety guardrail

而是：

Runtime Governance System

包括：

* execution timeout
* retry policy
* sandbox quota
* tool permission
* failure attribution
* trace replay
* eval regression

这会非常像真正 Infra。

⸻

3. Experiment Lineage（强烈建议新增）

这是目前项目里最缺失但最关键的一层。

建议增加：

Experiment DAG / Lineage System

记录：

* dataset
* model
* prompt
* toolchain
* env
* metrics
* git commit
* sandbox snapshot

形成：

Research Lineage Graph

这是 AI Scientist 系统真正重要的部分。

⸻

五、目前最大的技术风险

风险 1：Memory 失控（最大风险）

目前：

* Neo4j
* Graph Memory
* Consolidation

这些都很危险。

因为：

长期 Memory 很容易变成垃圾堆。

⸻

建议：

Memory 必须分层：

Episodic Memory

短期实验经历

Semantic Memory

稳定知识

Procedural Memory

工具技能与 workflow

Working Memory

当前 Runtime 上下文

不要全部塞进 Neo4j。

⸻

风险 2：State Explosion

目前 Runtime State 太重。

不要把：

* 全量 history
* eval reports
* trace
* messages

全部放进 LangGraph state。

⸻

正确方式：

Runtime State 只保留：

* execution cursor
* active task
* resumable refs

大对象全部外置存储。

⸻

风险 3：Self-Evolution 容易翻车

自动 Prompt Rewrite 风险极高。

容易：

* reward hacking
* eval overfitting
* prompt drift

⸻

建议：

不要：

自动修改 Prompt

而是：

Skill Distillation

即：

从成功轨迹中提炼：

* tool sequence
* retrieval pattern
* workflow strategy

形成可复用 Skill。

这是更稳定、更 Infra 的做法。

⸻

六、真正推荐的 MVP（非常重要）

不要一开始做：

* Neo4j
* Auto Evolution
* Multi-Agent Society
* Auto Reviewer

这些都会爆炸。

⸻

真正推荐的 MVP：

第一阶段（最小闭环）

实现：

Research Task
→ MCP Tool Execution
→ Sandbox Run
→ Checkpoint
→ Replay
→ Eval

只做这一条链路。

⸻

MVP 技术栈（推荐）

Runtime

* LangGraph

Tool Layer

* MCP

Sandbox

* Daytona / Docker

Storage

* PostgreSQL

Trace

* Langfuse

Retrieval

* Qdrant

先不要 Neo4j。

⸻

七、Neo4j 建议（非常重要）

我强烈建议：

Neo4j 不要 MVP 就做。

原因：

Graph Memory：

* 工程复杂
* 清洗复杂
* alignment 极难
* 漂移严重

而且：

对 MVP 的价值并不大。

⸻

建议：

第一阶段：

只做：

* vector retrieval
* structured metadata
* experiment lineage

⸻

第二阶段：

再逐步：

* graph extraction
* entity canonicalization
* topology reasoning

否则一定失控。

⸻

八、最终推荐路线（最合理）

Phase 1（核心）

Persistent Runtime MVP

实现：

* LangGraph checkpoint
* Rehydration
* MCP sandbox
* Experiment tracking
* Replay
* Harness governance

这是最重要的。

⸻

Phase 2（增强）

加入：

* Experiment lineage
* Semantic memory
* Retrieval memory
* Skill library

⸻

Phase 3（高级）

最后再做：

* Neo4j graph memory
* consolidation pipeline
* evaluator ensemble
* self-improving skill evolution

⸻

九、最终推荐（结论）

这个项目值得做。

而且：

很适合你当前背景。

因为你已经有：

* 多模态
* Benchmark
* CVPR
* Agent
* 数据生产
* Eval

所以：
这个方向会显得非常真实，而不是“跟风 Agent Demo”。

⸻

但一定不要：

一开始就做“AI Scientist 全家桶”。

真正正确的做法：

先做：

“Persistent Research Runtime”

然后逐渐演化。

⸻

十、我认为这个项目真正的核心价值

不是：

AI 帮你读论文

而是：

“让 Agent 具备长期科研执行能力”

即：

* 长周期状态保持
* 实验轨迹治理
* Runtime 恢复
* 工具编排
* Eval 驱动优化
* 研究记忆沉淀

这个方向非常像真正的：

AI Operating System / AI Scientist Runtime

长期价值很高。