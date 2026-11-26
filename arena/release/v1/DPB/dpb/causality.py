"""Automated causality test: tampering with future truth must not change past commands."""
from __future__ import annotations

import csv
import shutil
import tempfile
from pathlib import Path

from .config import load_config  # noqa: F401
from .io_utils import write_csv
from .pipeline import run_pipeline
from .sensor_sim import simulate_sensor


def _read(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [list(r.values()) for r in csv.DictReader(fh)]


def check_static_isolation(pkg_dir: Path) -> dict:
    """No DPB decision module may import DPA or reference true hook identity."""
    forbidden_dirs = ["predictors", "planner.py", "stream.py", "tracker.py", "robot_sim.py", "pipeline.py"]
    violations = []
    for name in forbidden_dirs:
        p = Path(pkg_dir) / name
        files = list(p.glob("*.py")) if p.is_dir() else ([p] if p.exists() else [])
        for f in files:
            text = f.read_text(encoding="utf-8")
            for token in ("import dpa", "from dpa", "hook_id", "event_flag", "truth/"):
                if token in text:
                    violations.append(f"{f.name}:{token}")
    return {"violations": violations, "passed": not violations}


def causal_test(dpa_dir: Path, dpb_dir: Path, out_dir: Path, cfg: dict,
                cut_s: float | None = None) -> dict:
    """Tamper with truth after cut_s, regenerate the stream, compare early commands."""
    cut = float(cfg["sim"]["causal_cut_s"] if cut_s is None else cut_s)
    tmp = Path(tempfile.mkdtemp(prefix="gate_causal_"))
    try:
        tampered = tmp / "dpa"
        shutil.copytree(dpa_dir, tampered)
        src = tampered / "truth" / "tip_truth.csv"
        with src.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            header = reader.fieldnames
            rows = list(reader)
        changed = 0
        for r in rows:
            if float(r["t_s"]) > cut:
                r["x_mm"] = str(float(r["x_mm"]) + 500.0)
                r["y_mm"] = str(float(r["y_mm"]) + 50.0)
                r["rz_deg"] = str(float(r["rz_deg"]) + 10.0)
                changed += 1
        write_csv(src, header, [[r[k] for k in header] for r in rows])
        seed = int(__import__("json").loads((tampered / "meta.json").read_text())["seed"])
        sensor_out = tmp / "dpb"
        simulate_sensor(tampered, cfg, sensor_out, seed)
        run_pipeline(sensor_out, cfg, tmp / "pipeline")
    finally:
        pass

    orig_preds = _read(Path(dpb_dir) / "predictions.csv")
    new_preds = _read(tmp / "pipeline" / "predictions.csv")
    orig_cmds = __import__("json").loads((Path(dpb_dir) / "robot_commands.json").read_text())
    new_cmds = __import__("json").loads((tmp / "pipeline" / "robot_commands.json").read_text())
    guard = 0.1
    def early_preds(rows):
        return [r for r in rows if float(r[2]) <= cut - guard]
    def early_cmds(rows):
        return [r for r in rows if float(r["issue_time"]) <= cut - guard]
    a, b = early_preds(orig_preds), early_preds(new_preds)
    ca, cb = early_cmds(orig_cmds), early_cmds(new_cmds)
    pred_equal = a == b
    cmd_equal = ca == cb
    first_pred_diff = None
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            first_pred_diff = {"index": i, "original": x, "tampered": y}
            break
    first_cmd_diff = None
    for i, (x, y) in enumerate(zip(ca, cb)):
        if x != y:
            first_cmd_diff = {"index": i, "original": x, "tampered": y}
            break
    result = {
        "first_pred_diff": first_pred_diff, "first_cmd_diff": first_cmd_diff,
        "cut_s": cut, "n_tampered_truth_rows": changed,
        "n_early_predictions": len(a), "n_early_commands": len(ca),
        "early_predictions_identical": pred_equal, "early_commands_identical": cmd_equal,
        "static_isolation": check_static_isolation(Path(__file__).parent),
        "passed": bool(pred_equal and cmd_equal),
    }
    import json
    (Path(out_dir) / "causal_report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    return result
