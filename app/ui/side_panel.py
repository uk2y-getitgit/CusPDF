"""옆 창: 다른 PDF를 열어 일부 쪽만 골라 넣는다 (1-6, 5-4). 원본 PDF는 바뀌지 않는다.

- 경계선을 끌어 폭을 바꾸면 썸네일이 여러 열로 늘어선다.
- 위쪽 크기 막대(30%~200%)로 썸네일 크기를 바꾼다.
- 쪽을 두 번 누르거나 돋보기를 누르면 크게 보며 넣을 쪽인지 확인할 수 있다.
"""

import time
from collections import OrderedDict

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem,
                               QSlider, QStyledItemDelegate, QVBoxLayout, QWidget)

from app.pdf.document import PageRef, PdfDocument, Source
from app.ui.icons import icon
from app.ui.theme import COLOR, SIZE
from app.ui.thumbnail_panel import MIME_SIDE_PAGES
from app.ui.widgets import button, icon_button

BASE_THUMB_W = 84      # 100%일 때 썸네일 너비
LENS = 24              # 돋보기 단추 크기


class _SideDelegate(QStyledItemDelegate):
    def __init__(self, view: "SideList"):
        super().__init__(view)
        self.view = view

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(self.view.thumb_w + 20, self.view.thumb_height(index.row()) + 40)

    def paint(self, painter: QPainter, option, index) -> None:
        view, row = self.view, index.row()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        box = view.thumb_rect(option.rect, row)
        painter.drawPixmap(box, view.thumbnail(row, box.size()))
        checked = row in view.checked
        if checked:
            painter.setPen(QPen(QColor(COLOR["primary"]), 3))
            painter.drawRect(box.adjusted(-2, -2, 1, 1))
            # 파란 체크 표시
            circle = QRect(box.right() - 22, box.top() + 4, 18, 18)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(COLOR["primary"]))
            painter.drawEllipse(circle)
            painter.drawPixmap(circle.adjusted(3, 3, -3, -3), icon("check", COLOR["white"], 12).pixmap(12, 12))
        else:
            painter.setPen(QColor(COLOR["line"]))
            painter.drawRect(box.adjusted(-1, -1, 0, 0))
        if row == view.hover_row:  # 마우스를 올린 쪽: 크게 보기 돋보기
            lens = view.lens_rect(box)
            painter.setPen(QPen(QColor(COLOR["line"]), 1))
            painter.setBrush(QColor(255, 255, 255, 235))
            painter.drawEllipse(lens)
            painter.drawPixmap(lens.adjusted(4, 4, -4, -4), icon("search", COLOR["text"], 16).pixmap(16, 16))
        font = QFont(painter.font())
        font.setPixelSize(12)
        font.setWeight(QFont.DemiBold if checked else QFont.Normal)
        painter.setFont(font)
        painter.setPen(QColor(COLOR["primary"] if checked else COLOR["text_sub"]))
        cell = option.rect
        painter.drawText(QRect(cell.left(), box.bottom() + 6, cell.width(), 18), Qt.AlignCenter, str(row + 1))
        painter.restore()


