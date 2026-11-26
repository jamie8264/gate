"""Sensor-side track state. Contains no truth, geometry or event information."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from .stream import SensorFrame

POSE_COLS = ("x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg")


@dataclass
class Track:
    track_id: str
    first_arrival: float
    frames: list[SensorFrame] = field(default_factory=list)
    cmd_count: int = 0
    first_cmd_time: float | None = None
    target_time: float | None = None
    second_issued: bool = False
    done: bool = False
    v_est: float | None = None
    event_suspected: bool = False

    def add(self, frame: SensorFrame, history_s: float) -> None:
        self.frames.append(frame)
        cutoff = frame.t_arrival - history_s
        while self.frames and self.frames[0].t_arrival < cutoff:
            self.frames.pop(0)

    def array(self, t_min: float | None = None) -> np.ndarray:
        """Columns: t_arrival, t_sensor, x,y,z,rx,ry,rz (6 pose dims)."""
        fr = [f for f in self.frames if t_min is None or f.t_arrival >= t_min]
        if not fr:
            return np.zeros((0, 8))
        return np.array(
            [[f.t_arrival, f.t_sensor, *f.pose] for f in fr], dtype=np.float64
        )


def robust_linear_slope(arr: np.ndarray, col: int, window_s: float, min_pts: int = 4,
                        mad_factor: float = 4.0) -> tuple[float | None, int]:
    """Robust OLS slope using residual-based outlier rejection (sensor-only)."""
    if arr.shape[0] < min_pts:
        return None, 0
    t = arr[:, 0]
    keep = t >= t[-1] - window_s
    t, y = t[keep], arr[keep, col]
    if t.size < min_pts or np.ptp(t) < 0.2:
        return None, 0
    a = np.polyfit(t, y, 1)
    resid = y - np.polyval(a, t)
    mad = np.median(np.abs(resid - np.median(resid))) * 1.4826 + 1e-6
    good = np.abs(resid - np.median(resid)) <= mad_factor * mad
    if int(np.count_nonzero(good)) >= min_pts:
        a = np.polyfit(t[good], y[good], 1)
        return float(a[0]), int(np.count_nonzero(good))
    return float(a[0]), int(t.size)


def estimate_tau(tracks: Iterable[Track], cfg: dict) -> float:
    """Pooled online OU correlation time from lag-0.2 s autocorrelation."""
    lag = float(cfg["predictor"]["ou_lag_s"])
    step = max(1, int(round(lag / float(cfg.get("_sensor_dt", 0.01)))))
    ratios: list[float] = []
    for tr in tracks:
        arr = tr.array()
        if arr.shape[0] < step + 20:
            continue
        for col in (3, 4, 5, 7):  # y, z, rx, rz
            a = arr[:-step, col]
            b = arr[step:, col]
            da = a - np.mean(a)
            db = b - np.mean(b)
            denom = float(np.dot(da, da))
            if denom > 1e-6 and np.std(b) > 1e-9:
                r = float(np.dot(da, db) / denom)
                if 0.05 < r < 0.995:
                    ratios.append(-lag / np.log(r))
    lo = float(cfg["predictor"]["tau_min_s"])
    hi = float(cfg["predictor"]["tau_max_s"])
    return float(np.clip(np.median(ratios), lo, hi)) if ratios else 1.2


class Tracker:
    """Holds sensor-only tracks keyed by track_id."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.tracks: dict[str, Track] = {}
        self.entry_times: list[float] = []

    def ingest(self, frames: list[SensorFrame]) -> None:
        hist = float(self.cfg["predictor"]["history_s"])
        for fr in frames:
            tr = self.tracks.get(fr.track_id)
            if tr is None:
                tr = Track(fr.track_id, fr.t_arrival)
                self.tracks[fr.track_id] = tr
                self.entry_times.append(fr.t_arrival)
            tr.add(fr, hist)

    def cadence(self, default_s: float) -> float:
        if len(self.entry_times) < 2:
            return default_s
        gaps = np.diff(sorted(self.entry_times))
        gaps = gaps[(gaps > 1.0) & (gaps < 60.0)]
        return float(np.median(gaps)) if gaps.size else default_s
