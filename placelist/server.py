"""데모 서버 (표준 라이브러리만 사용).

실행: python server.py [포트]          → http://localhost:8000

GET  /api/meta                                  사용자 목록
GET  /api/places                                지도 마커용 장소
GET  /api/mylists?user=자갈치토박이                     내 리스트 + 팔로우한 리스트 + 내 온도
GET  /api/list?id=F02&user=자갈치토박이                 리스트 상세 (항목, 리스트 온도와 근거)
GET  /api/friends?user=자갈치토박이                     친구들의 리스트 (친밀도 순)
GET  /api/compat?user=자갈치토박이                      친구별 리스트 궁합 점수
GET  /api/ranking?region=홍대&category=미용&purpose=&kind=lists|curators&user=자갈치토박이
GET  /api/search?q=...&user=자갈치토박이&llm=0          자연어 추천
GET  /api/events?since=0                        예약 확정·취소 이벤트 (화면이 주기적으로 읽음)
GET  /api/reservations?user=자갈치토박이                내 확정 예약
POST /api/reservation {"reservation_id":"R1","user":"자갈치토박이","place_id":"k1297139609"|"place_name":"다무치아",
                       "list_id":"B01"(선택),"datetime":"2026-11-08 19:00","party_size":2,
                       "status":"confirmed"|"pending"|"cancelled"}     ← 채팅 백엔드가 호출
POST /api/follow  {"user":"자갈치토박이","list_id":"F02","on":true}
GET|POST /chat/...                              채팅 저장 서버로 그대로 전달 (CHAT_SERVER_URL, 기본 http://localhost:8000)
                                                → 외부 링크(ngrok) 하나로 지도 + 채팅 예약 정보를 같이 보여 주려고
"""
import json
import os
import sys
import urllib.error
import urllib.request
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


CHAT_SERVER_URL = os.environ.get("CHAT_SERVER_URL", "http://localhost:8000").rstrip("/")


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

    def _proxy_chat(self, body=None):
        """/chat/api/... → 채팅 저장 서버 /api/... (같은 주소에서 부르니 CORS·https 문제 없음)"""
        url = CHAT_SERVER_URL + self.path[len("/chat"):]
        req = urllib.request.Request(url, data=body, method=self.command,
                                     headers={"Content-Type": self.headers.get("Content-Type", "application/json")})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                code, data, ctype = r.status, r.read(), r.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            code, data, ctype = e.code, e.read(), e.headers.get("Content-Type", "application/json")
        except Exception as e:  # 채팅 서버가 꺼져 있어도 지도는 살아 있게
            return self._json({"error": f"채팅 서버 연결 실패: {e}"}, 502)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/chat/"):
            return self._proxy_chat()
        u = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        user = qs.get("user", "자갈치토박이")
        s = ENGINE.s
        try:
            if u.path == "/api/meta":
                return self._json({"users": {k: {**v, "temps": s.profile_temps(k)}
                                             for k, v in s.users.items() if k in s.intimacy},
                                   # 리스트 주인 (답변 서버 프롬프트의 리스트 4개 = scores 가 있는 리스트) → 로그인 화면 칩
                                   "owners": [{"name": L["curator"], "list_id": L["list_id"], "title": L["title"]}
                                              for L in s.lists.values() if "scores" in L],
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
        raw = self.rfile.read(n)
        if self.path.startswith("/chat/"):
            return self._proxy_chat(raw)
        data = json.loads(raw or b"{}")
        if u.path == "/api/reservation":
            body, code = SERVICE.hub.receive(data)
            return self._json(body, code)
        if u.path == "/api/follow" and data.get("list_id") in ENGINE.s.lists:
            return self._json(SERVICE.follow(data.get("user", "자갈치토박이"), data["list_id"], bool(data.get("on", True))))
        return self._json({"error": "잘못된 요청"}, 400)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"플레이스리스트 데모: http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
