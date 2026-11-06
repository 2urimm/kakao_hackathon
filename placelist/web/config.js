// 카카오맵 JavaScript 키를 넣으면 실제 카카오맵 지도로 바뀝니다.
// (카카오 디벨로퍼스 > 앱 > 플랫폼 키 > JavaScript 키 > JS SDK 도메인 에 접속 주소 등록 필요)
// 비워 두면 OpenStreetMap 대체 지도를 씁니다.
window.KAKAO_JS_KEY = "2d90ed1918361f837324e3ca375a0eda";   // 앱 "쩝쩝박사 placelist" (등록 도메인: localhost:8200, 172.168.45.126:8200, localhost:5173, ngrok 주소)

// 채팅 저장 서버 주소 (카톡방 챗봇 백엔드). 채팅에서 "@톡스픽 예약해줘"로 잡은 예약을 여기서 읽어 지도에 표시.
// "/chat" = 이 지도 서버(server.py)가 채팅 서버로 대신 전달 → 와이파이 주소든 ngrok 외부 링크든 그대로 동작.
// 채팅 서버 실제 주소는 server.py 를 띄울 때 CHAT_SERVER_URL 환경변수 (기본 http://localhost:8000).
window.CHAT_API_BASE = "/chat";
window.CHAT_BOT_NAME = "톡스픽";   // 채팅 서버의 BOT_NAME (톡스픽 = 카카오톡에서 고른 곳)
