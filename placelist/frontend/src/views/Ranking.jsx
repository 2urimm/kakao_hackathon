import { useContext } from "react";
import { AppCtx } from "../context.js";
import { qs, useApi } from "../api.js";
import { PLMap } from "../map.js";
import { usePins } from "../pins.js";
import { Avatar, DRank, DTemp, FolderRow, Ico, Lv, tColor, useFlashing } from "../ui.jsx";

function Podium({ c, i, kind, onCurator }) {
  const flashing = useFlashing();
  const { openList } = useContext(AppCtx);
  const cls = (i === 0 ? "first" : "") + (kind === "lists" && flashing(c.list_id) ? " flash" : "");
  if (kind === "lists") {
    return (
      <div className={`pcard ${cls}`} onClick={() => openList(c.list_id)}>
        <div className="top-r"><span className={`medal m${i + 1}`}>{i + 1}</span><span className="small sub">{c.지역} · <Ico n={c.업종} px={14} /> {c.업종}</span></div>
        <div className="pt">{c.title}</div>
        <div className="m">{c.curator} · {c.n_items}곳 · 구독 {c.subscribers}{c.friend ? " · 친구" : ""}</div>
        <div className="pv2" style={{ color: tColor(c.temp) }}><Lv t={c.temp} px={22} /> <DTemp d={c.temp_delta} /><DRank d={c.rank_delta} /></div>
        {i === 0 && <div className="prev">{(c.preview || []).map(n => <span key={n}>{n}</span>)}</div>}
      </div>
    );
  }
  return (
    <div className={`pcard ${cls}`} onClick={onCurator}>
      <div className="top-r"><span className={`medal m${i + 1}`}>{i + 1}</span><span className="small sub">{c.group}</span></div>
      <div className="pt">{c.curator}{c.friend && <span className="badge">친구</span>}</div>
      <div className="m">{c.bio}</div>
      <div className="pv2" style={{ color: tColor(c.temp) }}><Lv t={c.temp} px={22} /> <DTemp d={c.temp_delta} /><DRank d={c.rank_delta} /></div>
    </div>
  );
}

export default function Ranking() {
  const { user, meta, places, rank, setRank } = useContext(AppCtx);
  const rows = useApi(`/api/ranking?${qs({ ...rank, user })}`);
  const act = places.filter(p => (!rank.region || p.지역 === rank.region) && (!rank.category || p.업종 === rank.category));
  usePins("rank:" + rank.region + rank.category, () => PLMap.show(places, act, { fit: true }));

  const set = (k, v) => setRank(r => ({ ...r, [k]: v }));
  const chips = (key, arr) => [["", "전체"], ...arr.map(a => [a, a])].map(([v, l]) => (
    <button key={v} className={`chip ${rank[key] === v ? "on" : ""}`} onClick={() => set(key, v)}>{l}</button>
  ));
  const title = [rank.region || "전체 지역", rank.category || "전체 업종", rank.purpose].filter(Boolean).join(" · ");
  const toLists = () => set("kind", "lists");
  const top = rows ? rows.slice(0, 3) : [], rest = rows ? rows.slice(3) : [];

  return (
    <>
      <div className="rk-head">
        <div className="kind">
          <button className={rank.kind === "lists" ? "on" : ""} onClick={() => set("kind", "lists")}>리스트 랭킹</button>
          <button className={rank.kind === "curators" ? "on" : ""} onClick={() => set("kind", "curators")}>카이드 랭킹</button>
        </div>
        {rank.kind === "curators" && <div className="small kaide-note">카이드 = 카카오맵 + 가이드. 맛집·숙소·놀거리 리스트를 만들어 공유하는 사람</div>}
      </div>
      <div className="filters">
        <div className="line"><span className="lbl">지역</span>{chips("region", meta.regions)}</div>
        <div className="line"><span className="lbl">업종</span>{chips("category", meta.categories)}</div>
        <div className="line"><span className="lbl">상황</span>{chips("purpose", meta.purposes)}</div>
      </div>
      <div className="rtitle">{title}</div>
      <div className="small rsub">지역·업종별로 나눠 보면 동네 고수가 드러나요</div>
      {!rows ? <div className="empty">불러오는 중…</div> : rows.length ? (
        <>
          <div className="podium">{top.map((c, i) => <Podium key={c.list_id || c.curator} c={c} i={i} kind={rank.kind} onCurator={toLists} />)}</div>
          {rank.kind === "lists"
            ? rest.map((c, i) => <FolderRow key={c.list_id} c={c} rank={i + 4} />)
            : rest.map((c, i) => (
              <div className="row" key={c.curator} onClick={toLists}>
                <div className="rank-n">{i + 4}<DRank d={c.rank_delta} /></div><Avatar name={c.curator} size="sm" />
                <div className="grow">
                  <div className="t">{c.curator}{c.friend && <span className="badge f">친구</span>}</div>
                  <div className="m">{c.bio} · 조건 맞는 장소 {c.n_matched}곳</div>
                </div>
                <div className="right"><div className="temp" style={{ color: tColor(c.temp) }}><DTemp d={c.temp_delta} /><Lv t={c.temp} /></div><div className="small">{c.group}</div></div>
              </div>
            ))}
        </>
      ) : <div className="empty">조건에 맞는 리스트가 없어요</div>}
    </>
  );
}
