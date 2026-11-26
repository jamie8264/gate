# release/v2 — 晋级记录（替代 v1）

- 时间：2026-11-26 04:56 UTC（R7）
- 关键修复：DPB 预测使用趋势校正的当前位置（消除 0.15 s 中位数滞后造成的 7–12 mm 系统偏差）；规划器在错过工位窗口后立即发指令（修复 fast 场景）；评估口径把无指令/无法插值的挂钩计为失败；自适应调度（cadence 11–20 s 单指令，其余双指令）；θ 在线 τ 估计修正（用 rx/rz 而非 ry）。
- schema：schema_v1；DPA config_hash=e573064647d3；DPB config_hash=8ef3820d670c
- 单案例（seed1 normal/correlated）：SR=0.7143，S=69.56，posRMSE=9.97 mm，angRMSE=2.24 deg
- 达成分母：计入链速 OU 的主档完美预测上限 0.886，达成率 0.806
- 门槛：DPA pytest 5 passed；DPB pytest 5 passed；因果测试 passed；dev/val/holdout 报告见 `../../tools/aggregate_report.md`
- v1 保留作回滚；v2 综合分与 SR 均不低于 v1。
