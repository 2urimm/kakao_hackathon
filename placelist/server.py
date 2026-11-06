"""데모 서버 (표준 라이브러리만 사용).

실행: python server.py [포트]          → http://localhost:8000

GET  /api/meta                                  사용자 목록
GET  /api/places                                지도 마커용 장소
GET  /api/mylists?user=민준                     내 리스트 + 팔로우한 리스트 + 내 온도
GET  /api/list?id=F02&user=민준                 리스트 상세 (항목, 리스트 온도와 근거)
GET  /api/friends?user=민준                     친구들의 리스트 (친밀도 순)
GET  /api/compat?user=민준                      친구별 리스트 궁합 점수
GET  /api/ranking?region=홍대&category=미용&purpose=&kind=lists|curators&user=민준
GET  /api/search?q=...&user=민준&llm=0          자연어 추천
GET  /api/events?since=0                        예약 확정·취소 이벤트 (화면이 주기적으로 읽음)
GET  /api/reservations?user=민준                내 확정 예약
POST /api/reservation {"reservation_id":"R1","user":"민준","place_id":"k1297139609"|"place_name":"다무치아",
                       "list_id":"B01"(선택),"datetime":"2026-11-08 19:00","party_size":2,
                       "status":"confirmed"|"pending"|"cancelled"}     ← 채팅 백엔드가 호출
POST /api/follow  {"user":"민준","list_id":"F02","on":true}
"""
import json
import sys
from collections import Counter
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from placelist.engine import Engine  # noqa: E402
from placelist.reservations import Reservations  # noqa: E402
from placelist.service import Service  # noqa: E402

ENGINE = Engine()
SERVICE = Service(ENGINE.s)
SERVICE.hub = Reservations(SERVICE)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "web"), **kw)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")      # 채팅 쪽 백엔드·프론트가 다른 주소여도 호출 가능
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        user = qs.get("user", "민준")
        s = ENGINE.s
        try:
            if u.path == "/api/meta":
                return self._json({"users": {k: {**v, "temps": s.profile_temps(k)}
                                             for k, v in s.users.items() if k in s.intimacy},
                                   "regions": [r for r, _ in Counter(pl["공통"]["지역"] for pl in s.places.values()).most_common()],
                                   "categories": [c for c in ("음식점", "카페", "미용") if any(pl["업종"] == c for pl in s.places.values())],
                                   "purposes": ["데이트", "혼자", "친구", "가족", "단체"]})
            if u.path == "/api/places":
                return self._json(SERVICE.places())
            if u.path == "/api/mylists":
                return self._json(SERVICE.my_lists(user))
            if u.path == "/api/list":
                if qs.get("id") not in s.lists:
                    return self._json({"error": "없는 리스트"}, 404)
                return self._json(SERVICE.list_detail(qs["id"], user))
            if u.path == "/api/friends":
                return self._json(SERVICE.friends(user))
            if u.path == "/api/events":
                return self._json(SERVICE.hub.since(int(qs.get("since", 0) or 0)))
            if u.path == "/api/reservations":
                return self._json(SERVICE.hub.of_user(user))
            if u.path == "/api/compat":
                return self._json(SERVICE.compat(user))
            if u.path == "/api/ranking":
                return self._json(SERVICE.ranking(qs.get("region") or None, qs.get("category") or None,
                                                  qs.get("purpose") or None, qs.get("kind", "lists"), user))
            if u.path == "/api/search":
                text = qs.get("q", "").strip()
                if not text:
                    return self._json({"error": "q가 비어 있어요"}, 400)
                return self._json(ENGINE.search_places(text, user, use_llm=qs.get("llm", "0") == "1"))
        except Exception as e:  # 데모 중 서버가 죽지 않게
            return self._json({"error": str(e)}, 500)
        return super().do_GET()

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n) or b"{}")
        if u.path == "/api/reservation":
            body, code = SERVICE.hub.receive(data)
            return self._json(body, code)
        if u.path == "/api/follow" and data.get("list_id") in ENGINE.s.lists:
            return self._json(SERVICE.follow(data.get("user", "민준"), data["list_id"], bool(data.get("on", True))))
        return self._json({"error": "잘못된 요청"}, 400)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"플레이스리스트 데모: http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
