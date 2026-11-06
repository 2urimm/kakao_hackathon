import { useContext } from "react";
import { AppCtx } from "../context.js";
import { qs, useApi } from "../api.js";
import { STATUS, fmtWhen, toPlaceId } from "../chat.js";
import { PLMap } from "../map.js";
import { useAllPins } from "../pins.js";
import { Avatar, FolderRow, ProfTemps } from "../ui.jsx";

/** 채팅에서 잡은 예약 카드 한 장 (채팅 서버 ReservationOut) */
function ChatRsv({ r }) {
  const { plEvents, openList } = useContext(AppCtx);
  const st = STATUS[r.status] || STATUS.requested;
  const ev = plEvents.get(`C${r.id}`);                          // placelist 에 반영된 온도 변화 (온도 반영이 켜져 있을 때)
  const fx = ev && ev.type === "confirmed" && ev.effect;
  const others = r.participants.map(p => p.user_name);
  return (
    <div className={`rsv ${st.cls}`} onClick={() => PLMap.focus(toPlaceId(r.place_id))}>
      <span className={`badge-rsv ${st.cls}`}>{st.label}</span>
      <div className="rt">{r.place_name}</div>
      <div className="small">{fmtWhen(r.reserved_at)} · {r.party_size}명</div>
      <div className="small">함께: {others.join(", ")}{r.requested_by ? ` · ${r.requested_by}님이 예약` : ""}</div>
      {fx && (
        <div className="rfx" onClick={e => { e.stopPropagation(); openList(ev.list.id); }}>
          '{ev.list.title}' 온도 {fx.list_temp[0].toFixed(1)} → <b>{fx.list_temp[1].toFixed(1)}℃</b>
          {fx.rank && fx.rank[0] !== fx.rank[1] ? ` · ${ev.place.지역} ${ev.place.업종} 랭킹 ${fx.rank[0]}위 → ${fx.rank[1]}위` : ""}
        </div>
      )}
      {r.link && <a className="rlink small" href={r.link} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>카카오맵에서 보기</a>}
    </div>
  );
}

export default function Mine() {
  const { user, meta, openList, myRsv, chatOk } = useContext(AppCtx);
  const d = useApi(`/api/mylists?${qs({ user })}`);
  const rsv = useApi(`/api/reservations?${qs({ user })}`);      // 리스트 온도에 반영된 예약 (placelist 웹훅)
  useAllPins();
  if (!d) return <div className="empty">불러오는 중…</div>;
  const bio = meta.users[user]?.bio || "";
  const active = myRsv.filter(r => r.status !== "cancelled");
  const cancelled = myRsv.filter(r => r.status === "cancelled");
  return (
    <>
      <div className="profile">
        <Avatar name={user} />
        <div><div className="name">{user}</div><div className="small">{bio}</div><ProfTemps p={d.profile} /></div>
      </div>

      <div className="sec">내 예약 <span className="cnt">{active.length}</span></div>
      {active.length ? active.map(r => <ChatRsv key={r.id} r={r} />)
        : <div className="empty small-empty">{chatOk ? "채팅방에서 \"@봇 예약해줘\"로 예약하면 여기에 떠요" : "채팅 서버에 연결하지 못했어요"}</div>}
      {cancelled.length > 0 && (
        <details className="rsv-old">
          <summary className="small">취소된 예약 {cancelled.length}</summary>
          {cancelled.map(r => <ChatRsv key={r.id} r={r} />)}
        </details>
      )}

      {rsv && rsv.filter(r => !String(r.reservation_id).startsWith("C")).length > 0 && (
        <>
          <div className="sec">리스트 온도에 반영된 예약 (채팅 밖)</div>
          {rsv.filter(r => !String(r.reservation_id).startsWith("C")).map(r => (
            <div key={r.reservation_id} className="rsv ok" onClick={() => r.list && openList(r.list.id)}>
              <span className="badge-rsv ok">예약 확정</span>
              <div className="rt">{r.place.name}</div>
              <div className="small">{r.datetime || ""}{r.party_size ? ` · ${r.party_size}명` : ""} · {r.place.지역}</div>
              {r.list && r.effect && (
                <div className="rfx">'{r.list.title}' 온도 {r.effect.list_temp[0].toFixed(1)} → <b>{r.effect.list_temp[1].toFixed(1)}℃</b></div>
              )}
            </div>
          ))}
        </>
      )}
      <div className="sec">내가 만든 리스트 {d.own.length}</div>
      {d.own.length ? d.own.map(c => <FolderRow key={c.list_id} c={c} />) : <div className="empty">아직 리스트가 없어요</div>}
      <div className="sec">구독 중인 리스트 {d.followed.length}</div>
      {d.followed.length ? d.followed.map(c => <FolderRow key={c.list_id} c={c} />)
        : <div className="empty">구독한 리스트가 없어요. 친구·랭킹 탭에서 찾아보세요</div>}
    </>
  );
}
