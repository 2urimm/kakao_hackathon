"""테스트 질문 20개로 파싱·추천 결과를 한 번에 확인.
실행: python scripts/test_queries.py        (LLM 끄고 규칙 파서만)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from placelist.engine import Engine  # noqa: E402

QUERIES = [
    ("민준", "가성비 좋은 한 끼 먹을 곳"),
    ("민준", "해장할 때 국밥"),
    ("지수", "작업하기 좋은 카페"),
    ("민준", "동래 카페 디저트"),
    ("수진", "광안 데이트 조용한 곳"),
    ("민준", "10명 단체 회식 장소"),
    ("지수", "부모님 모시고 갈 곳 주차 되는 데"),
    ("민준", "기장 바다 보이는 맛집"),
    ("민준", "마포 연남 피자 데이트"),
    ("민준", "홍대 2차 늦게까지 하는 술집"),
    ("도윤", "교대 혼밥 순대국"),
    ("태현", "서초 회식 고기 20명"),
    ("민준", "해산물 못 먹어 부산 친구랑 저녁"),
    ("지수", "웨이팅 없는 빵집"),
    ("민준", "원도심 남포동 먹거리"),
    ("민준", "냉면 먹고 싶다"),
    ("지수", "해운대 일식"),
    ("민준", "사하 칼국수"),
    ("민준", "1인 1만원 점심"),
    ("태현", "양재 파스타"),
]


def show(r):
    m = r["main"]
    if not m:
        return "  (결과 없음)"
    def line(u, head):
        who = f"{u['list']['curator']}({u['curator_temp']}℃)·'{u['list']['title']}'" if u["list"] else "카카오맵 태그"
        d = f" · {u['designer']} 디자이너" if u.get("designer") else ""
        return f"  {head} {u['place']['name']}{d} — {who} [{u['score']:.2f}]"
    out = [line(m, "▶")]
    for a in r["alternatives"]:
        out.append(line(a, f"  └ {a['axis']}:"))
    return "\n".join(out)


def main():
    e = Engine()
    for user, q in QUERIES:
        r = e.search_places(q, user, use_llm=False)
        parsed = {k: v for k, v in r["query"].items() if v and not k.startswith("_")}
        print(f"\n[{user}] {q}\n  조건: {parsed}\n  단계: {r['tier_reached']}  α={r['alpha']}")
        for n in r["notes"]:
            print("  ·", n)
        print(show(r))


if __name__ == "__main__":
    main()
