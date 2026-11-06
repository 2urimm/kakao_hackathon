"""채팅 수신/저장 서버.

실행:  python main.py
문서:  http://<서버IP>:<PORT>/docs   (프론트 담당자에게 이 주소 공유)

흐름:
  0. 프론트 → POST /api/rooms {"name": "해커톤 팀방", "member_names": [...]}  → 방 id 받음
  1. 프론트 → POST /api/messages {"room_id": <방 id>, ...}  ("@봇 ..." 채팅)
  2. 이 서버가 저장 후, 그 방의 최근 대화를 답변 생성 서버 POST /api/chat 으로 전달 (백그라운드)
  3. 답변 생성 서버가 답변을 만들어서 → 이 서버 POST /api/messages 로 user_name=BOT_NAME 으로 저장
  4. 저장되는 순간 ws://<서버IP>:<PORT>/ws/<room_id> 에 연결된 프론트로 바로 푸시
     (웹소켓을 못 쓰면 GET /api/messages?room_id=...&after_id=<마지막 id> 폴링도 가능)

예약 (채팅으로):
  1. 답변 생성 서버가 음식점을 추천 (답변 본문에 places/ 목록의 식당 이름)
  2. 채팅 "@봇 내일 7시에 예약해줘" → 답변 서버로 안 보내고 이 서버가 처리
     - 그 방의 직전 봇 답변에 나온 식당 이름을 places/ 목록에서 찾아 예약
     - 날짜/시간/인원은 이 문장 → 없으면 추천 받기 전후 대화에서 찾음. 시간이 끝내 없으면 봇이 되물음
     - 참여자 = 방 멤버 전원 (봇 제외)
  3. 예약 + 참여자 저장 → MCP 서버 reserve 도구 호출 → 안내 문구를 봇 메시지로 채팅방에 올림 (웹소켓 푸시)
  4. 예약 카드에서 X → DELETE /api/reservations/{id}/participants/{user_id} 로 참여자 제외
  5. 참여자 각자 GET /api/reservations?user_name=<이름> 으로 자기 예약 장소 목록 조회
"""
import logging
import re
import socket
import threading
from collections import defaultdict
from datetime import datetime
from typing import Literal

import anyio.from_thread
import httpx
import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session, selectinload

import config
from database import (Message, Reservation, ReservationParticipant, Room, RoomMember, SessionLocal, User,
                      get_db, init_db)
from places import find_place_in_text, load_places
from when_parser import parse_when

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Kakao 장소추천 챗봇 - 채팅 저장 서버")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
init_db()


# ---------- 요청/응답 스키마 ----------
class Place(BaseModel):
    """직전 봇 답변에서 찾은 식당 (내부용). "@봇 예약해줘" 하면 이 식당을 예약한다."""
    place_id: str = Field(..., min_length=1, max_length=50, examples=["12345"], description="카카오 장소 ID")
    place_name: str = Field(..., min_length=1, max_length=200, examples=["성수 파스타집"])
    x: float | None = Field(None, ge=-180, le=180, description="경도 (선택)")
    y: float | None = Field(None, ge=-90, le=90, description="위도 (선택)")


class MessageIn(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=100, examples=["유림"])
    content: str = Field(..., min_length=1, examples=["@봇 성수동 분위기 좋은 카페 추천해줘"])
    room_id: int = Field(..., examples=[1], description="POST /api/rooms 로 만든 방의 id")


class MessageOut(BaseModel):
    id: int
    user_name: str
    room_id: int
    content: str
    created_at: datetime
    reservation_id: int | None = None    # 예약 안내 메시지면 그 예약 id
    # 저장 응답에서만 의미 있음: True면 봇을 호출했으니 곧 봇 답변이 올라옴 ("답변 중..." 표시용)
    bot_called: bool = False


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class RoomIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, examples=["해커톤 팀방"])
    member_names: list[str] = Field(default_factory=list, examples=[["유림", "민수"]])


class RoomRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, examples=["주말 강릉 여행"])


class MemberIn(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=100, examples=["민수"])


class MemberOut(BaseModel):
    user_id: int
    user_name: str
    joined_at: datetime


class RoomOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    members: list[MemberOut]


ReservationStatus = Literal["requested", "confirmed", "cancelled"]


class ReservationIn(BaseModel):
    room_id: int = Field(..., examples=[1], description="예약 안내를 올릴 채팅방 id")
    place_id: str = Field(..., min_length=1, max_length=50, examples=["12345"], description="카카오 장소 ID")
    place_name: str = Field(..., min_length=1, max_length=200, examples=["성수 파스타집"])
    reserved_at: datetime = Field(..., examples=["2026-11-08 19:00"], description="예약 일시")
    requested_by: str = Field(..., min_length=1, max_length=100, examples=["유림"], description="예약 요청자 이름")
    participant_names: list[str] | None = Field(
        None, examples=[["유림", "민수"]],
        description="참여자 이름 목록. 생략(null)하면 방 멤버 전원(봇 제외). 요청자는 항상 포함. 방 멤버만 가능")
    party_size: int | None = Field(None, ge=1, le=100, description="인원 수. 생략하면 참여자 수")


