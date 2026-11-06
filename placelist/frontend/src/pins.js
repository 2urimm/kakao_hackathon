import { useContext, useEffect } from "react";
import { AppCtx } from "./context.js";
import { PLMap } from "./map.js";

/** key 가 바뀔 때만 지도 핀을 다시 그린다 (예약 이벤트로 목록이 다시 읽혀도 지도가 튀지 않게). */
export function usePins(key, draw) {
  const { mapKind } = useContext(AppCtx);
  useEffect(() => { if (mapKind) draw(); }, [key, mapKind]);
}

/** 내가 예약한 곳이 있으면 그곳들로, 없으면 내 주 활동 지역으로 지도를 맞춘다 (장소가 서울·부산에 흩어져 있어서). */
export function useAllPins() {
  const { places, meta, user, reservedKey } = useContext(AppCtx);
  const home = meta.users[user]?.home_region;
  usePins("all:" + user + ":" + home + ":" + reservedKey, () => {
    const mine = new Set(reservedKey ? reservedKey.split(",") : []);
    const rsvPlaces = places.filter(p => mine.has(p.place_id));
    const view = rsvPlaces.length ? rsvPlaces : home ? places.filter(p => p.지역 === home) : places.filter(p => p.lat > 37);
    PLMap.show(places, [], { fit: false, view });
  });
}
