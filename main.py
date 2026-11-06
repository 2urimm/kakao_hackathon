"""채팅 수신/저장 서버.

실행:  python main.py
문서:  http://<서버IP>:<PORT>/docs   (프론트 담당자에게 이 주소 공유)
"""
import socket
from datetime import datetime

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

import config
from database import Message, User, get_db, init_db

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
    content: str = Field(..., min_length=1, examples=["성수동 분위기 좋은 카페 추천해줘"])
    room_id: str = Field("default", max_length=100, examples=["hackathon-room"])


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_name: str
    room_id: str
    content: str
    created_at: datetime


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


def _to_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id, user_name=m.user.name, room_id=m.room_id, content=m.content, created_at=m.created_at
    )


# ---------- API ----------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/messages", response_model=MessageOut)
def save_message(body: MessageIn, db: Session = Depends(get_db)):
    """채팅 1건 저장. 처음 보는 유저 이름이면 users 테이블에 자동 등록."""
    name = body.user_name.strip()
    user = db.scalar(select(User).where(User.name == name))
    if user is None:
        user = User(name=name)
        db.add(user)
        db.flush()

    msg = Message(user_id=user.id, room_id=body.room_id, content=body.content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return _to_out(msg)


@app.get("/api/messages", response_model=list[MessageOut])
def list_messages(room_id: str | None = None, user_name: str | None = None, limit: int = 50,
                  db: Session = Depends(get_db)):
    """최근 채팅 조회 (오래된 → 최신 순). room_id / user_name 으로 필터 가능."""
    q = select(Message).join(User)
    if room_id:
        q = q.where(Message.room_id == room_id)
    if user_name:
        q = q.where(User.name == user_name)
    rows = db.scalars(q.order_by(Message.id.desc()).limit(limit)).all()
    return [_to_out(m) for m in reversed(rows)]


@app.get("/api/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.id)).all()


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
    print(f"  API 문서            →  http://{shown}:{config.PORT}/docs\n", flush=True)
    uvicorn.run(app, host=config.HOST, port=config.PORT)
