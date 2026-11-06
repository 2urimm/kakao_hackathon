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

- 설정은 전부 `.env` 또는 환경변수 (`HOST`, `PORT`, `CORS_ORIGINS`, `DB_*`, `ANSWER_SERVER_URL`, `MCP_SERVER_URL` 등)
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

**답변 생성 서버 담당자에게**: 답변은 이 서버의 `POST /api/messages`로 `{"user_name": "봇", "content": "<답변>", "room_id": <받은 room_id>}` 형태로 (방 번호, 숫자/문자열 둘 다 됨) 보내주세요. `user_name`은 `BOT_NAME`과 같아야 함.
`place`는 선택. 안 보내도 답변 본문에 **데모 식당 목록(`places/*.json`)에 있는 식당 이름**이 나오면 "@봇 예약해줘"로 그 식당을 예약할 수 있음.
```json
{ "user_name": "봇", "room_id": "2", "content": "### 성수 파스타집 추천 ...",
  "place": { "place_id": "12345", "place_name": "성수 파스타집", "x": 127.05, "y": 37.54 } }
```
(`x`=경도, `y`=위도는 선택)

## 예약 (채팅으로, 쩝쩝박사 MCP 서버 연동)

```
민수: @봇 내일 저녁 7시 4명 성수 파스타 맛집 추천해줘   → 답변 생성 서버
봇:   ### 성수 파스타집 추천해요!  (place 포함)
유림: @봇 예약해줘                                     → 답변 서버로 안 보내고 이 서버가 처리
      │ 1. 그 방에서 봇이 가장 최근에 추천한 식당(place 붙은 봇 메시지) 찾기
      │ 2. 날짜/시간/인원: 이 문장 → 없으면 추천 받기 전후 대화에서 ("내일 저녁 7시 4명")
      │ 3. 예약 + 참여자(방 멤버 전원, 봇 제외) 저장 → MCP 서버 POST /tools/reserve
      ▼
봇:   📅 유림님이 성수 파스타집 2026-11-07 19:00 4명 예약을 요청했어요. 예약 링크: ...
      👥 참여: 유림, 민수, 지수
예약 카드에서 지수 X → DELETE /api/reservations/{id}/participants/{user_id}
봇:   👋 지수님이 성수 파스타집 예약에서 빠졌어요. (이제 3명)
```

- **어떤 식당?** 직전 봇 답변 하나만 봄 (예약·택시 안내 같은 이 서버 안내 메시지는 건너뜀)
  1. 답변에 `place`가 붙어 있으면 그것
  2. 없으면 답변 본문에서 `places/` 목록의 식당 이름을 찾음 (띄어쓰기·`**굵게**` 무시, `이름 지점명` 도 매칭, 이름이 겹치면 더 긴 이름: `인하순대국 아들집` > `인하순대국`). 여러 곳이면 가장 먼저 언급된 곳
  3. 직전 답변에 아는 식당이 없으면 "못 찾았어요" (더 예전 답변의 식당을 예약하지 않음)
- **데모 식당 목록 `places/`**: 답변 서버 시스템 프롬프트에 넣은 카카오맵 추출 파일 그대로 (`mapo_places.json`, `seocho_places.json`, `busan_places.json`, 각 20곳). 폴더에 JSON을 넣거나 고치면 재시작 없이 반영. 확인: `GET /api/places`. 다른 위치면 `.env`의 `PLACES_FILE`
- 예약 요청으로 보는 말: `@봇` + `예약해 / 예약 좀 해 / 예약하자 / 예약 잡아 / 예약 부탁 / 예약 ㄱ` (`@봇 예약 가능한 곳 추천해줘`는 일반 질문 → 답변 서버)
- 알아듣는 날짜·시간: `오늘/내일/모레`, `11월 8일`, `8일`, `토요일`, `다음주 금요일`, `7시`, `7시 반`, `오후 1시`, `점심 12시`, `19:30`, `일곱시` / 인원: `4명`, `네 명`, `4인`
  - 오전/오후 없이 `1~9시`는 저녁으로 봄 (`7시` → 19:00). 날짜가 없으면 오늘, 이미 지난 시간이면 내일
- 상황별 봇 답변
  - 추천받은 식당이 없음 → "먼저 추천받아 주세요"
  - 시간을 못 찾음 → "몇 시로 예약할까요?" → `@봇 토요일 6시에 예약해줘` 하면 예약
  - 같은 식당·같은 시간 예약이 이미 있음 → "이미 돼 있어요" (중복 예약 안 함)
- MCP의 `reserve`는 **실제 예약을 하지 않는 데모용** (안내 문구 + 카카오맵 장소 링크만 만듦). MCP 서버가 꺼져 있어도 예약은 저장되고 안내 문구는 이 서버가 만든다

