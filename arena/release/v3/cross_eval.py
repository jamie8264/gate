"""Cross-evaluation: adapt a foreign DPA output and run our DPB on it (read-only)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from adapters import adapt_dpa

ROOT = Path(__file__).resolve().parents[0]  # self-contained snapshot
PY = Path(sys.executable)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--foreign", required=True, help="foreign DPA output directory (never modified)")
    p.add_argument("--out", required=True)
    p.add_argument("--variant", default="b3")
    args = p.parse_args()
    foreign = Path(args.foreign).resolve()
    out = Path(args.out).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        adapted = Path(tmp) / "adapted"
        log = adapt_dpa(foreign, adapted)
        cmd = [str(PY), "-m", "dpb.cli", "--config", "config/default.yaml",
               "--variant", args.variant, "--dpa", str(adapted), "--out", str(out), "--no-causal"]
        res = subprocess.run(cmd, cwd=str(ROOT / "DPB"), text=True, capture_output=True)
    if res.returncode != 0:
        print(res.stdout[-4000:], res.stderr[-4000:], file=sys.stderr)
        raise SystemExit(res.returncode)
    report = json.loads((out / "eval_report.json").read_text())
    summary = {
        "foreign": str(foreign), "adapter": log,
        "sr_main": report["sr_main"], "score": report["internal_score"],
        "pos_rmse": report["metric1"]["pos_3d"]["rmse"],
        "note": "foreign files are read-only; DPB is unmodified",
    }
    (out / "cross_eval_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
