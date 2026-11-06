"""예약 확정 이벤트 처리.

채팅 쪽 백엔드가 예약이 확정되면 POST /api/reservation 으로 알려준다. 여기서는
  1) 예약을 저장하고 (data/build/reservations.json, 서버를 다시 켜도 유지)
  2) 그 예약이 나온 리스트에 "예약 확정" 신호를 넣어 온도를 다시 계산하고
  3) 리스트 온도·큐레이터 온도·랭킹 순위가 얼마나 바뀌었는지 이벤트로 남긴다.
화면은 GET /api/events?since=N 을 주기적으로 읽어 알림을 띄운다.

예약 확정 → 온도 반영 방식
  예약은 방문 전이라 '좋았어요'가 아니라 "추천을 믿고 실제로 예약까지 이어졌다"는 신호이다.
  기존 피드백 식을 그대로 쓰되 방문 인증된 사람의 '좋았어요' 1건으로 센다.
  → 같은 사람이 여러 번 예약해도 체감(1, 1/2, 1/3…)·사람당 상한(1.5)이 그대로 적용되고,
    자기 리스트에 한 예약은 무시된다.  취소되면 그 신호를 빼고 다시 계산한다.
"""
import json
import threading
import time
from pathlib import Path

from .service import Service

FILE = Path(__file__).resolve().parents[1] / "data" / "build" / "reservations.json"


