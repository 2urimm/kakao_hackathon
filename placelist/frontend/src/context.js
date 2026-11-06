import { createContext } from "react";

/** 앱 전체 상태: user, meta, places, tick(예약 이벤트로 갱신), flash, 탭·보기 이동 함수 등 */
export const AppCtx = createContext(null);
