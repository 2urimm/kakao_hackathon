"""DB 연결 + 테이블 정의.

users ─┬─< room_members >─┬─ rooms
       ├──── messages ────┤
       └── reservations ──┘
             └─< reservation_participants >── users
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine
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
    """채팅방. id 는 자동 증가 숫자, name 은 화면에 보이는 방 이름 (필수, 중복 가능)."""
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    members: Mapped[list["RoomMember"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="room")
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="room")


class RoomMember(Base):
    """채팅방 멤버 (방 ↔ 사용자 다대다). 같은 사람이 같은 방에 두 번 들어갈 수 없음."""
    __tablename__ = "room_members"

    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    room: Mapped[Room] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)  # 서버 로컬시간(KST)

    # 봇이 음식점을 추천한 메시지면 그 장소 정보 (프론트가 "예약하기" 버튼을 띄우는 데 사용). 일반 채팅은 NULL
    place_id: Mapped[str | None] = mapped_column(String(50))
    place_name: Mapped[str | None] = mapped_column(String(200))
    place_x: Mapped[float | None] = mapped_column(Float)  # 경도
    place_y: Mapped[float | None] = mapped_column(Float)  # 위도
    # 예약 안내 메시지(봇)면 그 예약 id. 일반 채팅은 NULL
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id", ondelete="SET NULL"))

    user: Mapped[User] = relationship(back_populates="messages")
    room: Mapped[Room] = relationship(back_populates="messages")


class Reservation(Base):
    """음식점 예약. 실제 예약은 하지 않는 데모용 (MCP reserve 도구로 카톡방에 알림 + 카카오맵 링크)."""
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # 예약 요청자
    place_id: Mapped[str] = mapped_column(String(50))
    place_name: Mapped[str] = mapped_column(String(200))
    reserved_at: Mapped[datetime] = mapped_column(DateTime)      # 예약 일시
    party_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="requested")  # requested / confirmed / cancelled
    link: Mapped[str | None] = mapped_column(String(300))       # 카카오맵 장소 링크
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    room: Mapped[Room] = relationship(back_populates="reservations")
    user: Mapped[User] = relationship()
    participants: Mapped[list["ReservationParticipant"]] = relationship(
        back_populates="reservation", cascade="all, delete-orphan")


class ReservationParticipant(Base):
    """예약 참여자 (예약 ↔ 사용자 다대다). 여기 들어간 사람들의 계정에 예약 장소가 뜬다."""
    __tablename__ = "reservation_participants"

    reservation_id: Mapped[int] = mapped_column(ForeignKey("reservations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)

    reservation: Mapped[Reservation] = relationship(back_populates="participants")
    user: Mapped[User] = relationship()


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
