"""search_places: 플레이스리스트 추천의 핵심 함수.

흐름: 조건 파싱 → 범위 단계(팔로우 → 친구 → 온도 상위 큐레이터 → 태그 DB) → 필터 → 점수 → 메인 1 + 대안 2
점수 식과 변수 설명은 README.md 참고.
"""
import math
from collections import Counter

from .parser import parse
from .store import Store, days_since
from .vocab import GROUP_OF, MENU_SYNONYMS, REGION_CENTERS

# 업종별 가중치 (C: 맥락 일치도, T: 온도, R: 친밀도, P: 취향 유사도, D: 최신성, V: 방문·재방문)
WEIGHTS = {
    "맛집": {"C": 0.30, "T": 0.20, "R": 0.20, "P": 0.15, "D": 0.05, "V": 0.10},
    "뷰티": {"C": 0.25, "T": 0.20, "R": 0.15, "P": 0.10, "D": 0.05, "V": 0.25},  # 재방문 ↑
}
LAMBDA = 0.01           # 최신성 감쇠 속도 (약 70일 뒤 절반)
T_LOW, T_HIGH = 32.0, 46.0
ALPHA_K = 12            # 지역×업종에 리스트 항목이 이만큼 쌓이면 α = 1
TIER_BONUS = {1: 0.08, 2: 0.04, 3: 0.0, 4: 0.0}
TIER_NAME = {1: "팔로우한 리스트", 2: "친구의 리스트", 3: "온도 높은 큐레이터의 공개 리스트", 4: "카카오맵 장소 태그"}
TOP_CURATOR_TEMP = 40.0


