# 카카오 장소추천 챗봇 – 채팅 저장 서버

프론트에서 받은 채팅(유저 이름 + 내용)을 MySQL에 저장하는 FastAPI 서버.
MySQL은 서버 PC에서 돌고, 팀원들은 핫스팟 IP로 DB에 직접 접속해서 볼 수 있음.

## 처음 한 번 설정

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # DB_PASSWORD 등 수정
python setup_mysql.py           # MySQL root 비밀번호 입력 → DB + 팀 공용 계정 생성
```

## 실행

```bash
python main.py
```

시작하면 `프론트에 알려줄 주소 → http://192.168.x.x:8000` 이 출력됨. 핫스팟에 연결된 상태에서 이 주소를 프론트 담당자에게 공유.

- 설정은 전부 `.env` 또는 환경변수 (`HOST`, `PORT`, `CORS_ORIGINS`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`)
- 테이블은 서버 처음 실행할 때 자동 생성
- 다른 기기에서 접속이 안 되면 Windows 방화벽에서 Python 허용(개인 네트워크) 확인

## 팀원이 DB 직접 보기 (MySQL Workbench / DBeaver 등)

| 항목 | 값 |
|---|---|
| Host | 서버 PC의 핫스팟 IP (`python main.py` 실행 시 출력되는 IP) |
| Port | 3306 |
| User | `.env`의 `DB_USER` (기본 `kakao_app`) |
| Password | `.env`의 `DB_PASSWORD` (서버 담당자에게 받기) |
| Database | `kakao_chatbot` |

접속이 안 되면 서버 PC에서 **관리자 PowerShell**로 3306 포트를 열어야 함:
```powershell
New-NetFirewallRule -DisplayName "MySQL 3306" -Direction Inbound -Protocol TCP -LocalPort 3306 -Action Allow -Profile Private,Public
```
해커톤 끝나면 `Remove-NetFirewallRule -DisplayName "MySQL 3306"` 으로 닫기.

## API (프론트 담당자용)

전체 문서/테스트 화면: `http://<서버IP>:<PORT>/docs`

### 채팅 저장 `POST /api/messages`
```json
{ "user_name": "유림", "content": "성수동 카페 추천해줘", "room_id": "room1" }
```
- `room_id`는 생략 가능 (기본 `"default"`)
- 처음 보는 `user_name`이면 자동으로 유저 등록

응답:
```json
{ "id": 1, "user_name": "유림", "room_id": "room1", "content": "성수동 카페 추천해줘", "created_at": "2026-11-06T15:50:34" }
```

### 채팅 조회 `GET /api/messages?room_id=room1&user_name=유림&limit=50`
모든 파라미터 선택. 오래된 → 최신 순으로 최근 `limit`개.

### 유저 목록 `GET /api/users`

### 헬스체크 `GET /health`

## DB 구조

| users | | messages | |
|---|---|---|---|
| id | PK | id | PK |
| name | unique | user_id | FK → users.id |
| created_at | | room_id | 카톡방 구분 |
| | | content | 채팅 내용 |
| | | created_at | |
