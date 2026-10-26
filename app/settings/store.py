"""설정을 사용자 폴더의 JSON 파일에 저장한다 (CLAUDE.md 7-8).

위치: %APPDATA%\\CusPDF\\settings.json
"""

import json
import os
from pathlib import Path

SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "CusPDF" / "settings.json"
RECENT_LIMIT = 10

DEFAULTS = {
    "view_layout": "vertical",     # 페이지 배치 (보기 메뉴)
    "cover_separate": True,        # 두 쪽 보기에서 표지 따로 보기
    "fit_mode": "none",            # 크기 맞춤 방식
    "zoom": 1.0,
    "thumbnail_size": "medium",
    "thumb_panel_width": 232,      # 왼쪽 썸네일 패널 폭 (경계선으로 조절)
    "side_panel_width": 260,       # 오른쪽 옆 창 폭 (경계선으로 조절)
    "side_thumb_scale": 100,       # 옆 창 썸네일 크기 (%)
    "auto_sort": True,             # 파일 이름 번호 순 자동 정렬
    "save_folder": "",             # 저장 기본 폴더 (비어 있으면 원본 폴더)
    "last_folder": "",             # 마지막으로 파일을 고른 폴더
    "recent_files": [],
    "presets": {},                 # 첨부 순서 프리셋: 이름 → 종류 순서
    "current_preset": "기본",
    "font_map": {},                # 글꼴 연결표: PDF 글꼴 이름(정규화) → PC 글꼴 파일
}


class Settings:
    def __init__(self, path: Path = SETTINGS_PATH):
        self.path = path
        self.data = dict(DEFAULTS)
        try:
            self.data.update(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass  # 처음 실행이거나 파일이 깨졌으면 기본값

    def __getitem__(self, key: str):
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key: str, value) -> None:
        self.data[key] = value
        self.save()

    def add_recent(self, path: Path) -> None:
        recent = [p for p in self.data.get("recent_files", []) if Path(p) != path]
        self.data["recent_files"] = [str(path)] + recent[:RECENT_LIMIT - 1]
        self.save()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass  # 설정 저장 실패는 작업을 막지 않는다
