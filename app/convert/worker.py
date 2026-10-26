"""파일 넣기: 파일 종류 판단 + 별도 스레드에서 차례로 PDF 변환 (CLAUDE.md 1-4, 7-5)."""

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

# 한글·오피스 조종 부품은 화면 스레드에서 미리 불러 둔다 (작업 스레드에서 처음 불러오면 꼬일 수 있다).
import win32com.client  # noqa: E402,F401  isort: skip

KIND_BY_EXT = {
    ".hwp": "hwp", ".hwpx": "hwp",
    ".xlsx": "xlsx", ".xls": "xlsx", ".csv": "xlsx",
    ".docx": "docx", ".doc": "docx",
    ".jpg": "jpg", ".jpeg": "jpg", ".png": "jpg",
    ".pdf": "pdf",
}
STAGE_BY_KIND = {
    "hwp": "한글로 PDF 만드는 중",
    "xlsx": "엑셀로 PDF 만드는 중",
    "docx": "워드로 PDF 만드는 중",
    "jpg": "사진을 쪽으로 만드는 중",
    "pdf": "PDF 읽는 중",
}
FILE_FILTER = ("넣을 수 있는 파일 (*.hwp *.hwpx *.xlsx *.xls *.csv *.docx *.doc *.jpg *.jpeg *.png *.pdf);;"
               "모든 파일 (*.*)")


def kind_of(path: Path) -> str | None:
    return KIND_BY_EXT.get(path.suffix.lower())


def unsupported_message(path: Path) -> str:
    if path.is_dir():
        return f"{path.name} 폴더는 넣을 수 없어요. 폴더를 열고 안의 파일을 골라 넣어주세요."
    if path.suffix.lower() in (".zip", ".7z", ".egg", ".alz"):
        return f"{path.name} 파일은 넣을 수 없는 형식이에요. 압축을 풀고 안의 파일을 넣어주세요."
    return (f"{path.name} 파일은 넣을 수 없는 형식이에요. "
            "hwp, 엑셀, 워드, 사진(jpg·png), PDF 파일을 넣어주세요.")


@dataclass
class Job:
    path: Path
    kind: str


class ConvertWorker(QObject):
    """작업 스레드에서 파일을 하나씩 PDF로 바꾼다. 화면은 멈추지 않는다."""
    progress = Signal(str, str, int, int)     # 파일 이름, 단계, 끝난 수, 전체 수
    converted = Signal(object, str, str)      # Job, 만든 PDF 경로(실패면 ""), 오류 문장
    finished = Signal()

    def __init__(self, jobs: list[Job]):
        super().__init__()
        self.jobs = jobs
        self.temp_dir = Path(tempfile.mkdtemp(prefix="CusPDF_"))

    def run(self) -> None:
        import pythoncom  # COM(한글·엑셀·워드 조종)은 쓰는 스레드에서 준비해야 한다
        pythoncom.CoInitialize()
        try:
            total = len(self.jobs)
            for number, job in enumerate(self.jobs):
                self.progress.emit(job.path.name, STAGE_BY_KIND[job.kind], number, total)
                try:
                    pdf = self._convert(job, number)
                    self.converted.emit(job, str(pdf), "")
                except Exception as error:  # noqa: BLE001 — 실패는 이유를 사용자에게 보여준다
                    self.converted.emit(job, "", _message(job, error))
            self.progress.emit("", "다 넣었어요", total, total)
        finally:
            pythoncom.CoUninitialize()
            self.finished.emit()

    def _convert(self, job: Job, number: int) -> Path:
        out = self.temp_dir / f"{number:03d}.pdf"
        if job.kind == "pdf":
            return job.path
        if job.kind == "jpg":
            from app.convert.image import image_to_pdf
            image_to_pdf(job.path, out)
        elif job.kind == "xlsx":
            from app.convert.office import excel_to_pdf
            excel_to_pdf(job.path, out)
        elif job.kind == "docx":
            from app.convert.office import word_to_pdf
            word_to_pdf(job.path, out)
        elif job.kind == "hwp":
            from app.convert.hwp import hwp_to_pdf
            hwp_to_pdf(job.path, out)
        return out

    def cleanup(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)


def _message(job: Job, error: Exception) -> str:
    from app.convert.office import ConvertError
    if isinstance(error, ConvertError):
        return str(error)
    if isinstance(error, FileNotFoundError):
        return f"{job.path.name} 파일을 찾을 수 없어요. 옮기거나 지웠는지 확인해주세요."
    if isinstance(error, PermissionError):
        return f"{job.path.name} 파일을 읽을 수 없어요. 다른 프로그램에서 쓰고 있다면 닫고 다시 넣어주세요."
    if job.kind == "jpg":
        return f"{job.path.name} 사진을 읽지 못했어요. 사진 파일이 손상되었는지 확인해주세요."
    return f"{job.path.name} 파일을 PDF로 바꾸지 못했어요. ({error})"


def start_worker(jobs: list[Job], parent: QObject) -> tuple[QThread, ConvertWorker]:
    """작업 스레드를 만들어 시작한다. 연결할 신호는 부르는 쪽에서 start 전에 붙인다."""
    thread = QThread(parent)
    worker = ConvertWorker(jobs)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    return thread, worker
