"""DPB configuration loading and canonical hashing."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


def config_hash(cfg: dict[str, Any]) -> str:
    canonical = json.dumps(cfg, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def load_config(path: str | Path, scenario: str = "normal", variant: str = "b3") -> dict[str, Any]:
    cfg = copy.deepcopy(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
    preset = cfg.get("scenarios", {}).get(scenario, {})
    for k, v in preset.items():
        cfg["sensor"][k] = v
    cfg["predictor"]["variant"] = variant
    cfg["scenario"] = scenario
    cfg["config_hash"] = config_hash(cfg)
    return cfg
