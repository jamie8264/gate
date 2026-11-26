"""DPA command line entry point."""
from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .simulator import simulate
from .svg_animation import build_animation


def main() -> None:
    p = argparse.ArgumentParser(description="DPA hook-tip simulator")
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--scenario", default="normal")
    p.add_argument("--noise", choices=["correlated", "white"], default="correlated")
    p.add_argument("--mode", choices=["zone", "full"], default="zone")
    p.add_argument("--out", default="outputs/seed_1")
    args = p.parse_args()
    cfg = load_config(args.config, args.scenario, args.noise)
    cfg["mode"] = args.mode
    summary = simulate(cfg, args.seed, args.out)
    svg = build_animation(Path(args.out), cfg)
    print(f"DPA seed={args.seed} scenario={args.scenario} noise={args.noise} "
          f"rows={summary['n_truth_rows']} hooks={summary['n_hooks_output']} "
          f"duration={summary['duration_s']:.1f}s hash={cfg['config_hash']} "
          f"svg_series={svg['n_series']} svg_frames={svg['frames']}")


if __name__ == "__main__":
    main()
