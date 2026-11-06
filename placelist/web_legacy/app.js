const ST = { user: "민준", tab: "mine", places: [], meta: null, back: null,
  rank: { region: "", category: "", purpose: "", kind: "lists" } };
// 카카오맵 스타일 아이콘 (인라인 SVG, 색은 currentColor)
const SVG = {
  star: '<path fill="currentColor" d="M12 2.6l2.9 6 6.6.9-4.8 4.6 1.2 6.6L12 17.5l-5.9 3.2 1.2-6.6L2.5 9.5l6.6-.9z"/>',
  "음식점": '<path fill="currentColor" d="M5.5 2h1.6v6.2h1.1V2h1.6v6.2h1.1V2h1.6v7.3a3.2 3.2 0 0 1-2.4 3.1V22H7.9V12.4a3.2 3.2 0 0 1-2.4-3.1zM17.3 2c-2.2 0-3.7 2.8-3.7 6.4 0 2.2 1 3.5 2.4 3.9V22h2.6V2z"/>',
  "카페": '<path fill="currentColor" d="M3.5 6h12.5v7.2a5 5 0 0 1-5 5H8.5a5 5 0 0 1-5-5zM16 8h1.7a2.6 2.6 0 0 1 0 5.2H16v-1.7h1.7a.9.9 0 0 0 0-1.8H16zM3.5 20h13v1.6h-13z"/>',
  "미용": '<g fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="6.2" cy="18" r="3"/><circle cx="17.8" cy="18" r="3"/><path d="M8.3 15.6 19.5 3M15.7 15.6 4.5 3"/></g>',
  pin: '<path fill="currentColor" d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7zm0 9.4A2.4 2.4 0 1 1 12 6.600a2.4 2.4 0 0 1 0 4.800z"/>',
};
const ico = (n, px = 18) => `<svg class="ic" width="${px}" height="${px}" viewBox="0 0 24 24" aria-hidden="true">${SVG[n] || SVG.star}</svg>`;
const ICON = new Proxy({}, { get: (_, k) => typeof k === "string" && SVG[k] ? ico(k, 14) : "" });
const PIN_COLOR = { "음식점": "var(--pin-food)", "카페": "var(--pin-cafe)", "미용": "var(--pin-beauty)" };
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const api = async (p, opt) => (await fetch(p, opt)).json();
const qs = o => Object.entries(o).map(([k, v]) => `${k}=${encodeURIComponent(v ?? "")}`).join("&");

// 온도 색: 낮음(회색) → 보통(파랑) → 좋음(초록) → 높음(주황) → 매우 높음(빨강)
function tColor(t) { return t < 34 ? "#8b95a1" : t < 38 ? "#1A73E8" : t < 42 ? "#2fa36b" : t < 46 ? "#f08a24" : "#e8523f"; }
function tpill(t, label) { return `<span class="tpill" style="color:${tColor(t)}">${label ? `<span class="small" style="font-weight:500">${esc(label)}</span>` : ""}${t.toFixed(1)}℃</span>`; }
function tbar(t) { const w = Math.max(4, Math.min(100, (t - 30) / 20 * 100)); return `<div class="tbar"><i style="width:${w}%;background:${tColor(t)}"></i></div>`; }
function profTemps(p) {
  return Object.entries(p).map(([k, v]) => tpill(v, k === "대표" ? "대표 " : k + " ")).join("");
}

