"""Global chain speed: bounded OU process plus Poisson speed events."""
from __future__ import annotations

import numpy as np

from .config import sigma_from_tol


def simulate_speed(cfg: dict, rng: np.random.Generator, n_steps: int) -> dict[str, np.ndarray]:
    """Simulate v(t), event flags, noise sigma and cumulative chain position."""
    dt = float(cfg["dt_s"])
    sp = cfg["speed"]
    ev = sp["event"]
    t = np.arange(n_steps) * dt
    v0 = float(sp["v0_mm_s"])
    tau = float(sp["ou_tau_s"])
    rho = float(np.exp(-dt / tau))
    sig_base = sigma_from_tol(sp["normal_tol_mm_s"], sp["noise_sigma_mode"])
    sig_ou = float(sp["ou_sigma_mm_s"])
    eps = rng.standard_normal(n_steps)
    v_ou = np.empty(n_steps)
    v_ou[0] = v0
    innov = sig_ou * np.sqrt(1.0 - rho * rho)
    for k in range(1, n_steps):
        v_ou[k] = v0 + (v_ou[k - 1] - v0) * rho + innov * eps[k]

    lam = float(ev["lambda_per_s"])
    event_offset = np.zeros(n_steps)
    event_flag = np.zeros(n_steps, dtype=bool)
    tt = 0.0
    while True:
        tt += float(rng.exponential(1.0 / lam)) if lam > 0 else 1e12
        if tt >= t[-1]:
            break
        start = tt
        ramp = float(rng.uniform(ev["ramp_min_s"], ev["ramp_max_s"]))
        settle = float(ev["settle_s"])
        amp = float(rng.uniform(ev["amp_min_mm_s"], ev["amp_max_mm_s"]))
        amp *= -1.0 if rng.random() < 0.5 else 1.0
        end = start + 2.0 * ramp + settle
        idx = np.where((t >= start) & (t < end))[0]
        if idx.size == 0:
            continue
        rel = t[idx] - start
        profile = np.where(
            rel < ramp, rel / ramp,
            np.where(rel < ramp + settle, 1.0,
                     np.maximum(0.0, (end - t[idx]) / ramp)),
        )
        event_offset[idx] += amp * profile
        event_flag[idx] = True

    sig_event = sigma_from_tol(ev["event_tol_mm_s"], sp["noise_sigma_mode"])
    noise_sigma = np.where(event_flag, sig_event, sig_base)
    v = np.clip(v_ou + event_offset, float(sp["v_min_mm_s"]), float(sp["v_max_mm_s"]))
    s = np.cumsum(v) * dt
    return {"t": t, "v": v, "event_flag": event_flag, "noise_sigma": noise_sigma, "s": s}
