"""끌어다 놓은 내용에서 넣을 파일을 찾아낸다.

- 탐색기에서 끈 파일: 파일 경로
- 다른 PDF 리더기(ezPDF, 알PDF, Acrobat 등)에서 쪽을 끈 경우: 리더기마다 넘겨주는 방식이 다르다.
  · 가상 파일(FileGroupDescriptorW + FileContents): 이름과 PDF 내용을 넘긴다
  · PDF 내용 자체(%PDF로 시작하는 데이터)
  · 임시 PDF 파일 경로
  위 방식들을 모두 시도하고, 못 읽으면 어떤 형식이 왔는지 기록(drop_log.txt)을 남겨 나중에 맞출 수 있게 한다.
"""

import datetime
import os
import shutil
import struct
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QMimeData

from app.ui.ezpdf_source import EzpdfDrag, find_drag_source, is_ezpdf, remember_foreground  # noqa: F401

LOG_PATH = Path(os.environ.get("APPDATA", Path.home())) / "CusPDF" / "drop_log.txt"
_OUR_FORMATS = ("application/x-cuspdf-pages", "application/x-cuspdf-side")


@dataclass
class DropContent:
    paths: list[Path] = field(default_factory=list)   # 넣을 파일들 (리더기에서 온 쪽은 임시 PDF로 저장됨)
    from_reader: bool = False                          # 다른 리더기에서 끌어온 쪽인지
    formats: list[str] = field(default_factory=list)
    ezpdf: EzpdfDrag | None = None                     # ezPDF에서 끌어온 쪽 (파일·쪽을 따로 알아냄)


def has_droppable(mime: QMimeData) -> bool:
    """받을 만한 내용이 있는지 (우리 프로그램 내부 끌기는 따로 처리)."""
    return any(f not in _OUR_FORMATS for f in mime.formats())


def read_drop(mime: QMimeData) -> DropContent:
    content = DropContent(formats=list(mime.formats()))
    # 0) ezPDF: 넘겨주는 값으로는 알 수 없어, 끌기를 시작한 ezPDF 창에서 파일과 보던 쪽을 알아낸다
    if is_ezpdf(content.formats):
        content.ezpdf = find_drag_source()
        content.from_reader = True
        if not (content.ezpdf and content.ezpdf.path):
            _log(mime, note=f"ezPDF 출처: {content.ezpdf}")
        return content
    # 1) 탐색기 파일
    if mime.hasUrls():
        content.paths = [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile()]
        if content.paths:
            return content
    # 2) 가상 파일 (이름 + 내용)
    names = _virtual_names(mime)
    data = _format_data(mime, "FileContents")
    if data and data.startswith(b"%PDF"):
        name = names[0] if names else "끌어온 쪽.pdf"
        content.paths = [_save_temp(name, data)]
        content.from_reader = True
        return content
    # 3) 어떤 형식이든 PDF 내용이나 PDF 파일 경로가 들어 있으면 사용
    for fmt in mime.formats():
        if fmt in _OUR_FORMATS:
            continue
        raw = bytes(mime.data(fmt))
        if raw.startswith(b"%PDF"):
            content.paths = [_save_temp("끌어온 쪽.pdf", raw)]
            content.from_reader = True
            return content
        path = _path_in(raw)
        if path:
            content.paths = [path]
            content.from_reader = True
            return content
    _log(mime)
    return content


def _format_data(mime: QMimeData, windows_name: str) -> bytes:
    for fmt in mime.formats():
        if windows_name in fmt:
            return bytes(mime.data(fmt))
    return b""


def _virtual_names(mime: QMimeData) -> list[str]:
    """FileGroupDescriptorW에서 파일 이름들을 읽는다."""
    raw = _format_data(mime, "FileGroupDescriptorW")
    if len(raw) < 4:
        return []
    count = struct.unpack_from("<I", raw, 0)[0]
    names, size, offset = [], 592, 4  # FILEDESCRIPTORW 하나의 크기, 이름은 72바이트 뒤 520바이트
    for i in range(count):
        start = offset + i * size + 72
        chunk = raw[start:start + 520]
        if len(chunk) < 520:
            break
        names.append(chunk.decode("utf-16-le").split("\x00", 1)[0])
    return [n for n in names if n]


def _path_in(raw: bytes) -> Path | None:
    """데이터 안에 실제로 있는 PDF 파일 경로가 적혀 있으면 돌려준다."""
    for encoding in ("utf-16-le", "utf-8", "cp949"):
        try:
            text = raw.decode(encoding).strip("\x00").strip()
        except UnicodeDecodeError:
            continue
        for line in text.splitlines():
            line = line.strip().strip('"').strip("\x00")
            if line.lower().startswith("file:///"):
                line = line[8:].replace("/", "\\")
            if line.lower().endswith(".pdf") and len(line) < 400:
                try:
                    path = Path(line)
                    if path.is_file():
                        return path
                except OSError:
                    pass
    return None


TEMP_DIR = Path(tempfile.gettempdir()) / "CusPDF_drops"


def cleanup_temp() -> None:
    """지난번에 끌어 놓으며 만든 임시 PDF를 지운다 (내용은 이미 보고서 안에 읽어 둔 상태)."""
    shutil.rmtree(TEMP_DIR, ignore_errors=True)


def _save_temp(name: str, data: bytes) -> Path:
    # 놓을 때마다 새 폴더를 만들어, 파일 이름은 원래 이름 그대로 둔다 (썸네일·안내 문구에 보이는 이름)
    folder = TEMP_DIR / f"{datetime.datetime.now():%H%M%S%f}"
    folder.mkdir(parents=True, exist_ok=True)
    stem = Path(name).stem or "끌어온 쪽"
    path = folder / f"{stem}.pdf"
    path.write_bytes(data)
    return path


def _log(mime: QMimeData, note: str = "") -> None:
    """읽지 못한 끌어 놓기의 형식을 기록한다 (어느 리더기 방식인지 나중에 맞추기 위해)."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as log:
            log.write(f"\n=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
            if note:
                log.write(note + "\n")
            for fmt in mime.formats():
                raw = bytes(mime.data(fmt))
                log.write(f"{fmt} ({len(raw)} bytes): {raw[:120]!r}\n")
    except OSError:
        pass
