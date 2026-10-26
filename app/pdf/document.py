"""편집 중인 보고서 한 건을 다룬다. 화면 코드는 pymupdf를 직접 쓰지 않고 이 파일을 거친다.

구조: 보고서 = 쪽 목록(PageRef). 각 쪽은 '어느 원본 PDF의 몇 번째 쪽을, 몇 도 더 돌려서' 쓰는지만 기억한다.
회전·삭제·순서 바꾸기·되돌리기는 이 목록만 바꾸므로 빠르고, 원본 파일은 절대 바뀌지 않는다.
실제 PDF는 저장할 때 한 번에 만든다 (CLAUDE.md 7-6 규칙 적용).
"""

import itertools
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

# 순서 주의: PySide6를 pymupdf보다 먼저 불러온다.
# pymupdf가 먼저 오면 윈도우의 오래된 C++ 런타임(msvcp140.dll)이 먼저 올라가
# PySide6가 그 위에서 실행되다 프로그램이 강제 종료된다.
from PySide6.QtCore import QRectF  # isort: skip
from PySide6.QtGui import QImage  # isort: skip
import pymupdf  # isort: skip

from app.pdf import text_edit  # noqa: E402
from app.pdf.generate import PageNumbers, stamp_page_numbers  # noqa: E402

A4 = (595.28, 841.89)  # pt

# 용지 크기 (세로 기준, pt = 1/72인치). B4·B5는 우리나라에서 쓰는 JIS 규격
PAPERS = {
    "A4": (595.28, 841.89),
    "A3": (841.89, 1190.55),
    "B4": (728.50, 1031.81),
    "B5": (515.91, 728.50),
    "Letter": (612.0, 792.0),
    "Legal": (612.0, 1008.0),
}


def paper_name(width: float, height: float) -> str:
    """크기로 용지 이름 찾기 (2% 안쪽이면 같은 용지로 본다)."""
    short, long_ = sorted((width, height))
    direction = "가로" if width > height else "세로"
    for name, (w, h) in PAPERS.items():
        if abs(short - w) / w < 0.02 and abs(long_ - h) / h < 0.02:
            return f"{name} {direction}"
    return f"{round(width / 72 * 25.4)}×{round(height / 72 * 25.4)}mm"


def _qrect(r: pymupdf.Rect) -> tuple[float, float, float, float]:
    r = r.normalize()
    return r.x0, r.y0, r.width, r.height


def _to_image(pix: pymupdf.Pixmap) -> QImage:
    return QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
_uid = itertools.count(1)


class OpenError(Exception):
    """PDF를 열 수 없을 때. 메시지는 사용자에게 그대로 보여줄 문장이다."""


@dataclass(eq=False)
class Source:
    """쪽을 가져오는 원본 PDF 하나 (메모리에 읽어 둔 복사본)."""
    doc: pymupdf.Document
    name: str               # 파일 이름 (예: 01_표지.hwp)
    kind: str               # 파일 종류 꼬리표: 본문/hwp/xlsx/docx/pdf/jpg/간지/사진대지
    path: Path | None = None  # 원래 파일 위치 (변환한 파일이면 변환 전 파일)
    origin_pages: list[int] | None = None  # 복사본 쪽 → 원래 파일의 몇 번째 쪽 (페이지 교체용)


@dataclass(frozen=True)
class PageRef:
    source: Source | None   # None이면 빈 쪽
    index: int = 0          # 원본에서 몇 번째 쪽인지 (0부터)
    rotation: int = 0       # 이 프로그램에서 더 돌린 각도 (0, 90, 180, 270)
    blank_size: tuple[float, float] = A4
    uid: int = field(default_factory=lambda: next(_uid))  # 같은 쪽을 두 번 넣어도 구별
    marks: tuple[tuple[float, float, float, float], ...] = ()  # 글자 수정한 곳 (회전 전 좌표, 화면 표시용)


