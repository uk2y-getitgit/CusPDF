"""마무리 사이드바 (오른쪽, 너비 약 360): 위에서부터 차례로 진행한다 (CLAUDE.md 3단계, 5-4).

1. 순서 정렬(프리셋)  2. 사진 대지  3. 간지  4. 쪽번호  5. 페이지 교체
끝난 단계는 초록 체크, 지금 할 단계는 노란 동그라미와 연한 노란 배경.
"""

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygon
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QPushButton, QRadioButton, QScrollArea,
                               QToolButton, QVBoxLayout, QWidget)

from app.pdf import arrange
from app.pdf.document import PdfDocument
from app.pdf.generate import FORMATS, POSITIONS, PageNumbers
from app.ui.theme import COLOR, SIZE
from app.ui.widgets import button, icon_button

STEPS = [
    ("order", "순서 정렬", "파일 종류별 순서로 한 번에 정리해요"),
    ("photos", "사진 대지", "사진 쪽을 한 쪽에 여러 장씩 모아요"),
    ("dividers", "간지", "첨부 자료 앞에 '첨부 1. ○○' 쪽을 넣어요"),
    ("numbers", "쪽번호", "기본은 꺼져 있어요"),
    ("replace", "페이지 교체", "고친 hwp 쪽을 다시 변환해 바꿔 끼워요"),
]


