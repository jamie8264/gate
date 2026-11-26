# DPA · 挂钩尖端扰动仿真（真值源）

Python 3.10+，依赖 `numpy`、`PyYAML`（见 `requirements.txt`）。与 `../DPB` 完全隔离：本包不读 DPB 任何文件。

## 一键复现
```bash
cd /home/user/gate/arena/DPA
/home/user/gate/.venv/bin/python -m dpa.cli --config config/default.yaml --seed 1 \
  --scenario normal --noise correlated --out outputs/seed_1_normal_correlated
/home/user/gate/.venv/bin/python -m pytest -q
```

## 输出
- `meta.json`（schema_v1、seed、场景、噪声、config_hash、frame_definition）
- `truth/hooks_params.csv`、`truth/chain_speed.csv`、`truth/tip_truth.csv`
- `dpa_selfcheck_report.md`（公差/速度/扰动分布实测对照）
- `svg/animation.svg`（自包含 JS 动画：俯视/侧视/真实钩形/六维数值/速度曲线/播放暂停倍速/时间轴）、`svg/preview.svg`、`svg/animation_data.json`

## 模型要点
450 m 链条、700 钩、几何公差截断正态（±值=3σ）、链速 OU + 泊松速度事件、角度/根部扰动 OU（correlated，τ≈1.2 s）或白噪声（white）。逐钩独立 SeedSequence 流，subset 与 full 参数一致。默认 zone 输出 ≥30 个完整通过工位的挂钩；dt=0.01 s。所有参数在 `config/default.yaml`。
