import { useEffect, useState } from "react";
import { fetchChatUsers } from "./chat.js";

/** 이름만 입력하는 로그인. 채팅방에서 쓰는 이름과 같아야 그 사람의 예약이 보인다. */
export default function Login({ personas, onLogin }) {
  const [name, setName] = useState("");
  const [chatUsers, setChatUsers] = useState(null);
  useEffect(() => {
    fetchChatUsers().then(us => setChatUsers(us.filter(n => n !== (window.CHAT_BOT_NAME || "봇")))).catch(() => setChatUsers([]));
  }, []);
  const go = n => { n = n.trim(); if (n) onLogin(n); };
  return (
    <div className="login-wrap">
      <form className="login" onSubmit={e => { e.preventDefault(); go(name); }}>
        <h1>placelist</h1>
        <p className="small">채팅방에서 쓰는 이름으로 들어오면 그 이름으로 잡힌 예약이 지도에 표시돼요.</p>
        <label htmlFor="login-name">이름</label>
        <div className="login-row">
          <input id="login-name" autoFocus value={name} maxLength={100} placeholder="예: 이유림" autoComplete="off"
                 onChange={e => setName(e.target.value)} />
          <button disabled={!name.trim()}>시작</button>
        </div>
        {chatUsers && chatUsers.length > 0 && (
          <div className="login-pick">
            <div className="small">채팅방 멤버</div>
            <div className="chips">{chatUsers.map(n => <button type="button" key={n} className="chip" onClick={() => go(n)}>{n}</button>)}</div>
          </div>
        )}
        {personas.length > 0 && (
          <div className="login-pick">
            <div className="small">데모 인물 (리스트·친구 데이터가 있는 사람)</div>
            <div className="chips">{personas.map(n => <button type="button" key={n} className="chip" onClick={() => go(n)}>{n}</button>)}</div>
          </div>
        )}
      </form>
    </div>
  );
}
