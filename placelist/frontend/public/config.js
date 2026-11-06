// 카카오맵 JavaScript 키를 넣으면 실제 카카오맵 지도로 바뀝니다.
// (카카오 디벨로퍼스 > 앱 > 플랫폼 키 > JavaScript 키 > JS SDK 도메인 에 접속 주소 등록 필요)
// 비워 두면 OpenStreetMap 대체 지도를 씁니다.
window.KAKAO_JS_KEY = "2d90ed1918361f837324e3ca375a0eda";   // 앱 "쩝쩝박사 placelist" (등록 도메인: localhost:8200, 172.168.45.126:8200, localhost:5173)

// 채팅 저장 서버 주소 (카톡방 챗봇 백엔드). 채팅에서 "@봇 예약해줘"로 잡은 예약을 여기서 읽어 지도에 표시.
// 서버 PC의 IP가 바뀌면 이 값만 바꾸면 됩니다.
window.CHAT_API_BASE = "http://172.168.45.126:8000";
window.CHAT_BOT_NAME = "봇";
