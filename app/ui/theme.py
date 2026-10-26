"""UI 규칙(색상·글꼴·간격·버튼 모양)을 한 곳에서 관리한다. (CLAUDE.md 5-6, 5-7)

화면 코드에서는 색상 값을 직접 쓰지 말고 이 파일의 COLOR, SIZE를 가져다 쓴다.
"""

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

FONT_DIR = Path(__file__).resolve().parent.parent / "resources" / "fonts"
FONT_FAMILY = "IBM Plex Sans KR"
FALLBACK_FAMILY = "Malgun Gothic"  # 맑은 고딕

# 5-6. 색상
COLOR = {
    "primary": "#2457B3",        # 기본 파랑: 주요 버튼, 선택 테두리, 끼워 넣을 위치 선
    "primary_dark": "#1D4794",   # 짙은 파랑: 주요 버튼 마우스 올림, 켜진 버튼 글자
    "primary_soft": "#E3EBF8",   # 연한 파랑: 켜진 버튼 바탕, 글자 수정 모드 막대
    "highlight": "#F2C230",      # 강조 노랑: 지금 할 단계, 방금 들어온 쪽
    "text": "#1B2430",           # 글자, 선택 막대 바탕
    "text_sub": "#5A6575",       # 보조 글자
    "line": "#DDE2E8",           # 테두리, 구분선
    "background": "#F4F6F8",     # 창 배경, 검색칸
    "viewer": "#E9ECF0",         # PDF 뒤 배경
    "success": "#1C7343",        # 연결됨, 완료
    "danger": "#B3322A",         # 삭제, 오류
    "white": "#FFFFFF",
}

# 파일 종류 꼬리표 색 (흰 글자)
FILE_TAG_COLOR = {
    "본문": "#5B6573",
    "hwp": "#1A7FA8",
    "xlsx": "#1C7343",
    "docx": "#34558F",
    "pdf": "#B3322A",
    "jpg": "#6B47A8",
    "사진대지": "#6B47A8",
    "간지": "#8A6D1F",
}

# 5-7. 크기·간격 (px)
SIZE = {
    "space": 8,                  # 간격 기본 단위 (8, 16, 24, 32)
    "button_large": 48,          # 주요 큰 버튼 (파일 넣기)
    "button": 40,                # 일반 버튼
    "button_panel": 36,          # 패널 안 버튼
    "icon": 18,                  # 선 아이콘
    "icon_stroke": 1.75,
    "radius": 8,                 # 버튼 모서리
    "radius_float": 12,          # 떠 있는 창 모서리 (메뉴, 선택 막대, 진행 카드)
    "thumbnail_panel": 232,
    "side_panel": 240,           # 옆 창
    "finish_panel": 360,         # 마무리 사이드바
}

# 사용 불가 상태는 흐리게 40%
DISABLED_TEXT = "rgba(27, 36, 48, 0.4)"
DISABLED_PRIMARY = "rgba(36, 87, 179, 0.4)"


def load_fonts() -> str:
    """프로그램에 포함된 글꼴을 등록하고, 실제로 쓸 글꼴 이름을 돌려준다."""
    loaded = False
    for path in FONT_DIR.glob("*.ttf"):
        if QFontDatabase.addApplicationFont(str(path)) != -1:
            loaded = True
    return FONT_FAMILY if loaded else FALLBACK_FAMILY


