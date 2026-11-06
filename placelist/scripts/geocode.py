"""카카오맵 추출 JSON의 주소 → 좌표 (OpenStreetMap Nominatim, 키 불필요).

추출 파일에는 좌표가 없어서 한 번만 돌려 data/build/geocache.json 에 저장한다.
못 찾은 주소는 캐시에 null 로 남고, build_real.py 가 지역 중심 근처로 대체한다.
카카오 REST 키가 있으면 import_kakaomap.py 쪽 방식(카카오 로컬 API)이 더 정확하다.

실행: python scripts/geocode.py <places.json> [<places.json> ...]
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "build" / "geocache.json"
URL = "https://nominatim.openstreetmap.org/search"
UA = "placelist-demo/0.1"


def variants(addr):
    """상세주소(층·호·건물명)를 떼고 점점 짧게: 도로명+번호 → 도로명만."""
    head = " ".join(addr.split()[:2])
    m = re.search(r"(\S+(?:로|길)\S*)\s+(\d+(?:-\d+)?)", addr)
    if not m:
        return [addr]
    return [f"{head} {m.group(1)} {m.group(2)}", f"{head} {m.group(1)}"]


def lookup(q):
    url = f"{URL}?{urllib.parse.urlencode({'q': q, 'format': 'json', 'limit': 1, 'countrycodes': 'kr'})}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    return (float(data[0]["lat"]), float(data[0]["lon"])) if data else None


def main(paths):
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    for path in paths:
        for p in json.loads(Path(path).read_text(encoding="utf-8"))["places"]:
            pid, addr = p["place_id"], p["address"]
            if cache.get(pid):
                continue
            hit = None
            for q in variants(addr):
                try:
                    hit = lookup(q)
                except Exception as e:  # 네트워크 오류는 건너뜀
                    print("  ! 오류:", q, e)
                time.sleep(1.1)            # Nominatim 이용 규칙: 초당 1회
                if hit:
                    break
            cache[pid] = list(hit) if hit else None
            print(("OK " if hit else "-- "), p["name"], addr, hit or "")
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print("좌표 있음", sum(1 for v in cache.values() if v), "/", len(cache))


if __name__ == "__main__":
    main(sys.argv[1:])
