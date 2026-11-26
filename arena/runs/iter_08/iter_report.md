# iter_08 — 交叉评测、SVG 校验与策略边界
**量化假设**：别名适配后 SR 与原生差 ≤0.01；边界策略不优于默认。
**改动**：仅增加实验配置 `config/exp_singleall.yaml`、`exp_entry250.yaml`、`exp_h205.yaml`、`exp_angle2cmd.yaml`；未改默认。
**指标**：交叉评测 SR=0.7143（原生 seed1=0.7143）；fast 单指令 seed1=0.6047 < adaptive 对应 0.6512；entry=-250 seed1=0.6905 < 0.7143；H=2.05 seed1=0.7143、seed101=0.5952 < 0.5238? 实测 seed101 0.5952 > 0.5238，单种子不显著，故未采纳；angle_sigma5 双指令 seed1=0.0476 < 0.1190。
**验证**：`tools/cross_eval.py --foreign /tmp/foreign_dpa2 --out DPB/outputs/cross_eval_final` → `cross_eval_summary.json`（清理输出目录后数值记于总纲 §7.4）；`node --check /tmp/anim.js` 通过；`tools/aggregate.py` → 60 例。
**结论**：适配器与 SVG 通过；默认 adaptive 策略保持；release/v2 不改动。
