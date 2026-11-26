"""Tip disturbance processes (per hook, independent streams)."""
from __future__ import annotations

import numpy as np


def ou_process(rng: np.random.Generator, n: int, sigma: float, tau: float,
               dt: float, bound_sigma: float = 3.0) -> np.ndarray:
    """Stationary OU sequence clipped at +/- bound_sigma*sigma."""
    out = np.empty(n, dtype=np.float64)
    if n == 0:
        return out
    rho = float(np.exp(-dt / tau))
    innov = sigma * np.sqrt(max(0.0, 1.0 - rho * rho))
    out[0] = np.clip(rng.normal(0.0, sigma), -bound_sigma * sigma, bound_sigma * sigma)
    eps = rng.standard_normal(n)
    for k in range(1, n):
        val = rho * out[k - 1] + innov * eps[k]
        out[k] = np.clip(val, -bound_sigma * sigma, bound_sigma * sigma)
    return out


def disturbance_channels(rng: np.random.Generator, n: int, cfg: dict, seed_seq: np.random.SeedSequence,
                         hook_idx: int) -> dict[str, np.ndarray]:
    """Return yaw(rz), pitch(rx), roll(ry), root Y translation for one hook."""
    d = cfg["disturbance"]
    dt = float(cfg["dt_s"])
    sig_a = float(d["angle_tol_deg"]) / 3.0
    tau = float(d["tau_s"])
    jitter = float(d.get("tau_jitter_ratio", 0.0))
    mode = cfg.get("noise_mode", "correlated")
    child = np.random.default_rng(seed_seq.spawn(hook_idx + 1)[-1])
    if mode == "white":
        rz = np.clip(child.normal(0, sig_a, n), -3 * sig_a, 3 * sig_a)
        rx = np.clip(child.normal(0, sig_a, n), -3 * sig_a, 3 * sig_a)
        ry = np.clip(child.normal(0, float(d["ry_sigma_deg"]), n), -3 * float(d["ry_sigma_deg"]), 3 * float(d["ry_sigma_deg"]))
        root_y = np.clip(child.normal(0, float(d["root_y_sigma_mm"]), n), -3 * float(d["root_y_sigma_mm"]), 3 * float(d["root_y_sigma_mm"]))
    else:
        tau_i = tau * float(1.0 + jitter * child.uniform(-1, 1))
        tau_p = tau * float(1.0 + jitter * child.uniform(-1, 1))
        tau_y = tau * float(1.0 + jitter * child.uniform(-1, 1))
        rz = ou_process(child, n, sig_a, tau_i, dt)
        rx = ou_process(child, n, sig_a, tau_p, dt)
        ry = ou_process(child, n, float(d["ry_sigma_deg"]), tau_i, dt)
        root_y = ou_process(child, n, float(d["root_y_sigma_mm"]), tau_y, dt)
    return {"rz_deg": rz, "rx_deg": rx, "ry_deg": ry, "root_y_mm": root_y}
