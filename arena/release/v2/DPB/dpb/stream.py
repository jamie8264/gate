"""Causal stream gate: at time t only frames with t_arrival <= t are visible."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .io_utils import read_csv, f as read_float


@dataclass(frozen=True)
class SensorFrame:
    track_id: str
    t_sensor: float
    t_arrival: float
    pose: tuple[float, float, float, float, float, float]

    @property
    def x(self) -> float:
        return self.pose[0]


class StreamReplayer:
    """Sorted stream with a monotonically advancing arrival-time cursor."""

    def __init__(self, path: str | Path):
        rows = read_csv(Path(path))
        self.frames = [
            SensorFrame(
                track_id=str(r["track_id"]),
                t_sensor=read_float(r, "t_sensor_s"),
                t_arrival=read_float(r, "t_arrival_s"),
                pose=tuple(read_float(r, k) for k in
                           ("x_mm", "y_mm", "z_mm", "rx_deg", "ry_deg", "rz_deg")),
            )
            for r in rows if int(float(r["valid"])) == 1
        ]
        self.frames.sort(key=lambda f: f.t_arrival)
        self._cursor = 0

    def advancing_frames(self, t_now: float) -> list[SensorFrame]:
        """Return all frames that arrived since the previous call and <= t_now."""
        out = []
        while self._cursor < len(self.frames) and self.frames[self._cursor].t_arrival <= t_now + 1e-12:
            out.append(self.frames[self._cursor])
            self._cursor += 1
        return out

    def up_to(self, t_now: float) -> list[SensorFrame]:
        """Pure (non-consuming) view of all frames with t_arrival <= t_now."""
        import bisect
        times = [f.t_arrival for f in self.frames]
        n = bisect.bisect_right(times, t_now + 1e-12)
        return self.frames[:n]
