# iter_03 — 调参与 51 例矩阵
**量化假设**：共享链速 + 去掉加速度外推使验证集主 SR 提升 ≥0.05。
**改动**：`DPB/config/default.yaml`：shared_weight=1.0、accel_kappa=0.0、global_weight=0.0；新增 `tools/run_all.sh`、`tools/aggregate.py`。
**指标**：seed1 0.410→0.487（+0.077）；val normal/corr 5 例 SR=0.4872、S=39.66；dev 7 场景 SR 0.108–0.705；fast val SR=0.800；event_heavy val SR=0.364。
**验证**：`DEV_SEEDS='1 2 3 4 5' VAL_SEEDS='101 102 103 104 105' bash tools/run_all.sh`；`tools/aggregate_report.md` / `.json`；51 份 eval_report.json。
**结论**：假设成立；B3（调参后）晋级候选。
