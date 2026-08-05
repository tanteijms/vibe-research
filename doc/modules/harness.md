# Harness 模块

## 职责

负责治理运行时风险。

## 功能点

- 预算控制
- 权限控制
- 超时控制
- sandbox 控制
- 错误归因
- trace 审计
- replay 支持

## 接口建议

- `check_budget`
- `authorize_tool`
- `wrap_execution`
- `record_trace`
- `restore_checkpoint`

## 交付物

- policy 定义
- budget 计数器
- sandbox wrapper
- audit log

