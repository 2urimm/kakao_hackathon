# 카카오 장소추천 챗봇 – 채팅 저장 서버

프론트에서 받은 채팅(유저 이름 + 내용)을 MySQL에 저장하는 FastAPI 서버.
MySQL은 서버 PC에서 돌고, 같은 와이파이에 연결된 팀원들은 서버 PC의 IP로 DB에 직접 접속해서 볼 수 있음.

> 모든 팀원이 **같은 와이파이(건물 와이파이 또는 핫스팟)** 에 연결돼 있어야 함.

## 처음 한 번 설정 (서버 PC)

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

시작하면 `프론트에 알려줄 주소 → http://192.168.x.x:8000` 이 출력됨. 이 주소를 프론트 담당자에게 공유.

- 설정은 전부 `.env` 또는 환경변수 (`HOST`, `PORT`, `CORS_ORIGINS`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`)
- 테이블은 서버 처음 실행할 때 자동 생성
- 코드를 고쳤으면 서버를 껐다(`Ctrl+C`) 다시 켜야 반영됨
- 와이파이를 바꾸거나 다시 연결하면 IP가 바뀔 수 있음 → 코드 수정 없이 새로 출력된 IP만 다시 공유

## 팀원이 받아서 쓰려면

1. 저장소를 clone한 뒤 `.env.example`을 복사해 `.env`를 만든다.
   ```bash
   git clone https://github.com/2urimm/kakao_hackathon.git
   cd kakao_hackathon
   cp .env.example .env
   ```
2. `.env`의 `DB_PASSWORD`에는 서버 담당자가 따로 알려준 비밀번호를 넣는다. (카톡 등으로 직접 전달 — 비밀번호는 깃허브에 올리지 않음)
3. 서버 담당자 PC의 MySQL에 붙는 거라면 `.env`의 `DB_HOST`에 서버 담당자 PC의 IP를 넣는다.
   ```
   DB_HOST=192.168.x.x
   ```

## 팀원이 DB 직접 보기 (MySQL Workbench / DBeaver 등)

| 항목 | 값 |
|---|---|
| Host | 서버 PC의 IP (`python main.py` 실행 시 출력되는 IP) |
| Port | 3306 |
| User | `.env`의 `DB_USER` (기본 `kakao_app`) |
| Password | `.env`의 `DB_PASSWORD` (서버 담당자에게 받기) |
| Database | `kakao_chatbot` |

## 접속이 안 될 때

1. **방화벽** – 서버 PC에서 **관리자 PowerShell**로 포트를 연다.
   ```powershell
   New-NetFirewallRule -DisplayName "Kakao 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private,Public
   New-NetFirewallRule -DisplayName "MySQL 3306" -Direction Inbound -Protocol TCP -LocalPort 3306 -Action Allow -Profile Private,Public
   ```
   해커톤 끝나면 `Remove-NetFirewallRule -DisplayName "Kakao 8000"`, `Remove-NetFirewallRule -DisplayName "MySQL 3306"` 으로 닫기.
2. **건물 와이파이가 기기 간 통신을 막는 경우** – 공용 와이파이는 보안상 같은 와이파이 안에서도 PC끼리 접속을 막아두는 경우가 있음(AP 격리). 방화벽을 열어도 안 되면 휴대폰 핫스팟으로 모두 옮겨서 해보기.
3. 서버 PC에서 `http://localhost:8000/health` 가 열리는지 먼저 확인 → 열리는데 다른 PC에서만 안 되면 1·2번 문제.

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
