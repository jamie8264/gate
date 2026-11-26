"""The ONLY DPB module allowed to read DPA truth: emulate DP3000 profile frames."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from .config import config_hash
from .io_utils import read_csv, write_csv, f as read_float


def simulate_sensor(dpa_dir: Path, cfg: dict, out_dir: Path, seed: int) -> dict:
    """Turn schema_v1 truth into sensor_stream.csv + eval_only/track_map.csv."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = Path(dpa_dir) / "meta.json"
    import json
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    (out_dir / "dpa_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    truth = read_csv(Path(dpa_dir) / "truth" / "tip_truth.csv")
    sc = cfg["sensor"]
    salt = int(hashlib.sha256((str(seed) + cfg["scenario"] + meta.get("config_hash", "")).encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(salt)
    fov_lo, fov_hi = (float(x) for x in sc["fov_x_mm"])

    # Assign a sensor track per contiguous visibility interval, in
    # chronological first-detection order (so future data cannot renumber
    # tracks that already exist). RNG draws below stay in file order.
    chronological = sorted(truth, key=lambda r: (read_float(r, "t_s"), int(r["hook_id"])))
    first_visible: list[tuple[float, int]] = []
    seen_hook: set[int] = set()
    last_t: dict[int, float] = {}
    for row in chronological:
        hook = int(row["hook_id"])
        t = read_float(row, "t_s")
        x = read_float(row, "x_mm")
        if not (fov_lo <= x <= fov_hi):
            last_t.pop(hook, None)
            continue
        if hook not in seen_hook or t - last_t.get(hook, -1e9) > 2.0:
            first_visible.append((t, hook))
            seen_hook.add(hook)
        last_t[hook] = t
    track_of: dict[int, int] = {}
    mapping: list[list] = []
    for idx, (_, hook) in enumerate(sorted(first_visible), start=1):
        track_of[hook] = idx
        mapping.append([f"T{idx:04d}", hook])
    stream: list[list] = []
    cols = ["x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg"]
    last_t = {}
    for row in chronological:
        hook = int(row["hook_id"])
        t = read_float(row, "t_s")
        x = read_float(row, "x_mm")
        if not (fov_lo <= x <= fov_hi):
            last_t.pop(hook, None)
            continue
        if hook not in track_of:
            continue
        last_t[hook] = t
        if rng.random() < float(sc["drop_prob"]):
            continue
        pose = [read_float(row, c) for c in cols]
        outlier = rng.random() < float(sc["outlier_prob"])
        pos_sig = float(sc["pos_sigma_mm"]) * (1.0 if not outlier else 1.0 + float(sc["outlier_pos_mm"]) / float(sc["pos_sigma_mm"]))
        ang_sig = float(sc["ang_sigma_deg"]) * (1.0 if not outlier else 1.0 + float(sc["outlier_ang_deg"]) / float(sc["ang_sigma_deg"]))
        noisy = [p + rng.normal(0.0, pos_sig if i < 3 else ang_sig) for i, p in enumerate(pose)]
        q_mm, q_deg = float(sc["quant_mm"]), float(sc["quant_deg"])
        noisy = [round(v, 2) if i < 3 else round(v, 2) for i, v in enumerate(noisy)]
        if q_mm != 0.01:
            noisy = [round(v / q_mm) * q_mm if i < 3 else round(v / q_deg) * q_deg for i, v in enumerate(noisy)]
        t_arrival = t + float(sc["latency_s"]) + rng.normal(0.0, float(sc["timestamp_jitter_s"]))
        t_arrival = max(t_arrival, t)
        stream.append([round(t, 6), round(t_arrival, 6), f"T{track_of[hook]:04d}", *noisy, 1])

    stream.sort(key=lambda r: (r[1], r[0], r[2]))
    write_csv(out_dir / "sensor_stream.csv",
              ["t_sensor_s", "t_arrival_s", "track_id", "x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg", "valid"], stream)
    write_csv(out_dir / "eval_only" / "track_map.csv", ["track_id", "hook_id"], mapping)
    return {"n_frames": len(stream), "n_tracks": len(mapping), "dpa_config_hash": meta.get("config_hash"),
            "dpa_seed": meta.get("seed"), "dpa_scenario": meta.get("scenario"), "dpa_noise": meta.get("noise_mode")}
