"""Issue-time and target-time scheduling, sensor-only."""
from __future__ import annotations

import numpy as np

from .predictors import predict
from .robot_sim import Command, RobotSim
from .tracker import Track, Tracker, robust_linear_slope


class Planner:
    def __init__(self, cfg: dict, robot: RobotSim, tracker: Tracker):
        self.cfg = cfg
        self.robot = robot
        self.tracker = tracker
        self.p = cfg["planner"]
        self.n_cmd = 0

    def _other_busy_until(self, track_id: str, t: float) -> float:
        latest = 0.0
        for cmd in self.robot.commands:
            if cmd.track_id != track_id and cmd.issue_time <= t and not cmd.cancelled:
                latest = max(latest, cmd.target_time)
        return latest

    def consider(self, tr: Track, t_now: float) -> tuple[list[Command], list[tuple[Track, object]]]:
        """Return newly issued commands and (track, prediction) pairs."""
        new_cmds: list[Command] = []
        new_preds = []
        if tr.done or not tr.frames:
            return new_cmds, new_preds
        arr = tr.array()
        if t_now - arr[-1, 0] > 0.3:
            return new_cmds, new_preds
        x_now = float(np.median(arr[-min(5, len(arr)):, 2]))
        if tr.first_cmd_time is None:
            if t_now - tr.first_arrival < float(self.p["min_history_s"]):
                return new_cmds, new_preds
            s, _ = robust_linear_slope(arr, 2, float(self.cfg["predictor"]["velocity_window_s"]),
                                       int(self.cfg["predictor"]["velocity_min_frames"]))
            if s is None:
                return new_cmds, new_preds
            cadence = self.tracker.cadence(float(self.p["default_cadence_s"]))
            H = float(np.clip(float(self.p["cadence_factor"]) * cadence,
                              float(self.p["horizon_min_s"]) + 1.0,
                              float(self.p["horizon_max_s"])))
            # Wait until the predicted meeting point approaches the station,
            # but never leave the sensor field of view.
            if x_now > -100.0:
                # Hook already near the station: shorten the horizon rather
                # than waiting until it leaves the sensor field of view.
                H = max(float(self.p["horizon_min_s"]) + 0.5, min(H, 5.0))
            elif x_now + s * H > 30.0 and x_now > float(self.cfg["sensor"]["fov_x_mm"][0]) + 50.0:
                return new_cmds, new_preds
            # Shrink H if needed to stay inside the robot X envelope.
            x_hi = float(self.cfg["robot"]["envelope_x_mm"][1])
            if x_now + s * H > x_hi and s > 0:
                H = max(float(self.p["horizon_min_s"]) + 0.5, (x_hi - 20.0 - x_now) / s)
            if self._other_busy_until(tr.track_id, t_now) > t_now + 0.1:
                return new_cmds, new_preds
            t_target = t_now + H
            pred = predict(tr, self.tracker, t_now, t_target, self.cfg)
            start = self.robot.predicted_position(t_now + float(self.cfg["robot"]["comm_delay_s"]))
            d = float(np.linalg.norm(np.array(start) - np.array(pred.pose[:3])))
            min_H = float(self.cfg["robot"]["comm_delay_s"]) + d / float(self.cfg["robot"]["speed_mm_s"])
            if H < min_H * float(self.p["reachability_safety"]) + 0.1:
                return new_cmds, new_preds
        else:
            if tr.second_issued or tr.target_time is None:
                return new_cmds, new_preds
            remaining = tr.target_time - t_now
            lead = float(self.p["correction_lead_s"])
            if remaining > lead + 0.25:
                return new_cmds, new_preds
            if remaining < lead:
                tr.second_issued = True
                return new_cmds, new_preds
            t_target = tr.target_time
            pred = predict(tr, self.tracker, t_now, t_target, self.cfg)
            start = self.robot.predicted_position(t_now + float(self.cfg["robot"]["comm_delay_s"]))
            d = float(np.linalg.norm(np.array(start) - np.array(pred.pose[:3])))
            if t_target - t_now < float(self.cfg["robot"]["comm_delay_s"]) + d / float(self.cfg["robot"]["speed_mm_s"]):
                tr.second_issued = True
                return new_cmds, new_preds

        self.n_cmd += 1
        d = float(np.linalg.norm(np.array(self.robot.pose_at(t_now)[:3]) - np.array(pred.pose[:3])))
        cmd = Command(
            command_id=f"C{self.n_cmd:05d}", track_id=tr.track_id, issue_time=float(t_now),
            target_time=float(t_target), target_pose=tuple(pred.pose),
            move_distance=float(d),
            estimated_travel_time=float(d / self.cfg["robot"]["speed_mm_s"]),
            sequence=self.n_cmd,
        )
        self.robot.add(cmd)
        tr.cmd_count += 1
        if tr.first_cmd_time is None:
            tr.first_cmd_time = float(t_now)
            tr.target_time = float(t_target)
        else:
            tr.second_issued = True
        tr.v_est = pred.diagnostics.get("v_hat")
        tr.event_suspected = bool(pred.diagnostics.get("event_suspected", False))
        new_cmds.append(cmd)
        new_preds.append((tr, pred))
        return new_cmds, new_preds
