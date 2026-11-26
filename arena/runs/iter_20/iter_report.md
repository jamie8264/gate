# iter_20（05:50–06:03 UTC）— 本地运行/测试指引与脚本可移植化
**需求**：用户已从 GitHub 下载项目到本地，需给出运行与测试步骤。
**改动**：`arena/README.md` 完整本地命令；`tools/run_all.sh`、`tools/validate_release.py`、`tools/cross_eval.py` 及 release/v3 对应脚本去硬编码路径；快照脚本 ROOT 自包含。
**验证**：根目录与 release/v3 校验器均 VALIDATION PASSED；py_compile 通过；pytest DPA 5 + DPB 5 passed。
**结论**：用户按 `arena/README.md` 操作即可；GitHub 包不含 outputs，需先跑 DPA 或用 release/v3 夹具。
