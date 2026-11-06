"""DB 연결 + 테이블 정의.

users ─┬─< room_members >─┬─ rooms
       └──── messages ────┘
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from config import DATABASE_URL

# pool_pre_ping: 와이파이가 잠깐 끊겼다 붙어도 죽은 연결을 자동으로 버리고 새로 연결
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    messages: Mapped[list["Message"]] = relationship(back_populates="user")
    memberships: Mapped[list["RoomMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Room(Base):
    """채팅방. id 는 프론트가 보내는 room_id 문자열 그대로 사용 (예: "1", "hackathon-room")."""
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100))  # 화면 표시용 방 이름 (선택)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    members: Mapped[list["RoomMember"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="room")


class RoomMember(Base):
    """채팅방 멤버 (방 ↔ 사용자 다대다). 같은 사람이 같은 방에 두 번 들어갈 수 없음."""
    __tablename__ = "room_members"

    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    room: Mapped[Room] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)  # 서버 로컬시간(KST)

    user: Mapped[User] = relationship(back_populates="messages")
    room: Mapped[Room] = relationship(back_populates="messages")


def init_db() -> None:
    Base.metadata.create_all(engine)  # 없는 테이블(rooms, room_members)만 새로 만듦
    _migrate_rooms()


def _migrate_rooms() -> None:
    """rooms 테이블이 생기기 전에 쌓인 채팅을 새 구조로 옮긴다. 여러 번 실행해도 안전.
    1) messages 에 있는 room_id 로 rooms 행 생성
    2) 그 방에 채팅을 쓴 사람을 room_members 로 등록
    3) messages.room_id → rooms.id 외래키가 없으면 추가
    """
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT IGNORE INTO rooms (id, created_at) "
            "SELECT room_id, MIN(created_at) FROM messages GROUP BY room_id"))
        conn.execute(text(
            "INSERT IGNORE INTO room_members (room_id, user_id, joined_at) "
            "SELECT room_id, user_id, MIN(created_at) FROM messages GROUP BY room_id, user_id"))
        fks = inspect(conn).get_foreign_keys("messages")
        if not any(fk["referred_table"] == "rooms" for fk in fks):
            conn.execute(text(
                "ALTER TABLE messages ADD CONSTRAINT fk_messages_room "
                "FOREIGN KEY (room_id) REFERENCES rooms (id)"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
