"""덮어쓰기 방식 글자 수정 (CLAUDE.md 2단계, 7-6, 7-7).

1. 드래그한 영역에서 한 줄 안의 글자를 고른다 (여러 줄이면 첫 줄만).
2. 원래 글자의 글꼴·크기·색상을 읽는다.
3. 원래 글자만 지우고(표 선·배경·그림은 보존) 같은 자리에 새 글자를 PC 글꼴로 넣는다.
4. 고친 뒤 원래 글자가 사라졌는지, 옆 글자가 지워지지 않았는지 확인한다.
좌표는 모두 '회전 전' 쪽 좌표다 (get_text·리댁션·insert_text가 같은 좌표계를 쓴다).
"""

import math
from dataclasses import dataclass

import PySide6.QtCore  # isort: skip  # noqa: F401  pymupdf보다 먼저 (document.py 설명 참고)
import pymupdf  # isort: skip

MIN_SCALE = 0.8     # 자리가 조금 모자라면 글자 폭을 이만큼까지 좁혀 맞춘다 (한글의 장평처럼)


class EditError(Exception):
    """수정할 수 없을 때. 메시지는 사용자에게 그대로 보여줄 문장이다."""


@dataclass
class Selection:
    text: str
    rect: pymupdf.Rect          # 고른 글자들을 감싸는 영역
    origin: pymupdf.Point       # 첫 글자의 기준점 (글자를 놓을 자리)
    font: str                   # PDF 안 글꼴 이름
    size: float
    color: tuple[float, float, float]
    bold: bool
    angle: int                  # 글자 방향 (0, 90, 180, 270)
    line_text: str              # 같은 줄 전체 글자 (확인용)
    multiline: bool             # 여러 줄을 감쌌는지 (첫 줄만 골랐음)
    room: float                 # 첫 글자부터 다음 글자(또는 쪽 끝 여백)까지 쓸 수 있는 폭


def pick(page: pymupdf.Page, area: pymupdf.Rect) -> Selection | None:
    """area 안에 가운데가 들어오는 글자들을 줄 단위로 모아 첫 줄을 고른다."""
    lines = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            chosen, spans, rest = [], [], []
            for span in line["spans"]:
                for char in span["chars"]:
                    box = pymupdf.Rect(char["bbox"])
                    center = pymupdf.Point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
                    if center in area:
                        chosen.append(char)
                        spans.append(span)
                    else:
                        rest.append(char)
            if chosen:
                full = "".join(c["c"] for s in line["spans"] for c in s["chars"])
                lines.append((line, chosen, spans[0], full, rest))
    if not lines:
        return None
    lines.sort(key=lambda item: (round(item[0]["bbox"][1]), item[0]["bbox"][0]))
    line, chars, span, full, rest = lines[0]
    text = "".join(c["c"] for c in chars).strip()
    if not text:
        return None
    chars = [c for c in chars if c["c"].strip()] or chars
    rect = pymupdf.Rect(chars[0]["bbox"])
    for char in chars[1:]:
        rect |= pymupdf.Rect(char["bbox"])
    color_int = span["color"]
    color = (((color_int >> 16) & 255) / 255, ((color_int >> 8) & 255) / 255, (color_int & 255) / 255)
    dx, dy = line["dir"]
    angle = round(math.degrees(math.atan2(-dy, dx)) / 90) * 90 % 360
    origin = pymupdf.Point(chars[0]["origin"])
    if angle == 0:
        # 쓸 수 있는 폭: 고른 글자 뒤 같은 줄의 다음 글자 앞까지 (없으면 쪽 오른쪽 여백까지)
        after = [pymupdf.Rect(c["bbox"]).x0 for c in rest
                 if c["c"].strip() and pymupdf.Rect(c["bbox"]).x0 >= rect.x1 - 0.5]
        room = (min(after) - 0.8 if after else page.rect.x1 - 28) - origin.x
    else:
        room = max(rect.width, rect.height) * 1.2
    return Selection(
        text=text, rect=rect, origin=origin,
        font=span["font"], size=span["size"], color=color,
        bold=bool(span["flags"] & 16) or "bold" in span["font"].lower(),
        angle=angle, line_text=full, multiline=len(lines) > 1, room=max(room, rect.width))


