"""썸네일 패널(왼쪽): [＋ 파일 넣기], [PDF에서 쪽 가져오기], "페이지 N", 썸네일 목록 (5-3, 5-4, 5-5).

- 썸네일 아래에 쪽 번호와 파일 종류 꼬리표
- 누르면 그 쪽으로 이동, Ctrl·Shift로 여러 쪽 선택
- 끌어다 놓아 순서 바꾸기, 파일·옆 창의 쪽을 썸네일 사이에 놓으면 파란 선 위치에 들어감
"""

from collections import OrderedDict

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QLabel, QListView, QListWidget, QListWidgetItem,
                               QStyledItemDelegate, QVBoxLayout, QWidget)

from app.pdf.document import PdfDocument
from app.ui.drop_reader import has_droppable, is_ezpdf, read_drop, remember_foreground
from app.ui.theme import COLOR, FILE_TAG_COLOR, SIZE
from app.ui.widgets import add_danger_item, button, floating_menu

MIME_PAGES = "application/x-cuspdf-pages"        # 이 목록 안에서 끄는 쪽
MIME_SIDE_PAGES = "application/x-cuspdf-side"    # 옆 창에서 끄는 쪽
THUMB_WIDTH = {"small": 72, "medium": 96, "large": 128}
LABEL_HEIGHT = 28
PAD = SIZE["space"]


