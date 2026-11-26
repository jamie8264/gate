"""Schema_v1 adapter: tolerate foreign DPA column aliases and unit differences."""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

ALIASES = {
    "t_s": ("t_s", "time", "t", "timestamp_s"),
    "hook_id": ("hook_id", "hook", "id"),
    "x_mm": ("x_mm", "x", "px"),
    "y_mm": ("y_mm", "y", "py"),
    "z_mm": ("z_mm", "z", "pz"),
    "rx_deg": ("rx_deg", "rx", "roll_deg"),
    "ry_deg": ("ry_deg", "ry", "pitch_deg"),
    "rz_deg": ("rz_deg", "rz", "yaw_deg"),
    "v_mm_s": ("v_mm_s", "v", "speed"),
    "event_flag": ("event_flag", "event"),
    "noise_sigma_mm_s": ("noise_sigma_mm_s", "sigma"),
    "chain_pos_mm": ("chain_pos_mm", "s_mm", "s"),
    "length_mm": ("length_mm", "L_mm"),
    "arc_radius_mm": ("arc_radius_mm", "r_mm"),
    "tip_radius_mm": ("tip_radius_mm", "R_mm"),
    "in_sensor_fov": ("in_sensor_fov", "fov", "in_fov"),
    "in_robot_zone": ("in_robot_zone", "zone", "in_zone"),
}


def _resolve(row: dict[str, str], key: str) -> str:
    for alias in ALIASES[key]:
        if alias in row:
            return row[alias]
    raise KeyError(f"foreign data missing {key}; available={list(row)}")


def _unit_scale(header: list[str]) -> tuple[float, float]:
    lower = [str(h).lower() for h in header]
    pos = 1000.0 if any(h.endswith("_m") for h in lower) else 1.0
    ang = 180.0 / 3.141592653589793 if any(h.endswith("_rad") for h in lower) else 1.0
    return pos, ang


def adapt_dpa(source: str | Path, target: str | Path) -> dict:
    """Copy/convert a foreign DPA directory into schema_v1 under target."""
    src, dst = Path(source), Path(target)
    dst.mkdir(parents=True, exist_ok=True)
    log: dict = {"source": str(src), "target": str(dst), "changes": []}
    for rel in ("meta.json", "truth/hooks_params.csv", "truth/chain_speed.csv", "truth/tip_truth.csv"):
        p = src / rel
        if not p.exists():
            raise FileNotFoundError(p)
    meta_p = src / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    if meta.get("schema_version") != "schema_v1":
        log["changes"].append(f"schema {meta.get('schema_version')} -> schema_v1")
        meta["schema_version"] = "schema_v1"
    meta.setdefault("seed", 1)
    meta.setdefault("scenario", "normal")
    meta.setdefault("noise_mode", "correlated")
    meta.setdefault("config_hash", "foreign")
    meta.setdefault("dt_s", 0.01)
    meta.setdefault("sensor_fov_x_mm", [-700.0, 100.0])
    meta.setdefault("robot_x_mm", 0.0)
    meta.setdefault("frame_definition", {"tip_ref": "apex", "arc_plane": "vertical"})
    (dst / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    for rel, keys in (
        ("truth/hooks_params.csv", ("hook_id", "chain_pos_mm", "length_mm", "arc_radius_mm", "tip_radius_mm")),
        ("truth/chain_speed.csv", ("t_s", "v_mm_s", "event_flag", "noise_sigma_mm_s")),
        ("truth/tip_truth.csv", ("t_s", "hook_id", "x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg", "in_sensor_fov", "in_robot_zone")),
    ):
        with (src / rel).open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
            pos_scale, ang_scale = _unit_scale(reader.fieldnames or [])
        if pos_scale != 1.0 or ang_scale != 1.0:
            log["changes"].append(f"{rel}: pos_scale={pos_scale}, ang_scale={ang_scale}")
        out_rows = []
        for r in rows:
            out = []
            for k in keys:
                if k in ("in_sensor_fov", "in_robot_zone", "event_flag", "hook_id"):
                    out.append(int(float(_resolve(r, k))))
                elif k.endswith("_mm") or k.endswith("_mm_s"):
                    out.append(float(_resolve(r, k)) * pos_scale)
                elif k.endswith("_deg"):
                    out.append(float(_resolve(r, k)) * ang_scale)
                else:
                    out.append(float(_resolve(r, k)))
            out_rows.append(out)
        p = dst / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(keys)
            for row in out_rows:
                w.writerow([f"{v:.6f}" if isinstance(v, float) else v for v in row])
    # Static preview assets, if present, are read-only copies for convenience.
    for sub in ("svg",):
        if (src / sub).exists():
            shutil.copytree(src / sub, dst / sub, dirs_exist_ok=True)
    (dst / "adapter_log.json").write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    return log
