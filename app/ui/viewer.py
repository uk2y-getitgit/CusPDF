"""PDF 뷰어(가운데): 회색 바탕 + 떠 있는 막대들 (5-3).

- 오른쪽 아래: 보기 막대 [보기 방식 ▾] | [−] 100% [+] | [쪽 맞춤]
- 아래 가운데: 선택 막대 (쪽을 골랐을 때만)
- 왼쪽 아래: 변환 진행 카드 (파일 넣는 중에만)
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStackedLayout, QToolButton, QVBoxLayout, QWidget

from app.pdf.document import PdfDocument
from app.ui.icons import icon
from app.ui.overlays import EditPreview, ProgressCard, SelectionBar
from app.ui.page_view import FIT_PAGE, FIT_WIDTH, LAYOUTS, ZOOM_MAX, ZOOM_MIN, PageView
from app.ui.theme import SIZE
from app.ui.widgets import icon_button, vline


class ViewBar(QWidget):
    """[현재 보기 방식 ▾] | [−] 100% [+] | [쪽 맞춤]"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("viewBar")
        self.setAttribute(Qt.WA_StyledBackground)
        s = SIZE["space"]

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.layout_button = QToolButton()
        self.layout_button.setProperty("role", "flat")
        self.layout_button.setIconSize(QSize(SIZE["icon"], SIZE["icon"]))
        self.layout_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.layout_button.setToolTip("보기 방식 바꾸기")
        self.layout_button.setCursor(Qt.PointingHandCursor)
        self.set_layout_name("vertical")

        self.zoom_out_button = icon_button("minus", "축소 (Ctrl + 마우스 휠)", flat=True)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setFixedWidth(5 * s + 4)
        self.zoom_in_button = icon_button("plus", "확대 (Ctrl + 마우스 휠)", flat=True)

        self.fit_page_button = QToolButton()
        self.fit_page_button.setProperty("role", "flat")
        self.fit_page_button.setText("쪽 맞춤")
        self.fit_page_button.setToolTip("쪽 맞춤 (Ctrl+0)")
        self.fit_page_button.setCursor(Qt.PointingHandCursor)
        self.fit_page_button.setCheckable(True)  # 쪽 맞춤 상태일 때 '켜짐' 모양

        layout.addWidget(self.layout_button)
        layout.addWidget(vline())
        layout.addWidget(self.zoom_out_button)
        layout.addWidget(self.zoom_label)
        layout.addWidget(self.zoom_in_button)
        layout.addWidget(vline())
        layout.addWidget(self.fit_page_button)
        self.set_active(False)

    def set_layout_name(self, key: str) -> None:
        self.layout_button.setText(f"{LAYOUTS[key]} ▾")
        self.layout_button.setIcon(icon(f"layout_{key}"))
        self.adjustSize()

    def set_active(self, active: bool) -> None:
        """문서가 열려 있을 때만 쓸 수 있다."""
        for w in (self.layout_button, self.zoom_out_button, self.zoom_in_button, self.fit_page_button):
            w.setEnabled(active)
        self.zoom_label.setProperty("text_role", None if active else "sub")
        self.zoom_label.style().polish(self.zoom_label)

    def show_zoom(self, zoom: float, fit_page: bool) -> None:
        self.zoom_label.setText(f"{round(zoom * 100)}%")
        self.zoom_out_button.setEnabled(zoom > ZOOM_MIN + 0.001)
        self.zoom_in_button.setEnabled(zoom < ZOOM_MAX - 0.001)
        self.fit_page_button.setChecked(fit_page)


class Viewer(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("viewer")
        self.setAttribute(Qt.WA_StyledBackground)

        # 문서가 없을 때 안내
        empty = QWidget()
        title = QLabel("PDF를 열거나 파일을 넣어주세요")
        title.setProperty("text_role", "title")
        hint = QLabel("위쪽 [열기]로 PDF를 열거나, 왼쪽 [파일 넣기]로 hwp·엑셀·워드·사진·PDF를 넣으세요.\n"
                      "파일을 이 창에 끌어다 놓아도 돼요.")
        hint.setProperty("text_role", "sub")
        for label in (title, hint):
            label.setAlignment(Qt.AlignCenter)
        empty_layout = QVBoxLayout(empty)
        empty_layout.addStretch(1)
        empty_layout.addWidget(title)
        empty_layout.addSpacing(SIZE["space"])
        empty_layout.addWidget(hint)
        empty_layout.addStretch(1)

        self.page_view = PageView()
        self._stack = QStackedLayout(self)
        self._stack.addWidget(empty)
        self._stack.addWidget(self.page_view)

        self.view_bar = ViewBar(self)
        self.selection_bar = SelectionBar(self)
        self.progress_card = ProgressCard(self)
        self.edit_preview = EditPreview(self)

        bar, view = self.view_bar, self.page_view
        bar.zoom_in_button.clicked.connect(lambda: view.zoom_in())
        bar.zoom_out_button.clicked.connect(lambda: view.zoom_out())
        bar.fit_page_button.clicked.connect(lambda: view.fit_page())
        view.zoom_changed.connect(lambda zoom: bar.show_zoom(zoom, view.fit_mode == FIT_PAGE))

    def set_document(self, document: PdfDocument | None) -> None:
        view = self.page_view
        view.set_document(document)
        has_pages = bool(document and document.page_count)
        self._stack.setCurrentWidget(view if has_pages else self._stack.widget(0))
        self.view_bar.set_active(has_pages)
        if has_pages:  # 새 문서도 쓰던 맞춤 방식·배율 그대로
            if view.fit_mode == FIT_WIDTH:
                view.fit_width()
            elif view.fit_mode == FIT_PAGE:
                view.fit_page()
            else:
                view.set_zoom(view.zoom)
        self.place_overlays()

    def refresh(self) -> None:
        """쪽을 고친 뒤 다시 그린다."""
        view = self.page_view
        has_pages = bool(view.canvas.document and view.canvas.document.page_count)
        self._stack.setCurrentWidget(view if has_pages else self._stack.widget(0))
        self.view_bar.set_active(has_pages)
        view.refresh()
        self.place_overlays()

    def place_overlays(self) -> None:
        margin = 2 * SIZE["space"]
        w, h = self.width(), self.height()
        for widget in (self.view_bar, self.selection_bar, self.progress_card):
            widget.adjustSize()
        bar = self.view_bar
        bar.move(w - bar.width() - margin, h - bar.height() - margin)
        sel = self.selection_bar
        sel.move((w - sel.width()) // 2, h - sel.height() - margin - (bar.height() + 8 if w < 900 else 0))
        card = self.progress_card
        card.move(margin, h - card.height() - margin)
        for widget in (self.progress_card, self.selection_bar, self.view_bar):
            widget.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.place_overlays()
