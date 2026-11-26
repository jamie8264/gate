"""DPB command line entry point."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .causality import causal_test
from .config import load_config
from .evaluator import evaluate
from .pipeline import run_pipeline
from .sensor_sim import simulate_sensor


def main() -> None:
    p = argparse.ArgumentParser(description="DPB sensor-prediction-robot-evaluation pipeline")
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--dpa", required=True, help="directory containing DPA schema_v1 outputs")
    p.add_argument("--out", required=True)
    p.add_argument("--scenario", default=None)
    p.add_argument("--variant", default=None, choices=["b0", "b1", "b2", "b3", "b4"])
    p.add_argument("--no-causal", action="store_true")
    args = p.parse_args()

    dpa_meta = json.loads((Path(args.dpa) / "meta.json").read_text(encoding="utf-8"))
    scenario = args.scenario or dpa_meta.get("scenario", "normal")
    cfg = load_config(args.config, scenario, args.variant or "b3")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sensor_info = simulate_sensor(Path(args.dpa), cfg, out, int(dpa_meta["seed"]))
    pipeline_info = run_pipeline(out, cfg, out)
    report = evaluate(Path(args.dpa), out, cfg, out)
    causal = {"skipped": True}
    if not args.no_causal:
        causal = causal_test(Path(args.dpa), out, out, cfg)
    summary = {
        "sensor": sensor_info, "pipeline": pipeline_info,
        "sr_main": report["sr_main"], "score": report["internal_score"],
        "causal": causal,
    }
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"DPB scenario={scenario} variant={cfg['predictor']['variant']} tracks={pipeline_info['n_tracks']} "
          f"cmds={pipeline_info['n_commands']} SR_main={report['sr_main']:.4f} "
          f"S={report['internal_score']:.2f} causal={causal.get('passed', 'skipped')} out={out}")


if __name__ == "__main__":
    main()