// 카카오톡 기본 프로필 느낌: 파스텔 둥근 사각형 + 사람 실루엣
const AV_COLORS = ["#cfd8e8", "#f3d9b8", "#d3e6d0", "#e7d3ea", "#f1cfd2", "#cfe5ea", "#e9e3b8"];
function avatar(name, size) {
  let h = 0; for (const ch of String(name)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return `<div class="av ${size || ""}" style="background:${AV_COLORS[h % AV_COLORS.length]}"><svg viewBox="0 0 40 40"><circle cx="20" cy="15" r="7.5" fill="#fff"/><path d="M5 40c0-9 6.5-14 15-14s15 5 15 14z" fill="#fff"/></svg></div>`;
}

// 예약 확정으로 바뀐 값 표시: 온도 ▲0.6, 순위 ▲2
function dTemp(d) { return d > 0.04 ? `<span class="dt up">▲${d.toFixed(1)}</span>` : d < -0.04 ? `<span class="dt down">▼${Math.abs(d).toFixed(1)}</span>` : ""; }
function dRank(d) { return d > 0 ? `<span class="mv up">▲${d}</span>` : d < 0 ? `<span class="mv down">▼${-d}</span>` : ""; }
const flashing = id => ST.flash && ST.flash.list_id === id && Date.now() < ST.flash.until;

// ---------------------------------------------------------------- 공통 조각
function folderRow(c, rank) {
  const color = PIN_COLOR[c.업종] || "var(--accent)";
  return `<div class="row ${flashing(c.list_id) ? "flash" : ""}" data-list="${c.list_id}">
    ${rank ? `<div class="rank-n">${rank}${dRank(c.rank_delta || 0)}</div>` : ""}
    <div class="ficon" style="color:${color}">${ico(c.업종, 22)}</div>
    <div class="grow">
      <div class="t">${esc(c.title)}${c.friend ? `<span class="badge f">친구</span>` : ""}${c.followed ? `<span class="badge">구독 중</span>` : ""}</div>
      <div class="m">${esc(c.curator)} · ${c.n_items}곳${c.n_matched ? ` (조건 맞는 곳 ${c.n_matched})` : ""} · 구독 ${c.subscribers} · ${esc(c.지역)}</div>
    </div>
    <div class="right"><div class="temp" style="color:${tColor(c.temp)}">${dTemp(c.temp_delta || 0)}${c.temp.toFixed(1)}℃</div>${tbar(c.temp)}</div>
  </div>`;
}
function bindRows() {
  document.querySelectorAll("#view [data-list]").forEach(el => el.onclick = e => { e.stopPropagation(); openList(el.dataset.list); });
}
// 처음엔 내 주 활동 지역으로 지도를 맞춘다 (장소가 서울·부산에 흩어져 있어서)
function showAllPins() {
  const home = ST.meta.users[ST.user]?.home_region;
  const near = ST.places.filter(p => p.지역 === home);
  PLMap.show(ST.places, [], { fit: false, view: near });
}

// ---------------------------------------------------------------- 내 리스트
async function renderMine() {
  const [d, rsv] = await Promise.all([api(`/api/mylists?${qs({ user: ST.user })}`), api(`/api/reservations?${qs({ user: ST.user })}`)]);
  const bio = ST.meta.users[ST.user]?.bio || "";
  $("#view").innerHTML = `
    <div class="profile">${avatar(ST.user, "")}
      <div><div class="name">${esc(ST.user)}</div><div class="small">${esc(bio)}</div><div class="temps">${profTemps(d.profile)}</div></div></div>
    ${rsv.length ? `<div class="sec">내 예약 <span class="cnt">${rsv.length}</span></div>` + rsv.map(r => `
      <div class="rsv" ${r.list ? `data-list="${r.list.id}"` : ""}>
        <div class="badge-ok">예약 확정</div>
        <div class="rt">${esc(r.place.name)}</div>
        <div class="small">${esc(r.datetime || "")}${r.party_size ? " · " + r.party_size + "명" : ""} · ${esc(r.place.지역)}</div>
        ${r.list && r.effect ? `<div class="rfx">'${esc(r.list.title)}' 온도 ${r.effect.list_temp[0].toFixed(1)} → <b>${r.effect.list_temp[1].toFixed(1)}℃</b></div>` : ""}
      </div>`).join("") : ""}
    <div class="sec">내가 만든 리스트 ${d.own.length}</div>
    ${d.own.map(c => folderRow(c)).join("") || `<div class="empty">아직 리스트가 없어요</div>`}
    <div class="sec">구독 중인 리스트 ${d.followed.length}</div>
    ${d.followed.map(c => folderRow(c)).join("") || `<div class="empty">구독한 리스트가 없어요. 친구·랭킹 탭에서 찾아보세요</div>`}`;
  bindRows();
  showAllPins();
}

// ---------------------------------------------------------------- 친구
async function renderFriends() {
  const [fs, cs] = await Promise.all([api(`/api/friends?${qs({ user: ST.user })}`), api(`/api/compat?${qs({ user: ST.user })}`)]);
  const score = Object.fromEntries(cs.map(c => [c.name, c.score]));
  $("#view").innerHTML = fs.length ? `<div class="sec">친밀도 높은 순 <span class="small" style="font-weight:500">· 1:1 대화 빈도 기준</span></div>` + fs.map(f => `
    <div class="friend">
      <div class="head">${avatar(f.name, "sm")}
        <div class="grow" style="flex:1;min-width:0"><b>${esc(f.name)}</b> <span class="small">친밀도 ${f.intimacy}</span>
          <div class="small">${esc(f.bio)}</div><div class="temps">${profTemps(f.profile)}</div></div>
        ${score[f.name] != null ? `<div class="mscore" data-go="compat" data-f="${esc(f.name)}">${score[f.name]}<small>궁합</small></div>` : ""}</div>
      ${f.lists.map(c => folderRow(c)).join("")}
    </div>`).join("") : `<div class="empty">친구 리스트가 없어요</div>`;
  bindRows();
  document.querySelectorAll("[data-go]").forEach(el => el.onclick = () => { ST.tab = el.dataset.go; ST.compatOpen = el.dataset.f; render(); });
  showAllPins();
}

// ---------------------------------------------------------------- 궁합
function compatLabel(s) {
  return s >= 85 ? ["찰떡궁합", "#e8523f"] : s >= 70 ? ["잘 맞아요", "#1A73E8"] : s >= 55 ? ["무난해요", "#2fa36b"] : ["새로운 취향", "#8b95a1"];
}
async function renderCompat() {
  const cs = await api(`/api/compat?${qs({ user: ST.user })}`);
  const open = ST.compatOpen && cs.find(c => c.name === ST.compatOpen) ? ST.compatOpen : (cs[0] && cs[0].name);
  $("#view").innerHTML = `
    <div class="chero"><h3>${esc(ST.user)}님 × 친구 리스트 궁합</h3>
      <p>취향 · 겹치는 장소 · 활동 동네 · 가격대를 합쳐 계산해요</p></div>
    ${cs.length ? cs.map((c, i) => {
      const [lab, col] = compatLabel(c.score), isOpen = c.name === open;
      return `<div class="ccard ${isOpen ? "open" : ""}" data-f="${esc(c.name)}">
        <div class="hd">
          <div class="ring" style="--p:${c.score};--c:${col}"><span>${c.score}</span></div>
          <div style="flex:1;min-width:0">
            <div class="nm"><span class="rk" style="background:${i === 0 ? "var(--gold)" : "var(--silver)"}">${i + 1}위</span>${esc(c.name)}</div>
            <div class="lab" style="color:${col}">${lab}</div>
            <div class="small">${esc(c.bio)}</div>
          </div>
        </div>
        <div class="cbars">${Object.entries(c.parts).map(([k, v]) =>
          `<div>${esc(k)}</div><div class="cbar"><i style="width:${v}%"></i></div><div class="v">${v}</div>`).join("")}</div>
        ${isOpen ? `<div class="cextra">
          ${c.common_tags.length ? `<div><div class="lbl">둘 다 좋아하는 분위기</div><div class="tags">${c.common_tags.map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div></div>` : ""}
          <div><div class="lbl">둘 다 저장한 곳 ${c.n_shared}곳</div>
            <div class="tags">${c.shared.map(p => `<span class="tag pl">${ico("star", 11)} ${esc(p.name)}</span>`).join("") || `<span class="small">아직 겹치는 곳이 없어요</span>`}</div></div>
          ${c.try.length ? `<div><div class="lbl">${esc(c.name)}님만 가본 곳 · 가볼까요?</div><div class="tags">${c.try.map(p => `<span class="tag try">${ico("pin", 11)} ${esc(p.name)}</span>`).join("")}</div></div>` : ""}
        </div>` : ""}
      </div>`;
    }).join("") : `<div class="empty">비교할 친구 리스트가 없어요</div>`}`;
  document.querySelectorAll(".ccard").forEach(el => el.onclick = () => { ST.compatOpen = el.dataset.f; renderCompat(); });
  const c = cs.find(x => x.name === open);
  if (c) {
    const byId = Object.fromEntries(ST.places.map(p => [p.place_id, p]));
    const pts = [...c.shared.map(p => ({ ...byId[p.place_id], label: "함께" })), ...c.try.map(p => ({ ...byId[p.place_id], label: "추천" }))].filter(p => p.place_id);
    PLMap.show(ST.places, pts, { fit: pts.length > 0 });
  } else showAllPins();
}

// ---------------------------------------------------------------- 랭킹
function podiumCard(c, i, kind) {
  const cls = (i === 0 ? "first" : "") + (kind === "lists" && flashing(c.list_id) ? " flash" : ""), mc = `m${i + 1}`;
  if (kind === "lists") {
    return `<div class="pcard ${cls}" data-list="${c.list_id}">
      <div class="top-r"><span class="medal ${mc}">${i + 1}</span><span class="small sub">${esc(c.지역)} · ${ICON[c.업종]} ${esc(c.업종)}</span></div>
      <div class="pt">${esc(c.title)}</div>
      <div class="m">${esc(c.curator)} · ${c.n_items}곳 · 구독 ${c.subscribers}${c.friend ? " · 친구" : ""}</div>
      <div class="pv2" style="color:${tColor(c.temp)}">${c.temp.toFixed(1)}℃ ${dTemp(c.temp_delta || 0)}${dRank(c.rank_delta || 0)}</div>
      ${i === 0 ? `<div class="prev">${(c.preview || []).map(n => `<span>${esc(n)}</span>`).join("")}</div>` : ""}
    </div>`;
  }
  return `<div class="pcard ${cls}" data-curator="${esc(c.curator)}">
    <div class="top-r"><span class="medal ${mc}">${i + 1}</span><span class="small sub">${esc(c.group)}</span></div>
    <div class="pt">${esc(c.curator)}${c.friend ? `<span class="badge">친구</span>` : ""}</div>
    <div class="m">${esc(c.bio)}</div>
    <div class="pv2" style="color:${tColor(c.temp)}">${c.temp.toFixed(1)}℃ ${dTemp(c.temp_delta || 0)}${dRank(c.rank_delta || 0)}</div>
  </div>`;
}
async function renderRanking() {
  const r = ST.rank, m = ST.meta;
  const chips = (key, arr) => [["", "전체"], ...arr.map(a => [a, a])].map(([v, l]) =>
    `<button class="chip ${r[key] === v ? "on" : ""}" data-k="${key}" data-v="${v}">${l}</button>`).join("");
  const rows = await api(`/api/ranking?${qs({ ...r, user: ST.user })}`);
  const title = [r.region || "전체 지역", r.category || "전체 업종", r.purpose].filter(Boolean).join(" · ");
  const top = rows.slice(0, 3), rest = rows.slice(3);
  $("#view").innerHTML = `
    <div class="rk-head"><div class="kind">
      <button class="${r.kind === "lists" ? "on" : ""}" data-k="kind" data-v="lists">리스트 랭킹</button>
      <button class="${r.kind === "curators" ? "on" : ""}" data-k="kind" data-v="curators">큐레이터 랭킹</button></div></div>
    <div class="filters">
      <div class="line"><span class="lbl">지역</span>${chips("region", m.regions)}</div>
      <div class="line"><span class="lbl">업종</span>${chips("category", m.categories)}</div>
      <div class="line"><span class="lbl">상황</span>${chips("purpose", m.purposes)}</div>
    </div>
    <div class="rtitle">${esc(title)}</div>
    <div class="small rsub">지역·업종별로 나눠 보면 동네 고수가 드러나요</div>
    ${rows.length ? `<div class="podium">${top.map((c, i) => podiumCard(c, i, r.kind)).join("")}</div>
      ${rest.length ? (r.kind === "lists" ? rest.map((c, i) => folderRow(c, i + 4)).join("") : rest.map((c, i) => `
        <div class="row" data-curator="${esc(c.curator)}">
          <div class="rank-n">${i + 4}${dRank(c.rank_delta || 0)}</div>${avatar(c.curator, "sm")}
          <div class="grow"><div class="t">${esc(c.curator)}${c.friend ? `<span class="badge f">친구</span>` : ""}</div>
            <div class="m">${esc(c.bio)} · 조건 맞는 장소 ${c.n_matched}곳</div></div>
          <div class="right"><div class="temp" style="color:${tColor(c.temp)}">${dTemp(c.temp_delta || 0)}${c.temp.toFixed(1)}℃</div><div class="small">${esc(c.group)}</div></div>
        </div>`).join("")) : ""}`
      : `<div class="empty">조건에 맞는 리스트가 없어요</div>`}`;
  document.querySelectorAll("#view [data-k]").forEach(b => b.onclick = () => { ST.rank[b.dataset.k] = b.dataset.v; renderRanking(); });
  document.querySelectorAll("[data-curator]").forEach(el => el.onclick = () => {
    ST.rank.kind = "lists"; renderRanking();
  });
  bindRows();
  const act = ST.places.filter(p => (!r.region || p.지역 === r.region) && (!r.category || p.업종 === r.category));
  PLMap.show(ST.places, act, { fit: true });
}

// ---------------------------------------------------------------- 리스트 상세
async function openList(id, keep) {
  ST.mode = "detail"; ST.openId = id;
  const prevTab = ST.tab, prevScroll = $("#view").scrollTop;
  const d = await api(`/api/list?${qs({ id, user: ST.user })}`);
  const parts = Object.entries(d.temp_parts);
  const maxAbs = Math.max(1, ...parts.map(([, v]) => Math.abs(v)));
  const stats = d.temp_stats;
  $("#view").innerHTML = `
    <div class="dhead">
      <button class="back" id="back">‹ 뒤로</button>
      <div class="small">${esc(d.source || "")} · ${esc(d.지역)} · 구독 ${d.subscribers}</div>
      <h2>${esc(d.title)}</h2>
      <div class="by">${avatar(d.curator, "sm")}<div><b>${esc(d.curator)}</b>
        ${d.intimacy ? `<span class="small">친밀도 ${d.intimacy}</span>` : ""}<div class="temps">${profTemps(d.curator_profile)}</div></div></div>
      <div class="bigtemp">
        <div><div class="small">리스트 온도</div><div class="v" id="bigv" style="color:${tColor(d.temp)}">${d.temp.toFixed(1)}℃</div>${dTemp(d.temp_delta || 0)}</div>
        ${d.mine ? `<span class="small">내 리스트</span>` : `<button class="follow ${d.followed ? "on" : ""}" id="fol">${d.followed ? "구독 중" : "구독하기"}</button>`}
      </div>
      <details class="why"><summary>이 온도는 어떻게 나왔나요?</summary>
        <div class="small" style="margin-top:6px">36.5℃에서 시작 · 좋았어요 ${stats["좋았어요"]}건, 별로였어요 ${stats["별로였어요"]}건 · 방문 인증 ${Math.round(stats["방문인증 비율"] * 100)}% · 재방문 ${Math.round(stats["재방문 비율"] * 100)}% · 평균 ${stats["평균 경과일"]}일 전 저장</div>
        <div class="parts">${parts.map(([k, v]) => {
          const w = Math.abs(v) / maxAbs * 50;
          const bar = v >= 0 ? `left:50%;width:${w}%;background:var(--ok)` : `right:50%;width:${w}%;background:var(--bad)`;
          return `<div>${esc(k)}</div><div class="pbar"><i style="${bar}"></i></div><div class="pv" style="color:${v > 0 ? "var(--ok)" : v < 0 ? "var(--bad)" : "var(--sub)"}">${v > 0 ? "+" : ""}${v.toFixed(1)}</div>`;
        }).join("")}</div>
      </details>
    </div>
    ${d.items.map((it, i) => `
      <div class="item" data-pid="${it.place_id}">
        <div class="num" style="background:${PIN_COLOR[it.업종]}">${i + 1}</div>
        <div style="flex:1;min-width:0">
          <div class="t">${esc(it.name)}${it.designer ? ` <span class="d">· ${esc(it.designer)} 디자이너</span>` : ""}</div>
          <div class="small">${esc(it.업종)} · ${esc(it.지역)} · ${"₩".repeat(it.가격대)} · ${esc(it.분위기.join(", "))}</div>
          ${it.address ? `<div class="small">${esc(it.address)}${it.closed.length ? " · " + esc(it.closed[0]) : ""}</div>` : ""}
          ${it.comment ? `<div class="memo">${esc(it.comment)}</div>` : ""}
          <div class="bs">
            ${it.reservations ? `<span class="b res">예약 확정 ${it.reservations}건</span>` : ""}
            ${it.verified ? `<span class="b ok">방문 인증 ✓</span>` : `<span class="b">방문 인증 없음</span>`}
            ${it.revisit ? `<span class="b ok">재방문 ${it.revisit}회</span>` : ""}
            ${it.feedback["좋았어요"] ? `<span class="b ok">보고 간 사람 좋았어요 ${it.feedback["좋았어요"]}</span>` : ""}
            ${it.feedback["별로였어요"] ? `<span class="b bad">별로였어요 ${it.feedback["별로였어요"]}</span>` : ""}
            <span class="b">${esc(it.saved_at)} 저장</span>
          </div>
        </div>
      </div>`).join("")}`;
  $("#back").onclick = () => { ST.tab = prevTab; render().then(() => $("#view").scrollTop = prevScroll); };
  const fol = $("#fol");
  if (fol) fol.onclick = async () => {
    await api("/api/follow", { method: "POST", body: JSON.stringify({ user: ST.user, list_id: id, on: !d.followed }) });
    openList(id);
  };
  document.querySelectorAll(".item").forEach(el => el.onclick = () => PLMap.focus(el.dataset.pid));
  PLMap.show(ST.places, d.items.map((it, i) => ({ ...it, label: i + 1 })));
  $("#view").scrollTop = keep ? prevScroll : 0;
  if (ST.flash && ST.flash.list_id === id && ST.flash.from != null && Date.now() < ST.flash.until) countUp($("#bigv"), ST.flash.from, d.temp);
}
function countUp(el, from, to) {
  if (!el) return;
  const t0 = performance.now();
  const step = t => { const k = Math.min(1, (t - t0) / 1200); el.textContent = (from + (to - from) * k).toFixed(1) + "℃"; if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}

// ---------------------------------------------------------------- 검색
function parsedChips(q) {
  const c = [];
  if (q.업종) c.push(q.업종);
  if (q.지역) c.push(q.지역 + (q._지역출처 ? " (주 활동 지역)" : ""));
  [...(q.목적 || []), ...(q.분위기 || []), ...(q.메뉴 || [])].forEach(x => c.push(x));
  if (q.디자이너) c.push(q.디자이너 + " 디자이너");
  if (q.가격상한) c.push("₩".repeat(q.가격상한) + " 이하");
  if (q.인원) c.push(q.인원 + "명");
  if (q.상담스타일) c.push("상담 " + q.상담스타일);
  if (q.웨이팅없음) c.push("웨이팅 없음"); if (q.주차) c.push("주차"); if (q.늦게까지) c.push("늦게까지"); if (q.작업하기좋음) c.push("작업하기 좋음");
  return c.map(x => `<span class="ptag">${esc(x)}</span>`).join("") + ((q.제외 || [])[0] ? `<span class="ptag x">${esc(q.제외[0])}</span>` : "");
}
function resultCard(u, main) {
  const p = u.place;
  const src = u.list ? `<div class="src">${avatar(u.list.curator, "sm")}
      <div><b>${esc(u.list.curator)}</b>님(<span class="temp" style="color:${tColor(u.curator_temp)}">${u.curator_temp}℃</span>)의
      <span class="linkish" data-list="${u.list.id}">'${esc(u.list.title)}'</span><div class="small">${esc(u.tier_name)}</div></div></div>`
    : `<div class="small" style="margin-top:6px">리스트에 담긴 적 없는 곳 · 카카오맵 장소 태그로 찾음</div>`;
  return `<div class="rcard ${main ? "main" : ""}" data-pid="${p.place_id}">
    ${main ? `<div class="kick">이번엔 여기</div>` : `<span class="axis">${esc(u.axis)}</span>`}
    <div class="t">${ICON[p.업종]} ${esc(p.name)}${u.designer ? ` <span class="d small">· ${esc(u.designer)} 디자이너</span>` : ""}</div>
    <div class="small">${esc(p.지역)} · ${"₩".repeat(p.가격대)} · ${esc(p.분위기.join(", "))}</div>
    ${src}
    ${u.comment ? `<div class="memo">“${esc(u.comment)}”</div>` : ""}
    <div class="bs">${u.verified ? `<span class="b ok">방문 인증 ✓</span>` : ""}${u.revisit ? `<span class="b ok">재방문 ${u.revisit}회</span>` : ""}
      ${(u.also_curators || []).length ? `<span class="b">${esc(u.also_curators.join(", "))}님도 담음</span>` : ""}
      ${(u.matched || []).map(m => `<span class="b">✔ ${esc(m)}</span>`).join("")}</div>
  </div>`;
}
async function renderSearch(q) {
  ST.mode = "search";
  $("#view").innerHTML = `<div class="empty">찾는 중…</div>`;
  const r = await api(`/api/search?${qs({ q, user: ST.user })}`);
  document.querySelectorAll("#tabs button").forEach(b => b.classList.remove("on"));
  let h = `<div class="parsed">${parsedChips(r.query)}</div><div class="notes">${r.notes.map(n => `· ${esc(n)}`).join("<br>")}</div>`;
  if (!r.main) { $("#view").innerHTML = h + `<div class="empty">조건에 맞는 곳을 못 찾았어요</div>`; PLMap.show(ST.places, []); return; }
  if (r.follow_suggest) h += `<div class="suggest"><span><b>${esc(r.follow_suggest)}</b>님은 이 분야 온도가 높은 큐레이터예요</span><span class="linkish" data-list="${r.main.list.id}">리스트 보기</span></div>`;
  h += resultCard(r.main, true);
  if (r.alternatives.length) h += `<div class="sec">다른 선택지</div>` + r.alternatives.map(a => resultCard(a, false)).join("");
  $("#view").innerHTML = h;
  bindRows();
  document.querySelectorAll(".rcard").forEach(el => el.onclick = () => PLMap.focus(el.dataset.pid));
  const seen = new Set();
  const pts = [r.main, ...r.alternatives].map((u, i) => ({ ...u.place, label: i === 0 ? "★" : String(i + 1) }))
    .filter(p => !seen.has(p.place_id) && seen.add(p.place_id));
  PLMap.show(ST.places, pts, { highlight: r.main.place.place_id });
}

// ---------------------------------------------------------------- 탭·사용자
function render() {
  ST.mode = "tab";
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === ST.tab));
  return ({ mine: renderMine, friends: renderFriends, compat: renderCompat, ranking: renderRanking })[ST.tab]();
}
function renderUsers() {
  $("#users").innerHTML = Object.keys(ST.meta.users).map(u => `<button class="${u === ST.user ? "on" : ""}" data-u="${u}">${u}</button>`).join("");
}

// ---------------------------------------------------------------- 예약 확정 알림 (채팅 백엔드 → /api/reservation → 여기)
function toast(ev) {
  const e = ev.effect, p = ev.place;
  let fx = "";
  if (ev.type === "confirmed" && e) {
    const [b, a] = e.list_temp, [rb, ra] = e.rank;
    fx = `<div class="fx">'${esc(ev.list.title)}' 온도 <b>${b.toFixed(1)} → ${a.toFixed(1)}℃</b> <span class="dt up">▲${(a - b).toFixed(1)}</span></div>
      <div class="fx">${esc(e.curator)}님 ${esc(e.group)} 온도 ${e.curator_temp[0].toFixed(1)} → ${e.curator_temp[1].toFixed(1)}℃</div>
      <div class="fx">${esc(p.지역)} ${esc(p.업종)} 랭킹 ${ra == null ? "" : rb === ra ? `${ra}위 유지` : `<b>${rb}위 → ${ra}위</b> ${dRank(rb - ra)}`}</div>`;
  } else if (ev.type === "cancelled") fx = `<div class="fx">취소되어 온도 반영을 되돌렸어요</div>`;
  else if (ev.type === "pending") fx = `<div class="fx">확정되면 온도에 반영돼요</div>`;
  const head = { confirmed: "예약 확정", cancelled: "예약 취소", pending: "예약 요청" }[ev.type];
  const el = document.createElement("div");
  el.className = "toast " + ev.type;
  el.innerHTML = `<div class="th"><span class="tk">${head}</span><span class="tn">${esc(p.name)}</span></div>
    <div class="small">${esc(ev.user)}님 · ${esc(ev.datetime || "")}${ev.party_size ? " · " + ev.party_size + "명" : ""}</div>${fx}`;
  if (ev.list) el.onclick = () => { el.remove(); openList(ev.list.id); };
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 9000);
  while ($("#toasts").children.length > 3) $("#toasts").firstChild.remove();
}
async function pollEvents() {
  let r;
  try { r = await api(`/api/events?since=${ST.seq}`); } catch { return; }
  if (!r.events.length) return;
  ST.seq = r.last;
  r.events.forEach(ev => {
    toast(ev);
    if (ev.list && ev.effect) ST.flash = { list_id: ev.list.id, until: Date.now() + 6000, from: ev.type === "confirmed" ? ev.effect.list_temp[0] : null };
  });
  const redraw = () => { const sc = $("#view").scrollTop; if (ST.mode === "tab") render().then(() => $("#view").scrollTop = sc); };
  if (ST.mode === "detail") openList(ST.openId, true); else redraw();
  setTimeout(redraw, 6200);      // 깜빡임 끝나면 한 번 더 그려서 정리
}

