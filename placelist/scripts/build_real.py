"""카카오맵 장소 추출 JSON(kakaomap_places.json 형식) → 플레이스리스트 데이터.

입력 : 장소 추출 JSON 4개 (우슬랭가이드 / 부산 / 마포 / 서초)  + data/build/geocache.json (scripts/geocode.py)
출력 : data/build/places.json, data/build/lists.json, data/sample/social.json

카카오맵에서 온 값 : 이름, 주소, 카테고리, 메뉴·가격, 시설, 영업시간, 웨이팅 글 → 업종·가격대·분위기·목적·특화 태그는
                      이 값에서 규칙으로 뽑는다 (LLM 없음).
시뮬레이션 값      : 큐레이터, 리스트 구성, 메모 문장, 방문 인증, 재방문, 친밀도, 피드백 (make_sample.py 와 같은 성격)
                      → 카카오맵 폴더/후기 데이터가 생기면 import_kakaomap.py 쪽으로 대체

실행: python scripts/build_real.py <우슬랭.json> <busan.json> <mapo.json> <seocho.json>
"""
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "data" / "build"
SAMPLE = ROOT / "data" / "sample"
random.seed(11)

# ---------------------------------------------------------------- 지역
def region_of(addr):
    a = addr.split()
    head = " ".join(a[:2])
    table = [("서울 마포구", "마포"), ("서울 서초구", "서초"), ("서울 강남구", "서초"),
             ("부산 중구", "원도심"), ("부산 서구", "원도심"), ("부산 영도구", "원도심"), ("부산 동구", "원도심"),
             ("부산 동래구", "동래"), ("부산 연제구", "동래"),
             ("부산 수영구", "수영·남구"), ("부산 남구", "수영·남구"),
             ("부산 해운대구", "해운대"), ("부산 사하구", "사하"), ("부산 기장군", "기장")]
    for k, v in table:
        if head == k:
            return v
    return head


REGION_CENTER = {"마포": (37.5563, 126.9236), "서초": (37.4930, 127.0140), "원도심": (35.0985, 129.0325),
                 "동래": (35.2059, 129.0788), "수영·남구": (35.1553, 129.1111), "해운대": (35.1631, 129.1639),
                 "사하": (35.1048, 128.9744), "기장": (35.2443, 129.2150)}

# ---------------------------------------------------------------- 업종·종류
CAFE_CATS = {"카페", "커피전문점", "디저트카페", "제과,베이커리"}
CUISINE = {"이탈리안": "양식", "양식": "양식", "피자": "양식", "스페인음식": "양식", "와인바": "양식",
           "한식": "한식", "퓨전한식": "한식", "찌개,전골": "한식", "국수": "한식", "칼국수": "한식", "수제비": "한식",
           "순대": "한식", "국밥": "한식", "해장국": "한식", "곰탕": "한식", "삼계탕": "한식", "감자탕": "한식",
           "냉면": "한식", "분식": "분식", "토스트": "분식", "해물,생선": "해산물", "회": "해산물", "아구": "해산물",
           "장어": "해산물", "육류,고기": "고기", "족발,보쌈": "고기", "치킨": "치킨",
           "일식": "일식", "일식집": "일식", "초밥,롤": "일식", "일본식라면": "일식", "돈까스,우동": "일식",
           "중국요리": "중식", "실내포장마차": "술집"}
NOPO = {"순대", "국밥", "칼국수", "분식", "해장국", "곰탕", "수제비", "냉면", "감자탕", "토스트", "실내포장마차",
        "아구", "장어", "찌개,전골", "국수"}
LOUD = {"육류,고기", "족발,보쌈", "치킨", "실내포장마차", "장어", "피자", "와인바"}
LATE_LOUD = {"육류,고기", "족발,보쌈", "치킨", "실내포장마차", "장어", "한식", "찌개,전골"}
HIP = {"피자", "일본식라면", "스페인음식", "일식", "일식집", "돈까스,우동", "초밥,롤", "와인바", "양식", "이탈리안",
       "제과,베이커리", "카페", "디저트카페", "커피전문점"}
