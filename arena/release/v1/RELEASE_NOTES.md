# release/v1 — 晋级记录

- 时间：2026-11-26 04:20 UTC（第 R4 轮）
- schema：schema_v1；DPA config_hash=72151cf67bdf；DPB config_hash=fe7dcd96a32c
- 最佳策略：B3（全链共享链速、OU 条件均值、首指令+2 s 修正、2 条指令/钩）
- 单案例证据（seed1 normal/correlated）：SR@主=0.4872，S=39.58，位置RMSE=35.674 mm，角度RMSE=3.043 deg
- 验证集 5 例 normal/correlated：SR=0.4872，S=39.66（见 `../../tools/aggregate_report.md`）
- 门槛：DPA pytest 5 passed；DPB pytest 5 passed；因果测试 passed（16 条早期指令逐位一致）；normal/fast/event_heavy 无退化（dev/val 均有报告）
- 已知限制：event_heavy 场景 SR≈0.36；angle_sigma5 压力场景 SR≈0.11；B4  Ridge 实验未晋级（seed1 SR 0.436 < B3 0.487）
- 复现：`cd DPB && /home/user/gate/.venv/bin/python -m dpb.cli --config config/default.yaml --dpa ../DPA/outputs/seed_1_normal_correlated --out outputs/seed_1_normal_correlated_b3`