class ThumbnailDelegate(QStyledItemDelegate):
    """썸네일 하나를 그린다: 쪽 그림 + 쪽 번호 + 파일 종류 꼬리표."""

    def __init__(self, view: "ThumbnailList"):
        super().__init__(view)
        self.view = view

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(self.view.cell_width(), self.view.thumb_box(index.row()).height() + LABEL_HEIGHT + 2 * PAD)

    def paint(self, painter: QPainter, option, index) -> None:
        view, row = self.view, index.row()
        doc = view.document
        if not doc or row >= doc.page_count:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        cell = option.rect
        if row == view.current_row:  # 지금 뷰어에 보이는 쪽
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(COLOR["background"]))
            painter.drawRoundedRect(cell.adjusted(4, 2, -4, -2), SIZE["radius"], SIZE["radius"])
        painter.setBrush(Qt.NoBrush)  # 아래 테두리가 썸네일을 덮지 않도록

        box = view.thumb_box(row)
        box.moveTopLeft(QPoint(cell.left() + (cell.width() - box.width()) // 2, cell.top() + PAD))
        painter.drawPixmap(box, view.thumbnail(row, box.size()))

        selected = view.item(row).isSelected()
        if row in view.fresh_rows:  # 방금 들어온 쪽
            painter.setPen(QPen(QColor(COLOR["highlight"]), 4))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(box.adjusted(-3, -3, 2, 2))
        elif selected:
            painter.setPen(QPen(QColor(COLOR["primary"]), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(box.adjusted(-2, -2, 1, 1))
        else:
            painter.setPen(QColor(COLOR["line"]))
            painter.drawRect(box.adjusted(-1, -1, 0, 0))

        # 쪽 번호 + 파일 종류 꼬리표
        number = str(row + 1)
        kind = doc.kind(row)
        font = QFont(painter.font())
        font.setPixelSize(12)
        font.setWeight(QFont.DemiBold if selected else QFont.Normal)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        tag_font = QFont(font)
        tag_font.setPixelSize(11)
        tag_font.setWeight(QFont.DemiBold)
        tag_w = (QFontMetrics(tag_font).horizontalAdvance(kind) + 12) if kind in FILE_TAG_COLOR else 0
        num_w = metrics.horizontalAdvance(number)
        total = num_w + (6 + tag_w if tag_w else 0)
        x = cell.left() + (cell.width() - total) // 2
        y = box.bottom() + 6
        painter.setPen(QColor(COLOR["primary"] if selected else COLOR["text_sub"]))
        painter.drawText(QRect(x, y, num_w, 20), Qt.AlignVCenter, number)
        if tag_w:
            tag = QRect(x + num_w + 6, y + 2, tag_w, 16)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(FILE_TAG_COLOR[kind]))
            painter.drawRoundedRect(tag, 4, 4)
            painter.setFont(tag_font)
            painter.setPen(QColor(COLOR["white"]))
            painter.drawText(tag, Qt.AlignCenter, kind)
        painter.restore()


class ThumbnailList(QListWidget):
    page_clicked = Signal(int)                       # 썸네일을 누름 → 그 쪽으로 이동
    pages_moved = Signal(list, int)                  # 끌어서 순서 바꾸기: 쪽들, 놓을 위치
    files_dropped = Signal(list, int)                # 파일을 끌어다 놓음: 경로들, 놓을 위치
    side_pages_dropped = Signal(int)                 # 옆 창의 쪽을 끌어다 놓음: 놓을 위치
    external_drag = Signal(bool)                     # 파일·옆 창 쪽을 끌고 들어오는 중인지
    unreadable_dropped = Signal()                    # 읽을 수 없는 내용을 놓음
    ezpdf_dropped = Signal(object, int)              # ezPDF에서 끈 쪽: (출처 정보, 놓을 위치)
    menu_requested = Signal(QPoint)                  # 우클릭 메뉴

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.document: PdfDocument | None = None
        self.size_name = "medium"
        self.current_row = -1
        self.fresh_rows: set[int] = set()
        self.drop_row: int | None = None
        self._cache: OrderedDict[tuple, QPixmap] = OrderedDict()
        self._fresh_timer = QTimer(self, singleShot=True, interval=1600, timeout=self._clear_fresh)

        self.columns = 1
        self.setObjectName("thumbnailList")
        self.setItemDelegate(ThumbnailDelegate(self))
        # 패널을 넓히면 2열·3열로 늘어서도록 격자 배치
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setSpacing(0)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setUniformItemSizes(False)
        # 주의: setMovement(Static)은 끌기와 '안쪽 화면의 놓기 받기'를 몰래 꺼 버린다.
        # 그래서 그 뒤에 다시 켠다 (안쪽 화면 viewport까지 켜야 썸네일 사이에 놓을 수 있다)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(False)  # 파란 선은 직접 그린다
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setFocusPolicy(Qt.StrongFocus)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.itemClicked.connect(lambda item: self.page_clicked.emit(self.row(item)))

    # ---------- 내용 ----------
    def set_document(self, document: PdfDocument | None, selected: list[int] | None = None) -> None:
        self.document = document
        self.reload(selected or [])

    def reload(self, selected: list[int]) -> None:
        """쪽 목록이 바뀌면 다시 채운다. 썸네일 그림은 기억해 둔 것을 다시 쓴다."""
        self.blockSignals(True)
        self.clear()
        count = self.document.page_count if self.document else 0
        for _ in range(count):
            self.addItem(QListWidgetItem())
        for row in selected:
            if 0 <= row < count:
                self.item(row).setSelected(True)
        self.blockSignals(False)
        self.itemSelectionChanged.emit()
        self.viewport().update()

    def set_thumb_size(self, name: str) -> None:
        self.size_name = name
        self.reload(self.selected_rows())
        self.doItemsLayout()

    def cell_width(self) -> int:
        """칸 너비: 패널 너비에 들어가는 만큼 열을 만들고 똑같이 나눈다."""
        width = max(1, self.viewport().width())
        least = THUMB_WIDTH[self.size_name] + 2 * PAD + 16
        self.columns = max(1, width // least)
        return width // self.columns - 2  # 딱 맞으면 줄이 넘어가므로 약간 여유

    def thumb_box(self, row: int) -> QRect:
        width = THUMB_WIDTH[self.size_name]
        w_pt, h_pt = self.document.page_size(row)
        height = round(width * h_pt / w_pt)
        if height > width * 1.5:  # 아주 긴 쪽은 높이를 제한
            height = round(width * 1.5)
            width = round(height * w_pt / h_pt)
        return QRect(0, 0, width, height)

    def thumbnail(self, row: int, size: QSize) -> QPixmap:
        ratio = self.devicePixelRatioF()
        key = (self.document.page_key(row), size.width(), ratio)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        w_pt, _ = self.document.page_size(row)
        pixmap = QPixmap.fromImage(self.document.render(row, size.width() * ratio / w_pt))
        pixmap.setDevicePixelRatio(ratio)
        self._cache[key] = pixmap
        while len(self._cache) > 400:
            self._cache.popitem(last=False)
        return pixmap

    def selected_rows(self) -> list[int]:
        return sorted(self.row(item) for item in self.selectedItems())

    def select_rows(self, rows: list[int]) -> None:
        self.blockSignals(True)
        self.clearSelection()
        for row in rows:
            if 0 <= row < self.count():
                self.item(row).setSelected(True)
        self.blockSignals(False)
        self.itemSelectionChanged.emit()
        self.viewport().update()

    def set_current(self, row: int) -> None:
        if row == self.current_row:
            return
        old, self.current_row = self.current_row, row
        for r in (old, row):
            if 0 <= r < self.count():
                self.update(self.indexFromItem(self.item(r)))
        if 0 <= row < self.count():
            self.scrollToItem(self.item(row), QAbstractItemView.EnsureVisible)

    def flash(self, rows: list[int]) -> None:
        """방금 들어온 쪽을 잠깐 노란 테두리로 표시한다."""
        self.fresh_rows = set(rows)
        if rows:
            self.scrollToItem(self.item(rows[0]), QAbstractItemView.EnsureVisible)
        self.viewport().update()
        self._fresh_timer.start()

    def _clear_fresh(self) -> None:
        self.fresh_rows = set()
        self.viewport().update()

    # ---------- 끌어다 놓기 ----------
    def startDrag(self, actions) -> None:  # noqa: N802
        rows = self.selected_rows()
        if not rows:
            return
        mime = QMimeData()
        mime.setData(MIME_PAGES, QByteArray(",".join(map(str, rows)).encode()))
        drag = QDrag(self)
        drag.setMimeData(mime)
        box = self.thumb_box(rows[0])
        box.setSize(box.size() / 2)
        pixmap = self.thumbnail(rows[0], box.size())
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(box.width() // 2, box.height() // 2))
        drag.exec(Qt.MoveAction)
        self._end_drop()

    def _accepts(self, mime: QMimeData) -> bool:
        return mime.hasFormat(MIME_PAGES) or mime.hasFormat(MIME_SIDE_PAGES) or has_droppable(mime)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if not self._accepts(event.mimeData()):
            event.ignore()
            return
        event.acceptProposedAction()
        if not event.mimeData().hasFormat(MIME_PAGES):
            remember_foreground()  # 끌기를 시작한 프로그램 창 (ezPDF 등)
            self.external_drag.emit(True)
        self._update_drop(event.position().toPoint())

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if not self._accepts(event.mimeData()):
            event.ignore()
            return
        event.acceptProposedAction()
        self._update_drop(event.position().toPoint())
        # 위·아래 끝 근처면 자동으로 스크롤
        y, h = event.position().y(), self.viewport().height()
        bar = self.verticalScrollBar()
        if y < 40:
            bar.setValue(bar.value() - 12)
        elif y > h - 40:
            bar.setValue(bar.value() + 12)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._end_drop()

    def dropEvent(self, event) -> None:  # noqa: N802
        mime = event.mimeData()
        row = self.drop_row if self.drop_row is not None else self.count()
        self._end_drop()
        event.setDropAction(Qt.CopyAction)
        event.accept()  # 목록이 스스로 항목을 옮기지 않도록 직접 처리
        if mime.hasFormat(MIME_PAGES):
            rows = [int(x) for x in bytes(mime.data(MIME_PAGES)).decode().split(",") if x]
            self.pages_moved.emit(rows, row)
        elif mime.hasFormat(MIME_SIDE_PAGES):
            self.side_pages_dropped.emit(row)
        else:  # 탐색기 파일 또는 다른 PDF 리더기에서 끈 쪽
            content = read_drop(mime)
            if content.ezpdf is not None or is_ezpdf(content.formats):
                self.ezpdf_dropped.emit(content.ezpdf, row)
            elif content.paths:
                self.files_dropped.emit(content.paths, row)
            else:
                self.unreadable_dropped.emit()

    def _update_drop(self, point: QPoint) -> None:
        """마우스 위치로 들어갈 자리(그 쪽 앞)를 정한다."""
        row = self.count()
        for r in range(self.count()):
            rect = self.visualItemRect(self.item(r))
            if self.columns == 1:
                before = point.y() < rect.center().y()
            else:  # 여러 열: 그 칸의 위쪽 줄이거나, 같은 줄에서 칸 가운데보다 왼쪽이면 그 칸 앞
                before = point.y() < rect.top() or (point.y() <= rect.bottom() and point.x() < rect.center().x())
            if before:
                row = r
                break
        if row != self.drop_row:
            self.drop_row = row
            self.viewport().update()

    def _end_drop(self) -> None:
        self.drop_row = None
        self.external_drag.emit(False)
        self.viewport().update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        if self.count() == 0:
            painter.setPen(QColor(COLOR["text_sub"]))
            font = QFont(painter.font())
            font.setPixelSize(12)
            painter.setFont(font)
            painter.drawText(self.viewport().rect().adjusted(8, 16, -8, 0), Qt.AlignHCenter | Qt.AlignTop,
                             "아직 쪽이 없어요.\n파일을 이곳에 끌어다 놓아도 돼요.")
        if self.drop_row is None:
            return
        # 들어갈 자리: 파란 선 + 양 끝 동그라미 (한 열이면 가로선, 여러 열이면 칸 사이 세로선)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(COLOR["primary"]))
        if self.count() == 0:
            self._paint_line(painter, QPoint(14, 8), QPoint(self.viewport().width() - 14, 8))
        elif self.columns == 1:
            if self.drop_row < self.count():
                y = self.visualItemRect(self.item(self.drop_row)).top()
            else:
                y = self.visualItemRect(self.item(self.count() - 1)).bottom()
            self._paint_line(painter, QPoint(14, y), QPoint(self.viewport().width() - 14, y))
        else:
            if self.drop_row < self.count():
                rect = self.visualItemRect(self.item(self.drop_row))
                x = rect.left() + 2
            else:
                rect = self.visualItemRect(self.item(self.count() - 1))
                x = rect.right() - 1
            self._paint_line(painter, QPoint(x, rect.top() + 8), QPoint(x, rect.bottom() - 8))

    @staticmethod
    def _paint_line(painter: QPainter, start: QPoint, end: QPoint) -> None:
        if start.y() == end.y():
            painter.drawRoundedRect(QRect(start.x(), start.y() - 2, end.x() - start.x(), 4), 2, 2)
        else:
            painter.drawRoundedRect(QRect(start.x() - 2, start.y(), 4, end.y() - start.y()), 2, 2)
        painter.drawEllipse(start, 6, 6)
        painter.drawEllipse(end, 6, 6)

    def _on_context_menu(self, point: QPoint) -> None:
        item = self.itemAt(point)
        if item is None:
            return
        if not item.isSelected():  # 선택하지 않은 쪽에서 누르면 그 쪽만 선택
            self.select_rows([self.row(item)])
        self.menu_requested.emit(self.viewport().mapToGlobal(point))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.doItemsLayout()


class ThumbnailPanel(QWidget):
    action_requested = Signal(str)   # 우클릭 메뉴에서 고른 일

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("thumbnailPanel")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setMinimumWidth(SIZE["thumbnail_panel"] - 32)   # 경계선을 끌어 넓히면 썸네일이 여러 열로
        s = SIZE["space"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2 * s, 2 * s, 2 * s, 0)
        layout.setSpacing(s)

        self.add_files_button = button("파일 넣기", "plus", primary=True, large=True,
                                       tooltip="hwp·엑셀·워드·사진·PDF를 PDF로 바꿔 넣어요")
        self.import_pages_button = button("PDF에서 쪽 가져오기", "import_pages",
                                          tooltip="다른 PDF에서 필요한 쪽만 골라 넣어요")
        self.page_count = QLabel("페이지 0")
        self.page_count.setProperty("text_role", "section")
        self.drop_hint = QLabel("여기에 놓으면 파란 선 위치에 들어가요")
        self.drop_hint.setProperty("text_role", "sub")
        self.drop_hint.setWordWrap(True)
        self.drop_hint.hide()
        self.list = ThumbnailList()
        self.list.external_drag.connect(self._show_dropping)

        layout.addWidget(self.add_files_button)
        layout.addWidget(self.import_pages_button)
        layout.addSpacing(s)
        layout.addWidget(self.page_count)
        layout.addWidget(self.drop_hint)
        layout.addWidget(self.list, 1)

        self.list.menu_requested.connect(self._show_menu)

    def set_page_count(self, count: int) -> None:
        self.page_count.setText(f"페이지 {count}")

    def _show_dropping(self, on: bool) -> None:
        """첨부를 끌고 들어오는 동안 패널 바탕을 연한 파랑으로 (5-4)."""
        self.setProperty("dropping", on)
        self.list.setProperty("dropping", on)
        for w in (self, self.list):
            w.style().unpolish(w)
            w.style().polish(w)
        self.drop_hint.setVisible(on)

    def _show_menu(self, global_pos: QPoint) -> None:
        """썸네일 우클릭 메뉴 (5-5)."""
        menu = floating_menu(self)
        for key, text in (("insert_after", "뒤에 파일 넣기"), ("insert_before", "앞에 파일 넣기"),
                          ("add_blank", "빈 페이지 추가")):
            menu.addAction(text, lambda k=key: self.action_requested.emit(k))
        menu.addSeparator()
        menu.addAction("회전", lambda: self.action_requested.emit("rotate"))
        menu.addAction("페이지 교체", lambda: self.action_requested.emit("replace"))
        menu.addAction("용지 크기 맞추기", lambda: self.action_requested.emit("paper"))
        menu.addSeparator()
        add_danger_item(menu, "삭제", "Delete", lambda: self.action_requested.emit("delete"))
        menu.exec(global_pos)
