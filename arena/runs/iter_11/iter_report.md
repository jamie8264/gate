# iter_11 — yaw 几何去相关（release/v3）
**量化假设**：用传感器 Rz + 名义杠杆 95 mm 还原链速，val normal SR 相比 0.6429 提升 ≥0.10。
**改动**：`DPB/config/default.yaml` 的 `use_attitude_decorrelation: false → true`；schema_v1 不变。
**指标**：60 例报告 `tools/aggregate_report_final.md`：dev normal:corr SR=0.8476/S=83.15；val normal:corr SR=0.8333/S=81.69；dev fast 0.8791；dev angle_sigma5 0.3238；holdout 终测 0.8738/S=85.73。canonical seed1 SR=0.8571/S=84.13，因果 passed。
**验证**：`CONFIG=config/exp_yawclean.yaml bash tools/run_all.sh`（日志 `tools/run_all_yaw.log`）→ `tools/aggregate_report_yaw.md`；default 切换后 canonical + 10 holdout 重跑 → `tools/aggregate_report_final.md`；`python tools/validate_release.py` → VALIDATION PASSED；`release/v3` 内 DPA/DPB 各 5 passed。
**结论**：假设成立，release/v3 晋级，v2 保留回滚。下一轮优先 angle_sigma5。
