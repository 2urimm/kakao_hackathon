"""데모 식당 목록 (places/*.json) + 봇 답변에서 식당 이름 찾기.

답변 생성 서버가 place 를 안 붙여도, 봇 답변에 목록의 식당 이름이 나오면 그 식당으로 예약할 수 있게 한다.
목록은 답변 서버 시스템 프롬프트에 넣은 것과 같은 카카오맵 추출 파일 (mapo/seocho/busan_places.json).
파일을 넣거나 고치면 서버 재시작 없이 다음 요청부터 반영된다.

파일 형식 (둘 다 가능):
  {"source": "kakaomap", "places": [{"place_id": "805508054", "name": "오레타치카레", "branch": "서울홍대본점", ...}, ...]}
  [{"place_id": "...", "place_name": "...", "x": 127.0, "y": 37.5, "aliases": ["..."]}, ...]
"""
import json
import logging
import re
from pathlib import Path

import config

log = logging.getLogger("uvicorn.error")

_cache: dict = {"sig": None, "places": []}


def _files() -> list[Path]:
    p = Path(config.PLACES_FILE)
    if not p.is_absolute():
        p = Path(__file__).parent / p  # 상대 경로는 이 프로젝트 폴더 기준
    if p.is_dir():
        return sorted(p.glob("*.json"))
    return [p] if p.is_file() else []


def _normalize(item: dict, source: str) -> dict | None:
    name = str(item.get("place_name") or item.get("name") or "").strip()
    pid = str(item.get("place_id") or item.get("id") or "").strip()
    if not name or not pid:
        return None
    aliases = [str(a) for a in item.get("aliases", [])]
    if branch := str(item.get("branch") or "").strip():
        aliases.append(f"{name} {branch}")
    return {
        "place_id": pid, "place_name": name, "branch": branch or None,
        "category": item.get("category"), "address": item.get("address"),
        "url": item.get("url") or f"https://place.map.kakao.com/{pid}",
        "x": item.get("x"), "y": item.get("y"), "aliases": aliases, "list": source,
    }


def load_places() -> list[dict]:
    """파일이 바뀌었으면 다시 읽음. 읽기 실패한 파일은 건너뜀 (서버는 계속 동작)."""
    files = _files()
    sig = tuple((str(f), f.stat().st_mtime) for f in files)
    if sig == _cache["sig"]:
        return _cache["places"]
    places = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            items = data.get("places", []) if isinstance(data, dict) else data
            source = f.stem.removesuffix("_places")
            places += [p for p in (_normalize(i, source) for i in items if isinstance(i, dict)) if p]
        except (ValueError, OSError) as e:
            log.error("식당 목록 읽기 실패 (%s): %r", f, e)
    _cache.update(sig=sig, places=places)
    log.info("식당 목록 %d곳 읽음 (%s)", len(places), ", ".join(f.name for f in files) or "파일 없음")
    return places


def _norm(s: str) -> str:
    # 띄어쓰기·마크다운 기호 무시 ("서초 목살", "**서초목살**" 도 매칭)
    return re.sub(r"[\s*_`#~>\[\]()'\"]", "", s).lower()


def find_place_in_text(text: str) -> dict | None:
    """text 에 나온 식당 중 가장 먼저 언급된 것 (같은 위치면 더 긴 이름: "인하순대국 아들집" > "인하순대국"). 없으면 None."""
    body = _norm(text)
    best = None  # ((위치, -이름길이), place)
    for p in load_places():
        for name in [p["place_name"], *p["aliases"]]:
            n = _norm(name)
            if n and (i := body.find(n)) >= 0:
                key = (i, -len(n))
                if best is None or key < best[0]:
                    best = (key, p)
    return best[1] if best else None
