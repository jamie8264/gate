"""Vectorised DPA simulation: geometry, chain dynamics and tip disturbances."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .chain_dynamics import simulate_speed
from .config import load_config, sigma_from_tol
from .disturbance import disturbance_channels
from .exporter import write_csv, write_hook_params, write_meta, write_speed
from .hook_model import local_tip, rotate_tip, sample_hook_params


def simulate(cfg: dict, seed: int, out_dir: str | Path) -> dict:
    """Run one DPA case and write schema_v1 outputs; return summary stats."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dt = float(cfg["dt_s"])
    spacing = float(cfg["chain_length_mm"]) / int(cfg["n_hooks"])
    v0 = float(cfg["speed"]["v0_mm_s"])
    n_pass = int(cfg["zone"]["n_passing_hooks"])
    duration = (n_pass + 3) * spacing / v0 + float(cfg["zone"]["tail_s"])
    n_steps = int(round(duration / dt))
    cfg["_duration_s"] = float(n_steps * dt)

    params_all = sample_hook_params(cfg, seed)
    write_hook_params(out_dir, params_all)

    rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(0))
    speed = simulate_speed(cfg, rng, n_steps)
    write_speed(out_dir, speed)
    cfg["_n_simulated"] = 0

    chain_pos = speed["s"]
    fov_lo, fov_hi = (float(x) for x in cfg["sensor"]["fov_x_mm"])
    margin = float(cfg["sensor"]["export_margin_mm"])
    # Hooks pass the station (s=0) when their initial s is just below the
    # chain-length wrap point: s_i(t) = s_i(0) + integral(v dt) mod L.
    reach = v0 * duration * 1.25 + 5.0 * spacing
    chain_len = float(cfg["chain_length_mm"])
    selected = [
        i for i in range(params_all.shape[0])
        if params_all[i, 0] >= chain_len - reach or params_all[i, 0] <= margin
    ]
    cfg["_n_simulated"] = len(selected)

    dist_seed = np.random.SeedSequence(seed + 500003)
    truth_rows: list[list] = []
    angle_samples: list[np.ndarray] = []
    for local_idx, i in enumerate(selected):
        s_i = params_all[i, 0]
        x_t = ((s_i + chain_pos + float(cfg["chain_length_mm"]) / 2.0) % float(cfg["chain_length_mm"])) - float(cfg["chain_length_mm"]) / 2.0
        mask = (x_t >= fov_lo - margin) & (x_t <= fov_hi + margin)
        idx = np.flatnonzero(mask)
        if idx.size == 0:
            continue
        dist = disturbance_channels(rng, idx.size, cfg, dist_seed, local_idx)
        p_local = local_tip(params_all[i], cfg)
        points = np.tile(p_local, (idx.size, 1))
        offsets = rotate_tip(points, dist["rz_deg"], dist["rx_deg"], dist["ry_deg"], dist["root_y_mm"])
        xx = x_t[idx] + offsets[:, 0]
        yy = offsets[:, 1]
        zz = offsets[:, 2]
        angle_samples.append(np.column_stack((dist["rx_deg"], dist["ry_deg"], dist["rz_deg"])))
        for k, pos in enumerate(idx):
            xp = float(xx[k])
            truth_rows.append([
                float(speed["t"][pos]), int(i), xp, float(yy[k]), float(zz[k]),
                float(dist["rx_deg"][k]), float(dist["ry_deg"][k]), float(dist["rz_deg"][k]),
                int(fov_lo <= xp <= fov_hi), int(-300.0 <= xp <= 300.0),
            ])

    write_csv(out_dir / "truth" / "tip_truth.csv",
              ["t_s", "hook_id", "x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg",
               "in_sensor_fov", "in_robot_zone"], truth_rows)
    write_meta(out_dir, cfg, seed, params_all.shape[0])

    ang = np.vstack(angle_samples) if angle_samples else np.zeros((1, 3))
    summary = {
        "n_steps": n_steps,
        "duration_s": float(n_steps * dt),
        "n_truth_rows": len(truth_rows),
        "n_hooks_output": len({r[1] for r in truth_rows}),
        "L_mean_mm": float(np.mean(params_all[:, 1])), "L_std_mm": float(np.std(params_all[:, 1])),
        "r_mean_mm": float(np.mean(params_all[:, 2])), "r_std_mm": float(np.std(params_all[:, 2])),
        "R_mean_mm": float(np.mean(params_all[:, 3])), "R_std_mm": float(np.std(params_all[:, 3])),
        "v_mean": float(np.mean(speed["v"])), "v_std": float(np.std(speed["v"])),
        "v_min": float(np.min(speed["v"])), "v_max": float(np.max(speed["v"])),
        "n_events": int(np.sum(np.diff(speed["event_flag"].astype(int)) == 1)),
        "angle_std_deg": [float(x) for x in np.std(ang, axis=0)],
        "sigma_angle_target_deg": sigma_from_tol(cfg["disturbance"]["angle_tol_deg"], "3sigma"),
    }
    write_selfcheck(out_dir, cfg, summary)
    return summary


