import { useContext } from "react";
import { AppCtx } from "./context.js";
import { DRank, DTemp, Lv } from "./ui.jsx";
import { fmtWhen } from "./chat.js";
import { PLMap } from "./map.js";

const HEAD = { confirmed: "예약 확정", cancelled: "예약 취소", pending: "예약 요청" };
const CHAT_HEAD = { requested: "새 예약", confirmed: "예약 확정", cancelled: "예약 취소" };

function Effect({ ev }) {
  const e = ev.effect, p = ev.place;
  if (ev.type === "chat") return <div className="fx">함께: {ev.participants.join(", ")}</div>;
  if (ev.type === "cancelled") return <div className="fx">취소되어 레벨 반영을 되돌렸어요</div>;
  if (ev.type === "pending") return <div className="fx">확정되면 레벨에 반영돼요</div>;
  if (!e) return null;
  const [b, a] = e.list_temp, [rb, ra] = e.rank;
  return (
    <>
      <div className="fx">'{ev.list.title}' <b><Lv t={b} /> → <Lv t={a} /></b> <DTemp d={a - b} /></div>
      <div className="fx">카이드 {e.curator}님 {e.group} <Lv t={e.curator_temp[0]} /> → <Lv t={e.curator_temp[1]} /></div>
      <div className="fx">
        {p.지역} {p.업종} 랭킹 {ra == null ? "" : rb === ra ? `${ra}위 유지` : <><b>{rb}위 → {ra}위</b> <DRank d={rb - ra} /></>}
      </div>
    </>
  );
}

/** 채팅 백엔드에서 온 예약 확정·취소 알림. 누르면 해당 리스트로 이동. */
export default function Toasts({ items, dismiss }) {
  const { openList } = useContext(AppCtx);
  return (
    <div id="toasts">
      {items.map(ev => (
        <div key={ev.toastId} className={`toast ${ev.type === "chat" ? (ev.status === "cancelled" ? "cancelled" : "chat") : ev.type}`}
             onClick={() => { dismiss(ev.toastId); if (ev.list) openList(ev.list.id); else if (ev.type === "chat") PLMap.focus(ev.place.place_id); }}>
          <div className="th"><span className="tk">{ev.type === "chat" ? CHAT_HEAD[ev.status] || "예약" : HEAD[ev.type]}</span><span className="tn">{ev.place.name}</span></div>
          <div className="small">{ev.user}님 · {ev.type === "chat" ? fmtWhen(ev.datetime) : ev.datetime || ""}{ev.party_size ? ` · ${ev.party_size}명` : ""}</div>
          <Effect ev={ev} />
        </div>
      ))}
    </div>
  );
}
