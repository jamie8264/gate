# DPB · 激光轮廓感知 → 六维预测 → 机械臂相遇 → 独立评估

与 `../DPA` 隔离：决策路径（stream/tracker/predictors/planner/robot_sim/pipeline）只消费 `sensor_stream.csv`，禁止 `import dpa`、禁止读取真值/hook_id/事件标志。只有 `sensor_sim.py` 和 `evaluator.py` 读 DPA 文件。

## 一键复现
```bash
cd arena/DPB
python -m dpb.cli --config config/default.yaml \
  --dpa ../DPA/outputs/seed_1_normal_correlated --out outputs/seed_1_normal_correlated_b3
python -m pytest -q
```
`--variant b0|b1|b2|b3|b4` 切换预测器；`--no-causal` 跳过篡改未来真值的因果测试（批量时节省时间）。

## 输出
`sensor_stream.csv`、`eval_only/track_map.csv`、`dpa_meta.json`、`predictions.csv`、`robot_commands.json`、`robot_log.csv`、`predictor_debug.csv`、`eval_per_hook.csv`、`eval_report.json/md`、`causal_report.json`、`run_summary.json`。

## 策略摘要（B3）
- 默认 `adaptive` 调度：在线节拍 cadence∈[11,20] s 时在挂钩接近工位处发**单条**指令（H≈2.2 s）；cadence<11 s（fast）或>20 s（slow）时发首指令 + `t_target−[2.0,2.25] s` 修正；全程 H∈[2,10]、首指令起 10 s 内相遇。
- 新指令 0.5 s 后从 TCP 当时位置出发并抢占旧指令；目标点受三维可达性 `0.5+d/200≤H` 与工作包络约束。
- X：默认 `use_attitude_decorrelation: true`，先用传感器 Rz 与名义杠杆 95 mm 还原链上位置（`x_corr=x+95sin(rz)`），再以最近 0.3 s OLS 外推当前位置 + 全链共享稳健速度（shared_weight=1.0，κ_a=0）；目标点按预测 Rz 还原摆动。Y/Z/Rx/Ry/Rz：在线估计 τ 的 OU 条件均值。
- 评估：位置 3D + 旋转测地角，六分量与分组统计；主口径 10 mm/5°，副口径 ±0.5 s；理论下限与 MC 完美预测上限。