class ParticipantIn(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=100, examples=["지수"], description="다시 넣을 방 멤버 이름")


class ReservationStatusIn(BaseModel):
    status: ReservationStatus = Field(..., examples=["confirmed"], description="confirmed(확정) / cancelled(취소)")


class ParticipantOut(BaseModel):
    user_id: int
    user_name: str


class ReservationOut(BaseModel):
    id: int
    room_id: int
    place_id: str
    place_name: str
    reserved_at: datetime
    party_size: int
    requested_by: str
    participants: list[ParticipantOut]
    status: ReservationStatus
    link: str | None
    created_at: datetime
    message: str | None = None   # 생성/변경 응답에서만: 채팅방에 올린 안내 문구
    mcp_ok: bool | None = None   # 생성 응답에서만: MCP 서버 호출 성공 여부 (실패해도 예약은 저장됨)


def _to_out(m: Message, bot_called: bool = False) -> MessageOut:
    return MessageOut(
        id=m.id, user_name=m.user.name, room_id=m.room_id, content=m.content, created_at=m.created_at,
        reservation_id=m.reservation_id, bot_called=bot_called,
    )


def _reservation_out(r: Reservation, message: str | None = None, mcp_ok: bool | None = None) -> ReservationOut:
    return ReservationOut(
        id=r.id, room_id=r.room_id, place_id=r.place_id, place_name=r.place_name,
        reserved_at=r.reserved_at, party_size=r.party_size, requested_by=r.user.name,
        participants=[ParticipantOut(user_id=p.user_id, user_name=p.user.name)
                      for p in sorted(r.participants, key=lambda p: (p.user_id != r.user_id, p.user_id))],
        status=r.status, link=r.link, created_at=r.created_at, message=message, mcp_ok=mcp_ok,
    )


def _room_out(r: Room) -> RoomOut:
    return RoomOut(
        id=r.id, name=r.name, created_at=r.created_at,
        members=[MemberOut(user_id=m.user_id, user_name=m.user.name, joined_at=m.joined_at)
                 for m in sorted(r.members, key=lambda m: m.joined_at)],
    )


# ---------- DB 헬퍼 ----------
def _get_or_create_user(db: Session, name: str) -> User:
    name = name.strip()
    user = db.scalar(select(User).where(User.name == name))
    if user is None:
        user = User(name=name)
        db.add(user)
        db.flush()
    return user


def _require_room(db: Session, room_id: int) -> Room:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(404, f"방 {room_id} 이 없습니다. POST /api/rooms 로 먼저 만드세요.")
    return room


def _ensure_member(db: Session, room_id: int, user: User) -> None:
    """멤버 등록 (이미 멤버면 무시. 동시에 여러 요청이 와도 안전하도록 INSERT IGNORE)."""
    db.execute(mysql_insert(RoomMember).values(room_id=room_id, user_id=user.id).prefix_with("IGNORE"))


def _post_message(db: Session, background: BackgroundTasks | None, room_id: int, user_name: str, content: str,
                  reservation_id: int | None = None) -> MessageOut:
    """메시지 저장 + 그 방 웹소켓으로 푸시 (채팅 / 봇 답변 / 예약 안내 공통).
    background=None 은 이미 백그라운드 작업(스레드) 안이라는 뜻 → 바로 푸시."""
    user = _get_or_create_user(db, user_name)
    _ensure_member(db, room_id, user)
    msg = Message(user_id=user.id, room_id=room_id, content=content, reservation_id=reservation_id)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    out = _to_out(msg, _bot_will_reply(user.name, content))
    if background is not None:
        background.add_task(hub.broadcast, room_id, out.model_dump(mode="json"))
    else:
        anyio.from_thread.run(hub.broadcast, room_id, out.model_dump(mode="json"))
    return out


def _load_room(db: Session, room_id: int) -> Room | None:
    return db.scalar(select(Room).where(Room.id == room_id)
                     .options(selectinload(Room.members).selectinload(RoomMember.user))
                     .execution_options(populate_existing=True))


