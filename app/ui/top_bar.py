"""위쪽 막대: 열기·파일 이름·저장 상태·되돌리기 | 검색칸·글자 수정·마무리·PDF 저장·전체 메뉴 (5-3)."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QStackedLayout, QToolButton,
                               QWidget)

from app.ui.icons import icon
from app.ui.theme import COLOR, SIZE
from app.ui.widgets import button, floating_menu, icon_button, menu_heading


class SearchBox(QLineEdit):
    """Enter: 다음 결과, Shift+Enter: 이전 결과, Esc: 검색 지우기."""
    next_requested = Signal()
    previous_requested = Signal()
    cleared = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            (self.previous_requested if event.modifiers() & Qt.ShiftModifier else self.next_requested).emit()
            return
        if event.key() == Qt.Key_Escape:
            self.clear()
            self.cleared.emit()
            return
        super().keyPressEvent(event)


class TopBar(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setAttribute(Qt.WA_StyledBackground)
        s = SIZE["space"]

        # 평소 막대와 글자 수정 모드 막대를 바꿔 끼운다
        self._stack = QStackedLayout(self)
        normal = QWidget()
        layout = QHBoxLayout(normal)
        layout.setContentsMargins(2 * s, s + 4, 2 * s, s + 4)
        layout.setSpacing(s)
        self._stack.addWidget(normal)
        self._stack.addWidget(self._build_edit_bar())

        # ---- 왼쪽: 열기, 파일 이름, 저장 상태, 되돌리기/다시 실행
        self.open_button = button("열기", "open", tooltip="PDF 열기 (Ctrl+O)")
        self.file_name = QLabel("열린 파일 없음")
        self.file_name.setProperty("text_role", "title")
        self.save_state = QLabel("")
        self.save_state.setProperty("text_role", "sub")
        self.save_state.hide()

        # 3단계 상황별 버튼: 편집한 내용이 있을 때만 보인다
        self.undo_button = icon_button("undo", "되돌리기 (Ctrl+Z)")
        self.redo_button = icon_button("redo", "다시 실행 (Ctrl+Y)")
        self.undo_button.hide()
        self.redo_button.hide()

        layout.addWidget(self.open_button)
        layout.addSpacing(s)
        layout.addWidget(self.file_name)
        layout.addWidget(self.save_state)
        layout.addSpacing(s)
        layout.addWidget(self.undo_button)
        layout.addWidget(self.redo_button)
        layout.addStretch(1)

        # ---- 오른쪽: 검색칸, 글자 수정, 마무리, PDF 저장, 전체 메뉴
        # 검색칸: 돋보기 + 입력칸 + (결과가 있을 때만) 결과 수·이전·다음
        self.search_field = QWidget()
        self.search_field.setObjectName("searchBox")
        self.search_field.setAttribute(Qt.WA_StyledBackground)
        self.search_field.setFixedHeight(SIZE["button"])
        self.search_field.setMinimumWidth(220)
        search_icon = QLabel()
        search_icon.setPixmap(icon("search", COLOR["text_sub"]).pixmap(SIZE["icon"], SIZE["icon"]))
        self.search_box = SearchBox()
        self.search_box.setPlaceholderText("글자 검색 (Ctrl+F)")
        self.search_box.setMinimumWidth(150)
        self.search_count = QLabel("")
        self.search_count.setProperty("text_role", "sub")
        self.search_prev = icon_button("chevron_up", "이전 결과 (Shift+Enter)", flat=True)
        self.search_next = icon_button("chevron_down", "다음 결과 (Enter)", flat=True)
        for w in (self.search_prev, self.search_next):
            w.setFixedSize(28, 28)
        search_layout = QHBoxLayout(self.search_field)
        search_layout.setContentsMargins(12, 0, 4, 0)
        search_layout.setSpacing(s)
        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.search_box, 1)
        search_layout.addWidget(self.search_count)
        search_layout.addWidget(self.search_prev)
        search_layout.addWidget(self.search_next)
        self.show_search_result(None)

        self.text_edit_button = button("글자 수정", "text_edit", tooltip="PDF의 날짜·수치·오타를 바로 고쳐요")
        self.finish_button = button("마무리", "finish", tooltip="순서 정렬, 사진 대지, 간지, 쪽번호, 페이지 교체")
        self.finish_button.setCheckable(True)
        self.save_button = button("PDF 저장", "save", primary=True, tooltip="PDF 저장 (Ctrl+S)")

        self.menu_button = QToolButton()
        self.menu_button.setProperty("role", "icon")
        self.menu_button.setIcon(icon("menu"))
        self.menu_button.setIconSize(QSize(SIZE["icon"], SIZE["icon"]))
        self.menu_button.setToolTip("전체 메뉴")
        self.menu_button.setCursor(Qt.PointingHandCursor)
        self.menu_button.setFocusPolicy(Qt.TabFocus)
        self.menu_button.setPopupMode(QToolButton.InstantPopup)
        self.menu_button.setMenu(self._build_main_menu())

        for w in (self.search_field, self.text_edit_button, self.finish_button, self.save_button):
            layout.addWidget(w)
        layout.addWidget(self.menu_button)

        self.set_document_ready(False)

    def _build_edit_bar(self) -> QWidget:
        """글자 수정 모드: 제목·안내·되돌리기 | [수정 표시] [완료]"""
        s = SIZE["space"]
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(2 * s, s + 4, 2 * s, s + 4)
        layout.setSpacing(s)
        title = QLabel("글자 수정 모드")
        title.setProperty("text_role", "title")
        title.setStyleSheet(f"color: {COLOR['primary_dark']};")
        hint = QLabel("고칠 글자 주위를 드래그해서 감싸세요. 끝나면 [완료]를 누르세요.")
        hint.setProperty("text_role", "sub")
        self.edit_undo_button = icon_button("undo", "되돌리기 (Ctrl+Z)")
        self.show_marks = QCheckBox("수정 표시")
        self.show_marks.setToolTip("고친 곳을 주황 점선으로 보여줘요 (화면에만, 저장 PDF에는 없음)")
        self.show_marks.setChecked(True)
        self.done_button = button("완료", primary=True, tooltip="글자 수정 모드 끝내기 (Esc)")
        layout.addWidget(title)
        layout.addSpacing(s)
        layout.addWidget(hint)
        layout.addSpacing(s)
        layout.addWidget(self.edit_undo_button)
        layout.addStretch(1)
        layout.addWidget(self.show_marks)
        layout.addSpacing(s)
        layout.addWidget(self.done_button)
        return bar

    def set_edit_mode(self, on: bool) -> None:
        self._stack.setCurrentIndex(1 if on else 0)
        self.setProperty("mode", "edit" if on else None)
        self.style().unpolish(self)
        self.style().polish(self)

    # ---------- 상태 표시 ----------
    def set_document_ready(self, ready: bool) -> None:
        """문서(쪽)가 있어야 쓸 수 있는 칸·버튼."""
        for w in (self.search_field, self.save_button, self.text_edit_button, self.finish_button):
            w.setEnabled(ready)

    def show_document(self, name: str, page_count: int, modified: bool) -> None:
        self.file_name.setText(name)
        self.file_name.setToolTip(name)
        self.save_state.setText(f"{page_count}쪽, 저장하지 않은 변경 있음" if modified else f"{page_count}쪽")
        self.save_state.show()

    def set_history(self, can_undo: bool, can_redo: bool) -> None:
        """되돌리기·다시 실행: 기록이 있을 때만 보이고, 할 수 없는 쪽은 흐리게."""
        visible = can_undo or can_redo
        self.edit_undo_button.setEnabled(can_undo)
        self.undo_button.setVisible(visible)
        self.redo_button.setVisible(visible)
        self.undo_button.setEnabled(can_undo)
        self.redo_button.setEnabled(can_redo)

    def show_search_result(self, current: int | None, total: int = 0) -> None:
        """current=None이면 결과 표시를 숨긴다."""
        if current is None:
            self.search_count.hide()
            self.search_prev.hide()
            self.search_next.hide()
            return
        self.search_count.setText(f"{current + 1}/{total}" if total else "없음")
        self.search_count.show()
        self.search_prev.setVisible(total > 1)
        self.search_next.setVisible(total > 1)

    # ---------- 전체 메뉴 ----------
    def _build_main_menu(self) -> QMenu:
        """전체 메뉴(≡) 구성 (5-5). 기능 연결은 메인 창에서 한다."""
        menu = floating_menu(self)
        self.menu_actions: dict[str, QAction] = {}

        def add(key: str, text: str, shortcut: str = "") -> QAction:
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            menu.addAction(action)
            self.menu_actions[key] = action
            return action

        menu_heading(menu, "파일")
        self.recent_menu = floating_menu(menu, "최근 파일")
        menu.addMenu(self.recent_menu)
        add("save_as", "다른 이름으로 저장", "Ctrl+Shift+S")
        add("open_folder", "원본 폴더 열기")

        menu_heading(menu, "페이지")
        add("select_all", "모두 선택", "Ctrl+A")
        add("paper_size", "용지 크기 맞추기 (A4·A3 등)")

        menu_heading(menu, "보기")
        self.layout_menu = floating_menu(menu, "페이지 배치")
        menu.addMenu(self.layout_menu)
        add("fit_page", "쪽 맞춤", "Ctrl+0")
        add("fit_width", "너비 맞춤", "Ctrl+2")
        add("full_screen", "전체 화면", "Ctrl+L")
        self.thumb_size_menu = floating_menu(menu, "썸네일 크기")
        menu.addMenu(self.thumb_size_menu)

        menu_heading(menu, "설정")
        add("presets", "첨부 순서 프리셋 관리")
        add("font_map", "글꼴 연결표")
        add("office_status", "한글·오피스 연결 상태")
        add("save_folder", "저장 기본 폴더")
        add("auto_sort", "파일 이름 번호 순 자동 정렬").setCheckable(True)

        menu_heading(menu, "도움말")
        add("manual", "사용설명서", "F1").setEnabled(False)       # 마지막에 만든다
        add("shortcuts", "단축키 목록")
        return menu
