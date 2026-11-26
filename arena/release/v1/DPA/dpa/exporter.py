"""schema_v1 writers for DPA outputs."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for row in rows:
            w.writerow([f"{v:.6f}" if isinstance(v, (float,)) else v for v in row])


def write_meta(out_dir: Path, cfg: dict, seed: int, n_hooks: int) -> None:
    meta = {
        "schema_version": cfg["schema_version"],
        "generator_version": cfg["generator_version"],
        "seed": seed,
        "scenario": cfg["scenario"],
        "noise_mode": cfg["noise_mode"],
        "config_hash": cfg["config_hash"],
        "frame_definition": {
            "tip_ref": cfg["hook"]["tip_ref"],
            "arc_plane": cfg["hook"]["arc_plane"],
            "euler_order": "ZYX",
            "angle_sigma_mode": cfg["disturbance"]["angle_sigma_mode"],
            "angle_tol_deg": cfg["disturbance"]["angle_tol_deg"],
        },
        "dt_s": cfg["dt_s"],
        "n_hooks": n_hooks,
        "n_hooks_simulated": cfg.get("_n_simulated", 0),
        "duration_s": cfg.get("_duration_s", 0.0),
        "chain_length_mm": cfg["chain_length_mm"],
        "sensor_fov_x_mm": cfg["sensor"]["fov_x_mm"],
        "robot_x_mm": cfg["sensor"]["robot_x_mm"],
        "units": {"position": "mm", "angle": "deg", "time": "s", "speed": "mm/s"},
        "hook": {"length_mm": cfg["hook"]["length_mm"], "tip_radius_mm": cfg["hook"]["tip_radius_mm"],
                 "arc_radius_mm": cfg["hook"]["arc_radius_mm"]},
        "disturbance": {"angle_tol_deg": cfg["disturbance"]["angle_tol_deg"],
                        "ry_sigma_deg": cfg["disturbance"]["ry_sigma_deg"],
                        "root_y_sigma_mm": cfg["disturbance"]["root_y_sigma_mm"],
                        "tau_s": cfg["disturbance"]["tau_s"]},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_hook_params(out_dir: Path, params) -> None:
    rows = [
        (int(i), float(params[i, 0]), float(params[i, 1]), float(params[i, 2]), float(params[i, 3]))
        for i in range(params.shape[0])
    ]
    write_csv(out_dir / "truth" / "hooks_params.csv",
              ["hook_id", "chain_pos_mm", "length_mm", "arc_radius_mm", "tip_radius_mm"], rows)


def write_speed(out_dir: Path, speed: dict) -> None:
    rows = [
        (float(speed["t"][k]), float(speed["v"][k]), int(speed["event_flag"][k]), float(speed["noise_sigma"][k]))
        for k in range(len(speed["t"]))
    ]
    write_csv(out_dir / "truth" / "chain_speed.csv",
              ["t_s", "v_mm_s", "event_flag", "noise_sigma_mm_s"], rows)