def load_source(path: str | Path, kind: str, name: str | None = None,
                original: Path | None = None) -> Source:
    """PDF 파일을 메모리로 읽어 Source로 만든다. 원본 파일은 잠기지도, 바뀌지도 않는다."""
    path = Path(path)
    shown = name or path.name
    try:
        doc = pymupdf.open(stream=path.read_bytes(), filetype="pdf")
    except FileNotFoundError:
        raise OpenError(f"{shown} 파일을 찾을 수 없어요. 옮기거나 지웠는지 확인해주세요.")
    except PermissionError:
        raise OpenError(f"{shown} 파일을 읽을 수 없어요. 다른 프로그램에서 쓰고 있다면 닫고 다시 열어주세요.")
    except Exception:
        raise OpenError(f"{shown} 파일은 열 수 없는 PDF예요. 파일이 손상되었을 수 있어요. 원본에서 PDF를 다시 만들어주세요.")
    if doc.needs_pass:
        doc.close()
        raise OpenError(f"{shown} 파일은 암호가 걸린 PDF예요. 암호를 푼 PDF로 다시 열어주세요.")
    if doc.page_count == 0:
        doc.close()
        raise OpenError(f"{shown} 파일에는 쪽이 하나도 없어요.")
    return Source(doc, shown, kind, original or path)


