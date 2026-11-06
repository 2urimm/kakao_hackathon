"""MySQL에 DB와 팀 공용 계정을 한 번만 만들어주는 스크립트.

실행:  .venv\\Scripts\\python setup_mysql.py
 - MySQL root 비밀번호를 물어봄 (화면에 안 보임, 저장 안 함)
 - .env 의 DB_NAME / DB_USER / DB_PASSWORD 로 DB와 계정을 생성
 - 계정은 '%' 호스트로 만들어서 핫스팟에 붙은 팀원 PC에서도 접속 가능
여러 번 실행해도 안전함 (이미 있으면 비밀번호만 .env 값으로 맞춤).
"""
import getpass

import pymysql

import config

if not config.DB_PASSWORD or config.DB_PASSWORD == "여기에_비밀번호":
    raise SystemExit(".env 에 DB_PASSWORD 를 먼저 설정하세요.")

root_pw = getpass.getpass(f"MySQL root 비밀번호 ({config.DB_HOST}:{config.DB_PORT}): ")
conn = pymysql.connect(host=config.DB_HOST, port=config.DB_PORT, user="root", password=root_pw)
try:
    with conn.cursor() as cur:
        db, user = config.DB_NAME, config.DB_USER
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cur.execute("CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s", (user, config.DB_PASSWORD))
        cur.execute("ALTER USER %s@'%%' IDENTIFIED BY %s", (user, config.DB_PASSWORD))
        cur.execute(f"GRANT ALL PRIVILEGES ON `{db}`.* TO %s@'%%'", (user,))
        cur.execute("FLUSH PRIVILEGES")
    conn.commit()
finally:
    conn.close()

print(f"완료: DB `{config.DB_NAME}`, 계정 `{config.DB_USER}` (모든 IP에서 접속 가능)")
