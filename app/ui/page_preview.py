"""옆 창의 쪽을 크게 보는 창 (넣을 쪽 확인용).

- ‹ › 단추, ←/→, PgUp/PgDn, 마우스 휠로 앞뒤 쪽
- [넣을 쪽으로 고르기] 체크 (Space) → 옆 창 고르기와 함께 바뀜
- 창 크기를 바꾸거나 최대화하면 쪽도 그만큼 크게
"""

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui.side_panel import SideList
from app.ui.theme import COLOR
from app.ui.widgets import button


class PagePreview(QDialog):
    def __init__(self, side_list: SideList, row: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.side = side_list
        self.row = row
        self.setWindowTitle("크게 보기")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        screen = (parent.screen() if parent else self.screen()).availableGeometry()
        self.resize(int(screen.height() * 0.62), int(screen.height() * 0.85))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        top = QHBoxLayout()
        self.title = QLabel("")
        self.title.setProperty("text_role", "title")
        self.check = QCheckBox("넣을 쪽으로 고르기 (Space)")
        top.addWidget(self.title, 1)
        top.addWidget(self.check)

        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumSize(200, 200)
        self.image.setStyleSheet(f"background: {COLOR['viewer']}; border-radius: 8px;")

        bottom = QHBoxLayout()
        self.prev_button = button("‹ 이전 쪽", tooltip="← 또는 PgUp")
        self.next_button = button("다음 쪽 ›", tooltip="→ 또는 PgDn")
        close = button("닫기", tooltip="Esc")
        bottom.addWidget(self.prev_button)
        bottom.addWidget(self.next_button)
        bottom.addStretch(1)
        bottom.addWidget(close)

        layout.addLayout(top)
        layout.addWidget(self.image, 1)
        layout.addLayout(bottom)

        # 키보드(←→, Space)는 이 창이 받도록 단추·체크는 포커스를 받지 않게
        for w in (self.prev_button, self.next_button, close, self.check):
            w.setFocusPolicy(Qt.NoFocus)
        self.setFocusPolicy(Qt.StrongFocus)
        self.prev_button.clicked.connect(lambda: self.step(-1))
        self.next_button.clicked.connect(lambda: self.step(1))
        close.clicked.connect(self.close)
        self.check.toggled.connect(self._on_check)
        self.side.checked_changed.connect(self._sync_check)
        self._render_timer = QTimer(self, singleShot=True, interval=60, timeout=self._render)
        self.show_page(row)

    def show_page(self, row: int) -> None:
        count = self.side.document.page_count
        self.row = max(0, min(count - 1, row))
        self.title.setText(f"{self.side.document.name}  ·  {self.row + 1} / {count}쪽")
        self.prev_button.setEnabled(self.row > 0)
        self.next_button.setEnabled(self.row < count - 1)
        self._sync_check()
        self.side.scrollToItem(self.side.item(self.row))
        self._render()

    def step(self, delta: int) -> None:
        self.show_page(self.row + delta)

    def _render(self) -> None:
        """보이는 칸에 꼭 맞게 쪽을 그린다 (흐리지 않게 화면 배율만큼 크게)."""
        doc = self.side.document
        area = self.image.size() - QSize(16, 16)
        w_pt, h_pt = doc.page_size(self.row)
        ratio = self.devicePixelRatioF()
        scale = min(area.width() / w_pt, area.height() / h_pt) * ratio
        pixmap = QPixmap.fromImage(doc.render(self.row, max(scale, 0.1)))
        pixmap.setDevicePixelRatio(ratio)
        self.image.setPixmap(pixmap)

    def _sync_check(self) -> None:
        self.check.blockSignals(True)
        self.check.setChecked(self.row in self.side.checked)
        self.check.blockSignals(False)

    def _on_check(self, on: bool) -> None:
        self.side.set_checked(self.row, on)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._render_timer.start()

    def wheelEvent(self, event) -> None:  # noqa: N802
        self.step(-1 if event.angleDelta().y() > 0 else 1)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key_Left, Qt.Key_PageUp, Qt.Key_Up):
            self.step(-1)
        elif key in (Qt.Key_Right, Qt.Key_PageDown, Qt.Key_Down):
            self.step(1)
        elif key == Qt.Key_Space:
            self.check.toggle()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.side.checked_changed.disconnect(self._sync_check)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)
