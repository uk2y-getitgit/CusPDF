"""PC 글꼴 찾기와 글꼴 연결표 (CLAUDE.md 7-6, 7-7).

- PDF 안 글꼴 이름(예: ABCDEF+HCRBatang-Bold)을 PC 글꼴 파일(C:\\Windows\\Fonts\\HANBatangB.ttf)과 연결한다.
- TrueType(.ttf, .ttc)만 쓴다. OTF(CFF) 한글 글꼴은 부분 포함이 안 되어 PDF가 아주 커진다.
- PC 글꼴 목록은 처음 한 번 훑어서(약 3초) 설정 폴더에 저장해 두고 다시 쓴다.
"""

import json
import os
import re
from pathlib import Path

import PySide6.QtCore  # isort: skip  # noqa: F401  pymupdf보다 먼저 (document.py 설명 참고)
import pymupdf  # isort: skip

FONT_DIRS = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
             Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"]
INDEX_PATH = Path(os.environ.get("APPDATA", Path.home())) / "CusPDF" / "font_index.json"

# 새로 만드는 글자(간지, 사진 캡션, 쪽번호)에 쓰는 기본 글꼴
DEFAULT_FONT = FONT_DIRS[0] / "malgun.ttf"
DEFAULT_BOLD = FONT_DIRS[0] / "malgunbd.ttf"
SERIF_FONT = FONT_DIRS[0] / "HANBatang.ttf"   # 함초롬바탕 (한글 설치 PC)


def normalize(name: str) -> str:
    """'ABCDEF+HCRBatang-Bold' → 'hcrbatangbold', 'HCR Batang Regular' → 'hcrbatang'"""
    name = name.split("+", 1)[-1]
    key = re.sub(r"[\s\-_,]", "", name).lower()
    for suffix in ("regular", "normal", "roman", "mt", "ps"):
        if key.endswith(suffix) and len(key) > len(suffix):
            key = key[: -len(suffix)]
    return key


def _scan() -> dict[str, str]:
    index: dict[str, str] = {}
    for folder in FONT_DIRS:
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if path.suffix.lower() not in (".ttf", ".ttc"):
                continue
            try:
                name = pymupdf.Font(fontfile=str(path)).name
            except Exception:
                continue
            index.setdefault(normalize(name), str(path))
            index.setdefault(normalize(path.stem), str(path))
    return index


def font_index() -> dict[str, str]:
    """정규화한 글꼴 이름 → 글꼴 파일 경로. 글꼴 폴더가 바뀌면 다시 훑는다."""
    stamp = sum(len(list(f.iterdir())) for f in FONT_DIRS if f.is_dir())
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        if data.get("stamp") == stamp:
            return data["fonts"]
    except (OSError, ValueError, KeyError):
        pass
    fonts = _scan()
    try:
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        INDEX_PATH.write_text(json.dumps({"stamp": stamp, "fonts": fonts}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return fonts


def find_font(pdf_font: str, bold: bool, font_map: dict[str, str]) -> str | None:
    """PDF 글꼴 이름에 맞는 PC 글꼴 파일. 연결표(font_map)를 먼저 보고, 없으면 이름으로 찾는다."""
    key = normalize(pdf_font)
    mapped = font_map.get(key)
    if mapped and Path(mapped).exists():
        return mapped
    index = font_index()
    candidates = [key]
    if bold and not key.endswith("bold"):
        candidates.insert(0, key + "bold")
    if key.endswith("bold"):
        candidates.append(key[:-4])
    for candidate in candidates:
        if candidate in index:
            return index[candidate]
    return None


def font_choices() -> list[tuple[str, str]]:
    """사용자가 고를 수 있는 PC 글꼴 목록 (보이는 이름, 파일 경로), 한글 글꼴 먼저."""
    seen, items = set(), []
    for path in sorted(set(font_index().values())):
        try:
            name = pymupdf.Font(fontfile=path).name
        except Exception:
            continue
        if name in seen:
            continue
        seen.add(name)
        items.append((name, path))
    korean = ("HCR", "Malgun", "Batang", "Gulim", "Dotum", "Gungsuh", "HY", "Hancom", "Nanum", "HanSantteut")
    items.sort(key=lambda item: (not item[0].startswith(korean), item[0].lower()))
    return items


def generated_font(serif: bool = False, bold: bool = False) -> str:
    """새로 만드는 글자에 쓸 글꼴 파일."""
    if serif and SERIF_FONT.exists():
        return str(SERIF_FONT)
    path = DEFAULT_BOLD if bold else DEFAULT_FONT
    return str(path if path.exists() else DEFAULT_FONT)
