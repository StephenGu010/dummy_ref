from __future__ import annotations

import queue
import re
import threading
import time
from typing import Callable, Iterable, List, Optional

from .serial_client import SerialClient


JOINT_LINE_RE = re.compile(
    r"^ok\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)$"
)


class RobotProtocol:
    MODE_NAMES = {
        1: "SEQ_POINT",
        2: "INT_POINT",
        3: "CONT_TRAJ",
        4: "MOTOR_TUNE",
        5: "COMP_CURRENT",
    }

    def __init__(self, serial_client: SerialClient) -> None:
        self._ser = serial_client
        self._request_lock = threading.RLock()

    @classmethod
    def mode_name(cls, mode: int) -> str:
        return cls.MODE_NAMES.get(int(mode), "UNKNOWN")

    @staticmethod
    def parse_joint_line(line: str) -> Optional[List[float]]:
        match = JOINT_LINE_RE.match(line.strip())
        if not match:
            return None
        try:
            return [float(match.group(i)) for i in range(1, 7)]
        except Exception:
            return None

    @staticmethod
    def _is_error_line(line: str) -> bool:
        return line.strip().lower().startswith("error")

    @classmethod
    def _is_ok_ack_line(cls, line: str) -> bool:
        lower = line.strip().lower()
        if "ok" not in lower:
            return False
        return cls.parse_joint_line(line) is None

    def _wait_for(
        self,
        matcher: Callable[[str], bool],
        timeout_s: float = 0.4,
    ) -> str:
        q: queue.Queue[str] = queue.Queue(maxsize=4)

        def _listener(line: str) -> None:
            if matcher(line):
                try:
                    q.put_nowait(line)
                except queue.Full:
                    pass

        token = self._ser.register_listener(_listener)
        try:
            line = q.get(timeout=timeout_s)
            return line
        finally:
            self._ser.unregister_listener(token)

    def send_raw(self, cmd: str) -> None:
        self._ser.send_line(cmd)

    def send_expect_ok(self, cmd: str, timeout_s: float = 0.5) -> str:
        line = self._request(
            cmd,
            lambda s: self._is_error_line(s) or self._is_ok_ack_line(s),
            timeout_s=timeout_s,
        )
        if self._is_error_line(line):
            raise RuntimeError(f"device error for '{cmd}': {line}")
        return line

    def _request(self, cmd: str, matcher: Callable[[str], bool], timeout_s: float = 0.5) -> str:
        with self._request_lock:
            q: queue.Queue[str] = queue.Queue(maxsize=8)

            def _listener(line: str) -> None:
                if matcher(line):
                    try:
                        q.put_nowait(line)
                    except queue.Full:
                        pass

            token = self._ser.register_listener(_listener)
            try:
                self._ser.send_line(cmd)
                try:
                    return q.get(timeout=timeout_s)
                except queue.Empty as exc:
                    raise TimeoutError(f"timeout waiting reply for '{cmd}' ({timeout_s:.3f}s)") from exc
            finally:
                self._ser.unregister_listener(token)

    def start(self) -> str:
        return self.send_expect_ok("!START", timeout_s=1.0)

    def stop(self) -> str:
        return self.send_expect_ok("!STOP", timeout_s=0.6)

    def disable(self) -> str:
        return self.send_expect_ok("!DISABLE", timeout_s=0.8)

    def set_mode(self, mode: int) -> str:
        return self.send_expect_ok(f"#CMDMODE {mode}", timeout_s=0.6)

    def led_on(self) -> str:
        return self.send_expect_ok("!LEDON", timeout_s=0.5)

    def led_off(self) -> str:
        return self.send_expect_ok("!LEDOFF", timeout_s=0.5)

    def rgb_on(self) -> str:
        return self.send_expect_ok("!RGBON", timeout_s=0.5)

    def rgb_off(self) -> str:
        return self.send_expect_ok("!RGBOFF", timeout_s=0.5)

    def set_rgb_mode(self, mode: int) -> str:
        return self.send_expect_ok(f"#RGBMODE {int(mode)}", timeout_s=0.5)

    def set_rgb_color(self, r: int, g: int, b: int) -> str:
        rr = max(0, min(255, int(r)))
        gg = max(0, min(255, int(g)))
        bb = max(0, min(255, int(b)))
        return self.send_expect_ok(f"#RGBCOLOR {rr} {gg} {bb}", timeout_s=0.6)

    def _query_ok_line(self, cmd: str, timeout_s: float = 0.5) -> str:
        line = self._request(
            cmd,
            lambda s: self._is_error_line(s) or s.strip().lower().startswith("ok"),
            timeout_s=timeout_s,
        )
        if self._is_error_line(line):
            raise RuntimeError(f"device error for '{cmd}': {line}")
        return line

    def get_mode_status(self, timeout_s: float = 0.5) -> tuple[int, str]:
        line = self._query_ok_line("#GETMODE", timeout_s=timeout_s)
        parts = line.strip().split()
        if len(parts) < 2:
            raise RuntimeError(f"invalid mode reply: {line}")
        mode = int(parts[1])
        name = parts[2] if len(parts) >= 3 else self.mode_name(mode)
        return mode, name

    def get_enable_status(self, timeout_s: float = 0.5) -> bool:
        line = self._query_ok_line("#GETENABLE", timeout_s=timeout_s)
        parts = line.strip().split()
        if len(parts) < 2:
            raise RuntimeError(f"invalid enable reply: {line}")
        return int(parts[1]) != 0

    def get_rgb_status(self, timeout_s: float = 0.5) -> dict:
        line = self._query_ok_line("#GETRGB", timeout_s=timeout_s)
        parts = line.strip().split()
        if len(parts) < 7:
            raise RuntimeError(f"invalid rgb reply: {line}")
        return {
            "rgb_enabled": int(parts[1]) != 0,
            "rgb_mode": int(parts[2]),
            "r": int(parts[3]),
            "g": int(parts[4]),
            "b": int(parts[5]),
            "led_enabled": int(parts[6]) != 0,
        }

    def get_joints(self, timeout_s: float = 0.3) -> List[float]:
        line = self._request("#GETJPOS", lambda s: self.parse_joint_line(s) is not None, timeout_s=timeout_s)
        joints = self.parse_joint_line(line)
        if joints is None:
            raise RuntimeError(f"invalid joint line: {line}")
        return joints

    def move_joints(self, joints_deg: Iterable[float], speed_deg_s: Optional[float] = None, prefix: str = ">") -> None:
        vals = list(joints_deg)
        if len(vals) != 6:
            raise ValueError("joints_deg must have 6 elements")
        if prefix not in (">", "&"):
            raise ValueError("prefix must be '>' or '&'")
        if speed_deg_s is None:
            cmd = f"{prefix}{vals[0]:.3f},{vals[1]:.3f},{vals[2]:.3f},{vals[3]:.3f},{vals[4]:.3f},{vals[5]:.3f}"
        else:
            cmd = (
                f"{prefix}{vals[0]:.3f},{vals[1]:.3f},{vals[2]:.3f},"
                f"{vals[3]:.3f},{vals[4]:.3f},{vals[5]:.3f},{float(speed_deg_s):.3f}"
            )
        self.send_raw(cmd)

    def move_pose(self, pose_6d: Iterable[float], speed: Optional[float] = None) -> None:
        vals = list(pose_6d)
        if len(vals) != 6:
            raise ValueError("pose_6d must have 6 elements")
        if speed is None:
            cmd = f"@{vals[0]:.3f},{vals[1]:.3f},{vals[2]:.3f},{vals[3]:.3f},{vals[4]:.3f},{vals[5]:.3f}"
        else:
            cmd = (
                f"@{vals[0]:.3f},{vals[1]:.3f},{vals[2]:.3f},"
                f"{vals[3]:.3f},{vals[4]:.3f},{vals[5]:.3f},{float(speed):.3f}"
            )
        self.send_raw(cmd)

    def send_currents(self, currents_a: Iterable[float]) -> None:
        vals = list(currents_a)
        if len(vals) != 6:
            raise ValueError("currents_a must have 6 elements")
        cmd = f"${vals[0]:.3f},{vals[1]:.3f},{vals[2]:.3f},{vals[3]:.3f},{vals[4]:.3f},{vals[5]:.3f}"
        self.send_raw(cmd)

    def zero_currents(self) -> None:
        self.send_currents([0.0] * 6)

    def emergency_stop_disable(self) -> None:
        try:
            self.send_raw("!STOP")
        except Exception:
            pass
        time.sleep(0.05)
        try:
            self.zero_currents()
        except Exception:
            pass
        time.sleep(0.02)
        try:
            self.send_raw("!DISABLE")
        except Exception:
            pass

    def manual_command(self, cmd: str, wait_reply: bool = False, timeout_s: float = 0.3) -> str:
        text = cmd.strip()
        if not text:
            raise ValueError("empty command")
        if wait_reply:
            return self._request(text, lambda _s: True, timeout_s=timeout_s)
        self.send_raw(text)
        return ""
