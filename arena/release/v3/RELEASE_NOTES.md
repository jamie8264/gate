# release/v3 — 2026-11-26 05:22 UTC

## 变更（相对 release/v2）
- 采纳 yaw 几何去相关：`DPB/config/default.yaml` 中 `use_attitude_decorrelation: true`（仅用名义杠杆 95 mm 与传感器 Rz 观测，不读 DPA truth）。
- 60 例官方矩阵（run_all_v5 同口径，追加 holdout 最终评测）平均：dev normal:corr SR=0.8476/S=83.15；val normal:corr SR=0.8333/S=81.69；holdout SR=0.8738/S=85.73；dev angle_sigma5 SR=0.3238（v2 为 0.1286）。
- 证据：`tools/aggregate_report_final.md/.json`、`DPB/outputs/seed_1_normal_correlated/eval_report.json`（SR=0.8571/S=84.13）、`causal_report.json`（passed=true）。

## 不变项
- DPB 预测器仍为 b3、策略 adaptive；schema_v1；truth 隔离；仿真参数未改。
- release/v2 保留回滚。
