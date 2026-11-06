"""화면에서 쓰는 조회 기능: 내 리스트, 리스트 상세, 친구 리스트, 랭킹, 팔로우."""
import math
from collections import Counter, defaultdict

from .store import Store
from .vocab import GROUP_OF

GROUP_LABEL = {"맛집": "맛집", "뷰티": "뷰티"}


class Service:
    def __init__(self, store: Store):
        self.s = store
        self.hub = None       # reservations.Reservations (server.py 에서 연결)

    # ------------------------------------------------------------------
    def list_card(self, lid, viewer=None):
        L = self.s.lists[lid]
        meta = self.s.list_meta(lid)
        t = self.s.list_temps[lid]
        return {
            "list_id": lid, "title": L["title"], "curator": L["curator"], "n_items": len(L["items"]),
            "subscribers": L.get("subscribers", 0), "temp": t["temp"],
            "temp_delta": round(t["temp"] - self.s.base_list_temps[lid]["temp"], 1), "지역": meta["지역"], "업종": meta["업종"],
            "source": L.get("source"), "followed": bool(viewer and lid in self.s.follows.get(viewer, [])),
            "mine": viewer == L["curator"],
            "preview": [self.s.places[it["place_id"]]["name"] for it in L["items"][:3]],
        }

    def places(self):
        return [{"place_id": p["place_id"], "name": p["name"], "업종": p["업종"], "지역": p["공통"]["지역"],
                 "lat": p["lat"], "lng": p["lng"]} for p in self.s.places.values()]

    def my_lists(self, user):
        own = [self.list_card(lid, user) for lid, L in self.s.lists.items() if L["curator"] == user]
        followed = [self.list_card(lid, user) for lid in self.s.follows.get(user, []) if lid in self.s.lists]
        return {"user": user, "profile": self.s.profile_temps(user), "own": own, "followed": followed}

    def list_detail(self, lid, viewer=None):
        L = self.s.lists[lid]
        t = self.s.list_temps[lid]
        fb = defaultdict(lambda: {"좋았어요": 0, "별로였어요": 0})
        for f in self.s.feedback:
            if f["folder_id"] == lid and f["visitor"] != L["curator"] and f.get("source") != "reservation":
                fb[f["place_id"]]["좋았어요" if f["sentiment"] > 0 else "별로였어요"] += 1
        items = []
        booked = self.hub.counts() if self.hub else {}
        for it in L["items"]:
            p = self.s.places[it["place_id"]]
            items.append({
                "reservations": booked.get((lid, p["place_id"]), 0),
                "place_id": p["place_id"], "name": p["name"], "업종": p["업종"], "지역": p["공통"]["지역"],
                "가격대": p["공통"]["가격대"], "분위기": p["공통"]["분위기"], "lat": p["lat"], "lng": p["lng"],
                "address": p.get("address"), "closed": p.get("closed") or [], "place_url": p.get("place_url"),
                "designer": it.get("designer"), "comment": it["comment"], "saved_at": it["saved_at"],
                "verified": it["verified"], "revisit": it["revisit"], "feedback": fb[p["place_id"]],
            })
        return {**self.list_card(lid, viewer), "items": items, "temp_parts": t["parts"], "temp_stats": t["stats"],
                "curator_profile": self.s.profile_temps(L["curator"]),
                "intimacy": self.s.intimacy.get(viewer, {}).get(L["curator"], 0) if viewer else 0}

    def friends(self, user):
        out = []
        for friend, v in sorted(self.s.intimacy.get(user, {}).items(), key=lambda x: -x[1]):
            lists = [self.list_card(lid, user) for lid, L in self.s.lists.items()
                     if L["curator"] == friend and L.get("visibility", "전체 공개") in ("전체 공개", "친구")]
            if lists:
                out.append({"name": friend, "intimacy": v, "profile": self.s.profile_temps(friend),
                            "bio": self.s.users.get(friend, {}).get("bio", ""),
                            "lists": sorted(lists, key=lambda c: -c["temp"])})
        return out

    # ------------------------------------------------------------------
    # 궁합: 내 리스트와 친구 리스트의 닮은 정도 (0~100)
    # ------------------------------------------------------------------
    def _taste(self, user):
        """사용자가 만든 리스트의 장소들 → (태그 벡터, 장소 집합, 지역 분포, 평균 가격대)"""
        vec, pids, regions, prices = Counter(), set(), Counter(), []
        for L in self.s.lists.values():
            if L["curator"] != user:
                continue
            for it in L["items"]:
                p = self.s.places[it["place_id"]]
                c = p["공통"]
                pids.add(p["place_id"])
                regions[c["지역"]] += 1
                prices.append(c["가격대"])
                vec.update([f"분위기:{m}" for m in c["분위기"]] + [f"목적:{g}" for g in c["목적"]] + [f"업종:{p['업종']}"])
        return vec, pids, regions, (sum(prices) / len(prices) if prices else None)

    @staticmethod
    def _cos(a, b):
        dot = sum(a[k] * b.get(k, 0) for k in a)
        na, nb = math.sqrt(sum(x * x for x in a.values())), math.sqrt(sum(x * x for x in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    def compat(self, user):
        me = self._taste(user)
        out = []
        for friend, intim in self.s.intimacy.get(user, {}).items():
            fr = self._taste(friend)
            if not fr[1] or not me[1]:
                continue
            taste = self._cos(me[0], fr[0])
            shared = me[1] & fr[1]
            overlap = len(shared) / len(me[1] | fr[1])
            region = self._cos(me[2], fr[2])
            price = 1 - min(1.0, abs(me[3] - fr[3]) / 2)
            score = round(100 * (0.5 * taste + 0.2 * min(1.0, overlap * 3) + 0.15 * region + 0.15 * price))
            common_tags = sorted(((k, min(me[0][k], fr[0][k])) for k in me[0] if k in fr[0]), key=lambda x: -x[1])
            out.append({
                "name": friend, "score": score, "intimacy": intim,
                "bio": self.s.users.get(friend, {}).get("bio", ""),
                "parts": {"취향": round(taste * 100), "겹치는 장소": round(min(1.0, overlap * 3) * 100),
                          "활동 동네": round(region * 100), "가격대": round(price * 100)},
                "common_tags": [k.split(":", 1)[1] for k, _ in common_tags[:4]],
                "shared": [{"place_id": pid, "name": self.s.places[pid]["name"]} for pid in sorted(shared)][:4],
                "n_shared": len(shared),
                # 친구만 가본 곳 → 내가 가볼 만한 곳
                "try": [{"place_id": pid, "name": self.s.places[pid]["name"], "업종": self.s.places[pid]["업종"]}
                        for pid in sorted(fr[1] - me[1])][:3],
            })
        out.sort(key=lambda x: -x["score"])
        return out

    def follow(self, user, lid, on=True):
        fs = self.s.follows.setdefault(user, [])
        if on and lid not in fs and self.s.lists[lid]["curator"] != user:
            fs.append(lid)
        if not on and lid in fs:
            fs.remove(lid)
        return {"followed": lid in fs}

    # ------------------------------------------------------------------
    def _item_ok(self, pid, region, category, purpose):
        p = self.s.places[pid]
        if region and p["공통"]["지역"] != region:
            return False
        if category and p["업종"] != category:
            return False
        if purpose and purpose not in p["공통"]["목적"]:
            return False
        return True

    def ranking(self, region=None, category=None, purpose=None, kind="lists", viewer=None, limit=10):
        """지역 × 업종 × 상황 랭킹. 지역·분야별로 나눠 소수 큐레이터의 독식을 막는다."""
        if kind == "curators":
            group = GROUP_OF.get(category) if category else None
            rows = defaultdict(lambda: {"n": 0, "groups": set()})
            for L in self.s.lists.values():
                for it in L["items"]:
                    if self._item_ok(it["place_id"], region, category, purpose):
                        r = rows[L["curator"]]
                        r["n"] += 1
                        r["groups"].add(self.s.group_of_place(it["place_id"]))
            out = []
            for c, r in rows.items():
                g = group or max(r["groups"], key=lambda gg: self.s.temp(c, gg)["n_items"])
                out.append({"curator": c, "group": g, "temp": self.s.temp(c, g)["temp"], "n_matched": r["n"],
                        "temp_delta": round(self.s.temp(c, g)["temp"] - self.s.temp(c, g, base=True)["temp"], 1),
                        "base_temp": self.s.temp(c, g, base=True)["temp"],
                            "profile": self.s.profile_temps(c), "bio": self.s.users.get(c, {}).get("bio", ""),
                            "friend": bool(viewer and c in self.s.intimacy.get(viewer, {}))})
            out.sort(key=lambda x: (-x["temp"], -x["n_matched"]))
            base_rank = {x["curator"]: i + 1 for i, x in enumerate(sorted(out, key=lambda x: (-x["base_temp"], -x["n_matched"])))}
            for i, x in enumerate(out):
                x["rank_delta"] = base_rank[x["curator"]] - (i + 1)
            return out[:limit]

        out = []
        for lid, L in self.s.lists.items():
            n = len(L["items"])
            matched = sum(1 for it in L["items"] if self._item_ok(it["place_id"], region, category, purpose))
            if matched >= min(2, n) and matched > 0:
                card = self.list_card(lid, viewer)
                card["n_matched"] = matched
                card["friend"] = bool(viewer and L["curator"] in self.s.intimacy.get(viewer, {}))
                out.append(card)
        out.sort(key=lambda x: (-x["temp"], -x["n_matched"]))
        base = sorted(out, key=lambda x: (-(x["temp"] - x["temp_delta"]), -x["n_matched"]))
        base_rank = {x["list_id"]: i + 1 for i, x in enumerate(base)}
        for i, x in enumerate(out):
            x["rank_delta"] = base_rank[x["list_id"]] - (i + 1)       # +는 예약 덕분에 올라간 순위
        return out[:limit]
