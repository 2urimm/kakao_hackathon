import { useEffect, useState } from "react";
import { fetchChatUsers } from "./chat.js";

/** 이름만 입력하는 로그인. 채팅방에서 쓰는 이름과 같아야 그 사람의 예약이 보인다.
 *  owners: 리스트 주인 [{name, list_id, title}] (/api/meta) — 들어가면 "내 리스트"에 자기 리스트가 보인다. */
export default function Login({ owners, onLogin }) {
  const [name, setName] = useState("");
  const [chatUsers, setChatUsers] = useState(null);
  useEffect(() => {
    fetchChatUsers().then(us => setChatUsers(us.filter(n => n !== (window.CHAT_BOT_NAME || "봇")))).catch(() => setChatUsers([]));
  }, []);
  const go = n => { n = n.trim(); if (n) onLogin(n); };
  const ownerNames = new Set(owners.map(o => o.name));
  const members = (chatUsers || []).filter(n => !ownerNames.has(n));
  return (
    <div className="login-wrap">
      <form className="login" onSubmit={e => { e.preventDefault(); go(name); }}>
        <h1 className="wordmark" aria-label="카카오맵"><span>kakao</span><b>map</b></h1>
        <p className="small">채팅방에서 쓰는 이름으로 들어오면 그 이름으로 잡힌 예약이 지도에 표시돼요.</p>
        <label htmlFor="login-name">이름</label>
        <div className="login-row">
          <input id="login-name" autoFocus value={name} maxLength={100} placeholder="예: 이유림" autoComplete="off"
                 onChange={e => setName(e.target.value)} />
          <button disabled={!name.trim()}>시작</button>
        </div>
        {owners.length > 0 && (
          <div className="login-pick">
            <div className="small">리스트 주인</div>
            <div className="chips">
              {owners.map(o => (
                <button type="button" key={o.name} className="chip" title={o.title} onClick={() => go(o.name)}>
                  {o.name} <span className="small">· {o.title}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        {members.length > 0 && (
          <div className="login-pick">
            <div className="small">채팅방 멤버</div>
            <div className="chips">{members.map(n => <button type="button" key={n} className="chip" onClick={() => go(n)}>{n}</button>)}</div>
          </div>
        )}
      </form>
    </div>
  );
}
