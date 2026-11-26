# iter_12 — 调度边界消融
**量化假设**：单指令时域 H 从 2.2 s 改为 2.0 s 或双指令，主达成率提升 ≥0.03 且留出终测不降。
**指标**：双指令 angle_sigma5 seed1/2 0.2143/0.2619、normal seed1 0.7619；h=2.0 完整 60 例 val normal 0.8619（+0.0286）、dev normal 0.8810（+0.0333），但最终留出 SR=0.8476（-0.0262）；h=2.5 无优势。
**验证**：`tools/run_all_h20.log`、`tools/aggregate_report_h20.md`、`/tmp/canonical_h20.log`、`/tmp/holdout_h20.log`；恢复后 `tools/aggregate_report_final.md`、`tools/validate_release.py` PASSED。
**结论**：不晋级，保持 release/v3 与 H=2.2 s。
