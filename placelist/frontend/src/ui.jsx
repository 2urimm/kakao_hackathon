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

// ---- 티어·레벨 (카카오맵 배지 티어표 그대로: app.map.kakao.com/info/timeline/score/table.html)
//  브론즈 Lv1~10 (0~49점) · 실버 Lv11~30 (50~399) · 골드 Lv31~60 (400~3,499) · 블루 Lv61~80 (3,500~8,499) · 퍼플 Lv81~100 (8,500~19,300)
// 계산은 서버의 온도(30~50℃) 그대로 쓰고, 화면에서만 레벨 1~100 으로 고르게 펼친다 (1℃ ≈ 5레벨).
const LEVEL_START = (() => {
  const steps = [[0, 5], [50, 10], [150, 25], [400, 60], [1000, 100], [2000, 150], [3500, 200], [5500, 300], [8500, 450], [13000, 700]];
  const a = [];
  steps.forEach(([base, step]) => { for (let i = 0; i < 10; i++) a.push(base + step * i); });
  a[99] = 19300;                                  // 레벨100 = 19,300점
  return a;                                       // a[lv-1] = 그 레벨 시작 점수
})();
export const TIERS = [
  { name: "브론즈", from: 1, color: "#c8743a" },
  { name: "실버", from: 11, color: "#8e9aab" },
  { name: "골드", from: 31, color: "#e8a800" },
  { name: "블루", from: 61, color: "#2b7de9" },
  { name: "퍼플", from: 81, color: "#a93ad6" },
];
const LV_PER_DEG = 99 / 20;
/** 온도 → {level, tier, color, score} */
export function tierOf(t) {
  const x = Math.min(100, Math.max(1, 1 + (t - 30) * LV_PER_DEG));
  const level = Math.floor(x);
  const start = LEVEL_START[level - 1], next = level < 100 ? LEVEL_START[level] : start;
  const tier = [...TIERS].reverse().find(tt => level >= tt.from);
  return { level, tier: tier.name, color: tier.color, score: Math.round(start + (x - level) * (next - start)) };
}
export const tierText = t => { const v = tierOf(t); return `${v.tier} Lv.${v.level}`; };
export const tColor = t => tierOf(t).color;
/** 배지 아이콘 (티어 색 육각형 + 별) */
export const TierBadge = ({ t, px = 14 }) => (
  <svg className="tier-badge" width={px} height={px} viewBox="0 0 24 24" aria-hidden="true">
    <path fill={tColor(t)} d="M12 1.5 21.1 6.75v10.5L12 22.5 2.9 17.25V6.75z" />
    <path fill="#fff" d="M12 6.8l1.5 3.1 3.4.5-2.5 2.4.6 3.4-3-1.6-3 1.6.6-3.4-2.5-2.4 3.4-.5z" />
  </svg>
);
/** "🛡 Lv.75" (마우스를 올리면 "블루 · 6,912점") */
export const Lv = ({ t, full = false }) => {
  const v = tierOf(t);
  return (
    <span className="lv" style={{ color: v.color }} title={`${v.tier} Lv.${v.level} · ${v.score.toLocaleString()}점`}>
      <TierBadge t={t} />{full ? `${v.tier} ` : ""}Lv.{v.level}
    </span>
  );
};
export const Tpill = ({ t, label }) => (
  <span className="tpill" style={{ color: tColor(t) }}>
    {label && <span className="small" style={{ fontWeight: 500 }}>{label}</span>}<Lv t={t} />
  </span>
);
export const Tbar = ({ t }) => {
  const w = Math.max(4, tierOf(t).level);
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
// 온도 변화 → 레벨 변화 (1℃ ≈ 5레벨)
export const DTemp = ({ d = 0 }) => {
  const l = Math.round(d * LV_PER_DEG);
  return d > 0.04 ? <span className="dt up">▲{l || ""}</span> : d < -0.04 ? <span className="dt down">▼{-l || ""}</span> : null;
};
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
        <div className="temp" style={{ color: tColor(c.temp) }}><DTemp d={c.temp_delta} /><Lv t={c.temp} /></div>
        <Tbar t={c.temp} />
      </div>
    </div>
  );
}
