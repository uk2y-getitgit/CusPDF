"""새 쪽 만들기와 쪽번호 (CLAUDE.md 3단계, 7-6).

- 간지: "첨부 1. ○○" 한 쪽
- 사진 대지: 사진 쪽들을 한 쪽에 2·4·6장씩 표 형태로 배치하고 캡션을 단다.
  사진은 원래 쪽의 그림을 그대로 옮겨 놓아(show_pdf_page) 다시 압축하지 않는다.
- 쪽번호: 저장할 때 찍는다. 회전된 쪽도 '보이는 방향' 기준 위치에 찍는다.
새 글자는 TrueType 글꼴을 PDF 안에 포함한다 (저장 직전 subset_fonts로 필요한 글자만 남김).
"""

from dataclasses import dataclass

import PySide6.QtCore  # isort: skip  # noqa: F401  pymupdf보다 먼저 (document.py 설명 참고)
import pymupdf  # isort: skip

from app.pdf.fonts import generated_font

A4_W, A4_H = 595.28, 841.89
MARGIN = 42.5           # 15mm
LINE = (0.35, 0.38, 0.42)

POSITIONS = {"bottom_center": "아래 가운데", "bottom_right": "아래 오른쪽", "top_right": "위 오른쪽"}
FORMATS = {"dash": "- 1 -", "plain": "1", "total": "1 / 전체"}


# ---------------------------------------------------------------- 간지
def divider_pdf(title: str) -> pymupdf.Document:
    doc = pymupdf.open()
    page = doc.new_page(width=A4_W, height=A4_H)
    box = pymupdf.Rect(MARGIN * 2, A4_H * 0.40, A4_W - MARGIN * 2, A4_H * 0.40 + 120)
    font = generated_font(bold=True)
    # 길면 글자 크기를 줄여 상자 안에 넣는다 (넘치면 아무것도 쓰지 않고 음수를 돌려준다)
    for size in (24, 20, 16, 13):
        if page.insert_textbox(box, title, fontsize=size, fontname="kr_divider",
                               fontfile=font, align=pymupdf.TEXT_ALIGN_CENTER) >= 0:
            break
    return doc


# ---------------------------------------------------------------- 사진 대지
@dataclass
class Photo:
    doc: pymupdf.Document
    index: int          # 원본 문서에서 사진이 있는 쪽
    rotation: int       # 프로그램에서 더 돌린 각도
    caption: str


GRID = {2: (1, 2), 4: (2, 2), 6: (2, 3)}   # 한 쪽 사진 수 → (열, 줄)
CAPTION_H = 26


def photo_sheet_pdf(photos: list[Photo], per_page: int) -> pymupdf.Document:
    cols, rows = GRID[per_page]
    doc = pymupdf.open()
    font = generated_font()
    cell_w = (A4_W - 2 * MARGIN) / cols
    cell_h = (A4_H - 2 * MARGIN) / rows
    for start in range(0, len(photos), per_page):
        page = doc.new_page(width=A4_W, height=A4_H)
        for n, photo in enumerate(photos[start:start + per_page]):
            r, c = divmod(n, cols)
            cell = pymupdf.Rect(MARGIN + c * cell_w, MARGIN + r * cell_h,
                                MARGIN + (c + 1) * cell_w, MARGIN + (r + 1) * cell_h)
            picture = pymupdf.Rect(cell.x0, cell.y0, cell.x1, cell.y1 - CAPTION_H)
            caption = pymupdf.Rect(cell.x0, cell.y1 - CAPTION_H, cell.x1, cell.y1)
            page.draw_rect(cell, color=LINE, width=0.8)
            page.draw_line(caption.top_left, caption.top_right, color=LINE, width=0.8)
            src_page = photo.doc[photo.index]
            clip = _picture_area(src_page)
            page.show_pdf_page(picture + (4, 4, -4, -4), photo.doc, photo.index, clip=clip,
                               rotate=-photo.rotation, keep_proportion=True)
            page.insert_textbox(caption + (4, 6, -4, 0), photo.caption, fontsize=10, fontname="kr_caption",
                                fontfile=font, align=pymupdf.TEXT_ALIGN_CENTER)
    return doc


def _picture_area(page: pymupdf.Page) -> pymupdf.Rect:
    """사진 쪽에서 사진이 놓인 영역 (여백을 빼고 사진만 가져오기 위해)."""
    area = None
    for info in page.get_image_info():
        box = pymupdf.Rect(info["bbox"])
        area = box if area is None else area | box
    return area if area is not None else page.rect


# ---------------------------------------------------------------- 쪽번호
@dataclass
class PageNumbers:
    position: str = "bottom_center"
    style: str = "dash"
    skip_cover: bool = True
    hide_dividers: bool = True

    def labels(self, kinds: list[str]) -> list[str | None]:
        """쪽마다 찍을 글자 (찍지 않는 쪽은 None). 표지는 세지 않고, 간지는 세되 숨긴다."""
        counted = [i for i in range(len(kinds)) if not (self.skip_cover and i == 0)]
        total = len(counted)
        result: list[str | None] = [None] * len(kinds)
        for number, i in enumerate(counted, start=1):
            if self.hide_dividers and kinds[i] == "간지":
                continue
            result[i] = {"dash": f"- {number} -", "plain": f"{number}", "total": f"{number} / {total}"}[self.style]
        return result

    def anchor(self, width: float, height: float, text_w: float, size: float) -> tuple[float, float]:
        """보이는 방향 기준 글자 시작 위치 (왼쪽 아래 기준점)."""
        if self.position == "top_right":
            return width - 40 - text_w, 32 + size
        if self.position == "bottom_right":
            return width - 40 - text_w, height - 28
        return (width - text_w) / 2, height - 28


NUMBER_SIZE = 10


def stamp_page_numbers(doc: pymupdf.Document, numbers: PageNumbers, kinds: list[str]) -> None:
    font_path = generated_font(serif=True)
    font = pymupdf.Font(fontfile=font_path)
    for page, label in zip(doc, numbers.labels(kinds)):
        if not label:
            continue
        w = font.text_length(label, fontsize=NUMBER_SIZE)
        visible = page.rect  # 회전이 반영된 보이는 크기
        x, y = numbers.anchor(visible.width, visible.height, w, NUMBER_SIZE)
        point = pymupdf.Point(x, y) * page.derotation_matrix
        page.insert_text(point, label, fontsize=NUMBER_SIZE, fontname="kr_pageno", fontfile=font_path,
                         rotate=page.rotation, color=(0, 0, 0))