SOLO = {"순대", "국밥", "칼국수", "분식", "해장국", "토스트", "국수", "돈까스,우동", "우동", "일본식라면", "초밥,롤", "수제비"}
DATE_CATS = {"양식", "이탈리안", "피자", "스페인음식", "와인바", "일식", "일식집", "초밥,롤", "카페", "디저트카페", "커피전문점"}


def hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def late_night(p):
    for d in (p.get("business_hours") or {}).values():
        if d and (hhmm(d["close"]) >= 23 * 60 or hhmm(d["close"]) <= hhmm(d["open"])):
            return True
    return False


def weekday_close(p):
    ends = [hhmm(d["close"]) for k, d in (p.get("business_hours") or {}).items() if d and k in ("mon", "tue", "wed", "thu", "fri")]
    return max(ends) if ends else 0


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def clean_menu(name):
    n = re.sub(r"\(.*?\)|（.*?）", "", name)
    n = re.sub(r"[A-Za-z぀-ヿ一-鿿]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip(" -/")
    return n if len(n) >= 2 else ""


def rep_menus(p):
    ms = p.get("menus") or []
    picked = [m for m in ms if m.get("badges")] or ms[:2]
    out = []
    for m in picked:
        n = clean_menu(m["name"])
        if n and n not in out:
            out.append(n)
    return out[:3]


def waiting_flag(p):
    w = p.get("waiting")
    if not w:
        return False
    t = w["text"]
    if re.search(r"웨이팅\s*(없|이\s*없)|대기\s*없|없이\s*(바로|입장|들어)|바로\s*들어", t):
        return False
    return bool(re.search(r"웨이팅|줄\s*서|대기|기다", t))


def parking_flag(p):
    for f in p.get("facilities") or []:
        if "주차" in f and not re.search(r"불가|근처|인근|권장", f):
            return True
    return False


def tag(p, region):
    cat = p["category"]
    is_cafe = cat in CAFE_CATS
    fac = set(p.get("facilities") or [])
    facs = " ".join(fac)
    prices = [m["price"] for m in p.get("menus") or [] if m.get("price")]
    med = median(prices)
    if med is None:
        grade = 2
    elif is_cafe:
        grade = 1 if med <= 5500 else 2 if med <= 8000 else 3
    else:
        grade = 1 if med <= 12000 else 2 if med <= 25000 else 3
    group = "단체석" in fac or "단체예약" in facs
    private = "프라이빗룸" in fac
    bar = "바테이블" in fac
    late = late_night(p)

    moods = []
    text = p["name"] + p["address"]
    if (is_cafe and re.search(r"황령산|구름", text)) or re.search(r"송정해변|동암해안", text):
        moods.append("뷰맛집")
    if cat in NOPO and not is_cafe:
        moods.append("노포")
    if (group and cat in LOUD) or (late and cat in LATE_LOUD and "노포" not in moods):
        moods.append("활기찬")
    if (region == "마포" and cat in HIP) or cat in {"와인바"}:
        moods.append("힙한")
    if (private or bar or is_cafe) and "노포" not in moods and "활기찬" not in moods and "힙한" not in moods:
        moods.append("아늑한")
    if (private and cat not in LOUD) and grade >= 2 and "조용한" not in moods and "활기찬" not in moods:
        moods.append("조용한")
    if "오마카세" in json.dumps(p.get("menus") or [], ensure_ascii=False) and "조용한" not in moods:
        moods.append("조용한")
    if not moods:
        moods.append("아늑한" if is_cafe else ("활기찬" if group else "조용한"))
    moods = moods[:2]

    purposes = []
    if "혼밥" in facs or bar or is_cafe or cat in SOLO:
        purposes.append("혼자")
    if group or is_cafe or cat not in SOLO:
        purposes.append("친구")
    if group or (private and not is_cafe):
        purposes.append("단체")
    if re.search(r"유아의자|키즈", facs) or private or cat in {"삼계탕", "곰탕", "한식"} and group:
        purposes.append("가족")
    if (set(moods) & {"아늑한", "조용한", "힙한"}) and cat in DATE_CATS:
        purposes.append("데이트")
    purposes = list(dict.fromkeys(purposes)) or ["친구"]

    people = 12 if private else 20 if group else 4 if (bar or is_cafe) else 8
    sp = {"대표메뉴": rep_menus(p), "음식종류": "카페" if is_cafe else CUISINE.get(cat, "기타"), "적정인원": people,
          "웨이팅": waiting_flag(p), "주차": parking_flag(p), "늦게까지": late}
    if cat in ("제과,베이커리", "디저트카페"):
        sp["대표메뉴"] = list(dict.fromkeys(sp["대표메뉴"] + ["디저트"] + (["빵"] if cat == "제과,베이커리" else [])))[:4]
    if cat == "와인바":
        sp["대표메뉴"] = list(dict.fromkeys(sp["대표메뉴"] + ["와인"]))[:4]
    if is_cafe:
        sp["작업하기좋음"] = weekday_close(p) >= 21 * 60 and not sp["웨이팅"]
    return {"업종": "카페" if is_cafe else "음식점", "공통": {"지역": region, "가격대": grade, "분위기": moods, "목적": purposes},
            "특화": sp}


# ---------------------------------------------------------------- 장소 만들기
def load_places(paths):
    geo = json.loads((BUILD / "geocache.json").read_text(encoding="utf-8")) if (BUILD / "geocache.json").exists() else {}
    out = {}
    for path in paths:
        for p in json.loads(Path(path).read_text(encoding="utf-8"))["places"]:
            if p["place_id"] in out:
                continue
            region = region_of(p["address"])
            t = tag(p, region)
            ll = geo.get(p["place_id"])
            if not ll:                                  # 좌표를 못 구한 곳은 지역 중심 근처
                c = REGION_CENTER.get(region, (36.5, 127.5))
                ll = [c[0] + random.uniform(-.004, .004), c[1] + random.uniform(-.004, .004)]
            closed = [c if "휴무" in c else c + " 휴무" for c in (p.get("closed_days") or [])][:2]
            out[p["name"]] = {
                "place_id": "k" + p["place_id"], "kakao_place_id": p["place_id"],
                "name": p["name"] + (f" {p['branch']}" if p.get("branch") else ""),
                "업종": t["업종"], "kakao_category": p["category"],
                "lat": round(ll[0], 6), "lng": round(ll[1], 6), "place_url": p["url"],
                "address": p["address"], "phone": p.get("phone"), "closed": closed,
                "price_range": p.get("price_range"),
                "공통": t["공통"], "특화": t["특화"], "_raw": p,
            }
    return out


# ---------------------------------------------------------------- 메모 (시뮬레이션: 사실에서 뽑은 문장)
ANGLE = {
    "solo": ["혼밥", "늦게", "휴무"], "group": ["단체", "룸", "주차"], "date": ["룸", "테라스", "웨이팅"],
    "late": ["늦게", "단체", "웨이팅"], "cheap": ["휴무", "혼밥", "웨이팅"], "cafe": ["테라스", "늦게", "휴무"],
    "family": ["룸", "주차", "단체"], "any": ["웨이팅", "혼밥", "단체", "주차", "룸", "테라스", "늦게", "휴무"],
}


def memo(pl, angle):
    p, sp = pl["_raw"], pl["특화"]
    facs = " ".join(p.get("facilities") or [])
    ms = p.get("menus") or []
    pick = next((m for m in ms if m.get("badges") and m.get("price")), None) or next((m for m in ms if m.get("price")), None)
    head = f"{clean_menu(pick['name']) or pick['name']} {pick['price']:,}원" if pick else None
    phrase = {
        "혼밥": "혼밥하기 편함" if ("혼밥" in facs or "바테이블" in facs) else None,
        "단체": "단체석 있어서 모임 가능" if "단체석" in facs else None,
        "룸": "룸 있음" if "프라이빗룸" in facs else None,
        "주차": "주차 가능" if sp["주차"] else None,
        "테라스": "테라스 자리 있음" if "테라스" in facs else None,
        "늦게": "늦게까지 해서 2차·해장용" if sp["늦게까지"] else None,
        "웨이팅": "웨이팅 있는 편이라 일찍 가기" if sp["웨이팅"] else None,
        "휴무": pl["closed"][0] if pl["closed"] else None,
    }
    parts = [head] if head else []
    for k in ANGLE[angle]:
        if phrase.get(k) and len(parts) < 3:
            parts.append(phrase[k])
    return ". ".join(parts) if parts else pl["kakao_category"] + " 맛집"


# ---------------------------------------------------------------- 사용자·리스트
USERS = {
    "민준": {"home_region": "동래", "bio": "부산 대학생, 가성비·노포 좋아함"},
    "지수": {"home_region": "동래", "bio": "민준 동료, 카페 작업러"},
    "수진": {"home_region": "수영·남구", "bio": "광안·남천 맛집 탐방러"},
    "민지": {"home_region": "마포", "bio": "연남·홍대 데이트 코스 전문"},
    "하늘": {"home_region": "마포", "bio": "홍대 술자리 총무"},
    "도윤": {"home_region": "서초", "bio": "교대 직장인, 혼밥러"},
    "서연": {"home_region": "원도심", "bio": "부산 맛집 블로거 (모르는 사람)"},
    "예린": {"home_region": "수영·남구", "bio": "프리랜서, 카페 유목민"},
    "태현": {"home_region": "서초", "bio": "회사 총무, 회식 담당"},
    "유나": {"home_region": "마포", "bio": "빵지순례러"},
    "현우": {"home_region": "동래", "bio": "가성비 탐험가 (최근 활동 적음)"},
    "소희": {"home_region": "기장", "bio": "가족 모임 담당"},
    "핫플봇": {"home_region": "원도심", "bio": "홍보성 계정 (어뷰징 예시)"},
    "부산지방우정청": {"home_region": "원도심", "bio": "우체국 추천 맛집 (우슬랭가이드)"},
}
INTIMACY = {
    "민준": {"지수": 0.95, "수진": 0.85, "하늘": 0.6, "태현": 0.5, "현우": 0.3, "도윤": 0.2},
    "지수": {"민준": 0.95, "예린": 0.8, "수진": 0.7, "민지": 0.6, "태현": 0.3},
}
FOLLOWS = {"민준": ["B01", "F12", "F06"], "지수": ["F03", "F06", "F01"]}

# 장소 추출 파일 4개 = 큰 리스트 4개 (순서대로). 우슬랭가이드는 카카오맵 실제 폴더 이름·구독자 수
BIG = [
    ("B01", "2026년 우체국 추천 맛집(우슬랭가이드)", "부산지방우정청", 29305, "any", "2026-10-01"),
    ("B02", "부산 로컬 맛집 지도", "서연", 540, "any", "2026-10-10"),
    ("M01", "마포 맛집 모음", "민지", 112, "date", "2026-10-12"),
    ("S01", "서초·교대 맛집 모음", "도윤", 35, "solo", "2026-10-15"),
]
# 주제별 작은 리스트: (id, 제목, 큐레이터, 구독자, 각도, 시기, 장소 이름들)
THEMED = [
    ("F01", "동래 가성비 한 끼", "민준", 48, "cheap", "recent",
     ["동래밀면 본점", "연동본가해장국 연산본점", "제일통닭", "리바이브커피", "더라이스"]),
    ("F02", "동래 카페 투어", "지수", 61, "cafe", "recent",
     ["리바이브커피", "더라이스", "베르", "수안커피컴퍼니 커피하우스", "쿠루미과자점"]),
    ("F03", "광안 데이트 코스", "수진", 112, "date", "recent",
     ["소바재우재", "양경옥", "구름고개카페", "지밀레니얼"]),
    ("F04", "사하 동네 맛집", "현우", 22, "cheap", "stale",
     ["복성반점", "양평칼국수", "덕이네손수제비", "순덕이국밥"]),
    ("F05", "기장·해운대 가족 식사", "소희", 58, "family", "recent",
     ["국보미역 본점", "올바릇 식당 기장본점", "해녀할매집", "합천돼지국밥 해운대본점"]),
    ("F06", "부산 카페 유목민", "예린", 203, "cafe", "recent",
     ["구름고개카페", "지밀레니얼", "수안커피컴퍼니 커피하우스", "구자윤과자점", "스위스제과점"]),
    ("F07", "홍대·연남 2차 성지", "하늘", 87, "late", "recent",
     ["스필아웃", "평화연남", "로쏘1924나폴리화덕피자 홍대점", "뉴오더클럽 연남", "엘비스텍"]),
    ("F08", "마포 빵·카페", "유나", 94, "cafe", "recent",
     ["리피칩", "수더분", "타호커피", "트래블메이커"]),
    ("F09", "교대·서초 회식 안전빵", "태현", 76, "group", "recent",
     ["부안애서 청계본점", "서초목살", "청솔게르마늄감자탕", "아따맵소", "삼풍치킨 교대본점", "양재오제섞어 양재본점"]),
    ("F10", "교대 직장인 점심", "도윤", 35, "solo", "recent",
     ["인하순대국", "방배순대국", "서초삼계탕", "신선옥", "유성옥"]),
    ("F11", "수영·남구 맛집", "수진", 66, "any", "recent",
     ["소바재우재", "황령산보쌈", "부산돼지국밥", "금강복아구전문점"]),
    ("F12", "부산 국밥·해장 투어", "서연", 210, "solo", "recent",
     ["부산돼지국밥", "합천돼지국밥 해운대본점", "순덕이국밥", "연동본가해장국 연산본점", "간판없는김치찌개"]),
    ("F13", "원도심 먹거리", "서연", 120, "solo", "recent",
     ["신창토스트", "성일손칼국수", "부영집", "작은시장횟집", "새옹지마"]),
    ("F14", "연남 데이트", "민지", 66, "date", "recent",
     ["진우네초밥", "엘비스텍", "오레타치카레 서울홍대본점", "뉴오더클럽 연남"]),
    ("F15", "부산 핫플 모음", "핫플봇", 9, "any", "promo", ["봉식당", "쿠루미과자점", "다무치아"]),
    ("F16", "동래 디저트 BEST", "핫플봇", 4, "any", "promo", ["쿠루미과자점", "베르"]),
    ("F17", "민준 단골", "민준", 3, "solo", "recent", ["동래밀면 본점", "영남식육식당 동래점", "연동본가해장국 연산본점"]),
]
# 우슬랭가이드 실제 메모 (카카오맵 화면에서 확인한 것)
REAL_MEMO = {
    "다무치아": "[3년 연속] 이탈리안 레스토랑 맛집으로 직접 기른 바질페스토 파스타가 시그니처!",
    "된장한상": "[2년 연속] No MSG! 건강하고 맛있는 한상차림의 재래식 된장찌개 전문점",
    "황태를벗삼아": "[2년 연속] 연하고 부드러운 황태살과 매콤달콤한 양념으로 맛과 가성비 모두 사로잡은 맛집",
    "분식회계": "상호는 분식회계지만 가성비와 맞은 정직함 그 자체",
}


def day(kind):
    if kind == "stale":
        base = random.randint(0, 70)
        return f"2026-0{random.choice([3, 4, 5])}-{random.randint(1, 28):02d}" if base >= 0 else ""
    if kind == "promo":
        return "2025-11-02"
    m = random.choice([9, 10, 10, 10, 11])
    return f"2026-{m:02d}-{random.randint(1, 5 if m == 11 else 28):02d}"          # 오늘(11-06) 이후 날짜가 나오지 않게


def main(paths):
    if len(paths) != 4:
        sys.exit("장소 추출 JSON 4개를 우슬랭, 부산, 마포, 서초 순서로 넘겨주세요.")
    per_file = [list(load_places([p]).values()) for p in paths]
    by_name = {pl["name"]: pl for L in per_file for pl in L}
    places = list(by_name.values())

    lists = []
    for (lid, title, cur, subs, angle, base), pls in zip(BIG, per_file):
        items = []
        for i, pl in enumerate(pls):
            m = REAL_MEMO.get(pl["_raw"]["name"]) if lid == "B01" else None
            d = pl["_raw"]
            items.append({"place_id": pl["place_id"], "designer": None, "comment": m or memo(pl, angle),
                          "saved_at": f"2026-{10 if i % 3 else 9:02d}-{(i * 3) % 27 + 1:02d}"})
        lists.append({"list_id": lid, "title": title, "curator": cur, "subscribers": subs, "visibility": "전체 공개",
                      "source": "카카오맵 즐겨찾기 폴더", "items": items})
    for lid, title, cur, subs, angle, kind, names in THEMED:
        items = []
        for n in names:
            if n not in by_name:
                sys.exit(f"장소 이름을 못 찾음: {n}")
            pl = by_name[n]
            items.append({"place_id": pl["place_id"], "designer": None, "comment": memo(pl, angle), "saved_at": day(kind)})
        lists.append({"list_id": lid, "title": title, "curator": cur, "subscribers": subs, "visibility": "전체 공개",
                      "source": "카카오맵 즐겨찾기 폴더", "items": items})

    # ---- 방문 인증·재방문·피드백 (시뮬레이션)
    visits, feedback = [], []
    solo_like = {"한식", "분식", "카페"}
    for L in lists:
        bot = L["curator"] == "핫플봇"
        stale = L["list_id"] == "F04"
        for it in L["items"]:
            ok = False if bot else (random.random() < (0.4 if stale else 0.86))
            visits.append({"folder_id": L["list_id"], "place_id": it["place_id"], "verified": ok,
                           "revisit": 0 if not ok else random.choice([0, 0, 1, 1, 2, 3])})
    users = [u for u in USERS if u not in ("핫플봇", "부산지방우정청")]
    for L in lists:
        if L["curator"] in ("핫플봇",):
            continue
        for v in random.sample([u for u in users if u != L["curator"]], 3):
            it = random.choice(L["items"])
            feedback.append({"visitor": v, "folder_id": L["list_id"], "place_id": it["place_id"],
                             "sentiment": -1 if random.random() < 0.08 else 1, "visitor_verified": True})
    # 지인 몰아주기 예시: 하늘이 태현 리스트(F09)에 5번 → 상한·체감
    for it in next(L for L in lists if L["list_id"] == "F09")["items"][:5]:
        feedback.append({"visitor": "하늘", "folder_id": "F09", "place_id": it["place_id"], "sentiment": 1, "visitor_verified": True})
    # 홍보성 계정: 실제 방문자의 혹평
    for fid, who in (("F15", "민지"), ("F16", "예린"), ("F15", "수진")):
        L = next(x for x in lists if x["list_id"] == fid)
        feedback.append({"visitor": who, "folder_id": fid, "place_id": L["items"][0]["place_id"], "sentiment": -1, "visitor_verified": True})
    feedback.append({"visitor": "도윤", "folder_id": "F04", "place_id": next(L for L in lists if L["list_id"] == "F04")["items"][0]["place_id"],
                     "sentiment": 1, "visitor_verified": False})

    # ---- 저장
    for pl in places:
        pl.pop("_raw")
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / "places.json").write_text(json.dumps(places, ensure_ascii=False, indent=1), encoding="utf-8")
    (BUILD / "lists.json").write_text(json.dumps(lists, ensure_ascii=False, indent=1), encoding="utf-8")
    social = {"users": USERS, "intimacy": INTIMACY, "follows": FOLLOWS, "visits": visits, "feedback": feedback,
              "_note": "카카오맵에 없는 값. 데모용 시뮬레이션 데이터"}
    (SAMPLE / "social.json").write_text(json.dumps(social, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"places {len(places)}, lists {len(lists)}, visits {len(visits)}, feedback {len(feedback)}")


if __name__ == "__main__":
    main(sys.argv[1:])