async function init() {
  [ST.meta, ST.places] = await Promise.all([api("/api/meta"), api("/api/places")]);
  renderUsers();
  ST.seq = (await api("/api/events?since=0")).last;           // 이미 있던 이벤트는 알림 없이 건너뜀
  setInterval(pollEvents, 2000);
  $("#users").onclick = e => { const u = e.target.dataset.u; if (u) { ST.user = u; renderUsers(); render(); } };
  $("#tabs").onclick = e => { const t = e.target.dataset.tab; if (t) { ST.tab = t; render(); } };
  $("#sf").onsubmit = e => { e.preventDefault(); const q = $("#q").value.trim(); if (q) renderSearch(q); };
  // 주소 해시로 바로 열기: #friends, #compat, #ranking, #list=F02, #q=홍대 탈색
  const route = () => {
    const hash = decodeURIComponent(location.hash.slice(1));
    if (hash.startsWith("q=")) { $("#q").value = hash.slice(2); renderSearch(hash.slice(2)); }
    else if (hash.startsWith("list=")) openList(hash.slice(5));
    else { ST.tab = ["mine", "friends", "compat", "ranking"].includes(hash) ? hash : "mine"; render(); }
  };
  PLMap.init($("#map"), kind => {
    if (kind === "leaflet") document.body.insertAdjacentHTML("beforeend", `<div class="mapnote">대체 지도 · config.js에 카카오맵 키를 넣으면 카카오맵으로 바뀝니다</div>`);
    window.addEventListener("hashchange", route);
    route();
  });
}
init();
