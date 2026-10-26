"""보기 메뉴: 보기 막대의 [보기 방식 ▾]를 누르면 위로 열린다 (5-5)."""

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction

from app.ui.icons import icon
from app.ui.page_view import LAYOUTS
from app.ui.theme import SIZE
from app.ui.widgets import make_floating, menu_heading


class LayoutTiles(QWidget):
    """페이지 배치 5종을 그림 아이콘 타일로 보여준다."""
    chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(12, 4, 12, 8)
        grid.setSpacing(6)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QToolButton] = {}
        for n, (key, text) in enumerate(LAYOUTS.items()):
            tile = QToolButton()
            tile.setProperty("role", "tile")
            tile.setCheckable(True)
            tile.setText(text)
            tile.setIcon(icon(f"layout_{key}", size=24))
            tile.setIconSize(QSize(24, 24))
            tile.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            tile.setCursor(Qt.PointingHandCursor)
            tile.clicked.connect(lambda _=False, k=key: self.chosen.emit(k))
            self.group.addButton(tile)
            self.buttons[key] = tile
            grid.addWidget(tile, n // 3, n % 3)

    def set_current(self, key: str) -> None:
        self.buttons[key].setChecked(True)


class ViewMenu(QMenu):
    def __init__(self, actions: dict[str, QAction], parent: QWidget | None = None):
        super().__init__(parent)
        make_floating(self)
        self.setMinimumWidth(300)

        menu_heading(self, "페이지 배치")
        self.tiles = LayoutTiles()
        tiles_action = QWidgetAction(self)
        tiles_action.setDefaultWidget(self.tiles)
        self.addAction(tiles_action)
        self.addAction(actions["cover_separate"])

        menu_heading(self, "크기")
        for key in ("fit_page", "fit_width", "actual_size"):
            self.addAction(actions[key])

        menu_heading(self, "화면")
        self.addAction(actions["rotate_view_left"])
        self.addAction(actions["rotate_view_right"])
        note = QLabel("화면 회전은 보기만 돌아가고 파일은 바뀌지 않아요")
        note.setProperty("text_role", "menu_note")
        note_action = QWidgetAction(self)
        note_action.setDefaultWidget(note)
        note_action.setEnabled(False)
        self.addAction(note_action)
        self.addAction(actions["full_screen"])
        self.addAction(actions["toggle_thumbnails"])

    def popup_above(self, widget: QWidget, layout_key: str) -> None:
        """버튼 위쪽으로, 오른쪽 끝을 맞춰 연다."""
        self.tiles.set_current(layout_key)
        size = self.sizeHint()
        corner = widget.mapToGlobal(widget.rect().topRight())
        self.popup(QPoint(corner.x() - size.width(), corner.y() - size.height() - SIZE["space"]))
