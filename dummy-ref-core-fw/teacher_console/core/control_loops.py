from __future__ import annotations

import threading
import time
from typing import Iterable, Optional

import numpy as np

from .model_pinocchio import PinocchioModel
from .robot_protocol import RobotProtocol
from .state_store import StateStore


def _as_vec6(values: Iterable[float], name: str) -> np.ndarray:
    arr = np.asarray(list(values), dtype=float)
    if arr.shape != (6,):
        raise ValueError(f"{name} must have 6 values")
    return arr


def _clamp_vec(v: np.ndarray, limit_a: float) -> np.ndarray:
    return np.clip(v, -abs(limit_a), abs(limit_a))


class JointPoller:
    def __init__(
        self,
        protocol: RobotProtocol,
        state: StateStore,
        hz: float = 50.0,
        timeout_s: float = 0.12,
        alarm_throttle_s: float = 1.0,
        mode5_hz: float = 30.0,
    ) -> None:
        self.protocol = protocol
        self.state = state
        self.base_hz = float(max(1.0, hz))
        self.mode5_hz = float(max(1.0, mode5_hz))
        self.timeout_s = float(max(0.02, timeout_s))
        self.alarm_throttle_s = float(max(0.2, alarm_throttle_s))
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_alarm_s = 0.0
        self._fail_count = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _loop(self) -> None:
        while not self._stop_evt.is_set():
            t0 = time.monotonic()
            snap = self.state.snapshot()
            if not snap.connected:
                time.sleep(0.1)
                continue
            run_hz = self.mode5_hz if snap.mode == 5 else self.base_hz
            period_s = 1.0 / max(1.0, run_hz)
            try:
                joints = self.protocol.get_joints(timeout_s=self.timeout_s)
                self.state.set_joints(joints)
                self._fail_count = 0
            except Exception as exc:
                self._fail_count += 1
                now_s = time.monotonic()
                if now_s - self._last_alarm_s >= self.alarm_throttle_s:
                    self.state.add_alarm(f"poller fail x{self._fail_count}: {exc}")
                    self._last_alarm_s = now_s
                time.sleep(0.05)
            dt = time.monotonic() - t0
            if dt < period_s:
                time.sleep(period_s - dt)


class ZeroGravityLoop:
    def __init__(
        self,
        protocol: RobotProtocol,
        state: StateStore,
        model: PinocchioModel,
        k_tau2i: Iterable[float],
        i_bias: Iterable[float],
        current_limit_a: float = 1.5,
        hz: float = 50.0,
    ) -> None:
        self.protocol = protocol
        self.state = state
        self.model = model
        self.k_tau2i = _as_vec6(k_tau2i, "k_tau2i")
        self.i_bias = _as_vec6(i_bias, "i_bias")
        self.current_limit_a = float(current_limit_a)
        self.period_s = 1.0 / max(1.0, hz)

        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def set_params(self, k_tau2i: Iterable[float], i_bias: Iterable[float], current_limit_a: float) -> None:
        self.k_tau2i = _as_vec6(k_tau2i, "k_tau2i")
        self.i_bias = _as_vec6(i_bias, "i_bias")
        self.current_limit_a = float(current_limit_a)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.protocol.set_mode(5)
        self.state.set_mode(5)
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        try:
            self.protocol.zero_currents()
        except Exception:
            pass
        self.state.set_currents([0.0] * 6)

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _loop(self) -> None:
        while not self._stop_evt.is_set():
            t0 = time.monotonic()
            snap = self.state.snapshot()
            if not snap.connected or not snap.enabled:
                time.sleep(0.05)
                continue
            if t0 - snap.last_joint_update_s > 0.3:
                time.sleep(0.02)
                continue
            try:
                q = np.asarray(snap.joints_deg, dtype=float)
                tau = self.model.compute_gravity_torque_nm(q)
                i_cmd = _clamp_vec(tau * self.k_tau2i + self.i_bias, self.current_limit_a)
                self.protocol.send_currents(i_cmd.tolist())
                self.state.set_currents(i_cmd.tolist())
            except Exception as exc:
                self.state.add_alarm(f"zerog: {exc}")
            dt = time.monotonic() - t0
            if dt < self.period_s:
                time.sleep(self.period_s - dt)


class ImpedanceLoop:
    def __init__(
        self,
        protocol: RobotProtocol,
        state: StateStore,
        model: PinocchioModel,
        k_tau2i: Iterable[float],
        i_bias: Iterable[float],
        kp: Iterable[float],
        kd: Iterable[float],
        current_limit_a: float = 1.5,
        hz: float = 50.0,
        vel_filter_alpha: float = 0.2,
    ) -> None:
        self.protocol = protocol
        self.state = state
        self.model = model
        self.k_tau2i = _as_vec6(k_tau2i, "k_tau2i")
        self.i_bias = _as_vec6(i_bias, "i_bias")
        self.kp = _as_vec6(kp, "kp")
        self.kd = _as_vec6(kd, "kd")
        self.current_limit_a = float(current_limit_a)
        self.period_s = 1.0 / max(1.0, hz)
        self.vel_alpha = float(max(0.0, min(1.0, vel_filter_alpha)))

        self._q_ref = np.zeros(6, dtype=float)
        self._q_prev = np.zeros(6, dtype=float)
        self._qdot = np.zeros(6, dtype=float)
        self._t_prev = 0.0
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def set_params(
        self,
        k_tau2i: Iterable[float],
        i_bias: Iterable[float],
        kp: Iterable[float],
        kd: Iterable[float],
        current_limit_a: float,
    ) -> None:
        self.k_tau2i = _as_vec6(k_tau2i, "k_tau2i")
        self.i_bias = _as_vec6(i_bias, "i_bias")
        self.kp = _as_vec6(kp, "kp")
        self.kd = _as_vec6(kd, "kd")
        self.current_limit_a = float(current_limit_a)

    def capture_reference(self) -> None:
        snap = self.state.snapshot()
        self._q_ref = np.asarray(snap.joints_deg, dtype=float)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.protocol.set_mode(5)
        self.state.set_mode(5)
        self.capture_reference()
        self._q_prev = self._q_ref.copy()
        self._qdot = np.zeros(6, dtype=float)
        self._t_prev = time.monotonic()
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        try:
            self.protocol.zero_currents()
        except Exception:
            pass
        self.state.set_currents([0.0] * 6)

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _loop(self) -> None:
        while not self._stop_evt.is_set():
            t0 = time.monotonic()
            snap = self.state.snapshot()
            if not snap.connected or not snap.enabled:
                time.sleep(0.05)
                continue
            if t0 - snap.last_joint_update_s > 0.3:
                time.sleep(0.02)
                continue
            try:
                q = np.asarray(snap.joints_deg, dtype=float)
                dt = max(1e-4, t0 - self._t_prev)
                qdot_raw = (q - self._q_prev) / dt
                self._qdot = self.vel_alpha * qdot_raw + (1.0 - self.vel_alpha) * self._qdot

                tau = self.model.compute_gravity_torque_nm(q)
                i_ff = tau * self.k_tau2i + self.i_bias
                i_cmd = i_ff + self.kp * (self._q_ref - q) + self.kd * (-self._qdot)
                i_cmd = _clamp_vec(i_cmd, self.current_limit_a)

                self.protocol.send_currents(i_cmd.tolist())
                self.state.set_currents(i_cmd.tolist())

                self._q_prev = q
                self._t_prev = t0
            except Exception as exc:
                self.state.add_alarm(f"impedance: {exc}")
            dt = time.monotonic() - t0
            if dt < self.period_s:
                time.sleep(self.period_s - dt)