| 변수 | 설명 | 기본값 |
|---|---|---|
| `MCP_SERVER_URL` | 쩝쩝박사 MCP 서버 주소 (예: `http://192.168.x.x:8100`). 비우면 MCP 호출 없이 저장만 | (없음) |
| `MCP_TIMEOUT` | MCP 호출 대기 시간(초) | `10` |

## MCP 서버 알림 `POST /ai/notify` (쩝쩝박사 MCP 서버 → 이 서버)

AI가 MCP 도구(`reserve`, `call_taxi`)를 부르면 MCP 서버가 실제 예약 대신 이 경로로 안내 문구를 보낸다. 이 서버는 `text`를 **그 방에 봇 메시지로 그대로** 올리고 웹소켓으로 푸시한다. 인증 없음(내부망).

```json
{ "roomId": "3", "type": "taxi", "text": "🚕 민수님이 서초칼국수까지 택시를 요청했어요. 예상 4분",
  "payload": { "ok": true, "status": "requested", "eta_min": 4 } }
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `roomId` | string, 필수 | **이 서버의 방 번호를 문자열로** (`"1"`, `"3"`). 답변 생성 서버가 `/api/chat`에서 받은 `room_id` 그대로 |
| `type` | string, 필수 | `reserve` / `taxi` / `info` |
| `text` | string, 필수 | 방에 그대로 표시할 문구 |
| `payload` | object, 필수 | 원본 데이터 (표시 안 함) |

| 상황 | 응답 |
|---|---|
| 정상 | `200 {"ok": true}` |
| 필드 누락·형식 오류·깨진 JSON | `400 {"ok": false, "error": "..."}` |
| 방 없음 (`"r1"`처럼 숫자가 아닌 것 포함) | `422 {"ok": false, "error": "room not found"}` |
| 내부 오류 | `500 {"ok": false, "error": "..."}` |

- 서버 로그: `notify room=3 type=taxi ok=True`
- 이 서버가 "@봇 예약해줘"로 직접 MCP `reserve`를 부른 경우, 그 호출 중에 오는 `type=reserve` 알림은 표시하지 않고 200만 준다 (이 서버가 참여자·예약 id를 붙인 안내를 따로 올리므로 중복 방지)
- 테스트용 방: `3` ("알림테스트")

## API (프론트 담당자용)

전체 문서/테스트 화면: `http://<서버IP>:<PORT>/docs`

**순서: 방을 먼저 만들고(`POST /api/rooms`) → 응답의 방 `id`로 채팅을 보낸다.** 없는 방에 채팅을 보내면 404.

### 채팅방

| API | 설명 |
|---|---|
| `POST /api/rooms` | 방 만들기 + 멤버 초대. `name` 필수, 방 `id`는 자동(1, 2, 3...) |
| `GET /api/rooms` | 전체 방 + 멤버 목록. `?user_name=유림` → 그 사람이 속한 방만 |
| `GET /api/rooms/{room_id}` | 방 하나 + 멤버 (없으면 404) |
| `PATCH /api/rooms/{room_id}` | 방 이름 바꾸기 `{"name": "주말 강릉 여행"}` |
| `POST /api/rooms/{room_id}/members` | 멤버 초대 `{"user_name": "민수"}` (이미 멤버면 그대로) |

```json
// POST /api/rooms
{ "name": "해커톤 팀방", "member_names": ["유림", "민수"] }

// 응답 (RoomOut)
{ "id": 2, "name": "해커톤 팀방", "created_at": "...",
  "members": [ { "user_id": 1, "user_name": "유림", "joined_at": "..." },
               { "user_id": 2, "user_name": "민수", "joined_at": "..." } ] }
```

### 채팅 저장 `POST /api/messages`
```json
{ "user_name": "유림", "content": "@봇 성수동 카페 추천해줘", "room_id": 2 }
```
- `room_id`는 필수 (방 `id` 숫자)
- 처음 보는 `user_name`이면 자동으로 유저 등록, 그 방 멤버가 아니었으면 자동으로 멤버 등록

응답:
```json
{ "id": 1, "user_name": "유림", "room_id": 2, "content": "@봇 성수동 카페 추천해줘", "created_at": "2026-11-06T15:50:34", "bot_called": true }
```
- `bot_called: true` → 봇을 불렀으니 곧 `user_name: "봇"` 메시지가 올라옴. 이때 "봇이 답변 중..." 표시하면 됨
- `bot_called: true` 는 "@봇 예약해줘" 같은 예약 요청에도 옴 (곧 봇 안내 메시지가 올라옴)
- 모든 메시지(`MessageOut`)에 `place`, `reservation_id` 가 있음 (보통은 `null`)
  - `place` 있음 → 봇이 추천한 식당 (지도 핀 등에 활용 가능)
  - `reservation_id` 있음 → 예약 안내 메시지 → **예약 카드** (`GET /api/reservations/{id}` 로 상세, 참여자 칩 + X)

### 채팅 조회 `GET /api/messages?room_id=2&user_name=유림&limit=50`
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