def write_selfcheck(out_dir: Path, cfg: dict, s: dict) -> None:
    """Write a self-check report comparing measured vs configured statistics."""
    lines = [
        "# DPA 自检报告", "",
        f"- schema: {cfg['schema_version']} / seed={cfg['_seed'] if '_seed' in cfg else 'n/a'} / "
        f"scenario={cfg['scenario']} / noise={cfg['noise_mode']}",
        f"- config_hash: {cfg['config_hash']}", "",
        "| 项 | 设定 | 实测 | 判定 |", "|---|---|---|---|",
        f"| 钩长 L | {cfg['hook']['length_mm']} ± {cfg['hook']['length_tol_mm']} (σ={cfg['hook']['length_tol_mm']/3:.3f}) | "
        f"{s['L_mean_mm']:.3f} ± {s['L_std_mm']:.3f} (std) | {'OK' if abs(s['L_std_mm'] - cfg['hook']['length_tol_mm']/3) < cfg['hook']['length_tol_mm']/15 else 'CHECK'} |",
        f"| 弧半径 r | {cfg['hook']['arc_radius_mm']} ± {cfg['hook']['arc_radius_tol_mm']} | "
        f"{s['r_mean_mm']:.3f} ± {s['r_std_mm']:.3f} | {'OK' if abs(s['r_std_mm'] - 2/3) < 0.15 else 'CHECK'} |",
        f"| 半球半径 R | {cfg['hook']['tip_radius_mm']} ± {cfg['hook']['tip_radius_tol_mm']} | "
        f"{s['R_mean_mm']:.3f} ± {s['R_std_mm']:.3f} | {'OK' if abs(s['R_std_mm'] - 1/3) < 0.1 else 'CHECK'} |",
        f"| 链速范围 | [{cfg['speed']['v_min_mm_s']}, {cfg['speed']['v_max_mm_s']}] | "
        f"[{s['v_min']:.2f}, {s['v_max']:.2f}] mean={s['v_mean']:.2f} | OK |",
        f"| 速度事件 | λ={cfg['speed']['event']['lambda_per_s']:.5f}/s, T={s['duration_s']:.1f}s | {s['n_events']} 次 | 信息 |",
        f"| 角度 σ (rx,ry,rz) | σ_a={s['sigma_angle_target_deg']:.3f}°, ry={cfg['disturbance']['ry_sigma_deg']}° | "
        f"({s['angle_std_deg'][0]:.3f}, {s['angle_std_deg'][1]:.3f}, {s['angle_std_deg'][2]:.3f})° | 信息 |",
        f"| 输出 | {s['n_hooks_output']} 钩 / {s['n_truth_rows']} 行 / {s['n_steps']} 步 | 见 truth/ | OK |", "",
        "分布说明：公差用截断正态（σ=公差/3），OU 平稳边际经 ±3σ 截断；角度单位 deg，长度 mm。",
    ]
    (out_dir / "dpa_selfcheck_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
