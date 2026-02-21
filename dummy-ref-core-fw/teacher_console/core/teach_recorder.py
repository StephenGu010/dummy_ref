from __future__ import annotations

import csv
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import yaml

from .state_store import StateStore


@dataclass
class RecordPoint:
    t_s: float
    joints_deg: List[float]


class TeachRecorder:
    def __init__(self, state: StateStore, sample_hz: float = 20.0) -> None:
        self.state = state
        self.period_s = 1.0 / max(1.0, sample_hz)
        self.angle_threshold_deg = 2.0
        self.time_threshold_s = 5.0

        self._points: List[RecordPoint] = []
        self._points_lock = threading.RLock()
        self._start_monotonic_s = 0.0
        self._last_record_s = 0.0
        self._last_record_joints: Optional[List[float]] = None
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self, angle_threshold_deg: float, time_threshold_s: float) -> None:
        if self.is_recording():
            return
        self.angle_threshold_deg = float(max(0.01, angle_threshold_deg))
        self.time_threshold_s = float(max(0.1, time_threshold_s))
        with self._points_lock:
            self._points.clear()
        self._start_monotonic_s = time.monotonic()
        self._last_record_s = self._start_monotonic_s
        self._last_record_joints = None
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def is_recording(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def points(self) -> List[RecordPoint]:
        with self._points_lock:
            return [RecordPoint(p.t_s, list(p.joints_deg)) for p in self._points]

    def _loop(self) -> None:
        while not self._stop_evt.is_set():
            t0 = time.monotonic()
            snap = self.state.snapshot()
            if not snap.connected:
                time.sleep(0.1)
                continue
            joints = list(snap.joints_deg)
            now_s = time.monotonic()

            if self._last_record_joints is None:
                self._append_point(now_s, joints)
            else:
                max_delta = max(abs(joints[i] - self._last_record_joints[i]) for i in range(6))
                time_delta = now_s - self._last_record_s
                if max_delta >= self.angle_threshold_deg or time_delta >= self.time_threshold_s:
                    self._append_point(now_s, joints)

            dt = time.monotonic() - t0
            if dt < self.period_s:
                time.sleep(self.period_s - dt)

    def _append_point(self, now_s: float, joints: List[float]) -> None:
        rel_t = max(0.0, now_s - self._start_monotonic_s)
        with self._points_lock:
            self._points.append(RecordPoint(t_s=rel_t, joints_deg=list(joints)))
        self._last_record_s = now_s
        self._last_record_joints = list(joints)

    def export_csv(self, csv_path: str) -> None:
        points = self.points()
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["t_s", "j1", "j2", "j3", "j4", "j5", "j6"])
            for p in points:
                writer.writerow([f"{p.t_s:.3f}", *[f"{v:.3f}" for v in p.joints_deg]])

    def build_program_payload(self, default_speed_deg_s: float, default_duration_s: float) -> Dict:
        points = self.points()
        if len(points) < 1:
            raise RuntimeError("no points recorded")

        steps = []
        for i, p in enumerate(points):
            if i == 0:
                duration = float(default_duration_s)
            else:
                duration = max(0.05, p.t_s - points[i - 1].t_s)
            steps.append(
                {
                    "mode": "movej",
                    "duration_s": round(duration, 3),
                    "speed_deg_s": float(default_speed_deg_s),
                    "target_deg": [round(v, 3) for v in p.joints_deg],
                    "comment": f"teach point {i + 1}",
                }
            )
        return {
            "name": "teach_program",
            "version": 1,
            "description": "Recorded from teach mode",
            "defaults": {
                "speed_deg_s": float(default_speed_deg_s),
                "duration_s": float(default_duration_s),
            },
            "steps": steps,
        }

    def export_yaml_program(self, yaml_path: str, defaults: Dict) -> None:
        payload = self.build_program_payload(
            default_speed_deg_s=float(defaults.get("speed_deg_s", 20.0)),
            default_duration_s=float(defaults.get("duration_s", 1.0)),
        )
        payload["name"] = defaults.get("name", "taught_program")
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=False)
