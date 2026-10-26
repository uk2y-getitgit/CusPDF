"""작은 설정 창들."""

from pathlib import Path

from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QRadioButton, QVBoxLayout)

from app.pdf.document import PAPERS
from app.ui.widgets import button


class PaperDialog(QDialog):
    """용지 크기 맞추기: 모든 쪽 또는 선택한 쪽을 A4·A3 등으로. 내용은 비율을 지키며 새 용지에 맞춘다."""

    def __init__(self, summary_all: dict[str, int], summary_selected: dict[str, int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("용지 크기 맞추기")
        self.setMinimumWidth(420)
        self._summaries = {"all": summary_all, "selected": summary_selected}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(8)

        def heading(text: str) -> QLabel:
            label = QLabel(text)
            label.setProperty("text_role", "section")
            return label

        self.target = QButtonGroup(self)
        all_count, sel_count = sum(summary_all.values()), sum(summary_selected.values())
        self.all_radio = QRadioButton(f"모든 쪽 ({all_count}쪽)")
        self.sel_radio = QRadioButton(f"선택한 쪽 ({sel_count}쪽)")
        self.sel_radio.setEnabled(sel_count > 0)
        (self.sel_radio if sel_count else self.all_radio).setChecked(True)
        for radio in (self.all_radio, self.sel_radio):
            self.target.addButton(radio)
        self.current = QLabel("")
        self.current.setProperty("text_role", "sub")
        self.current.setWordWrap(True)

        self.paper = QComboBox()
        for name, (w, h) in PAPERS.items():
            self.paper.addItem(f"{name}  ({round(w / 72 * 25.4)}×{round(h / 72 * 25.4)}mm)", name)

        self.orientation = QButtonGroup(self)
        options = (("keep", "쪽마다 지금 방향 그대로 (세로는 세로, 가로는 가로)"),
                   ("portrait", "모두 세로"), ("landscape", "모두 가로"))
        radios = []
        for key, text in options:
            radio = QRadioButton(text)
            radio.setProperty("key", key)
            radio.setChecked(key == "keep")
            self.orientation.addButton(radio)
            radios.append(radio)

        note = QLabel("내용은 비율을 지키며 새 용지에 맞춰 줄이거나 키워요. 이미 그 크기인 쪽은 그대로 둬요.\n"
                      "원본 파일은 바뀌지 않고, 되돌리기(Ctrl+Z)로 돌릴 수 있어요.")
        note.setProperty("text_role", "sub")
        note.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("바꾸기")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(heading("대상"))
        layout.addWidget(self.all_radio)
        layout.addWidget(self.sel_radio)
        layout.addWidget(self.current)
        layout.addSpacing(4)
        layout.addWidget(heading("용지"))
        layout.addWidget(self.paper)
        layout.addSpacing(4)
        layout.addWidget(heading("방향"))
        for radio in radios:
            layout.addWidget(radio)
        layout.addSpacing(4)
        layout.addWidget(note)
        layout.addWidget(buttons)
        self.target.buttonToggled.connect(lambda *_: self._show_current())
        self._show_current()

    def _show_current(self) -> None:
        summary = self._summaries["selected" if self.sel_radio.isChecked() else "all"]
        text = " · ".join(f"{name} {count}쪽" for name, count in sorted(summary.items(), key=lambda x: -x[1]))
        self.current.setText(f"지금 용지: {text}" if text else "")

    def choice(self) -> tuple[bool, str, str]:
        """(선택한 쪽만인지, 용지 이름, 방향)"""
        return (self.sel_radio.isChecked(), self.paper.currentData(),
                self.orientation.checkedButton().property("key"))


class FontMapDialog(QDialog):
    """글꼴 연결표: PDF 안 글꼴 이름 → PC 글꼴 파일. 글자 수정에서 '다음에도 자동 연결'로 쌓인다."""

    def __init__(self, font_map: dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("글꼴 연결표")
        self.setMinimumSize(460, 360)
        self.font_map = dict(font_map)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(8)
        lead = QLabel("글자 수정에서 PDF 글꼴을 PC에서 찾지 못해 직접 고른 글꼴이 여기에 저장돼요.\n"
                      "이름이 같은 글꼴은 자동으로 찾으므로 여기에 없어도 돼요.")
        lead.setProperty("text_role", "sub")
        lead.setWordWrap(True)
        self.list = QListWidget()
        self.list.setObjectName("orderList")
        for pdf_font, path in sorted(self.font_map.items()):
            item = QListWidgetItem(f"{pdf_font}  →  {Path(path).stem}")
            item.setData(256, pdf_font)
            item.setToolTip(path)
            self.list.addItem(item)
        if not self.font_map:
            self.list.addItem("아직 저장한 연결이 없어요")
        remove = button("고른 연결 지우기", "trash")
        remove.setProperty("size", "panel")
        remove.clicked.connect(self._remove)
        remove.setEnabled(bool(self.font_map))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("확인")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(remove)
        row.addStretch(1)
        layout.addWidget(lead)
        layout.addWidget(self.list, 1)
        layout.addLayout(row)
        layout.addWidget(buttons)

    def _remove(self) -> None:
        item = self.list.currentItem()
        key = item.data(256) if item else None
        if key:
            self.font_map.pop(key, None)
            self.list.takeItem(self.list.row(item))
