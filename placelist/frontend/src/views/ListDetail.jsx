import { useContext, useEffect, useState } from "react";
import { AppCtx } from "../context.js";
import { api, qs, useApi } from "../api.js";
import { PLMap } from "../map.js";
import { usePins } from "../pins.js";
import { Avatar, DTemp, PIN_COLOR, ProfTemps, TierBadge, tColor, tierOf } from "../ui.jsx";
import { fmtWhen } from "../chat.js";

/** 리스트 레벨 (카카오맵 티어). 예약 확정으로 올랐으면 이전 레벨에서 새 레벨까지 숫자가 올라간다. */
function BigTemp({ d }) {
  const { flash } = useContext(AppCtx);
  const [shown, setShown] = useState(d.temp);
  useEffect(() => {
    if (flash && flash.list_id === d.list_id && flash.from != null && Date.now() < flash.until && flash.from !== d.temp) {
      const t0 = performance.now();
      let raf;
      const step = t => {
        const k = Math.min(1, (t - t0) / 1200);
        setShown(flash.from + (d.temp - flash.from) * k);
        if (k < 1) raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
      return () => cancelAnimationFrame(raf);
    }
    setShown(d.temp);
  }, [d.temp, d.list_id, flash]);
  return (
    <div>
      <div className="small">리스트 레벨</div>
      <div className="v" style={{ color: tColor(shown) }}>
        <TierBadge t={shown} px={26} /> {tierOf(shown).tier} Lv.{tierOf(shown).level}
      </div>
      <div className="small">{tierOf(shown).score.toLocaleString()}점 <DTemp d={d.temp_delta} /></div>
    </div>
  );
}

export default function ListDetail({ id }) {
  const { user, places, goBack, setTick, rsvByPlace } = useContext(AppCtx);
  const d = useApi(`/api/list?${qs({ id, user })}`);
  usePins("detail:" + id + (d ? d.items.length : 0), () => {
    if (d) PLMap.show(places, d.items.map((it, i) => ({ ...it, label: i + 1 })));
  });
  if (!d) return <div className="empty">불러오는 중…</div>;

  const parts = Object.entries(d.temp_parts);
  const maxAbs = Math.max(1, ...parts.map(([, v]) => Math.abs(v)));
  const st = d.temp_stats;
  const follow = async () => {
    await api("/api/follow", { method: "POST", body: JSON.stringify({ user, list_id: id, on: !d.followed }) });
    setTick(t => t + 1);
  };
  return (
    <>
      <div className="dhead">
        <button className="back" onClick={goBack}>‹ 뒤로</button>
        <div className="small">{d.source || ""} · {d.지역} · 구독 {d.subscribers}</div>
        <h2>{d.title}</h2>
        <div className="by">
          <Avatar name={d.curator} size="sm" />
          <div><b>{d.curator}</b>{d.intimacy ? <span className="small"> 친밀도 {d.intimacy}</span> : null}<ProfTemps p={d.curator_profile} /></div>
        </div>
        <div className="bigtemp">
          <BigTemp d={d} />
          {d.mine ? <span className="small">내 리스트</span>
            : <button className={`follow ${d.followed ? "on" : ""}`} onClick={follow}>{d.followed ? "구독 중" : "구독하기"}</button>}
        </div>
        <details className="why">
          <summary>이 레벨은 어떻게 정해졌나요?</summary>
          <div className="small" style={{ marginTop: 6 }}>
            골드 Lv.33에서 시작 · 좋았어요 {st["좋았어요"]}건, 별로였어요 {st["별로였어요"]}건 · 방문 인증 {Math.round(st["방문인증 비율"] * 100)}% · 재방문 {Math.round(st["재방문 비율"] * 100)}% · 평균 {st["평균 경과일"]}일 전 저장
          </div>
          <div className="parts">
            {parts.map(([k, v]) => {
              const w = Math.abs(v) / maxAbs * 50;
              const bar = v >= 0 ? { left: "50%", width: `${w}%`, background: "var(--ok)" } : { right: "50%", width: `${w}%`, background: "var(--bad)" };
              return (
                <div key={k} style={{ display: "contents" }}>
                  <div>{k}</div><div className="pbar"><i style={bar} /></div>
                  <div className="pv" style={{ color: v > 0 ? "var(--ok)" : v < 0 ? "var(--bad)" : "var(--sub)" }}>{v > 0 ? "+" : ""}{(v * 99 / 20).toFixed(1)}</div>
                </div>
              );
            })}
          </div>
        </details>
      </div>
      {d.items.map((it, i) => (
        <div className={`item ${rsvByPlace.has(it.place_id) ? "reserved" : ""}`} key={it.place_id} onClick={() => PLMap.focus(it.place_id)}>
          <div className="num" style={{ background: PIN_COLOR[it.업종] }}>{i + 1}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="t">{it.name}{it.designer && <span className="d"> · {it.designer} 디자이너</span>}</div>
            <div className="small">{it.업종} · {it.지역} · {"₩".repeat(it.가격대)} · {it.분위기.join(", ")}</div>
            {it.address && <div className="small">{it.address}{it.closed.length ? ` · ${it.closed[0]}` : ""}</div>}
            {it.comment && <div className="memo">{it.comment}</div>}
            <div className="bs">
              {(rsvByPlace.get(it.place_id) || []).map(r => <span key={r.id} className="b mine">내 예약 · {fmtWhen(r.reserved_at)}</span>)}
              {it.reservations > 0 && <span className="b res">예약 확정 {it.reservations}건</span>}
              {it.verified ? <span className="b ok">방문 인증 ✓</span> : <span className="b">방문 인증 없음</span>}
              {it.revisit > 0 && <span className="b ok">재방문 {it.revisit}회</span>}
              {it.feedback["좋았어요"] > 0 && <span className="b ok">보고 간 사람 좋았어요 {it.feedback["좋았어요"]}</span>}
              {it.feedback["별로였어요"] > 0 && <span className="b bad">별로였어요 {it.feedback["별로였어요"]}</span>}
              <span className="b">{it.saved_at} 저장</span>
            </div>
          </div>
        </div>
      ))}
    </>
  );
}
