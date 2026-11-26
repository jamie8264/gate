"""Prediction algorithms. Inputs are sensor-side tracks only (no truth)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import config_hash  # noqa: F401  (schema consistency marker)
from ..tracker import Track, Tracker, robust_linear_slope, estimate_tau

POSE = ("x", "y", "z", "rx", "ry", "rz")


@dataclass
class Prediction:
    pose: tuple[float, float, float, float, float, float]
    sigma_pos_mm: float
    diagnostics: dict



def corrected_array(arr: np.ndarray, cfg: dict) -> np.ndarray:
    """Remove the nominal yaw-induced X offset from measured tip positions.

    Uses only the nominal lever from the task specification and the sensor's
    own Rz measurement -- never a hook's true geometric parameters.
    """
    p = cfg["predictor"]
    if not p.get("use_attitude_decorrelation", False) or arr.shape[0] == 0:
        return arr
    out = arr.copy()
    lever = float(p.get("yaw_lever_mm", 95.0))
    out[:, 2] = arr[:, 2] + lever * np.sin(np.deg2rad(arr[:, 7]))
    return out

def _median_last(arr: np.ndarray, col: int, window_s: float = 0.3) -> float:
    keep = arr[:, 0] >= arr[-1, 0] - window_s
    return float(np.median(arr[keep, col]))



def _current_value(arr: np.ndarray, col: int, window_s: float = 0.3) -> float:
    """Trend-corrected estimate of the value at the latest observation time.

    A plain median over the last window lags a linearly moving quantity by
    half the window (up to 12 mm at 80 mm/s); OLS evaluated at t_max removes
    that bias while still suppressing sensor noise.
    """
    keep = arr[:, 0] >= arr[-1, 0] - window_s
    t, y = arr[keep, 0], arr[keep, col]
    if t.size < 3 or np.ptp(t) < 0.05:
        return float(y[-1])
    slope, intercept = np.polyfit(t - t[-1], y, 1)
    return float(intercept)

def _ou_mean(arr: np.ndarray, col: int, horizon: float, tau: float, window_s: float) -> float:
    cur = _current_value(arr, col)
    base = float(np.median(arr[:, col]))
    return float(base + (cur - base) * np.exp(-horizon / tau))



def _weighted_slope(arr: np.ndarray, col: int, window_s: float, half_life_s: float,
                    min_pts: int = 4) -> float | None:
    """Exponentially weighted OLS slope: recent observations dominate."""
    t = arr[:, 0]
    keep = t >= t[-1] - window_s
    t, y = t[keep], arr[keep, col]
    if t.size < min_pts or np.ptp(t) < 0.2:
        return None
    w = np.exp(-(t[-1] - t) / max(0.1, half_life_s))
    X = np.column_stack((np.ones_like(t), t - t[-1]))
    W = np.sqrt(w)[:, None]
    beta, *_ = np.linalg.lstsq(X * W, y * np.sqrt(w), rcond=None)
    return float(beta[1])

def _shared_slope(tracker: Tracker, cfg: dict, t_now: float) -> tuple[float | None, dict]:
    slopes = []
    for tr in tracker.tracks.values():
        arr = corrected_array(tr.array(t_now - float(cfg["predictor"]["velocity_window_s"])), cfg)
        s, n = robust_linear_slope(arr, 2, float(cfg["predictor"]["velocity_window_s"]),
                                   int(cfg["predictor"]["velocity_min_frames"]),
                                   float(cfg["predictor"]["outlier_mad_factor"]))
        if s is not None and n >= 8:
            slopes.append(s)
    if not slopes:
        return None, {"n_shared": 0}
    return float(np.median(slopes)), {"n_shared": len(slopes), "v_shared_spread": float(np.std(slopes))}



def _global_speed_model(tracker: Tracker, cfg: dict, t_now: float):
    """Joint fit x_i(t)=b_i+v0*dt+0.5*a*dt^2 over all visible tracks.

    Per-track intercepts absorb static geometry and slow yaw offsets, so the
    velocity estimate is not biased by an individual hook's disturbance.
    """
    window = float(cfg["predictor"].get("global_window_s", 3.0))
    rows = []
    tracks = list(tracker.tracks.values())
    for idx, tr in enumerate(tracks):
        arr = corrected_array(tr.array(t_now - window), cfg)
        if arr.shape[0] < 10:
            continue
        for f in arr:
            dt = float(f[0]) - t_now
            rows.append((idx, dt, float(f[2])))
    if len(rows) < 40:
        return None, 0.0, {"n_global": 0}
    n = len(tracks)
    X = np.zeros((len(rows), n + 2))
    y = np.empty(len(rows))
    for k, (idx, dt, x) in enumerate(rows):
        X[k, idx] = 1.0
        X[k, n] = dt
        X[k, n + 1] = 0.5 * dt * dt
        y[k] = x
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(beta[n]), float(2.0 * beta[n + 1]), {"n_global": len(rows), "n_tracks_fit": len(set(r[0] for r in rows))}


def _ridge_velocity_correction(tracker: Tracker, cfg: dict, t_now: float):
    """Self-supervised ridge fit of short-horizon velocity residuals.

    Labels come only from sensor frames already arrived (x at t+0.3 s), never
    from DPA truth. Returns coefficients for [dv*H, 0.5*a*H^2].
    """
    p = cfg["predictor"]
    window = float(p.get("b4_window_s", 6.0))
    lag = float(p.get("ou_lag_s", 0.2))
    Xs, ys = [], []
    for tr in tracker.tracks.values():
        arr = tr.array(t_now - window)
        if arr.shape[0] < 80:
            continue
        for i in range(60, len(arr) - 30, 20):
            t = arr[i, 0]
            if t + lag > arr[-1, 0]:
                break
            past = arr[(arr[:, 0] >= t - 1.0) & (arr[:, 0] <= t)]
            if past.shape[0] < 10:
                continue
            v = robust_linear_slope(past, 2, 1.0, 6)[0]
            if v is None:
                continue
            x0 = float(np.median(past[-5:, 2]))
            j = int(np.argmin(np.abs(arr[:, 0] - (t + lag))))
            x1 = float(arr[j, 2])
            dv = v - float(np.median(past[:, 2]) - np.median(arr[:max(1, i // 2), 2]) + v * (t - np.median(past[:, 0])))
            dv = float(v - np.median([robust_linear_slope(arr[max(0, k - 60):k + 1], 2, 1.0, 6)[0] or v
                                      for k in range(max(60, i - 300), i + 1, 60)]))
            c = np.polyfit(past[:, 0] - t, past[:, 2], 2) if past.shape[0] >= 8 else np.zeros(3)
            a = float(np.clip(2.0 * c[0], -25.0, 25.0))
            Xs.append([dv * lag, 0.5 * a * lag * lag])
            ys.append(x1 - x0 - v * lag)
    if len(Xs) < 20:
        return None
    X = np.asarray(Xs)
    y = np.asarray(ys)
    lam = float(p.get("b4_ridge_lambda", 1.0))
    beta = np.linalg.solve(X.T @ X + lam * np.eye(2), X.T @ y)
    return beta

def predict(track: Track, tracker: Tracker, t_issue: float, t_target: float, cfg: dict) -> Prediction:
    """Predict the 6-D pose at t_target using only frames with arrival<=t_issue."""
    p = cfg["predictor"]
    variant = p.get("variant", "b3")
    arr = track.array()
    arr_corr = corrected_array(arr, cfg)
    if arr.shape[0] == 0:
        raise ValueError("prediction without sensor frames")
    H = max(0.0, float(t_target) - float(t_issue))
    x_now = _current_value(arr_corr, 2)
    if variant == "b0":
        idx = max(0, len(arr) - 2)
        dt = max(1e-3, arr[-1, 0] - arr[idx, 0])
        v = float((arr[-1, 2] - arr[idx, 2]) / dt)
        pose = (x_now + v * H, *[_median_last(arr, c) for c in (3, 4, 5, 6, 7)])
        return Prediction(pose, 0.5 + abs(v) * H * 0.05, {"variant": "b0", "v": v})

    vel_window = float(p["velocity_window_s"])
    half_life = float(p.get("velocity_half_life_s", 0.0))
    if half_life > 0 and variant in ("b3", "b4"):
        v_local = _weighted_slope(arr_corr, 2, vel_window, half_life, int(p["velocity_min_frames"]))
        n_pts = int(np.count_nonzero(arr[:, 0] >= arr[-1, 0] - vel_window))
    else:
        v_local, n_pts = robust_linear_slope(arr_corr, 2, vel_window,
                                             int(p["velocity_min_frames"]),
                                             float(p["outlier_mad_factor"]))
    v_shared, diag = _shared_slope(tracker, cfg, t_issue)
    if v_local is None:
        v_local = v_shared if v_shared is not None else 0.0
    if v_shared is None:
        v_shared = v_local
    residual = abs(v_local - v_shared)
    event = residual > float(cfg["planner"]["event_residual_threshold_mm_s"])
    w_shared = float(p["shared_weight"]) if variant in ("b3", "b4") else 1.0 if variant == "b2" else 0.0
    if event:
        w_shared *= 0.25
    v_hat = (1.0 - w_shared) * v_local + w_shared * v_shared
    v_global, a_global, gdiag = _global_speed_model(tracker, cfg, t_issue)
    wg = float(p.get("global_weight", 0.0)) if variant in ("b3", "b4") else 0.0
    if v_global is not None:
        v_hat = (1.0 - wg) * v_hat + wg * v_global
        diag["v_global"] = v_global

    accel = 0.0
    accel_raw = 0.0
    if variant in ("b3", "b4"):
        aw = float(p["accel_window_s"])
        sel = arr[:, 0] >= arr[-1, 0] - aw
        tt, xx = arr_corr[sel, 0] - arr_corr[-1, 0], arr_corr[sel, 2]
        if tt.size >= 8 and np.ptp(tt) > 0.5:
            c = np.polyfit(tt, xx, 2)
            accel_raw = float(np.clip(2.0 * c[0], -float(p["accel_cap_mm_s2"]), float(p["accel_cap_mm_s2"])))
            dyn_event = event or abs(accel_raw) > float(p.get("event_accel_threshold", 8.0))
            kappa = float(p["accel_kappa"]) + (float(p.get("event_accel_kappa", 0.0)) if dyn_event else 0.0)
            accel = accel_raw * kappa
            diag["dyn_event"] = bool(dyn_event)
    # Curvature is only trustworthy over a short span: never extrapolate a
    # noisy quadratic fit across a long command horizon.
    eff_H = min(H, 2.0)
    accel_cap = float(p.get("accel_cap_correction_mm", 12.0))
    accel_correction = float(np.clip(0.5 * accel * eff_H * eff_H, -accel_cap, accel_cap))
    x_pred = x_now + v_hat * H + accel_correction

    tau = estimate_tau(tracker.tracks.values(), cfg) if variant != "b1" else 1.2
    angles = []
    for col in (3, 4, 5, 6, 7):  # y,z,rx,ry,rz
        angles.append(_ou_mean(arr, col, H, tau, float(p["history_s"])))
    if variant == "b4":
        beta = _ridge_velocity_correction(tracker, cfg, t_issue)
        if beta is not None:
            dv = float(v_local - v_shared)
            corr = float(p.get("b4_ridge_weight", 0.5)) * (
                beta[0] * dv * H + beta[1] * 0.5 * accel_raw * H * H)
            x_pred += float(np.clip(corr, -20.0, 20.0))
            diag["ridge_corr"] = corr
    if p.get("use_attitude_decorrelation", False) and variant in ("b2", "b3", "b4"):
        lever = float(p.get("yaw_lever_mm", 95.0))
        x_pred -= lever * np.sin(np.deg2rad(float(angles[4])))
    pose = (x_pred, *angles)
    sig_a = float(p["sigma_floor_ang_deg"])
    decay = np.sqrt(max(0.0, 1.0 - np.exp(-2.0 * H / tau)))
    sigma_pos = float(max(float(p["sigma_floor_pos_mm"]),
                          np.sqrt((3.0 * decay) ** 2 + (abs(diag.get("v_shared_spread", 2.0)) * H * 0.3) ** 2)))
    diag.update(gdiag)
    diag.update({"variant": variant, "v_local": v_local, "v_shared": v_shared, "v_hat": v_hat,
                 "tau_hat": tau, "accel": accel, "accel_correction": accel_correction, "event_suspected": event, "n_pts": n_pts})
    return Prediction(tuple(float(v) for v in pose), sigma_pos, diag)
