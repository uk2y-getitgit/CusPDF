"""파일 이름 앞 번호 순서로 정렬한다 (CLAUDE.md 1-5).

- 번호는 숫자 크기로 비교: 2_ < 10_, 01_ = 1_
- 번호 뒤 구분 기호: _ - . 공백 (예: 01_표지, 2-현황, 03.제 2장, 4 사진)
- 앞 번호가 없는 파일은 번호 있는 파일 뒤에, 파일 이름 가나다순
"""

import re
from pathlib import Path

_NUMBER = re.compile(r"^\s*(\d+)[_\-. ]")


def leading_number(path: Path) -> int | None:
    match = _NUMBER.match(path.name)
    return int(match.group(1)) if match else None


def sort_by_number(paths: list[Path]) -> list[Path]:
    def key(path: Path):
        number = leading_number(path)
        if number is None:
            return (1, 0, path.name.casefold())
        return (0, number, path.name.casefold())
    return sorted(paths, key=key)


def order_preview(paths: list[Path], limit: int = 4) -> str:
    """'01_표지 → 02_제_1장_서두 → … 순서로 넣어요' 같은 짧은 안내 문장."""
    names = [p.stem for p in paths]
    if len(names) > limit:
        names = names[:limit - 1] + ["…", names[-1]]
    return " → ".join(names) + " 순서로 넣어요"
