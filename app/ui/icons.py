"""선 아이콘 (18px, 선 두께 1.75). SVG를 그려서 QIcon으로 만든다."""

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from app.ui.theme import COLOR, SIZE

# 24×24 기준 선 그림
_PATHS = {
    "open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "redo": '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "text_edit": '<path d="M4 7V5h12v2"/><path d="M10 5v14"/><path d="M8 19h4"/>'
                 '<path d="m14 20 6-6a1.4 1.4 0 0 0-2-2l-6 6v2z"/>',
    "finish": '<path d="m4 6 1.5 1.5L8 5"/><path d="M11 6h9"/><path d="m4 12 1.5 1.5L8 11"/>'
              '<path d="M11 12h9"/><path d="m4 18 1.5 1.5L8 17"/><path d="M11 18h9"/>',
    "save": '<path d="M12 4v11"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "import_pages": '<rect x="13" y="3" width="8" height="11" rx="1"/><path d="M3 12h8"/>'
                    '<path d="m8 9 3 3-3 3"/><path d="M13 17v3a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-3"/>',
    "chevron_down": '<path d="m6 9 6 6 6-6"/>',
    "fit_page": '<path d="M4 8V4h4M20 8V4h-4M4 16v4h4M20 16v4h-4"/><rect x="8" y="7" width="8" height="10" rx="1"/>',
    "layout_vertical": '<rect x="7" y="2" width="10" height="9" rx="1"/><rect x="7" y="13" width="10" height="9" rx="1"/>',
    "layout_single": '<rect x="6" y="3" width="12" height="18" rx="1"/>',
    "layout_horizontal": '<rect x="2" y="6" width="9" height="12" rx="1"/><rect x="13" y="6" width="9" height="12" rx="1"/>'
                         '<path d="M2 21h20"/>',
    "layout_two": '<rect x="2" y="5" width="9" height="14" rx="1"/><rect x="13" y="5" width="9" height="14" rx="1"/>',
    "layout_two_scroll": '<rect x="2" y="2" width="9" height="9" rx="1"/><rect x="13" y="2" width="9" height="9" rx="1"/>'
                         '<rect x="2" y="13" width="9" height="9" rx="1"/><rect x="13" y="13" width="9" height="9" rx="1"/>',
    "rotate_right": '<path d="M20 4v5h-5"/><path d="M19.5 9A8 8 0 1 0 20 14"/>',
    "rotate_left": '<path d="M4 4v5h5"/><path d="M4.5 9A8 8 0 1 1 4 14"/>',
    "trash": '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/>',
    "replace": '<path d="M4 9h13l-3-3"/><path d="M20 15H7l3 3"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "full_screen": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "panel": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
    "chevron_up": '<path d="m6 15 6-6 6 6"/>',
    "chevron_down_small": '<path d="m8 10 4 4 4-4"/>',
    "check": '<path d="m5 12 5 5 9-10"/>',
    "swap": '<path d="M7 4 3 8l4 4"/><path d="M3 8h14"/><path d="m17 12 4 4-4 4"/><path d="M21 16H7"/>',
}


def _render(name: str, color: str, size: int, opacity: float = 1.0, ratio: float = 2.0) -> QPixmap:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-opacity="{opacity}" stroke-width="{SIZE["icon_stroke"] * 24 / size:.2f}" '
        f'stroke-linecap="round" stroke-linejoin="round">{_PATHS[name]}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


def icon(name: str, color: str = COLOR["text"], size: int = SIZE["icon"],
         disabled_color: str | None = None) -> QIcon:
    """보통 상태와 사용 불가(흐리게 40%) 상태 그림을 함께 담은 아이콘.
    disabled_color를 주면 사용 불가 상태에도 그 색을 흐리지 않고 쓴다."""
    result = QIcon()
    result.addPixmap(_render(name, color, size), QIcon.Normal)
    if disabled_color:
        result.addPixmap(_render(name, disabled_color, size), QIcon.Disabled)
    else:
        result.addPixmap(_render(name, color, size, opacity=0.4), QIcon.Disabled)
    return result
