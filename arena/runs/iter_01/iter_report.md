# iter_01 — DPA 真值源
**量化假设**：几何公差实测 σ 与设定偏差 <5%；SVG ≥3 钩 ≥100 帧。
**改动**：DPA 全模块（hook_model/chain_dynamics/disturbance/simulator/exporter/svg_animation/cli）、配置、5 个 pytest。
**指标**：钩长 100.028±1.603 mm、r 20.017±0.647、R 5.022±0.343、v∈[20,76.24] mm/s（2 次事件）、角度 σ=(1.667,0.207,1.683)°；41 钩/85480 行；SVG 4 钩 330 帧。
**验证**：`cd DPA && /home/user/gate/.venv/bin/python -m dpa.cli --config config/default.yaml --seed 1 --out outputs/seed_1_normal_correlated`；`pytest -q` → 5 passed。
**结论**：假设成立；工况内参数可信。
