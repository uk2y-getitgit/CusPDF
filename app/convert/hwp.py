"""한글(hwp·hwpx) → PDF (CLAUDE.md 7-1). 반드시 설치된 한글로 변환한다.

- 보안 승인 팝업이 뜨지 않도록 한컴 보안 모듈(FilePathCheckerModule.dll)을 등록한다.
  pyhwpx에 들어 있는 dll을 %APPDATA%\\CusPDF로 복사하고, 사용자 레지스트리에 그 경로를 적는다.
- 한글 조종은 엑셀·워드처럼 win32com으로 직접 한다. pyhwpx의 Hwp 객체는 정리될 때 COM 준비를 해제해서
  (CoUninitialize) 다른 스레드의 엑셀·워드 변환을 멈추게 할 수 있어 쓰지 않는다.
- 사용자가 열어 둔 한글에 붙지 않도록 항상 새 한글을 띄우고(DispatchEx), 끝나면 반드시 종료한다.
- 이 함수는 작업 스레드에서 호출되며, 그 스레드에서 pythoncom.CoInitialize()를 먼저 해야 한다.
"""

import os
import shutil
import winreg
from pathlib import Path

import pywintypes
import win32com.client

from app.convert.office import ConvertError, _call, _Blocked, _OfficeApp

MODULE_NAME = "FilePathCheckerModule"
MODULE_KEY = r"SOFTWARE\HNC\HwpAutomation\Modules"
MODULE_DIR = Path(os.environ.get("APPDATA", Path.home())) / "CusPDF"
# 열 때 안내 창이 뜨지 않게: 강제로 열기, 암호 문서는 묻지 않고 실패, 버전 경고 끄기
OPEN_ARGS = "forceopen:true;suspendpassword:true;versionwarning:false"


def ensure_security_module() -> None:
    """보안 모듈이 등록되어 있지 않으면 등록한다 (사용자 레지스트리, 관리자 권한 불필요)."""
    target = MODULE_DIR / f"{MODULE_NAME}.dll"
    if not target.exists():
        # 프로그램 자료 폴더(실행 파일에도 들어감)에 넣어 둔 dll을 먼저, 없으면 설치된 pyhwpx에서 찾는다
        bundled = Path(__file__).resolve().parent.parent / "resources" / "hwp" / f"{MODULE_NAME}.dll"
        if not bundled.exists():
            import importlib.util
            spec = importlib.util.find_spec("pyhwpx")   # dll만 쓰므로 모듈을 불러오지 않고 위치만 찾는다
            bundled = Path(spec.origin).parent / f"{MODULE_NAME}.dll" if spec and spec.origin else None
        if not bundled or not bundled.exists():
            raise ConvertError("한글 보안 모듈 파일을 찾지 못했어요. 프로그램을 다시 설치해주세요.")
        MODULE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled, target)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MODULE_KEY) as key:
            current, _ = winreg.QueryValueEx(key, MODULE_NAME)
            if Path(current).exists():
                return
    except OSError:
        pass
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, MODULE_KEY) as key:
        winreg.SetValueEx(key, MODULE_NAME, 0, winreg.REG_SZ, str(target))


def hwp_to_pdf(src: Path, out: Path) -> None:
    ensure_security_module()
    with _OfficeApp("HWPFrame.HwpObject", "Hwp.exe", "한글") as hwp:
        try:
            _call(lambda: hwp.RegisterModule("FilePathCheckDLL", MODULE_NAME))
            try:
                _call(lambda: setattr(hwp.XHwpWindows.Item(0), "Visible", False))
            except pywintypes.com_error:
                pass  # 창 숨기기에 실패해도 변환은 된다
            try:
                opened = _call(lambda: hwp.Open(str(src), "", OPEN_ARGS))
            except pywintypes.com_error:
                opened = False
            if not opened:
                raise ConvertError(f"{src.name} 파일을 한글에서 열지 못했어요. "
                                   "암호가 걸려 있거나 손상된 파일인지 한글에서 직접 열어 확인해주세요.")
            if not _save_pdf(hwp, out) or not out.exists():
                raise ConvertError(f"{src.name} 파일을 PDF로 만들지 못했어요. 한글에서 직접 PDF로 저장해 넣어주세요.")
            _call(lambda: hwp.Clear(1))  # 저장하지 않고 문서 닫기
        except _Blocked:
            raise ConvertError(f"한글이 안내 창을 띄우고 멈춰서 {src.name} 파일을 변환하지 못했어요. "
                               "한글을 직접 한 번 열어 뜨는 안내 창을 닫은 뒤 다시 넣어주세요.")


def _save_pdf(hwp, out: Path) -> bool:
    """한글의 '다른 이름으로 저장 → PDF'. 한글에서 인쇄하는 것과 같은 결과이고 그림은 원본 화질 그대로다."""
    def run(action: str, attributes: int) -> bool:
        pset = hwp.HParameterSet.HFileOpenSave
        hwp.HAction.GetDefault(action, pset.HSet)
        pset.filename = str(out)
        pset.Format = "PDF"
        pset.Attributes = attributes
        return bool(hwp.HAction.Execute(action, pset.HSet))
    return _call(lambda: run("FileSaveAs_S", 0)) or _call(lambda: run("FileSaveAsPdf", 16384))
