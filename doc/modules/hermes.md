# Hermes 模块

## 职责

负责长期任务执行和状态恢复。

## 功能点

- checkpoint
- rehydration
- resume
- hydration manifest
- 多轮任务推进
- 人工插入后继续
- process lifecycle：active / waiting / suspended / archiving
- state ledger：长期状态项的 authority / scope / mutability / provenance / recoverability / actionability 审计
- research session：paper_scan / hypothesis / experiment / analysis / review / writeup 的 typed phase gate，支持 required evidence claim
- evidence ledger：source-backed claims、lineage、quarantine / retraction、claim citation

## 接口建议

- `save_checkpoint`
- `load_checkpoint`
- `build_hydration_manifest`
- `verify_hydration_manifest`
- `resume_task`
- `advance_cursor`
- `audit_process_lifecycle`
- `verify_research_session`
- `audit_evidence_ledger`

## 交付物

- 状态机
- checkpoint 存储
- 恢复流程
