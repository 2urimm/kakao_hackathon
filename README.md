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

## 챗봇 (`@봇` 호출)

채팅에 `@봇`이 들어 있으면 답변 생성 서버(팀원 PC)가 그 방의 대화를 보고 장소를 추천한다.

```
프론트 ──POST /api/messages "@봇 홍대 식당 추천"──▶ 채팅 저장 서버 (이 서버)
                                                    │ 저장 후, 그 방 최근 대화 20개를
                                                    ▼ POST /api/chat 으로 전달 (202 접수)
                                              답변 생성 서버
                                                    │ 답변 생성 (LLM 생성 시간, 약 10초)
채팅 저장 서버 ◀──POST /api/messages user_name="봇"──┘
      │ 저장되는 즉시 (수십 ms)
      ▼
프론트 ◀── 웹소켓 ws://<서버IP>:8000/ws/<room_id> 로 푸시 (기다림/폴링 없음)
```

`.env` 설정:

| 변수 | 설명 | 기본값 |
|---|---|---|
| `ANSWER_SERVER_URL` | 답변 생성 서버 주소. 비우면 봇 호출 안 함 | (없음) |
| `BOT_TRIGGER` | 이 단어가 채팅에 있으면 봇 호출 | `@봇` |
| `BOT_NAME` | 답변 생성 서버가 답변 저장할 때 쓰는 `user_name`. 이 이름의 메시지는 봇을 다시 부르지 않음(무한루프 방지) | `봇` |
| `CONTEXT_MESSAGES` | 봇에게 넘길 최근 대화 개수 | `20` |
| `ANSWER_TIMEOUT` | 답변 서버 접수 대기 시간(초) | `10` |

**답변 생성 서버 담당자에게**: 답변은 이 서버의 `POST /api/messages`로 `{"user_name": "봇", "content": "<답변>", "room_id": "<받은 room_id>"}` 형태로 보내주세요. `user_name`은 `BOT_NAME`과 같아야 함.

## API (프론트 담당자용)

전체 문서/테스트 화면: `http://<서버IP>:<PORT>/docs`

### 채팅 저장 `POST /api/messages`
```json
{ "user_name": "유림", "content": "@봇 성수동 카페 추천해줘", "room_id": "room1" }
```
- `room_id`는 생략 가능 (기본 `"default"`)
- 처음 보는 `user_name`이면 자동으로 유저 등록

응답:
```json
{ "id": 1, "user_name": "유림", "room_id": "room1", "content": "@봇 성수동 카페 추천해줘", "created_at": "2026-11-06T15:50:34", "bot_called": true }
```
- `bot_called: true` → 봇을 불렀으니 곧 `user_name: "봇"` 메시지가 올라옴. 이때 "봇이 답변 중..." 표시하면 됨

### 채팅 조회 `GET /api/messages?room_id=room1&user_name=유림&limit=50`
모든 파라미터 선택. 오래된 → 최신 순으로 최근 `limit`개.

### 실시간 수신 (웹소켓) `ws://<서버IP>:<PORT>/ws/<room_id>`
연결해두면 그 방에 저장되는 **모든 새 메시지(다른 사람 채팅 + 봇 답변)** 가 저장 즉시 `MessageOut` JSON으로 온다.
보내기는 계속 `POST /api/messages`. 내가 보낸 메시지도 웹소켓으로 한 번 더 오니 `id`로 중복 제거.

```js
const ws = new WebSocket(`ws://${SERVER_IP}:8000/ws/${roomId}`);
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);   // {id, user_name, room_id, content, created_at, bot_called}
  if (msg.bot_called) showTyping();              // 누가 @봇 불렀음 → "봇이 답변 중..."
  if (msg.user_name === "봇") hideTyping();      // 봇 답변 도착
  addMessage(msg);                               // id 로 중복 체크 후 화면에 추가
};
ws.onclose = () => setTimeout(reconnect, 1000);  // 와이파이 끊기면 재연결 + after_id 로 놓친 것 받아오기
```

봇 답변(`content`)은 마크다운(`###`, `**굵게**`, 목록)으로 오니 마크다운 렌더링 추천.

### 새 메시지만 조회 `GET /api/messages?room_id=room1&after_id=12`
`id`가 12보다 큰 메시지만 반환. 웹소켓 재연결 후 끊긴 동안 놓친 메시지를 받아올 때 사용 (웹소켓을 못 쓰면 2~3초마다 폴링해도 됨).

### 유저 목록 `GET /api/users`

### 채팅방

채팅을 보내면 방이 없을 때 자동으로 만들어지고, 보낸 사람은 그 방 멤버로 자동 등록됨. 아래 API는 방을 미리 만들거나 멤버를 초대할 때 사용.

| API | 설명 |
|---|---|
| `GET /api/rooms` | 전체 방 + 멤버 목록. `?user_name=유림` → 그 사람이 속한 방만 |
| `GET /api/rooms/{room_id}` | 방 하나 + 멤버 (없으면 404) |
| `POST /api/rooms` | 방 만들기 + 멤버 초대. 이미 있는 방이면 이름 수정 + 멤버 추가 |
| `POST /api/rooms/{room_id}/members` | 멤버 초대 `{"user_name": "민수"}` (이미 멤버면 그대로) |

```json
// POST /api/rooms
{ "id": "hackathon-room", "name": "해커톤 팀방", "member_names": ["유림", "민수"] }

// 응답 (RoomOut)
{ "id": "hackathon-room", "name": "해커톤 팀방", "created_at": "...",
  "members": [ { "user_id": 1, "user_name": "유림", "joined_at": "..." },
               { "user_id": 2, "user_name": "민수", "joined_at": "..." } ] }
```

### 헬스체크 `GET /health`

## DB 구조

```
users ─┬─< room_members >─┬─ rooms
       └──── messages ────┘
```

| 테이블 | 컬럼 | 설명 |
|---|---|---|
| **users** | `id` PK | |
| | `name` unique | 유저 이름 |
| | `created_at` | |
| **rooms** | `id` PK (문자열) | 프론트가 보내는 `room_id` 그대로 (예: `"1"`) |
| | `name` | 방 이름 (선택) |
| | `created_at` | |
| **room_members** | `room_id` PK, FK → rooms.id | 방 삭제 시 같이 삭제 |
| | `user_id` PK, FK → users.id | 유저 삭제 시 같이 삭제 |
| | `joined_at` | 방에 들어온 시간 |
| **messages** | `id` PK | |
| | `user_id` FK → users.id | 보낸 사람 |
| | `room_id` FK → rooms.id | 채팅방 |
| | `content` | 채팅 내용 |
| | `created_at` | |

`room_members`는 (방, 유저) 쌍이 PK라서 같은 사람이 같은 방에 두 번 들어갈 수 없음.
rooms 테이블이 생기기 전에 쌓인 채팅은 서버 시작 시 자동으로 옮겨짐 (`database.py`의 `_migrate_rooms`).
