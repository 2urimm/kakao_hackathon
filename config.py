"""환경변수 기반 설정. 값은 .env 파일이나 실행 시 환경변수로 넣는다 (하드코딩 금지)."""
import os

from dotenv import load_dotenv
from sqlalchemy import URL

load_dotenv()

# API 서버
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))
CORS_ORIGINS: list[str] = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

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
