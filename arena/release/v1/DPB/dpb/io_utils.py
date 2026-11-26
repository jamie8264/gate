"""Shared CSV/JSON helpers (schema_v1)."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def read_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for row in rows:
            w.writerow([f"{v:.6f}" if isinstance(v, float) else v for v in row])


def write_json(path: Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def f(row: dict[str, str], key: str, aliases: tuple[str, ...] = ()) -> float:
    """Read a float tolerating common column aliases from other DPA outputs."""
    if key in row:
        return float(row[key])
    for a in aliases:
        if a in row:
            return float(row[a])
    raise KeyError(f"missing column {key} (aliases {aliases})")
