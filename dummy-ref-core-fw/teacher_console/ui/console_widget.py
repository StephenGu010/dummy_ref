from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.app_controller import AppController


class ConsoleWidget(QWidget):
    log_line = Signal(str)

    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._listener_token: int | None = None

        self._build_ui()
        self.log_line.connect(self._append_log_line)
        self._listener_token = self.controller.serial_client.register_listener(self._on_serial_line)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        send_box = QGroupBox("Manual Serial Command")
        send_layout = QHBoxLayout(send_box)
        self.input_cmd = QLineEdit()
        self.input_cmd.setPlaceholderText("Type command, e.g. #GETJPOS or !START")
        self.input_cmd.returnPressed.connect(self._send_current_command)
        self.btn_send = QPushButton("Send")
        self.btn_send.clicked.connect(self._send_current_command)
        self.chk_wait_reply = QCheckBox("Wait one reply")
        self.chk_wait_reply.setChecked(False)
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(0.05, 3.0)
        self.timeout_spin.setSingleStep(0.05)
        self.timeout_spin.setValue(0.30)
        self.timeout_spin.setSuffix(" s")
        send_layout.addWidget(self.input_cmd, 1)
        send_layout.addWidget(self.btn_send)
        send_layout.addWidget(self.chk_wait_reply)
        send_layout.addWidget(QLabel("Timeout"))
        send_layout.addWidget(self.timeout_spin)
        send_layout.addWidget(QLabel("Auto newline: ON"))

        quick_box = QGroupBox("Quick Commands")
        quick_layout = QHBoxLayout(quick_box)
        self._quick_cmds = [
            "!START",
            "!STOP",
            "!DISABLE",
            "!HOME",
            "#GETJPOS",
            "#CMDMODE 2",
            "#CMDMODE 5",
            "!LEDON",
            "!LEDOFF",
            "!RGBON",
            "!RGBOFF",
            "#RGBMODE 0",
            "#RGBCOLOR 255 120 40",
            "$0,0,0,0,0,0",
        ]
        for cmd in self._quick_cmds:
            btn = QPushButton(cmd)
            btn.clicked.connect(lambda _checked=False, c=cmd: self._send_command(c))
            quick_layout.addWidget(btn)
        quick_layout.addStretch(1)

        log_box = QGroupBox("Raw RX/TX Log")
        log_layout = QVBoxLayout(log_box)
        tool_row = QHBoxLayout()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Serial RX/TX lines...")
        self.btn_clear = QPushButton("Clear Log")
        self.btn_clear.clicked.connect(self.log_view.clear)
        tool_row.addStretch(1)
        tool_row.addWidget(self.btn_clear)
        log_layout.addLayout(tool_row)
        log_layout.addWidget(self.log_view)

        root.addWidget(send_box)
        root.addWidget(quick_box)
        root.addWidget(log_box, 1)

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def _append_log_line(self, line: str) -> None:
        self.log_view.appendPlainText(line)
        if self.log_view.document().blockCount() > 3000:
            self.log_view.clear()
            self.log_view.appendPlainText(f"{self._timestamp()} [SYS] log trimmed")
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def _send_current_command(self) -> None:
        text = self.input_cmd.text().strip()
        if not text:
            return
        self._send_command(text)

    def _send_command(self, text: str) -> None:
        cmd = text.strip()
        if not cmd:
            return
        self.log_line.emit(f"{self._timestamp()} [TX] {cmd}")
        try:
            self.controller.send_manual_command(
                cmd,
                wait_reply=self.chk_wait_reply.isChecked(),
                timeout_s=float(self.timeout_spin.value()),
            )
        except Exception as exc:
            self.log_line.emit(f"{self._timestamp()} [ERR] {exc}")

    def _on_serial_line(self, line: str) -> None:
        self.log_line.emit(f"{self._timestamp()} [RX] {line}")

    def dispose(self) -> None:
        if self._listener_token is not None:
            self.controller.serial_client.unregister_listener(self._listener_token)
            self._listener_token = None

    def closeEvent(self, event) -> None:  # noqa: N802
        self.dispose()
        event.accept()
