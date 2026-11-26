# iter_06 — 评估口径与理论上限
**量化假设**：把不可评估挂钩计入失败后，SR 会下降但结论更可靠；计入链速 OU 后主档上限约 0.89。
**改动**：evaluator 分母修复、DPA export_margin=600、theory.speed_forecast_sigma、aggregate 用诚实达成率、τ 列索引修复。
**指标**：val normal SR 0.487→0.452（旧策略、严口径）；seed1 含链速上限 0.886；τ̂ 从 0.3 s 恢复到约 1 s。
**验证**：`tools/run_all_v3.log`、`tools/aggregate_report.md`、各 eval_report.json 的 theory 段。
**结论**：假设成立；为 R7 误差源定位提供了可靠口径。
