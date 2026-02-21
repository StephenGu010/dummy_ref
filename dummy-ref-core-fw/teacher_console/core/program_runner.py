from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional

import yaml

from .robot_protocol import RobotProtocol
from .state_store import StateStore


class ProgramRunner:
    def __init__(
        self,
        protocol: RobotProtocol,
        state: StateStore,
        on_start_zerog: Optional[Callable[[Dict], None]] = None,
        on_stop_zerog: Optional[Callable[[], None]] = None,
        on_start_impedance: Optional[Callable[[Dict], None]] = None,
        on_stop_impedance: Optional[Callable[[], None]] = None,
    ) -> None:
        self.protocol = protocol
        self.state = state
        self.on_start_zerog = on_start_zerog
        self.on_stop_zerog = on_stop_zerog
        self.on_start_impedance = on_start_impedance
        self.on_stop_impedance = on_stop_impedance

        self.program: Dict = {"name": "empty", "steps": []}
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._pause_evt = threading.Event()
        self._pause_evt.set()

    def load_yaml(self, yaml_path: str) -> Dict:
        with open(yaml_path, "r", encoding="utf-8") as f:
            payload = yaml.safe_load(f) or {}
        self.set_program(payload)
        return payload

    def save_yaml(self, yaml_path: str) -> None:
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.program, f, sort_keys=False, allow_unicode=False)

    def set_program(self, payload: Dict) -> None:
        if "steps" not in payload or not isinstance(payload.get("steps"), list):
            raise ValueError("program yaml must contain a list field: steps")
        self.program = payload

    def start(self) -> None:
        if self.is_running():
            return
        self._stop_evt.clear()
        self._pause_evt.set()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        self._pause_evt.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._stop_all_mode_loops()

    def pause(self) -> None:
        self._pause_evt.clear()

    def resume(self) -> None:
        self._pause_evt.set()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def is_paused(self) -> bool:
        return not self._pause_evt.is_set()

    def _sleep_interruptible(self, duration_s: float) -> bool:
        end_t = time.monotonic() + max(0.0, duration_s)
        while time.monotonic() < end_t:
            if self._stop_evt.is_set():
                return False
            if not self._pause_evt.is_set():
                time.sleep(0.02)
                continue
            time.sleep(0.01)
        return True

    def _stop_all_mode_loops(self) -> None:
        if self.on_stop_zerog:
            try:
                self.on_stop_zerog()
            except Exception:
                pass
        if self.on_stop_impedance:
            try:
                self.on_stop_impedance()
            except Exception:
                pass

    def _loop(self) -> None:
        steps: List[Dict] = self.program.get("steps", [])
        defaults = self.program.get("defaults", {})
        default_speed = float(defaults.get("speed_deg_s", 20.0))
        self._stop_all_mode_loops()

        for idx, step in enumerate(steps):
            if self._stop_evt.is_set():
                break
            while not self._pause_evt.is_set() and not self._stop_evt.is_set():
                time.sleep(0.02)
            if self._stop_evt.is_set():
                break

            mode = str(step.get("mode", "movej")).strip().lower()
            duration_s = float(step.get("duration_s", 1.0))
            self.state.add_alarm(f"program step {idx + 1}: {mode}")

            if mode == "movej":
                self._stop_all_mode_loops()
                speed = float(step.get("speed_deg_s", default_speed))
                target = step.get("target_deg", [0, 0, 0, 0, 0, 0])
                self.protocol.set_mode(2)
                self.state.set_mode(2)
                self.protocol.move_joints(target, speed_deg_s=speed, prefix=">")
                if not self._sleep_interruptible(duration_s):
                    break
            elif mode == "zerog":
                if self.on_start_zerog:
                    self.on_start_zerog(step)
                if not self._sleep_interruptible(duration_s):
                    break
                if self.on_stop_zerog:
                    self.on_stop_zerog()
            elif mode == "impedance":
                if self.on_start_impedance:
                    self.on_start_impedance(step)
                if not self._sleep_interruptible(duration_s):
                    break
                if self.on_stop_impedance:
                    self.on_stop_impedance()
            else:
                self.state.add_alarm(f"unknown step mode: {mode}")

        self._stop_all_mode_loops()

