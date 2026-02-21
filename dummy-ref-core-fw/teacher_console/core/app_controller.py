from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml
from serial.tools import list_ports

from .control_loops import ImpedanceLoop, JointPoller, ZeroGravityLoop
from .model_pinocchio import ModelMapping, PinocchioModel
from .program_runner import ProgramRunner
from .robot_protocol import RobotProtocol
from .serial_client import SerialClient
from .state_store import StateStore
from .teach_recorder import TeachRecorder


def _vec6(values: Iterable[float], default: float = 0.0) -> List[float]:
    vals = list(values)
    if len(vals) != 6:
        return [float(default)] * 6
    return [float(v) for v in vals]


@dataclass
class ControlParams:
    k_tau2i: List[float]
    i_bias: List[float]
    kp: List[float]
    kd: List[float]
    current_limit_a: float


class AppController:
    def __init__(self, config_path: str) -> None:
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.state = StateStore()
        self.model_error = "model not loaded"
        self.model_meta: Dict[str, object] = {
            "loaded": False,
            "path": "",
            "error": self.model_error,
            "nq": 0,
            "nv": 0,
        }

        self.serial_client = SerialClient(auto_reconnect=True)
        self.serial_client.on_connect = self._on_serial_connect
        self.serial_client.on_disconnect = self._on_serial_disconnect
        self.serial_client.on_rx = self._on_serial_rx
        self.serial_client.on_tx = self.state.mark_tx

        self.protocol = RobotProtocol(self.serial_client)
        self.poller = JointPoller(
            self.protocol,
            self.state,
            hz=float(self.config["runtime"]["poll_hz"]),
            timeout_s=float(self.config["runtime"]["poll_timeout_s"]),
            alarm_throttle_s=float(self.config["runtime"]["alarm_throttle_s"]),
            mode5_hz=float(self.config["runtime"]["poll_hz_mode5"]),
        )
        self.recorder = TeachRecorder(self.state, sample_hz=float(self.config["runtime"]["record_hz"]))

        self.model: Optional[PinocchioModel] = None
        self.zero_loop: Optional[ZeroGravityLoop] = None
        self.imp_loop: Optional[ImpedanceLoop] = None
        self.control = self._control_params_from_config()
        self._load_model_from_config()

        self.program_runner = ProgramRunner(
            protocol=self.protocol,
            state=self.state,
            on_start_zerog=self._program_start_zerog,
            on_stop_zerog=self.stop_zero_gravity,
            on_start_impedance=self._program_start_impedance,
            on_stop_impedance=self.stop_impedance,
        )
        self._load_default_program_if_exists()

    @staticmethod
    def cmdmode_name(mode: int) -> str:
        return RobotProtocol.mode_name(mode)

    @staticmethod
    def _load_config(path: str) -> Dict:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        cfg.setdefault("serial", {})
        cfg["serial"].setdefault("port", "/dev/ttyACM0")
        cfg["serial"].setdefault("baudrate", 115200)
        cfg["serial"].setdefault("timeout_s", 0.05)

        cfg.setdefault("model", {})
        cfg["model"].setdefault("urdf_path", "")
        cfg["model"].setdefault("joint_map", [0, 1, 2, 3, 4, 5])
        cfg["model"].setdefault("joint_sign", [1, 1, 1, 1, 1, 1])
        cfg["model"].setdefault("joint_offset_deg", [0, 0, 0, 0, 0, 0])

        cfg.setdefault("control", {})
        cfg["control"].setdefault("k_tau2i", [0.0, 0.35, 0.3, 0.1, 0.1, 0.1])
        cfg["control"].setdefault("i_bias", [0, 0, 0, 0, 0, 0])
        cfg["control"].setdefault("kp", [0.04, 0.08, 0.08, 0.03, 0.03, 0.02])
        cfg["control"].setdefault("kd", [0.002, 0.004, 0.004, 0.002, 0.002, 0.0015])
        cfg["control"].setdefault("current_limit_a", 1.5)

        cfg.setdefault("teach", {})
        cfg["teach"].setdefault("angle_threshold_deg", 2.0)
        cfg["teach"].setdefault("time_threshold_s", 5.0)
        cfg["teach"].setdefault("yaml_default_speed_deg_s", 20.0)
        cfg["teach"].setdefault("yaml_default_duration_s", 1.0)

        cfg.setdefault("runtime", {})
        cfg["runtime"].setdefault("poll_hz", 50.0)
        cfg["runtime"].setdefault("control_hz", 50.0)
        cfg["runtime"].setdefault("record_hz", 20.0)
        cfg["runtime"].setdefault("poll_timeout_s", 0.12)
        cfg["runtime"].setdefault("alarm_throttle_s", 1.0)
        cfg["runtime"].setdefault("poll_hz_mode5", 30.0)
        cfg["runtime"].setdefault("safe_sync_on_connect", True)
        return cfg

    def save_config(self) -> None:
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.config, f, sort_keys=False, allow_unicode=False)

    def _control_params_from_config(self) -> ControlParams:
        c = self.config["control"]
        return ControlParams(
            k_tau2i=_vec6(c.get("k_tau2i", []), 0.0),
            i_bias=_vec6(c.get("i_bias", []), 0.0),
            kp=_vec6(c.get("kp", []), 0.0),
            kd=_vec6(c.get("kd", []), 0.0),
            current_limit_a=float(c.get("current_limit_a", 1.5)),
        )

    def update_control_params(
        self,
        k_tau2i: Iterable[float],
        i_bias: Iterable[float],
        kp: Iterable[float],
        kd: Iterable[float],
        current_limit_a: float,
    ) -> None:
        self.control = ControlParams(
            k_tau2i=_vec6(k_tau2i),
            i_bias=_vec6(i_bias),
            kp=_vec6(kp),
            kd=_vec6(kd),
            current_limit_a=float(current_limit_a),
        )
        self.config["control"]["k_tau2i"] = list(self.control.k_tau2i)
        self.config["control"]["i_bias"] = list(self.control.i_bias)
        self.config["control"]["kp"] = list(self.control.kp)
        self.config["control"]["kd"] = list(self.control.kd)
        self.config["control"]["current_limit_a"] = float(self.control.current_limit_a)

        if self.zero_loop:
            self.zero_loop.set_params(self.control.k_tau2i, self.control.i_bias, self.control.current_limit_a)
        if self.imp_loop:
            self.imp_loop.set_params(
                self.control.k_tau2i,
                self.control.i_bias,
                self.control.kp,
                self.control.kd,
                self.control.current_limit_a,
            )

    def _resolve_urdf_path(self, raw_path: str) -> str:
        text = str(raw_path or "").strip()
        if not text:
            return ""
        resolved = os.path.expandvars(os.path.expanduser(text))
        if not os.path.isabs(resolved):
            cfg_dir = os.path.dirname(os.path.abspath(self.config_path))
            resolved = os.path.join(cfg_dir, resolved)
        return os.path.abspath(resolved)

    def load_model_from_path(self, urdf_path: str) -> tuple[bool, str, str]:
        resolved_path = self._resolve_urdf_path(urdf_path)
        self.config["model"]["urdf_path"] = urdf_path

        if not resolved_path:
            self.model = None
            self.model_error = "urdf_path is empty"
            self.model_meta = {
                "loaded": False,
                "path": "",
                "error": self.model_error,
                "nq": 0,
                "nv": 0,
            }
            self.state.add_alarm(f"model: {self.model_error}")
            return False, self.model_error, resolved_path

        if not os.path.exists(resolved_path):
            self.model = None
            self.model_error = f"urdf file not found: {resolved_path}"
            self.model_meta = {
                "loaded": False,
                "path": resolved_path,
                "error": self.model_error,
                "nq": 0,
                "nv": 0,
            }
            self.state.add_alarm(f"model: {self.model_error}")
            return False, self.model_error, resolved_path

        mapping = ModelMapping(
            joint_map=[int(v) for v in self.config["model"].get("joint_map", [0, 1, 2, 3, 4, 5])],
            joint_sign=[float(v) for v in self.config["model"].get("joint_sign", [1, 1, 1, 1, 1, 1])],
            joint_offset_deg=[float(v) for v in self.config["model"].get("joint_offset_deg", [0, 0, 0, 0, 0, 0])],
        )

        try:
            self.model = PinocchioModel(urdf_path=resolved_path, mapping=mapping)
            self.model_error = ""
            self.model_meta = {
                "loaded": True,
                "path": resolved_path,
                "error": "",
                "nq": int(self.model.model.nq),
                "nv": int(self.model.model.nv),
            }
            self.state.add_alarm(
                f"model loaded: {resolved_path} (nq={self.model.model.nq}, nv={self.model.model.nv})"
            )
            return True, "ok", resolved_path
        except Exception as exc:
            self.model = None
            self.model_error = str(exc)
            self.model_meta = {
                "loaded": False,
                "path": resolved_path,
                "error": self.model_error,
                "nq": 0,
                "nv": 0,
            }
            self.state.add_alarm(f"model load failed: {self.model_error}")
            return False, self.model_error, resolved_path

    def _load_model_from_config(self) -> None:
        self.load_model_from_path(str(self.config["model"].get("urdf_path", "")))

    def _load_default_program_if_exists(self) -> None:
        root = Path(self.config_path).resolve().parent.parent
        default_path = root / "programs" / "default_demo.yaml"
        if default_path.exists():
            try:
                self.program_runner.load_yaml(str(default_path))
            except Exception as exc:
                self.state.add_alarm(f"default program load failed: {exc}")

    def set_urdf_path(self, urdf_path: str) -> tuple[bool, str, str]:
        return self.load_model_from_path(urdf_path)

    def get_model_status(self) -> Dict[str, object]:
        return dict(self.model_meta)

    def list_serial_ports(self) -> List[str]:
        return sorted([p.device for p in list_ports.comports()])

    def connect_serial(self, port: Optional[str] = None) -> None:
        serial_cfg = self.config["serial"]
        port = port or serial_cfg.get("port", "/dev/ttyACM0")
        self.config["serial"]["port"] = port
        self.serial_client.connect(
            port=port,
            baudrate=int(serial_cfg.get("baudrate", 115200)),
            timeout_s=float(serial_cfg.get("timeout_s", 0.05)),
        )
        self.poller.start()

        if bool(self.config["runtime"].get("safe_sync_on_connect", True)):
            try:
                self.protocol.emergency_stop_disable()
                self.state.set_enabled(False)
                self.state.add_alarm("safe sync on connect: !STOP -> $0 -> !DISABLE")
            except Exception as exc:
                self.state.add_alarm(f"safe sync failed: {exc}")

    def disconnect_serial(self) -> None:
        self.stop_program()
        self.stop_zero_gravity()
        self.stop_impedance()
        self.poller.stop()
        self.serial_client.disconnect()

    def start_robot(self) -> None:
        self.protocol.start()
        self.state.set_enabled(True)

    def disable_robot(self) -> None:
        self.stop_program()
        self.stop_zero_gravity()
        self.stop_impedance()
        try:
            self.protocol.zero_currents()
        except Exception:
            pass
        self.protocol.disable()
        self.state.set_enabled(False)

    def emergency_stop(self) -> None:
        self.stop_program()
        self.stop_zero_gravity()
        self.stop_impedance()
        self.protocol.emergency_stop_disable()
        self.state.set_enabled(False)

    def send_manual_command(self, cmd: str, wait_reply: bool = False, timeout_s: float = 0.3) -> str:
        return self.protocol.manual_command(cmd, wait_reply=wait_reply, timeout_s=timeout_s)

    def set_led_enabled(self, enabled: bool) -> None:
        if enabled:
            self.protocol.led_on()
        else:
            self.protocol.led_off()

    def set_rgb_enabled(self, enabled: bool) -> None:
        if enabled:
            self.protocol.rgb_on()
        else:
            self.protocol.rgb_off()

    def set_rgb_mode(self, mode: int) -> None:
        self.protocol.set_rgb_mode(mode)

    def set_rgb_color(self, r: int, g: int, b: int) -> None:
        self.protocol.set_rgb_color(r, g, b)

    def refresh_device_runtime_status(self) -> Dict[str, object]:
        mode, mode_name = self.protocol.get_mode_status(timeout_s=0.4)
        enabled = self.protocol.get_enable_status(timeout_s=0.4)
        rgb = self.protocol.get_rgb_status(timeout_s=0.4)
        self.state.set_mode(mode)
        self.state.set_enabled(enabled)
        return {
            "mode": mode,
            "mode_name": mode_name,
            "enabled": enabled,
            **rgb,
        }

    def _ensure_loops_ready(self) -> None:
        if self.model is None:
            reason = self.model_error if self.model_error else "unknown model error"
            raise RuntimeError(f"model is not loaded: {reason}")

        hz = float(self.config["runtime"]["control_hz"])
        if self.zero_loop is None:
            self.zero_loop = ZeroGravityLoop(
                protocol=self.protocol,
                state=self.state,
                model=self.model,
                k_tau2i=self.control.k_tau2i,
                i_bias=self.control.i_bias,
                current_limit_a=self.control.current_limit_a,
                hz=hz,
            )
        if self.imp_loop is None:
            self.imp_loop = ImpedanceLoop(
                protocol=self.protocol,
                state=self.state,
                model=self.model,
                k_tau2i=self.control.k_tau2i,
                i_bias=self.control.i_bias,
                kp=self.control.kp,
                kd=self.control.kd,
                current_limit_a=self.control.current_limit_a,
                hz=hz,
            )

    def start_zero_gravity(self) -> None:
        if not self.state.snapshot().enabled:
            raise RuntimeError("robot is not enabled, send !START first")
        self._ensure_loops_ready()
        self.stop_impedance()
        assert self.zero_loop is not None
        self.zero_loop.start()
        self.state.set_mode(5)

    def stop_zero_gravity(self) -> None:
        if self.zero_loop:
            self.zero_loop.stop()

    def start_impedance(self) -> None:
        if not self.state.snapshot().enabled:
            raise RuntimeError("robot is not enabled, send !START first")
        self._ensure_loops_ready()
        self.stop_zero_gravity()
        assert self.imp_loop is not None
        self.imp_loop.start()
        self.state.set_mode(5)

    def stop_impedance(self) -> None:
        if self.imp_loop:
            self.imp_loop.stop()

    def capture_impedance_ref(self) -> None:
        if self.imp_loop:
            self.imp_loop.capture_reference()

    def start_recording(self, angle_threshold_deg: float, time_threshold_s: float) -> None:
        self.recorder.start(angle_threshold_deg, time_threshold_s)

    def stop_recording(self) -> None:
        self.recorder.stop()

    def export_record_csv(self, path: str) -> None:
        self.recorder.export_csv(path)

    def export_record_yaml(self, path: str) -> None:
        defaults = {
            "name": "teach_program",
            "speed_deg_s": float(self.config["teach"]["yaml_default_speed_deg_s"]),
            "duration_s": float(self.config["teach"]["yaml_default_duration_s"]),
        }
        self.recorder.export_yaml_program(path, defaults=defaults)

    def play_recorded_points(self, auto_start_if_disabled: bool = True) -> None:
        self.stop_program()
        self.stop_zero_gravity()
        self.stop_impedance()
        if self.recorder.is_recording():
            self.recorder.stop()

        snap = self.state.snapshot()
        if not snap.enabled:
            if auto_start_if_disabled:
                self.start_robot()
            else:
                raise RuntimeError("robot is disabled")

        payload = self.recorder.build_program_payload(
            default_speed_deg_s=float(self.config["teach"]["yaml_default_speed_deg_s"]),
            default_duration_s=float(self.config["teach"]["yaml_default_duration_s"]),
        )
        payload["name"] = "teach_live_playback"
        self.program_runner.set_program(payload)
        self.program_runner.start()

    def get_record_points(self):
        return self.recorder.points()

    def set_program(self, payload: Dict) -> None:
        self.program_runner.set_program(payload)

    def load_program_yaml(self, path: str) -> Dict:
        return self.program_runner.load_yaml(path)

    def save_program_yaml(self, path: str) -> None:
        self.program_runner.save_yaml(path)

    def start_program(self) -> None:
        self.program_runner.start()

    def stop_program(self) -> None:
        self.program_runner.stop()

    def pause_program(self) -> None:
        self.program_runner.pause()

    def resume_program(self) -> None:
        self.program_runner.resume()

    def _program_start_zerog(self, step: Dict) -> None:
        self.start_zero_gravity()

    def _program_start_impedance(self, step: Dict) -> None:
        kp = step.get("kp")
        kd = step.get("kd")
        if kp is not None and kd is not None:
            self.update_control_params(
                k_tau2i=self.control.k_tau2i,
                i_bias=self.control.i_bias,
                kp=kp,
                kd=kd,
                current_limit_a=self.control.current_limit_a,
            )
        self.start_impedance()

    def shutdown(self) -> None:
        try:
            self.emergency_stop()
        except Exception:
            pass
        try:
            self.poller.stop()
        except Exception:
            pass
        try:
            self.serial_client.close()
        except Exception:
            pass
        self.save_config()

    def _on_serial_connect(self) -> None:
        port = self.config["serial"].get("port", "")
        self.state.set_connection(True, serial_port=port)

    def _on_serial_disconnect(self, reason: str) -> None:
        self.state.set_connection(False, serial_port="")
        self.state.add_alarm(f"serial disconnected: {reason}")

    def _on_serial_rx(self, line: str) -> None:
        self.state.set_last_line(line)
