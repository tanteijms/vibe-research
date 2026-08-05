# Self-Evo 模块

## 职责

负责从轨迹中提炼更好的执行策略。

## 功能点

- 成功轨迹提炼
- 失败轨迹分析
- skill 候选生成
- eval 回归
- 晋升策略

## 接口建议

- `mine_success_trace`
- `classify_failure`
- `propose_skill`
- `run_regression`
- `promote_skill`

## 交付物

- 轨迹分析器
- 候选池
- 晋升规则

