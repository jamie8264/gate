"""Deterministic robot kinematics with 0.5 s communication delay and preemption."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class Command:
    command_id: str
    track_id: str
    issue_time: float
    target_time: float
    target_pose: tuple[float, float, float, float, float, float]
    move_distance: float
    estimated_travel_time: float
    sequence: int
    start_time: float = 0.0
    arrive_time: float = 0.0
    actual_distance: float = 0.0
    cancelled: bool = False


@dataclass
class Segment:
    start_time: float
    start_pose: tuple[float, float, float, float, float, float]
    target_pose: tuple[float, float, float, float, float, float]
    duration: float
    command_id: str


class RobotSim:
    """Piecewise-linear TCP motion; later commands supersede earlier ones."""

    def __init__(self, cfg: dict):
        r = cfg["robot"]
        self.speed = float(r["speed_mm_s"])
        self.delay = float(r["comm_delay_s"])
        self.home = (
            float(r["home_x_mm"]),
            float(r["home_y_nominal_mm"]) + float(r["home_y_offset_mm"]),
            float(r["home_z_nominal_mm"]),
            0.0, 0.0, 0.0,
        )
        self.pending: list[Command] = []
        self.commands: list[Command] = []
        self.segments: list[Segment] = []
        self._seq = 0

    def add(self, cmd: Command) -> Command:
        self._seq += 1
        cmd.sequence = self._seq
        self.pending.append(cmd)
        self.commands.append(cmd)
        return cmd

    def predicted_position(self, t: float) -> tuple[float, float, float]:
        p = self.pose_at(t)
        # Account for commands already issued that will start before t.
        for cmd in self.pending:
            if cmd.issue_time <= t < cmd.issue_time + self.delay:
                pass
        return p[:3]

    def pose_at(self, t: float) -> tuple[float, float, float, float, float, float]:
        if not self.segments:
            return self.home
        seg = None
        # Segments are appended in start-time order; a later start preempts.
        for s in self.segments:
            if s.start_time <= t + 1e-12:
                seg = s
            else:
                break
        if seg is None:
            return self.home
        u = 0.0 if seg.duration <= 0 else min(1.0, max(0.0, (t - seg.start_time) / seg.duration))
        pos = tuple(a + (b - a) * u for a, b in zip(seg.start_pose[:3], seg.target_pose[:3]))
        # Rotation is treated as instantaneous at the target (H11).
        rot = seg.target_pose[3:] if u >= 1.0 else seg.start_pose[3:]
        return (*pos, *rot)

    def advance(self, t_from: float, t_to: float) -> None:
        """Apply all command start events in (t_from, t_to] in chronological order."""
        starts = []
        for cmd in self.pending:
            ts = cmd.issue_time + self.delay
            if t_from < ts <= t_to + 1e-12:
                starts.append((ts, cmd.sequence, cmd))
        starts.sort(key=lambda item: (item[0], item[1]))
        for ts, _, cmd in starts:
            current = self.pose_at(ts)
            d = math.dist(current[:3], cmd.target_pose[:3])
            dur = d / self.speed
            cmd.start_time = ts
            cmd.arrive_time = ts + dur
            cmd.actual_distance = d
            self.segments.append(Segment(ts, current, cmd.target_pose, dur, cmd.command_id))
            self.pending.remove(cmd)
            # A command that starts before the previous one finished cancels it.
            for older in self.commands:
                if older is not cmd and older.start_time > 0 and older.arrive_time > ts and older.arrive_time > 0:
                    older.cancelled = True if older.command_id != cmd.command_id else False

    def busy_until(self, t: float) -> float:
        latest = 0.0
        for cmd in self.commands:
            if cmd.issue_time <= t and cmd.arrive_time > 0 and not cmd.cancelled:
                latest = max(latest, cmd.target_time)
        return latest
