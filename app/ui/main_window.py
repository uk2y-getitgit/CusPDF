"""메인 창: 위쪽 막대 / 썸네일 패널 · 뷰어 · 오른쪽 패널 / 상태 막대 (5-3).
화면 부품들을 연결하고, 열기·저장·쪽 편집·파일 넣기·검색·보기 설정을 처리한다."""

import os
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QDragEnterEvent, QDropEvent, QKeySequence, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QInputDialog, QMainWindow,
                               QMessageBox, QSplitter, QStackedWidget, QVBoxLayout, QWidget)

from app.convert import availability
from app.convert.order import order_preview, sort_by_number
from app.convert.worker import FILE_FILTER, Job, kind_of, start_worker, unsupported_message
from app.pdf import arrange, generate
from app.pdf.document import A4, PAPERS, OpenError, PdfDocument, load_source
from app.pdf.fonts import find_font, normalize
from app.pdf.text_edit import EditError
from app.settings.store import Settings
from app.ui.page_preview import PagePreview
from app.ui.page_view import FIT_NONE, LAYOUTS, PT_TO_PX
from app.ui.dialogs import FontMapDialog, PaperDialog
from app.ui.drop_reader import has_droppable, is_ezpdf, read_drop, remember_foreground
from app.ui.finish_panel import FinishPanel
from app.ui.side_panel import SidePanel
from app.ui.status_bar import StatusBar
from app.ui.text_edit_panel import TextEditPanel
from app.ui.theme import SIZE
from app.ui.thumbnail_panel import THUMB_WIDTH, ThumbnailPanel
from app.ui.top_bar import TopBar
from app.ui.view_menu import ViewMenu
from app.ui.viewer import Viewer

