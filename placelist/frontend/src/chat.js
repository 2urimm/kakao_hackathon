// 채팅 저장 서버(카톡방 챗봇 백엔드) 연동.
// 채팅에서 "@톡스픽 예약해줘"로 만든 예약을 그 사람 이름으로 읽어 와 지도·목록에 "예약됨"으로 표시한다.
// 서버 주소는 public/config.js 의 window.CHAT_API_BASE (기본 "/chat" = 지도 서버가 대신 전달)

export const CHAT_API = (window.CHAT_API_BASE || "").trim().replace(/\/$/, "");

/** 채팅 서버의 카카오 장소 ID(숫자) → placelist 장소 ID ("k" + 숫자) */
export const toPlaceId = kakaoId => (String(kakaoId).startsWith("k") ? String(kakaoId) : "k" + kakaoId);

async function get(path) {
  const r = await fetch(CHAT_API + path, { headers: { "ngrok-skip-browser-warning": "1" } });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

/** 이 사람이 참여자인 예약 (예약 일시 순). 취소된 것도 온다. */
export const fetchMyReservations = name => get(`/api/reservations?user_name=${encodeURIComponent(name)}`);

/** 이 사람이 들어가 있는 채팅방들 (멤버 포함). 같은 방 멤버 = 기본 친구 */
export const fetchMyRooms = name => get(`/api/rooms?user_name=${encodeURIComponent(name)}`);

/** 채팅 서버에 등록된 사람 이름 (로그인 화면의 빠른 선택용) */
export const fetchChatUsers = async () => (await get("/api/users")).map(u => u.name);

export const STATUS = {
  requested: { label: "예약 요청", cls: "req" },
  confirmed: { label: "예약 확정", cls: "ok" },
  cancelled: { label: "취소됨", cls: "x" },
};

/** "2026-11-07T12:00:00" → "11월 7일 (토) 12:00" */
export function fmtWhen(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso || "";
  const wd = "일월화수목금토"[d.getDay()];
  return `${d.getMonth() + 1}월 ${d.getDate()}일 (${wd}) ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
