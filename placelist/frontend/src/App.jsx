import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AppCtx } from "./context.js";
import { api } from "./api.js";
import { PLMap } from "./map.js";
import { fetchMyReservations, toPlaceId } from "./chat.js";
import Login from "./Login.jsx";
import Toasts from "./Toasts.jsx";
import Compat from "./views/Compat.jsx";
import Friends from "./views/Friends.jsx";
import ListDetail from "./views/ListDetail.jsx";
import Mine from "./views/Mine.jsx";
import Ranking from "./views/Ranking.jsx";
import Search from "./views/Search.jsx";

const TABS = [["mine", "내 리스트"], ["friends", "친구"], ["compat", "궁합"], ["ranking", "랭킹"]];
const TAB_VIEW = { mine: Mine, friends: Friends, compat: Compat, ranking: Ranking };
const USER_KEY = "placelist_user";
const loadUser = () => { try { return localStorage.getItem(USER_KEY) || ""; } catch { return ""; } };
const saveUser = n => { try { n ? localStorage.setItem(USER_KEY, n) : localStorage.removeItem(USER_KEY); } catch { /* 저장 못 해도 동작 */ } };

export default function App() {
  const [meta, setMeta] = useState(null);
  const [places, setPlaces] = useState([]);
  const [user, setUserState] = useState(loadUser);           // 이름만 입력하는 로그인 (브라우저에 기억)
  const setUser = useCallback(n => { saveUser(n); setUserState(n); }, []);
  const [myRsv, setMyRsv] = useState([]);                       // 채팅 서버의 내 예약 (참여자 기준)
  const [chatOk, setChatOk] = useState(true);
  const rsvSeen = useRef(null);
  const [plEvents, setPlEvents] = useState(new Map());          // placelist 예약 이벤트 (reservation_id → 마지막 이벤트). 온도 변화 표시용
  const plSeen = useRef(new Set());                             // 알림을 띄운 채팅 예약 id (중복 알림 방지)
  const keepEvents = evs => setPlEvents(m => { const n = new Map(m); evs.forEach(ev => n.set(ev.reservation_id, ev)); return n; });
  const [tab, setTab] = useState("mine");
  const [view, setView] = useState({ type: "tab" });           // {type:"tab"} | {type:"detail", id} | {type:"search", q}
  const [rank, setRank] = useState({ region: "", category: "", purpose: "", kind: "lists" });
  const [compatOpen, setCompatOpen] = useState(null);
  const [q, setQ] = useState("");
  const [tick, setTick] = useState(0);                          // 예약 이벤트 등으로 목록을 다시 읽어야 할 때 +1
  const [flash, setFlash] = useState(null);                     // 방금 예약이 들어온 리스트 강조 {list_id, until, from}
  const [toasts, setToasts] = useState([]);
  const [mapKind, setMapKind] = useState(null);
  const viewRef = useRef(null);
  const scrollMemo = useRef(0);
  const restore = useRef(false);
  const seq = useRef(0);
  const toastId = useRef(0);

  // ---- 처음 불러오기 + 지도
  useEffect(() => {
    Promise.all([api("/api/meta"), api("/api/places"), api("/api/events?since=0")]).then(([m, p, e]) => {
      seq.current = e.last;                                     // 이미 있던 이벤트는 알림 없이 건너뜀
      keepEvents(e.events);
      e.events.forEach(ev => plSeen.current.add(ev.reservation_id));
      setMeta(m); setPlaces(p);
    });
  }, []);
  useEffect(() => { PLMap.init(document.getElementById("map"), setMapKind); }, []);

  // ---- 이동
  const openList = useCallback(id => {
    scrollMemo.current = viewRef.current ? viewRef.current.scrollTop : 0;
    setView({ type: "detail", id });
  }, []);
  const goBack = useCallback(() => { restore.current = true; setView({ type: "tab" }); }, []);
  const goTab = useCallback((t, who) => {
    setTab(t); setView({ type: "tab" });
    if (who) setCompatOpen(who);
  }, []);
  useLayoutEffect(() => {
    if (!viewRef.current) return;
    viewRef.current.scrollTop = restore.current ? scrollMemo.current : 0;
    restore.current = false;
  }, [view, tab, user]);

  // ---- 주소 해시로 바로 열기: #friends, #compat, #ranking, #list=F02, #q=동래 가성비
  useEffect(() => {
    if (!meta) return;
    const route = () => {
      const h = decodeURIComponent(location.hash.slice(1));
      if (h.startsWith("q=")) { setQ(h.slice(2)); setView({ type: "search", q: h.slice(2) }); }
      else if (h.startsWith("list=")) setView({ type: "detail", id: h.slice(5) });
      else { setTab(TABS.some(([k]) => k === h) ? h : "mine"); setView({ type: "tab" }); }
    };
    route();
    window.addEventListener("hashchange", route);
    return () => window.removeEventListener("hashchange", route);
  }, [meta]);

  // ---- 예약 확정 이벤트 (채팅 백엔드 → /api/reservation → 여기서 2초마다 확인)
  useEffect(() => {
    if (!meta) return;
    const timer = setInterval(async () => {
      let r;
      try { r = await api(`/api/events?since=${seq.current}`); } catch { return; }
      if (!r.events.length) return;
      seq.current = r.last;
      keepEvents(r.events);
      const added = r.events.map(ev => ({ ...ev, toastId: ++toastId.current }));
      // 채팅 예약(C<id>)은 채팅 쪽 "새 예약" 알림이 먼저 떴으면 온도 변화가 담긴 이 알림으로 바꿔 끼움
      const rids = new Set(added.map(ev => ev.reservation_id + ":" + ev.type));
      added.forEach(ev => plSeen.current.add(ev.reservation_id));
      setToasts(t => [...t.filter(x => !(x.type === "chat" && rids.has(x.rsvKey))), ...added].slice(-3));
      added.forEach(ev => setTimeout(() => setToasts(t => t.filter(x => x.toastId !== ev.toastId)), 9000));
      const last = [...added].reverse().find(ev => ev.list && ev.effect);
      if (last) setFlash({ list_id: last.list.id, until: Date.now() + 6000, from: last.type === "confirmed" ? last.effect.list_temp[0] : null });
      setTick(t => t + 1);
      setTimeout(() => setTick(t => t + 1), 6200);              // 깜빡임이 끝나면 한 번 더 그려서 정리
    }, 2000);
    return () => clearInterval(timer);
  }, [meta]);

  // ---- 채팅에서 잡은 내 예약 (채팅 서버, 3초마다). 새로 생기면 알림
  useEffect(() => {
    if (!user) return;
    let off = false;
    rsvSeen.current = null;
    setMyRsv([]);
    const load = async () => {
      let rows;
      try { rows = await fetchMyReservations(user); setChatOk(true); } catch { if (!off) setChatOk(false); return; }
      if (off) return;
      const key = r => `${r.id}:${r.status}`;
      if (rsvSeen.current) {                                    // 첫 로딩 때 있던 예약은 알림 없이
        // placelist 이벤트로 이미 알림이 뜬 예약은 건너뜀 (온도 반영이 켜져 있으면 그쪽이 더 자세함)
        const fresh = rows.filter(r => !rsvSeen.current.has(key(r)) && !(r.status !== "cancelled" && plSeen.current.has(`C${r.id}`)));
        const added = fresh.map(r => ({
          type: "chat", status: r.status, toastId: ++toastId.current, user: r.requested_by,
          rsvKey: `C${r.id}:${r.status === "cancelled" ? "cancelled" : "confirmed"}`,
          place: { name: r.place_name, place_id: toPlaceId(r.place_id) }, datetime: r.reserved_at,
          party_size: r.party_size, participants: r.participants.map(p => p.user_name), list: null,
        }));
        if (added.length) {
          setToasts(t => [...t, ...added].slice(-3));
          added.forEach(ev => setTimeout(() => setToasts(t => t.filter(x => x.toastId !== ev.toastId)), 9000));
        }
      }
      rsvSeen.current = new Set(rows.map(key));
      setMyRsv(rows);
    };
    load();
    const timer = setInterval(load, 3000);
    return () => { off = true; clearInterval(timer); };
  }, [user]);
  const rsvByPlace = useMemo(() => {                            // placelist 장소 id → 취소 안 된 내 예약들
    const m = new Map();
    myRsv.filter(r => r.status !== "cancelled").forEach(r => {
      const id = toPlaceId(r.place_id);
      m.set(id, [...(m.get(id) || []), r]);
    });
    return m;
  }, [myRsv]);
  const reservedKey = [...rsvByPlace.keys()].sort().join(",");
  useEffect(() => { PLMap.setReserved(reservedKey ? reservedKey.split(",") : []); }, [reservedKey, mapKind]);

  const ctx = useMemo(() => ({
    user, meta, places, tick, flash, mapKind, rank, setRank, compatOpen, setCompatOpen, openList, goBack, goTab, setTick,
    myRsv, rsvByPlace, reservedKey, chatOk, plEvents,
  }), [user, meta, places, tick, flash, mapKind, rank, compatOpen, openList, goBack, goTab, myRsv, rsvByPlace, reservedKey, chatOk, plEvents]);

  const Tab = TAB_VIEW[tab];
  const body = !meta || !user ? null : view.type === "detail" ? <ListDetail key={view.id} id={view.id} />
    : view.type === "search" ? <Search key={view.q + user} q={view.q} />
    : <Tab />;

  return (
    <AppCtx.Provider value={ctx}>
      <div id="map" />
      {meta && !user && <Login personas={Object.keys(meta.users)} onLogin={n => { setUser(n); setView({ type: "tab" }); setTab("mine"); }} />}
      {meta && user && <>
      <aside id="panel">
        <header className="top">
          <div className="brand"><h1>placelist</h1></div>
          <form id="sf" onSubmit={e => { e.preventDefault(); if (q.trim()) setView({ type: "search", q: q.trim() }); }}>
            <input id="q" type="text" value={q} onChange={e => setQ(e.target.value)} placeholder="어디 갈까? 예) 동래 가성비 국밥" autoComplete="off" />
            <button aria-label="검색">검색</button>
          </form>
          <nav id="tabs">
            {TABS.map(([k, label]) => (
              <button key={k} className={view.type === "tab" && tab === k ? "on" : ""} onClick={() => goTab(k)}>{label}</button>
            ))}
          </nav>
        </header>
        <div className="who-row">
          <span className="me"><b>{user}</b>님</span>
          {myRsv.some(r => r.status !== "cancelled") && <span className="me-rsv">예약 {myRsv.filter(r => r.status !== "cancelled").length}</span>}
          {!chatOk && <span className="small warn" title="public/config.js 의 CHAT_API_BASE 확인">채팅 서버 연결 안 됨</span>}
          <button className="logout" onClick={() => { setUser(""); setView({ type: "tab" }); }}>다른 이름으로</button>
        </div>
        <div id="view" ref={viewRef}>{body}</div>
      </aside>
      <Toasts items={toasts} dismiss={id => setToasts(t => t.filter(x => x.toastId !== id))} />
      {mapKind === "leaflet" && <div className="mapnote">대체 지도 · config.js에 카카오맵 키를 넣으면 카카오맵으로 바뀝니다</div>}
      </>}
    </AppCtx.Provider>
  );
}