class Engine:
    def __init__(self, store=None):
        self.s = store or Store()
        ps = self.s.places.values()
        self.vocab = {
            "menus": {m for p in ps for m in p["특화"].get("대표메뉴", []) or []}
                     | {p["특화"].get("음식종류") for p in ps if p["특화"].get("음식종류") not in (None, "", "카페")},
            "cafe_menus": {m for p in ps if p["업종"] == "카페" for m in p["특화"].get("대표메뉴", [])},
            "services": {m for p in ps for m in p["특화"].get("시술", []) or []},
            "designers": {d for p in ps for d in p["특화"].get("디자이너", []) or []},
        }

    # ------------------------------------------------------------------
    # 필터와 맥락 일치도
    # ------------------------------------------------------------------
    def _passes(self, p, q, designer):
        if q["업종"] and p["업종"] != q["업종"]:
            # '밥'이라고 했는데 카페가 나오지 않게, 업종은 정확히 맞춘다
            return False
        if q["지역"] and p["공통"]["지역"] != q["지역"]:
            return False
        sp = p["특화"]
        offered = set(sp.get("대표메뉴", []) or []) | set(sp.get("시술", []) or []) | {sp.get("음식종류") or ""}
        for m in q["메뉴"]:
            words = MENU_SYNONYMS.get(m, [m])
            if not any(w in o for w in words for o in offered):
                return False
        for x in q["제외"]:
            if any(x in o for o in offered):
                return False
        if q["디자이너"] and designer != q["디자이너"]:
            return False
        if q["인원"] and sp.get("적정인원") and sp["적정인원"] < q["인원"]:
            return False
        return True

    def _context(self, p, q, comment):
        """맥락 일치도 C와 맞은 조건 목록. 태그 또는 큐레이터 코멘트에 근거가 있으면 일치로 본다."""
        c, sp, text = p["공통"], p["특화"], comment or ""
        checks = []
        for m in q["분위기"]:
            checks.append((m, m in c["분위기"] or m[:2] in text))
        for g in q["목적"]:
            checks.append((g, g in c["목적"]))
        if q["가격상한"]:
            checks.append(("가격대 " + "₩" * q["가격상한"] + " 이하", c["가격대"] <= q["가격상한"]))
        if q["웨이팅없음"]:
            checks.append(("웨이팅 없음", sp.get("웨이팅") is False))
        if q["주차"]:
            checks.append(("주차 가능", bool(sp.get("주차"))))
        if q["늦게까지"]:
            checks.append(("늦게까지 영업", bool(sp.get("늦게까지")) or "늦게" in text or "새벽" in text))
        if q["작업하기좋음"]:
            checks.append(("작업하기 좋음", bool(sp.get("작업하기좋음"))))
        if q["상담스타일"]:
            checks.append(("상담: " + q["상담스타일"], sp.get("상담스타일") == q["상담스타일"]))
        if not checks:
            return 1.0, []
        return sum(ok for _, ok in checks) / len(checks), checks

    # ------------------------------------------------------------------
    # 취향 유사도
    # ------------------------------------------------------------------
    @staticmethod
    def _vec(p):
        c, sp = p["공통"], p["특화"]
        feats = [f"분위기:{m}" for m in c["분위기"]] + [f"목적:{g}" for g in c["목적"]] + [f"가격:{c['가격대']}"]
        if sp.get("음식종류"):
            feats.append(f"종류:{sp['음식종류']}")
        feats += [f"시술:{s}" for s in sp.get("시술", []) or []]
        return Counter(feats)

    def _profile(self, user):
        v = Counter()
        for L in self.s.lists.values():
            if L["curator"] == user:
                for it in L["items"]:
                    v.update(self._vec(self.s.places[it["place_id"]]))
        return v

    @staticmethod
    def _cos(a, b):
        if not a or not b:
            return 0.5     # 내 리스트가 없으면 중립값
        dot = sum(a[k] * b.get(k, 0) for k in a)
        na = math.sqrt(sum(x * x for x in a.values()))
        nb = math.sqrt(sum(x * x for x in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    # ------------------------------------------------------------------
    def _tiers(self, user, group):
        own = {lid for lid, L in self.s.lists.items() if L["curator"] == user}
        followed = [lid for lid in self.s.follows.get(user, []) if lid in self.s.lists and lid not in own]
        friends = {c for c, v in self.s.intimacy.get(user, {}).items() if v > 0}
        friend_lists = [lid for lid, L in self.s.lists.items()
                        if L["curator"] in friends and lid not in own and lid not in followed]
        seen = set(followed) | set(friend_lists) | own
        top = [lid for lid, L in self.s.lists.items()
               if lid not in seen and L.get("visibility") == "전체 공개"
               and (group is None or self.s.temp(L["curator"], group)["temp"] >= TOP_CURATOR_TEMP)]
        return [(1, followed), (2, friend_lists), (3, top)]

    def _alpha(self, region, group):
        n = sum(1 for L in self.s.lists.values() for it in L["items"]
                if (region is None or self.s.places[it["place_id"]]["공통"]["지역"] == region)
                and (group is None or self.s.group_of_place(it["place_id"]) == group))
        return min(1.0, n / ALPHA_K), n

    def search_places(self, text, user="민준", use_llm=True):
        q = parse(text, self.vocab, use_llm=use_llm)
        notes = []
        if not q["지역"]:
            home = self.s.users.get(user, {}).get("home_region")
            if home:
                q["지역"], q["_지역출처"] = home, "주 활동 지역"
                notes.append(f"지역을 말하지 않아 {user}님의 주 활동 지역({home})으로 찾았어요.")
        res = self._run(q, user)
        if not res["candidates"] and q.get("_지역출처"):
            q["지역"] = None
            notes.append("주 활동 지역에 결과가 없어 지역 조건을 풀었어요.")
            res = self._run(q, user)
        res["query"] = {k: v for k, v in q.items()}
        res["notes"] = notes + res["notes"]
        res["user"] = user
        return res

    def _run(self, q, user):
        group = GROUP_OF.get(q["업종"]) if q["업종"] else None
        prof = self._profile(user)
        alpha, n_items = self._alpha(q["지역"], group)
        intim = self.s.intimacy.get(user, {})
        units = {}          # (place_id, designer) → 최고 점수 후보
        endorsers = {}      # (place_id, designer) → 담은 큐레이터 집합
        notes = []
        reached = 0

        for tier, list_ids in self._tiers(user, group):
            for lid in list_ids:
                L = self.s.lists[lid]
                for it in L["items"]:
                    p = self.s.places[it["place_id"]]
                    if not self._passes(p, q, it.get("designer")):
                        continue
                    g = GROUP_OF.get(p["업종"], "맛집")
                    w = WEIGHTS.get(g, WEIGHTS["맛집"])
                    C, checks = self._context(p, q, it["comment"])
                    if checks and C == 0:
                        continue        # 조건을 하나도 못 맞추면 추천하지 않음
                    T_raw = self.s.temp(L["curator"], g)["temp"]
                    x = {
                        "C": C,
                        "T": min(1, max(0, (T_raw - T_LOW) / (T_HIGH - T_LOW))),
                        "R": intim.get(L["curator"], 0.0),
                        "P": self._cos(prof, self._vec(p)),
                        "D": math.exp(-LAMBDA * days_since(it["saved_at"])),
                        "V": (0.5 + 0.5 * min(it["revisit"], 3) / 3) if it["verified"] else 0.0,
                    }
                    s_list = sum(w[k] * x[k] for k in w)
                    s_tag = 0.6 * x["C"] + 0.4 * x["P"]
                    final = alpha * s_list + (1 - alpha) * s_tag + TIER_BONUS[tier]
                    key = (p["place_id"], it.get("designer"))
                    endorsers.setdefault(key, set()).add(L["curator"])
                    if key not in units or final > units[key]["score"]:
                        units[key] = {
                            "score": round(final, 4), "tier": tier, "tier_name": TIER_NAME[tier],
                            "place": self._place_view(p), "designer": it.get("designer"),
                            "list": {"id": lid, "title": L["title"], "curator": L["curator"],
                                     "subscribers": L.get("subscribers", 0), "source": L.get("source")},
                            "curator_temp": T_raw,
                            "curator_profile": self.s.profile_temps(L["curator"]),
                            "comment": it["comment"], "verified": it["verified"], "revisit": it["revisit"],
                            "saved_at": it["saved_at"],
                            "matched": [n for n, ok in checks if ok], "missed": [n for n, ok in checks if not ok],
                            "breakdown": {k: round(v, 3) for k, v in x.items()}, "weights": w,
                            "s_list": round(s_list, 3), "s_tag": round(s_tag, 3),
                        }
            reached = tier
            if len({k[0] for k in units}) >= 3:
                break

        # 4단계: 리스트에 없는 장소는 카카오맵 장소 태그로 보충
        if len({k[0] for k in units}) < 3:
            reached = 4
            listed = {k[0] for k in units}
            for p in self.s.places.values():
                if p["place_id"] in listed or not self._passes(p, q, None if not q["디자이너"] else q["디자이너"]):
                    continue
                C, checks = self._context(p, q, "")
                if checks and C == 0:
                    continue
                P = self._cos(prof, self._vec(p))
                units[(p["place_id"], None)] = {
                    "score": round(0.6 * C + 0.4 * P - 0.1, 4), "tier": 4, "tier_name": TIER_NAME[4],
                    "place": self._place_view(p), "designer": None, "list": None, "comment": None,
                    "verified": False, "revisit": 0, "matched": [n for n, ok in checks if ok],
                    "missed": [n for n, ok in checks if not ok],
                    "breakdown": {"C": round(C, 3), "P": round(P, 3)}, "s_tag": round(0.6 * C + 0.4 * P, 3),
                }

        for key, u in units.items():
            others = sorted(endorsers.get(key, set()) - ({u["list"]["curator"]} if u["list"] else set()))
            u["also_curators"] = others
        ranked = sorted(units.values(), key=lambda u: -u["score"])
        main, alts = self._pick(ranked, q)
        if main and main["tier"] >= 2:
            notes.append(f"팔로우한 리스트엔 맞는 곳이 없어 '{TIER_NAME[main['tier']]}'에서 찾았어요.")
        elif reached >= 2:
            notes.append(f"대안을 채우려고 '{TIER_NAME[reached]}'까지 범위를 넓혔어요.")
        follow_suggest = None
        if main and main["tier"] == 3:
            follow_suggest = main["list"]["curator"]
        return {"main": main, "alternatives": alts, "candidates": ranked[:10], "tier_reached": reached,
                "alpha": round(alpha, 2), "n_items_area": n_items, "notes": notes, "follow_suggest": follow_suggest}

    # ------------------------------------------------------------------
    def _place_view(self, p):
        return {"place_id": p["place_id"], "name": p["name"], "업종": p["업종"], "지역": p["공통"]["지역"],
                "가격대": p["공통"]["가격대"], "분위기": p["공통"]["분위기"], "목적": p["공통"]["목적"],
                "lat": p["lat"], "lng": p["lng"], "특화": p["특화"], "place_url": p.get("place_url")}

    @staticmethod
    def _dist(p):
        lat0, lng0, _ = REGION_CENTERS.get(p["지역"], (p["lat"], p["lng"], ""))
        dy = (p["lat"] - lat0) * 111_000
        dx = (p["lng"] - lng0) * 88_000
        return math.hypot(dx, dy)

    def _pick(self, ranked, q):
        """메인 1곳 + 대안 2곳. 대안은 점수 2·3위가 아니라 서로 다른 축으로 고른다."""
        if not ranked:
            return None, []
        main = ranked[0]
        mp = main["place"]
        others = [u for u in ranked[1:] if u["place"]["place_id"] != mp["place_id"]]
        # 대안도 조건에 어느 정도 맞아야 한다 (맥락 일치도 0.5 이상, 메인 점수의 60% 이상)
        pool = [u for u in others if u["breakdown"].get("C", 1) >= 0.5 and u["score"] >= 0.6 * main["score"]]
        station = REGION_CENTERS.get(mp["지역"], (0, 0, "역"))[2]
        moods = set(mp["분위기"])

        def jacc(a, b):
            return len(a & b) / len(a | b) if a | b else 1.0

        asked_moods = set(q["분위기"])
        keeps_mood = lambda u: not (asked_moods & set(u.get("missed", [])))   # noqa: E731
        axes = [
            ("더 저렴한 곳", lambda u: keeps_mood(u) and u["place"]["가격대"] < mp["가격대"]),
            (f"{station}에서 더 가까운 곳", lambda u: keeps_mood(u) and self._dist(u["place"]) < self._dist(mp) - 80),
            ("분위기가 다른 곳", lambda u: jacc(set(u["place"]["분위기"]), moods) <= 0.34),
        ]
        if mp["업종"] == "미용":
            axes.insert(1, ("상담 스타일이 다른 곳",
                            lambda u: u["place"]["특화"].get("상담스타일") != mp["특화"].get("상담스타일")))
        alts, used = [], {mp["place_id"]}
        for label, ok in axes:
            if len(alts) == 2:
                break
            for u in pool:
                if u["place"]["place_id"] not in used and ok(u):
                    alts.append({**u, "axis": label})
                    used.add(u["place"]["place_id"])
                    break
        for u in pool:
            if len(alts) == 2:
                break
            if u["place"]["place_id"] not in used and keeps_mood(u):
                alts.append({**u, "axis": "다음으로 잘 맞는 곳"})
                used.add(u["place"]["place_id"])
        # 미용: 장소가 모자라면 같은 미용실의 다른 디자이너
        if mp["업종"] == "미용":
            for u in ranked[1:]:
                if len(alts) == 2:
                    break
                if u["place"]["place_id"] == mp["place_id"] and u["designer"] != main["designer"]:
                    alts.append({**u, "axis": "같은 곳, 다른 디자이너"})
        return main, alts
