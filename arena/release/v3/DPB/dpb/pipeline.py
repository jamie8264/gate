"""End-to-end causal DPB pipeline: stream -> tracker -> planner -> robot."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .config import config_hash  # noqa: F401
from .io_utils import read_csv, write_csv, write_json
from .planner import Planner
from .predictors import Prediction
from .robot_sim import RobotSim
from .stream import StreamReplayer
from .tracker import Tracker


def run_pipeline(dpb_dir: Path, cfg: dict, out_dir: Path) -> dict:
    """Run the prediction/planning/robot loop; inputs limited to sensor_stream."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    replayer = StreamReplayer(dpb_dir / "sensor_stream.csv")
    tracker = Tracker(cfg)
    robot = RobotSim(cfg)
    planner = Planner(cfg, robot, tracker)
    meta_dpa = json.loads((Path(dpb_dir) / "dpa_meta.json").read_text(encoding="utf-8"))
    cfg["_sensor_dt"] = float(meta_dpa["dt_s"])

    pred_rows: list[list] = []
    debug_rows: list[list] = []
    cmd_rows: list[dict] = []
    t_end = (replayer.frames[-1].t_arrival + 1.0) if replayer.frames else 1.0
    dt = float(cfg["sim"]["dt_s"])
    n_steps = int(np.ceil(t_end / dt)) + 1
    t_prev = 0.0
    active: set[str] = set()
    for k in range(n_steps):
        t = min(float(k) * dt, t_end)
        frames = replayer.advancing_frames(t)
        tracker.ingest(frames)
        active.update(f.track_id for f in frames)
        robot.advance(t_prev, t)
        for tid in list(active):
            tr = tracker.tracks[tid]
            if tr.done:
                active.discard(tid)
                continue
            cmds, preds = planner.consider(tr, t)
            for cmd, (_, pred) in zip(cmds, preds):
                pred_rows.append([
                    tr.track_id, cmd.command_id, round(cmd.issue_time, 6), round(cmd.target_time, 6),
                    round(cmd.target_time - cmd.issue_time, 6), *[round(v, 6) for v in pred.pose],
                    round(pred.sigma_pos_mm, 6),
                ])
                d = pred.diagnostics
                debug_rows.append([
                    tr.track_id, cmd.command_id, round(cmd.issue_time, 6),
                    round(float(d.get("v_local", 0)), 4), round(float(d.get("v_shared", 0)), 4),
                    round(float(d.get("v_hat", 0)), 4), round(float(d.get("tau_hat", 0)), 4),
                    round(float(d.get("accel", 0)), 4), round(float(d.get("accel_correction", 0)), 4),
                    int(d.get("event_suspected", False)),
                ])
                cmd_rows.append({
                    "command_id": cmd.command_id, "track_id": cmd.track_id,
                    "issue_time": round(cmd.issue_time, 6), "target_time": round(cmd.target_time, 6),
                    "target_pose": [round(float(v), 6) for v in cmd.target_pose],
                    "communication_delay": float(cfg["robot"]["comm_delay_s"]),
                    "move_distance": round(cmd.move_distance, 6),
                    "estimated_travel_time": round(cmd.estimated_travel_time, 6),
                    "sequence": cmd.sequence,
                })
            if tr.target_time is not None and t > tr.target_time + 0.2:
                tr.done = True
        t_prev = t

    write_csv(out_dir / "predictions.csv",
              ["track_id", "cmd_id", "t_issue_s", "t_target_s", "horizon_s",
               "x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg", "sigma_pos_mm"], pred_rows)
    write_json(out_dir / "robot_commands.json", cmd_rows)
    write_csv(out_dir / "predictor_debug.csv",
              ["track_id", "cmd_id", "t_issue_s", "v_local", "v_shared", "v_hat", "tau_hat",
               "accel", "accel_correction", "event_suspected"], debug_rows)
    log_rows = []
    for cmd in robot.commands:
        pose = robot.pose_at(cmd.target_time)
        if cmd.start_time <= 0:
            continue
        log_rows.append([
            cmd.track_id, cmd.command_id, round(cmd.issue_time, 6), round(cmd.start_time, 6),
            round(cmd.arrive_time, 6), round(cmd.actual_distance, 6),
            *[round(float(v), 6) for v in pose],
        ])
    write_csv(out_dir / "robot_log.csv",
              ["track_id", "cmd_id", "t_issue_s", "t_start_s", "t_arrive_s", "d_mm",
               "tcp_x_mm", "tcp_y_mm", "tcp_z_mm", "tcp_rx_deg", "tcp_ry_deg", "tcp_rz_deg"], log_rows)
    report = {
        "n_tracks": len(tracker.tracks), "n_commands": len(robot.commands),
        "n_predictions": len(pred_rows), "n_moves": sum(1 for c in robot.commands if c.actual_distance > 1.0),
        "n_cancelled": sum(1 for c in robot.commands if c.cancelled),
        "t_end_s": t_end, "dt_s": dt, "predictor_variant": cfg["predictor"]["variant"],
        "config_hash": cfg["config_hash"], "schema_version": cfg["schema_version"],
    }
    write_json(out_dir / "pipeline_report.json", report)
    return report
