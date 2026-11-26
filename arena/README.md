# arena · 挂钩尖端预测双项目（DPA / DPB）

- `00_项目总纲与动态记忆_先读.md`：先读此文件（规则、状态、指标、日志）
- `01_技术规范与假设.md`：坐标系、物理模型 H1–H14、schema_v1、理论下限
- `02_迭代日志与多模型互评.md`：历史轮次、实验记录、交叉评测
- `DPA/`：挂钩几何/链速/扰动真值仿真 + SVG 动画（独立项目）
- `DPB/`：DP3000 传感器仿真 → 因果门控 → 预测 → 机械臂 → 独立评估（独立项目）
- `tools/`：批量复现、聚合、适配层、交叉评测、交付校验
- `runs/iter_XX/`：每轮量化假设 → 改动 → 指标 → 结论
- `release/v1`：通过测试的快照（含代码、配置、夹具、RELEASE_NOTES）

## 复现
```bash
cd /home/user/gate/arena
bash tools/run_all.sh                 # 全矩阵（dev/val/holdout 由环境变量控制）
python tools/validate_release.py      # 交付校验（需 .venv）
```
细节与当前最佳指标见总纲 §14 头部与 `tools/aggregate_report.md`。
`validate_release.py` 使用 `/home/user/gate/.venv/bin/python`；若环境不同请改该脚本常量。

## 隔离承诺
DPB 决策路径只读 `sensor_stream.csv`；真值仅 `sensor_sim` 与 `evaluator` 可读；自动因果测试在 `DPB/dpb/causality.py`。无同级模型文件夹被修改。
