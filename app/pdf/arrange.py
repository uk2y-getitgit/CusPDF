"""마무리 사이드바의 정리 규칙: 순서 프리셋 정렬, 첨부 묶음 찾기, 사진 쪽 찾기 (CLAUDE.md 3단계).

묶음 = 같은 파일에서 온 연속된 쪽들. 빈 쪽은 앞 묶음에 붙고, 간지는 바로 뒤 묶음과 함께 움직인다.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.convert.order import leading_number
from app.pdf.document import PageRef

# 프리셋에서 고르는 종류 (보이는 이름 → 파일 종류들)
CATEGORIES = {
    "본문": ("본문", "hwp"),
    "엑셀": ("xlsx",),
    "워드": ("docx",),
    "PDF": ("pdf",),
    "사진": ("jpg", "사진대지"),
}
DEFAULT_PRESET = ["본문", "엑셀", "워드", "PDF", "사진"]
ATTACHMENT_KINDS = ("xlsx", "docx", "pdf", "jpg", "사진대지")


def category_of(kind: str) -> str:
    for name, kinds in CATEGORIES.items():
        if kind in kinds:
            return name
    return "본문"


@dataclass
class Group:
    pages: list[PageRef] = field(default_factory=list)
    start: int = 0          # 보고서에서 첫 쪽 번호
    kind: str = ""          # 대표 파일 종류 (간지가 앞에 붙어도 뒤 묶음의 종류)
    name: str = ""          # 대표 파일 이름
    has_divider: bool = False


def groups_of(pages: list[PageRef], attach_dividers: bool = True) -> list[Group]:
    groups: list[Group] = []
    pending_divider: list[PageRef] = []
    for i, ref in enumerate(pages):
        kind = ref.source.kind if ref.source else "빈 쪽"
        if ref.source is None and groups and not pending_divider:
            groups[-1].pages.append(ref)          # 빈 쪽은 앞 묶음에
            continue
        if kind == "간지" and attach_dividers:
            pending_divider.append(ref)           # 간지는 다음 묶음 앞에
            continue
        if groups and not pending_divider and groups[-1].pages[-1].source is ref.source:
            groups[-1].pages.append(ref)
            continue
        group = Group(pages=pending_divider + [ref], start=i - len(pending_divider), kind=kind,
                      name=ref.source.name if ref.source else "", has_divider=bool(pending_divider))
        pending_divider = []
        groups.append(group)
    if pending_divider:  # 맨 끝에 남은 간지
        groups.append(Group(pages=pending_divider, start=len(pages) - len(pending_divider), kind="간지"))
    return groups


def sort_by_preset(pages: list[PageRef], preset: list[str]) -> list[PageRef]:
    """프리셋의 종류 순서대로, 같은 종류 안에서는 파일 이름 번호 순으로."""
    order = {name: n for n, name in enumerate(preset)}

    def key(item: tuple[int, Group]):
        position, group = item
        number = leading_number(Path(group.name)) if group.name else None
        return (order.get(category_of(group.kind), len(order)),
                0 if number is not None else 1, number or 0, group.name.casefold(), position)

    ordered = sorted(enumerate(groups_of(pages)), key=key)
    return [ref for _, group in ordered for ref in group.pages]


def attachment_groups(pages: list[PageRef]) -> list[Group]:
    """간지를 넣을 첨부 묶음들. 본문(hwp에서 온 쪽 포함)과 이미 간지가 있는 묶음은 뺀다."""
    return [g for g in groups_of(pages) if g.kind in ATTACHMENT_KINDS and not g.has_divider]


def divider_title(name: str) -> str:
    """'10_측정데이터.xlsx' → '측정데이터'"""
    stem = Path(name).stem
    return re.sub(r"^\s*\d+[_\-. ]+", "", stem) or stem


def photo_indices(pages: list[PageRef]) -> list[int]:
    return [i for i, ref in enumerate(pages) if ref.source and ref.source.kind == "jpg"]