# ---------- 실시간 푸시 (웹소켓) ----------
class RoomHub:
    """방별로 연결된 웹소켓 목록. 새 메시지가 저장되면 그 방에 연결된 모두에게 바로 보낸다."""

    def __init__(self) -> None:
        self.rooms: dict[int, set[WebSocket]] = defaultdict(set)

    async def join(self, room_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self.rooms[room_id].add(ws)

    def leave(self, room_id: int, ws: WebSocket) -> None:
        self.rooms[room_id].discard(ws)
        if not self.rooms[room_id]:
            del self.rooms[room_id]

    async def broadcast(self, room_id: int, data: dict) -> None:
        for ws in list(self.rooms.get(room_id, ())):
            try:
                await ws.send_json(data)
            except Exception:  # 끊긴 연결은 정리
                self.leave(room_id, ws)


hub = RoomHub()


# ---------- 챗봇 호출 ----------
# "@봇 예약해줘 / 예약 좀 해줘 / 예약하자 / 예약 잡아줘 / 예약 부탁해" → 예약 요청
_RESERVE_RE = re.compile(r"예약\s*(?:을\s*)?(?:좀\s*)?(?:해|하자|할게|할래|부탁|ㄱ|잡아|진행|넣어)")


def _bot_mentioned(user_name: str, content: str) -> bool:
    # 봇이 쓴 메시지는 봇을 다시 부르지 않음 (무한루프 방지)
    return user_name != config.BOT_NAME and config.BOT_TRIGGER in content


def _is_reserve_request(user_name: str, content: str) -> bool:
    return _bot_mentioned(user_name, content) and bool(_RESERVE_RE.search(content))


def _should_call_bot(user_name: str, content: str) -> bool:
    """답변 생성 서버로 넘길지. 예약 요청은 이 서버가 직접 처리하므로 넘기지 않음."""
    return (bool(config.ANSWER_SERVER_URL) and _bot_mentioned(user_name, content)
            and not _is_reserve_request(user_name, content))


def _bot_will_reply(user_name: str, content: str) -> bool:
    """곧 봇 메시지가 올라오는지 (프론트 "봇이 답변 중..." 표시용)."""
    return _should_call_bot(user_name, content) or _is_reserve_request(user_name, content)


def _recent_context(db: Session, room_id: int) -> list[dict]:
    """그 방의 최근 대화 (오래된 → 최신 순). 답변 생성 서버의 ChatRequest.messages 형식."""
    rows = db.scalars(
        select(Message).where(Message.room_id == room_id)
        .order_by(Message.id.desc()).limit(config.CONTEXT_MESSAGES)
    ).all()
    return [{"user_name": m.user.name, "content": m.content} for m in reversed(rows)]


def _send_to_answer_server(payload: dict) -> None:
    """답변 생성 서버에 대화 전달. 답변은 그쪽이 나중에 POST /api/messages 로 보내준다."""
    url = f"{config.ANSWER_SERVER_URL}/api/chat"
    try:
        r = httpx.post(url, json=payload, timeout=config.ANSWER_TIMEOUT)
        r.raise_for_status()
        log.info("봇 호출 접수됨 (room=%s, %d개 메시지) → %s", payload["room_id"], len(payload["messages"]), r.text)
    except httpx.HTTPError as e:
        log.error("봇 호출 실패 (%s): %r", url, e)


# ---------- API: 기본 ----------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.id)).all()


# ---------- API: 채팅방 ----------
@app.post("/api/rooms", response_model=RoomOut)
def create_room(body: RoomIn, db: Session = Depends(get_db)):
    """채팅방 만들기 + 멤버 초대. 방 id 는 자동으로 붙어서 응답에 들어있음."""
    room = Room(name=body.name.strip())
    db.add(room)
    db.flush()
    for n in body.member_names:
        if n.strip():
            _ensure_member(db, room.id, _get_or_create_user(db, n))
    db.commit()
    return _room_out(_load_room(db, room.id))


@app.get("/api/rooms", response_model=list[RoomOut])
def list_rooms(user_name: str | None = None, db: Session = Depends(get_db)):
    """채팅방 목록 + 멤버. user_name 을 주면 그 사람이 속한 방만."""
    q = select(Room).options(selectinload(Room.members).selectinload(RoomMember.user)).order_by(Room.id)
    if user_name:
        q = q.join(RoomMember).join(User).where(User.name == user_name.strip())
    return [_room_out(r) for r in db.scalars(q).unique()]


@app.get("/api/rooms/{room_id}", response_model=RoomOut)
def get_room(room_id: int, db: Session = Depends(get_db)):
    _require_room(db, room_id)
    return _room_out(_load_room(db, room_id))


@app.patch("/api/rooms/{room_id}", response_model=RoomOut)
def rename_room(room_id: int, body: RoomRename, db: Session = Depends(get_db)):
    """방 이름 바꾸기."""
    _require_room(db, room_id).name = body.name.strip()
    db.commit()
    return _room_out(_load_room(db, room_id))


@app.post("/api/rooms/{room_id}/members", response_model=RoomOut)
def add_member(room_id: int, body: MemberIn, db: Session = Depends(get_db)):
    """방에 멤버 초대 (이미 멤버면 그대로)."""
    _require_room(db, room_id)
    _ensure_member(db, room_id, _get_or_create_user(db, body.user_name))
    db.commit()
    return _room_out(_load_room(db, room_id))


# ---------- API: 채팅 ----------
@app.post("/api/messages", response_model=MessageOut)
def save_message(body: MessageIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    """채팅 1건 저장. 방이 없으면 404. 처음 보는 유저면 자동 등록하고, 보낸 사람은 그 방 멤버로 자동 등록.
    - "@봇 ... 예약해줘" → 그 방에서 봇이 가장 최근에 추천한 식당을 예약 (이 서버가 처리)
    - 그 밖의 "@봇 ..." → 답변 생성 서버 호출
    - 봇 답변에 places/ 목록의 식당 이름이 나오면 "@봇 예약해줘" 로 그 식당을 예약할 수 있다."""
    _require_room(db, body.room_id)
    # 저장 즉시 그 방에 연결된 프론트들에게 푸시 (봇 답변도 이 경로로 저장되므로 생성 즉시 표시됨)
    out = _post_message(db, background, body.room_id, body.user_name, body.content)
    if _is_reserve_request(out.user_name, out.content):
        background.add_task(_reserve_from_chat, body.room_id, out.user_name, out.id)
    elif _should_call_bot(out.user_name, out.content):
        # 응답을 먼저 돌려주고, 답변 서버 호출은 뒤에서 처리 (프론트가 기다리지 않게)
        # 답변 생성 서버의 room_id 는 문자열 타입이라 str 로 변환해서 보냄
        background.add_task(_send_to_answer_server,
                            {"room_id": str(body.room_id), "messages": _recent_context(db, body.room_id)})
    return out


@app.get("/api/messages", response_model=list[MessageOut])
def list_messages(room_id: int | None = None, user_name: str | None = None,
                  after_id: int | None = None, limit: int = 50, db: Session = Depends(get_db)):
    """채팅 조회 (오래된 → 최신 순). room_id / user_name 으로 필터 가능.
    after_id 를 주면 그 id 이후의 새 메시지만 (웹소켓 재연결 후 놓친 메시지 받기용)."""
    q = select(Message).join(User)
    if room_id is not None:
        q = q.where(Message.room_id == room_id)
    if user_name:
        q = q.where(User.name == user_name)
    if after_id is not None:
        return [_to_out(m) for m in db.scalars(q.where(Message.id > after_id).order_by(Message.id).limit(limit))]
    rows = db.scalars(q.order_by(Message.id.desc()).limit(limit)).all()
    return [_to_out(m) for m in reversed(rows)]


# ---------- API: 예약 ----------
_self_mcp_lock = threading.Lock()
_self_mcp_calls: dict[str, int] = defaultdict(int)  # 방별로 이 서버가 지금 MCP reserve 를 부르는 중인 횟수


def _call_mcp_reserve(r: Reservation, requested_by: str) -> tuple[bool, str | None]:
    """MCP 서버 reserve 도구 호출 → (성공 여부, 안내 문구). 실제 예약은 하지 않는 데모용 도구."""
    if not config.MCP_SERVER_URL:
        return False, None
    url = f"{config.MCP_SERVER_URL}/tools/reserve"
    args = {
        "roomId": str(r.room_id), "place_id": r.place_id, "place_name": r.place_name,
        "datetime": r.reserved_at.strftime("%Y-%m-%d %H:%M"), "party_size": r.party_size,
        "requested_by": requested_by,
    }
    try:
        # MCP 서버는 reserve 처리 중에 POST /ai/notify 로 같은 문구를 이 서버에 보낸다.
        # 이 서버가 직접 부른 호출은 참여자·예약 id 를 붙여 따로 올리므로, 그 알림은 건너뛰게 표시해 둠
        with _self_mcp_lock:
            _self_mcp_calls[str(r.room_id)] += 1
        try:
            resp = httpx.post(url, json={"args": args}, timeout=config.MCP_TIMEOUT)
        finally:
            with _self_mcp_lock:
                _self_mcp_calls[str(r.room_id)] -= 1
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            log.error("MCP reserve 실패: %s", data.get("error"))
            return False, None
        log.info("MCP reserve 성공 (예약 %s)", r.id)
        return True, (data.get("result") or {}).get("message")
    except (httpx.HTTPError, ValueError) as e:
        log.error("MCP reserve 호출 실패 (%s): %r", url, e)
        return False, None


def _get_reservation(db: Session, reservation_id: int) -> Reservation:
    r = db.get(Reservation, reservation_id)
    if r is None:
        raise HTTPException(404, f"예약 {reservation_id} 이 없습니다.")
    return r


def _pick_participants(db: Session, room_id: int, requester: User, names: list[str] | None) -> list[User]:
    """참여자 결정. names 가 None 이면 방 멤버 전원(봇 제외). 요청자는 항상 포함(맨 앞). 방 멤버가 아닌 이름은 400."""
    room = _load_room(db, room_id)
    members = {m.user.name: m.user
               for m in sorted(room.members, key=lambda m: m.joined_at) if m.user.name != config.BOT_NAME}
    if names is not None:
        wanted = {n.strip() for n in names if n.strip()}
        unknown = sorted(wanted - members.keys())
        if unknown:
            raise HTTPException(400, f"방 {room_id} 의 멤버가 아닙니다: {', '.join(unknown)}")
        members = {n: u for n, u in members.items() if n in wanted}
    return [requester] + [u for u in members.values() if u.id != requester.id]


def _make_reservation(db: Session, background: BackgroundTasks | None, room_id: int, requester: User,
                      place_id: str, place_name: str, reserved_at: datetime,
                      participant_names: list[str] | None = None,
                      party_size: int | None = None) -> tuple[Reservation, str, bool]:
    """예약 + 참여자 저장 → MCP reserve 호출 → 안내 문구를 봇 메시지로 채팅방에 올림. (예약, 문구, MCP 성공)"""
    _ensure_member(db, room_id, requester)
    people = _pick_participants(db, room_id, requester, participant_names)
    place_id = place_id.strip()
    r = Reservation(
        room_id=room_id, user_id=requester.id, place_id=place_id, place_name=place_name.strip(),
        reserved_at=reserved_at.replace(tzinfo=None, second=0, microsecond=0),
        party_size=party_size or len(people),
        link=f"https://place.map.kakao.com/{place_id}",
        participants=[ReservationParticipant(user_id=u.id) for u in people],
    )
    db.add(r)
    db.commit()
    db.refresh(r)

    mcp_ok, text = _call_mcp_reserve(r, requester.name)
    if not text:
        text = (f"📅 {requester.name}님이 {r.place_name} {r.reserved_at:%Y-%m-%d %H:%M} {r.party_size}명 예약을 "
                f"요청했어요. 예약 링크: {r.link}")
    text += f"\n👥 참여: {', '.join(u.name for u in people)}"
    _post_message(db, background, room_id, config.BOT_NAME, text, reservation_id=r.id)
    _schedule_placelist(background, r.id)
    return r, text, mcp_ok


# ---------- placelist (카카오맵 목업) 온도 반영 ----------
# 데모에는 실제 "확정" 단계가 없으므로, 채팅에서 잡은 예약(requested)도 placelist 에는 확정으로 보낸다.
_PLACELIST_STATUS = {"requested": "confirmed", "confirmed": "confirmed", "cancelled": "cancelled"}


def _send_to_placelist(reservation_id: int) -> None:
    """예약 상태를 placelist POST /api/reservation 으로 알림 → 그 리스트 온도·랭킹에 반영. 실패해도 예약엔 영향 없음.
    reservation_id 는 "C<예약 id>" 로 보내서 같은 예약이 두 번 반영되지 않게 한다 (placelist 가 멱등 처리)."""
    with SessionLocal() as db:
        r = db.get(Reservation, reservation_id)
        if r is None:
            return
        src = next((p["list"] for p in load_places() if p["place_id"] == r.place_id), None)
        body = {
            "reservation_id": f"C{r.id}", "user": r.user.name,
            "place_id": f"k{r.place_id}", "place_name": r.place_name,
            "datetime": r.reserved_at.strftime("%Y-%m-%d %H:%M"), "party_size": r.party_size,
            "status": _PLACELIST_STATUS[r.status],
        }
        if src in config.PLACELIST_LISTS:
            body["list_id"] = config.PLACELIST_LISTS[src]
    url = f"{config.PLACELIST_URL}/api/reservation"
    try:
        resp = httpx.post(url, json=body, timeout=5)
        data = resp.json()
        fx = (data.get("event") or {}).get("effect") or {}
        log.info("placelist 반영 (예약 %s, %s) %s %s", reservation_id, body["status"], resp.status_code,
                 f"온도 {fx['list_temp'][0]} → {fx['list_temp'][1]}" if fx.get("list_temp") else data)
    except (httpx.HTTPError, ValueError) as e:
        log.error("placelist 반영 실패 (%s): %r", url, e)


def _schedule_placelist(background: BackgroundTasks | None, reservation_id: int) -> None:
    if not config.PLACELIST_URL:
        return
    if background is not None:
        background.add_task(_send_to_placelist, reservation_id)
    else:  # 이미 백그라운드 작업 안 ("@봇 예약해줘")
        _send_to_placelist(reservation_id)


def _find_recommendation(db: Session, room_id: int, before_id: int) -> tuple[Message, Place] | None:
    """직전 봇 답변에서 추천 식당 찾기.
    본문에 나온 식당 이름을 places/ 목록에서 찾음 (가장 먼저 언급된 곳)
    이 서버가 올린 안내(예약/택시 알림, "못 찾았어요" 등)는 건너뛰고, 그 앞의 진짜 답변 하나만 본다.
    그 답변에 아는 식당이 없으면 None (더 예전 답변의 식당을 잘못 예약하지 않게)."""
    bot_msgs = db.scalars(
        select(Message).join(User)
        .where(Message.room_id == room_id, Message.id < before_id, User.name == config.BOT_NAME,
               Message.reservation_id.is_(None))
        .order_by(Message.id.desc()).limit(10)).all()
    for m in bot_msgs:
        if m.content.startswith(_SYSTEM_PREFIXES):
            continue
        if p := find_place_in_text(m.content):
            return m, Place(place_id=str(p["place_id"]), place_name=p["place_name"], x=p.get("x"), y=p.get("y"))
        return None
    return None


# 이 서버(또는 MCP 알림)가 올리는 봇 안내 문구의 시작. 추천 답변이 아니므로 "직전 답변" 찾을 때 건너뜀
_SYSTEM_PREFIXES = ("예약할 식당을 못 찾았어요", "예약 중에 문제가", "📅", "🚕", "✅", "❌", "👋", "🙌", "ℹ️")


def _reserve_from_chat(room_id: int, requester_name: str, request_msg_id: int) -> None:
    """"@봇 ... 예약해줘" 처리 (백그라운드). 그 방에서 봇이 가장 최근에 추천한 식당을 예약한다."""
    with SessionLocal() as db:
        try:
            found = _find_recommendation(db, room_id, request_msg_id)
            if found is None:
                _post_message(db, None, room_id, config.BOT_NAME,
                              "예약할 식당을 못 찾았어요 🥲 먼저 \"@봇 OO 맛집 추천해줘\"로 식당을 추천받은 뒤 "
                              "\"@봇 내일 저녁 7시에 예약해줘\"라고 말해 주세요.")
                return
            rec, place = found

            # 날짜/시간/인원: 이 요청 → 추천 받기 직전의 봇 메시지 이후 대화 (최신 → 오래된 순)
            prev_bot_id = db.scalar(
                select(Message.id).join(User)
                .where(Message.room_id == room_id, Message.id < rec.id, User.name == config.BOT_NAME)
                .order_by(Message.id.desc()).limit(1)) or 0
            talk = db.scalars(
                select(Message).join(User)
                .where(Message.room_id == room_id, Message.id > prev_bot_id, Message.id <= request_msg_id,
                       User.name != config.BOT_NAME)
                .order_by(Message.id.desc()).limit(config.CONTEXT_MESSAGES)).all()
            when, party = parse_when([(m.content, m.created_at) for m in talk], datetime.now())
            if when is None:
                _post_message(db, None, room_id, config.BOT_NAME,
                              f"{place.place_name} 몇 시로 예약할까요? ⏰\n예) \"@봇 내일 저녁 7시에 예약해줘\"")
                return

            # 같은 말을 두 번 해서 같은 예약이 또 생기지 않게
            dup = db.scalar(select(Reservation).where(
                Reservation.room_id == room_id, Reservation.place_id == place.place_id,
                Reservation.reserved_at == when, Reservation.status != "cancelled"))
            if dup is not None:
                _post_message(db, None, room_id, config.BOT_NAME,
                              f"{dup.place_name} {dup.reserved_at:%m월 %d일 %H:%M} 예약은 이미 돼 있어요 🙂",
                              reservation_id=dup.id)
                return

            requester = _get_or_create_user(db, requester_name)
            _make_reservation(db, None, room_id, requester, place.place_id, place.place_name, when, party_size=party)
        except Exception:
            log.exception("채팅 예약 처리 실패 (room=%s, msg=%s)", room_id, request_msg_id)
            db.rollback()
            _post_message(db, None, room_id, config.BOT_NAME, "예약 중에 문제가 생겼어요 😢 잠시 후 다시 말해 주세요.")


@app.post("/api/reservations", response_model=ReservationOut)
def create_reservation(body: ReservationIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    """(선택) 화면에서 직접 예약할 때. 보통은 채팅 "@봇 내일 7시에 예약해줘" 로 예약된다.
    참여자: participant_names 생략 시 방 멤버 전원(봇 제외).
    예약 + 참여자를 저장하고 MCP 서버 reserve 도구를 호출한 뒤, 안내 문구를 봇 메시지로 채팅방에 올린다.
    MCP 서버가 꺼져 있어도 예약은 저장되고 안내 문구는 이 서버가 만든다 (mcp_ok=false)."""
    _require_room(db, body.room_id)
    requester = _get_or_create_user(db, body.requested_by)
    r, text, mcp_ok = _make_reservation(db, background, body.room_id, requester, body.place_id, body.place_name,
                                        body.reserved_at, body.participant_names, body.party_size)
    return _reservation_out(_get_reservation(db, r.id), message=text, mcp_ok=mcp_ok)


@app.get("/api/reservations", response_model=list[ReservationOut])
def list_reservations(room_id: int | None = None, user_name: str | None = None,
                      status: ReservationStatus | None = None, db: Session = Depends(get_db)):
    """예약 목록 (예약 일시 순). user_name 을 주면 그 사람이 참여자인 예약만 (= 그 계정의 예약 장소 목록).
    room_id / status 로도 필터 가능. 취소된 것까지 오니 화면에서 숨기려면 status 로 걸러서 쓰기."""
    q = (select(Reservation)
         .options(selectinload(Reservation.participants).selectinload(ReservationParticipant.user),
                  selectinload(Reservation.user))
         .order_by(Reservation.reserved_at, Reservation.id))
    if room_id is not None:
        q = q.where(Reservation.room_id == room_id)
    if user_name:
        q = q.where(Reservation.participants.any(
            ReservationParticipant.user.has(User.name == user_name.strip())))
    if status:
        q = q.where(Reservation.status == status)
    return [_reservation_out(r) for r in db.scalars(q)]


@app.get("/api/reservations/{reservation_id}", response_model=ReservationOut)
def get_reservation(reservation_id: int, db: Session = Depends(get_db)):
    return _reservation_out(_get_reservation(db, reservation_id))


@app.patch("/api/reservations/{reservation_id}", response_model=ReservationOut)
def update_reservation_status(reservation_id: int, body: ReservationStatusIn, background: BackgroundTasks,
                              db: Session = Depends(get_db)):
    """예약 확정/취소 (카카오맵 목업에서 호출). 상태가 바뀌면 채팅방에 봇 안내 메시지를 올린다."""
    r = _get_reservation(db, reservation_id)
    if r.status == body.status:
        return _reservation_out(r)
    r.status = body.status
    db.commit()
    when = f"{r.reserved_at:%m월 %d일 %H:%M}"
    text = {
        "confirmed": f"✅ {r.place_name} {when} {r.party_size}명 예약이 확정됐어요!",
        "cancelled": f"❌ {r.place_name} {when} {r.party_size}명 예약이 취소됐어요.",
        "requested": f"📅 {r.place_name} {when} {r.party_size}명 예약이 다시 요청됐어요.",
    }[r.status]
    _post_message(db, background, r.room_id, config.BOT_NAME, text, reservation_id=r.id)
    _schedule_placelist(background, r.id)
    return _reservation_out(_get_reservation(db, r.id), message=text)


@app.delete("/api/reservations/{reservation_id}/participants/{user_id}", response_model=ReservationOut)
def remove_participant(reservation_id: int, user_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    """예약 카드에서 참여자 칩의 X. 그 사람 계정의 예약 목록에서 빠지고, 인원이 1 줄고, 채팅방에 안내가 올라간다.
    예약한 사람(requested_by)은 뺄 수 없음 (400)."""
    r = _get_reservation(db, reservation_id)
    p = next((p for p in r.participants if p.user_id == user_id), None)
    if p is None:
        raise HTTPException(404, f"user_id {user_id} 는 예약 {reservation_id} 의 참여자가 아닙니다.")
    if user_id == r.user_id:
        raise HTTPException(400, "예약한 사람은 뺄 수 없어요. 예약을 취소하려면 PATCH 로 status=cancelled.")
    name = p.user.name
    r.participants.remove(p)
    r.party_size = max(1, r.party_size - 1)
    db.commit()
    text = f"👋 {name}님이 {r.place_name} 예약에서 빠졌어요. (이제 {r.party_size}명)"
    _post_message(db, background, r.room_id, config.BOT_NAME, text, reservation_id=r.id)
    return _reservation_out(_get_reservation(db, r.id), message=text)


@app.post("/api/reservations/{reservation_id}/participants", response_model=ReservationOut)
def add_participant(reservation_id: int, body: ParticipantIn, background: BackgroundTasks,
                    db: Session = Depends(get_db)):
    """X 로 뺀 사람 다시 넣기 (방 멤버만). 인원이 1 늘고 채팅방에 안내가 올라간다."""
    r = _get_reservation(db, reservation_id)
    [user] = _pick_participants(db, r.room_id, r.user, [body.user_name])[1:] or [None]
    if user is None:
        raise HTTPException(400, "예약한 사람은 이미 참여자예요.")
    if any(p.user_id == user.id for p in r.participants):
        return _reservation_out(r)
    r.participants.append(ReservationParticipant(user_id=user.id))
    r.party_size += 1
    db.commit()
    text = f"🙌 {user.name}님이 {r.place_name} 예약에 함께해요. (이제 {r.party_size}명)"
    _post_message(db, background, r.room_id, config.BOT_NAME, text, reservation_id=r.id)
    return _reservation_out(_get_reservation(db, r.id), message=text)


@app.get("/api/places")
def list_places():
    """데모 식당 목록 (places/*.json, 메뉴 등 상세 제외). 봇 답변에 이 이름이 나오면 "@봇 예약해줘" 로 예약 가능."""
    return load_places()


# ---------- API: MCP 서버 알림 ----------
NOTIFY_TYPES = ("reserve", "taxi", "info")


def _notify_room(room_id: int, text: str) -> bool:
    """방에 봇 메시지로 text 를 그대로 올리고 웹소켓 푸시. 방이 없으면 False."""
    with SessionLocal() as db:
        if db.get(Room, room_id) is None:
            return False
        _post_message(db, None, room_id, config.BOT_NAME, text)
        return True


@app.post("/ai/notify")
async def ai_notify(request: Request):
    """쩝쩝박사 MCP 서버 → 이 서버. AI 가 예약/택시 도구를 부르면 그 안내 문구(text)를 그 방에 봇 메시지로 그대로 띄운다.
    본문 {roomId: str, type: "reserve"|"taxi"|"info", text: str, payload: object}. 인증 없음(내부망).
    응답: 200 {ok:true} / 400 형식 오류 / 422 방 없음 / 500 내부 오류 (모두 {ok:false, error})."""
    def fail(code: int, error: str, room="-", typ="-") -> JSONResponse:
        log.info("notify room=%s type=%s ok=False (%s)", room, typ, error)
        return JSONResponse({"ok": False, "error": error}, status_code=code)

    try:
        body = await request.json()
    except Exception:
        return fail(400, "invalid JSON body")
    if not isinstance(body, dict):
        return fail(400, "body must be a JSON object")
    missing = [k for k in ("roomId", "type", "text", "payload") if k not in body]
    if missing:
        return fail(400, f"missing field: {', '.join(missing)}")
    room, typ, text, payload = body["roomId"], body["type"], body["text"], body["payload"]
    if not isinstance(room, str) or not room.strip():
        return fail(400, "roomId must be a non-empty string")
    if typ not in NOTIFY_TYPES:
        return fail(400, f"type must be one of {', '.join(NOTIFY_TYPES)}", room)
    if not isinstance(text, str) or not text.strip():
        return fail(400, "text must be a non-empty string", room, typ)
    if not isinstance(payload, dict):
        return fail(400, "payload must be an object", room, typ)
    if not room.strip().isdigit():  # 이 서버의 방 id 는 숫자 ("1", "2", ...)
        return fail(422, "room not found", room, typ)

    # 이 서버가 직접 부른 reserve 의 알림이면 이미 (참여자·예약 id 포함) 안내를 올리므로 건너뜀
    with _self_mcp_lock:
        own_call = typ == "reserve" and _self_mcp_calls[room.strip()] > 0
    if own_call:
        log.info("notify room=%s type=%s ok=True (이 서버가 부른 예약이라 표시 생략)", room, typ)
        return {"ok": True}

    try:
        found = await run_in_threadpool(_notify_room, int(room), text)
    except Exception as e:
        log.exception("notify 처리 실패")
        return fail(500, f"internal error: {e.__class__.__name__}", room, typ)
    if not found:
        return fail(422, "room not found", room, typ)
    log.info("notify room=%s type=%s ok=True", room, typ)
    return {"ok": True}


@app.websocket("/ws/{room_id}")
async def room_socket(ws: WebSocket, room_id: int):
    """실시간 수신용. 연결해두면 이 방에 저장되는 새 메시지(봇 답변 포함)가 MessageOut JSON으로 바로 온다.
    보내기는 계속 POST /api/messages 사용. 클라이언트가 보내는 텍스트는 무시(연결 유지용 ping 정도로만)."""
    await hub.join(room_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.leave(room_id, ws)


# ---------- 실행 ----------
def _local_ip() -> str:
    """현재 연결된 네트워크(와이파이 등)에서의 내 IP 추정. 실제 패킷은 안 보냄."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    shown = _local_ip() if config.HOST == "0.0.0.0" else config.HOST
    print(f"\n  프론트에 알려줄 주소 →  http://{shown}:{config.PORT}")
    print(f"  API 문서            →  http://{shown}:{config.PORT}/docs")
    print(f"  실시간 수신         →  ws://{shown}:{config.PORT}/ws/<room_id>")
    if config.ANSWER_SERVER_URL:
        print(f"  답변 생성 서버      →  {config.ANSWER_SERVER_URL}  (호출어: {config.BOT_TRIGGER}, 봇 이름: {config.BOT_NAME})\n", flush=True)
    else:
        print("  답변 생성 서버      →  (미설정: .env 의 ANSWER_SERVER_URL 을 넣으면 봇 호출 활성화)\n", flush=True)
    mcp = config.MCP_SERVER_URL or "(미설정: 예약은 저장만, 안내 문구는 이 서버가 생성)"
    print(f"  예약 MCP 서버       →  {mcp}", flush=True)
    print(f"  데모 식당 목록      →  {config.PLACES_FILE} ({len(load_places())}곳)", flush=True)
    print(f"  placelist 온도 반영 →  {config.PLACELIST_URL or '(미설정)'}\n", flush=True)
    uvicorn.run(app, host=config.HOST, port=config.PORT)
