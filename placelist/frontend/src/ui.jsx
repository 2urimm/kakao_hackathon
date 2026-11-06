import { useContext } from "react";
import { AppCtx } from "./context.js";

// ---- 카카오맵 스타일 아이콘 (인라인 SVG, 색은 currentColor)
const SVG = {
  star: <path fill="currentColor" d="M12 2.6l2.9 6 6.6.9-4.8 4.6 1.2 6.6L12 17.5l-5.9 3.2 1.2-6.6L2.5 9.5l6.6-.9z" />,
  "음식점": <path fill="currentColor" d="M5.5 2h1.6v6.2h1.1V2h1.6v6.2h1.1V2h1.6v7.3a3.2 3.2 0 0 1-2.4 3.1V22H7.9V12.4a3.2 3.2 0 0 1-2.4-3.1zM17.3 2c-2.2 0-3.7 2.8-3.7 6.4 0 2.2 1 3.5 2.4 3.9V22h2.6V2z" />,
  "카페": <path fill="currentColor" d="M3.5 6h12.5v7.2a5 5 0 0 1-5 5H8.5a5 5 0 0 1-5-5zM16 8h1.7a2.6 2.6 0 0 1 0 5.2H16v-1.7h1.7a.9.9 0 0 0 0-1.8H16zM3.5 20h13v1.6h-13z" />,
  "미용": <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="6.2" cy="18" r="3" /><circle cx="17.8" cy="18" r="3" /><path d="M8.3 15.6 19.5 3M15.7 15.6 4.5 3" /></g>,
  pin: <path fill="currentColor" d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7zm0 9.4A2.4 2.4 0 1 1 12 6.6a2.4 2.4 0 0 1 0 4.8z" />,
};
export const Ico = ({ n, px = 18 }) => (
  <svg className="ic" width={px} height={px} viewBox="0 0 24 24" aria-hidden="true">{SVG[n] || SVG.star}</svg>
);
export const PIN_COLOR = { "음식점": "var(--pin-food)", "카페": "var(--pin-cafe)", "미용": "var(--pin-beauty)" };

// ---- 온도: 낮음(회색) → 보통(파랑) → 좋음(초록) → 높음(주황) → 매우 높음(빨강)
export const tColor = t => (t < 34 ? "#8b95a1" : t < 38 ? "#1A73E8" : t < 42 ? "#2fa36b" : t < 46 ? "#f08a24" : "#e8523f");
export const Tpill = ({ t, label }) => (
  <span className="tpill" style={{ color: tColor(t) }}>
    {label && <span className="small" style={{ fontWeight: 500 }}>{label}</span>}{t.toFixed(1)}℃
  </span>
);
export const Tbar = ({ t }) => {
  const w = Math.max(4, Math.min(100, (t - 30) / 20 * 100));
  return <div className="tbar"><i style={{ width: `${w}%`, background: tColor(t) }} /></div>;
};
export const ProfTemps = ({ p }) => (
  <div className="temps">
    {Object.entries(p).map(([k, v]) => <Tpill key={k} t={v} label={k === "대표" ? "대표 " : k + " "} />)}
  </div>
);

// ---- 카카오톡 기본 프로필 느낌: 파스텔 둥근 사각형 + 사람 실루엣
const AV_COLORS = ["#cfd8e8", "#f3d9b8", "#d3e6d0", "#e7d3ea", "#f1cfd2", "#cfe5ea", "#e9e3b8"];
export function Avatar({ name, size = "" }) {
  let h = 0;
  for (const ch of String(name)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return (
    <div className={`av ${size}`} style={{ background: AV_COLORS[h % AV_COLORS.length] }}>
      <svg viewBox="0 0 40 40"><circle cx="20" cy="15" r="7.5" fill="#fff" /><path d="M5 40c0-9 6.5-14 15-14s15 5 15 14z" fill="#fff" /></svg>
    </div>
  );
}

// ---- 예약 확정으로 바뀐 값: 온도 ▲0.6, 순위 ▲2
export const DTemp = ({ d = 0 }) =>
  d > 0.04 ? <span className="dt up">▲{d.toFixed(1)}</span> : d < -0.04 ? <span className="dt down">▼{Math.abs(d).toFixed(1)}</span> : null;
export const DRank = ({ d = 0 }) =>
  d > 0 ? <span className="mv up">▲{d}</span> : d < 0 ? <span className="mv down">▼{-d}</span> : null;

export function useFlashing() {
  const { flash } = useContext(AppCtx);
  return id => !!flash && flash.list_id === id && Date.now() < flash.until;
}

// ---- 리스트 한 줄 (내 리스트·친구·랭킹 공통)
export function FolderRow({ c, rank }) {
  const { openList } = useContext(AppCtx);
  const flashing = useFlashing();
  return (
    <div className={`row ${flashing(c.list_id) ? "flash" : ""}`} onClick={e => { e.stopPropagation(); openList(c.list_id); }}>
      {rank ? <div className="rank-n">{rank}<DRank d={c.rank_delta} /></div> : null}
      <div className="ficon" style={{ color: PIN_COLOR[c.업종] || "var(--accent)" }}><Ico n={c.업종} px={22} /></div>
      <div className="grow">
        <div className="t">{c.title}{c.friend && <span className="badge f">친구</span>}{c.followed && <span className="badge">구독 중</span>}</div>
        <div className="m">{c.curator} · {c.n_items}곳{c.n_matched ? ` (조건 맞는 곳 ${c.n_matched})` : ""} · 구독 {c.subscribers} · {c.지역}</div>
      </div>
      <div className="right">
        <div className="temp" style={{ color: tColor(c.temp) }}><DTemp d={c.temp_delta} />{c.temp.toFixed(1)}℃</div>
        <Tbar t={c.temp} />
      </div>
    </div>
  );
}
