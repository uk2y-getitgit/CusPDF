"""상태 막대(맨 아래): 왼쪽 최근 작업 메시지, 오른쪽 한글·엑셀·워드 연결 상태 (5-3)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.ui.theme import COLOR, SIZE


class StatusBar(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("statusBar")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setFixedHeight(4 * SIZE["space"])

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2 * SIZE["space"], 0, 2 * SIZE["space"], 0)
        layout.setSpacing(6)

        self.message = QLabel("준비됨")
        self.message.setProperty("text_role", "sub")
        self.office_dot = QLabel("●")
        self.office_status = QLabel("")
        self.office_status.setProperty("text_role", "sub")

        layout.addWidget(self.message)
        layout.addStretch(1)
        layout.addWidget(self.office_dot)
        layout.addWidget(self.office_status)

        # 실제 연결 확인은 변환 기능 단계(9~11번)에서 붙인다
        self.set_office_status("한글·엑셀·워드 연결 확인 전", connected=None)

    def show_message(self, text: str) -> None:
        self.message.setText(text)

    def set_office_status(self, text: str, connected: bool | None) -> None:
        """connected: True=초록 점, False=빨간 점, None=회색 점(확인 전)."""
        color = {True: COLOR["success"], False: COLOR["danger"], None: COLOR["line"]}[connected]
        self.office_dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        self.office_status.setText(text)
