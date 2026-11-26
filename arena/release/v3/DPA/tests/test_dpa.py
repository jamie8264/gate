"""DPA regression tests: geometry, speed, distributions, reproducibility, schema."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dpa.config import load_config, sigma_from_tol  # noqa: E402
from dpa.hook_model import rotate_tip, sample_hook_params, truncated_normal  # noqa: E402
from dpa.chain_dynamics import simulate_speed  # noqa: E402
from dpa.simulator import simulate  # noqa: E402

CFG = ROOT / "config" / "default.yaml"


def test_tolerances_and_truncation():
    cfg = load_config(CFG)
    p = sample_hook_params(cfg, 7)
    assert p.shape == (700, 5)
    assert np.all(np.abs(p[:, 1] - 100.0) <= 5.0 + 1e-9)
    assert np.all(np.abs(p[:, 2] - 20.0) <= 2.0 + 1e-9)
    assert np.all(np.abs(p[:, 3] - 5.0) <= 1.0 + 1e-9)
    assert abs(p[:, 1].std() - 5 / 3) < 0.3
    assert sigma_from_tol(5, "3sigma") == pytest.approx(5 / 3)


def test_seed_reproducibility_and_independence():
    cfg = load_config(CFG)
    a = sample_hook_params(cfg, 11)
    b = sample_hook_params(cfg, 11)
    c = sample_hook_params(cfg, 12)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_rotation_kinematics():
    pts = np.array([[0.0, 95.0, 40.0]])
    out = rotate_tip(pts, np.array([0.0]), np.array([0.0]), np.array([0.0]))
    assert out[0] == pytest.approx([0, 95, 40])
    out = rotate_tip(pts, np.array([1.0]), np.array([0.0]), np.array([0.0]))
    assert out[0, 0] == pytest.approx(-95 * np.sin(np.deg2rad(1.0)))
    assert out[0, 1] == pytest.approx(95 * np.cos(np.deg2rad(1.0)))


def test_speed_bounds_and_events():
    cfg = load_config(CFG, "event_heavy")
    rng = np.random.default_rng(3)
    sp = simulate_speed(cfg, rng, 20000)
    assert sp["v"].min() >= 20.0 and sp["v"].max() <= 80.0
    assert sp["event_flag"].sum() > 0
    assert np.allclose(sp["noise_sigma"][sp["event_flag"]], 12.0 / 3.0)


def test_simulate_schema_and_reproducibility(tmp_path):
    cfg = load_config(CFG, "normal", "correlated")
    out1, out2 = tmp_path / "a", tmp_path / "b"
    simulate(cfg, 5, out1)
    simulate(cfg, 5, out2)
    for rel in ["meta.json", "truth/hooks_params.csv", "truth/chain_speed.csv", "truth/tip_truth.csv"]:
        assert (out1 / rel).read_bytes() == (out2 / rel).read_bytes(), rel
    meta = json.loads((out1 / "meta.json").read_text())
    assert meta["schema_version"] == "schema_v1"
    with (out1 / "truth" / "tip_truth.csv").open() as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == ["t_s", "hook_id", "x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg", "in_sensor_fov", "in_robot_zone"]
        rows = list(reader)
    unique_hooks = {int(r["hook_id"]) for r in rows}
    assert len(unique_hooks) >= 30
    assert all(np.isfinite(float(r[k])) for r in rows for k in ("x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg"))