def text_width(text: str, font_path: str, size: float) -> float:
    return pymupdf.Font(fontfile=font_path).text_length(text, fontsize=size)


def check(selection: Selection, new_text: str, font_path: str) -> float:
    """적용 전에 막아야 할 경우를 확인하고, 글자 폭 비율(1이면 그대로, 1보다 작으면 좁혀 넣기)을 돌려준다."""
    if not new_text.strip():
        raise EditError("새 글자를 입력해주세요. 글자를 지우기만 하려면 공백 한 칸을 넣지 말고 원본 hwp에서 고쳐주세요.")
    font = pymupdf.Font(fontfile=font_path)
    missing = sorted({ch for ch in new_text if not ch.isspace() and not font.has_glyph(ord(ch))})
    if missing:
        raise EditError(f"고른 글꼴에 '{''.join(missing)}' 글자가 없어요. 다른 글꼴을 골라주세요.")
    new = font.text_length(new_text, fontsize=selection.size)
    if new <= selection.room:
        return 1.0
    if new * MIN_SCALE <= selection.room and selection.angle == 0:
        return selection.room / new
    raise EditError("새 글자가 원래 자리보다 많이 길어서 옆 글자와 겹쳐요. "
                    "원본 hwp에서 고친 뒤 [페이지 교체]를 써주세요.")


def apply(page: pymupdf.Page, selection: Selection, new_text: str, font_path: str) -> None:
    """page(복사본)에서 글자를 바꾼다. 실패하면 EditError — 그 복사본은 버리면 된다."""
    scale = check(selection, new_text, font_path)
    before = _line_text_at(page, selection.rect)
    # 원래 글자만 지운다: 옆 글자를 건드리지 않게 영역을 살짝 줄이고, 배경·표 선·그림은 남긴다
    inset = min(selection.rect.width, selection.rect.height) * 0.15
    area = pymupdf.Rect(selection.rect)
    if selection.angle in (0, 180):
        area = pymupdf.Rect(area.x0 + 0.3, area.y0 + inset, area.x1 - 0.3, area.y1 - inset)
    else:
        area = pymupdf.Rect(area.x0 + inset, area.y0 + 0.3, area.x1 - inset, area.y1 - 0.3)
    page.add_redact_annot(area, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    after = _line_text_at(page, selection.rect)
    # 지운 결과 확인: 같은 줄에서 고른 글자만 빠졌는지
    squeeze = lambda s: s.replace(" ", "")  # noqa: E731
    expected = squeeze(before.replace(selection.text, "", 1))
    if squeeze(after) != expected:
        if squeeze(after).count(squeeze(selection.text)) >= squeeze(before).count(squeeze(selection.text)):
            raise EditError("원래 글자를 지우지 못했어요. 이 쪽은 글자가 그림으로 되어 있을 수 있어요.")
        raise EditError("고른 글자 옆의 글자까지 지워질 수 있어서 멈췄어요. 고칠 글자만 조금 더 좁게 감싸 주세요.")
    # 자리가 조금 모자라면 글자 폭만 좁혀(기준점 고정) 옆 글자와 겹치지 않게
    morph = (selection.origin, pymupdf.Matrix(scale, 1)) if scale < 1 else None
    page.insert_text(selection.origin, new_text, fontsize=selection.size, fontname="kr_edit",
                     fontfile=font_path, color=selection.color, rotate=selection.angle, morph=morph)


def _line_text_at(page: pymupdf.Page, rect: pymupdf.Rect) -> str:
    """rect와 같은 줄(가로 글자) 또는 같은 열(세로 글자)에 있는 글자들. 가운데가 띠 안에 있는 글자만 센다."""
    vertical = rect.height > rect.width * 3 and rect.width < 30
    chars = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                for char in span["chars"]:
                    box = pymupdf.Rect(char["bbox"])
                    if vertical:
                        inside = rect.x0 <= (box.x0 + box.x1) / 2 <= rect.x1
                    else:
                        inside = rect.y0 <= (box.y0 + box.y1) / 2 <= rect.y1
                    if inside:
                        chars.append((box.y0 if vertical else box.x0, char["c"]))
    return "".join(c for _, c in sorted(chars))
