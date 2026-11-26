# DPB · 激光轮廓感知 → 六维预测 → 机械臂相遇 → 独立评估

与 `../DPA` 隔离：决策路径（stream/tracker/predictors/planner/robot_sim/pipeline）只消费 `sensor_stream.csv`，禁止 `import dpa`、禁止读取真值/hook_id/事件标志。只有 `sensor_sim.py` 和 `evaluator.py` 读 DPA 文件。

## 一键复现
```bash
cd /home/user/gate/arena/DPB
/home/user/gate/.venv/bin/python -m dpb.cli --config config/default.yaml \
  --dpa ../DPA/outputs/seed_1_normal_correlated --out outputs/seed_1_normal_correlated_b3
/home/user/gate/.venv/bin/python -m pytest -q
```
`--variant b0|b1|b2|b3|b4` 切换预测器；`--no-causal` 跳过篡改未来真值的因果测试（批量时节省时间）。

## 输出
`sensor_stream.csv`、`eval_only/track_map.csv`、`dpa_meta.json`、`predictions.csv`、`robot_commands.json`、`robot_log.csv`、`predictor_debug.csv`、`eval_per_hook.csv`、`eval_report.json/md`、`causal_report.json`、`run_summary.json`。

## 策略摘要（B3）
- 首条指令：hook 在视场内、能满足 H∈[2,10] 且目标在机械臂包络内时发出，目标时刻选挂钩接近工位处；cadence 由传感器首次检测间隔在线估计。
- 最后一条修正：在 `t_target−[2.0,2.25] s` 发出，H≥2 s；新指令 0.5 s 后从 TCP 当前位置出发并抢占旧指令。
- X：全链共享速度估计（稳健斜率中位数），不再用受钩体扰动污染的加速度外推；Y/Z/Rx/Ry/Rz：在线估计 τ 的 OU 条件均值。
- 评估：位置 3D + 旋转测地角，六分量与分组统计；主口径 10 mm/5°，副口径 ±0.5 s；理论下限与 MC 完美预测上限。
