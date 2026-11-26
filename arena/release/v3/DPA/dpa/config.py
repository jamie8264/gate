"""Configuration loading, scenario overrides, deterministic config hashing."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


def config_hash(cfg: dict[str, Any]) -> str:
    """Stable 12-hex hash of a canonical JSON representation of a config."""
    canonical = json.dumps(cfg, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def load_config(path: str | Path, scenario: str = "normal", noise: str = "correlated") -> dict[str, Any]:
    """Load YAML and apply a named scenario plus noise-mode settings."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    cfg = copy.deepcopy(raw)
    preset = cfg.get("scenarios", {}).get(scenario)
    if preset is None:
        raise ValueError(f"unknown scenario: {scenario}")
    for key, value in preset.items():
        if key == "event_lambda_scale":
            cfg["speed"]["event"]["lambda_per_s"] *= float(value)
        elif key == "noise_scale":
            cfg["disturbance"]["angle_tol_deg"] = float(cfg["disturbance"]["angle_tol_deg"]) * float(value)
            cfg["speed"]["event"]["event_tol_mm_s"] = float(cfg["speed"]["event"]["event_tol_mm_s"]) * float(value)
        elif key == "v0_mm_s":
            cfg["speed"]["v0_mm_s"] = float(value)
        else:
            cfg["disturbance"][key] = value
    cfg["noise_mode"] = noise
    cfg["scenario"] = scenario
    cfg["config_hash"] = config_hash(cfg)
    return cfg


def sigma_from_tol(tol: float, mode: str) -> float:
    """Tolerance -> sigma: '+/-x' means 3-sigma by default."""
    if mode == "3sigma":
        return float(tol) / 3.0
    if mode == "sigma":
        return float(tol)
    raise ValueError(f"unknown sigma mode: {mode}")
