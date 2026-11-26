# iter_05 — B4 / 事件自适应实验（未晋级）
**量化假设**：自监督 Ridge 残差校正或事件期加速度修正能把 event_heavy SR 提升 ≥0.03。
**改动**：`predictors/base.py` 新增 `_ridge_velocity_correction()`（只用已到达传感器帧做标签）、`event_accel_kappa` 分支；均保留为可选配置，默认关闭。
**指标**：B4 seed1 normal SR=0.4359、seed101 normal SR=0.3333；事件自适应 kappa=0.8 在 seed1/101 event_heavy 上 SR=0.436/0.308（基线 0.436/0.282，seed101 下降）；B3 基线 seed1=0.4872。
**验证**：`python -m dpb.cli --variant b4 ... --no-causal`；`--config config/exp_eventacc.yaml ...`。
**结论**：假设不成立，B4/事件自适应未晋级；保留实验记录与配置以便复现。