class StatusDot(QWidget):
    """단계 상태 표시: 끝남(초록 체크) / 지금(노란 동그라미) / 남음(회색 동그라미)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = "todo"
        self.setFixedSize(22, 22)

    def set_state(self, state: str) -> None:
        self.state = state
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        if self.state == "done":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(COLOR["success"]))
            p.drawEllipse(r)
            p.setPen(QPen(QColor(COLOR["white"]), 2))
            c = r.center()
            p.drawPolyline(QPolygon([c + QPoint(-4, 0), c + QPoint(-1, 3), c + QPoint(4, -3)]))
        elif self.state == "current":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(COLOR["highlight"]))
            p.drawEllipse(r)
        else:
            p.setPen(QPen(QColor(COLOR["line"]), 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(r.adjusted(1, 1, -1, -1))



class Step(QFrame):
    """한 단계: 머리줄(상태·제목·설명)을 누르면 내용이 펼쳐진다."""
    toggled = Signal(str)
    skip_requested = Signal(str)

    def __init__(self, key: str, title: str, summary: str, body: QWidget):
        super().__init__()
        self.key = key
        self.setObjectName("finishStep")
        self.setAttribute(Qt.WA_StyledBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        head = QPushButton()
        head.setObjectName("stepHead")
        head.setCursor(Qt.PointingHandCursor)
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(0, 0, 0, 0)
        head_layout.setSpacing(10)
        self.dot = StatusDot()
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight: 600;")
        self.summary = QLabel(summary)
        self.summary.setProperty("text_role", "sub")
        texts.addWidget(self.title)
        texts.addWidget(self.summary)
        head_layout.addWidget(self.dot)
        head_layout.addLayout(texts, 1)
        head.setMinimumHeight(40)
        head.clicked.connect(lambda: self.toggled.emit(self.key))

        self.body = body
        skip = QPushButton("이 단계 건너뛰기")
        skip.setObjectName("linkButton")
        skip.setCursor(Qt.PointingHandCursor)
        skip.clicked.connect(lambda: self.skip_requested.emit(self.key))
        self.skip = skip
        layout.addWidget(head)
        layout.addWidget(body)
        layout.addWidget(skip, 0, Qt.AlignRight)
        self.set_open(False)

    def set_state(self, state: str) -> None:
        self.dot.set_state(state)
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_open(self, open_: bool) -> None:
        self.body.setVisible(open_)
        self.skip.setVisible(open_)


class FinishPanel(QWidget):
    closed = Signal()
    sort_requested = Signal(list)                 # 프리셋 순서
    preset_save_requested = Signal(list)          # 지금 목록 순서를 프리셋으로
    preset_delete_requested = Signal(str)
    preset_chosen = Signal(str)
    photo_sheet_requested = Signal(int, list)     # 한 쪽 사진 수, 캡션들
    dividers_requested = Signal(list)             # [(묶음 첫 쪽, 간지 제목)]
    page_numbers_changed = Signal(object)         # PageNumbers 또는 None
    replace_requested = Signal()
    step_done = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedWidth(SIZE["finish_panel"])
        self.document: PdfDocument | None = None
        self.open_key: str | None = None
        self._groups: list[arrange.Group] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(16, 12, 8, 8)
        title = QLabel("마무리")
        title.setProperty("text_role", "title")
        close = icon_button("close", "마무리 닫기", flat=True)
        close.clicked.connect(self.closed)
        head.addWidget(title, 1)
        head.addWidget(close)
        lead = QLabel("위에서부터 차례로 하면 가장 깔끔해요. 필요 없는 단계는 건너뛰세요.")
        lead.setProperty("text_role", "sub")
        lead.setWordWrap(True)
        lead.setContentsMargins(16, 0, 16, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        holder = QWidget()
        self.steps_layout = QVBoxLayout(holder)
        self.steps_layout.setContentsMargins(8, 0, 8, 16)
        self.steps_layout.setSpacing(4)
        scroll.setWidget(holder)

        bodies = {"order": self._order_body(), "photos": self._photos_body(), "dividers": self._dividers_body(),
                  "numbers": self._numbers_body(), "replace": self._replace_body()}
        self.steps: dict[str, Step] = {}
        for key, name, summary in STEPS:
            step = Step(key, name, summary, bodies[key])
            step.toggled.connect(self._toggle)
            step.skip_requested.connect(self.step_done)
            self.steps[key] = step
            self.steps_layout.addWidget(step)
        self.steps_layout.addStretch(1)

        outer.addLayout(head)
        outer.addWidget(lead)
        outer.addWidget(scroll, 1)

    # ================================================================ 단계 내용
    def _order_body(self) -> QWidget:
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 0, 0, 0)
        lay.setSpacing(6)
        row = QHBoxLayout()
        self.preset_box = QComboBox()
        self.preset_box.currentTextChanged.connect(lambda name: name and self.preset_chosen.emit(name))
        delete = icon_button("trash", "이 프리셋 지우기", flat=True)
        delete.clicked.connect(lambda: self.preset_delete_requested.emit(self.preset_box.currentText()))
        row.addWidget(self.preset_box, 1)
        row.addWidget(delete)
        self.order_list = QListWidget()
        self.order_list.setObjectName("orderList")
        self.order_list.setFixedHeight(5 * 30 + 6)
        moves = QHBoxLayout()
        up = icon_button("chevron_up", "위로", flat=True)
        down = icon_button("chevron_down", "아래로", flat=True)
        up.clicked.connect(lambda: self._move_item(-1))
        down.clicked.connect(lambda: self._move_item(1))
        save = QPushButton("현재 순서를 프리셋으로 저장")
        save.setObjectName("linkButton")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(lambda: self.preset_save_requested.emit(self.order()))
        moves.addWidget(up)
        moves.addWidget(down)
        moves.addStretch(1)
        moves.addWidget(save)
        hint = QLabel("같은 종류 안에서는 파일 이름 번호 순서로 놓여요. 간지는 자기 첨부와 함께 움직여요.")
        hint.setProperty("text_role", "sub")
        hint.setWordWrap(True)
        apply = button("이 순서로 정렬")
        apply.setProperty("size", "panel")
        apply.clicked.connect(lambda: self.sort_requested.emit(self.order()))
        lay.addLayout(row)
        lay.addWidget(self.order_list)
        lay.addLayout(moves)
        lay.addWidget(hint)
        lay.addWidget(apply)
        return body

    def _photos_body(self) -> QWidget:
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 0, 0, 0)
        lay.setSpacing(6)
        self.photo_info = QLabel("")
        self.photo_info.setWordWrap(True)
        counts = QHBoxLayout()
        self.per_page = QButtonGroup(self)
        for n in (2, 4, 6):
            choice = QToolButton()
            choice.setText(f"{n}장씩")
            choice.setCheckable(True)
            choice.setProperty("role", "segment")
            choice.setChecked(n == 4)
            self.per_page.addButton(choice, n)
            counts.addWidget(choice)
        counts.addStretch(1)
        cap = QLabel("캡션 (파일 이름으로 시작해요. 눌러서 고칠 수 있어요)")
        cap.setProperty("text_role", "sub")
        cap.setWordWrap(True)
        self.captions = QListWidget()
        self.captions.setObjectName("orderList")
        self.captions.setFixedHeight(150)
        self.photo_button = button("사진 대지 만들기")
        self.photo_button.setProperty("size", "panel")
        self.photo_button.clicked.connect(self._request_photo_sheet)
        self.photo_widgets = [cap, self.captions, self.photo_button]
        lay.addWidget(self.photo_info)
        lay.addLayout(counts)
        for w in self.photo_widgets:
            lay.addWidget(w)
        self._count_row = counts
        return body

    def _dividers_body(self) -> QWidget:
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 0, 0, 0)
        lay.setSpacing(6)
        self.divider_info = QLabel("")
        self.divider_info.setWordWrap(True)
        self.divider_rows = QVBoxLayout()
        self.divider_rows.setSpacing(4)
        note = QLabel("본문 장 간지는 한글에서 만들므로 hwp에서 온 쪽 앞에는 넣지 않아요.")
        note.setProperty("text_role", "sub")
        note.setWordWrap(True)
        self.divider_button = button("간지 넣기")
        self.divider_button.setProperty("size", "panel")
        self.divider_button.clicked.connect(self._request_dividers)
        lay.addWidget(self.divider_info)
        lay.addLayout(self.divider_rows)
        lay.addWidget(note)
        lay.addWidget(self.divider_button)
        self._divider_edits: list[tuple[QCheckBox, QLineEdit, int]] = []
        return body

    def _numbers_body(self) -> QWidget:
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 0, 0, 0)
        lay.setSpacing(6)
        self.numbers_on = QCheckBox("쪽번호 넣기")
        self.numbers_warning = QLabel("한글에서 넣은 쪽번호와 겹칠 수 있어요. 한글 보고서에 이미 쪽번호가 있다면 켜지 마세요.")
        self.numbers_warning.setObjectName("warningText")
        self.numbers_warning.setWordWrap(True)
        self.numbers_options = QWidget()
        opt = QVBoxLayout(self.numbers_options)
        opt.setContentsMargins(0, 0, 0, 0)
        opt.setSpacing(4)
        pos_label = QLabel("위치")
        pos_label.setProperty("text_role", "section")
        self.position_group = QButtonGroup(self)
        opt.addWidget(pos_label)
        for key, text in POSITIONS.items():
            radio = QRadioButton(text)
            radio.setProperty("key", key)
            radio.setChecked(key == "bottom_center")
            self.position_group.addButton(radio)
            opt.addWidget(radio)
        fmt_label = QLabel("형식")
        fmt_label.setProperty("text_role", "section")
        self.format_group = QButtonGroup(self)
        opt.addWidget(fmt_label)
        for key, text in FORMATS.items():
            radio = QRadioButton(text)
            radio.setProperty("key", key)
            radio.setChecked(key == "dash")
            self.format_group.addButton(radio)
            opt.addWidget(radio)
        self.skip_cover = QCheckBox("표지는 빼고 세기")
        self.skip_cover.setChecked(True)
        self.hide_dividers = QCheckBox("간지에는 번호 숨기기")
        self.hide_dividers.setChecked(True)
        opt.addWidget(self.skip_cover)
        opt.addWidget(self.hide_dividers)
        done = button("이대로 쓰기")
        done.setProperty("size", "panel")
        done.clicked.connect(lambda: self.step_done.emit("numbers"))
        lay.addWidget(self.numbers_on)
        lay.addWidget(self.numbers_warning)
        lay.addWidget(self.numbers_options)
        lay.addWidget(done)
        self.numbers_warning.hide()
        self.numbers_options.setEnabled(False)
        self.numbers_on.toggled.connect(self._numbers_changed)
        for group in (self.position_group, self.format_group):
            group.buttonToggled.connect(lambda *_: self._numbers_changed())
        for box in (self.skip_cover, self.hide_dividers):
            box.toggled.connect(lambda *_: self._numbers_changed())
        return body

    def _replace_body(self) -> QWidget:
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 0, 0, 0)
        lay.setSpacing(6)
        text = QLabel("원본 hwp에서 고친 뒤, 바꿀 쪽을 왼쪽 썸네일에서 고르고 아래 버튼을 누르세요. "
                      "원본 hwp의 같은 쪽만 다시 변환해 바꿔 끼워요.\n첨부 쪽은 원본 파일에서 고친 뒤 다시 넣어주세요.")
        text.setProperty("text_role", "sub")
        text.setWordWrap(True)
        self.replace_button = button("고른 쪽 교체", "replace")
        self.replace_button.setProperty("size", "panel")
        self.replace_button.clicked.connect(self.replace_requested)
        lay.addWidget(text)
        lay.addWidget(self.replace_button)
        return body

    # ================================================================ 채우기
    def set_presets(self, presets: dict[str, list[str]], current: str) -> None:
        self.preset_box.blockSignals(True)
        self.preset_box.clear()
        self.preset_box.addItems(list(presets))
        self.preset_box.setCurrentText(current)
        self.preset_box.blockSignals(False)
        self.order_list.clear()
        self.order_list.addItems(presets.get(current, arrange.DEFAULT_PRESET))

    def order(self) -> list[str]:
        return [self.order_list.item(i).text() for i in range(self.order_list.count())]

    def _move_item(self, step: int) -> None:
        row = self.order_list.currentRow()
        target = row + step
        if row < 0 or not (0 <= target < self.order_list.count()):
            return
        item = self.order_list.takeItem(row)
        self.order_list.insertItem(target, item)
        self.order_list.setCurrentRow(target)

    def refresh(self, document: PdfDocument | None, selected_count: int) -> None:
        """보고서가 바뀌면 단계 내용(사진 수, 첨부 묶음 등)과 상태를 다시 맞춘다."""
        self.document = document
        pages = document.pages if document else []
        # 사진
        photos = arrange.photo_indices(pages)
        self.photo_info.setText(f"사진 {len(photos)}장을 찾았어요. 한 쪽에 몇 장씩 넣을까요?" if photos
                                else "사진 쪽이 없어요. 이미 대지로 만들었다면 되돌리기로 다시 해볼 수 있어요.")
        for w in self.photo_widgets:
            w.setVisible(bool(photos))
        for b in self.per_page.buttons():
            b.setVisible(bool(photos))
        old = {self.captions.item(i).data(Qt.UserRole): self.captions.item(i).text()
               for i in range(self.captions.count())}
        self.captions.clear()
        for i in photos:
            ref = pages[i]
            caption = old.get(ref.uid, Path(ref.source.name).stem)
            self.captions.addItem(caption)
            item = self.captions.item(self.captions.count() - 1)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setData(Qt.UserRole, ref.uid)
        # 간지
        self._groups = arrange.attachment_groups(pages)
        while self.divider_rows.count():
            w = self.divider_rows.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._divider_edits = []
        for n, group in enumerate(self._groups, start=1):
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            check = QCheckBox()
            check.setChecked(True)
            title = arrange.divider_title(group.name) if group.kind != "사진대지" else "사진 대지"
            edit = QLineEdit(f"첨부 {n}. {title}")
            edit.setToolTip(f"{group.start + 1}쪽부터: {group.name}")
            lay.addWidget(check)
            lay.addWidget(edit, 1)
            self.divider_rows.addWidget(row)
            self._divider_edits.append((check, edit, group.start))
        self.divider_info.setText(f"첨부 묶음 {len(self._groups)}개를 찾았어요. 제목을 확인하세요." if self._groups
                                  else "간지를 넣을 첨부 묶음이 없어요.")
        self.divider_button.setVisible(bool(self._groups))
        # 쪽번호
        numbers = document.page_numbers if document else None
        self.numbers_on.blockSignals(True)
        self.numbers_on.setChecked(numbers is not None)
        self.numbers_on.blockSignals(False)
        self.numbers_options.setEnabled(numbers is not None)
        self.numbers_warning.setVisible(numbers is not None)
        # 교체
        self.replace_button.setEnabled(selected_count > 0)
        self._update_states()

    def _update_states(self) -> None:
        done = self.document.finish_done if self.document else set()
        current = next((key for key, *_ in STEPS if key not in done), None)
        for key, step in self.steps.items():
            step.set_state("done" if key in done else "current" if key == current else "todo")
        if self.open_key is None or self.open_key in done:
            self.open_key = current
        for key, step in self.steps.items():
            step.set_open(key == self.open_key)

    def _toggle(self, key: str) -> None:
        self.open_key = None if self.open_key == key else key
        for k, step in self.steps.items():
            step.set_open(k == self.open_key)

    # ================================================================ 요청
    def _request_photo_sheet(self) -> None:
        captions = [self.captions.item(i).text() for i in range(self.captions.count())]
        self.photo_sheet_requested.emit(self.per_page.checkedId(), captions)

    def _request_dividers(self) -> None:
        chosen = [(start, edit.text().strip()) for check, edit, start in self._divider_edits
                  if check.isChecked() and edit.text().strip()]
        if chosen:
            self.dividers_requested.emit(chosen)

    def _numbers_changed(self, *_) -> None:
        on = self.numbers_on.isChecked()
        self.numbers_options.setEnabled(on)
        self.numbers_warning.setVisible(on)
        if not on:
            self.page_numbers_changed.emit(None)
            return
        self.page_numbers_changed.emit(PageNumbers(
            position=self.position_group.checkedButton().property("key"),
            style=self.format_group.checkedButton().property("key"),
            skip_cover=self.skip_cover.isChecked(),
            hide_dividers=self.hide_dividers.isChecked()))
