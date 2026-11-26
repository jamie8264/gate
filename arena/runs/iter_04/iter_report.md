# iter_04 — release/v1 与留出集
**量化假设**：留出集（10 seed）主 SR 与验证集差距 ≤0.10，说明未过拟合开发集。
**改动**：`release/v1/` 快照（代码+配置+夹具+RELEASE_NOTES）、README/requirements、`tools/adapters.py`、`tools/cross_eval.py`；修复适配器单位误判（`arc_radius_mm` 含 `_rad` 子串）和 hook_id 浮点化。
**指标**：holdout normal/corr 10 例 SR=0.4487、S=35.89、位置RMSE=33.43 mm、平均次数 1.995；与 val 0.4872 差 0.0385，假设成立。交叉评测（别名转换伪外部 DPA）SR=0.4872，接口兼容。
**验证**：`HOLDOUT_SEEDS='9001 ... 9010' SCENARIOS='normal:correlated' bash tools/run_all.sh`；`tools/aggregate_report.md`；`tools/cross_eval.py --foreign /tmp/foreign_dpa --out DPB/outputs/cross_eval_selfalias`；release 内 DPA pytest 5 passed、DPB pytest 5 passed。
**结论**：release/v1 通过晋级门槛；留出集只用于评估，未调参。
