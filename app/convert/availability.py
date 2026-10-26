"""한글·엑셀·워드가 이 PC에 설치되어 프로그램이 조종할 수 있는지 확인한다 (상태 막대 표시용)."""

import winreg

PROGRAMS = {
    "한글": "HWPFrame.HwpObject",
    "엑셀": "Excel.Application",
    "워드": "Word.Application",
}


def check() -> dict[str, bool]:
    result = {}
    for name, prog_id in PROGRAMS.items():
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id + r"\CLSID"))
            result[name] = True
        except OSError:
            result[name] = False
    return result
