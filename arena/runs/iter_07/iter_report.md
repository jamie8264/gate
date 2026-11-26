# iter_07 — 趋势校正与自适应调度（release/v2）
**量化假设**：消除当前位置滞后 + 自适应单/双指令，使 val normal/corr SR≥0.60、S≥60。
**改动**：`predictors/base.py:_current_value()`；planner 用趋势校正 x、错过窗口立即发令；config strategy=adaptive（cadence 11–20 s 单指令）。
**指标**：val normal SR=0.6429、S=62.43、位置RMSE=9.32 mm、运动 0.95 次、相遇 2.10 s；holdout SR=0.7048；val fast SR=0.7628；val event_heavy SR=0.6048；dev white SR=0.8714。
**验证**：`DEV_SEEDS='1 2 3 4 5' VAL_SEEDS='101 ... 105' HOLDOUT_SEEDS='9001 ... 9010' bash tools/run_all.sh` → `tools/aggregate_report.md`；最终代码因果测试 passed；`python tools/validate_release.py` PASSED；release/v2 内 pytest 5+5 passed。
**结论**：假设成立；release/v2 晋级，v1 保留回滚。
