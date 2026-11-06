"""데모 식당 목록 (demo_places.json) + 봇 답변에서 식당 이름 찾기.

답변 생성 서버가 place 를 안 붙여도, 봇 답변에 목록의 식당 이름이 나오면 그 식당으로 예약할 수 있게 한다.
파일을 고치면 서버 재시작 없이 다음 요청부터 반영된다.

demo_places.json 형식:
[
  {"place_name": "서초칼국수", "place_id": "12345678", "x": 127.0, "y": 37.5, "aliases": ["서초 칼국수집"]},
  ...
]
place_name, place_id 필수. x(경도)/y(위도)/aliases(다른 이름) 는 선택.
"""
import json
import logging
import os
import re
from pathlib import Path

import config

log = logging.getLogger("uvicorn.error")

_cache: dict = {"mtime": None, "places": []}


def _path() -> Path:
    p = Path(config.PLACES_FILE)
    return p if p.is_absolute() else Path(__file__).parent / p  # 상대 경로는 이 프로젝트 폴더 기준


def load_places() -> list[dict]:
    """파일이 바뀌었으면 다시 읽음. 파일이 없거나 깨졌으면 빈 목록 (서버는 계속 동작)."""
    path = _path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    if mtime != _cache["mtime"]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            places = [p for p in data if str(p.get("place_name", "")).strip() and str(p.get("place_id", "")).strip()]
            _cache.update(mtime=mtime, places=places)
            log.info("식당 목록 %d곳 읽음 (%s)", len(places), path)
        except (ValueError, OSError, AttributeError, TypeError) as e:
            log.error("식당 목록 읽기 실패 (%s): %r", path, e)
            return _cache["places"]
    return _cache["places"]


def _norm(s: str) -> str:
    # 띄어쓰기·마크다운 기호 무시 ("서초 칼국수", "**서초칼국수**" 도 매칭)
    return re.sub(r"[\s*_`#~>\[\]()'\"]", "", s).lower()


def find_place_in_text(text: str) -> dict | None:
    """text 에 나온 식당 중 가장 먼저 언급된 것 (같은 위치면 더 긴 이름). 없으면 None."""
    body = _norm(text)
    best = None  # (위치, -이름길이, place)
    for p in load_places():
        for name in [p["place_name"], *p.get("aliases", [])]:
            n = _norm(str(name))
            if n and (i := body.find(n)) >= 0:
                key = (i, -len(n))
                if best is None or key < best[0]:
                    best = (key, p)
    return best[1] if best else None
