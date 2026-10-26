"""엑셀·워드·CSV → PDF (CLAUDE.md 7-3).

- DispatchEx로 '새' 엑셀·워드 프로세스를 띄워, 사용자가 열어 둔 문서에 영향을 주지 않는다.
- 파일은 읽기 전용으로 열고, 저장하지 않고 닫는다. 끝나면 프로그램을 반드시 종료한다.
- 이 함수들은 작업 스레드에서 호출되며, 그 스레드에서 pythoncom.CoInitialize()를 먼저 해야 한다.
- 오피스가 바쁘면 명령을 거절한다. 잠깐 쉬었다 다시 보내고, 숨은 안내 창 때문에 계속 멈춰 있으면
  우리가 띄운 프로세스만 정리하고 해결 방법을 알려준다.
"""

import time
from pathlib import Path

import pywintypes
import win32api
import win32con
import win32process
import win32com.client


class ConvertError(Exception):
    """변환 실패. 메시지는 사용자에게 그대로 보여줄 문장이다."""


XL_TYPE_PDF = 0
XL_DELIMITED = 1
WD_EXPORT_PDF = 17

BUSY_CODES = (-2147418111, -2147417846)  # 호출 거절됨, 나중에 다시 시도
BUSY_LIMIT = 20  # 초. 이보다 오래 거절하면 숨은 안내 창에 막힌 것으로 본다


class _Blocked(Exception):
    pass


def _process_ids(exe_name: str) -> set[int]:
    """지금 실행 중인 해당 프로그램(EXCEL.EXE 등)의 프로세스 번호들."""
    found = set()
    for pid in win32process.EnumProcesses():
        try:
            handle = win32api.OpenProcess(
                win32con.PROCESS_QUERY_LIMITED_INFORMATION | win32con.PROCESS_VM_READ, False, pid)
        except pywintypes.error:
            continue
        try:
            path = win32process.GetModuleFileNameEx(handle, 0)
            if path.lower().endswith("\\" + exe_name.lower()):
                found.add(pid)
        except pywintypes.error:
            pass
        finally:
            win32api.CloseHandle(handle)
    return found


def _call(fn):
    """오피스가 바쁘다고 거절하면 잠깐 쉬었다 다시 보낸다."""
    start = time.monotonic()
    while True:
        try:
            return fn()
        except pywintypes.com_error as error:
            if error.hresult not in BUSY_CODES:
                raise
        except AttributeError:
            pass  # 바쁜 동안에는 기능 이름 조회도 거절되어 이 오류로 나타난다
        if time.monotonic() - start > BUSY_LIMIT:
            raise _Blocked()
        time.sleep(0.25)


def _retry_export(fn, attempts: int = 3) -> None:
    """PDF 내보내기. 일시적인 실패면 1초 쉬고 다시 시도한다."""
    for attempt in range(attempts):
        try:
            _call(fn)
            return
        except pywintypes.com_error:
            if attempt == attempts - 1:
                raise
            time.sleep(1)


class _OfficeApp:
    """새 오피스 프로세스를 띄우고, 끝나면 반드시 닫는다 (안 닫히면 우리가 띄운 것만 강제 종료)."""

    def __init__(self, prog_id: str, exe_name: str, label: str):
        self.prog_id, self.exe_name, self.label = prog_id, exe_name, label
        self.app = None
        self.pid = None

    def __enter__(self):
        before = _process_ids(self.exe_name)
        try:
            self.app = win32com.client.DispatchEx(self.prog_id)
        except pywintypes.com_error:
            subject, obj = _PARTICLES[self.label]
            raise ConvertError(f"{obj} 실행하지 못했어요. {subject} 설치되어 있는지 확인해주세요.")
        new = _process_ids(self.exe_name) - before
        self.pid = next(iter(new)) if len(new) == 1 else None
        return self.app

    def __exit__(self, *exc):
        try:
            self.app.Quit()  # 막혀 있으면 거절되므로 한 번만 시도하고 아래에서 정리
        except Exception:
            pass
        self.app = None
        if self.pid:
            for _ in range(20):  # 최대 5초 기다린 뒤에도 남아 있으면 정리
                if self.pid not in _process_ids(self.exe_name):
                    return False
                time.sleep(0.25)
            _terminate(self.pid)
        return False


def _terminate(pid: int) -> None:
    """우리가 띄운 프로세스 하나를 강제로 끝낸다."""
    try:
        handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
        win32api.TerminateProcess(handle, 1)
        win32api.CloseHandle(handle)
    except pywintypes.error:
        pass


# 조사를 맞춘 이름: (은/는 없이) 이/가, 을/를
_PARTICLES = {"엑셀": ("엑셀이", "엑셀을"), "워드": ("워드가", "워드를"), "한글": ("한글이", "한글을")}


