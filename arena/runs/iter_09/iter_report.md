# iter_09 — full 模式 700 钩大样本评测
**量化假设**：full 700 钩主 SR 与 zone dev normal/corr（0.7524）差 ≤0.10。
**改动**：DPA `--mode full` + decimated full（10 Hz）夹具；不混入口径矩阵。
**指标**：DPA 700 钩/1,545,137 行/9025 s；DPB 700 tracks/700 cmds，SR=0.6771、S=65.69，差 0.075，假设成立。
**验证**：`DPA/outputs/full_seed_1/meta.json`、`DPB/outputs/full_seed_1_decimated_b3/eval_report.json`；命令见总纲 §7.6。
**结论**：full 模式向量化与 DPB 大样本闭环均通过；release/v2 保持。
