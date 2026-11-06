// 지도 어댑터: KAKAO_JS_KEY 가 있으면 카카오맵 JS SDK, 없으면 Leaflet + OpenStreetMap.
// 화면 코드는 PLMap.show / PLMap.focus 만 쓰므로 지도 종류와 상관없이 동작한다.
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const COLOR = { "음식점": "var(--pin-food)", "카페": "var(--pin-cafe)", "미용": "var(--pin-beauty)" };
const CENTER = [37.556, 126.926];
let kind = null, map = null, layers = [], byId = {};
let reserved = new Set();      // 내가 예약한 장소 id (채팅 서버) → 핀에 "예약" 표시
let lastShow = null;           // 예약이 바뀌면 같은 화면을 지도 이동 없이 다시 그리기 위해

function pinEl(p, opt) {
  const el = document.createElement("div");
  const rsv = reserved.has(p.place_id);
  el.className = "pin" + (opt.dim ? " dim" : "") + (opt.hl ? " hl" : "") + (rsv ? " rsv" : "") + (kind === "kakao" ? " k" : "");
  el.style.color = COLOR[p.업종] || "var(--accent)";
  el.style.setProperty("--c", el.style.color);
  const name = document.createTextNode(p.name);
  if (opt.dim) {
    el.innerHTML = `<div class="dot"></div>`;
    el.firstChild.title = p.name;
    el.style.transform = "translate(-50%,-50%)";
  } else {
    const bub = document.createElement("div");
    bub.className = "bub";
    if (rsv) { const r = document.createElement("span"); r.className = "rtag"; r.textContent = "예약"; bub.appendChild(r); }
    if (opt.label) { const b = document.createElement("b"); b.textContent = opt.label; bub.appendChild(b); }
    bub.appendChild(name);
    const tail = document.createElement("div");
    tail.className = "tail";
    el.append(bub, tail);
  }
  if (kind === "kakao") el.style.transform = "none";
  return el;
}

function clear() {
  layers.forEach(l => (kind === "kakao" ? l.setMap(null) : map.removeLayer(l)));
  layers = []; byId = {};
}

function add(p, opt) {
  const el = pinEl(p, opt);
  let layer;
  if (kind === "kakao") {
    layer = new kakao.maps.CustomOverlay({ position: new kakao.maps.LatLng(p.lat, p.lng), content: el, xAnchor: 0.5, yAnchor: opt.dim ? 0.5 : 1, zIndex: opt.dim ? 1 : 10 });
    layer.setMap(map);
  } else {
    layer = L.marker([p.lat, p.lng], { icon: L.divIcon({ html: el, className: "", iconSize: null }), zIndexOffset: opt.dim ? 0 : 1000 }).addTo(map);
  }
  layers.push(layer);
  if (!opt.dim) byId[p.place_id] = { p, el };
}

const leftPad = () => (window.innerWidth > 700 ? 420 : 20);

function fit(points) {
  if (!points.length) return;
  if (kind === "kakao") {
    const b = new kakao.maps.LatLngBounds();
    points.forEach(p => b.extend(new kakao.maps.LatLng(p.lat, p.lng)));
    map.setBounds(b, 60, 60, 60, leftPad());
  } else {
    map.fitBounds(points.map(p => [p.lat, p.lng]), { paddingTopLeft: [leftPad(), 60], paddingBottomRight: [60, 60], maxZoom: 16 });
  }
}

export const PLMap = {
  init(el, cb) {
    const key = (window.KAKAO_JS_KEY || "").trim();
    if (key) {
      const s = document.createElement("script");
      s.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(key)}&autoload=false`;
      s.onload = () => kakao.maps.load(() => {
        kind = "kakao";
        map = new kakao.maps.Map(el, { center: new kakao.maps.LatLng(...CENTER), level: 5 });
        cb(kind);
      });
      s.onerror = () => this._leaflet(el, cb);
      document.head.appendChild(s);
    } else this._leaflet(el, cb);
  },
  _leaflet(el, cb) {
    kind = "leaflet";
    map = L.map(el, { zoomControl: false }).setView(CENTER, 15);
    L.control.zoom({ position: "topright" }).addTo(map);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
    cb(kind);
  },
  // all: 배경으로 흐리게 보여줄 장소들, active: 강조할 장소들 [{...place, label}]
  show(all, active, opts = {}) {
    if (!map) return;
    lastShow = [all, active, opts];
    clear();
    const act = new Set(active.map(a => a.place_id));
    // 배경 장소는 흐린 점, 단 내가 예약한 곳은 이름 말풍선 + "예약" 표시로 항상 보이게
    all.filter(p => !act.has(p.place_id)).forEach(p => add(p, { dim: !reserved.has(p.place_id) }));
    active.forEach(a => add(a, { label: a.label, hl: a.place_id === opts.highlight }));
    if (opts.fit !== false) fit(active.length ? active : all);
    else if (opts.view && opts.view.length) fit(opts.view);
  },
  /** 내 예약 장소가 바뀌면 지금 화면을 지도 이동 없이 다시 그린다. */
  setReserved(ids) {
    const next = new Set(ids);
    if (next.size === reserved.size && [...next].every(i => reserved.has(i))) return;
    reserved = next;
    if (lastShow) { const [a, b, o] = lastShow; this.show(a, b, { ...o, fit: false, view: null }); }
  },
  focus(id) {
    Object.values(byId).forEach(v => v.el.classList.remove("hl"));
    const v = byId[id];
    if (!v) return;
    v.el.classList.add("hl");
    if (kind === "kakao") map.panTo(new kakao.maps.LatLng(v.p.lat, v.p.lng));
    else map.panTo([v.p.lat, v.p.lng]);
  },
};
