"""Per-hook geometry sampled once and kept fixed for the whole run."""
from __future__ import annotations

import numpy as np

from .config import sigma_from_tol


def truncated_normal(rng: np.random.Generator, sigma: float, size: int, n_sigma: float = 3.0) -> np.ndarray:
    """Vectorised rejection sampling from a zero-mean truncated normal."""
    out = rng.normal(0.0, sigma, size=size)
    pending = np.abs(out) > n_sigma * sigma
    while np.any(pending):
        n = int(np.count_nonzero(pending))
        out[pending] = rng.normal(0.0, sigma, size=n)
        pending = np.abs(out) > n_sigma * sigma
    return out


def sample_hook_params(cfg: dict, seed: int) -> np.ndarray:
    """Return (n_hooks, 5) array: chain_pos, L, r, R, install_jitter.

    Each hook gets its own spawned stream, so simulating a subset yields the
    same parameters as simulating the full chain.
    """
    n = int(cfg["n_hooks"])
    spacing = float(cfg["chain_length_mm"]) / n
    ss = np.random.SeedSequence(seed).spawn(n + 1)
    result = np.empty((n, 5), dtype=np.float64)
    hook_cfg = cfg["hook"]
    mode = hook_cfg.get("sigma_mode", "3sigma")
    sL = sigma_from_tol(hook_cfg["length_tol_mm"], mode)
    sr = sigma_from_tol(hook_cfg["arc_radius_tol_mm"], mode)
    sR = sigma_from_tol(hook_cfg["tip_radius_tol_mm"], mode)
    sj = sigma_from_tol(cfg["install_jitter_mm"], mode)
    for i in range(n):
        r = np.random.default_rng(ss[i])
        result[i] = (
            (i * spacing) % float(cfg["chain_length_mm"]),
            hook_cfg["length_mm"] + truncated_normal(r, sL, 1)[0],
            hook_cfg["arc_radius_mm"] + truncated_normal(r, sr, 1)[0],
            hook_cfg["tip_radius_mm"] + truncated_normal(r, sR, 1)[0],
            truncated_normal(r, sj, 1)[0],
        )
    result[:, 0] += result[:, 4]
    result[:, 0] %= float(cfg["chain_length_mm"])
    return result


def local_tip(params: np.ndarray, cfg: dict) -> np.ndarray:
    """Local apex/centre point of one hook in its root frame, shape (3,)."""
    L, r, R = float(params[1]), float(params[2]), float(params[3])
    if cfg["hook"].get("tip_ref", "apex") == "center":
        py = L
    else:
        py = L - R
    if cfg["hook"].get("arc_plane", "vertical") == "horizontal":
        # Half-circle bends in the XY plane: the height term becomes X.
        return np.array([2.0 * r, py, 0.0])
    return np.array([0.0, py, 2.0 * r])


def rotate_tip(points: np.ndarray, rz_deg: np.ndarray, rx_deg: np.ndarray,
               ry_deg: np.ndarray, root_y: np.ndarray | None = None) -> np.ndarray:
    """Apply ZYX Euler rotation to local points.

    points: (N,3), angle arrays: (N,); returns world offsets (N,3).
    """
    cz, sz = np.cos(np.deg2rad(rz_deg)), np.sin(np.deg2rad(rz_deg))
    cx, sx = np.cos(np.deg2rad(rx_deg)), np.sin(np.deg2rad(rx_deg))
    cy, sy = np.cos(np.deg2rad(ry_deg)), np.sin(np.deg2rad(ry_deg))
    p = np.asarray(points, dtype=np.float64)
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    # Rx then Ry then Rz (ZYX convention applied to the local vector).
    x1, y1, z1 = x, cx * y - sx * z, sx * y + cx * z
    x2, y2, z2 = cy * x1 + sy * z1, y1, -sy * x1 + cy * z1
    out = np.column_stack((cz * x2 - sz * y2, sz * x2 + cz * y2, z2))
    if root_y is not None:
        out[:, 1] += root_y
    return out