class SideList(QListWidget):
    """썸네일 격자. 누르면 고르기·풀기, Shift로 범위, 두 번 누르기·돋보기로 크게 보기, 고른 쪽을 끌어다 놓기."""
    checked_changed = Signal()
    preview_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sideList")
        self.document: PdfDocument | None = None
        self.checked: set[int] = set()
        self.thumb_w = BASE_THUMB_W
        self.hover_row = -1
        self._anchor: int | None = None
        self._press: tuple[QPoint, int] | None = None
        self._last_toggle: tuple[int, bool, float] | None = None   # (쪽, 바꾸기 전 상태, 시각)
        self._cache: OrderedDict[tuple, QPixmap] = OrderedDict()
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(False)
        self.setSelectionMode(QListWidget.NoSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.setMouseTracking(True)
        self.setItemDelegate(_SideDelegate(self))

    def set_document(self, document: PdfDocument | None) -> None:
        self.document = document
        self.checked, self._anchor = set(), None
        self._cache.clear()
        self.clear()
        for _ in range(document.page_count if document else 0):
            self.addItem(QListWidgetItem())
        self.checked_changed.emit()

    def set_scale(self, percent: int) -> None:
        self.thumb_w = max(24, round(BASE_THUMB_W * percent / 100))
        self.doItemsLayout()
        self.viewport().update()

    def thumb_height(self, row: int) -> int:
        w, h = self.document.page_size(row)
        return min(round(self.thumb_w * h / w), round(self.thumb_w * 1.5))

    def thumb_rect(self, cell: QRect, row: int) -> QRect:
        return QRect(cell.left() + (cell.width() - self.thumb_w) // 2, cell.top() + 8, self.thumb_w,
                     self.thumb_height(row))

    @staticmethod
    def lens_rect(box: QRect) -> QRect:
        return QRect(box.left() + 4, box.bottom() - LENS - 4, LENS, LENS)

    def thumbnail(self, row: int, size: QSize) -> QPixmap:
        ratio = self.devicePixelRatioF()
        key = (row, size.width(), ratio)
        if key not in self._cache:
            w_pt, _ = self.document.page_size(row)
            pixmap = QPixmap.fromImage(self.document.render(row, size.width() * ratio / w_pt))
            pixmap.setDevicePixelRatio(ratio)
            self._cache[key] = pixmap
            while len(self._cache) > 300:
                self._cache.popitem(last=False)
        return self._cache[key]

    def checked_rows(self) -> list[int]:
        return sorted(self.checked)

    def set_checked(self, row: int, on: bool) -> None:
        (self.checked.add if on else self.checked.discard)(row)
        self._anchor = row
        self.checked_changed.emit()
        self.viewport().update()

    def _row_at(self, point: QPoint) -> int | None:
        item = self.itemAt(point)
        return self.row(item) if item else None

    def _on_lens(self, point: QPoint, row: int) -> bool:
        cell = self.visualItemRect(self.item(row))
        return self.lens_rect(self.thumb_rect(cell, row)).contains(point)

    # ---------- 마우스 ----------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        row = self._row_at(point)
        if row is not None and event.button() == Qt.LeftButton and self._on_lens(point, row):
            self._press = None
            self.preview_requested.emit(row)
            return
        self._press = (point, row) if event.button() == Qt.LeftButton and row is not None else None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        row = self._row_at(event.position().toPoint())
        if row is None:
            return
        # 두 번 누르기 = 크게 보기. 바로 앞 누르기로 바뀐 고르기만 되돌리고, 그 밖에는 고르기를 건드리지 않는다
        last = self._last_toggle
        if last and last[0] == row and time.monotonic() - last[2] < 1.0:
            self.set_checked(row, last[1])
        self._last_toggle = None
        self._press = None
        self.preview_requested.emit(row)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        hover = self._row_at(point)
        hover = -1 if hover is None else hover
        if hover != self.hover_row:
            self.hover_row = hover
            self.viewport().update()
        if not self._press:
            return
        start, row = self._press
        if (point - start).manhattanLength() < QApplication.startDragDistance():
            return
        self._press = None
        if row not in self.checked:  # 고르지 않은 쪽을 끌면 그 쪽을 골라서 끈다
            self.set_checked(row, True)
        mime = QMimeData()
        mime.setData(MIME_SIDE_PAGES, QByteArray(b"side"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.thumbnail(row, QSize(self.thumb_w, self.thumb_height(row))).scaledToWidth(56))
        drag.exec(Qt.CopyAction)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if not self._press:
            return
        _, row = self._press
        self._press = None
        if event.modifiers() & Qt.ShiftModifier and self._anchor is not None:
            low, high = sorted((self._anchor, row))
            self.checked.update(range(low, high + 1))
            self.checked_changed.emit()
            self.viewport().update()
        else:
            self._last_toggle = (row, row in self.checked, time.monotonic())  # 두 번 누르기면 되돌리려고
            self.set_checked(row, row not in self.checked)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.hover_row = -1
        self.viewport().update()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.doItemsLayout()


class SidePanel(QWidget):
    closed = Signal()
    change_requested = Signal()    # 다른 PDF로 바꿔 열기
    insert_requested = Signal()    # [선택한 N쪽 넣기]
    scale_changed = Signal(int)    # 썸네일 크기 (%)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumWidth(SIZE["side_panel"] - 20)
        self.source: Source | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 12)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(0)
        self.title = QLabel("")
        self.title.setStyleSheet("font-weight: 600;")
        self.change_button = icon_button("swap", "다른 PDF로 바꿔 열기", flat=True)
        self.close_button = icon_button("close", "옆 창 닫기", flat=True)
        head.addWidget(self.title, 1)
        head.addWidget(self.change_button)
        head.addWidget(self.close_button)

        # 썸네일 크기 막대 30% ~ 200%
        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        size_label = QLabel("크기")
        size_label.setProperty("text_role", "sub")
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setObjectName("sizeSlider")
        self.size_slider.setRange(30, 200)
        self.size_slider.setSingleStep(10)
        self.size_slider.setPageStep(20)
        self.size_slider.setValue(100)
        self.size_slider.setToolTip("썸네일 크기 (30% ~ 200%)")
        self.size_value = QLabel("100%")
        self.size_value.setProperty("text_role", "sub")
        self.size_value.setFixedWidth(40)
        size_row.addWidget(size_label)
        size_row.addWidget(self.size_slider, 1)
        size_row.addWidget(self.size_value)

        hint = QLabel("눌러서 넣을 쪽을 고르세요 (Shift로 범위). 두 번 누르거나 돋보기를 누르면 크게 보여요.")
        hint.setProperty("text_role", "sub")
        hint.setWordWrap(True)
        self.list = SideList()
        self.insert_button = button("선택한 0쪽 넣기", primary=True)
        self.insert_button.setProperty("size", "panel")

        layout.addLayout(head)
        layout.addLayout(size_row)
        layout.addWidget(hint)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.insert_button)

        self.close_button.clicked.connect(self.closed)
        self.change_button.clicked.connect(self.change_requested)
        self.insert_button.clicked.connect(self.insert_requested)
        self.list.checked_changed.connect(self._update_button)
        self.size_slider.valueChanged.connect(self._on_scale)
        self._update_button()

    def set_scale(self, percent: int) -> None:
        self.size_slider.setValue(max(30, min(200, int(percent))))
        self._on_scale(self.size_slider.value())

    def _on_scale(self, value: int) -> None:
        value = round(value / 10) * 10  # 10% 단위로
        self.size_value.setText(f"{value}%")
        self.list.set_scale(value)
        self.scale_changed.emit(value)

    def set_source(self, source: Source) -> None:
        self.source = source
        preview = PdfDocument(source.name)
        preview.pages = [PageRef(source, i) for i in range(source.doc.page_count)]
        self.title.setToolTip(source.name)
        self.list.set_document(preview)
        self._elide_title()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide_title()

    def _elide_title(self) -> None:
        if self.source:
            metrics = self.title.fontMetrics()
            self.title.setText(metrics.elidedText(self.source.name, Qt.ElideMiddle, max(60, self.width() - 100)))

    def checked_pages(self) -> list[int]:
        return self.list.checked_rows()

    def _update_button(self) -> None:
        count = len(self.list.checked)
        self.insert_button.setText(f"선택한 {count}쪽 넣기")
        self.insert_button.setEnabled(count > 0)
