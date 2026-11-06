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
"""
import logging
import socket
from collections import defaultdict
from datetime import datetime

import httpx
import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session, selectinload

import config
from database import Message, Room, RoomMember, User, get_db, init_db

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


def _to_out(m: Message, bot_called: bool = False) -> MessageOut:
    return MessageOut(
        id=m.id, user_name=m.user.name, room_id=m.room_id, content=m.content,
        created_at=m.created_at, bot_called=bot_called,
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
def _should_call_bot(user_name: str, content: str) -> bool:
    return (
        bool(config.ANSWER_SERVER_URL)
        and user_name != config.BOT_NAME          # 봇 답변이 봇을 다시 부르는 무한루프 방지
        and config.BOT_TRIGGER in content
    )


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
    내용에 BOT_TRIGGER(기본 "@봇")가 있으면 답변 생성 서버를 호출한다."""
    _require_room(db, body.room_id)
    user = _get_or_create_user(db, body.user_name)
    _ensure_member(db, body.room_id, user)

    msg = Message(user_id=user.id, room_id=body.room_id, content=body.content)
    db.add(msg)
    db.commit()
    db.refresh(msg)

    bot_called = _should_call_bot(user.name, body.content)
    out = _to_out(msg, bot_called)
    # 그 방에 연결된 프론트들에게 바로 푸시 (봇 답변도 이 경로로 저장되므로 생성 즉시 표시됨)
    background.add_task(hub.broadcast, body.room_id, out.model_dump(mode="json"))
    if bot_called:
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
    uvicorn.run(app, host=config.HOST, port=config.PORT)
