# iter_13 — full 与跨接口复验
**量化假设**：yaw 去相关在 full 700 钩提升 SR ≥0.10，伪外部接口指标一致。
**指标**：full 700 钩 SR 0.6771→0.8000、S 65.69→78.11；cross_eval sr=0.8571/S=84.13，与原生 seed1 一致。
**验证**：`DPB/outputs/full_seed_1_decimated_v3/eval_report.json`、`/tmp/full_v3.log`、`/tmp/cross_v3.log`。
**结论**：release/v3 保持；继续 R14。
