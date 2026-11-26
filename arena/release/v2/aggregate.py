"""Aggregate eval_report.json files into a matrix report (dev/val/holdout)."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "DPB" / "outputs"


def classify(seed: int) -> str:
    if 1 <= seed <= 10:
        return "dev"
    if 101 <= seed <= 110:
        return "val"
    if 9001 <= seed <= 9010:
        return "holdout"
    return "other"


def main() -> None:
    rows = []
    for p in sorted(OUT.glob("seed_*/eval_report.json")):
        tag = p.parent.name
        try:
            rep = json.loads(p.read_text())
        except Exception:
            continue
        meta = rep.get("dpa_meta", {})
        seed = int(meta["seed"])
        scenario = str(meta["scenario"])
        noise = str(meta["noise_mode"])
        variant = str(rep.get("predictor_variant", "b3"))
        m1 = rep["metric1"]
        m2 = rep["metric2"]
        rows.append({
            "tag": tag, "seed": seed, "scenario": scenario, "noise": noise, "variant": variant,
            "group": classify(seed), "sr_main": rep["sr_main"], "score": rep["internal_score"],
            "pos_rmse": m1["pos_3d"]["rmse"], "ang_rmse": m1["ang_geo"]["rmse"],
            "final_pos_mean": m2["final_pos_err_mm"]["mean"],
            "final_ang_mean": m2["final_ang_err_deg"]["mean"],
            "n_cmds": m2["n_cmds"]["mean"], "meet": m2["meet_time_s"]["mean"],
            "attainment": rep["theory"].get("attainment_with_speed", rep["theory"].get("attainment")),
        })
    if not rows:
        raise SystemExit("no eval_report.json found")
    (ROOT / "tools" / "aggregate_report.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    def agg(key: str, rows_subset: list[dict]) -> str:
        v = [r[key] for r in rows_subset if r[key] is not None]
        return f"{np.mean(v):.4f}" if v else "-"

    lines = ["# DPB 多场景/多种子汇总（自动生成）", "",
             "| 分组 | 场景:噪声 | n | SR@主 | 综合分 S | 位置RMSE(mm) | 角度RMSE(deg) | 最终误差(mm) | 次数 | 相遇(s) | 达成率 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    keys = sorted({(r["group"], r["scenario"], r["noise"]) for r in rows})
    for group, scenario, noise in keys:
        sub = [r for r in rows if r["group"] == group and r["scenario"] == scenario and r["noise"] == noise]
        lines.append(f"| {group} | {scenario}:{noise} | {len(sub)} | {agg('sr_main', sub)} | {agg('score', sub)} | "
                     f"{agg('pos_rmse', sub)} | {agg('ang_rmse', sub)} | {agg('final_pos_mean', sub)} | "
                     f"{agg('n_cmds', sub)} | {agg('meet', sub)} | {agg('attainment', sub)} |")
    main_sub = [r for r in rows if r["group"] == "val" and r["scenario"] == "normal" and r["noise"] == "correlated"]
    lines += ["", f"- 验证集主榜单（normal/correlated，{len(main_sub)} 例）平均 SR={agg('sr_main', main_sub)}，S={agg('score', main_sub)}",
              f"- 总案例数：{len(rows)}；报告由 `tools/aggregate.py` 从各案例 `eval_report.json` 汇总，无手工填数。"]
    (ROOT / "tools" / "aggregate_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"aggregated {len(rows)} cases -> tools/aggregate_report.md")


if __name__ == "__main__":
    main()
