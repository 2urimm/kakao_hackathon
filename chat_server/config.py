"""환경변수 기반 설정. 값은 .env 파일이나 실행 시 환경변수로 넣는다 (하드코딩 금지)."""
import os

from dotenv import load_dotenv
from sqlalchemy import URL

load_dotenv()

# API 서버
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))
CORS_ORIGINS: list[str] = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

# 챗봇 (답변 생성 서버)
ANSWER_SERVER_URL: str = os.getenv("ANSWER_SERVER_URL", "").rstrip("/")  # 예: http://192.168.x.x:8000
# 채팅에 이 단어 중 하나가 있으면 봇 호출 (쉼표로 여러 개). 첫 번째가 대표 호출어 (안내 문구에 사용)
BOT_TRIGGERS: list[str] = [t.strip() for t in os.getenv("BOT_TRIGGER", "@톡스픽").split(",") if t.strip()]
BOT_TRIGGER: str = BOT_TRIGGERS[0]
BOT_NAME: str = os.getenv("BOT_NAME", "톡스픽")          # 봇 메시지의 user_name (이 이름의 메시지는 봇을 다시 부르지 않음)
# 이 이름으로 온 메시지도 봇으로 보고 BOT_NAME 으로 저장 (답변 서버가 예전 이름 "봇"으로 보내도 됨)
BOT_ALIASES: set[str] = {a.strip() for a in os.getenv("BOT_ALIASES", "봇").split(",") if a.strip()}
CONTEXT_MESSAGES: int = int(os.getenv("CONTEXT_MESSAGES", "20"))  # 봇에게 넘길 최근 대화 개수
ANSWER_TIMEOUT: float = float(os.getenv("ANSWER_TIMEOUT", "10"))  # 답변 서버 접수 대기 시간(초)

# 예약 (쩝쩝박사 MCP 서버의 reserve 도구)
MCP_SERVER_URL: str = os.getenv("MCP_SERVER_URL", "").rstrip("/")  # 예: http://192.168.x.x:8100. 비우면 MCP 없이 예약만 저장
MCP_TIMEOUT: float = float(os.getenv("MCP_TIMEOUT", "10"))
# 데모 식당 목록 (카카오맵 추출 JSON). 봇 답변에 이 목록의 식당 이름이 나오면 "@톡스픽 예약해줘" 로 예약 가능
PLACES_FILE: str = os.getenv("PLACES_FILE", "places")  # 폴더면 안의 *.json 전부

# placelist (카카오맵 목업) 서버. 예약이 생기거나 취소되면 POST /api/reservation 으로 알려 리스트 온도에 반영
PLACELIST_URL: str = os.getenv("PLACELIST_URL", "").rstrip("/")  # 예: http://192.168.x.x:8200. 비우면 안 보냄
# 식당 목록 파일(places/<이름>_places.json) → placelist 리스트 id. "이 리스트를 보고 예약했다"로 온도에 반영
PLACELIST_LISTS: dict[str, str] = dict(
    kv.split(":", 1) for kv in os.getenv("PLACELIST_LISTS", "mapo:M01,seocho:S01,busan_1:B02,busan_2:B01").split(",") if ":" in kv)

# MySQL
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
DB_USER: str = os.getenv("DB_USER", "kakao_app")
DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
DB_NAME: str = os.getenv("DB_NAME", "kakao_chatbot")

# URL.create 는 비밀번호에 특수문자가 있어도 알아서 처리해줌
DATABASE_URL = URL.create(
    "mysql+pymysql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
    query={"charset": "utf8mb4"},  # 한글/이모지 저장용
)
