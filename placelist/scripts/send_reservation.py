"""채팅 백엔드를 대신해 예약 확정 이벤트를 보내 보는 시연용 스크립트.

  python scripts/send_reservation.py 자갈치토박이 "황태를벗삼아"                # 확정
  python scripts/send_reservation.py 하늘 "동래밀면" --list F01 --time "2026-11-09 12:30" --party 3
  python scripts/send_reservation.py 자갈치토박이 "황태를벗삼아" --cancel R0001  # 취소 (온도 되돌림)
  python scripts/send_reservation.py --reset                          # 저장된 예약 지우기 (서버 재시작 필요)
"""
import argparse
import json
import urllib.request
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("user", nargs="?")
ap.add_argument("place", nargs="?", help="장소 이름 또는 place_id")
ap.add_argument("--list", dest="list_id")
ap.add_argument("--time", default="2026-11-08 19:00")
ap.add_argument("--party", type=int, default=2)
ap.add_argument("--id", dest="rid")
ap.add_argument("--cancel", metavar="RESERVATION_ID")
ap.add_argument("--status", default="confirmed")
ap.add_argument("--url", default="http://localhost:8000")
ap.add_argument("--reset", action="store_true")
a = ap.parse_args()

if a.reset:
    f = Path(__file__).resolve().parents[1] / "data" / "build" / "reservations.json"
    f.unlink(missing_ok=True)
    print("삭제함:", f, "→ 서버를 다시 켜세요")
    raise SystemExit
body = {"user": a.user, "datetime": a.time, "party_size": a.party, "status": a.status}
body["place_id" if (a.place or "").startswith("k") and (a.place or "")[1:].isdigit() else "place_name"] = a.place
if a.list_id:
    body["list_id"] = a.list_id
if a.rid:
    body["reservation_id"] = a.rid
if a.cancel:
    body.update(status="cancelled", reservation_id=a.cancel)
req = urllib.request.Request(a.url + "/api/reservation", json.dumps(body, ensure_ascii=False).encode(),
                             {"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req) as r:
        print(json.dumps(json.load(r), ensure_ascii=False, indent=1))
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode())
