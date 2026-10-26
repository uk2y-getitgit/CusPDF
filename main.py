"""보고서 PDF 편집기 — 프로그램 시작점."""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.ui import theme
from app.ui.drop_reader import cleanup_temp
from app.ui.main_window import APP_TITLE, MainWindow

ICON = Path(__file__).resolve().parent / "app" / "resources" / "icon.ico"


def main() -> int:
    if len(sys.argv) >= 4 and sys.argv[1] == "--selftest":  # 개발자용 자체 점검 (화면 없음)
        from app.selftest import run
        return run(sys.argv[2], sys.argv[3])

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    if ICON.exists():
        app.setWindowIcon(QIcon(str(ICON)))
    theme.apply(app)
    cleanup_temp()

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