### 새 메시지만 조회 `GET /api/messages?room_id=2&after_id=12`
`id`가 12보다 큰 메시지만 반환. 웹소켓 재연결 후 끊긴 동안 놓친 메시지를 받아올 때 사용 (웹소켓을 못 쓰면 2~3초마다 폴링해도 됨).

### 예약

| API | 설명 |
|---|---|
| (채팅) `@봇 내일 7시에 예약해줘` | **기본 예약 방법.** 직전에 추천한 식당을 예약 |
| `DELETE /api/reservations/{id}/participants/{user_id}` | 참여자 칩의 **X**. 인원 -1, 채팅방에 안내. 예약한 사람은 못 뺌(400) |
| `POST /api/reservations/{id}/participants` | X로 뺀 사람 다시 넣기 `{"user_name": "지수"}`. 인원 +1 |
| `POST /api/reservations` | (선택) 화면에서 직접 예약할 때 |
| `GET /api/reservations?user_name=유림` | **그 사람이 참여자인 예약 목록** (= 그 계정의 예약 장소). `room_id`, `status` 필터도 가능. 예약 일시 순 |
| `GET /api/reservations/{id}` | 예약 하나 |
| `PATCH /api/reservations/{id}` | 상태 변경 `{"status": "confirmed"}` / `"cancelled"` → 채팅방에 ✅/❌ 안내 |

`POST /api/reservations` (선택, 채팅 대신 화면에서 직접 예약할 때):
```json
{ "room_id": 2, "place_id": "12345", "place_name": "성수 파스타집",
  "reserved_at": "2026-11-08 19:00", "requested_by": "유림",
  "participant_names": ["유림", "민수"] }
```
- `participant_names` **생략(또는 null) = 방 멤버 전원** (봇 제외). 화면에서 X로 뺀 사람을 제외한 이름들을 보내면 그 사람들만 참여
- 요청자(`requested_by`)는 목록에 없어도 항상 참여자에 포함
- 방 멤버가 아닌 이름 → 400, 없는 방 → 404
- `party_size` 생략 시 참여자 수

응답 (`ReservationOut`):
```json
{ "id": 1, "room_id": 2, "place_id": "12345", "place_name": "성수 파스타집",
  "reserved_at": "2026-11-08T19:00:00", "party_size": 2, "requested_by": "유림",
  "participants": [ {"user_id": 10, "user_name": "유림"}, {"user_id": 11, "user_name": "민수"} ],
  "status": "requested", "link": "https://place.map.kakao.com/12345", "created_at": "...",
  "message": "📅 유림님이 성수 파스타집 2026-11-08 19:00 2명 예약을 요청했어요. ...", "mcp_ok": true }
```

### 유저 목록 `GET /api/users`

### 헬스체크 `GET /health`

## DB 구조

```
users ─┬─< room_members >─┬─ rooms
       ├──── messages ────┤
       └── reservations ──┘
             └─< reservation_participants >── users
```

| 테이블 | 컬럼 | 설명 |
|---|---|---|
| **users** | `id` PK | |
| | `name` NOT NULL, unique | 유저 이름 |
| | `created_at` | |
| **rooms** | `id` PK, 자동 증가 | 방 번호 |
| | `name` NOT NULL | 방 이름 (중복 가능) |
| | `created_at` | |
| **room_members** | `room_id` PK, FK → rooms.id | 방 삭제 시 같이 삭제 |
| | `user_id` PK, FK → users.id | 유저 삭제 시 같이 삭제 |
| | `joined_at` | 방에 들어온 시간 |
| **messages** | `id` PK | |
| | `user_id` FK → users.id | 보낸 사람 |
| | `room_id` FK → rooms.id | 채팅방 |
| | `content` | 채팅 내용 |
| | `created_at` | |
| | `place_id`, `place_name`, `place_x`, `place_y` | 봇이 추천한 장소 (없으면 NULL) |
| | `reservation_id` FK → reservations.id | 예약 안내 메시지면 그 예약 (없으면 NULL) |
| **reservations** | `id` PK, 자동 증가 | 예약 번호 |
| | `room_id` FK → rooms.id | 예약한 채팅방 |
| | `user_id` FK → users.id | 예약 요청자 |
| | `place_id`, `place_name` | 카카오 장소 ID / 이름 |
| | `reserved_at` | 예약 일시 |
| | `party_size` | 인원 |
| | `status` | `requested` / `confirmed` / `cancelled` |
| | `link` | 카카오맵 장소 링크 |
| | `created_at` | |
| **reservation_participants** | `reservation_id` PK, FK → reservations.id | 예약 삭제 시 같이 삭제 |
| | `user_id` PK, FK → users.id | 참여자 (이 사람 계정에 예약 장소가 뜸) |

`room_members`는 (방, 유저) 쌍이 PK라서 같은 사람이 같은 방에 두 번 들어갈 수 없음.
