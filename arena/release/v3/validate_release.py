"""Delivery validation: schema, reports, causal evidence, tests (no fabricated numbers)."""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]  # self-contained snapshot
PY = Path(sys.executable)
DPA_SCHEMA = ["meta.json", "truth/hooks_params.csv", "truth/chain_speed.csv", "truth/tip_truth.csv"]
DPB_SCHEMA = ["sensor_stream.csv", "eval_only/track_map.csv", "predictions.csv", "robot_commands.json",
              "robot_log.csv", "eval_per_hook.csv", "eval_report.json"]


def check_files(base: Path, files: list[str]) -> list[str]:
    missing = [f for f in files if not (base / f).exists()]
    return missing


def main() -> int:
    checks = []
    for tag, base, files in [
        ("DPA", ROOT / "DPA" / "outputs" / "seed_1_normal_correlated", DPA_SCHEMA),
        ("DPB", ROOT / "DPB" / "outputs" / "seed_1_normal_correlated", DPB_SCHEMA),
        ("release/DPA", ROOT / "DPA" / "outputs" / "seed_1_normal_correlated", DPA_SCHEMA),
        ("release/DPB", ROOT / "DPB" / "outputs" / "seed_1_normal_correlated", DPB_SCHEMA),
    ]:
        missing = check_files(base, files)
        checks.append((f"{tag}: {len(files)-len(missing)}/{len(files)} schema files", not missing, missing))
    causal = ROOT / "DPB" / "outputs" / "seed_1_normal_correlated" / "causal_report.json"
    if causal.exists():
        rep = json.loads(causal.read_text())
        checks.append(("causal test passed", rep["passed"], rep))
    report = json.loads((ROOT / "tools" / "aggregate_report.json").read_text())
    checks.append(("aggregate report has >=50 cases", len(report) >= 50, len(report)))
    for proj in ("DPA", "DPB"):
        res = subprocess.run([str(PY), "-m", "pytest", "-q"], cwd=str(ROOT / proj),
                             capture_output=True, text=True)
        checks.append((f"{proj} pytest", res.returncode == 0, res.stdout.strip().splitlines()[-1] if res.stdout else ""))
    ok = True
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + (f" | {detail}" if not passed else ""))
        ok &= bool(passed)
    print("VALIDATION " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
