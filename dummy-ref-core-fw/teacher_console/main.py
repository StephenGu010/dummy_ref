from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QApplication

from teacher_console.core.app_controller import AppController
from teacher_console.ui.main_window import MainWindow


def _default_config_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    return root / "config" / "robot_profile.yaml"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Teacher Console (PySide6)")
    parser.add_argument("--config", type=str, default=str(_default_config_path()), help="YAML config path")
    parser.add_argument("--port", type=str, default="", help="Override serial port, e.g. /dev/ttyACM0")
    return parser


def _install_signal_handlers(app: QApplication, controller: AppController) -> None:
    def _handler(_sig: int, _frame: Optional[object]) -> None:
        try:
            controller.shutdown()
        except Exception:
            pass
        app.quit()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except Exception:
            continue


def main() -> int:
    args = _build_arg_parser().parse_args()
    app = QApplication(sys.argv)

    controller = AppController(config_path=args.config)
    if args.port:
        controller.config["serial"]["port"] = args.port

    app.aboutToQuit.connect(controller.shutdown)
    _install_signal_handlers(app, controller)

    window = MainWindow(controller)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
