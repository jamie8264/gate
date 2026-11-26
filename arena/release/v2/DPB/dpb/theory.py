"""Theoretical prediction floor and perfect-prediction success ceiling."""
from __future__ import annotations

import math

import numpy as np


def ou_sigma(sigma0: float, horizon: float, tau: float) -> float:
    """Perfect-filter prediction error std for a stationary OU process."""
    return float(sigma0 * math.sqrt(max(0.0, 1.0 - math.exp(-2.0 * horizon / tau))))


def component_floor(cfg_dpa: dict, horizon: float, tau: float) -> dict[str, float]:
    """Analytic sigma of the six tip components at a given horizon."""
    d = cfg_dpa["disturbance"]
    sig_a = float(d["angle_tol_deg"]) / 3.0
    sig_y = float(d["root_y_sigma_mm"])
    L = float(cfg_dpa["hook"]["length_mm"])
    R = float(cfg_dpa["hook"]["tip_radius_mm"])
    lever = L - R
    decay = math.exp(-horizon / tau)
    # OU residual is sigma*sqrt(1-exp(-2H/tau)); the conditional mean of the
    # static geometry offset leaves only the residual random part.
    r = math.sqrt(max(0.0, 1.0 - decay * decay))
    sx = math.radians(sig_a) * lever * r
    sz = math.radians(sig_a) * lever * r
    sy = math.hypot(sig_y * r, math.radians(sig_a) * 40.0 * r)
    return {"x_mm": sx, "y_mm": sy, "z_mm": sz,
            "rx_deg": sig_a * r, "ry_deg": float(d["ry_sigma_deg"]) * r,
            "rz_deg": sig_a * r}


def success_ceiling(pos_sig: tuple[float, float, float], ang_sig: tuple[float, float, float],
                    thresholds: list[dict], n: int = 200000, seed: int = 12345) -> dict[str, float]:
    """Monte-Carlo ceiling P(|dp|<=p_th and geodesic<=a_th) for Gaussian errors."""
    rng = np.random.default_rng(seed)
    dp = rng.normal(size=(n, 3)) * np.asarray(pos_sig)
    dr = rng.normal(size=(n, 3)) * np.asarray(ang_sig)
    pos = np.linalg.norm(dp, axis=1)
    ang = np.linalg.norm(dr, axis=1)  # small-angle geodesic approximation
    return {str(t["name"]): float(np.mean((pos <= float(t["pos_mm"])) & (ang <= float(t["ang_deg"]))))
            for t in thresholds}


def speed_forecast_sigma(sigma_v: float, horizon: float, tau_v: float) -> float:
    """Std of future mean chain speed error from an OU baseline over H."""
    return float(sigma_v * math.sqrt(max(0.0, 1.0 - math.exp(-2.0 * horizon / tau_v))) * horizon)
