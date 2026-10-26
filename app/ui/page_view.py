"""PDF 쪽을 보여주는 화면. 화면에 보이는 쪽만 그린다.

- 보기 방식: 한 쪽씩 / 세로 스크롤 / 가로 스크롤 / 두 쪽씩 / 두 쪽 스크롤 (+ 두 쪽 보기에서 표지 따로)
- 확대·축소, 쪽 맞춤, 너비 맞춤, 실제 크기
- 화면 회전 (보기만 돌아가고 파일은 바뀌지 않음)
- 선택한 쪽 파란 테두리, 검색 결과 노란 표시
"""

from collections import OrderedDict

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QScrollArea, QWidget

from app.pdf.document import PdfDocument
from app.ui.theme import COLOR, SIZE

PT_TO_PX = 96 / 72   # 100% = 실제 크기 (화면 96dpi 기준)
CACHE_LIMIT = 24     # 그려 둔 쪽 그림을 몇 장까지 기억할지
GAP = 2 * SIZE["space"]      # 쪽 사이 간격
MARGIN = 3 * SIZE["space"]   # 바깥 여백

# 확대·축소 단계 (배율). [+]/[−]와 Ctrl+마우스 휠이 이 단계를 따라 움직인다.
ZOOM_STEPS = [0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0]
ZOOM_MIN, ZOOM_MAX = ZOOM_STEPS[0], ZOOM_STEPS[-1]

# 맞춤 방식: 창 크기가 바뀌면 이 방식대로 다시 맞춘다
FIT_NONE, FIT_PAGE, FIT_WIDTH = "none", "page", "width"

# 페이지 배치
LAYOUTS = {
    "single": "한 쪽씩",
    "vertical": "세로 스크롤",
    "horizontal": "가로 스크롤",
    "two": "두 쪽씩",
    "two_scroll": "두 쪽 스크롤",
}


def make_groups(count: int, layout: str, cover_separate: bool) -> list[list[int]]:
    """나란히 놓을 쪽 묶음. 두 쪽 보기면 [0], [1, 2], [3, 4] … (표지 따로)"""
    if layout in ("two", "two_scroll"):
        start = 1 if cover_separate else 0
        groups = [[0]] if cover_separate and count else []
        groups += [list(range(i, min(i + 2, count))) for i in range(start, count, 2)]
        return groups
    return [[i] for i in range(count)]