class PdfDocument:
    def __init__(self, name: str = "새 보고서", path: Path | None = None):
        self.name = name
        self.path = path            # 처음 연 PDF (새 보고서면 None)
        self.pages: list[PageRef] = []
        self.sources: list[Source] = []
        self.modified = False
        self._undo: list[tuple[list[PageRef], str, bool]] = []
        self._redo: list[tuple[list[PageRef], str, bool]] = []
        self._group_depth = 0
        self._group_recorded = False
        self.page_numbers: PageNumbers | None = None   # 쪽번호 (기본은 꺼짐)
        self.finish_done: set[str] = set()             # 마무리 사이드바에서 끝낸 단계

    @classmethod
    def open(cls, path: str | Path) -> "PdfDocument":
        path = Path(path)
        source = load_source(path, "본문")
        document = cls(path.name, path)
        document.sources.append(source)
        document.pages = [PageRef(source, i) for i in range(source.doc.page_count)]
        return document

    # ---------- 쪽 정보 ----------
    @property
    def page_count(self) -> int:
        return len(self.pages)

    def kind(self, index: int) -> str:
        ref = self.pages[index]
        return ref.source.kind if ref.source else "빈 쪽"

    def source_name(self, index: int) -> str:
        ref = self.pages[index]
        return ref.source.name if ref.source else "빈 쪽"

    def page_key(self, index: int, view_rotation: int = 0) -> tuple:
        """그림 기억(캐시)용 이름. 같은 쪽·같은 방향이면 다시 그리지 않는다."""
        ref = self.pages[index]
        return ref.uid, ref.rotation, view_rotation

    def page_size(self, index: int, view_rotation: int = 0) -> tuple[float, float]:
        """보이는 방향 기준 쪽 크기 (pt, 1pt = 1/72인치)."""
        ref = self.pages[index]
        if ref.source:
            rect = ref.source.doc[ref.index].rect  # 원본의 회전이 이미 반영된 크기
            w, h = rect.width, rect.height
        else:
            w, h = ref.blank_size
        if (ref.rotation + view_rotation) % 180:
            w, h = h, w
        return w, h

    def render(self, index: int, scale: float, view_rotation: int = 0) -> QImage:
        """쪽을 그림으로 만든다. scale=1이면 1pt가 1픽셀."""
        ref = self.pages[index]
        if not ref.source:
            w, h = self.page_size(index, view_rotation)
            image = QImage(max(1, round(w * scale)), max(1, round(h * scale)), QImage.Format_RGB888)
            image.fill(0xFFFFFF)
            return image
        page = ref.source.doc[ref.index]
        matrix = pymupdf.Matrix(scale, scale).prerotate((ref.rotation + view_rotation) % 360)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        return image.copy()  # pix가 사라져도 그림이 남도록 복사

    def to_visible(self, index: int, view_rotation: int = 0) -> pymupdf.Matrix:
        """'회전 전' 쪽 좌표 → 화면에 보이는 방향의 좌표 (pt)."""
        ref = self.pages[index]
        page = ref.source.doc[ref.index]
        extra = pymupdf.Matrix((ref.rotation + view_rotation) % 360)
        box = page.rect * extra
        return page.rotation_matrix * extra * pymupdf.Matrix(1, 0, 0, 1, -box.x0, -box.y0)

    def search(self, text: str, view_rotation: int = 0) -> list[tuple[int, QRectF]]:
        """글자를 찾아 (쪽 번호, 보이는 방향 기준 위치 pt) 목록을 돌려준다."""
        results = []
        for i, ref in enumerate(self.pages):
            if not ref.source:
                continue
            hits = ref.source.doc[ref.index].search_for(text)
            if not hits:
                continue
            matrix = self.to_visible(i, view_rotation)  # 찾은 위치는 '회전 전' 기준
            for hit in hits:
                r = (hit * matrix).normalize()
                results.append((i, QRectF(r.x0, r.y0, r.width, r.height)))
        return results

    def edit_marks(self, index: int, view_rotation: int = 0) -> list[QRectF]:
        """글자 수정한 곳 (보이는 방향 기준 pt)."""
        ref = self.pages[index]
        if not ref.marks or not ref.source:
            return []
        matrix = self.to_visible(index, view_rotation)
        return [QRectF(*_qrect(pymupdf.Rect(m) * matrix)) for m in ref.marks]

    def original_page(self, index: int) -> int:
        """원래 파일에서 몇 번째 쪽인지 (페이지 교체용)."""
        ref = self.pages[index]
        if ref.source and ref.source.origin_pages:
            return ref.source.origin_pages[ref.index]
        return ref.index

    # ---------- 글자 수정 (2단계) ----------
    def pick_text(self, index: int, area: QRectF, view_rotation: int = 0):
        """화면에서 감싼 영역(보이는 방향 pt) 안의 글자를 고른다."""
        ref = self.pages[index]
        if not ref.source:
            return None
        back = ~self.to_visible(index, view_rotation)
        rect = pymupdf.Rect(area.left(), area.top(), area.right(), area.bottom()) * back
        return text_edit.pick(ref.source.doc[ref.index], rect.normalize())

    def _page_copy(self, index: int) -> Source:
        """쪽 하나를 새 문서로 복사한다. 고칠 때는 원본이 아니라 이 복사본을 고친다."""
        ref = self.pages[index]
        copy = pymupdf.open()
        copy.insert_pdf(ref.source.doc, from_page=ref.index, to_page=ref.index)
        return Source(copy, ref.source.name, ref.source.kind, ref.source.path, [self.original_page(index)])

    def visible_rect(self, index: int, rect, view_rotation: int = 0) -> QRectF:
        """'회전 전' 좌표의 영역 → 보이는 방향 pt."""
        return QRectF(*_qrect(pymupdf.Rect(rect) * self.to_visible(index, view_rotation)))

    def preview_text_edit(self, index: int, selection, new_text: str, font_path: str,
                          scale: float = 3.0) -> tuple[QImage, QImage | None, str]:
        """수정 전/후 미리보기 그림 (고른 글자 주변만)과, 적용할 수 없으면 그 이유."""
        ref = self.pages[index]
        clip = pymupdf.Rect(selection.rect) + (-40, -8, 40, 8)
        matrix = pymupdf.Matrix(scale, scale)
        before = _to_image(ref.source.doc[ref.index].get_pixmap(matrix=matrix, clip=clip, alpha=False))
        copy = self._page_copy(index)
        try:
            text_edit.apply(copy.doc[0], selection, new_text, font_path)
        except text_edit.EditError as error:
            return before, None, str(error)
        return before, _to_image(copy.doc[0].get_pixmap(matrix=matrix, clip=clip, alpha=False)), ""

    def apply_text_edit(self, index: int, selection, new_text: str, font_path: str) -> None:
        """글자를 고친다. 실패하면 EditError (보고서는 바뀌지 않음)."""
        ref = self.pages[index]
        copy = self._page_copy(index)
        text_edit.apply(copy.doc[0], selection, new_text, font_path)
        self._record(f"{index + 1}쪽 글자 수정")
        self.sources.append(copy)
        mark = tuple(selection.rect)
        self.pages[index] = PageRef(copy, 0, ref.rotation, marks=ref.marks + (mark,))

    # ---------- 마무리 (3단계) ----------
    def replace_page(self, index: int, source: Source, page: int, label: str = "페이지 교체") -> None:
        ref = self.pages[index]
        self._record(label)
        if source not in self.sources:
            self.sources.append(source)
        self.pages[index] = PageRef(source, page, ref.rotation)

    def insert_generated(self, doc: pymupdf.Document, kind: str, name: str, at: int) -> list[int]:
        source = Source(doc, name, kind)
        return self.insert_source(source, at)

    def replace_with(self, indices: list[int], doc: pymupdf.Document, kind: str, name: str,
                     label: str) -> list[int]:
        """indices 쪽들을 지우고 그 첫 자리에 새로 만든 쪽들을 넣는다 (예: 사진 대지)."""
        indices = sorted(indices)
        self._record(label)
        source = Source(doc, name, kind)
        self.sources.append(source)
        first = indices[0]
        drop = set(indices)
        kept = [p for i, p in enumerate(self.pages) if i not in drop]
        at = sum(1 for i in range(first) if i not in drop)
        new = [PageRef(source, i) for i in range(doc.page_count)]
        self.pages = kept[:at] + new + kept[at:]
        return list(range(at, at + len(new)))

    def reorder(self, pages: list[PageRef], label: str) -> None:
        if pages == self.pages:
            return
        self._record(label)
        self.pages = list(pages)

    def resize_pages(self, indices: list[int], paper: tuple[float, float], orientation: str = "keep",
                     label: str = "용지 크기 바꾸기") -> list[int]:
        """쪽들을 정한 용지 크기(세로 기준 pt)로 바꾼다. 내용은 비율을 지키며 새 용지 가운데에 맞춘다.
        orientation: keep(쪽마다 지금 방향 그대로) / portrait(세로) / landscape(가로).
        이미 그 크기인 쪽은 그대로 두고, 바꾼 쪽 번호들을 돌려준다."""
        short, long_ = sorted(paper)
        out = pymupdf.open()
        made: list[tuple[int, int]] = []           # (보고서 쪽 번호, 새 문서 쪽 번호)
        blanks: dict[int, tuple[float, float]] = {}
        for i in sorted(set(indices)):
            vis_w, vis_h = self.page_size(i)
            landscape = vis_w > vis_h if orientation == "keep" else orientation == "landscape"
            target_w, target_h = (long_, short) if landscape else (short, long_)
            if abs(vis_w - target_w) < 1 and abs(vis_h - target_h) < 1:
                continue
            ref = self.pages[i]
            if ref.source is None:                # 빈 쪽은 크기만 바꾼다
                blanks[i] = (target_w, target_h)
                continue
            src_page = ref.source.doc[ref.index]
            total = (src_page.rotation + ref.rotation) % 360
            # 회전 전 방향으로 새 쪽을 만들고, 내용을 회전 없이 맞춰 넣은 뒤 쪽 회전값만 원본과 같게
            raw_w, raw_h = (target_h, target_w) if total in (90, 270) else (target_w, target_h)
            page = out.new_page(width=raw_w, height=raw_h)
            page.show_pdf_page(page.rect, ref.source.doc, ref.index, keep_proportion=True)
            page.set_rotation(total)
            made.append((i, out.page_count - 1))
        changed = sorted([i for i, _ in made] + list(blanks))
        if not changed:
            return []
        self._record(label)
        if made:
            source = Source(out, "용지 크기", "", None, [self.original_page(i) for i, _ in made])
            self.sources.append(source)
        for i, k in made:
            ref = self.pages[i]
            source.kind, source.name, source.path = ref.source.kind, ref.source.name, ref.source.path
            self.pages[i] = PageRef(source, k)
        for i, size in blanks.items():
            self.pages[i] = replace(self.pages[i], blank_size=size, rotation=0)
        return changed

    def paper_summary(self, indices: list[int] | None = None) -> dict[str, int]:
        """용지 크기별 쪽 수 (예: {'A4 세로': 20, 'A3 가로': 3})."""
        result: dict[str, int] = {}
        for i in (indices if indices is not None else range(self.page_count)):
            name = paper_name(*self.page_size(i))
            result[name] = result.get(name, 0) + 1
        return result

    def set_page_numbers(self, numbers: "PageNumbers | None") -> None:
        self.page_numbers = numbers
        self.modified = True

    def kinds(self) -> list[str]:
        return [self.kind(i) for i in range(self.page_count)]

    # ---------- 되돌리기 ----------
    def _record(self, label: str) -> None:
        """바꾸기 직전 상태를 되돌리기 목록에 넣는다."""
        if self._group_depth and self._group_recorded:
            return
        self._undo.append((list(self.pages), label, self.modified))
        self._redo.clear()
        self._group_recorded = bool(self._group_depth)
        self.modified = True

    def begin_group(self) -> None:
        """여러 번 바꾼 것을 되돌리기 한 번으로 묶는다 (예: 파일 여러 개 넣기)."""
        self._group_depth += 1

    def end_group(self) -> None:
        self._group_depth = max(0, self._group_depth - 1)
        if not self._group_depth:
            self._group_recorded = False

    def rename_last_undo(self, label: str) -> None:
        if self._undo:
            pages, _, modified = self._undo[-1]
            self._undo[-1] = (pages, label, modified)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> str:
        pages, label, modified = self._undo.pop()
        self._redo.append((self.pages, label, self.modified))
        self.pages, self.modified = pages, modified
        return label

    def redo(self) -> str:
        pages, label, modified = self._redo.pop()
        self._undo.append((self.pages, label, self.modified))
        self.pages, self.modified = pages, modified
        return label

    # ---------- 편집 ----------
    def rotate(self, indices: list[int], angle: int = 90) -> None:
        self._record(f"{len(indices)}쪽 회전")
        for i in indices:
            ref = self.pages[i]
            self.pages[i] = replace(ref, rotation=(ref.rotation + angle) % 360)

    def delete(self, indices: list[int]) -> None:
        self._record(f"{len(indices)}쪽 삭제")
        drop = set(indices)
        self.pages = [p for i, p in enumerate(self.pages) if i not in drop]

    def move(self, indices: list[int], to: int) -> list[int]:
        """indices 쪽들을 to 위치(0~쪽 수, 그 쪽 앞)로 옮기고 옮긴 뒤 번호를 돌려준다."""
        indices = sorted(set(indices))
        moving = [self.pages[i] for i in indices]
        rest = [p for i, p in enumerate(self.pages) if i not in set(indices)]
        to -= sum(1 for i in indices if i < to)
        new_pages = rest[:to] + moving + rest[to:]
        if new_pages == self.pages:
            return indices
        self._record(f"{len(indices)}쪽 순서 변경")
        self.pages = new_pages
        return list(range(to, to + len(moving)))

    def insert_blank(self, at: int, size: tuple[float, float] = A4) -> int:
        self._record("빈 페이지 추가")
        self.pages.insert(at, PageRef(None, blank_size=size))
        return at

    def insert_source(self, source: Source, at: int, page_indices: list[int] | None = None) -> list[int]:
        """원본 PDF의 쪽들(기본: 전부)을 at 위치에 넣고 새 쪽 번호들을 돌려준다."""
        if page_indices is None:
            page_indices = list(range(source.doc.page_count))
        self._record(f"{source.name} {len(page_indices)}쪽 넣기")
        if source not in self.sources:
            self.sources.append(source)
        refs = [PageRef(source, i) for i in page_indices]
        self.pages[at:at] = refs
        return list(range(at, at + len(refs)))

    # ---------- 저장 ----------
    def original_paths(self) -> set[Path]:
        """이 보고서에 쓰인 원본 파일들. 이 이름으로는 저장하지 않는다."""
        paths = {s.path.resolve() for s in self.sources if s.path}
        if self.path:
            paths.add(self.path.resolve())
        return paths

    def save(self, path: str | Path) -> None:
        """새 PDF 파일로 저장한다 (CLAUDE.md 7-6). 원본 덮어쓰기·증분 저장은 하지 않는다."""
        path = Path(path)
        out = pymupdf.open()
        # 같은 원본에서 이어지는 쪽은 한 번에 복사해 빠르게
        for (source, _), run in itertools.groupby(
                enumerate(self.pages), key=lambda item: (item[1].source, item[0] - item[1].index)):
            run = [ref for _, ref in run]
            start = out.page_count
            if source is None:
                for ref in run:
                    w, h = ref.blank_size
                    out.new_page(width=w, height=h)
            else:
                out.insert_pdf(source.doc, from_page=run[0].index, to_page=run[-1].index)
            for offset, ref in enumerate(run):
                if ref.rotation:
                    page = out[start + offset]
                    page.set_rotation((page.rotation + ref.rotation) % 360)
        if self.page_numbers:
            stamp_page_numbers(out, self.page_numbers, self.kinds())
        try:
            out.subset_fonts()  # 새로 넣은 글자의 글꼴만 필요한 글자로 줄인다
        except Exception:
            pass
        # 같은 폴더에 임시 이름으로 다 쓴 뒤 바꿔 달아, 저장 중 문제가 생겨도 반쪽 파일이 남지 않게
        temp = path.with_name(f".{path.stem}.saving.pdf")
        try:
            out.save(temp, garbage=4, deflate=True, clean=True)
            out.close()
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()
        self.modified = False
        # 저장한 상태에서 되돌리기를 하면 다시 '변경 있음'이 되도록
        self._undo = [(p, label, True) for p, label, _ in self._undo]
        self._redo = [(p, label, True) for p, label, _ in self._redo]

    def close(self) -> None:
        """연결만 끊는다. 원본 PDF는 옆 창 등에서 같이 쓸 수 있어 직접 닫지 않고,
        아무도 쓰지 않게 되면 파이썬이 알아서 메모리를 정리한다."""
        self.pages = []
        self.sources = []
        self._undo.clear()
        self._redo.clear()
