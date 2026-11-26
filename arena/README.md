# arena · 挂钩尖端预测双项目（DPA / DPB）

> 从 GitHub 下载的仓库里，**本任务在 `arena/` 子目录**（仓库根 README 是另一个限流项目，不要混用）。

- `00_项目总纲与动态记忆_先读.md`：先读此文件（规则、状态、指标、日志）
- `01_技术规范与假设.md`：坐标系、物理模型 H1–H14、schema_v1、理论下限
- `02_迭代日志与多模型互评.md`：历史轮次、实验记录、交叉评测
- `DPA/`：挂钩几何/链速/扰动真值仿真 + SVG 动画（独立项目）
- `DPB/`：DP3000 传感器仿真 → 因果门控 → 预测 → 机械臂 → 独立评估（独立项目）
- `tools/`：批量复现、聚合、适配层、交叉评测、交付校验
- `runs/iter_XX/`：每轮量化假设 → 改动 → 指标 → 结论
- `release/v1`、`release/v2`、`release/v3`：通过测试的历史快照；**当前最佳 `release/v3`**（yaw 几何去相关）

## 本地安装（Python ≥3.10）

```bash
cd <你下载的仓库目录>/arena
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell:  .venv\Scripts\Activate.ps1
python -m pip install -r DPA/requirements.txt -r DPB/requirements.txt
```

依赖只有 `numpy`、`PyYAML`、`pytest`。`pypdf` 只在早期读取参考 PDF 时使用，运行本项目不需要。

## 两步跑通（DPA → DPB）

> GitHub 包**不含** `DPA/outputs/`、`DPB/outputs/`（被 `.gitignore` 排除），首次必须先生成 DPA 数据；或使用快照里的现成夹具 `release/v3/DPA/outputs/seed_1_normal_correlated`。

```bash
# 终端 1：生成真值 + SVG
cd arena/DPA
python -m dpa.cli --config config/default.yaml --seed 1 \
  --scenario normal --noise correlated --out outputs/seed_1_normal_correlated
# 预期：rows=85480 hooks=41 ... svg_series=4 svg_frames=330

# 终端 2：传感器仿真 → 预测 → 机械臂 → 评估（含因果测试）
cd ../DPB
python -m dpb.cli --config config/default.yaml \
  --dpa ../DPA/outputs/seed_1_normal_correlated \
  --out outputs/seed_1_normal_correlated
# 预期：SR_main=0.8571 S=84.13 causal=True
```

不想重新生成 DPA，可直接用快照夹具：把上面 `--dpa` 改成 `../release/v3/DPA/outputs/seed_1_normal_correlated`。

打开 `DPA/outputs/seed_1_normal_correlated/svg/animation.svg`（浏览器直接打开）即可看自包含动画：俯视/侧视/真实钩形、六维数值、速度曲线、播放/暂停/倍速/时间轴。

## 测试

```bash
cd arena/DPA && python -m pytest -q     # 5 passed
cd ../DPB   && python -m pytest -q     # 5 passed
```

## 批量复现 60 例矩阵（约 5–6 分钟）

`bash` 脚本在 Windows 需用 Git Bash / WSL；命令会用 `PY` 环境变量指定的解释器：

```bash
cd arena
PY="$(python -c 'import sys; print(sys.executable)')" bash tools/run_all.sh
# 或 macOS/Linux 直接：PY=python3 bash tools/run_all.sh
python tools/validate_release.py          # VALIDATION PASSED
cd release/v3 && python validate_release.py   # 快照自包含校验，也 PASSED
```

可用环境变量裁剪/改写矩阵：

```bash
DEV_SEEDS="1 2" VAL_SEEDS="101" HOLDOUT_SEEDS="" \
SCENARIOS="normal:correlated fast:correlated" \
PY="$(python -c 'import sys; print(sys.executable)')" bash tools/run_all.sh
```

批量输出在 `DPA/outputs/`、`DPB/outputs/`；聚合报告为 `tools/aggregate_report.md/.json`，最终 60 例报告另存为 `tools/aggregate_report_final.md/.json`。

## full 模式（700 钩整圈，约 33 秒 + DPB 1 分钟）

```bash
cd arena/DPA && python -m dpa.cli --config config/default.yaml --seed 1 --mode full --out outputs/full_seed_1
cd ../DPB && python -m dpb.cli --config config/default.yaml --dpa ../DPA/outputs/full_seed_1 \
  --out outputs/full_seed_1 --no-causal
```

full 模式约 154 万行真值；10 Hz 降采样版本的验证结果见 `00` §7.6（SR=0.8000、S=78.11）。

## 隔离承诺
DPB 决策路径只读 `sensor_stream.csv`；真值仅 `sensor_sim` 与 `evaluator` 可读；自动因果测试在 `DPB/dpb/causality.py`。无同级模型文件夹被修改。
