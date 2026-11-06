"""자연어 검색 → 조건 JSON.

규칙 기반이 기본이고, ANTHROPIC_API_KEY 가 있으면 LLM 파싱 결과로 빈칸을 보강한다.
플리 봇이 대화에서 조건을 뽑을 때도 이 함수를 그대로 쓴다.
"""
import re

from . import llm
from .vocab import (CATEGORY_WORDS, CONSULT_WORDS, EXCLUDE_GROUPS, KOREAN_NUMS, MENU_SYNONYMS,
                    MOOD_WORDS, PURPOSE_WORDS, REGION_ALIASES)

# 한 글자 메뉴가 다른 단어 안에서 잘못 잡히는 경우
FALSE_HITS = {"회": ["회식", "회사", "회의", "회장"], "펌": [], "컷": []}


def empty_query():
    return {"업종": None, "지역": None, "목적": [], "분위기": [], "가격상한": None, "인원": None,
            "메뉴": [], "제외": [], "웨이팅없음": False, "주차": False, "늦게까지": False,
            "작업하기좋음": False, "상담스타일": None, "디자이너": None}


def _menu_hit(word, text):
    if word not in text:
        return False
    for bad in FALSE_HITS.get(word, []):
        if bad in text and text.count(word) == text.count(bad):
            return False
    return True


def parse_rules(text, vocab):
    """vocab: {"menus": set, "services": set, "designers": set}  (장소 데이터에서 만든 사전)"""
    q = empty_query()
    t = text.strip()

    # 지역
    for alias, region in sorted(REGION_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if alias in t:
            q["지역"] = region
            break

    # 제외 ("해산물 못 먹어", "고기 빼고")
    for m in re.finditer(r"([가-힣]+?)\s*(?:은|는|이|가|류)?\s*(?:못\s*먹|안\s*먹|빼고|말고|싫어|별로야)", t):
        w = m.group(1)
        hit = [k for k in EXCLUDE_GROUPS if k in w]
        q["제외"].extend(EXCLUDE_GROUPS[hit[0]] if hit else [w])
    excl_text = " ".join(m.group(0) for m in re.finditer(r"[가-힣]+\s*(?:못\s*먹|안\s*먹|빼고|말고|싫어)", t))

    # 메뉴·시술 (제외 문구 안의 단어는 빼고)
    body = t.replace(excl_text, " ") if excl_text else t
    for w in sorted(vocab["menus"] | vocab["services"], key=len, reverse=True):
        if (len(w) >= 2 or w in FALSE_HITS) and _menu_hit(w, body) and not any(w in m for m in q["메뉴"]):
            q["메뉴"].append(w)
    for w in sorted(MENU_SYNONYMS, key=len, reverse=True):
        if w in body and not any(w in m or m in w for m in q["메뉴"]):
            q["메뉴"].append(w)

    # 디자이너 ("지은쌤", "지은 디자이너", "지은 원장님")
    for d in vocab["designers"]:
        if re.search(d + r"\s*(쌤|선생님|디자이너|원장님|실장님)", t):
            q["디자이너"] = d

    # 업종
    scores = {c: sum(1 for w in ws if w in body) for c, ws in CATEGORY_WORDS.items()}
    if any(m in vocab["services"] for m in q["메뉴"]) or q["디자이너"]:
        scores["미용"] += 3
    if any(m in vocab["cafe_menus"] for m in q["메뉴"]):
        scores["카페"] += 2
    elif any(m in ("디저트", "케이크", "커피", "베이글", "빵", "빙수") for m in q["메뉴"]):
        scores["카페"] += 2
    elif q["메뉴"]:
        scores["음식점"] += 2
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        q["업종"] = best

    # 목적·분위기
    for w, p in PURPOSE_WORDS.items():
        if w in t and p not in q["목적"]:
            q["목적"].append(p)
    for w, m in MOOD_WORDS.items():
        if w in t and m not in q["분위기"]:
            q["분위기"].append(m)
    if q["업종"] == "미용":
        for w, c in CONSULT_WORDS.items():
            if w in t:
                q["상담스타일"] = c
        if "조용한" in q["분위기"] and not q["상담스타일"]:
            q["상담스타일"] = "말적은"
        q["분위기"] = [m for m in q["분위기"] if m != "조용한"]

    # 가격
    m = re.search(r"(\d+(?:\.\d+)?)\s*만\s*원", t)
    if m:
        won = float(m.group(1))
        q["가격상한"] = 1 if won <= 1.2 else 2 if won <= 3 else 3
    elif re.search(r"안\s*비싼|비싸지\s*않|부담\s*없", t):
        q["가격상한"] = 2
    elif re.search(r"저렴|싼\s|싼곳|싼 데|싸게|가성비", t + " "):
        q["가격상한"] = 1

    # 인원
    m = re.search(r"(\d+)\s*명", t)
    if m:
        q["인원"] = int(m.group(1))
    else:
        for w, n in KOREAN_NUMS.items():
            if re.search(w + r"\s*(명|이서|이 ?서)", t):
                q["인원"] = n
                break
    if q["인원"] and q["인원"] >= 6 and "단체" not in q["목적"]:
        q["목적"].append("단체")

    # 기타 조건
    q["웨이팅없음"] = bool(re.search(r"웨이팅\s*(없|안)|안\s*기다|바로\s*들어", t))
    q["주차"] = "주차" in t
    q["늦게까지"] = bool(re.search(r"늦게|새벽|밤늦|2차|야식", t))
    q["작업하기좋음"] = bool(re.search(r"작업|공부|노트북|콘센트|과제", t)) and q["업종"] == "카페"
    return q


def parse(text, vocab, use_llm=True):
    q = parse_rules(text, vocab)
    q["_파서"] = "규칙"
    if not use_llm:
        return q
    data = llm.ask_json(
        "다음 장소 검색 문장을 JSON으로 바꾸세요. 키: 업종(음식점|카페|미용|null), 지역(마포|서초|원도심|동래|수영·남구|해운대|사하|기장|null), "
        "목적(데이트|혼자|친구|가족|단체 리스트), 분위기(조용한|아늑한|힙한|활기찬|노포|뷰맛집 리스트), "
        "가격상한(1|2|3|null), 인원(숫자|null), 메뉴(리스트), 제외(리스트), 웨이팅없음, 주차, 늦게까지(bool).\n"
        f"문장: {text}")
    if data:
        for k, v in data.items():
            if k in q and v not in (None, [], "") and not q[k]:
                q[k] = v
        q["_파서"] = "규칙+LLM"
    return q
