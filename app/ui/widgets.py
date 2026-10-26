"""여러 화면에서 같이 쓰는 작은 부품 (버튼, 구분선)."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QToolButton, QWidget,
                               QWidgetAction)

from app.ui.icons import icon
from app.ui.theme import COLOR, SIZE


def button(text: str, icon_name: str | None = None, primary: bool = False,
           large: bool = False, tooltip: str = "") -> QPushButton:
    """글자 버튼. primary=True면 파란 채움 주요 버튼 (화면에 딱 2개만)."""
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFocusPolicy(Qt.TabFocus)  # 파란 외곽선은 키보드(Tab)로 고를 때만
    if primary:
        btn.setProperty("role", "primary")
    if large:
        btn.setProperty("size", "large")
    if icon_name:
        if primary:  # 파란 바탕 위에서는 사용 불가 상태에도 흰 아이콘
            btn.setIcon(icon(icon_name, COLOR["white"], disabled_color=COLOR["white"]))
        else:
            btn.setIcon(icon(icon_name))
        btn.setIconSize(QSize(SIZE["icon"], SIZE["icon"]))
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


def icon_button(icon_name: str, tooltip: str, flat: bool = False) -> QToolButton:
    """아이콘만 있는 버튼. 설명은 마우스를 올리면 보인다."""
    btn = QToolButton()
    btn.setProperty("role", "flat" if flat else "icon")
    btn.setIcon(icon(icon_name))
    btn.setIconSize(QSize(SIZE["icon"], SIZE["icon"]))
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFocusPolicy(Qt.TabFocus)
    return btn


def floating_menu(parent: QWidget | None = None, title: str = "") -> QMenu:
    """모서리가 둥근 떠 있는 메뉴 (모서리 12)."""
    return make_floating(QMenu(title, parent))


def make_floating(menu: QMenu) -> QMenu:
    """메뉴 바깥 네모 그림자를 없애 둥근 모서리가 보이게 한다."""
    menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WA_TranslucentBackground)
    return menu


def menu_heading(menu: QMenu, text: str) -> None:
    """메뉴 안의 묶음 제목 (파일, 페이지, 보기 …). 첫 묶음이 아니면 위에 구분선."""
    if menu.actions():
        menu.addSeparator()
    label = QLabel(text)
    label.setProperty("text_role", "menu_heading")
    action = QWidgetAction(menu)
    action.setDefaultWidget(label)
    action.setEnabled(False)
    menu.addAction(action)


class _MenuRow(QWidget):
    """메뉴 안에 직접 그리는 한 줄 (빨간 '삭제'처럼 색이 다른 항목용)."""
    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.rect().contains(event.position().toPoint()):
            self.clicked.emit()


def add_danger_item(menu: QMenu, text: str, shortcut: str, on_click) -> None:
    """빨간 글자 메뉴 항목 (예: 삭제)."""
    row = _MenuRow()
    row.setObjectName("dangerMenuItem")
    row.setAttribute(Qt.WA_StyledBackground)
    row.setCursor(Qt.PointingHandCursor)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(16, 8, 16, 8)
    label = QLabel(text)
    label.setObjectName("dangerText")
    key = QLabel(shortcut)
    key.setProperty("text_role", "sub")
    layout.addWidget(label)
    layout.addStretch(1)
    layout.addSpacing(24)
    layout.addWidget(key)
    action = QWidgetAction(menu)
    action.setDefaultWidget(row)
    menu.addAction(action)
    row.clicked.connect(lambda: (menu.close(), on_click()))


def vline() -> QFrame:
    """세로 구분선."""
    line = QFrame()
    line.setProperty("line", "vertical")
    line.setFixedHeight(20)
    return line
