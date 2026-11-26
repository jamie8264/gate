"""DPB tests: schema, sensor causality, stream gating, predictor isolation."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dpb.config import load_config  # noqa: E402
from dpb.evaluator import geodesic_deg  # noqa: E402
from dpb.io_utils import read_csv  # noqa: E402
from dpb.robot_sim import Command, RobotSim  # noqa: E402
from dpb.stream import StreamReplayer  # noqa: E402
from dpb.causality import check_static_isolation  # noqa: E402

CFG = ROOT / "config" / "default.yaml"
DPA = ROOT.parent / "DPA" / "outputs" / "seed_1_normal_correlated"


def test_geodesic_identity():
    assert geodesic_deg((0, 0, 0), (0, 0, 0)) == pytest.approx(0.0)
    assert geodesic_deg((0, 0, 0), (5, 0, 0)) == pytest.approx(5.0, abs=1e-6)


def test_robot_delay_and_preemption():
    cfg = load_config(CFG)
    r = RobotSim(cfg)
    c1 = Command("C1", "T1", 0.0, 4.0, (200.0, 95.0, 40.0, 0, 0, 0), 0, 0, 1)
    r.add(c1)
    r.advance(0, 0.4)
    assert r.pose_at(0.4) == r.home
    r.advance(0.4, 0.6)
    assert c1.start_time == pytest.approx(0.5)
    c2 = Command("C2", "T2", 1.0, 3.0, (0.0, 95.0, 40.0, 0, 0, 0), 0, 0, 2)
    r.add(c2)
    r.advance(1.0, 1.5)
    assert c2.start_time == pytest.approx(1.5)
    assert c1.cancelled
    assert r.pose_at(3.0)[:3] == pytest.approx((0.0, 95.0, 40.0))


@pytest.mark.skipif(not (DPA / "meta.json").exists(), reason="DPA fixture not generated")
def test_stream_gating_is_causal():
    cfg = load_config(CFG)
    dpb_out = ROOT / "outputs" / "seed_1_normal_correlated"
    stream = dpb_out / "sensor_stream.csv"
    if not stream.exists():
        pytest.skip("DPB fixture not generated")
    r = StreamReplayer(stream)
    t_cut = 100.0
    early = r.up_to(t_cut)
    r.advancing_frames(t_cut)
    assert len(r.advancing_frames(1e9)) == len(r.frames) - len(early)
    assert all(f.t_arrival <= t_cut for f in early)
    assert all(f.t_arrival > t_cut for f in r.advancing_frames(1e9))


@pytest.mark.skipif(not (DPA / "meta.json").exists(), reason="DPA fixture not generated")
def test_outputs_schema_and_causal_report():
    out = ROOT / "outputs" / "seed_1_normal_correlated"
    if not (out / "eval_report.json").exists():
        pytest.skip("DPB fixture not generated")
    pred = read_csv(out / "predictions.csv")
    assert list(pred[0].keys()) == ["track_id", "cmd_id", "t_issue_s", "t_target_s", "horizon_s",
                                   "x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg", "sigma_pos_mm"]
    assert all(2.0 - 1e-6 <= float(r["horizon_s"]) <= 10.0 + 1e-6 for r in pred)
    cmds = json.loads((out / "robot_commands.json").read_text())
    assert all(c["communication_delay"] == 0.5 for c in cmds)
    rep = json.loads((out / "causal_report.json").read_text())
    assert rep["passed"] and rep["early_commands_identical"]
    assert check_static_isolation(ROOT / "dpb")["passed"]


def test_config_hash_stability():
    a = load_config(CFG, "normal", "b3")
    b = load_config(CFG, "normal", "b3")
    assert a["config_hash"] == b["config_hash"]
    assert len(a["config_hash"]) == 12
