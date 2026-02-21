from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.app_controller import AppController
from .console_widget import ConsoleWidget


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self._last_alarm_count = 0
        self._pause_state = False
        self._last_ui_state: Dict[str, str] = {}

        self.setWindowTitle("Teacher Console - Ubuntu22.04")
        self.resize(1280, 760)
        self.setMinimumSize(1080, 680)
        self._build_ui()
        self._load_theme()

        self._refresh_ports()
        self._pull_params_from_controller()
        self._fill_program_table(self.controller.program_runner.program)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_state)
        self.timer.start(150)

    def _wrap_scroll(self, content: QWidget) -> QScrollArea:
        area = QScrollArea(self)
        area.setWidgetResizable(True)
        area.setWidget(content)
        area.setFrameShape(QScrollArea.NoFrame)
        return area

    def _make_collapsible(self, title: str, content: QWidget, expanded: bool = False) -> QGroupBox:
        box = QGroupBox(title)
        box.setCheckable(True)
        box.setChecked(expanded)
        layout = QVBoxLayout(box)
        layout.addWidget(content)

        def _toggle(flag: bool) -> None:
            content.setVisible(flag)

        box.toggled.connect(_toggle)
        content.setVisible(expanded)
        return box

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)
        self.setCentralWidget(central)

        root.addWidget(self._build_top_bar())

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._wrap_scroll(self._build_dashboard_tab()), "Dashboard")
        self.tabs.addTab(self._wrap_scroll(self._build_teach_tab()), "Teach")
        self.tabs.addTab(self._wrap_scroll(self._build_program_tab()), "Program")
        self.tabs.addTab(self._wrap_scroll(self._build_modes_tab()), "Modes")
        self.tabs.addTab(self._wrap_scroll(self._build_safety_tab()), "Safety")
        self.console_widget = ConsoleWidget(self.controller)
        self.tabs.addTab(self.console_widget, "Console")
        root.addWidget(self.tabs, 1)

    def _build_top_bar(self) -> QWidget:
        box = QGroupBox("Core Controls")
        layout = QHBoxLayout(box)
        layout.setSpacing(8)

        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(180)

        self.btn_refresh_ports = QPushButton("Refresh")
        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_start = QPushButton("!START")
        self.btn_disable = QPushButton("!DISABLE")
        self.btn_estop = QPushButton("EMERGENCY")
        self.btn_estop.setObjectName("estopButton")

        self.lbl_top_status = QLabel("Disconnected")
        self.lbl_top_mode = QLabel("Mode: -")
        self.lbl_top_model = QLabel("Model: -")

        for w in [
            self.port_combo,
            self.btn_refresh_ports,
            self.btn_connect,
            self.btn_disconnect,
            self.btn_start,
            self.btn_disable,
            self.btn_estop,
            self.lbl_top_status,
            self.lbl_top_mode,
            self.lbl_top_model,
        ]:
            layout.addWidget(w)
        layout.addStretch(1)

        self.btn_refresh_ports.clicked.connect(self._refresh_ports)
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        self.btn_disconnect.clicked.connect(self._on_disconnect_clicked)
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_disable.clicked.connect(self._on_disable_clicked)
        self.btn_estop.clicked.connect(self._on_estop_clicked)
        return box

    def _build_dashboard_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        joints_box = QGroupBox("Joints (deg)")
        joints_grid = QGridLayout(joints_box)
        self.joint_labels: List[QLabel] = []
        for i in range(6):
            lbl_name = QLabel(f"J{i + 1}")
            lbl_val = QLabel("0.000")
            lbl_val.setObjectName("jointValue")
            joints_grid.addWidget(lbl_name, i // 3, (i % 3) * 2)
            joints_grid.addWidget(lbl_val, i // 3, (i % 3) * 2 + 1)
            self.joint_labels.append(lbl_val)

        status_box = QGroupBox("Runtime")
        status_grid = QGridLayout(status_box)
        self.lbl_conn = QLabel("-")
        self.lbl_enabled = QLabel("-")
        self.lbl_mode = QLabel("-")
        self.lbl_txrx = QLabel("-")
        self.lbl_last_line = QLabel("-")
        self.lbl_currents = QLabel("-")
        status_grid.addWidget(QLabel("Connection"), 0, 0)
        status_grid.addWidget(self.lbl_conn, 0, 1)
        status_grid.addWidget(QLabel("Enabled"), 1, 0)
        status_grid.addWidget(self.lbl_enabled, 1, 1)
        status_grid.addWidget(QLabel("Mode"), 2, 0)
        status_grid.addWidget(self.lbl_mode, 2, 1)
        status_grid.addWidget(QLabel("TX/RX"), 3, 0)
        status_grid.addWidget(self.lbl_txrx, 3, 1)
        status_grid.addWidget(QLabel("Currents(A)"), 4, 0)
        status_grid.addWidget(self.lbl_currents, 4, 1)
        status_grid.addWidget(QLabel("Last line"), 5, 0)
        status_grid.addWidget(self.lbl_last_line, 5, 1)

        setup_content = QWidget()
        setup_layout = QVBoxLayout(setup_content)
        setup_row = QHBoxLayout()
        self.edt_urdf = QLineEdit()
        self.edt_urdf.setPlaceholderText("URDF path")
        self.edt_urdf.setReadOnly(True)
        self.edt_urdf.setText(str(self.controller.config["model"].get("urdf_path", "")))
        self.btn_pick_urdf = QPushButton("Select URDF")
        self.btn_reload_urdf = QPushButton("Reload")
        self.btn_refresh_device_state = QPushButton("Refresh Device Status")
        setup_row.addWidget(self.edt_urdf, 1)
        setup_row.addWidget(self.btn_pick_urdf)
        setup_row.addWidget(self.btn_reload_urdf)
        setup_layout.addLayout(setup_row)
        setup_layout.addWidget(self.btn_refresh_device_state)
        setup_box = self._make_collapsible("Setup / Diagnostics", setup_content, expanded=False)

        layout.addWidget(joints_box)
        layout.addWidget(status_box)
        layout.addWidget(setup_box)
        layout.addStretch(1)

        self.btn_pick_urdf.clicked.connect(self._on_pick_urdf)
        self.btn_reload_urdf.clicked.connect(self._on_reload_urdf)
        self.btn_refresh_device_state.clicked.connect(self._on_refresh_device_state)
        return page

    def _build_teach_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        ctl = QGroupBox("Teach Controls")
        ctl_layout = QHBoxLayout(ctl)
        self.spn_angle_threshold = QDoubleSpinBox()
        self.spn_angle_threshold.setRange(0.1, 30.0)
        self.spn_angle_threshold.setSingleStep(0.1)
        self.spn_angle_threshold.setValue(2.0)
        self.spn_time_threshold = QDoubleSpinBox()
        self.spn_time_threshold.setRange(0.1, 30.0)
        self.spn_time_threshold.setSingleStep(0.1)
        self.spn_time_threshold.setValue(5.0)

        self.btn_record_start = QPushButton("Start Record")
        self.btn_record_stop = QPushButton("Stop Record")
        self.btn_record_play = QPushButton("Play Recorded")
        self.btn_record_csv = QPushButton("Export CSV")
        self.btn_record_yaml = QPushButton("Export YAML")

        ctl_layout.addWidget(QLabel("Angle threshold"))
        ctl_layout.addWidget(self.spn_angle_threshold)
        ctl_layout.addWidget(QLabel("Time threshold(s)"))
        ctl_layout.addWidget(self.spn_time_threshold)
        ctl_layout.addWidget(self.btn_record_start)
        ctl_layout.addWidget(self.btn_record_stop)
        ctl_layout.addWidget(self.btn_record_play)
        ctl_layout.addStretch(1)

        export_content = QWidget()
        export_row = QHBoxLayout(export_content)
        export_row.addWidget(self.btn_record_csv)
        export_row.addWidget(self.btn_record_yaml)
        export_row.addStretch(1)
        export_box = self._make_collapsible("Export Options", export_content, expanded=False)

        self.record_table = QTableWidget(0, 8)
        self.record_table.setHorizontalHeaderLabels(["t_s", "j1", "j2", "j3", "j4", "j5", "j6", "note"])
        self.record_table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(ctl)
        layout.addWidget(export_box)
        layout.addWidget(QLabel("Tip: recording works when connected, even if robot is not enabled."))
        layout.addWidget(self.record_table)

        self.btn_record_start.clicked.connect(self._on_record_start)
        self.btn_record_stop.clicked.connect(self._on_record_stop)
        self.btn_record_play.clicked.connect(self._on_record_play)
        self.btn_record_csv.clicked.connect(self._on_record_export_csv)
        self.btn_record_yaml.clicked.connect(self._on_record_export_yaml)
        return page

    def _build_program_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        ctl = QGroupBox("Program Controls")
        ctl_layout = QHBoxLayout(ctl)
        self.btn_program_load = QPushButton("Load YAML")
        self.btn_program_save = QPushButton("Save YAML")
        self.btn_program_add = QPushButton("Add Step")
        self.btn_program_del = QPushButton("Delete Step")
        self.btn_program_play = QPushButton("Play")
        self.btn_program_pause = QPushButton("Pause")
        self.btn_program_stop = QPushButton("Stop")
        for w in [
            self.btn_program_load,
            self.btn_program_play,
            self.btn_program_pause,
            self.btn_program_stop,
        ]:
            ctl_layout.addWidget(w)
        ctl_layout.addStretch(1)

        edit_content = QWidget()
        edit_row = QHBoxLayout(edit_content)
        edit_row.addWidget(self.btn_program_save)
        edit_row.addWidget(self.btn_program_add)
        edit_row.addWidget(self.btn_program_del)
        edit_row.addStretch(1)
        edit_box = self._make_collapsible("Edit Options", edit_content, expanded=False)

        cols = [
            "mode",
            "duration_s",
            "speed_deg_s",
            "j1",
            "j2",
            "j3",
            "j4",
            "j5",
            "j6",
            "kp(csv6)",
            "kd(csv6)",
            "comment",
        ]
        self.program_table = QTableWidget(0, len(cols))
        self.program_table.setHorizontalHeaderLabels(cols)
        self.program_table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(ctl)
        layout.addWidget(edit_box)
        layout.addWidget(self.program_table)

        self.btn_program_load.clicked.connect(self._on_program_load)
        self.btn_program_save.clicked.connect(self._on_program_save)
        self.btn_program_add.clicked.connect(self._on_program_add_row)
        self.btn_program_del.clicked.connect(self._on_program_del_row)
        self.btn_program_play.clicked.connect(self._on_program_play)
        self.btn_program_pause.clicked.connect(self._on_program_pause_resume)
        self.btn_program_stop.clicked.connect(self._on_program_stop)
        return page

    def _build_modes_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)

        mode_box = QGroupBox("Mode Actions")
        mode_layout = QHBoxLayout(mode_box)
        self.btn_zero_start = QPushButton("Start Zero-G")
        self.btn_zero_stop = QPushButton("Stop Zero-G")
        self.btn_imp_start = QPushButton("Start Impedance")
        self.btn_imp_stop = QPushButton("Stop Impedance")
        self.btn_imp_capture = QPushButton("Capture q_ref")
        for w in [self.btn_zero_start, self.btn_zero_stop, self.btn_imp_start, self.btn_imp_stop, self.btn_imp_capture]:
            mode_layout.addWidget(w)
        mode_layout.addStretch(1)

        params = QGroupBox("Control Params")
        params_grid = QGridLayout(params)
        self.edit_k_tau2i = self._make_vec_editor()
        self.edit_i_bias = self._make_vec_editor()
        self.edit_kp = self._make_vec_editor()
        self.edit_kd = self._make_vec_editor()
        self.spn_current_limit = QDoubleSpinBox()
        self.spn_current_limit.setRange(0.1, 3.0)
        self.spn_current_limit.setSingleStep(0.05)
        self.spn_current_limit.setValue(1.5)
        self.btn_apply_params = QPushButton("Apply Params")
        self.chk_save_config = QCheckBox("Save into config")
        self.chk_save_config.setChecked(True)

        params_grid.addWidget(QLabel("k_tau2i"), 0, 0)
        params_grid.addLayout(self.edit_k_tau2i, 0, 1)
        params_grid.addWidget(QLabel("i_bias"), 1, 0)
        params_grid.addLayout(self.edit_i_bias, 1, 1)
        params_grid.addWidget(QLabel("Kp"), 2, 0)
        params_grid.addLayout(self.edit_kp, 2, 1)
        params_grid.addWidget(QLabel("Kd"), 3, 0)
        params_grid.addLayout(self.edit_kd, 3, 1)
        params_grid.addWidget(QLabel("Current limit(A)"), 4, 0)
        params_grid.addWidget(self.spn_current_limit, 4, 1)
        params_grid.addWidget(self.btn_apply_params, 5, 0)
        params_grid.addWidget(self.chk_save_config, 5, 1)

        root.addWidget(mode_box)
        root.addWidget(params)

        light_content = QWidget()
        light_grid = QGridLayout(light_content)
        self.btn_led_on = QPushButton("LED ON")
        self.btn_led_off = QPushButton("LED OFF")
        self.btn_rgb_on = QPushButton("RGB ON")
        self.btn_rgb_off = QPushButton("RGB OFF")
        self.cmb_rgb_mode = QComboBox()
        self.cmb_rgb_mode.addItems(
            [
                "0 RAINBOW",
                "1 FADE",
                "2 BLINK",
                "3 ALL_RED",
                "4 ALL_GREEN",
                "5 ALL_BLUE",
                "6 ALL_OFF",
                "7 CUSTOM_COLOR",
            ]
        )
        self.btn_rgb_mode_apply = QPushButton("Apply Mode")
        self.spn_rgb_r = QDoubleSpinBox()
        self.spn_rgb_g = QDoubleSpinBox()
        self.spn_rgb_b = QDoubleSpinBox()
        for spn in [self.spn_rgb_r, self.spn_rgb_g, self.spn_rgb_b]:
            spn.setRange(0, 255)
            spn.setSingleStep(1)
            spn.setDecimals(0)
        self.btn_rgb_color_apply = QPushButton("Apply RGB")

        light_grid.addWidget(self.btn_led_on, 0, 0)
        light_grid.addWidget(self.btn_led_off, 0, 1)
        light_grid.addWidget(self.btn_rgb_on, 1, 0)
        light_grid.addWidget(self.btn_rgb_off, 1, 1)
        light_grid.addWidget(QLabel("RGB Mode"), 2, 0)
        light_grid.addWidget(self.cmb_rgb_mode, 2, 1)
        light_grid.addWidget(self.btn_rgb_mode_apply, 2, 2)
        light_grid.addWidget(QLabel("R"), 3, 0)
        light_grid.addWidget(self.spn_rgb_r, 3, 1)
        light_grid.addWidget(QLabel("G"), 4, 0)
        light_grid.addWidget(self.spn_rgb_g, 4, 1)
        light_grid.addWidget(QLabel("B"), 5, 0)
        light_grid.addWidget(self.spn_rgb_b, 5, 1)
        light_grid.addWidget(self.btn_rgb_color_apply, 5, 2)
        light_box = self._make_collapsible("Lighting", light_content, expanded=False)

        root.addWidget(light_box)
        root.addStretch(1)

        self.btn_zero_start.clicked.connect(self._on_zero_start)
        self.btn_zero_stop.clicked.connect(self._on_zero_stop)
        self.btn_imp_start.clicked.connect(self._on_imp_start)
        self.btn_imp_stop.clicked.connect(self._on_imp_stop)
        self.btn_imp_capture.clicked.connect(self._on_imp_capture)
        self.btn_apply_params.clicked.connect(self._on_apply_params)
        self.btn_led_on.clicked.connect(self._on_led_on)
        self.btn_led_off.clicked.connect(self._on_led_off)
        self.btn_rgb_on.clicked.connect(self._on_rgb_on)
        self.btn_rgb_off.clicked.connect(self._on_rgb_off)
        self.btn_rgb_mode_apply.clicked.connect(self._on_rgb_mode_apply)
        self.btn_rgb_color_apply.clicked.connect(self._on_rgb_color_apply)
        return page

    def _build_safety_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        buttons = QGroupBox("Safety Actions")
        b = QHBoxLayout(buttons)
        self.btn_stop_only = QPushButton("Send !STOP")
        self.btn_disable_only = QPushButton("Send !DISABLE")
        self.btn_zero_currents = QPushButton("Send $0,...,0")
        self.btn_clear_alarms = QPushButton("Clear Log")
        for w in [self.btn_stop_only, self.btn_disable_only, self.btn_zero_currents, self.btn_clear_alarms]:
            b.addWidget(w)
        b.addStretch(1)

        self.alarm_log = QTextEdit()
        self.alarm_log.setReadOnly(True)
        self.alarm_log.setPlaceholderText("Runtime alarms and events...")

        layout.addWidget(buttons)
        layout.addWidget(self.alarm_log)

        self.btn_stop_only.clicked.connect(self._on_stop_only)
        self.btn_disable_only.clicked.connect(self._on_disable_clicked)
        self.btn_zero_currents.clicked.connect(self._on_zero_currents)
        self.btn_clear_alarms.clicked.connect(self._on_clear_alarms)
        return page

    def _make_vec_editor(self):
        layout = QHBoxLayout()
        edits: List[QDoubleSpinBox] = []
        for i in range(6):
            spn = QDoubleSpinBox()
            spn.setRange(-10.0, 10.0)
            spn.setSingleStep(0.01)
            spn.setDecimals(4)
            spn.setObjectName(f"vec_{i}")
            spn.setFixedWidth(100)
            layout.addWidget(spn)
            edits.append(spn)
        layout._spins = edits  # type: ignore[attr-defined]
        return layout

    def _vec_values(self, layout) -> List[float]:
        return [float(s.value()) for s in layout._spins]  # type: ignore[attr-defined]

    def _set_vec_values(self, layout, values: List[float]) -> None:
        vals = values if len(values) == 6 else [0] * 6
        for i, spn in enumerate(layout._spins):  # type: ignore[attr-defined]
            spn.setValue(float(vals[i]))

    def _load_theme(self) -> None:
        qss_path = Path(__file__).with_name("theme.qss")
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    def _show_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Error", msg)

    def _show_info(self, msg: str) -> None:
        QMessageBox.information(self, "Info", msg)

    def _refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = self.controller.list_serial_ports()
        self.port_combo.addItems(ports)
        if current in ports:
            self.port_combo.setCurrentText(current)

    def _on_connect_clicked(self) -> None:
        if not self.port_combo.currentText().strip():
            self._show_error("No serial port selected")
            return
        try:
            self.controller.connect_serial(self.port_combo.currentText())
        except Exception as exc:
            self._show_error(str(exc))

    def _on_pick_urdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select URDF", ".", "URDF (*.urdf)")
        if not path:
            return
        try:
            ok, message, resolved = self.controller.set_urdf_path(path)
            self.controller.save_config()
            self.edt_urdf.setText(path)
            if ok:
                self._show_info(f"Model loaded:\n{resolved}")
            else:
                self._show_error(f"Model load failed:\n{message}")
        except Exception as exc:
            self._show_error(str(exc))

    def _on_reload_urdf(self) -> None:
        try:
            ok, message, resolved = self.controller.set_urdf_path(str(self.controller.config["model"].get("urdf_path", "")))
            self.edt_urdf.setText(str(self.controller.config["model"].get("urdf_path", "")))
            if ok:
                self._show_info(f"Model reloaded:\n{resolved}")
            else:
                self._show_error(f"Model load failed:\n{message}")
        except Exception as exc:
            self._show_error(str(exc))

    def _on_disconnect_clicked(self) -> None:
        try:
            self.controller.disconnect_serial()
        except Exception as exc:
            self._show_error(str(exc))

    def _on_start_clicked(self) -> None:
        try:
            self.controller.start_robot()
        except Exception as exc:
            self._show_error(str(exc))

    def _on_disable_clicked(self) -> None:
        try:
            self.controller.disable_robot()
        except Exception as exc:
            self._show_error(str(exc))

    def _on_estop_clicked(self) -> None:
        try:
            self.controller.emergency_stop()
            self._show_info("Emergency stop sent: !STOP -> $0,...,0 -> !DISABLE")
        except Exception as exc:
            self._show_error(str(exc))

    def _on_stop_only(self) -> None:
        try:
            self.controller.protocol.stop()
        except Exception as exc:
            self._show_error(str(exc))

    def _on_zero_currents(self) -> None:
        try:
            self.controller.protocol.zero_currents()
        except Exception as exc:
            self._show_error(str(exc))

    def _on_clear_alarms(self) -> None:
        self.controller.state.clear_alarms()
        self.alarm_log.clear()
        self._last_alarm_count = 0

    def _on_led_on(self) -> None:
        try:
            self.controller.set_led_enabled(True)
        except Exception as exc:
            self._show_error(str(exc))

    def _on_led_off(self) -> None:
        try:
            self.controller.set_led_enabled(False)
        except Exception as exc:
            self._show_error(str(exc))

    def _on_rgb_on(self) -> None:
        try:
            self.controller.set_rgb_enabled(True)
        except Exception as exc:
            self._show_error(str(exc))

    def _on_rgb_off(self) -> None:
        try:
            self.controller.set_rgb_enabled(False)
        except Exception as exc:
            self._show_error(str(exc))

    def _on_rgb_mode_apply(self) -> None:
        try:
            mode = int(self.cmb_rgb_mode.currentText().strip().split()[0])
            self.controller.set_rgb_mode(mode)
        except Exception as exc:
            self._show_error(str(exc))

    def _on_rgb_color_apply(self) -> None:
        try:
            self.controller.set_rgb_color(
                int(self.spn_rgb_r.value()),
                int(self.spn_rgb_g.value()),
                int(self.spn_rgb_b.value()),
            )
        except Exception as exc:
            self._show_error(str(exc))

    def _on_refresh_device_state(self) -> None:
        try:
            status = self.controller.refresh_device_runtime_status()
            self._show_info(
                "Device status refreshed:\n"
                f"mode={status['mode']} {status['mode_name']}\n"
                f"enabled={int(bool(status['enabled']))}\n"
                f"rgb_en={int(bool(status['rgb_enabled']))}, rgb_mode={status['rgb_mode']}\n"
                f"rgb=({status['r']},{status['g']},{status['b']}), led_en={int(bool(status['led_enabled']))}"
            )
        except Exception as exc:
            self._show_error(str(exc))

    def _on_record_start(self) -> None:
        try:
            self.controller.start_recording(self.spn_angle_threshold.value(), self.spn_time_threshold.value())
        except Exception as exc:
            self._show_error(str(exc))

    def _on_record_stop(self) -> None:
        self.controller.stop_recording()
        self._refresh_record_table()

    def _on_record_play(self) -> None:
        try:
            self.controller.play_recorded_points(auto_start_if_disabled=True)
            self._pause_state = False
            self.btn_program_pause.setText("Pause")
            self._show_info("Playing recorded points")
        except Exception as exc:
            self._show_error(str(exc))

    def _on_record_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "teach_record.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            self.controller.export_record_csv(path)
            self._show_info(f"Saved: {path}")
        except Exception as exc:
            self._show_error(str(exc))

    def _on_record_export_yaml(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save YAML Program", "teach_program.yaml", "YAML (*.yaml *.yml)")
        if not path:
            return
        try:
            self.controller.export_record_yaml(path)
            self._show_info(f"Saved: {path}")
        except Exception as exc:
            self._show_error(str(exc))

    def _on_program_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Program", "programs", "YAML (*.yaml *.yml)")
        if not path:
            return
        try:
            payload = self.controller.load_program_yaml(path)
            self._fill_program_table(payload)
        except Exception as exc:
            self._show_error(str(exc))

    def _on_program_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Program", "programs/program.yaml", "YAML (*.yaml *.yml)")
        if not path:
            return
        try:
            payload = self._program_from_table()
            self.controller.set_program(payload)
            self.controller.save_program_yaml(path)
            self._show_info(f"Saved: {path}")
        except Exception as exc:
            self._show_error(str(exc))

    def _on_program_add_row(self) -> None:
        row = self.program_table.rowCount()
        self.program_table.insertRow(row)
        defaults = ["movej", "1.0", "20.0", "0", "0", "0", "0", "0", "0", "", "", ""]
        for i, txt in enumerate(defaults):
            self.program_table.setItem(row, i, QTableWidgetItem(txt))

    def _on_program_del_row(self) -> None:
        row = self.program_table.currentRow()
        if row >= 0:
            self.program_table.removeRow(row)

    def _on_program_play(self) -> None:
        try:
            payload = self._program_from_table()
            self.controller.set_program(payload)
            self.controller.start_program()
            self._pause_state = False
            self.btn_program_pause.setText("Pause")
        except Exception as exc:
            self._show_error(str(exc))

    def _on_program_pause_resume(self) -> None:
        if not self.controller.program_runner.is_running():
            return
        if self._pause_state:
            self.controller.resume_program()
            self._pause_state = False
            self.btn_program_pause.setText("Pause")
        else:
            self.controller.pause_program()
            self._pause_state = True
            self.btn_program_pause.setText("Resume")

    def _on_program_stop(self) -> None:
        self.controller.stop_program()
        self._pause_state = False
        self.btn_program_pause.setText("Pause")

    def _on_zero_start(self) -> None:
        try:
            self._on_apply_params()
            self.controller.start_zero_gravity()
        except Exception as exc:
            self._show_error(str(exc))

    def _on_zero_stop(self) -> None:
        self.controller.stop_zero_gravity()

    def _on_imp_start(self) -> None:
        try:
            self._on_apply_params()
            self.controller.start_impedance()
        except Exception as exc:
            self._show_error(str(exc))

    def _on_imp_stop(self) -> None:
        self.controller.stop_impedance()

    def _on_imp_capture(self) -> None:
        self.controller.capture_impedance_ref()

    def _on_apply_params(self) -> None:
        try:
            self.controller.update_control_params(
                k_tau2i=self._vec_values(self.edit_k_tau2i),
                i_bias=self._vec_values(self.edit_i_bias),
                kp=self._vec_values(self.edit_kp),
                kd=self._vec_values(self.edit_kd),
                current_limit_a=self.spn_current_limit.value(),
            )
            if self.chk_save_config.isChecked():
                self.controller.save_config()
        except Exception as exc:
            self._show_error(str(exc))

    def _pull_params_from_controller(self) -> None:
        c = self.controller.control
        self._set_vec_values(self.edit_k_tau2i, c.k_tau2i)
        self._set_vec_values(self.edit_i_bias, c.i_bias)
        self._set_vec_values(self.edit_kp, c.kp)
        self._set_vec_values(self.edit_kd, c.kd)
        self.spn_current_limit.setValue(float(c.current_limit_a))
        self.spn_angle_threshold.setValue(float(self.controller.config["teach"]["angle_threshold_deg"]))
        self.spn_time_threshold.setValue(float(self.controller.config["teach"]["time_threshold_s"]))

    def _program_from_table(self) -> Dict:
        steps = []
        rows = self.program_table.rowCount()
        for r in range(rows):
            def val(c: int, default: str = "") -> str:
                item = self.program_table.item(r, c)
                return item.text().strip() if item else default

            mode = val(0, "movej").lower()
            step = {
                "mode": mode,
                "duration_s": float(val(1, "1.0")),
                "speed_deg_s": float(val(2, "20.0")),
                "comment": val(11, ""),
            }
            if mode in ("movej",):
                step["target_deg"] = [float(val(c, "0")) for c in range(3, 9)]
            kp_text = val(9, "")
            kd_text = val(10, "")
            if kp_text:
                step["kp"] = [float(x) for x in kp_text.split(",")]
            if kd_text:
                step["kd"] = [float(x) for x in kd_text.split(",")]
            steps.append(step)

        payload = {
            "name": "ui_program",
            "version": 1,
            "description": "edited in teacher console",
            "defaults": {"speed_deg_s": 20.0, "duration_s": 1.0},
            "steps": steps,
        }
        return payload

    def _fill_program_table(self, payload: Dict) -> None:
        self.program_table.setRowCount(0)
        for step in payload.get("steps", []):
            row = self.program_table.rowCount()
            self.program_table.insertRow(row)

            target = step.get("target_deg", [0, 0, 0, 0, 0, 0])
            kp = step.get("kp", [])
            kd = step.get("kd", [])
            vals = [
                str(step.get("mode", "movej")),
                str(step.get("duration_s", 1.0)),
                str(step.get("speed_deg_s", 20.0)),
                str(target[0] if len(target) > 0 else 0),
                str(target[1] if len(target) > 1 else 0),
                str(target[2] if len(target) > 2 else 0),
                str(target[3] if len(target) > 3 else 0),
                str(target[4] if len(target) > 4 else 0),
                str(target[5] if len(target) > 5 else 0),
                ",".join([str(v) for v in kp]) if kp else "",
                ",".join([str(v) for v in kd]) if kd else "",
                str(step.get("comment", "")),
            ]
            for i, txt in enumerate(vals):
                self.program_table.setItem(row, i, QTableWidgetItem(txt))

    def _refresh_record_table(self) -> None:
        points = self.controller.get_record_points()
        self.record_table.setRowCount(0)
        for p in points[-500:]:
            row = self.record_table.rowCount()
            self.record_table.insertRow(row)
            vals = [f"{p.t_s:.3f}", *[f"{v:.3f}" for v in p.joints_deg], ""]
            for i, txt in enumerate(vals):
                self.record_table.setItem(row, i, QTableWidgetItem(txt))

    def _set_text_if_changed(self, key: str, widget: QLabel, text: str) -> None:
        if self._last_ui_state.get(key) == text:
            return
        widget.setText(text)
        self._last_ui_state[key] = text

    def _refresh_state(self) -> None:
        snap = self.controller.state.snapshot()
        model_status = self.controller.get_model_status()
        mode_name = self.controller.cmdmode_name(snap.mode)
        for i in range(6):
            self._set_text_if_changed(f"joint_{i}", self.joint_labels[i], f"{snap.joints_deg[i]:.3f}")

        self._set_text_if_changed("conn", self.lbl_conn, "Connected" if snap.connected else "Disconnected")
        self._set_text_if_changed("enabled", self.lbl_enabled, "ON" if snap.enabled else "OFF")
        self._set_text_if_changed("mode", self.lbl_mode, f"{snap.mode} {mode_name}")
        self._set_text_if_changed("txrx", self.lbl_txrx, f"{snap.tx_count}/{snap.rx_count}")
        self._set_text_if_changed("last_line", self.lbl_last_line, snap.last_line[:180])
        self._set_text_if_changed("currents", self.lbl_currents, ", ".join([f"{v:.2f}" for v in snap.currents_a]))

        self._set_text_if_changed("top_status", self.lbl_top_status, "Connected" if snap.connected else "Disconnected")
        self._set_text_if_changed("top_mode", self.lbl_top_mode, f"Mode: {snap.mode} {mode_name}")
        model_loaded = bool(model_status.get("loaded", False))
        model_text = "Model: Loaded" if model_loaded else "Model: Failed"
        self._set_text_if_changed("top_model", self.lbl_top_model, model_text)
        model_tip = str(model_status.get("path", "")) if model_loaded else str(model_status.get("error", ""))
        self.lbl_top_model.setToolTip(model_tip)

        if len(snap.alarms) < self._last_alarm_count:
            self.alarm_log.setPlainText("\n".join(snap.alarms[-500:]))
            self._last_alarm_count = len(snap.alarms)
        elif len(snap.alarms) > self._last_alarm_count:
            new_lines = snap.alarms[self._last_alarm_count :]
            for line in new_lines:
                self.alarm_log.append(line)
            self.alarm_log.verticalScrollBar().setValue(self.alarm_log.verticalScrollBar().maximum())
            self._last_alarm_count = len(snap.alarms)

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.console_widget.dispose()
        except Exception:
            pass
        try:
            self.controller.shutdown()
        except Exception:
            pass
        event.accept()
