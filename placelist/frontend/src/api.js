import { useContext, useEffect, useRef, useState } from "react";
import { AppCtx } from "./context.js";

// ngrok 무료 링크의 "Visit Site" 경고 화면이 API 응답 대신 오지 않게 하는 헤더 (같은 주소라 다른 곳엔 영향 없음)
export const NO_WARN = { "ngrok-skip-browser-warning": "1" };
export const api = async (p, opt = {}) => (await fetch(p, { ...opt, headers: { ...NO_WARN, ...(opt.headers || {}) } })).json();
export const qs = o => Object.entries(o).map(([k, v]) => `${k}=${encodeURIComponent(v ?? "")}`).join("&");

const cache = new Map();        // 주소 → 마지막 응답 (뒤로 가기·탭 전환 때 바로 보여주고 뒤에서 새로 읽음)

/** GET 하고 결과를 state로. 예약 이벤트가 오면(tick) 같은 주소를 다시 읽는다. url이 null이면 쉼. */
export function useApi(url, live = true) {
  const { tick } = useContext(AppCtx);
  const [data, setData] = useState(() => (url ? cache.get(url) ?? null : null));
  const last = useRef(url);
  useEffect(() => {
    if (!url) return;
    let off = false;
    if (last.current !== url) setData(cache.get(url) ?? null);   // 다른 주소면 캐시(없으면 빈 값), 같은 주소의 새로고침이면 유지
    last.current = url;
    api(url).then(d => { cache.set(url, d); if (!off) setData(d); }).catch(() => {});
    return () => { off = true; };
  }, [url, live ? tick : 0]);
  return data;
}
