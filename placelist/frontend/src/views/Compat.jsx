import { useContext } from "react";
import { AppCtx } from "../context.js";
import { qs, useApi } from "../api.js";
import { PLMap } from "../map.js";
import { usePins } from "../pins.js";
import { Ico } from "../ui.jsx";

const compatLabel = s =>
  s >= 85 ? ["찰떡궁합", "#e8523f"] : s >= 70 ? ["잘 맞아요", "#1A73E8"] : s >= 55 ? ["무난해요", "#2fa36b"] : ["새로운 취향", "#8b95a1"];

export default function Compat() {
  const { user, places, compatOpen, setCompatOpen } = useContext(AppCtx);
  const cs = useApi(`/api/compat?${qs({ user })}`);
  const open = cs && (cs.find(c => c.name === compatOpen) ? compatOpen : cs[0]?.name);
  const cur = cs && cs.find(c => c.name === open);

  usePins("compat:" + user + ":" + open + ":" + (cs ? cs.length : 0), () => {
    if (!cur) return PLMap.show(places, [], { fit: false });
    const byId = Object.fromEntries(places.map(p => [p.place_id, p]));
    const pts = [...cur.shared.map(p => ({ ...byId[p.place_id], label: "함께" })), ...cur.try.map(p => ({ ...byId[p.place_id], label: "추천" }))]
      .filter(p => p.place_id);
    PLMap.show(places, pts, { fit: pts.length > 0 });
  });

  if (!cs) return <div className="empty">불러오는 중…</div>;
  return (
    <>
      <div className="chero"><h3>{user}님 × 친구 리스트 궁합</h3><p>취향 · 겹치는 장소 · 활동 동네 · 가격대를 합쳐 계산해요</p></div>
      {cs.length ? cs.map((c, i) => {
        const [lab, col] = compatLabel(c.score), isOpen = c.name === open;
        return (
          <div key={c.name} className={`ccard ${isOpen ? "open" : ""}`} onClick={() => setCompatOpen(c.name)}>
            <div className="hd">
              <div className="ring" style={{ "--p": c.score, "--c": col }}><span>{c.score}</span></div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="nm"><span className="rk" style={{ background: i === 0 ? "var(--gold)" : "var(--silver)" }}>{i + 1}위</span>{c.name}</div>
                <div className="lab" style={{ color: col }}>{lab}</div>
                <div className="small">{c.bio}</div>
              </div>
            </div>
            <div className="cbars">
              {Object.entries(c.parts).map(([k, v]) => (
                <div key={k} style={{ display: "contents" }}>
                  <div>{k}</div><div className="cbar"><i style={{ width: `${v}%` }} /></div><div className="v">{v}</div>
                </div>
              ))}
            </div>
            {isOpen && (
              <div className="cextra">
                {c.common_tags.length > 0 && (
                  <div><div className="lbl">둘 다 좋아하는 분위기</div><div className="tags">{c.common_tags.map(t => <span key={t} className="tag">{t}</span>)}</div></div>
                )}
                <div>
                  <div className="lbl">둘 다 저장한 곳 {c.n_shared}곳</div>
                  <div className="tags">
                    {c.shared.length ? c.shared.map(p => <span key={p.place_id} className="tag pl"><Ico n="star" px={11} /> {p.name}</span>)
                      : <span className="small">아직 겹치는 곳이 없어요</span>}
                  </div>
                </div>
                {c.try.length > 0 && (
                  <div>
                    <div className="lbl">{c.name}님만 가본 곳 · 가볼까요?</div>
                    <div className="tags">{c.try.map(p => <span key={p.place_id} className="tag try"><Ico n="pin" px={11} /> {p.name}</span>)}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      }) : <div className="empty">비교할 친구 리스트가 없어요</div>}
    </>
  );
}
