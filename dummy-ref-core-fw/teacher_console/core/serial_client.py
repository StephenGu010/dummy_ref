from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional

import serial


LineListener = Callable[[str], None]


class SerialClient:
    def __init__(self, auto_reconnect: bool = True) -> None:
        self._serial: Optional[serial.Serial] = None
        self._stop_evt = threading.Event()
        self._io_lock = threading.RLock()
        self._listeners: Dict[int, LineListener] = {}
        self._listener_seq = 0
        self._reader_thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None

        self._auto_reconnect = auto_reconnect
        self._manual_disconnect = True
        self._last_params: Optional[tuple[str, int, float]] = None
        self._connected_evt = threading.Event()
        self._connect_sig_logged = False

        self.on_connect: Optional[Callable[[], None]] = None
        self.on_disconnect: Optional[Callable[[str], None]] = None
        self.on_tx: Optional[Callable[[], None]] = None
        self.on_rx: Optional[Callable[[str], None]] = None

    def connect(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float | None = None,
        timeout_s: float | None = None,
    ) -> None:
        resolved_timeout = timeout_s if timeout_s is not None else timeout
        if resolved_timeout is None:
            resolved_timeout = 0.05
        resolved_timeout = float(resolved_timeout)

        if not self._connect_sig_logged:
            print(
                f"[SerialClient] connect compatibility enabled (timeout/timeout_s), file={__file__}"
            )
            self._connect_sig_logged = True

        with self._io_lock:
            self._manual_disconnect = False
            self._last_params = (port, baudrate, resolved_timeout)
            self._open_locked(port, baudrate, resolved_timeout)

        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()

    def _open_locked(self, port: str, baudrate: int, timeout: float) -> None:
        if self._serial and self._serial.is_open:
            return
        self._serial = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()
        self._connected_evt.set()
        if self.on_connect:
            self.on_connect()
        self._ensure_reader_started()

    def _ensure_reader_started(self) -> None:
        if self._reader_thread and self._reader_thread.is_alive():
            return
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def disconnect(self) -> None:
        with self._io_lock:
            self._manual_disconnect = True
            self._close_locked("manual disconnect")

    def close(self) -> None:
        self._stop_evt.set()
        self.disconnect()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=0.5)
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=0.5)

    def _close_locked(self, reason: str) -> None:
        ser = self._serial
        self._serial = None
        self._connected_evt.clear()
        if ser:
            try:
                if ser.is_open:
                    ser.close()
            except Exception:
                pass
        if self.on_disconnect:
            self.on_disconnect(reason)

    def is_connected(self) -> bool:
        ser = self._serial
        return bool(ser and ser.is_open and self._connected_evt.is_set())

    def send_line(self, text: str) -> None:
        payload = text if text.endswith("\n") else f"{text}\n"
        with self._io_lock:
            if not self._serial or not self._serial.is_open:
                raise RuntimeError("serial is not connected")
            self._serial.write(payload.encode("utf-8"))
            self._serial.flush()
        if self.on_tx:
            self.on_tx()

    def register_listener(self, fn: LineListener) -> int:
        with self._io_lock:
            token = self._listener_seq
            self._listener_seq += 1
            self._listeners[token] = fn
            return token

    def unregister_listener(self, token: int) -> None:
        with self._io_lock:
            self._listeners.pop(token, None)

    def _reader_loop(self) -> None:
        while not self._stop_evt.is_set():
            ser = self._serial
            if not ser or not ser.is_open:
                time.sleep(0.05)
                continue
            try:
                raw = ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                if self.on_rx:
                    self.on_rx(line)
                listeners = []
                with self._io_lock:
                    listeners = list(self._listeners.values())
                for fn in listeners:
                    try:
                        fn(line)
                    except Exception:
                        continue
            except Exception as exc:
                with self._io_lock:
                    self._close_locked(f"reader error: {exc}")
                time.sleep(0.1)

    def _monitor_loop(self) -> None:
        while not self._stop_evt.is_set():
            if self.is_connected():
                time.sleep(0.2)
                continue
            if not self._auto_reconnect or self._manual_disconnect or not self._last_params:
                time.sleep(0.3)
                continue
            port, baudrate, timeout = self._last_params
            try:
                with self._io_lock:
                    self._open_locked(port, baudrate, timeout)
            except Exception:
                time.sleep(1.0)
