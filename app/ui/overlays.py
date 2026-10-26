"""뷰어 위에 떠 있는 작은 창들: 선택 막대, 변환 진행 카드 (5-3, 5-4)."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QToolButton, QVBoxLayout, QWidget

from app.ui.icons import icon
from app.ui.theme import COLOR, SIZE
from app.ui.widgets import vline


class SelectionBar(QWidget):
    """쪽을 고르면 뷰어 아래 가운데에 나타난다: N쪽 선택됨 | 회전 | 삭제 | 페이지 교체 | ✕"""
    rotate_clicked = Signal()
    delete_clicked = Signal()
    replace_clicked = Signal()
    clear_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("selectionBar")
        self.setAttribute(Qt.WA_StyledBackground)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 4, 4)
        layout.setSpacing(4)

        self.count_label = QLabel("")
        self.rotate_button = self._button("회전", "rotate_right", "선택한 쪽을 오른쪽으로 90° 돌려요 (파일에 반영)")
        self.delete_button = self._button("삭제", "trash", "선택한 쪽을 지워요 (Delete)")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.setIcon(icon("trash", "#F2A7A1"))
        self.replace_button = self._button("페이지 교체", "replace", "원본 hwp에서 다시 변환해 바꿔 끼워요")
        self.close_button = self._button("", "close", "선택 해제 (Esc)")

        layout.addWidget(self.count_label)
        layout.addSpacing(8)
        layout.addWidget(vline())
        for w in (self.rotate_button, self.delete_button, self.replace_button):
            layout.addWidget(w)
        layout.addWidget(vline())
        layout.addWidget(self.close_button)

        self.rotate_button.clicked.connect(self.rotate_clicked)
        self.delete_button.clicked.connect(self.delete_clicked)
        self.replace_button.clicked.connect(self.replace_clicked)
        self.close_button.clicked.connect(self.clear_clicked)
        self.hide()

    def _button(self, text: str, icon_name: str, tooltip: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setIcon(icon(icon_name, COLOR["white"]))
        btn.setIconSize(QSize(SIZE["icon"], SIZE["icon"]))
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if text else Qt.ToolButtonIconOnly)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.TabFocus)
        return btn

    def set_count(self, count: int) -> None:
        self.count_label.setText(f"{count}쪽 선택됨")
        self.setVisible(count > 0)
        self.adjustSize()


class EditPreview(QWidget):
    """글자 수정: 고칠 글자 바로 아래(자리가 없으면 위)에 뜨는 '수정 후' 미리보기 카드."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("editPreview")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)  # 카드가 쪽 위의 드래그를 막지 않게
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 10)
        layout.setSpacing(4)
        self.caption = QLabel("수정 후 미리보기")
        self.caption.setProperty("text_role", "sub")
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        self.error = QLabel("")
        self.error.setObjectName("warningText")
        self.error.setWordWrap(True)
        layout.addWidget(self.caption)
        layout.addWidget(self.image)
        layout.addWidget(self.error)
        self.hide()

    def show_result(self, pixmap, error: str = "") -> None:
        self.image.setVisible(pixmap is not None and not error)
        if pixmap is not None and not error:
            self.image.setPixmap(pixmap)
        self.error.setText(error)
        self.error.setVisible(bool(error))
        if error:
            self.error.setMaximumWidth(360)
        self.adjustSize()
        self.show()
        self.raise_()

    def place_near(self, target, area) -> None:
        """target(고른 글자 영역, 부모 좌표) 바로 아래에, 자리가 없으면 위에 놓는다. area 밖으로 나가지 않게."""
        gap = 8
        x = max(area.left() + 8, min(target.center().x() - self.width() // 2, area.right() - self.width() - 8))
        y = target.bottom() + gap
        if y + self.height() > area.bottom() - 70:     # 아래쪽 보기 막대와 겹치지 않게
            y = target.top() - gap - self.height()
        self.move(int(x), int(max(area.top() + 8, y)))


class ProgressCard(QWidget):
    """변환 진행: 파일 이름, 지금 단계, 진행 막대 (뷰어 왼쪽 아래)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("progressCard")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setFixedWidth(300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(4)
        self.title = QLabel("")
        self.title.setStyleSheet("font-weight: 600;")
        self.stage = QLabel("")
        self.stage.setProperty("text_role", "sub")
        self.stage.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        layout.addWidget(self.title)
        layout.addWidget(self.stage)
        layout.addSpacing(4)
        layout.addWidget(self.bar)
        self.hide()

    def show_progress(self, name: str, stage: str, done: int, total: int) -> None:
        metrics = self.title.fontMetrics()
        self.title.setText(metrics.elidedText(name or "파일 넣기", Qt.ElideMiddle, 268))
        self.stage.setText(f"{stage} ({min(done + 1, total)}/{total})" if done < total else stage)
        self.bar.setMaximum(total)
        self.bar.setValue(done)
        self.adjustSize()
        self.show()
        self.raise_()
