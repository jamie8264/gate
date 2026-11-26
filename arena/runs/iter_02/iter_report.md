# iter_02 — DPB 闭环与因果
**量化假设**：因果测试通过、seed1 主口径 SR>0.30。
**改动**：传感器/门控/预测 B0–B3/规划/机械臂/评估/理论上限/causality；修复加速度长程外推、修正指令 H<2、track_id 未来依赖三个 bug。
**指标**：seed1 SR_main=0.410，S=31.85；B0=0.026，B1=0.487；因果测试 16 条早期指令逐位一致；DPB pytest 5 passed。
**验证**：`cd DPB && /home/user/gate/.venv/bin/python -m dpb.cli --config config/default.yaml --dpa ../DPA/outputs/seed_1_normal_correlated --out outputs/seed_1_normal_correlated`；证据 `outputs/seed_1_normal_correlated/{eval_report.json,causal_report.json}`。
**结论**：假设成立；X 向误差仍受链速 OU 不可预测项主导。