def build_qss(family: str) -> str:
    c, s = COLOR, SIZE
    return f"""
* {{
    font-family: "{family}", "{FALLBACK_FAMILY}";
    font-size: 13px;
    color: {c['text']};
}}
QMainWindow, #centralArea {{
    background: {c['background']};
}}

/* ---------- 버튼 공통: 2단계 보조 (흰 바탕 + 테두리) ---------- */
QPushButton, QToolButton {{
    background: {c['white']};
    border: 1px solid {c['line']};
    border-radius: {s['radius']}px;
    min-height: {s['button'] - 2}px;
    max-height: {s['button'] - 2}px;
    padding: 0 14px;
    font-weight: 500;
}}
QPushButton:hover, QToolButton:hover {{
    background: {c['background']};
}}
QPushButton:checked, QToolButton:checked {{
    background: {c['primary_soft']};
    border-color: {c['primary']};
    color: {c['primary_dark']};
}}
QPushButton:focus, QToolButton:focus {{
    border: 2px solid {c['primary']};
}}
QPushButton:disabled, QToolButton:disabled {{
    color: {DISABLED_TEXT};
    border-color: rgba(221, 226, 232, 0.6);
}}
QToolButton::menu-indicator {{
    image: none;
    width: 0;
}}

/* ---------- 1단계 주요 (파란 채움) ---------- */
QPushButton[role="primary"] {{
    background: {c['primary']};
    border: 1px solid {c['primary']};
    color: {c['white']};
    font-weight: 700;
}}
QPushButton[role="primary"]:hover {{
    background: {c['primary_dark']};
    border-color: {c['primary_dark']};
}}
QPushButton[role="primary"]:focus {{
    border: 2px solid {c['primary_dark']};
}}
QPushButton[role="primary"]:disabled {{
    background: {DISABLED_PRIMARY};
    border-color: transparent;
    color: {c['white']};
}}
QPushButton[size="large"] {{
    min-height: {s['button_large'] - 2}px;
    max-height: {s['button_large'] - 2}px;
    font-size: 14px;
}}

/* 아이콘만 있는 버튼 (되돌리기, 전체 메뉴 등) */
QToolButton[role="icon"] {{
    min-width: {s['button'] - 2}px;
    max-width: {s['button'] - 2}px;
    padding: 0;
}}
/* 테두리 없는 작은 버튼 (보기 막대 안) */
QToolButton[role="flat"] {{
    border: 1px solid transparent;
    background: transparent;
    min-height: {s['button_panel'] - 2}px;
    max-height: {s['button_panel'] - 2}px;
    padding: 0 8px;
}}
QToolButton[role="flat"]:hover {{
    background: {c['background']};
}}
QToolButton[role="flat"]:checked {{
    background: {c['primary_soft']};
    border-color: {c['primary']};
    color: {c['primary_dark']};
}}

/* ---------- 검색칸 ---------- */
#searchBox {{
    background: {c['background']};
    border: 1px solid {c['line']};
    border-radius: {s['radius']}px;
}}
#searchBox QLineEdit {{
    background: transparent;
    border: none;
    padding: 0;
}}
#searchBox QLineEdit:disabled {{
    color: {DISABLED_TEXT};
}}

/* ---------- 영역 ---------- */
#topBar {{
    background: {c['white']};
    border-bottom: 1px solid {c['line']};
}}
#thumbnailPanel {{
    background: {c['white']};
}}
#viewer {{
    background: {c['viewer']};
}}
#pageView, #pageView > QWidget {{
    background: {c['viewer']};
}}
#mainSplitter::handle {{
    background: {c['line']};
    margin: 0 2px;
}}
#mainSplitter::handle:hover {{
    background: {c['primary']};
}}
#thumbnailList {{
    border: none;
    background: transparent;
    outline: none;
}}
#thumbnailPanel[dropping="true"] {{
    background: {c['primary_soft']};
}}
#dangerMenuItem:hover {{
    background: {c['background']};
}}
#dangerText {{
    color: {c['danger']};
}}

QLabel[text_role="menu_note"] {{
    padding: 0 16px 6px 32px;
    font-size: 12px;
    color: {c['text_sub']};
}}
QToolButton[role="tile"] {{
    min-height: 64px;
    max-height: 64px;
    min-width: 80px;
    padding: 6px 4px;
    font-size: 12px;
    font-weight: 400;
}}

/* ---------- 선택 막대 (어두운 떠 있는 막대) ---------- */
#selectionBar {{
    background: {c['text']};
    border-radius: {s['radius_float']}px;
}}
#selectionBar QLabel {{
    color: {c['white']};
    font-weight: 500;
}}
#selectionBar QToolButton {{
    background: transparent;
    border: none;
    color: {c['white']};
    min-height: {s['button_panel'] - 2}px;
    max-height: {s['button_panel'] - 2}px;
    padding: 0 10px;
}}
#selectionBar QToolButton:hover {{
    background: rgba(255, 255, 255, 0.12);
}}
#selectionBar QToolButton#dangerButton {{
    color: #F2A7A1;
}}
#selectionBar QFrame[line="vertical"] {{
    background: rgba(255, 255, 255, 0.25);
}}

/* ---------- 글자 수정 미리보기 카드 ---------- */
#editPreview {{
    background: {c['white']};
    border: 2px solid {c['primary']};
    border-radius: {s['radius_float']}px;
}}

/* ---------- 진행 카드 ---------- */
#progressCard {{
    background: {c['white']};
    border: 1px solid {c['line']};
    border-radius: {s['radius_float']}px;
}}
QProgressBar {{
    background: {c['background']};
    border: none;
    border-radius: 3px;
    max-height: 6px;
    min-height: 6px;
}}
QProgressBar::chunk {{
    background: {c['primary']};
    border-radius: 3px;
}}

/* ---------- 마무리 사이드바 ---------- */
#finishStep {{
    background: transparent;
    border-radius: {s['radius']}px;
}}
#finishStep[state="current"] {{
    background: #FFF7DA;
}}
QPushButton#stepHead {{
    background: transparent;
    border: none;
    padding: 0;
    text-align: left;
    min-height: 40px;
    max-height: 999px;
}}
QPushButton#linkButton {{
    background: transparent;
    border: none;
    color: {c['primary']};
    padding: 0 4px;
    min-height: 28px;
    max-height: 28px;
    font-weight: 400;
    font-size: 12px;
}}
QPushButton#linkButton:hover {{
    text-decoration: underline;
}}
QToolButton[role="segment"] {{
    min-height: {s['button_panel'] - 2}px;
    max-height: {s['button_panel'] - 2}px;
    padding: 0 12px;
}}
#orderList {{
    border: 1px solid {c['line']};
    border-radius: {s['radius']}px;
    background: {c['white']};
    padding: 2px;
}}
#orderList::item {{
    min-height: 28px;
    padding: 0 8px;
}}
#orderList::item:selected {{
    background: {c['primary_soft']};
    color: {c['primary_dark']};
}}
#warningText {{
    color: {c['danger']};
    font-size: 12px;
}}
QComboBox, QLineEdit {{
    background: {c['white']};
    border: 1px solid {c['line']};
    border-radius: 6px;
    min-height: 30px;
    padding: 0 8px;
}}
QComboBox:focus, QLineEdit:focus {{
    border: 2px solid {c['primary']};
}}
QCheckBox, QRadioButton {{
    spacing: 8px;
    min-height: 24px;
}}

/* ---------- 글자 수정 ---------- */
#topBar[mode="edit"] {{
    background: {c['primary_soft']};
}}
#previewBox {{
    background: {c['background']};
    border-radius: {s['radius']}px;
}}
QPushButton#applyButton {{
    background: {c['primary_soft']};
    border: 1px solid {c['primary']};
    color: {c['primary_dark']};
    font-weight: 600;
}}
QPushButton#applyButton:hover {{
    background: #D4E1F5;
}}

/* ---------- 옆 창 ---------- */
QSlider#sizeSlider::groove:horizontal {{
    height: 4px;
    background: {c['line']};
    border-radius: 2px;
}}
QSlider#sizeSlider::sub-page:horizontal {{
    background: {c['primary']};
    border-radius: 2px;
}}
QSlider#sizeSlider::handle:horizontal {{
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
    background: {c['white']};
    border: 2px solid {c['primary']};
}}
#sideList {{
    border: none;
    background: transparent;
    outline: none;
}}
QPushButton[size="panel"] {{
    min-height: {s['button_panel'] - 2}px;
    max-height: {s['button_panel'] - 2}px;
}}
#rightPanel {{
    background: {c['white']};
    border-left: 1px solid {c['line']};
}}
#statusBar {{
    background: {c['white']};
    border-top: 1px solid {c['line']};
}}
#viewBar {{
    background: {c['white']};
    border: 1px solid {c['line']};
    border-radius: {s['radius_float']}px;
}}

/* ---------- 스크롤 막대 (얇은 회색) ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: #C3CAD3;
    border-radius: 4px;
    margin: 1px;
}}
QScrollBar::handle:vertical {{
    min-height: 32px;
}}
QScrollBar::handle:horizontal {{
    min-width: 32px;
}}
QScrollBar::handle:hover {{
    background: #9AA3AE;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ---------- 글자 ---------- */
QLabel {{
    background: transparent;
}}
QLabel[text_role="title"] {{
    font-size: 15px;
    font-weight: 600;
}}
QLabel[text_role="sub"] {{
    font-size: 12px;
    color: {c['text_sub']};
}}
QLabel[text_role="section"] {{
    font-weight: 500;
    color: {c['text_sub']};
}}
QFrame[line="vertical"] {{
    background: {c['line']};
    max-width: 1px;
    min-width: 1px;
}}

/* ---------- 메뉴 (떠 있는 창: 모서리 12) ---------- */
QMenu {{
    background: {c['white']};
    border: 1px solid {c['line']};
    border-radius: {s['radius_float']}px;
    padding: 8px 0;
}}
QMenu::item {{
    padding: 8px 32px 8px 16px;
    min-height: 20px;
}}
QMenu::item:selected {{
    background: {c['background']};
}}
QMenu::item:disabled {{
    color: {DISABLED_TEXT};
}}
QMenu::separator {{
    height: 1px;
    background: {c['line']};
    margin: 8px 0;
}}
QLabel[text_role="menu_heading"] {{
    padding: 4px 16px;
    font-size: 12px;
    font-weight: 600;
    color: {c['text_sub']};
}}
QToolTip {{
    background: {c['text']};
    color: {c['white']};
    border: none;
    padding: 4px 8px;
}}
"""


def apply(app: QApplication) -> None:
    """프로그램 전체에 글꼴과 스타일을 적용한다."""
    family = load_fonts()
    font = QFont(family)
    font.setPixelSize(13)
    app.setFont(font)
    app.setStyle("Fusion")  # 윈도우 기본 모양의 영향을 줄여 QSS가 그대로 보이게 함
    app.setStyleSheet(build_qss(family))
