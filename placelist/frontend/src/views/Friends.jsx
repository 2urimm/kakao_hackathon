import { useContext, useEffect, useState } from "react";
import { AppCtx } from "../context.js";
import { api, qs, useApi } from "../api.js";
import { fetchMyReservations, fetchMyRooms, fmtWhen, toPlaceId } from "../chat.js";
import { PLMap } from "../map.js";
import { usePins } from "../pins.js";
import { Avatar, FolderRow, ProfTemps } from "../ui.jsx";

const BOT = () => window.CHAT_BOT_NAME || "봇";

/** 같은 채팅방 멤버 = 기본 친구. 방 이름, 그 친구의 예약(채팅 서버), 그 친구가 만든 리스트(placelist)를 5초마다 읽는다. */
function useRoomFriends(user) {
  const [friends, setFriends] = useState(null);
  useEffect(() => {
    let off = false;
    const load = async () => {
      let rooms;
      try { rooms = await fetchMyRooms(user); } catch { if (!off) setFriends(f => f ?? []); return; }
      const byName = new Map();                                  // 친구 이름 → 같이 있는 방 이름들
      rooms.forEach(r => r.members.forEach(m => {
        if (m.user_name === user || m.user_name === BOT()) return;
        byName.set(m.user_name, [...(byName.get(m.user_name) || []), r.name]);
      }));
      const rows = await Promise.all([...byName].map(async ([name, roomNames]) => {
        const [rsv, mine] = await Promise.all([
          fetchMyReservations(name).catch(() => []),
          api(`/api/mylists?${qs({ user: name })}`).catch(() => null),
        ]);
        return { name, rooms: roomNames, rsv: rsv.filter(r => r.status !== "cancelled"),
                 profile: mine?.profile || {}, lists: mine?.own || [] };
      }));
      if (!off) setFriends(rows.sort((a, b) => b.rsv.length - a.rsv.length || a.name.localeCompare(b.name, "ko")));
    };
    load();
    const t = setInterval(load, 5000);
    return () => { off = true; clearInterval(t); };
  }, [user]);
  return friends;
}

export default function Friends() {
  const { user, goTab, places, reservedKey } = useContext(AppCtx);
  const fs = useApi(`/api/friends?${qs({ user })}`);
  const cs = useApi(`/api/compat?${qs({ user })}`);
  const roomFriends = useRoomFriends(user);

  // 지도: 단톡방 친구들이 예약한 곳을 친구 이름 핀으로 (내 예약은 "예약" 표시로 따로 보임)
  const pinsKey = (roomFriends || []).flatMap(f => f.rsv.map(r => f.name + r.id)).join(",");
  usePins("friends:" + user + ":" + pinsKey + ":" + reservedKey, () => {
    const byId = new Map(places.map(p => [p.place_id, p]));
    const active = new Map();
    (roomFriends || []).forEach(f => f.rsv.forEach(r => {
      const p = byId.get(toPlaceId(r.place_id));
      if (!p) return;
      const prev = active.get(p.place_id);
      active.set(p.place_id, { ...p, label: prev ? `${prev.label}·${f.name}` : f.name });
    }));
    const act = [...active.values()];
    if (act.length) PLMap.show(places, act);
    else PLMap.show(places, [], { fit: false, view: places.filter(p => p.lat > 37) });
  });

  if (!fs) return <div className="empty">불러오는 중…</div>;
  const score = Object.fromEntries((cs || []).map(c => [c.name, c.score]));
  const shown = new Set((roomFriends || []).map(f => f.name));
  const others = fs.filter(f => !shown.has(f.name));
  return (
    <>
      <div className="sec">단톡방 친구 <span className="cnt">{roomFriends ? roomFriends.length : "…"}</span>
        <span className="small" style={{ fontWeight: 500 }}>· 같은 채팅방 멤버는 자동으로 친구</span></div>
      {roomFriends && !roomFriends.length && <div className="empty small-empty">아직 같은 채팅방에 있는 사람이 없어요</div>}
      {(roomFriends || []).map(f => (
        <div className="friend" key={"room:" + f.name}>
          <div className="head">
            <Avatar name={f.name} size="sm" />
            <div className="grow" style={{ flex: 1, minWidth: 0 }}>
              <b>{f.name}</b> <span className="badge f">단톡방</span>
              <div className="small">{f.rooms.join(", ")}</div>
              {Object.keys(f.profile).length > 0 && <ProfTemps p={f.profile} />}
            </div>
            {score[f.name] != null && (
              <div className="mscore" onClick={() => goTab("compat", f.name)}>{score[f.name]}<small>궁합</small></div>
            )}
          </div>
          {f.rsv.map(r => (
            <div className="frsv" key={r.id} onClick={() => PLMap.focus(toPlaceId(r.place_id))}>
              <span className="b mine">예약</span> <b>{r.place_name}</b>
              <span className="small"> · {fmtWhen(r.reserved_at)} · {r.party_size}명</span>
            </div>
          ))}
          {f.lists.map(c => <FolderRow key={c.list_id} c={c} />)}
          {!f.rsv.length && !f.lists.length && <div className="small fnone">아직 예약이나 리스트가 없어요</div>}
        </div>
      ))}

      {others.length > 0 && (
        <div className="sec">친밀도 높은 순 <span className="small" style={{ fontWeight: 500 }}>· 1:1 대화 빈도 기준</span></div>
      )}
      {others.map(f => (
        <div className="friend" key={f.name}>
          <div className="head">
            <Avatar name={f.name} size="sm" />
            <div className="grow" style={{ flex: 1, minWidth: 0 }}>
              <b>{f.name}</b> <span className="small">친밀도 {f.intimacy}</span>
              <div className="small">{f.bio}</div>
              <ProfTemps p={f.profile} />
            </div>
            {score[f.name] != null && (
              <div className="mscore" onClick={() => goTab("compat", f.name)}>{score[f.name]}<small>궁합</small></div>
            )}
          </div>
          {f.lists.map(c => <FolderRow key={c.list_id} c={c} />)}
        </div>
      ))}
    </>
  );
}