APP_TITLE = "보고서 PDF 편집기"
THUMB_SIZES = {"small": "작게", "medium": "보통", "large": "크게"}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1100, 680)
        self.resize(1440, 880)
        self.settings = Settings()
        self.document: PdfDocument | None = None
        self._worker = None
        self._thread = None
        self._search_text = ""
        self._search_index = -1
        self._anchor_row: int | None = None
        self._was_maximized = False

        self.top_bar = TopBar()
        self.thumbnail_panel = ThumbnailPanel()
        self.thumbs = self.thumbnail_panel.list
        self.viewer = Viewer()
        self.view = self.viewer.page_view
        self.status = StatusBar()
        self.side_panel = SidePanel()
        self.text_panel = TextEditPanel()
        self.finish_panel = FinishPanel()
        self.edit_mode = False
        self._edit_index: int | None = None     # 글자 수정: 고른 글자가 있는 쪽
        self._jobs_done = None                   # 변환 작업이 끝났을 때 할 일
        self._side_insert_at: int | None = None  # ezPDF에서 끌어 놓은 자리 (옆 창 넣기를 그 뒤로 잇기)

        # 오른쪽 패널: 옆 창 / 마무리 사이드바 / 글자 수정 패널 중 하나만, 필요할 때만 열린다
        self.right_panel = QStackedWidget()
        self.right_panel.setObjectName("rightPanel")
        for panel in (self.side_panel, self.text_panel, self.finish_panel):
            self.right_panel.addWidget(panel)
        self.right_panel.hide()

        # 썸네일 패널과 뷰어 사이 경계선을 끌어 패널 폭을 바꾼다 (넓히면 썸네일 2~3열)
        center = QWidget()
        center_layout = QHBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        # 뷰어와 오른쪽 패널 사이 경계선: 옆 창은 끌어서 폭을 바꾼다 (넓히면 썸네일 여러 열)
        self.right_splitter = QSplitter(Qt.Horizontal)
        self.right_splitter.setObjectName("mainSplitter")
        self.right_splitter.setHandleWidth(5)
        self.right_splitter.setChildrenCollapsible(False)
        self.right_splitter.addWidget(self.viewer)
        self.right_splitter.addWidget(self.right_panel)
        self.right_splitter.setStretchFactor(0, 1)
        self.right_splitter.setStretchFactor(1, 0)
        self.right_splitter.splitterMoved.connect(self._remember_side_width)
        center_layout.addWidget(self.right_splitter)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName("mainSplitter")
        self.splitter.setHandleWidth(5)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.thumbnail_panel)
        self.splitter.addWidget(center)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.thumbnail_panel.setMaximumWidth(720)
        self.splitter.splitterMoved.connect(
            lambda *_: self.settings.__setitem__("thumb_panel_width", self.thumbnail_panel.width()))
        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.addWidget(self.splitter)

        central = QWidget()
        central.setObjectName("centralArea")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.top_bar)
        root.addLayout(middle, 1)
        root.addWidget(self.status)
        self.setCentralWidget(central)

        # 시작할 때 어떤 버튼에도 파란 외곽선(키보드 선택)이 보이지 않게
        central.setFocusPolicy(Qt.ClickFocus)
        central.setFocus()
        self.setAcceptDrops(True)

        self._build_actions()
        self._connect()
        self._apply_settings()
        self._check_office()
        self._update_ui()

    # =====================================================================
    # 준비
    # =====================================================================
    def _action(self, text: str, shortcut: str = "", slot=None, checkable: bool = False) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if slot:
            action.triggered.connect(slot)
        action.setCheckable(checkable)
        self.addAction(action)  # 메뉴를 열지 않아도 단축키가 듣도록 창에 등록
        return action

    def _build_actions(self) -> None:
        menu = self.top_bar.menu_actions
        for action in menu.values():
            self.addAction(action)
        a = self.actions_by_key = dict(menu)
        a["open"] = self._action("열기", "Ctrl+O", self.choose_and_open)
        a["save"] = self._action("PDF 저장", "Ctrl+S", self.save)
        a["undo"] = self._action("되돌리기", "Ctrl+Z", self.undo)
        a["redo"] = self._action("다시 실행", "Ctrl+Y", self.redo)
        a["delete"] = self._action("삭제", "Delete", self.delete_selected)
        a["find"] = self._action("글자 검색", "Ctrl+F", self.focus_search)
        a["actual_size"] = self._action("실제 크기 100%", "Ctrl+1", lambda: self.view.actual_size())
        a["toggle_thumbnails"] = self._action("썸네일 패널 숨기기", "F4", self.toggle_thumbnails)
        a["rotate_view_left"] = self._action("화면 회전 왼쪽", "", lambda: self.rotate_view(-90))
        a["rotate_view_right"] = self._action("화면 회전 오른쪽", "", lambda: self.rotate_view(90))
        a["cover_separate"] = self._action("두 쪽 보기에서 표지는 따로 보기", "", self.toggle_cover, checkable=True)
        a["page_up"] = self._action("이전 쪽", "PgUp", lambda: self.view.page_step(-1))
        a["page_down"] = self._action("다음 쪽", "PgDown", lambda: self.view.page_step(1))
        a["page_up"].setShortcutContext(Qt.WidgetWithChildrenShortcut)   # 뷰어 안에서만
        a["page_down"].setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.viewer.addAction(a["page_up"])
        self.viewer.addAction(a["page_down"])

        menu["save_as"].triggered.connect(self.save)
        menu["open_folder"].triggered.connect(self.open_source_folder)
        menu["select_all"].triggered.connect(self.select_all)
        menu["fit_page"].triggered.connect(lambda: self.view.fit_page())
        menu["fit_width"].triggered.connect(lambda: self.view.fit_width())
        menu["full_screen"].triggered.connect(self.toggle_full_screen)
        menu["office_status"].triggered.connect(self.show_office_status)
        menu["save_folder"].triggered.connect(self.choose_save_folder)
        menu["auto_sort"].toggled.connect(lambda on: self.settings.__setitem__("auto_sort", on))
        menu["shortcuts"].triggered.connect(self.show_shortcuts)
        menu["presets"].triggered.connect(lambda: self.open_finish_panel("order"))
        menu["paper_size"].triggered.connect(self.change_paper_size)
        menu["font_map"].triggered.connect(self.show_font_map)

        # 페이지 배치 (전체 메뉴 › 페이지 배치, 보기 메뉴 타일)
        self.layout_group = QActionGroup(self)
        self.layout_actions: dict[str, QAction] = {}
        for key, text in LAYOUTS.items():
            action = QAction(text, self, checkable=True)
            action.triggered.connect(lambda _=False, k=key: self.set_layout(k))
            self.layout_group.addAction(action)
            self.top_bar.layout_menu.addAction(action)
            self.layout_actions[key] = action
        self.thumb_group = QActionGroup(self)
        self.thumb_actions: dict[str, QAction] = {}
        for key, text in THUMB_SIZES.items():
            action = QAction(text, self, checkable=True)
            action.triggered.connect(lambda _=False, k=key: self.set_thumb_size(k))
            self.thumb_group.addAction(action)
            self.top_bar.thumb_size_menu.addAction(action)
            self.thumb_actions[key] = action
        self.top_bar.recent_menu.aboutToShow.connect(self._fill_recent_menu)

        self.view_menu = ViewMenu(a, self)
        self.view_menu.tiles.chosen.connect(lambda key: (self.view_menu.close(), self.set_layout(key)))

    def _connect(self) -> None:
        tb, th, v = self.top_bar, self.thumbnail_panel, self.viewer
        tb.open_button.clicked.connect(self.choose_and_open)
        tb.save_button.clicked.connect(self.save)
        tb.undo_button.clicked.connect(self.undo)
        tb.redo_button.clicked.connect(self.redo)
        tb.search_box.next_requested.connect(lambda: self.search_step(1))
        tb.search_box.previous_requested.connect(lambda: self.search_step(-1))
        tb.search_box.cleared.connect(self.clear_search)
        tb.search_box.textChanged.connect(lambda _: self._reset_search_marks())
        tb.search_next.clicked.connect(lambda: self.search_step(1))
        tb.search_prev.clicked.connect(lambda: self.search_step(-1))

        th.add_files_button.clicked.connect(lambda: self.choose_and_insert(self._insert_position()))
        th.import_pages_button.clicked.connect(lambda: self.open_side_pdf())
        for target in (th.import_pages_button, self.side_panel):
            target.setAcceptDrops(True)
            target.installEventFilter(self)
        self.thumbs.unreadable_dropped.connect(self.show_unreadable_drop)
        self.thumbs.ezpdf_dropped.connect(self.insert_from_ezpdf)
        th.action_requested.connect(self._on_thumb_menu)
        self.thumbs.page_clicked.connect(self._on_thumb_clicked)
        self.thumbs.itemSelectionChanged.connect(self._on_selection_changed)
        self.thumbs.pages_moved.connect(self.move_pages)
        self.thumbs.files_dropped.connect(self.insert_files)
        self.thumbs.side_pages_dropped.connect(self.insert_side_pages)

        self.view.current_page_changed.connect(self.thumbs.set_current)
        self.view.canvas.page_clicked.connect(self._on_page_clicked)
        self.view.zoom_changed.connect(lambda _: self._remember_zoom())
        v.view_bar.layout_button.clicked.connect(
            lambda: self.view_menu.popup_above(v.view_bar.layout_button, self.view.canvas.layout_mode))
        v.selection_bar.rotate_clicked.connect(self.rotate_selected)
        v.selection_bar.delete_clicked.connect(self.delete_selected)
        v.selection_bar.clear_clicked.connect(self.clear_selection)

        self.side_panel.closed.connect(self.close_side_panel)
        self.side_panel.change_requested.connect(lambda: self.open_side_pdf())
        self.side_panel.insert_requested.connect(lambda: self.insert_side_pages(None))
        self.side_panel.list.preview_requested.connect(self.preview_side_page)
        self.side_panel.scale_changed.connect(lambda v: self.settings.__setitem__("side_thumb_scale", v))

        # 글자 수정 (2단계)
        tb.text_edit_button.clicked.connect(self.enter_text_edit)
        tb.done_button.clicked.connect(self.exit_text_edit)
        tb.edit_undo_button.clicked.connect(self.undo)
        tb.show_marks.toggled.connect(self._toggle_marks)
        self.view.canvas.area_selected.connect(self._on_area_selected)
        self.view.verticalScrollBar().valueChanged.connect(self._place_edit_preview)
        self.view.horizontalScrollBar().valueChanged.connect(self._place_edit_preview)
        self.view.zoom_changed.connect(lambda _: self._update_edit_preview())
        self.text_panel.preview_requested.connect(self._update_edit_preview)
        self.text_panel.apply_requested.connect(self.apply_text_edit)
        self.text_panel.cancel_requested.connect(self._cancel_edit_selection)

        # 마무리 (3단계)
        tb.finish_button.clicked.connect(lambda: self.toggle_finish_panel())
        fp = self.finish_panel
        fp.closed.connect(self.close_right_panel)
        fp.sort_requested.connect(self.sort_by_preset)
        fp.preset_chosen.connect(self._choose_preset)
        fp.preset_save_requested.connect(self._save_preset)
        fp.preset_delete_requested.connect(self._delete_preset)
        fp.photo_sheet_requested.connect(self.make_photo_sheet)
        fp.dividers_requested.connect(self.insert_dividers)
        fp.page_numbers_changed.connect(self.set_page_numbers)
        fp.replace_requested.connect(self.replace_selected_pages)
        fp.step_done.connect(self._finish_step_done)
        v.selection_bar.replace_clicked.connect(self.replace_selected_pages)

    def _apply_settings(self) -> None:
        """마지막으로 쓴 보기 방식을 다시 적용한다 (1-2)."""
        st = self.settings
        layout = st["view_layout"] if st["view_layout"] in LAYOUTS else "vertical"
        canvas = self.view.canvas
        canvas.layout_mode = layout
        canvas.cover_separate = bool(st["cover_separate"])
        canvas.zoom = float(st["zoom"] or 1.0)
        self.view.fit_mode = st["fit_mode"] if st["fit_mode"] in ("none", "page", "width") else FIT_NONE
        self.layout_actions[layout].setChecked(True)
        self.viewer.view_bar.set_layout_name(layout)
        self.actions_by_key["cover_separate"].setChecked(canvas.cover_separate)
        width = int(st["thumb_panel_width"] or SIZE["thumbnail_panel"])
        self.splitter.setSizes([width, max(400, self.width() - width)])
        size = st["thumbnail_size"] if st["thumbnail_size"] in THUMB_WIDTH else "medium"
        self.thumbs.size_name = size
        self.thumb_actions[size].setChecked(True)
        self.top_bar.menu_actions["auto_sort"].setChecked(bool(st["auto_sort"]))
        self.side_panel.set_scale(int(st["side_thumb_scale"] or 100))

    def _check_office(self) -> None:
        found = availability.check()
        missing = [name for name, ok in found.items() if not ok]
        if not missing:
            self.status.set_office_status("한글·엑셀·워드 연결됨", True)
        else:
            self.status.set_office_status(f"{'·'.join(missing)} 없음", False)

    # =====================================================================
    # 화면 갱신
    # =====================================================================
    def _update_ui(self) -> None:
        doc = self.document
        has_pages = bool(doc and doc.page_count)
        busy = self._thread is not None
        if doc:
            self.top_bar.show_document(doc.name, doc.page_count, doc.modified)
            self.top_bar.set_history(doc.can_undo and not busy, doc.can_redo and not busy)
            self.thumbnail_panel.set_page_count(doc.page_count)
            mark = "* " if doc.modified else ""
            self.setWindowTitle(f"{mark}{doc.name} - {APP_TITLE}")
        else:
            self.top_bar.set_history(False, False)
        self.top_bar.set_document_ready(has_pages)
        a = self.actions_by_key
        for key in ("save", "save_as", "select_all", "fit_page", "fit_width", "actual_size",
                    "rotate_view_left", "rotate_view_right", "find"):
            a[key].setEnabled(has_pages)
        a["undo"].setEnabled(bool(doc and doc.can_undo and not busy))
        a["redo"].setEnabled(bool(doc and doc.can_redo and not busy))
        a["open_folder"].setEnabled(bool(doc and (doc.path or doc.sources)))

    def _set_document(self, document: PdfDocument | None) -> None:
        if self.document and self.document is not document:
            self.document.close()
        self.document = document
        self.clear_search()
        self.viewer.set_document(document)
        self.thumbs.set_document(document)
        self._update_ui()

    def _after_edit(self, selected: list[int] | None = None, fresh: list[int] | None = None,
                    message: str = "") -> None:
        """쪽을 고친 뒤 썸네일·뷰어·막대를 모두 새로 고친다."""
        self._reset_search_marks()
        self.thumbs.reload(selected or [])
        self.viewer.refresh()
        if fresh:
            self.thumbs.flash(fresh)
            self.view.go_to_page(fresh[0])
        self._refresh_page_numbers()
        self._update_ui()
        if self.right_panel.isVisible() and self.right_panel.currentWidget() is self.finish_panel:
            self.finish_panel.refresh(self.document, len(self.selected_rows()))
        if message:
            self.status.show_message(message)

    def _ensure_document(self) -> PdfDocument:
        if not self.document:
            self._set_document(PdfDocument())
        return self.document

    # =====================================================================
    # 열기·저장
    # =====================================================================
    def _start_folder(self) -> str:
        folder = self.settings["last_folder"]
        return folder if folder and Path(folder).is_dir() else str(Path.home() / "Documents")

    def choose_and_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "PDF 열기", self._start_folder(), "PDF 파일 (*.pdf)")
        if path:
            self.open_pdf(Path(path))

    def open_pdf(self, path: Path) -> None:
        if not self._confirm_discard():
            return
        try:
            document = PdfDocument.open(path)
        except OpenError as error:
            QMessageBox.warning(self, "열 수 없어요", str(error))
            return
        self.settings["last_folder"] = str(path.parent)
        self.settings.add_recent(path)
        self._set_document(document)
        self.status.show_message(f"{document.name} 파일을 열었어요")

    def _confirm_discard(self) -> bool:
        """저장하지 않은 변경이 있으면 물어본다. 계속해도 되면 True."""
        if self._thread is not None:
            QMessageBox.information(self, "파일을 넣는 중이에요", "파일 넣기가 끝난 뒤 다시 해주세요.")
            return False
        if not (self.document and self.document.modified and self.document.page_count):
            return True
        answer = QMessageBox.question(
            self, "저장하지 않은 변경", f"{self.document.name}에 저장하지 않은 변경이 있어요. 저장할까요?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if answer == QMessageBox.Save:
            return self.save()
        return answer == QMessageBox.Discard

    def save(self) -> bool:
        """다른 이름으로 저장 창을 연다. 기본 이름은 원래이름_최종.pdf, 원본과 같은 이름은 막는다."""
        doc = self.document
        if not doc or not doc.page_count:
            return False
        stem = doc.path.stem if doc.path else "보고서"
        folder = self.settings["save_folder"]
        if not (folder and Path(folder).is_dir()):
            folder = str(doc.path.parent) if doc.path else self._start_folder()
        suggested = str(Path(folder) / f"{stem}_최종.pdf")
        while True:
            path, _ = QFileDialog.getSaveFileName(self, "PDF 저장", suggested, "PDF 파일 (*.pdf)")
            if not path:
                return False
            target = Path(path)
            if target.suffix.lower() != ".pdf":
                target = target.with_suffix(".pdf")
            if target.resolve() in doc.original_paths():
                QMessageBox.warning(self, "원본과 같은 이름이에요",
                                    f"{target.name}은(는) 원본 파일이라 덮어쓸 수 없어요. 다른 이름으로 저장해주세요.")
                suggested = str(target.with_name(f"{target.stem}_최종.pdf"))
                continue
            break
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            doc.save(target)
        except PermissionError:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "저장하지 못했어요",
                                f"{target.name} 파일이 다른 프로그램에서 열려 있어요. 그 파일을 닫고 다시 저장해주세요.")
            return False
        except Exception as error:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "저장하지 못했어요",
                                f"{target.name} 파일을 저장하지 못했어요. 저장할 폴더에 쓸 수 있는지 확인해주세요.\n({error})")
            return False
        QApplication.restoreOverrideCursor()
        self.settings["last_folder"] = str(target.parent)
        self._update_ui()
        self.status.show_message(f"{target.name} 파일로 저장했어요")
        return True

    def open_source_folder(self) -> None:
        doc = self.document
        if not doc:
            return
        path = doc.path or next((s.path for s in doc.sources if s.path), None)
        if path and path.parent.is_dir():
            os.startfile(path.parent)

    def choose_save_folder(self) -> None:
        current = self.settings["save_folder"] or self._start_folder()
        folder = QFileDialog.getExistingDirectory(self, "저장 기본 폴더 고르기", current)
        if folder:
            self.settings["save_folder"] = folder
            self.status.show_message(f"저장 창이 {folder} 폴더에서 열려요")

    def _fill_recent_menu(self) -> None:
        menu = self.top_bar.recent_menu
        menu.clear()
        recent = [Path(p) for p in self.settings["recent_files"] if Path(p).exists()]
        if not recent:
            menu.addAction("최근 파일 없음").setEnabled(False)
        for path in recent:
            menu.addAction(path.name, lambda p=path: self.open_pdf(p)).setToolTip(str(path))

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    # =====================================================================
    # 선택
    # =====================================================================
    def selected_rows(self) -> list[int]:
        return self.thumbs.selected_rows()

    def _on_selection_changed(self) -> None:
        rows = self.selected_rows()
        self.viewer.selection_bar.set_count(len(rows))
        self.viewer.place_overlays()
        self.view.canvas.selected = set(rows)
        self.view.canvas.update()
        self.actions_by_key["delete"].setEnabled(bool(rows))

    def _on_thumb_clicked(self, row: int) -> None:
        self._anchor_row = row
        self.view.go_to_page(row)

    def _on_page_clicked(self, index: int, modifiers) -> None:
        """뷰어에서 쪽을 누르면 그 쪽을 고른다 (Ctrl: 더하기·빼기, Shift: 범위)."""
        rows = set(self.selected_rows())
        if modifiers & Qt.ControlModifier:
            rows ^= {index}
        elif modifiers & Qt.ShiftModifier and self._anchor_row is not None:
            low, high = sorted((self._anchor_row, index))
            rows |= set(range(low, high + 1))
        else:
            rows = {index}
        if not modifiers & Qt.ShiftModifier:
            self._anchor_row = index
        self.thumbs.select_rows(sorted(rows))

    def select_all(self) -> None:
        if self.document:
            self.thumbs.select_rows(list(range(self.document.page_count)))

    def clear_selection(self) -> None:
        self.thumbs.select_rows([])

    def _insert_position(self) -> int:
        """새 쪽이 들어갈 자리: 선택한 쪽 바로 뒤, 없으면 맨 끝."""
        rows = self.selected_rows()
        if rows:
            return rows[-1] + 1
        return self.document.page_count if self.document else 0

    # =====================================================================
    # 쪽 편집
    # =====================================================================
    def rotate_selected(self) -> None:
        rows = self.selected_rows()
        if not rows:
            return
        self.document.rotate(rows, 90)
        self._after_edit(selected=rows, message=f"{len(rows)}쪽을 오른쪽으로 돌렸어요")

    def delete_selected(self) -> None:
        rows = self.selected_rows()
        if not rows or self._thread is not None:
            return
        self.document.delete(rows)
        self._after_edit(message=f"{len(rows)}쪽을 지웠어요. 되돌리려면 Ctrl+Z를 누르세요")

    def move_pages(self, rows: list[int], to: int) -> None:
        if not self.document or self._thread is not None:
            return
        before = list(self.document.pages)
        new_rows = self.document.move(rows, to)
        if self.document.pages != before:
            self._after_edit(selected=new_rows, message=f"{len(rows)}쪽을 옮겼어요")

    def add_blank_page(self) -> None:
        """선택한 쪽 바로 뒤에 빈 쪽 (크기는 선택한 쪽과 같게, 없으면 A4 세로)."""
        doc = self._ensure_document()
        rows = self.selected_rows()
        if rows:
            after = rows[-1]
            size = doc.page_size(after)
        elif doc.page_count:
            after = self.view.current_page()
            size = doc.page_size(after)
        else:
            after, size = -1, A4
        index = doc.insert_blank(after + 1, size)
        self._after_edit(selected=[index], fresh=[index], message=f"{index}쪽 뒤에 빈 페이지를 추가했어요"
                         if index else "빈 페이지를 추가했어요")

    def change_paper_size(self) -> None:
        """모든 쪽 또는 선택한 쪽의 용지 크기를 A4·A3 등으로 맞춘다."""
        doc = self.document
        if not (doc and doc.page_count) or self._thread is not None:
            return
        rows = self.selected_rows()
        dialog = PaperDialog(doc.paper_summary(), doc.paper_summary(rows) if rows else {}, self)
        if not dialog.exec():
            return
        only_selected, paper, orientation = dialog.choice()
        targets = rows if only_selected else list(range(doc.page_count))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            changed = doc.resize_pages(targets, PAPERS[paper], orientation, label=f"용지 {paper}로 맞추기")
        finally:
            QApplication.restoreOverrideCursor()
        if not changed:
            self.status.show_message(f"이미 모두 {paper} 크기예요")
            return
        self._after_edit(selected=rows, message=f"{len(changed)}쪽을 {paper} 용지로 맞췄어요. 되돌리려면 Ctrl+Z")

    def undo(self) -> None:
        if self.document and self.document.can_undo and self._thread is None:
            if self.edit_mode:
                self._cancel_edit_selection()
            label = self.document.undo()
            self._after_edit(message=f"되돌렸어요: {label}")

    def redo(self) -> None:
        if self.document and self.document.can_redo and self._thread is None:
            label = self.document.redo()
            self._after_edit(message=f"다시 했어요: {label}")

    def _on_thumb_menu(self, key: str) -> None:
        rows = self.selected_rows()
        if key == "insert_after":
            self.choose_and_insert(rows[-1] + 1 if rows else self._insert_position())
        elif key == "insert_before":
            self.choose_and_insert(rows[0] if rows else 0)
        elif key == "add_blank":
            self.add_blank_page()
        elif key == "rotate":
            self.rotate_selected()
        elif key == "replace":
            self.replace_selected_pages()
        elif key == "paper":
            self.change_paper_size()
        elif key == "delete":
            self.delete_selected()

    # =====================================================================
    # 파일 넣기 (변환 후 삽입)
    # =====================================================================
    def choose_and_insert(self, at: int) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "넣을 파일 고르기", self._start_folder(), FILE_FILTER)
        if paths:
            self.settings["last_folder"] = str(Path(paths[0]).parent)
            self.insert_files([Path(p) for p in paths], at)

    def insert_files(self, paths: list[Path], at: int) -> None:
        if self._thread is not None:
            QMessageBox.information(self, "파일을 넣는 중이에요", "앞의 파일을 넣는 중이에요. 끝난 뒤 다시 넣어주세요.")
            return
        problems = [unsupported_message(p) for p in paths if p.is_dir() or not kind_of(p)]
        paths = [p for p in paths if p.is_file() and kind_of(p)]
        if self.settings["auto_sort"]:
            paths = sort_by_number(paths)
        if problems:
            QMessageBox.warning(self, "넣을 수 없는 파일이 있어요", "\n".join(problems))
        if not paths:
            return

        doc = self._ensure_document()
        self._insert_at = max(0, min(at, doc.page_count))
        self._inserted: list[int] = []
        self._insert_errors: list[str] = []
        self._inserted_files = 0
        self._has_excel = False
        doc.begin_group()
        if len(paths) > 1:
            self.status.show_message(order_preview(paths))

        self._run_jobs([Job(p, kind_of(p)) for p in paths], self._on_converted, self._on_convert_finished)

    def _run_jobs(self, jobs: list[Job], on_converted, on_finished) -> None:
        """작업 스레드에서 차례로 변환한다. 파일 하나가 끝날 때마다 on_converted, 다 끝나면 on_finished.
        작업 스레드의 신호는 모두 이 창의 메서드로 받는다(QueuedConnection) → 화면 스레드에서 실행된다.
        (lambda로 받으면 작업 스레드에서 바로 실행되어 화면을 건드리다 프로그램이 멈출 수 있다)"""
        self._on_job_converted = on_converted
        self._jobs_done = on_finished
        self._thread, self._worker = start_worker(jobs, self)
        self._worker.progress.connect(self._on_job_progress, Qt.QueuedConnection)
        self._worker.converted.connect(self._on_job_converted_slot, Qt.QueuedConnection)
        self._worker.finished.connect(self._on_jobs_finished, Qt.QueuedConnection)
        self._update_ui()
        self._thread.start()

    def _on_job_progress(self, name: str, stage: str, done: int, total: int) -> None:
        self.viewer.progress_card.show_progress(name, stage, done, total)
        self.viewer.place_overlays()

    def _on_job_converted_slot(self, job: Job, pdf: str, error: str) -> None:
        self._on_job_converted(job, pdf, error)

    def _on_jobs_finished(self) -> None:
        self._thread.wait()
        self._worker.cleanup()
        self._thread = self._worker = None
        QTimer.singleShot(1200, self.viewer.progress_card.hide)
        self._jobs_done()
        self._update_ui()

    def _on_converted(self, job: Job, pdf: str, error: str) -> None:
        if error:
            self._insert_errors.append(error)
            return
        doc = self.document
        try:
            source = load_source(pdf, job.kind, name=job.path.name, original=job.path)
        except OpenError as open_error:
            self._insert_errors.append(str(open_error))
            return
        at = max(0, min(self._insert_at, doc.page_count))
        rows = doc.insert_source(source, at)
        self._insert_at = at + len(rows)
        self._inserted.extend(rows)
        self._inserted_files += 1
        self._has_excel |= job.kind == "xlsx"
        self._after_edit(fresh=rows, message=f"{job.path.name} {len(rows)}쪽을 넣었어요")

    def _on_convert_finished(self) -> None:
        doc = self.document
        doc.end_group()
        if self._inserted_files:
            doc.rename_last_undo(f"파일 {self._inserted_files}개 넣기")

        pages = len(self._inserted)
        if pages:
            message = f"파일 {self._inserted_files}개, {pages}쪽을 넣었어요"
            if self._has_excel:
                message += ". 엑셀에서 온 쪽은 표가 잘리지 않았는지 확인해주세요"
            self.status.show_message(message)
            self.thumbs.flash(self._inserted)
        if self._insert_errors:
            QMessageBox.warning(self, "넣지 못한 파일이 있어요", "\n\n".join(self._insert_errors))
        elif self._has_excel:
            QMessageBox.information(self, "표를 확인해주세요",
                                    "엑셀에서 온 쪽이 들어왔어요. 표가 잘리거나 여러 장으로 나뉘지 않았는지 확인해주세요.\n"
                                    "잘렸다면 엑셀에서 인쇄 영역과 용지 방향을 고친 뒤 다시 넣어주세요.")

    # =====================================================================
    # 옆 창 (다른 PDF에서 일부 쪽 넣기)
    # =====================================================================
    def open_side_pdf(self, path: str | Path | None = None) -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "쪽을 가져올 PDF 고르기", self._start_folder(),
                                                  "PDF 파일 (*.pdf)")
        if not path:
            return
        try:
            source = load_source(path, "pdf")
        except OpenError as error:
            QMessageBox.warning(self, "열 수 없어요", str(error))
            return
        self.settings["last_folder"] = str(Path(path).parent)
        self.side_panel.set_source(source)
        self._side_insert_at = None  # 직접 연 옆 창은 '선택한 쪽 뒤'에 넣는다
        self.show_right_panel(self.side_panel)
        self.status.show_message(f"{source.name}을(를) 옆 창에 열었어요. 넣을 쪽을 골라주세요")

    def preview_side_page(self, row: int) -> None:
        """옆 창의 쪽을 크게 보기 (넣을 쪽 확인용). 창은 하나만 띄우고 쪽만 바꾼다."""
        preview = getattr(self, "_preview", None)
        if preview is not None and preview.isVisible() and preview.side is self.side_panel.list:
            preview.show_page(row)
            preview.raise_()
            preview.activateWindow()
            return
        self._preview = PagePreview(self.side_panel.list, row, self)
        self._preview.show()

    def close_side_panel(self) -> None:
        self._side_insert_at = None
        self.close_right_panel()

    def show_right_panel(self, panel: QWidget) -> None:
        """오른쪽 패널은 하나만: 옆 창 / 글자 수정 / 마무리."""
        if self.edit_mode and panel is not self.text_panel:
            self.exit_text_edit()
        self.right_panel.setCurrentWidget(panel)
        if panel is self.side_panel:   # 옆 창만 폭 조절 (글자 수정·마무리는 정해진 폭)
            self.right_panel.setMinimumWidth(SIZE["side_panel"] - 20)
            self.right_panel.setMaximumWidth(1000)
            width = int(self.settings["side_panel_width"] or SIZE["side_panel"])
        else:
            width = panel.minimumWidth() or panel.width()
            self.right_panel.setFixedWidth(width)
        self.right_panel.show()
        total = sum(self.right_splitter.sizes())
        self.right_splitter.setSizes([max(300, total - width), width])
        self.top_bar.finish_button.setChecked(panel is self.finish_panel)
        self.viewer.place_overlays()

    def _remember_side_width(self, *_) -> None:
        if self.right_panel.isVisible() and self.right_panel.currentWidget() is self.side_panel:
            self.settings["side_panel_width"] = self.right_panel.width()
        self.viewer.place_overlays()

    def close_right_panel(self) -> None:
        self.right_panel.hide()
        self.top_bar.finish_button.setChecked(False)
        self.viewer.place_overlays()

    def insert_side_pages(self, at: int | None) -> None:
        source = self.side_panel.source
        pages = self.side_panel.checked_pages()
        if not source or not pages or self._thread is not None:
            return
        doc = self._ensure_document()
        if at is None:
            at = self._side_insert_at if self._side_insert_at is not None else self._insert_position()
        at = max(0, min(at, doc.page_count))
        rows = doc.insert_source(source, at, pages)
        if self._side_insert_at is not None:
            self._side_insert_at = rows[-1] + 1
        self._after_edit(fresh=rows, message=f"{source.name}에서 {len(rows)}쪽을 넣었어요")

    # =====================================================================
    # 창에 끌어다 놓기 (썸네일 패널 밖)
    # =====================================================================
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if has_droppable(event.mimeData()):
            remember_foreground()  # 끌기를 시작한 프로그램 창 (ezPDF 등)
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        content = read_drop(event.mimeData())
        event.acceptProposedAction()
        if content.ezpdf is not None or is_ezpdf(content.formats):
            self.insert_from_ezpdf(content.ezpdf, self.document.page_count if self.document else 0)
            return
        if not content.paths:
            self.show_unreadable_drop()
            return
        paths = content.paths
        # 아무것도 열려 있지 않을 때 탐색기의 PDF 하나 → 그 PDF 열기. 그 밖에는 맨 끝에 넣기
        if not (self.document and self.document.page_count) and len(paths) == 1 \
                and paths[0].suffix.lower() == ".pdf" and not content.from_reader:
            self.open_pdf(paths[0])
        else:
            self.insert_files(paths, self.document.page_count if self.document else 0)

    def insert_from_ezpdf(self, drag, at: int) -> None:
        """ezPDF에서 끈 쪽: 그 파일에서 지금 보던 쪽을 놓은 자리에 넣고, 옆 창에도 열어 더 넣을 수 있게 한다."""
        if self._thread is not None:
            QMessageBox.information(self, "파일을 넣는 중이에요", "앞의 파일을 넣는 중이에요. 끝난 뒤 다시 끌어다 놓아주세요.")
            return
        if drag is None or drag.path is None:
            name = f"{drag.name} " if drag else ""
            QMessageBox.information(
                self, "ezPDF 파일 위치를 찾지 못했어요",
                f"ezPDF에서 끌어온 {name}파일이 어디 있는지 찾지 못했어요.\n"
                "그 PDF 파일을 탐색기에서 [PDF에서 쪽 가져오기] 버튼에 끌어다 놓으면 옆 창에서 쪽을 고를 수 있어요.")
            return
        try:
            source = load_source(drag.path, "pdf")
        except OpenError as error:
            QMessageBox.warning(self, "열 수 없어요", str(error))
            return
        doc = self._ensure_document()
        at = max(0, min(at, doc.page_count))
        self.side_panel.set_source(source)
        self.show_right_panel(self.side_panel)
        if drag.page is not None and drag.page < source.doc.page_count:
            rows = doc.insert_source(source, at, [drag.page])
            self._side_insert_at = rows[-1] + 1   # 옆 창에서 더 고르면 바로 뒤에 이어서
            self.side_panel.list.scrollToItem(self.side_panel.list.item(drag.page))
            self._after_edit(fresh=rows, message=f"ezPDF의 {source.name} {drag.page + 1}쪽을 넣었어요. "
                                                 "여러 쪽을 고르셨다면 옆 창에서 나머지를 골라 넣으세요")
        else:
            self._side_insert_at = at
            self.status.show_message(f"ezPDF의 {source.name}을(를) 옆 창에 열었어요. 넣을 쪽을 골라주세요")

    def show_unreadable_drop(self) -> None:
        QMessageBox.information(
            self, "끌어온 내용을 읽지 못했어요",
            "이 프로그램에서 끌어온 쪽은 아직 읽을 수 없는 형식이에요.\n"
            "대신 그 PDF 파일을 [PDF에서 쪽 가져오기] 버튼에 끌어다 놓으면 옆 창에서 쪽을 고를 수 있어요.\n\n"
            "(어떤 형식이었는지 기록해 두었어요. 알려주시면 이 방식도 읽을 수 있게 맞출게요.)")

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        """[PDF에서 쪽 가져오기] 버튼이나 옆 창에 PDF 파일을 놓으면 옆 창에 바로 연다."""
        if watched in (self.thumbnail_panel.import_pages_button, self.side_panel):
            if event.type() in (QEvent.DragEnter, QEvent.DragMove):
                urls = event.mimeData().urls()
                if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Drop:
                urls = event.mimeData().urls()
                if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    self.open_side_pdf(urls[0].toLocalFile())
                    return True
        return super().eventFilter(watched, event)

    # =====================================================================
    # 검색
    # =====================================================================
    def focus_search(self) -> None:
        self.top_bar.search_box.setFocus()
        self.top_bar.search_box.selectAll()

    def search_step(self, step: int) -> None:
        text = self.top_bar.search_box.text().strip()
        canvas = self.view.canvas
        if not text or not self.document:
            return
        if text != self._search_text or not canvas.highlights:
            self._search_text = text
            canvas.highlights = self.document.search(text, canvas.view_rotation)
            self._search_index = -1 if step > 0 else 0
            if not canvas.highlights:
                self.top_bar.show_search_result(0, 0)
                self.status.show_message(f"'{text}' 글자를 찾지 못했어요")
                canvas.update()
                return
        total = len(canvas.highlights)
        self._search_index = (self._search_index + step) % total
        canvas.current_highlight = self._search_index
        page = canvas.highlights[self._search_index][0]
        self.view.go_to_page(page)
        rect = canvas.highlight_rect(self._search_index)
        if rect is not None:
            self.view.show_rect(rect)
        canvas.update()
        self.top_bar.show_search_result(self._search_index, total)
        self.status.show_message(f"'{text}' {total}곳 중 {self._search_index + 1}번째 ({page + 1}쪽)")

    def _reset_search_marks(self) -> None:
        """글자를 바꾸거나 쪽을 고치면 찾은 위치가 달라지므로 표시를 지운다."""
        self._search_text = ""
        self._search_index = -1
        self.view.canvas.highlights = []
        self.view.canvas.current_highlight = -1
        self.view.canvas.update()
        self.top_bar.show_search_result(None)

    def clear_search(self) -> None:
        self.top_bar.search_box.clear()
        self._reset_search_marks()

    # =====================================================================
    # 보기
    # =====================================================================
    def set_layout(self, key: str) -> None:
        self.view.set_layout(key)
        self.layout_actions[key].setChecked(True)
        self.viewer.view_bar.set_layout_name(key)
        self.viewer.place_overlays()
        self._reset_search_marks()
        self.settings["view_layout"] = key
        self.status.show_message(f"보기 방식: {LAYOUTS[key]}")

    def toggle_cover(self, on: bool) -> None:
        self.view.set_layout(self.view.canvas.layout_mode, cover_separate=on)
        self.settings["cover_separate"] = on

    def rotate_view(self, angle: int) -> None:
        self.view.rotate_view(angle)
        self._reset_search_marks()
        self.status.show_message("화면만 돌렸어요. 파일은 바뀌지 않아요")

    def toggle_full_screen(self) -> None:
        if self.isFullScreen():
            self.showMaximized() if self._was_maximized else self.showNormal()
        else:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()
            self.status.show_message("전체 화면이에요. 나가려면 Esc나 Ctrl+L을 누르세요")

    def toggle_thumbnails(self) -> None:
        visible = not self.thumbnail_panel.isVisible()
        self.thumbnail_panel.setVisible(visible)
        self.actions_by_key["toggle_thumbnails"].setText("썸네일 패널 숨기기" if visible else "썸네일 패널 보이기")

    def set_thumb_size(self, key: str) -> None:
        self.thumbs.set_thumb_size(key)
        self.settings["thumbnail_size"] = key

    def _remember_zoom(self) -> None:
        self.settings.data["zoom"] = self.view.zoom
        self.settings["fit_mode"] = self.view.fit_mode

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            if self.edit_mode:
                if self._edit_index is not None:
                    self._cancel_edit_selection()
                else:
                    self.exit_text_edit()
            elif self.isFullScreen():
                self.toggle_full_screen()
            elif self.selected_rows():
                self.clear_selection()
            return
        super().keyPressEvent(event)

    # =====================================================================
    # 글자 수정 (2단계)
    # =====================================================================
    def enter_text_edit(self) -> None:
        if not (self.document and self.document.page_count) or self._thread is not None:
            return
        self.edit_mode = True
        self.clear_selection()
        self.top_bar.set_edit_mode(True)
        canvas = self.view.canvas
        canvas.edit_mode = True
        canvas.show_marks = self.top_bar.show_marks.isChecked()
        canvas.setCursor(Qt.CrossCursor)
        self.text_panel.reset()
        self.show_right_panel(self.text_panel)
        canvas.update()
        self.status.show_message("글자 수정 모드예요. 고칠 글자를 드래그해서 감싸세요")

    def exit_text_edit(self) -> None:
        if not self.edit_mode:
            return
        self.edit_mode = False
        self.top_bar.set_edit_mode(False)
        canvas = self.view.canvas
        canvas.edit_mode = False
        canvas.show_marks = False  # 수정 표시는 글자 수정 모드에서만 (저장 PDF에는 없음)
        canvas.edit_target = None
        canvas.unsetCursor()
        self._edit_index = None
        self.viewer.edit_preview.hide()
        self.close_right_panel()
        canvas.update()
        self.status.show_message("글자 수정을 마쳤어요")

    def _toggle_marks(self, on: bool) -> None:
        self.view.canvas.show_marks = on and self.edit_mode
        self.view.canvas.update()

    def _on_area_selected(self, index: int, area) -> None:
        doc, canvas = self.document, self.view.canvas
        selection = doc.pick_text(index, area, canvas.view_rotation)
        if selection is None:
            self._edit_index = None
            canvas.edit_target = None
            self.viewer.edit_preview.hide()
            canvas.update()
            self.text_panel.reset("고른 곳에 글자가 없어요. 글자가 그림(스캔)으로 된 쪽이면 고칠 수 없어요.")
            return
        self._edit_index = index
        self._selection = selection
        canvas.edit_target = (index, doc.visible_rect(index, selection.rect, canvas.view_rotation))
        canvas.update()
        font = find_font(selection.font, selection.bold, self.settings["font_map"] or {})
        note = "여러 줄을 감싸서 첫 줄만 골랐어요. 다른 줄은 따로 골라주세요." if selection.multiline else ""
        self.text_panel.show_selection(selection, font, note)

    def _update_edit_preview(self) -> None:
        if self._edit_index is None:
            return
        panel, card = self.text_panel, self.viewer.edit_preview
        font = panel.font_path()
        if not font:
            panel.show_error("넣을 글꼴을 골라주세요.")
            card.hide()
            return
        # 화면 배율의 1.6배(최소 1pt=2.5px)로 크게, 흐리지 않게 화면 배율만큼 더 촘촘히 그린다
        ratio = self.devicePixelRatioF()
        scale = max(PT_TO_PX * self.view.zoom * 1.6, 2.5)
        _, after, error = self.document.preview_text_edit(
            self._edit_index, self._selection, panel.new_text.text(), font, scale=scale * ratio)
        panel.show_error(error)
        pixmap = None
        if after is not None:
            pixmap = QPixmap.fromImage(after)
            pixmap.setDevicePixelRatio(ratio)
        card.show_result(pixmap, error)
        self._place_edit_preview()

    def _place_edit_preview(self, *_) -> None:
        """미리보기 카드를 고른 글자 바로 아래(자리가 없으면 위)에 놓는다. 스크롤·확대하면 따라간다."""
        card, canvas = self.viewer.edit_preview, self.view.canvas
        if not card.isVisible() or not canvas.edit_target or canvas.edit_target[0] not in canvas.page_rects:
            return
        box = canvas._pt_rect(*canvas.edit_target).toAlignedRect()
        top_left = canvas.mapTo(self.viewer, box.topLeft())
        target = box.translated(top_left - box.topLeft())
        card.place_near(target, self.viewer.rect())

    def apply_text_edit(self) -> None:
        if self._edit_index is None:
            return
        panel, index, selection = self.text_panel, self._edit_index, self._selection
        new_text, font = panel.new_text.text(), panel.font_path()
        if not font:
            return
        try:
            self.document.apply_text_edit(index, selection, new_text, font)
        except EditError as error:
            panel.show_error(str(error))
            self.viewer.edit_preview.show_result(None, str(error))
            self._place_edit_preview()
            return
        if panel.remember_font.isVisible() and panel.remember_font.isChecked():
            font_map = dict(self.settings["font_map"] or {})
            font_map[normalize(selection.font)] = font
            self.settings["font_map"] = font_map
        self._edit_index = None
        self.view.canvas.edit_target = None
        self.viewer.edit_preview.hide()
        self._after_edit(message=f"{index + 1}쪽 글자를 고쳤어요: {selection.text} → {new_text}")
        panel.reset("고쳤어요. 다른 글자를 고르거나 위쪽 [완료]를 누르세요.")

    def _cancel_edit_selection(self) -> None:
        self._edit_index = None
        self.view.canvas.edit_target = None
        self.viewer.edit_preview.hide()
        self.view.canvas.update()
        self.text_panel.reset()

    def show_font_map(self) -> None:
        dialog = FontMapDialog(dict(self.settings["font_map"] or {}), self)
        if dialog.exec():
            self.settings["font_map"] = dialog.font_map

    # =====================================================================
    # 마무리 (3단계)
    # =====================================================================
    def toggle_finish_panel(self) -> None:
        if self.right_panel.isVisible() and self.right_panel.currentWidget() is self.finish_panel:
            self.close_right_panel()
        else:
            self.open_finish_panel()

    def open_finish_panel(self, step: str | None = None) -> None:
        if not (self.document and self.document.page_count):
            self.top_bar.finish_button.setChecked(False)
            return
        self.finish_panel.set_presets(self._presets(), self._current_preset())
        if step:
            self.finish_panel.open_key = step
        self.finish_panel.refresh(self.document, len(self.selected_rows()))
        self.show_right_panel(self.finish_panel)

    def _refresh_finish(self) -> None:
        self.finish_panel.refresh(self.document, len(self.selected_rows()))

    def _finish_step_done(self, key: str) -> None:
        if self.document:
            self.document.finish_done.add(key)
            self._refresh_finish()

    def _presets(self) -> dict[str, list[str]]:
        presets = dict(self.settings["presets"] or {})
        presets.setdefault("기본", list(arrange.DEFAULT_PRESET))
        return presets

    def _current_preset(self) -> str:
        name = self.settings["current_preset"]
        return name if name in self._presets() else "기본"

    def _choose_preset(self, name: str) -> None:
        self.settings["current_preset"] = name
        self.finish_panel.set_presets(self._presets(), name)

    def _save_preset(self, order: list[str]) -> None:
        name, ok = QInputDialog.getText(self, "프리셋 저장", "프리셋 이름을 입력하세요 (같은 이름이면 덮어써요)",
                                        text=self._current_preset())
        name = name.strip()
        if not ok or not name:
            return
        presets = self._presets()
        presets[name] = order
        self.settings["presets"] = presets
        self._choose_preset(name)
        self.status.show_message(f"'{name}' 프리셋을 저장했어요")

    def _delete_preset(self, name: str) -> None:
        if name == "기본":
            QMessageBox.information(self, "지울 수 없어요", "기본 프리셋은 지울 수 없어요. 순서를 바꿔 저장해서 써주세요.")
            return
        presets = self._presets()
        presets.pop(name, None)
        self.settings["presets"] = presets
        self._choose_preset("기본")
        self.status.show_message(f"'{name}' 프리셋을 지웠어요")

    def sort_by_preset(self, order: list[str]) -> None:
        doc = self.document
        before = list(doc.pages)
        doc.reorder(arrange.sort_by_preset(doc.pages, order), "순서 정렬")
        doc.finish_done.add("order")
        moved = doc.pages != before
        self._after_edit(message=f"{' → '.join(order)} 순서로 정렬했어요" if moved else "이미 이 순서예요")

    def make_photo_sheet(self, per_page: int, captions: list[str]) -> None:
        doc = self.document
        indices = arrange.photo_indices(doc.pages)
        if not indices:
            return
        photos = [generate.Photo(doc.pages[i].source.doc, doc.pages[i].index, doc.pages[i].rotation,
                                 captions[n] if n < len(captions) else "")
                  for n, i in enumerate(indices)]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            sheet = generate.photo_sheet_pdf(photos, per_page)
        finally:
            QApplication.restoreOverrideCursor()
        new = doc.replace_with(indices, sheet, "사진대지", "사진 대지", "사진 대지 만들기")
        doc.finish_done.add("photos")
        self._after_edit(fresh=new, message=f"사진 {len(indices)}장을 {len(new)}쪽 사진 대지로 만들었어요")

    def insert_dividers(self, chosen: list[tuple[int, str]]) -> None:
        doc = self.document
        doc.begin_group()
        for start, title in sorted(chosen, reverse=True):  # 뒤에서부터 넣어야 앞 위치가 밀리지 않는다
            doc.insert_generated(generate.divider_pdf(title), "간지", title, start)
        doc.end_group()
        doc.rename_last_undo(f"간지 {len(chosen)}개 넣기")
        fresh = [start + n for n, (start, _) in enumerate(sorted(chosen))]
        doc.finish_done.add("dividers")
        self._after_edit(fresh=fresh, message=f"간지 {len(chosen)}쪽을 넣었어요")

    def set_page_numbers(self, numbers) -> None:
        if not self.document:
            return
        self.document.set_page_numbers(numbers)
        self._refresh_page_numbers()
        self._update_ui()
        self.status.show_message("쪽번호를 넣어요. 화면에 미리 보이고, 저장할 때 찍혀요" if numbers
                                 else "쪽번호를 넣지 않아요")

    def _refresh_page_numbers(self) -> None:
        canvas, doc = self.view.canvas, self.document
        numbers = doc.page_numbers if doc else None
        canvas.numbers = numbers
        canvas.page_labels = numbers.labels(doc.kinds()) if numbers else []
        canvas.update()

    # =====================================================================
    # 페이지 교체 (원본 hwp의 같은 쪽만 다시 변환해 바꿔 끼우기)
    # =====================================================================
    def replace_selected_pages(self) -> None:
        doc = self.document
        rows = self.selected_rows()
        if not rows:
            QMessageBox.information(self, "바꿀 쪽을 골라주세요", "바꿀 쪽을 왼쪽 썸네일에서 먼저 골라주세요.")
            return
        if self._thread is not None:
            return
        by_file: dict[Path, list[int]] = {}
        opened, others = [], []
        for row in rows:
            source = doc.pages[row].source
            if source and source.kind == "hwp" and source.path and source.path.suffix.lower() in (".hwp", ".hwpx"):
                by_file.setdefault(source.path, []).append(row)
            elif source and source.kind == "본문":
                opened.append(row)
            else:
                others.append(row)
        if opened:
            path, _ = QFileDialog.getOpenFileName(
                self, f"{len(opened)}쪽의 원본 hwp 고르기 (이 PDF를 만든 hwp 파일)", self._start_folder(),
                "한글 파일 (*.hwp *.hwpx)")
            if path:
                by_file.setdefault(Path(path), []).extend(opened)
        if not by_file:
            if others:
                QMessageBox.information(self, "hwp에서 온 쪽이 아니에요",
                                        "첨부 쪽은 원본 파일에서 고친 뒤 다시 넣어주세요. "
                                        "페이지 교체는 hwp에서 온 본문 쪽만 할 수 있어요.")
            return
        missing = [p.name for p in by_file if not p.exists()]
        if missing:
            QMessageBox.warning(self, "원본 hwp를 찾을 수 없어요",
                                f"{', '.join(missing)} 파일을 찾을 수 없어요. 옮기거나 이름을 바꿨는지 확인해주세요.")
            return
        self._replace_map = by_file
        self._replace_errors: list[str] = []
        self._replaced: list[int] = []
        doc.begin_group()
        self._run_jobs([Job(p, "hwp") for p in by_file], self._on_replace_converted, self._on_replace_finished)

    def _on_replace_converted(self, job: Job, pdf: str, error: str) -> None:
        if error:
            self._replace_errors.append(error)
            return
        doc = self.document
        try:
            source = load_source(pdf, "hwp", name=job.path.name, original=job.path)
        except OpenError as open_error:
            self._replace_errors.append(str(open_error))
            return
        for row in self._replace_map[job.path]:
            page = doc.original_page(row)
            if page >= source.doc.page_count:
                self._replace_errors.append(f"{job.path.name}에는 {page + 1}쪽이 없어요. 원본 hwp의 쪽 수가 줄었는지 확인해주세요.")
                continue
            doc.replace_page(row, source, page)
            self._replaced.append(row)
        self._after_edit(selected=self._replaced, fresh=list(self._replaced))

    def _on_replace_finished(self) -> None:
        doc = self.document
        doc.end_group()
        if self._replaced:
            doc.rename_last_undo(f"{len(self._replaced)}쪽 페이지 교체")
            doc.finish_done.add("replace")
            self.status.show_message(f"{len(self._replaced)}쪽을 원본 hwp에서 다시 만들어 바꿨어요")
            self._refresh_finish()
        if self._replace_errors:
            QMessageBox.warning(self, "바꾸지 못한 쪽이 있어요", "\n\n".join(self._replace_errors))

    # =====================================================================
    # 안내 창
    # =====================================================================
    def show_office_status(self) -> None:
        found = availability.check()
        lines = [f"{name}: {'사용할 수 있어요' if ok else '설치되어 있지 않아요'}" for name, ok in found.items()]
        lines.append("\n한글은 보안 모듈이 등록되어 있어 승인 창 없이 변환해요.")
        QMessageBox.information(self, "한글·오피스 연결 상태", "\n".join(lines))

    def show_shortcuts(self) -> None:
        rows = [
            ("열기", "Ctrl+O"), ("PDF 저장", "Ctrl+S"), ("다른 이름으로 저장", "Ctrl+Shift+S"),
            ("되돌리기 / 다시 실행", "Ctrl+Z / Ctrl+Y"), ("선택한 쪽 삭제", "Delete"), ("모두 선택", "Ctrl+A"),
            ("글자 검색", "Ctrl+F"), ("다음 / 이전 검색 결과", "Enter / Shift+Enter"),
            ("쪽 맞춤 / 실제 크기 / 너비 맞춤", "Ctrl+0 / Ctrl+1 / Ctrl+2"), ("확대·축소", "Ctrl + 마우스 휠"),
            ("전체 화면", "Ctrl+L"), ("썸네일 패널 숨기기", "F4"), ("선택 해제, 전체 화면 나가기", "Esc"),
        ]
        table = "".join(f"<tr><td style='padding:4px 24px 4px 0'>{a}</td><td><b>{b}</b></td></tr>" for a, b in rows)
        box = QMessageBox(self)
        box.setWindowTitle("단축키 목록")
        box.setTextFormat(Qt.RichText)
        box.setText(f"<table>{table}</table>")
        box.exec()
