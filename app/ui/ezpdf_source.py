"""ezPDF에서 쪽 썸네일을 끌어 왔을 때, 어떤 파일의 몇 쪽인지 알아낸다.

ezPDF는 끌어 놓을 때 'EZPDF_PAGE_THUMBNAIL' 형식으로 ezPDF 안에서만 쓰는 4바이트 값만 넘긴다
(파일 경로·쪽 번호·PDF 내용이 없다). 그래서 다음 방법으로 알아낸다.
- 어느 창인지: 끌기를 시작한 ezPDF 창 (끄는 동안 앞에 있던 창, 없으면 가장 위에 있는 ezPDF 창)
- 어느 파일인지: 창 제목의 파일 이름 → 그 프로그램의 실행 정보(파일 경로) 또는
  ezPDF가 레지스트리에 적어 두는 '지금 열린 파일 목록'(OpenFileList)에서 전체 경로를 찾는다.
  (최근 파일 목록은 보지 않는다)
- 몇 쪽인지: ezPDF 아래쪽 상태 막대의 쪽 번호 칸 (지금 보고 있는 쪽)
"""

import ctypes
import winreg
from dataclasses import dataclass
from pathlib import Path

import win32con
import win32gui
import win32process

EZPDF_FORMAT = "EZPDF_PAGE_THUMBNAIL"
TITLE_MARK = " - ezPDF"

_drag_foreground: int = 0   # 끌기가 들어올 때 앞에 있던 창 (드래그를 시작한 프로그램)


@dataclass
class EzpdfDrag:
    name: str                 # 창 제목의 파일 이름
    path: Path | None         # 찾은 전체 경로 (못 찾으면 None)
    page: int | None          # 지금 보고 있는 쪽 (0부터, 못 읽으면 None)


def is_ezpdf(formats: list[str]) -> bool:
    return any(EZPDF_FORMAT in f for f in formats)


def remember_foreground() -> None:
    """끌기가 창에 들어오는 순간 호출: 그때 앞에 있는 창이 끌기를 시작한 프로그램이다."""
    global _drag_foreground
    _drag_foreground = win32gui.GetForegroundWindow()


def _ezpdf_windows() -> list[int]:
    """화면에 보이는 ezPDF 창들 (위에 있는 창부터)."""
    found = []

    def visit(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and TITLE_MARK in win32gui.GetWindowText(hwnd):
            found.append(hwnd)
        return True
    win32gui.EnumWindows(visit, None)
    return found


def find_drag_source() -> EzpdfDrag | None:
    windows = _ezpdf_windows()
    if not windows:
        return None
    root = win32gui.GetAncestor(_drag_foreground, win32con.GA_ROOT) if _drag_foreground else 0
    hwnd = root if root in windows else windows[0]
    title = win32gui.GetWindowText(hwnd)
    name = title.split(TITLE_MARK, 1)[0].strip().lstrip("*").strip()
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return EzpdfDrag(name=name, path=_path_for(pid, name), page=_current_page(hwnd))


# ---------------------------------------------------------------- 파일 경로
def _path_for(pid: int, name: str) -> Path | None:
    wanted = name.casefold()
    for candidate in _command_line_paths(pid) + _open_file_list():
        try:
            if candidate.name.casefold() == wanted and candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _command_line_paths(pid: int) -> list[Path]:
    """그 ezPDF를 실행할 때 넘긴 파일 경로 (탐색기에서 PDF를 더블클릭해 연 경우)."""
    try:
        import win32com.client
        wmi = win32com.client.GetObject("winmgmts:")
        rows = wmi.ExecQuery(f"SELECT CommandLine FROM Win32_Process WHERE ProcessId = {int(pid)}")
        line = next(iter(rows)).CommandLine or ""
    except Exception:
        return []
    parts = [p for p in line.split('"') if p.strip().lower().endswith(".pdf")]
    return [Path(p.strip()) for p in parts]


def _open_file_list() -> list[Path]:
    """ezPDF가 적어 두는 '지금 열린 파일' 목록 (값 이름이 파일 경로)."""
    paths = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Unidocs") as root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                product = winreg.EnumKey(root, i)
                try:
                    with winreg.OpenKey(root, product + r"\OpenFileList") as key:
                        for j in range(winreg.QueryInfoKey(key)[1]):
                            paths.append(Path(winreg.EnumValue(key, j)[0]))
                except OSError:
                    continue
    except OSError:
        pass
    return paths


# ---------------------------------------------------------------- 지금 보는 쪽
def _current_page(hwnd: int) -> int | None:
    """상태 막대(XTPStatusBar) 안의 쪽 번호 칸 글자를 읽는다."""
    found: list[int] = []

    def visit(child, _):
        if win32gui.GetClassName(child) == "Edit":
            parent = win32gui.GetParent(child)
            if parent and win32gui.GetClassName(parent).startswith("XTPStatusBar"):
                found.append(child)
        return True
    try:
        win32gui.EnumChildWindows(hwnd, visit, None)
    except Exception:
        return None
    for edit in found:
        text = _window_text(edit).strip()
        if text.isdigit() and int(text) > 0:
            return int(text) - 1
    return None


def _window_text(hwnd: int) -> str:
    """다른 프로그램의 입력칸 글자 (WM_GETTEXT는 프로그램 사이에서도 전달된다)."""
    send = ctypes.windll.user32.SendMessageW
    length = send(hwnd, win32con.WM_GETTEXTLENGTH, 0, 0)
    buffer = ctypes.create_unicode_buffer(length + 1)
    send(hwnd, win32con.WM_GETTEXT, length + 1, buffer)
    return buffer.value
