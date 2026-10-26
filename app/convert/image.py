"""사진(jpg·png) → PDF 한 쪽 (CLAUDE.md 7-4).

- 휴대폰 사진은 EXIF 회전 정보로 방향을 바로잡는다.
- A4 세로 종이의 여백 안에 비율을 유지해 가운데 배치한다.
- 그 크기에서 300dpi를 넘는 큰 사진만 300dpi로 줄인다 (200dpi 아래로는 절대 줄이지 않음).
- 방향 보정도 크기 조정도 필요 없으면 원본 사진 데이터를 그대로 넣어 화질이 그대로다.
"""

import io
from pathlib import Path

from PIL import Image, ImageOps

import PySide6.QtCore  # isort: skip  # noqa: F401  pymupdf보다 먼저 (document.py 설명 참고)
import pymupdf  # isort: skip

A4_W, A4_H = 595.28, 841.89
MARGIN = 42.5        # 15mm
TARGET_DPI = 300


def image_to_pdf(src: Path, out: Path) -> None:
    with Image.open(src) as img:
        rotated = _has_rotation(img)
        upright = ImageOps.exif_transpose(img) if rotated else img
        img_w, img_h = upright.size

        box_w, box_h = A4_W - 2 * MARGIN, A4_H - 2 * MARGIN
        scale = min(box_w / img_w, box_h / img_h)
        draw_w, draw_h = img_w * scale, img_h * scale

        # 종이 위 크기에서 몇 dpi인지 계산해 300dpi보다 크면 줄인다
        dpi = img_w / (draw_w / 72)
        resize = dpi > TARGET_DPI
        if resize:
            ratio = TARGET_DPI / dpi
            upright = upright.resize((round(img_w * ratio), round(img_h * ratio)), Image.LANCZOS)

        if rotated or resize:
            data = _encode(upright, src)
        else:
            data = src.read_bytes()  # 손대지 않은 원본 그대로

    doc = pymupdf.open()
    page = doc.new_page(width=A4_W, height=A4_H)
    x0 = (A4_W - draw_w) / 2
    y0 = (A4_H - draw_h) / 2
    page.insert_image(pymupdf.Rect(x0, y0, x0 + draw_w, y0 + draw_h), stream=data)
    doc.save(out, garbage=4, deflate=True)
    doc.close()


def _has_rotation(img: Image.Image) -> bool:
    try:
        return img.getexif().get(0x0112, 1) not in (1, None)
    except Exception:
        return False


def _encode(img: Image.Image, src: Path) -> bytes:
    buf = io.BytesIO()
    if src.suffix.lower() == ".png":
        img.save(buf, "PNG", optimize=True)
    else:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(buf, "JPEG", quality=92, subsampling=0)
    return buf.getvalue()
