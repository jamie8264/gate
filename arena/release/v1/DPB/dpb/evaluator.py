"""Independent evaluator: the only module (besides sensor_sim) reading truth."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from .io_utils import f as read_float, read_csv, write_csv, write_json
from .robot_sim import RobotSim
from .theory import component_floor, success_ceiling


def quat_from_euler(rx: float, ry: float, rz: float) -> np.ndarray:
    """ZYX Euler (deg) -> quaternion [w,x,y,z]."""
    x, y, z = (math.radians(v) * 0.5 for v in (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    return np.array([cx * cy * cz + sx * sy * sz,
                     sx * cy * cz - cx * sy * sz,
                     cx * sy * cz + sx * cy * sz,
                     cx * cy * sz - sx * sy * cz])


def geodesic_deg(a, b) -> float:
    q1, q2 = quat_from_euler(*a), quat_from_euler(*b)
    dot = float(np.clip(abs(np.dot(q1, q2)), -1.0, 1.0))
    return math.degrees(2.0 * math.acos(min(1.0, dot)))


def stats(values: list[float] | np.ndarray) -> dict:
    v = np.asarray(values, dtype=float)
    if v.size == 0:
        return {k: None for k in ("n", "mean", "rmse", "p50", "p90", "p95", "p99", "max")}
    return {
        "n": int(v.size), "mean": float(np.mean(v)), "rmse": float(np.sqrt(np.mean(v ** 2))),
        "p50": float(np.percentile(v, 50)), "p90": float(np.percentile(v, 90)),
        "p95": float(np.percentile(v, 95)), "p99": float(np.percentile(v, 99)),
        "max": float(np.max(v)),
    }


class TruthTable:
    """Fast per-hook truth lookup (read-only from evaluator)."""

    def __init__(self, dpa_dir: Path):
        rows = read_csv(Path(dpa_dir) / "truth" / "tip_truth.csv")
        self.by_hook: dict[int, list] = defaultdict(list)
        for r in rows:
            self.by_hook[int(r["hook_id"])].append((
                read_float(r, "t_s"),
                [read_float(r, k) for k in ("x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg")],
            ))
        for hook, seq in self.by_hook.items():
            seq.sort(key=lambda p: p[0])
            self.by_hook[hook] = (np.array([p[0] for p in seq]), np.array([p[1] for p in seq]))

    def pose_at(self, hook: int, t: float) -> np.ndarray | None:
        item = self.by_hook.get(hook)
        if item is None:
            return None
        tt, pp = item
        if t < tt[0] - 1e-6 or t > tt[-1] + 1e-6:
            return None
        return np.array([np.interp(t, tt, pp[:, j]) for j in range(6)])


def evaluate(dpa_dir: Path, dpb_dir: Path, cfg: dict, out_dir: Path) -> dict:
    """Produce eval_per_hook.csv, eval_report.json/md with both metrics."""
    out_dir = Path(out_dir)
    truth = TruthTable(dpa_dir)
    dpa_meta = json.loads((Path(dpb_dir) / "dpa_meta.json").read_text(encoding="utf-8"))
    track_map = {r["track_id"]: int(r["hook_id"]) for r in read_csv(Path(dpb_dir) / "eval_only" / "track_map.csv")}
    pred_rows = read_csv(Path(dpb_dir) / "predictions.csv")
    cmd_rows = json.loads((Path(dpb_dir) / "robot_commands.json").read_text(encoding="utf-8"))
    log_rows = read_csv(Path(dpb_dir) / "robot_log.csv")
    stream_rows = read_csv(Path(dpb_dir) / "sensor_stream.csv")
    speed_rows = read_csv(Path(dpa_dir) / "truth" / "chain_speed.csv")

    robot = RobotSim(cfg)
    for c in sorted(cmd_rows, key=lambda x: x["sequence"]):
        from .robot_sim import Command
        cmd = Command(c["command_id"], c["track_id"], c["issue_time"], c["target_time"],
                      tuple(c["target_pose"]), c["move_distance"], c["estimated_travel_time"], c["sequence"])
        robot.add(cmd)
    t_min = min((c["issue_time"] for c in cmd_rows), default=0.0)
    t_max = max((c["target_time"] for c in cmd_rows), default=0.0) + 1.0
    tt = np.arange(t_min, t_max + float(cfg["sim"]["dt_s"]), float(cfg["sim"]["dt_s"]))
    for i in range(1, len(tt)):
        robot.advance(tt[i - 1], tt[i])

    speed_t = np.array([read_float(r, "t_s") for r in speed_rows])
    speed_v = np.array([read_float(r, "v_mm_s") for r in speed_rows])
    speed_e = np.array([int(r["event_flag"]) for r in speed_rows])
    stream_by_track: dict[str, list[float]] = defaultdict(list)
    for r in stream_rows:
        stream_by_track[r["track_id"]].append(read_float(r, "t_arrival_s"))
    for k in stream_by_track:
        stream_by_track[k].sort()

    def speed_at(t: float) -> float:
        i = int(np.clip(np.searchsorted(speed_t, t), 0, len(speed_t) - 1))
        return float(speed_v[i])

    # ---- Metric 1: prediction accuracy ----
    groups: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    by_cmd: dict[str, list] = defaultdict(list)
    components = ["x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg"]
    for r in pred_rows:
        hook = track_map.get(r["track_id"])
        if hook is None:
            continue
        issue, target = read_float(r, "t_issue_s"), read_float(r, "t_target_s")
        H = target - issue
        true = truth.pose_at(hook, target)
        if true is None:
            continue
        pred = np.array([read_float(r, c) for c in components])
        err = pred - true
        pos_err = float(np.linalg.norm(err[:3]))
        ang_err = geodesic_deg(pred[3:], true[3:])
        hbucket = ("2-4" if H < 4 else "4-6" if H < 6 else "6-8" if H < 8 else "8-10" if H <= 10 else ">10")
        i0 = int(np.clip(np.searchsorted(speed_t, issue), 0, len(speed_t) - 1))
        i1 = int(np.clip(np.searchsorted(speed_t, target), 0, len(speed_t) - 1))
        is_event = bool(speed_e[i0:i1 + 1].any())
        v = speed_at(target)
        vbin = "low" if v < 40 else "mid" if v < 60 else "high"
        arr = stream_by_track.get(r["track_id"], [])
        gap = bool(arr and any(b - a > 0.2 for a, b in zip(arr, arr[1:]) if issue - 1.0 <= a <= issue))
        keys = ["all", f"H:{hbucket}", "event" if is_event else "normal", f"speed:{vbin}",
                "first" if r["cmd_id"] == min((p["cmd_id"] for p in pred_rows if p["track_id"] == r["track_id"]), default="") else "last",
                "dropout" if gap else "no_dropout", f"hook:{hook}"]
        for k in keys:
            for i, c in enumerate(components):
                groups[k][f"err_{c}"].append(float(err[i]))
            groups[k]["pos_3d"].append(pos_err)
            groups[k]["ang_geo"].append(ang_err)
        by_cmd[r["cmd_id"]].append(pos_err)

    prediction_stats = {
        k: {name: stats(v) for name, v in d.items()} for k, d in groups.items()
    }

    # ---- Metric 2: meeting capability ----
    cmds_by_hook: dict[int, list[dict]] = defaultdict(list)
    for c in cmd_rows:
        hook = track_map.get(c["track_id"])
        if hook is not None:
            cmds_by_hook[hook].append(c)
    moves_by_cmd = {r["cmd_id"]: read_float(r, "d_mm") for r in log_rows}
    log_by_cmd = {r["cmd_id"]: r for r in log_rows}
    thresholds = cfg["eval"]["thresholds"]
    per_hook: list[list] = []
    sr = {str(t["name"]): [] for t in thresholds}
    sr["pos10_only"], sr["ang3_only"] = [], []
    n_cmds_list, meet_times, final_pos, final_ang = [], [], [], []
    side_sr: dict[str, list] = defaultdict(list)
    fail_reasons: dict[str, int] = defaultdict(int)
    for hook in sorted(truth.by_hook):
        cmds = sorted(cmds_by_hook.get(hook, []), key=lambda c: c["target_time"])
        if not cmds:
            fail_reasons["传感器丢失"] += 1
            per_hook.append([hook, 0, "", "", "", *[0] * len(thresholds), "", "", "传感器丢失", ""])
            continue
        final = cmds[-1]
        t_meet = float(final["target_time"])
        t_first = min(float(c["issue_time"]) for c in cmds)
        tcp = robot.pose_at(t_meet)
        true = truth.pose_at(hook, t_meet)
        if true is None:
            fail_reasons["传感器丢失"] += 1
            continue
        pe = float(np.linalg.norm(np.array(tcp[:3]) - true[:3]))
        ae = geodesic_deg(tcp[3:], true[3:])
        n_moves = sum(1 for c in cmds if moves_by_cmd.get(c["command_id"], 0.0) > 1.0)
        valid_H = all(float(c["target_time"]) - float(c["issue_time"]) >= float(cfg["planner"]["horizon_min_s"]) - 1e-6
                      and float(c["target_time"]) - float(c["issue_time"]) <= 10.0 + 1e-6 for c in cmds)
        within_10 = t_meet - t_first <= 10.0 + 1e-6
        successes = {}
        for t in thresholds:
            ok = bool(valid_H and within_10 and pe <= float(t["pos_mm"]) and ae <= float(t["ang_deg"]))
            successes[str(t["name"])] = int(ok)
            sr[str(t["name"])].append(ok)
        sr["pos10_only"].append(bool(pe <= 10.0 and valid_H and within_10))
        sr["ang3_only"].append(bool(ae <= 3.0 and valid_H and within_10))
        # Secondary口径: minimum error in +/-0.5 s window.
        tol = float(cfg["eval"]["time_tolerance_s"])
        min_pos, min_ang = 1e9, 1e9
        for dt in np.arange(-tol, tol + 1e-6, 0.05):
            tv = t_meet + float(dt)
            tv_pose = robot.pose_at(tv)
            tv_true = truth.pose_at(hook, tv)
            if tv_true is None:
                continue
            min_pos = min(min_pos, float(np.linalg.norm(np.array(tv_pose[:3]) - tv_true[:3])))
            min_ang = min(min_ang, geodesic_deg(tv_pose[3:], tv_true[3:]))
        for t in thresholds:
            side_sr[str(t["name"])].append(bool(min_pos <= float(t["pos_mm"]) and min_ang <= float(t["ang_deg"]) and valid_H and within_10))
        reason = ""
        if not successes[str(thresholds[2]["name"])]:
            if not within_10:
                reason = "超时"
            elif not valid_H:
                reason = "物理不可达"
            elif any(c["track_id"] not in stream_by_track for c in cmds):
                reason = "传感器丢失"
            else:
                reason = "预测偏差"
            fail_reasons[reason] += 1
        n_cmds_list.append(n_moves)
        meet_times.append(t_meet - t_first)
        final_pos.append(pe)
        final_ang.append(ae)
        pred_errs = [float(np.mean(by_cmd[c["command_id"]])) for c in cmds if c["command_id"] in by_cmd]
        per_hook.append([
            hook, n_moves, round(t_first, 3), round(t_meet, 3), round(t_meet - t_first, 3),
            *[successes[str(t["name"])] for t in thresholds], round(pe, 4), round(ae, 4),
            reason,
            "|".join(f"{v:.2f}" for v in pred_errs),
        ])

    write_csv(out_dir / "eval_per_hook.csv",
              ["hook_id", "n_cmds", "t_first_cmd_s", "t_meet_s", "meet_time_s",
               *[f"success@{t['name']}" for t in thresholds], "final_pos_err_mm",
               "final_ang_err_deg", "fail_reason", "pred_pos_err_mm_by_cmd"], per_hook)

    # ---- Ceiling and internal score ----
    tau = float(dpa_meta.get("disturbance", {}).get("tau_s", 1.2))
    floor_at2 = component_floor(dpa_meta, 2.0, tau)
    floor_at4 = component_floor(dpa_meta, 4.0, tau)
    ceiling = success_ceiling(
        (floor_at2["x_mm"], floor_at2["y_mm"], floor_at2["z_mm"]),
        (floor_at2["rx_deg"], floor_at2["ry_deg"], floor_at2["rz_deg"]),
        thresholds, int(cfg["eval"]["monte_carlo_samples"]),
    )
    main_name = str(next(t for t in thresholds if float(t["pos_mm"]) == float(cfg["eval"]["main"]["pos_mm"]))["name"])
    sr_main = float(np.mean(sr[main_name])) if sr[main_name] else 0.0
    mean_moves = float(np.mean(n_cmds_list)) if n_cmds_list else 0.0
    mean_meet = float(np.mean(meet_times)) if meet_times else 0.0
    mean_pe = float(np.mean(final_pos)) if final_pos else 0.0
    score = 100.0 * sr_main - 3.0 * max(0.0, mean_moves - 1.0) - 0.5 * mean_meet - 0.1 * mean_pe
    report = {
        "schema_version": cfg["schema_version"], "config_hash": cfg["config_hash"],
        "dpa_meta": {k: dpa_meta.get(k) for k in ("seed", "scenario", "noise_mode", "config_hash")},
        "predictor_variant": cfg["predictor"]["variant"],
        "n_hooks_evaluated": len(per_hook),
        "metric1": {
            "by_component": {c: prediction_stats["all"][f"err_{c}"] for c in components},
            "pos_3d": prediction_stats["all"]["pos_3d"], "ang_geo": prediction_stats["all"]["ang_geo"],
            "groups": {k: {"pos_3d": v["pos_3d"], "ang_geo": v["ang_geo"],
                           "x_mm": v["err_x_mm"], "rz_deg": v["err_rz_deg"]}
                       for k, v in prediction_stats.items()},
        },
        "metric2": {
            "sr_by_threshold": {k: float(np.mean(v)) if v else 0.0 for k, v in sr.items()},
            "sr_side_window": {k: float(np.mean(v)) if v else 0.0 for k, v in side_sr.items()},
            "n_cmds": {"mean": mean_moves, "p90": float(np.percentile(n_cmds_list, 90)) if n_cmds_list else 0,
                       "max": int(max(n_cmds_list)) if n_cmds_list else 0},
            "meet_time_s": stats(meet_times),
            "final_pos_err_mm": stats(final_pos), "final_ang_err_deg": stats(final_ang),
            "first_cmd_success_ratio": float(np.mean([1 if m <= 1 else 0 for m in n_cmds_list])) if n_cmds_list else 0.0,
            "fail_reasons": dict(fail_reasons),
        },
        "theory": {
            "sigma_components_h2": floor_at2, "sigma_components_h4": floor_at4,
            "success_ceiling": ceiling, "ceiling_main": ceiling.get(main_name),
            "attainment": (sr_main / ceiling[main_name]) if ceiling.get(main_name) else None,
        },
        "internal_score": score, "sr_main": sr_main,
    }
    write_json(out_dir / "eval_report.json", report)
    _write_md(out_dir / "eval_report.md", report, thresholds)
    return report


def _write_md(path: Path, report: dict, thresholds: list[dict]) -> None:
    m1, m2, th = report["metric1"], report["metric2"], report["theory"]
    lines = [
        "# DPB 评估报告（schema_v1）", "",
        f"- 预测器：{report['predictor_variant']} ｜ config_hash={report['config_hash']} ｜ 评估钩数={report['n_hooks_evaluated']}",
        f"- DPA：seed={report['dpa_meta']['seed']} scenario={report['dpa_meta']['scenario']} noise={report['dpa_meta']['noise_mode']}", "",
        "## 指标一：预测精度", "",
        "| 项 | n | mean | RMSE | P50 | P90 | P95 | P99 | max |", "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, d in [("pos_3d", m1["pos_3d"]), ("ang_geo(deg)", m1["ang_geo"])] + [
        (c, m1["by_component"][c]) for c in ("x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg")
    ]:
        lines.append(f"| {name} | {d['n']} | {d['mean']:.3f} | {d['rmse']:.3f} | {d['p50']:.3f} | "
                     f"{d['p90']:.3f} | {d['p95']:.3f} | {d['p99']:.3f} | {d['max']:.3f} |" if d["n"] else f"| {name} | 0 | - | - | - | - | - | - | - |")
    lines += ["", "### 分组（位置 3D RMSE / 角度 RMSE）", "", "| 组 | n | pos RMSE | ang RMSE |", "|---|---|---|---|"]
    for k, v in m1["groups"].items():
        lines.append(f"| {k} | {v['pos_3d']['n']} | {v['pos_3d']['rmse']:.3f} | {v['ang_geo']['rmse']:.3f} |")
    lines += ["", "## 指标二：相遇能力（主口径 = 10mm/5deg）", "",
              "| 口径 | SR | 上限 | 达成率 |", "|---|---|---|---|"]
    for t in thresholds:
        name = str(t["name"])
        s = m2["sr_by_threshold"].get(name, 0.0)
        cap = th["success_ceiling"].get(name, 0.0)
        lines.append(f"| {name} | {s:.3f} | {cap:.3f} | {(s / cap if cap else 0):.3f} |")
    lines += [
        f"- 副口径（t_target±0.5 s 最小距离）：{m2['sr_side_window']}",
        f"- 平均运动次数 {m2['n_cmds']['mean']:.2f}（P90={m2['n_cmds']['p90']}, max={m2['n_cmds']['max']}）",
        f"- 首指令到相遇：mean={m2['meet_time_s']['mean']:.2f}s P50={m2['meet_time_s']['p50']:.2f} P90={m2['meet_time_s']['p90']:.2f} max={m2['meet_time_s']['max']:.2f}",
        f"- 最终位置误差 mean={m2['final_pos_err_mm']['mean']:.2f} mm；角度 mean={m2['final_ang_err_deg']['mean']:.2f} deg",
        f"- 失败原因：{m2['fail_reasons']}", "",
        "## 理论下限与上限", "",
        f"- H=2 s 各分量 σ：{th['sigma_components_h2']}",
        f"- MC 完美预测上限（200000 样本）：{th['success_ceiling']}",
        f"- 内部综合分 S={report['internal_score']:.2f}；主口径 SR={report['sr_main']:.3f}", "",
        "说明：主口径要求最后一条有效指令 t_target 时刻位置与测地角同时达标，且全程 H∈[2,10] s、首指令起 10 s 内相遇；副口径单独标注。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