class Reservations:
    def __init__(self, svc: Service):
        self.svc, self.s = svc, svc.s
        self.lock = threading.Lock()
        self.records = []          # 예약 (reservation_id 당 1건)
        self.events = []           # 화면 알림용 이벤트 (seq 증가)
        if FILE.exists():
            data = json.loads(FILE.read_text(encoding="utf-8"))
            self.records, self.events = data.get("records", []), data.get("events", [])
            for r in self.records:
                if r["status"] == "confirmed" and r.get("credited_list"):
                    self._add_feedback(r)
            self.s.recompute()

    # ------------------------------------------------------------------
    def _save(self):
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text(json.dumps({"records": self.records, "events": self.events}, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    def _add_feedback(self, r):
        self.s.feedback.append({"visitor": r["user"], "folder_id": r["credited_list"], "place_id": r["place_id"],
                                "sentiment": 1, "visitor_verified": True, "source": "reservation",
                                "reservation_id": r["reservation_id"]})

    def _resolve_place(self, d):
        if d.get("place_id") in self.s.places:
            return d["place_id"]
        name = (d.get("place_name") or "").strip()
        if name:
            for p in self.s.places.values():
                if p["name"] == name:
                    return p["place_id"]
            for p in self.s.places.values():
                if name in p["name"] or p["name"] in name:
                    return p["place_id"]
        return None

    def _pick_list(self, user, pid, wanted):
        """예약이 나온 리스트. 채팅 쪽이 list_id를 주면 그대로, 아니면 팔로우 → 친구 → 온도 높은 순으로 고른다."""
        cands = [lid for lid, L in self.s.lists.items() if any(it["place_id"] == pid for it in L["items"])]
        if wanted in cands:
            return wanted
        others = [l for l in cands if self.s.lists[l]["curator"] != user] or cands
        if not others:
            return None
        follows, friends = set(self.s.follows.get(user, [])), set(self.s.intimacy.get(user, {}))
        return sorted(others, key=lambda l: (l not in follows, self.s.lists[l]["curator"] not in friends,
                                             -self.s.list_temps[l]["temp"]))[0]

    def _snapshot(self, lid, place):
        L = self.s.lists[lid]
        g = self.s.group_of_place(place["place_id"])
        rows = self.svc.ranking(place["공통"]["지역"], place["업종"], None, "lists", None, limit=999)
        rank = next((i + 1 for i, c in enumerate(rows) if c["list_id"] == lid), None)
        return {"list_temp": self.s.list_temps[lid]["temp"], "curator": L["curator"], "group": g,
                "curator_temp": self.s.temp(L["curator"], g)["temp"], "rank": rank, "of": len(rows)}

    def _event(self, kind, r, effect=None):
        p = self.s.places[r["place_id"]]
        L = self.s.lists.get(r.get("credited_list") or "")
        ev = {"seq": len(self.events) + 1, "type": kind, "ts": int(time.time()), "reservation_id": r["reservation_id"],
              "user": r["user"], "datetime": r.get("datetime"), "party_size": r.get("party_size"),
              "place": {"place_id": p["place_id"], "name": p["name"], "지역": p["공통"]["지역"], "업종": p["업종"]},
              "list": {"id": L["list_id"], "title": L["title"], "curator": L["curator"]} if L else None,
              "effect": effect}
        self.events.append(ev)
        return ev

    # ------------------------------------------------------------------
    def receive(self, d):
        """웹훅 본문 d → (응답 dict, HTTP 코드)."""
        with self.lock:
            user = (d.get("user") or "").strip()
            rid = str(d.get("reservation_id") or f"R{len(self.records) + 1:04d}")
            status = d.get("status", "confirmed")
            old = next((r for r in self.records if r["reservation_id"] == rid), None)

            if status == "cancelled":
                if not old or old["status"] != "confirmed":
                    return {"error": "취소할 확정 예약이 없어요", "reservation_id": rid}, 404
                place = self.s.places[old["place_id"]]
                before = self._snapshot(old["credited_list"], place) if old.get("credited_list") else None
                self.s.feedback[:] = [f for f in self.s.feedback if f.get("reservation_id") != rid]
                self.s.recompute()
                old["status"] = "cancelled"
                after = self._snapshot(old["credited_list"], place) if old.get("credited_list") else None
                ev = self._event("cancelled", old, self._effect(before, after))
                self._save()
                return {"ok": True, "event": ev}, 200

            if old:   # 같은 예약 번호가 다시 오면 한 번만 반영
                return {"ok": True, "duplicate": True, "reservation_id": rid}, 200
            pid = self._resolve_place(d)
            if not user or not pid:
                return {"error": "user 와 place_id(또는 place_name)가 필요해요"}, 400

            r = {"reservation_id": rid, "user": user, "place_id": pid, "datetime": d.get("datetime"),
                 "party_size": d.get("party_size"), "status": status, "credited_list": None}
            self.records.append(r)
            if status != "confirmed":      # 대기·요청 중: 저장만 하고 온도는 건드리지 않음
                ev = self._event("pending", r)
                self._save()
                return {"ok": True, "event": ev}, 200

            lid = self._pick_list(user, pid, d.get("list_id"))
            place = self.s.places[pid]
            before = self._snapshot(lid, place) if lid else None
            r["credited_list"] = lid
            if lid:
                self._add_feedback(r)
                self.s.recompute()
            after = self._snapshot(lid, place) if lid else None
            ev = self._event("confirmed", r, self._effect(before, after))
            self._save()
            return {"ok": True, "event": ev}, 200

    @staticmethod
    def _effect(b, a):
        if not b or not a:
            return None
        return {"list_temp": [b["list_temp"], a["list_temp"]], "curator": a["curator"], "group": a["group"],
                "curator_temp": [b["curator_temp"], a["curator_temp"]],
                "rank": [b["rank"], a["rank"]], "rank_of": a["of"]}

    # ------------------------------------------------------------------
    def since(self, n):
        return {"last": len(self.events), "events": [e for e in self.events if e["seq"] > n]}

    def of_user(self, user):
        out = []
        for r in reversed(self.records):
            if r["user"] != user or r["status"] != "confirmed":
                continue
            p = self.s.places[r["place_id"]]
            ev = next((e for e in self.events if e["reservation_id"] == r["reservation_id"] and e["type"] == "confirmed"), None)
            out.append({"reservation_id": r["reservation_id"], "place": {"place_id": p["place_id"], "name": p["name"],
                                                                         "지역": p["공통"]["지역"], "업종": p["업종"]},
                        "datetime": r.get("datetime"), "party_size": r.get("party_size"),
                        "list": ev["list"] if ev else None, "effect": ev["effect"] if ev else None})
        return out

    def counts(self):
        """(list_id, place_id) → 확정 예약 수. 리스트 상세에 표시."""
        c = {}
        for r in self.records:
            if r["status"] == "confirmed" and r.get("credited_list"):
                k = (r["credited_list"], r["place_id"])
                c[k] = c.get(k, 0) + 1
        return c
