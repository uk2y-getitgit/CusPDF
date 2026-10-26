"""글자 수정 패널 (오른쪽): 고른 글자·글꼴·크기·색상, 새 글자, 수정 전/후 미리보기, [취소] [적용] (5-4)."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout,
                               QWidget)

from app.pdf.fonts import font_choices
from app.pdf.text_edit import Selection
from app.ui.theme import SIZE
from app.ui.widgets import button

class NewTextBox(QLineEdit):
    escape_pressed = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.escape_pressed.emit()
            return
        super().keyPressEvent(event)


class TextEditPanel(QWidget):
    apply_requested = Signal()
    cancel_requested = Signal()
    preview_requested = Signal()   # 새 글자·글꼴이 바뀌어 미리보기를 다시 그려야 할 때

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedWidth(300)
        self.selection: Selection | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("글자 수정")
        title.setProperty("text_role", "title")
        self.hint = QLabel("고칠 글자 주위를 드래그해서 감싸세요. 한 줄 안에서만 고를 수 있어요.")
        self.hint.setProperty("text_role", "sub")
        self.hint.setWordWrap(True)

        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 8, 0, 0)
        body.setSpacing(8)

        self.original = QLabel("")
        self.original.setWordWrap(True)
        self.original.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.style_info = QLabel("")
        self.style_info.setProperty("text_role", "sub")
        self.style_info.setWordWrap(True)

        font_label = QLabel("넣을 글꼴")
        font_label.setProperty("text_role", "section")
        self.font_box = QComboBox()
        self.font_box.setMaxVisibleItems(20)
        self.font_warning = QLabel("")
        self.font_warning.setObjectName("warningText")
        self.font_warning.setWordWrap(True)
        self.remember_font = QCheckBox("다음에도 이 글꼴로 자동 연결")

        new_label = QLabel("새 글자")
        new_label.setProperty("text_role", "section")
        self.new_text = NewTextBox()
        self.new_text.setObjectName("newTextBox")
        self.new_text.setPlaceholderText("바꿀 글자를 입력하세요 (Enter: 적용)")
        self.new_text.setFixedHeight(SIZE["button"])

        preview_note = QLabel("수정 후 모습은 고칠 글자 바로 아래에 크게 떠요.")
        preview_note.setProperty("text_role", "sub")
        preview_note.setWordWrap(True)
        self.error = QLabel("")
        self.error.setObjectName("warningText")
        self.error.setWordWrap(True)

        buttons = QHBoxLayout()
        self.cancel_button = button("취소")
        self.apply_button = button("적용", tooltip="Enter")
        self.apply_button.setObjectName("applyButton")
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.apply_button, 1)

        for w in (self.original, self.style_info, font_label, self.font_box, self.font_warning,
                  self.remember_font, new_label, self.new_text, preview_note):
            body.addWidget(w)
        body.addWidget(self.error)
        body.addLayout(buttons)

        layout.addWidget(title)
        layout.addWidget(self.hint)
        layout.addWidget(self.body)
        layout.addStretch(1)
        self.body.hide()

        self._timer = QTimer(self, singleShot=True, interval=250, timeout=self.preview_requested.emit)
        self.new_text.textChanged.connect(lambda _: self._timer.start())
        self.font_box.currentIndexChanged.connect(lambda _: self._timer.start())
        self.new_text.returnPressed.connect(self.apply_requested)
        self.new_text.escape_pressed.connect(self.cancel_requested)
        self.apply_button.clicked.connect(self.apply_requested)
        self.cancel_button.clicked.connect(self.cancel_requested)
        self._fonts_loaded = False


    # ---------- 표시 ----------
    def reset(self, hint: str = "") -> None:
        self.selection = None
        self.body.hide()
        self.hint.setText(hint or "고칠 글자 주위를 드래그해서 감싸세요. 한 줄 안에서만 고를 수 있어요.")

    def show_selection(self, selection: Selection, font_path: str | None, note: str = "") -> None:
        self._load_fonts()
        self.selection = selection
        self.hint.setText(note or "새 글자를 입력하고 미리보기를 확인한 뒤 [적용]을 누르세요.")
        self.original.setText(selection.text)
        r, g, b = (round(c * 255) for c in selection.color)
        color = "검정" if max(r, g, b) < 30 else f"색 #{r:02X}{g:02X}{b:02X}"
        weight = "굵게" if selection.bold else "보통"
        name = selection.font.split("+", 1)[-1]
        self.style_info.setText(f"PDF 글꼴: {name} · {weight} · {selection.size:.1f}pt · {color}")
        self.font_box.blockSignals(True)
        if font_path:
            index = self.font_box.findData(font_path)
            if index < 0:
                self.font_box.insertItem(0, Path(font_path).stem, font_path)
                index = 0
            self.font_box.setCurrentIndex(index)
            self.font_warning.hide()
            self.remember_font.hide()
        else:
            self.font_warning.setText(f"'{name}' 글꼴을 이 PC에서 찾지 못했어요. 비슷한 글꼴을 골라주세요.")
            self.font_warning.show()
            self.remember_font.setChecked(True)
            self.remember_font.show()
        self.font_box.blockSignals(False)
        self.error.hide()
        self.new_text.setText(selection.text)
        self.new_text.selectAll()
        self.body.show()
        self.new_text.setFocus()
        self.preview_requested.emit()

    def _load_fonts(self) -> None:
        if self._fonts_loaded:
            return
        for name, path in font_choices():
            self.font_box.addItem(name, path)
        self._fonts_loaded = True

    def font_path(self) -> str | None:
        return self.font_box.currentData()

    def show_error(self, error: str = "") -> None:
        """적용할 수 없는 이유 (없으면 숨김). 미리보기 그림은 뷰어의 카드에 뜬다."""
        self.error.setText(error)
        self.error.setVisible(bool(error))
        self.apply_button.setEnabled(not error)
