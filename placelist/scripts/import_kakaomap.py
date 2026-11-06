"""카카오맵 즐겨찾기 폴더 → 플레이스리스트 데이터 변환기.

입력 : 폴더 CSV (컬럼은 data/sample/folders.csv 참고)
       folder_id, folder_title, owner, subscribers, place_name, kakao_place_id,
       address, memo, saved_at, designer
출력 : data/build/places.json, data/build/lists.json

장소 정보는 두 가지 방법으로 붙인다.
  1) --places 로 이미 태그가 붙은 places.json을 주면 kakao_place_id로 매칭 (샘플 모드)
  2) KAKAO_REST_KEY 환경변수가 있으면 카카오 로컬 API 키워드 검색으로 좌표·카테고리를 가져오고,
     태그는 ANTHROPIC_API_KEY가 있으면 LLM으로, 없으면 메모 기반 규칙으로 추출

사용 예:
  python scripts/import_kakaomap.py --folders data/sample/folders.csv --places data/sample/places.json
  KAKAO_REST_KEY=... python scripts/import_kakaomap.py --folders my_folders.csv
"""
import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from placelist import llm  # noqa: E402
from placelist.vocab import MOOD_WORDS, PURPOSE_WORDS, REGION_ALIASES  # noqa: E402

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def kakao_search(name, address, key):
    """카카오 로컬 API 키워드 검색으로 장소 1건 조회."""
    q = urllib.parse.urlencode({"query": f"{name}", "size": 5})
    req = urllib.request.Request(f"{KAKAO_KEYWORD_URL}?{q}", headers={"Authorization": f"KakaoAK {key}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        docs = json.load(r).get("documents", [])
    if not docs:
        return None
    # 주소가 주어지면 주소 문자열이 겹치는 결과를 우선
    for d in docs:
        if address and any(tok in d.get("address_name", "") for tok in address.split()[:2]):
            return d
    return docs[0]


def category_from_kakao(doc):
    code = doc.get("category_group_code", "")
    name = doc.get("category_name", "")
    if code == "CE7" or "카페" in name:
        return "카페"
    if code == "FD6":
        return "음식점"
    if "미용" in name or "헤어" in name or "네일" in name:
        return "미용"
    return "기타"


def region_from_address(addr):
    for alias, region in REGION_ALIASES.items():
        if alias in addr:
            return region
    for dong, region in {"창천동": "신촌", "서교동": "홍대", "동교동": "홍대", "합정동": "합정",
                         "망원동": "합정", "연남동": "연남"}.items():
        if dong in addr:
            return region
    return addr.split()[1] if len(addr.split()) > 1 else ""


def rule_tags(category, memos):
    """LLM이 없을 때: 메모 문장에서 분위기/목적 단어만 뽑는 최소 규칙."""
    text = " ".join(memos)
    moods = sorted({m for w, m in MOOD_WORDS.items() if w in text})
    purposes = sorted({p for w, p in PURPOSE_WORDS.items() if w in text})
    special = ({"시술": [], "디자이너": [], "상담스타일": "", "가격투명": None} if category == "미용"
               else {"대표메뉴": [], "음식종류": "", "적정인원": None, "웨이팅": None, "주차": None, "늦게까지": None})
    return {"가격대": 2, "분위기": moods, "목적": purposes}, special


def llm_tags(name, category, kakao_category, memos):
    prompt = f"""장소 태그를 JSON 하나로만 답하세요.
장소: {name} / 업종: {category} / 카카오 카테고리: {kakao_category}
사람들이 남긴 메모:
- """ + "\n- ".join(memos) + """

형식:
{"가격대": 1|2|3, "분위기": [조용한, 아늑한, 힙한, 활기찬, 노포, 뷰맛집 중], "목적": [데이트, 혼자, 친구, 가족, 단체 중],
 "특화": 음식점·카페면 {"대표메뉴": [...], "음식종류": "", "적정인원": 숫자, "웨이팅": bool, "주차": bool, "늦게까지": bool},
         미용이면 {"시술": [...], "디자이너": [...], "상담스타일": "꼼꼼한"|"말적은", "가격투명": bool}}
메모에 근거가 없으면 null 또는 빈 리스트로 두세요."""
    data = llm.ask_json(prompt)
    if not data:
        return None
    special = data.pop("특화", {}) or {}
    return data, special


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folders", required=True)
    ap.add_argument("--places", help="이미 태그가 붙은 places.json (샘플 모드)")
    ap.add_argument("--out", default=str(ROOT / "data" / "build"))
    args = ap.parse_args()

    with open(args.folders, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    places_by_kid = {}
    if args.places:
        for p in json.loads(Path(args.places).read_text(encoding="utf-8")):
            places_by_kid[p["kakao_place_id"]] = p
    else:
        key = os.environ.get("KAKAO_REST_KEY")
        if not key:
            sys.exit("--places 를 주거나 KAKAO_REST_KEY 환경변수를 설정하세요.")
        memos_by_name = {}
        for r in rows:
            memos_by_name.setdefault((r["place_name"], r["address"]), []).append(r["memo"])
        for i, ((name, addr), memos) in enumerate(memos_by_name.items()):
            doc = kakao_search(name, addr, key)
            if not doc:
                print(f"  ! 못 찾음: {name}")
                continue
            cat = category_from_kakao(doc)
            tagged = llm_tags(name, cat, doc.get("category_name", ""), memos) or rule_tags(cat, memos)
            common, special = tagged
            common["지역"] = region_from_address(doc.get("address_name", ""))
            places_by_kid[doc["id"]] = {
                "place_id": f"k{doc['id']}", "kakao_place_id": doc["id"], "name": doc["place_name"],
                "업종": cat, "kakao_category": doc.get("category_name", ""),
                "lat": float(doc["y"]), "lng": float(doc["x"]),
                "place_url": doc.get("place_url"), "공통": common, "특화": special,
            }
            for r in rows:
                if r["place_name"] == name and r["address"] == addr:
                    r["kakao_place_id"] = doc["id"]
            print(f"  {i + 1}. {name} → {doc['place_name']} ({cat})")

    lists = {}
    for r in rows:
        p = places_by_kid.get(r["kakao_place_id"])
        if not p:
            continue
        L = lists.setdefault(r["folder_id"], {
            "list_id": r["folder_id"], "title": r["folder_title"], "curator": r["owner"],
            "subscribers": int(r["subscribers"] or 0), "visibility": "전체 공개",
            "source": "카카오맵 즐겨찾기 폴더", "items": []})
        L["items"].append({"place_id": p["place_id"], "designer": r.get("designer") or None,
                           "comment": r["memo"], "saved_at": r["saved_at"]})

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "places.json").write_text(json.dumps(list(places_by_kid.values()), ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "lists.json").write_text(json.dumps(list(lists.values()), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"places {len(places_by_kid)}, lists {len(lists)} → {out}")


if __name__ == "__main__":
    main()
