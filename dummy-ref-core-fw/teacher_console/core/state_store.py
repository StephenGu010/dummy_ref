from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import List
import copy
import time


@dataclass
class RobotState:
    connected: bool = False
    enabled: bool = False
    mode: int = 2
    serial_port: str = ""
    last_line: str = ""
    joints_deg: List[float] = field(default_factory=lambda: [0.0] * 6)
    currents_a: List[float] = field(default_factory=lambda: [0.0] * 6)
    alarms: List[str] = field(default_factory=list)
    last_joint_update_s: float = 0.0
    tx_count: int = 0
    rx_count: int = 0


class StateStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._state = RobotState()

    def snapshot(self) -> RobotState:
        with self._lock:
            return copy.deepcopy(self._state)

    def set_connection(self, connected: bool, serial_port: str = "") -> None:
        with self._lock:
            self._state.connected = connected
            self._state.serial_port = serial_port if connected else ""
            if not connected:
                self._state.enabled = False

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._state.enabled = enabled

    def set_mode(self, mode: int) -> None:
        with self._lock:
            self._state.mode = mode

    def set_joints(self, joints_deg: List[float]) -> None:
        if len(joints_deg) != 6:
            return
        with self._lock:
            self._state.joints_deg = list(joints_deg)
            self._state.last_joint_update_s = time.monotonic()

    def set_currents(self, currents_a: List[float]) -> None:
        if len(currents_a) != 6:
            return
        with self._lock:
            self._state.currents_a = list(currents_a)

    def set_last_line(self, line: str) -> None:
        with self._lock:
            self._state.last_line = line
            self._state.rx_count += 1

    def mark_tx(self) -> None:
        with self._lock:
            self._state.tx_count += 1

    def add_alarm(self, msg: str) -> None:
        with self._lock:
            self._state.alarms.append(msg)
            if len(self._state.alarms) > 200:
                self._state.alarms = self._state.alarms[-200:]

    def clear_alarms(self) -> None:
        with self._lock:
            self._state.alarms.clear()

