"""데이터 로드 + 큐레이터 업종별 온도 계산.

카카오맵에서 가져온 것 : data/build/places.json, data/build/lists.json
데모 시뮬레이션        : data/sample/social.json (방문 인증, 재방문, 친밀도, 팔로우, 피드백)
"""
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .vocab import GROUP_OF

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 6)

# 온도 식 계수 (README의 온도 식 참고)
BASE = 36.5
K_GOOD, K_BAD, K_SUBS, K_REVISIT, K_VERIFIED = 3.0, 4.0, 0.6, 2.0, 2.0
GIVER_CAP = 1.5          # 한 사람이 한 큐레이터에게 줄 수 있는 피드백 효과 상한
UNVERIFIED_W = 0.3       # 방문 인증 없는 피드백의 가중치
STALE_FREE_DAYS, STALE_SCALE, STALE_MAX = 90, 60, 3.0
PROMO_PENALTY = 2.5
T_MIN, T_MAX = 30.0, 50.0


def days_since(d):
    y, m, dd = map(int, d.split("-"))
    return (TODAY - date(y, m, dd)).days


class Store:
    def __init__(self, build_dir=None, social_path=None):
        build_dir = Path(build_dir or ROOT / "data" / "build")
        social_path = Path(social_path or ROOT / "data" / "sample" / "social.json")
        self.places = {p["place_id"]: p for p in json.loads((build_dir / "places.json").read_text(encoding="utf-8"))}
        self.lists = {L["list_id"]: L for L in json.loads((build_dir / "lists.json").read_text(encoding="utf-8"))}
        social = json.loads(social_path.read_text(encoding="utf-8")) if social_path.exists() else {}
        self.users = social.get("users", {})
        self.intimacy = social.get("intimacy", {})
        self.follows = social.get("follows", {})
        self.feedback = social.get("feedback", [])
        visits = {(v["folder_id"], v["place_id"]): v for v in social.get("visits", [])}

        # 리스트 항목에 방문 인증·재방문을 덧붙임 (카카오맵에는 없는 값)
        for L in self.lists.values():
            for it in L["items"]:
                v = visits.get((L["list_id"], it["place_id"]), {})
                it["verified"] = bool(v.get("verified", False))
                it["revisit"] = int(v.get("revisit", 0))
        self.recompute()

    # ------------------------------------------------------------------
    def group_of_place(self, pid):
        return GROUP_OF.get(self.places[pid]["업종"], "기타")

    def recompute(self):
        """온도 계산. base_* 는 예약 확정 피드백을 뺀 값 (예약으로 얼마나 올랐는지 비교용)."""
        self.temps, self.list_temps = self._compute_temperatures(self.feedback)
        base_fb = [f for f in self.feedback if f.get("source") != "reservation"]
        self.base_temps, self.base_list_temps = self._compute_temperatures(base_fb)

    def _compute_temperatures(self, feedback):
        """온도를 두 단위로 계산한다.
        - 리스트 온도   : 리스트 하나에 대한 신뢰 (리스트 카드·랭킹에 표시)
        - 큐레이터 × 업종 그룹 온도 : 프로필의 업종별 온도, 추천 점수의 T 항
        """
        buckets = defaultdict(lambda: {"items": [], "subs": 0.0, "fb": defaultdict(list)})
        place_list_count = defaultdict(lambda: defaultdict(int))
        for L in self.lists.values():
            c = L["curator"]
            n = len(L["items"]) or 1
            for it in L["items"]:
                g = self.group_of_place(it["place_id"])
                for key in (("curator", c, g), ("list", L["list_id"])):
                    buckets[key]["items"].append(it)
                buckets[("curator", c, g)]["subs"] += L.get("subscribers", 0) / n
                place_list_count[c][it["place_id"]] += 1
            buckets[("list", L["list_id"])]["subs"] = L.get("subscribers", 0)

        # 피드백: 같은 사람이 줄수록 1, 1/2, 1/3 ... 으로 체감, 사람당 상한
        for f in feedback:
            L = self.lists.get(f["folder_id"])
            if not L or f["place_id"] not in self.places or f["visitor"] == L["curator"]:
                continue        # 자기 리스트에 준 피드백은 무시
            w = 1.0 if f.get("visitor_verified") else UNVERIFIED_W
            for key in (("curator", L["curator"], self.group_of_place(f["place_id"])), ("list", L["list_id"])):
                buckets[key]["fb"][f["visitor"]].append((f["sentiment"], w))

        temps, list_temps = {}, {}
        for key, b in buckets.items():
            curator = key[1] if key[0] == "curator" else self.lists[key[1]]["curator"]
            dup = any(cnt >= 2 for cnt in place_list_count[curator].values())
            res = self._temperature(b["items"], b["subs"], b["fb"], dup)
            if key[0] == "curator":
                temps[(key[1], key[2])] = res
            else:
                list_temps[key[1]] = res
        return temps, list_temps

    @staticmethod
    def _temperature(its, subs, fb, dup):
        good = bad = 0.0
        n_good = n_bad = 0
        for evs in fb.values():
            pos = [w for s, w in evs if s > 0]
            neg = [w for s, w in evs if s < 0]
            n_good += len(pos)
            n_bad += len(neg)
            good += min(GIVER_CAP, sum(w / (k + 1) for k, w in enumerate(pos)))
            bad += min(GIVER_CAP, sum(w / (k + 1) for k, w in enumerate(neg)))
        n = len(its) or 1
        revisit_ratio = sum(1 for it in its if it["revisit"] > 0) / n
        verified_ratio = sum(1 for it in its if it["verified"]) / n
        avg_age = sum(days_since(it["saved_at"]) for it in its) / n
        stale = min(STALE_MAX, max(0.0, avg_age - STALE_FREE_DAYS) / STALE_SCALE)
        promo = PROMO_PENALTY if (verified_ratio < 0.3 and (n >= 3 or dup)) else 0.0
        parts = {
            "좋았어요": round(K_GOOD * math.log1p(good), 2),
            "별로였어요": round(-K_BAD * math.log1p(bad), 2),
            "구독자": round(K_SUBS * math.log1p(subs), 2),
            "재방문": round(K_REVISIT * revisit_ratio, 2),
            "방문인증": round(K_VERIFIED * (verified_ratio - 0.5), 2),
            "오래 방치": round(-stale, 2),
            "홍보성 패턴": round(-promo, 2),
        }
        t = max(T_MIN, min(T_MAX, BASE + sum(parts.values())))
        return {"temp": round(t, 1), "parts": parts, "n_items": len(its),
                "stats": {"좋았어요": n_good, "별로였어요": n_bad, "재방문 비율": round(revisit_ratio, 2),
                          "방문인증 비율": round(verified_ratio, 2), "평균 경과일": round(avg_age)}}

    def list_meta(self, lid):
        """리스트의 대표 지역·업종 (항목 중 가장 많은 것)."""
        L = self.lists[lid]
        regions = Counter(self.places[it["place_id"]]["공통"]["지역"] for it in L["items"])
        cats = Counter(self.places[it["place_id"]]["업종"] for it in L["items"])
        return {"지역": regions.most_common(1)[0][0] if regions else "",
                "업종": cats.most_common(1)[0][0] if cats else "",
                "지역들": dict(regions), "업종들": dict(cats)}

    def temp(self, curator, group, base=False):
        src = self.base_temps if base else self.temps
        return src.get((curator, group), {"temp": BASE, "parts": {}, "n_items": 0})

    def profile_temps(self, curator):
        """프로필 표시용: 대표 온도(항목 수 가중 평균)와 업종별 온도."""
        rows = {g: v for (c, g), v in self.temps.items() if c == curator}
        if not rows:
            return {"대표": BASE}
        total = sum(v["n_items"] for v in rows.values())
        rep = sum(v["temp"] * v["n_items"] for v in rows.values()) / total
        return {"대표": round(rep, 1), **{g: v["temp"] for g, v in rows.items()}}
