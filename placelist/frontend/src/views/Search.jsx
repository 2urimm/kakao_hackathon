import { useContext } from "react";
import { AppCtx } from "../context.js";
import { qs, useApi } from "../api.js";
import { PLMap } from "../map.js";
import { usePins } from "../pins.js";
import { Avatar, Ico, tColor } from "../ui.jsx";
import { fmtWhen } from "../chat.js";

function ParsedChips({ q }) {
  const c = [];
  if (q.업종) c.push(q.업종);
  if (q.지역) c.push(q.지역 + (q._지역출처 ? " (주 활동 지역)" : ""));
  [...(q.목적 || []), ...(q.분위기 || []), ...(q.메뉴 || [])].forEach(x => c.push(x));
  if (q.디자이너) c.push(q.디자이너 + " 디자이너");
  if (q.가격상한) c.push("₩".repeat(q.가격상한) + " 이하");
  if (q.인원) c.push(q.인원 + "명");
  if (q.상담스타일) c.push("상담 " + q.상담스타일);
  if (q.웨이팅없음) c.push("웨이팅 없음");
  if (q.주차) c.push("주차");
  if (q.늦게까지) c.push("늦게까지");
  if (q.작업하기좋음) c.push("작업하기 좋음");
  return (
    <div className="parsed">
      {c.map(x => <span key={x} className="ptag">{x}</span>)}
      {(q.제외 || [])[0] && <span className="ptag x">{q.제외[0]}</span>}
    </div>
  );
}

function ResultCard({ u, main }) {
  const { openList, rsvByPlace } = useContext(AppCtx);
  const p = u.place;
  const mine = rsvByPlace.get(p.place_id);
  return (
    <div className={`rcard ${main ? "main" : ""}`} onClick={() => PLMap.focus(p.place_id)}>
      {main ? <div className="kick">이번엔 여기</div> : <span className="axis">{u.axis}</span>}
      {mine && <span className="b mine" style={{ marginLeft: 6 }}>내 예약 · {fmtWhen(mine[0].reserved_at)}</span>}
      <div className="t"><Ico n={p.업종} px={14} /> {p.name}{u.designer && <span className="d small"> · {u.designer} 디자이너</span>}</div>
      <div className="small">{p.지역} · {"₩".repeat(p.가격대)} · {p.분위기.join(", ")}</div>
      {u.list ? (
        <div className="src">
          <Avatar name={u.list.curator} size="sm" />
          <div>
            <b>{u.list.curator}</b>님(<span className="temp" style={{ color: tColor(u.curator_temp) }}>{u.curator_temp}℃</span>)의{" "}
            <span className="linkish" onClick={e => { e.stopPropagation(); openList(u.list.id); }}>'{u.list.title}'</span>
            <div className="small">{u.tier_name}</div>
          </div>
        </div>
      ) : <div className="small" style={{ marginTop: 6 }}>리스트에 담긴 적 없는 곳 · 카카오맵 장소 태그로 찾음</div>}
      {u.comment && <div className="memo">“{u.comment}”</div>}
      <div className="bs">
        {u.verified && <span className="b ok">방문 인증 ✓</span>}
        {u.revisit > 0 && <span className="b ok">재방문 {u.revisit}회</span>}
        {(u.also_curators || []).length > 0 && <span className="b">{u.also_curators.join(", ")}님도 담음</span>}
        {(u.matched || []).map(m => <span key={m} className="b">✔ {m}</span>)}
      </div>
    </div>
  );
}

export default function Search({ q }) {
  const { user, places, openList } = useContext(AppCtx);
  const r = useApi(`/api/search?${qs({ q, user })}`, false);
  usePins("search:" + q + user + (r ? "1" : "0"), () => {
    if (!r) return;
    if (!r.main) return PLMap.show(places, []);
    const seen = new Set();
    const pts = [r.main, ...r.alternatives].map((u, i) => ({ ...u.place, label: i === 0 ? "★" : String(i + 1) }))
      .filter(p => !seen.has(p.place_id) && seen.add(p.place_id));
    PLMap.show(places, pts, { highlight: r.main.place.place_id });
  });
  if (!r) return <div className="empty">찾는 중…</div>;
  return (
    <>
      <ParsedChips q={r.query} />
      <div className="notes">{r.notes.map(n => <div key={n}>· {n}</div>)}</div>
      {!r.main ? <div className="empty">조건에 맞는 곳을 못 찾았어요</div> : (
        <>
          {r.follow_suggest && (
            <div className="suggest">
              <span><b>{r.follow_suggest}</b>님은 이 분야 온도가 높은 큐레이터예요</span>
              <span className="linkish" onClick={() => openList(r.main.list.id)}>리스트 보기</span>
            </div>
          )}
          <ResultCard u={r.main} main />
          {r.alternatives.length > 0 && <div className="sec">다른 선택지</div>}
          {r.alternatives.map(a => <ResultCard key={a.place.place_id} u={a} />)}
        </>
      )}
    </>
  );
}