class PageCanvas(QWidget):
    """쪽들이 놓이는 판. QScrollArea 안에 들어간다."""
    page_clicked = Signal(int, object)  # 쪽 번호, 누른 키(Ctrl·Shift)
    area_selected = Signal(int, QRectF)  # 글자 수정 모드: 감싼 영역 (쪽 번호, 보이는 방향 pt)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.document: PdfDocument | None = None
        self.zoom = 1.0
        self.layout_mode = "vertical"
        self.cover_separate = True
        self.view_rotation = 0
        self.groups: list[list[int]] = []
        self.current_group = 0           # 한 쪽씩·두 쪽씩 보기에서 지금 보이는 묶음
        self.page_rects: dict[int, QRect] = {}
        self.group_rects: list[tuple[list[int], QRect]] = []
        self.content_size = QSize(0, 0)
        self.selected: set[int] = set()
        self.highlights: list[tuple[int, QRectF]] = []
        self.current_highlight = -1
        # 글자 수정 모드
        self.edit_mode = False
        self.show_marks = True
        self.edit_target: tuple[int, QRectF] | None = None   # 고른 글자 (쪽, pt)
        self._band: tuple[int, QPoint, QPoint] | None = None  # 끌고 있는 영역 (쪽, 시작, 끝)
        # 쪽번호 미리보기 (저장할 때 찍힐 글자)
        self.page_labels: list[str | None] = []
        self.numbers = None
        self._items: list[tuple[list[int], list[QSize], QSize]] = []
        self._cache: OrderedDict[tuple, QPixmap] = OrderedDict()

    @property
    def paged(self) -> bool:
        return self.layout_mode in ("single", "two")

    @property
    def horizontal(self) -> bool:
        return self.layout_mode == "horizontal"

    def group_of(self, index: int) -> int:
        for g, pages in enumerate(self.groups):
            if index in pages:
                return g
        return 0

    def relayout(self) -> None:
        """쪽 크기·배율·보기 방식으로 배치를 계산한다 (실제 좌표는 place_pages에서)."""
        self._items = []
        self.page_rects, self.group_rects = {}, []
        if not self.document or not self.document.page_count:
            self.groups = []
            self.content_size = QSize(0, 0)
            return
        self.groups = make_groups(self.document.page_count, self.layout_mode, self.cover_separate)
        self.current_group = max(0, min(self.current_group, len(self.groups) - 1))
        shown = [self.groups[self.current_group]] if self.paged else self.groups
        main = MARGIN
        cross = 0
        for pages in shown:
            sizes = []
            for i in pages:
                w_pt, h_pt = self.document.page_size(i, self.view_rotation)
                sizes.append(QSize(round(w_pt * PT_TO_PX * self.zoom), round(h_pt * PT_TO_PX * self.zoom)))
            size = QSize(sum(s.width() for s in sizes) + GAP * (len(sizes) - 1),
                         max(s.height() for s in sizes))
            self._items.append((pages, sizes, size))
            if self.horizontal:
                main += size.width() + GAP
                cross = max(cross, size.height())
            else:
                main += size.height() + GAP
                cross = max(cross, size.width())
        main += MARGIN - GAP
        cross += 2 * MARGIN
        self.content_size = QSize(main, cross) if self.horizontal else QSize(cross, main)

    def place_pages(self) -> None:
        """묶음을 판 가운데에 놓고, 묶음 안에서 쪽을 나란히 놓는다."""
        self.page_rects, self.group_rects = {}, []
        offset = MARGIN
        for pages, sizes, size in self._items:
            if self.horizontal:
                group = QRect(offset, (self.height() - size.height()) // 2, size.width(), size.height())
                offset += size.width() + GAP
            else:
                group = QRect((self.width() - size.width()) // 2, offset, size.width(), size.height())
                offset += size.height() + GAP
            self.group_rects.append((pages, group))
            x = group.left()
            for i, s in zip(pages, sizes):
                self.page_rects[i] = QRect(x, group.top() + (size.height() - s.height()) // 2, s.width(), s.height())
                x += s.width() + GAP

    # ---------- 그리기 ----------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(COLOR["viewer"]))
        if not self.document:
            return
        visible = event.rect()
        for index, rect in self.page_rects.items():
            if not rect.intersects(visible):
                continue
            painter.drawPixmap(rect, self._page_pixmap(index, rect.size()))
            if index in self.selected:
                painter.setPen(QPen(QColor(COLOR["primary"]), 3))
                painter.drawRect(rect.adjusted(-2, -2, 1, 1))
            else:
                painter.setPen(QColor(COLOR["line"]))
                painter.drawRect(rect.adjusted(-1, -1, 0, 0))
        self._paint_highlights(painter)
        self._paint_edit_layer(painter, visible)

    def _pt_rect(self, index: int, box: QRectF) -> QRectF:
        """쪽 안의 pt 영역 → 판 위의 화면 좌표."""
        rect = self.page_rects[index]
        scale = PT_TO_PX * self.zoom
        return QRectF(rect.left() + box.x() * scale, rect.top() + box.y() * scale,
                      box.width() * scale, box.height() * scale)

    def _paint_edit_layer(self, painter: QPainter, visible: QRect) -> None:
        scale = PT_TO_PX * self.zoom
        # 쪽번호 미리보기
        if self.numbers and self.view_rotation == 0:
            font = QFont("HCR Batang")
            font.setPixelSize(max(6, round(10 * scale)))
            painter.setFont(font)
            painter.setPen(QColor("#000000"))
            metrics = painter.fontMetrics()
            for index, rect in self.page_rects.items():
                label = self.page_labels[index] if index < len(self.page_labels) else None
                if not label or not rect.intersects(visible):
                    continue
                w_pt, h_pt = self.document.page_size(index)
                text_w = metrics.horizontalAdvance(label) / scale
                x, y = self.numbers.anchor(w_pt, h_pt, text_w, 10)
                painter.drawText(QPointF(rect.left() + x * scale, rect.top() + y * scale), label)
        # 고친 곳 (주황 점선, 화면에만)
        if self.show_marks:
            painter.setPen(QPen(QColor("#E07B00"), 1.5, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            for index in self.page_rects:
                for box in self.document.edit_marks(index, self.view_rotation):
                    painter.drawRect(self._pt_rect(index, box).adjusted(-2, -2, 2, 2))
        # 고른 글자
        if self.edit_target and self.edit_target[0] in self.page_rects:
            painter.setPen(QPen(QColor(COLOR["primary"]), 2))
            painter.drawRect(self._pt_rect(*self.edit_target).adjusted(-2, -2, 2, 2))
        # 끌고 있는 영역
        if self._band:
            _, start, end = self._band
            painter.setPen(QPen(QColor(COLOR["primary"]), 1, Qt.DashLine))
            fill = QColor(COLOR["primary"])
            fill.setAlpha(30)
            painter.setBrush(fill)
            painter.drawRect(QRect(start, end).normalized())

    def _paint_highlights(self, painter: QPainter) -> None:
        mark = QColor(COLOR["highlight"])
        for n, (index, box) in enumerate(self.highlights):
            rect = self.page_rects.get(index)
            if rect is None:
                continue
            scale = PT_TO_PX * self.zoom
            area = QRectF(rect.left() + box.x() * scale, rect.top() + box.y() * scale,
                          box.width() * scale, box.height() * scale)
            mark.setAlpha(200 if n == self.current_highlight else 90)
            painter.fillRect(area, mark)
            if n == self.current_highlight:
                painter.setPen(QPen(QColor(COLOR["text"]), 1.5))
                painter.drawRect(area.adjusted(-1, -1, 1, 1))

    def highlight_rect(self, n: int) -> QRect | None:
        """n번째 검색 결과의 화면 위치."""
        if not (0 <= n < len(self.highlights)):
            return None
        index, box = self.highlights[n]
        rect = self.page_rects.get(index)
        if rect is None:
            return None
        scale = PT_TO_PX * self.zoom
        return QRect(round(rect.left() + box.x() * scale), round(rect.top() + box.y() * scale),
                     round(box.width() * scale), round(box.height() * scale))

    def _page_pixmap(self, index: int, size: QSize) -> QPixmap:
        ratio = self.devicePixelRatioF()
        key = (self.document.page_key(index, self.view_rotation), self.zoom, ratio)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        w_pt, _ = self.document.page_size(index, self.view_rotation)
        pixmap = QPixmap.fromImage(self.document.render(index, size.width() * ratio / w_pt, self.view_rotation))
        pixmap.setDevicePixelRatio(ratio)
        self._cache[key] = pixmap
        while len(self._cache) > CACHE_LIMIT:
            self._cache.popitem(last=False)
        return pixmap

    def page_at(self, point: QPoint) -> int | None:
        for index, rect in self.page_rects.items():
            if rect.contains(point):
                return index
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        index = self.page_at(point)
        if index is None or event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        if self.edit_mode:  # 글자 수정: 고칠 글자를 드래그로 감싼다
            self._band = (index, point, point)
            self.update()
            return
        self.page_clicked.emit(index, event.modifiers())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._band:
            index, start, _ = self._band
            end = event.position().toPoint()
            rect = self.page_rects[index]  # 그 쪽 밖으로는 나가지 않게
            end = QPoint(max(rect.left(), min(rect.right(), end.x())), max(rect.top(), min(rect.bottom(), end.y())))
            self._band = (index, start, end)
            self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if not self._band:
            super().mouseReleaseEvent(event)
            return
        index, start, end = self._band
        self._band = None
        band = QRect(start, end).normalized()
        if band.width() < 4 and band.height() < 4:  # 그냥 누르기: 그 자리 글자 한 줄 주변을 작게 감싼다
            band = QRect(start.x() - 3, start.y() - 3, 6, 6)
        rect = self.page_rects[index]
        scale = PT_TO_PX * self.zoom
        area = QRectF((band.left() - rect.left()) / scale, (band.top() - rect.top()) / scale,
                      band.width() / scale, band.height() / scale)
        self.update()
        self.area_selected.emit(index, area)


class PageView(QScrollArea):
    zoom_changed = Signal(float)         # 배율이 바뀌면 보기 막대의 % 글자를 갱신한다
    current_page_changed = Signal(int)   # 화면 가운데 쪽이 바뀌면 썸네일 표시를 갱신한다

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pageView")
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(False)  # 판 크기는 직접 계산한다
        self.canvas = PageCanvas()
        self.setWidget(self.canvas)
        self.fit_mode = FIT_NONE
        self._last_current = -1
        self.verticalScrollBar().valueChanged.connect(self._emit_current)
        self.horizontalScrollBar().valueChanged.connect(self._emit_current)

    # ---------- 문서 ----------
    def set_document(self, document: PdfDocument | None) -> None:
        self.canvas.document = document
        self.canvas._cache.clear()
        self.canvas.current_group = 0
        self.canvas.selected = set()
        self.canvas.highlights = []
        self._relayout()
        self.verticalScrollBar().setValue(0)
        self.horizontalScrollBar().setValue(0)
        self._emit_current(force=True)

    def refresh(self) -> None:
        """쪽을 고친 뒤(회전·삭제·넣기 등) 다시 그린다. 보던 위치는 최대한 그대로."""
        v, h = self.verticalScrollBar().value(), self.horizontalScrollBar().value()
        if self.fit_mode == FIT_PAGE:
            self.fit_page()
        elif self.fit_mode == FIT_WIDTH:
            self.fit_width()
        else:
            self._relayout()
        self.verticalScrollBar().setValue(v)
        self.horizontalScrollBar().setValue(h)
        self.canvas.update()
        self._emit_current(force=True)

    @property
    def zoom(self) -> float:
        return self.canvas.zoom

    def current_page(self) -> int:
        """화면 가운데에 보이는 쪽 번호 (0부터)."""
        c = self.canvas
        if not c.group_rects:
            return 0
        if c.paged:
            return c.group_rects[0][0][0]
        if c.horizontal:
            center = self.horizontalScrollBar().value() + self.viewport().width() // 2
            for pages, rect in c.group_rects:
                if center <= rect.right() + GAP // 2:
                    return pages[0]
        else:
            center = self.verticalScrollBar().value() + self.viewport().height() // 2
            for pages, rect in c.group_rects:
                if center <= rect.bottom() + GAP // 2:
                    return pages[0]
        return c.group_rects[-1][0][0]

    def go_to_page(self, index: int) -> None:
        c = self.canvas
        if not c.document or not (0 <= index < c.document.page_count):
            return
        if c.paged:
            group = c.group_of(index)
            if group != c.current_group:
                c.current_group = group
                self._relayout()
            self.verticalScrollBar().setValue(0)
            self.horizontalScrollBar().setValue(0)
            c.update()
            self._emit_current(force=True)
            return
        rect = c.page_rects.get(index)
        if rect is None:
            return
        if c.horizontal:
            self.horizontalScrollBar().setValue(rect.left() - MARGIN)
        else:
            self.verticalScrollBar().setValue(rect.top() - MARGIN)

    def show_rect(self, rect: QRect) -> None:
        """rect(판 좌표)가 화면 안에 들어오도록 스크롤한다."""
        margin = 4 * SIZE["space"]
        self.ensureVisible(rect.center().x(), rect.center().y(),
                           rect.width() // 2 + margin, rect.height() // 2 + margin)

    def page_step(self, step: int) -> None:
        """다음(+1)/이전(-1) 쪽 또는 묶음으로."""
        c = self.canvas
        if not c.groups:
            return
        group = max(0, min(len(c.groups) - 1, c.group_of(self.current_page()) + step))
        self.go_to_page(c.groups[group][0])

    # ---------- 보기 방식 ----------
    def set_layout(self, layout: str, cover_separate: bool | None = None) -> None:
        current = self.current_page()
        self.canvas.layout_mode = layout
        if cover_separate is not None:
            self.canvas.cover_separate = cover_separate
        self.canvas.current_group = 0
        self.canvas.relayout()
        self.canvas.current_group = self.canvas.group_of(current)
        self.refresh_fit()
        self.go_to_page(current)

    def rotate_view(self, angle: int) -> None:
        current = self.current_page()
        self.canvas.view_rotation = (self.canvas.view_rotation + angle) % 360
        self.canvas.highlights = []
        self.refresh_fit()
        self.go_to_page(current)

    def refresh_fit(self) -> None:
        if self.fit_mode == FIT_PAGE:
            self.fit_page()
        elif self.fit_mode == FIT_WIDTH:
            self.fit_width()
        else:
            self._relayout()
            self.canvas.update()

    # ---------- 확대·축소 ----------
    def zoom_in(self, anchor: QPoint | None = None) -> None:
        bigger = [z for z in ZOOM_STEPS if z > self.zoom + 0.001]
        if bigger:
            self.set_zoom(bigger[0], anchor)

    def zoom_out(self, anchor: QPoint | None = None) -> None:
        smaller = [z for z in ZOOM_STEPS if z < self.zoom - 0.001]
        if smaller:
            self.set_zoom(smaller[-1], anchor)

    def actual_size(self) -> None:
        self.set_zoom(1.0)

    def _group_size_pt(self, pages: list[int]) -> tuple[float, float]:
        sizes = [self.canvas.document.page_size(i, self.canvas.view_rotation) for i in pages]
        gap_pt = GAP / PT_TO_PX
        return sum(w for w, _ in sizes) + gap_pt * (len(sizes) - 1), max(h for _, h in sizes)

    def fit_page(self) -> None:
        """지금 보는 쪽(두 쪽 보기면 두 쪽)이 화면에 다 들어오게."""
        c = self.canvas
        if not c.document or not c.document.page_count:
            return
        index = self.current_page()
        self._relayout()  # 배치를 다시 계산하면 쪽 위치도 바로 다시 놓는다 (안 놓으면 쪽이 사라짐)
        w_pt, h_pt = self._group_size_pt(c.groups[c.group_of(index)])
        width, height = self._available_size()
        self.set_zoom(min(width / (w_pt * PT_TO_PX), height / (h_pt * PT_TO_PX)), fit=FIT_PAGE)
        self.go_to_page(index)

    def fit_width(self) -> None:
        """쪽(두 쪽 보기면 두 쪽) 너비가 화면 너비에 꼭 맞게."""
        c = self.canvas
        if not c.document or not c.document.page_count:
            return
        self._relayout()
        if c.horizontal or c.paged:
            widest = self._group_size_pt(c.groups[c.group_of(self.current_page())])[0]
        else:
            widest = max(self._group_size_pt(g)[0] for g in c.groups)
        width, _ = self._available_size()
        self.set_zoom(width / (widest * PT_TO_PX), fit=FIT_WIDTH)

    def set_zoom(self, zoom: float, anchor: QPoint | None = None, fit: str = FIT_NONE) -> None:
        """배율을 바꾼다. anchor(화면 안의 점)가 가리키던 종이 위치를 그 자리에 그대로 둔다."""
        self.fit_mode = fit
        zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
        if not self.canvas.document or abs(zoom - self.canvas.zoom) < 0.0001:
            # 배율이 그대로여도 배치는 다시 놓는다 (이미 쪽 맞춤 상태에서 [쪽 맞춤]을 또 누른 경우 등)
            self._relayout()
            self.canvas.update()
            self.zoom_changed.emit(self.canvas.zoom)
            return
        if anchor is None:
            anchor = QPoint(self.viewport().width() // 2, self.viewport().height() // 2)
        spot = self._spot_at(anchor)        # 1) 바꾸기 전: anchor 아래 쪽과 그 안의 위치(비율)
        self.canvas.zoom = zoom             # 2) 배율을 바꾸고 다시 배치
        self._relayout()
        if spot:                            # 3) 같은 지점이 anchor 위치에 오도록 스크롤
            index, fx, fy = spot
            rect = self.canvas.page_rects.get(index)
            if rect is not None:
                self.horizontalScrollBar().setValue(round(rect.left() + fx * rect.width()) - anchor.x())
                self.verticalScrollBar().setValue(round(rect.top() + fy * rect.height()) - anchor.y())
        self.canvas.update()
        self.zoom_changed.emit(zoom)

    def _spot_at(self, anchor: QPoint) -> tuple[int, float, float] | None:
        rects = self.canvas.page_rects
        if not rects:
            return None
        point = QPoint(anchor.x() + self.horizontalScrollBar().value(),
                       anchor.y() + self.verticalScrollBar().value())
        index = self.canvas.page_at(point)
        if index is None:  # 쪽 사이 빈 곳이면 가장 가까운 쪽
            index = min(rects, key=lambda i: (rects[i].center() - point).manhattanLength())
        rect = rects[index]
        return index, (point.x() - rect.left()) / rect.width(), (point.y() - rect.top()) / rect.height()

    def _available_size(self) -> tuple[int, int]:
        """맞춤 계산에 쓸 화면 크기. 스크롤 막대 자리를 미리 빼 두어 맞춘 뒤 반대 방향 막대가 생기지 않게."""
        bar = self.verticalScrollBar().sizeHint().width()
        width = self.width() - 2 * MARGIN - (0 if self.canvas.horizontal else bar)
        height = self.height() - 2 * MARGIN - (bar if self.canvas.horizontal else 0)
        return max(width, 50), max(height, 50)

    def _relayout(self) -> None:
        self.canvas.relayout()
        self._resize_canvas()

    def _resize_canvas(self) -> None:
        """판을 내용 크기에 맞춘다 (창보다 작으면 창 크기로 늘려 가운데 정렬)."""
        content = self.canvas.content_size
        viewport = self.viewport().size()
        self.canvas.resize(max(content.width(), viewport.width()), max(content.height(), viewport.height()))
        self.canvas.place_pages()

    def _emit_current(self, *_, force: bool = False) -> None:
        current = self.current_page()
        if force or current != self._last_current:
            self._last_current = current
            self.current_page_changed.emit(current)

    # ---------- 이벤트 ----------
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.fit_mode == FIT_WIDTH:
            self.fit_width()
        elif self.fit_mode == FIT_PAGE:
            self.fit_page()
        else:
            self._resize_canvas()

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.ControlModifier:
            # Ctrl + 마우스 휠: 마우스가 가리키는 곳을 중심으로 확대·축소
            anchor = event.position().toPoint()
            if delta > 0:
                self.zoom_in(anchor)
            elif delta < 0:
                self.zoom_out(anchor)
            event.accept()
            return
        bar = self.verticalScrollBar()
        if self.canvas.paged and delta:
            # 한 쪽씩·두 쪽씩: 끝에서 더 굴리면 다음/이전 쪽으로 넘어간다
            if delta < 0 and bar.value() >= bar.maximum():
                self.page_step(1)
                event.accept()
                return
            if delta > 0 and bar.value() <= bar.minimum():
                self.page_step(-1)
                bar.setValue(bar.maximum())
                event.accept()
                return
        if self.canvas.horizontal and delta and not event.angleDelta().x():
            # 가로 스크롤 보기: 마우스 휠로 옆으로 이동
            hbar = self.horizontalScrollBar()
            hbar.setValue(hbar.value() - delta)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_PageDown, Qt.Key_PageUp) and self.canvas.paged:
            self.page_step(1 if event.key() == Qt.Key_PageDown else -1)
            return
        super().keyPressEvent(event)
