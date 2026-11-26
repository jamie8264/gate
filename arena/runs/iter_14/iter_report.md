# iter_14 — yaw 后速度窗口复测
**假设**：窗口 1.5 s 使 val normal SR 再提升 ≥0.02。
**指标**：dev normal 0.8667（+0.019）、val normal 0.8381（+0.0048）、dev angle 0.3286（+0.0048）；1.0/3.0 代表种子更差。
**验证**：`config/exp_vw1.0_yaw.yaml`、`config/exp_vw1.5_yaw.yaml`、`config/exp_vw3.0_yaw.yaml`；CLI 输出目录已清理。
**结论**：不晋级，保持 release/v3。