def _blocked_message(label: str, name: str) -> str:
    subject, obj = _PARTICLES[label]
    return (f"{subject} 안내 창을 띄우고 멈춰서 {name} 파일을 변환하지 못했어요. "
            f"{obj} 직접 한 번 열어 뜨는 안내 창을 닫은 뒤(가능하면 '다시 표시 안 함' 체크) 다시 넣어주세요.")


def excel_to_pdf(src: Path, out: Path) -> None:
    with _OfficeApp("Excel.Application", "EXCEL.EXE", "엑셀") as excel:
        try:
            _call(lambda: setattr(excel, "Visible", False))
            _call(lambda: setattr(excel, "DisplayAlerts", False))
            try:
                if src.suffix.lower() == ".csv":
                    workbook = _open_csv(excel, src, out.parent)
                else:
                    # Password="!": 암호 걸린 파일이면 보이지 않는 암호 창에서 멈추지 않고 바로 실패하게
                    workbook = _call(lambda: excel.Workbooks.Open(
                        str(src), UpdateLinks=0, ReadOnly=True, Password="!",
                        IgnoreReadOnlyRecommended=True, AddToMru=False))
            except pywintypes.com_error:
                raise ConvertError(f"{src.name} 파일을 엑셀에서 열지 못했어요. "
                                   "암호가 걸려 있거나 손상된 파일인지 엑셀에서 직접 열어 확인해주세요.")
            try:
                # 형식과 파일 이름만 넘긴다. 나머지(표준 품질, 문서 속성 포함, 인쇄 영역 따름)는 기본값과 같고,
                # 다 넘기면 CSV처럼 텍스트로 연 문서에서 실패한다.
                _retry_export(lambda: workbook.ExportAsFixedFormat(XL_TYPE_PDF, str(out)))
            except pywintypes.com_error:
                raise ConvertError(f"{src.name} 파일을 PDF로 만들지 못했어요. "
                                   "인쇄할 내용이 없는 빈 시트만 있는지 엑셀에서 확인해주세요.")
            finally:
                _call(lambda: workbook.Close(SaveChanges=False))
        except _Blocked:
            raise ConvertError(_blocked_message("엑셀", src.name))


def _open_csv(excel, src: Path, temp_dir: Path):
    """CSV는 글자 인코딩(UTF-8 / 한글 윈도우 기본)을 맞춰 열어야 한글이 깨지지 않는다.
    엑셀은 확장자가 .csv면 인코딩 지정을 무시하므로 .txt 복사본을 만들어 연다."""
    raw = src.read_bytes()
    try:
        raw.decode("utf-8")
        origin = 65001  # UTF-8
    except UnicodeDecodeError:
        origin = 949    # 한글 윈도우 기본(CP949)
    copy = temp_dir / (src.stem + ".txt")
    copy.write_bytes(raw)
    # 이름 붙인 지정은 무시되어 순서대로 넘긴다:
    # 파일, 인코딩, 시작 줄, 구분 방식, 따옴표, 연속 구분자, 탭, 세미콜론, 쉼표
    _call(lambda: excel.Workbooks.OpenText(str(copy), origin, 1, XL_DELIMITED, 1, False, False, False, True))
    return _call(lambda: excel.ActiveWorkbook)


def word_to_pdf(src: Path, out: Path) -> None:
    with _OfficeApp("Word.Application", "WINWORD.EXE", "워드") as word:
        try:
            _call(lambda: setattr(word, "Visible", False))
            _call(lambda: setattr(word, "DisplayAlerts", 0))
            try:
                # PasswordDocument="!": 암호 걸린 문서면 암호 창에서 멈추지 않고 바로 실패하게
                document = _call(lambda: word.Documents.Open(
                    str(src), ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False,
                    PasswordDocument="!", Visible=False))
            except pywintypes.com_error:
                raise ConvertError(f"{src.name} 파일을 워드에서 열지 못했어요. "
                                   "암호가 걸려 있거나 손상된 파일인지 워드에서 직접 열어 확인해주세요.")
            try:
                # 파일 이름과 형식만 넘긴다 (나머지는 기본값: 인쇄용 품질)
                _retry_export(lambda: document.ExportAsFixedFormat(str(out), WD_EXPORT_PDF))
            except pywintypes.com_error:
                raise ConvertError(f"{src.name} 파일을 PDF로 만들지 못했어요. 워드에서 직접 PDF로 저장해 넣어주세요.")
            finally:
                _call(lambda: document.Close(SaveChanges=False))
        except _Blocked:
            raise ConvertError(_blocked_message("워드", src.name))
