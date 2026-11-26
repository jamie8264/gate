# iter_10 — 速度窗口消融
**量化假设**：速度窗口 1.0/1.5/3.0 s 相比当前 2.0 s 提升 normal 主达成率 >0.02。
**指标**：seed1 0.5714/0.7143/0.7143 vs 当前 0.7143；seed101 0.4762/0.5476/0.5714 vs 当前 0.6429；fast 0.4651/0.5814/0.5814 vs 当前 0.5814（双指令）。
**验证**：CLI 输出目录 `DPB/outputs/seed_*_vw*`；清理后 canonical 恢复，`tools/validate_release.py` → VALIDATION PASSED。
**结论**：拒绝晋级，保持 velocity_window_s=2.0。
