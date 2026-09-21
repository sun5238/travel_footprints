// 看板纯函数：与 app.js 原逻辑逐行对应，拆出以便 node:test 无浏览器测试。
// 数据契约来源：后端 travel/store.py 序列化器（键集见 tests/backend/test_contract.py）。

// places -> Map(id -> place)
export function indexPlaces(places) {
  const m = new Map();
  for (const p of places) m.set(p.id, p);
  return m;
}

// media -> Map(visit_id -> media[])，跳过无 visit 的待精分项
export function groupMediaByVisit(media) {
  const m = new Map();
  for (const item of media) {
    if (item.visit_id == null) continue;
    if (!m.has(item.visit_id)) m.set(item.visit_id, []);
    m.get(item.visit_id).push(item);
  }
  return m;
}

// visits -> 年份列表（降序）
export function yearsFromVisits(visits) {
  const ys = new Set();
  for (const v of visits) {
    const local = v.at && v.at.local;
    if (local && local.length >= 4) ys.add(local.slice(0, 4));
  }
  return [...ys].sort().reverse();
}

export function countPending(media) {
  let n = 0;
  for (const m of media) if (m.status === "pending") n += 1;
  return n;
}

export function pendingMedia(media) {
  return media.filter((m) => m.status === "pending");
}

// 时间轴过滤：年份 / 城市 / 类型 / 仅带媒体 / 关键词（地点名快照+现名+评价）
export function filterVisits({ visits, places, media, filters }) {
  const byId = indexPlaces(places);
  const mediaByVisit = groupMediaByVisit(media);
  return visits.filter((v) => {
    const place = byId.get(v.place_id) || null;
    if (filters.year) {
      const local = v.at && v.at.local;
      if ((local ? local.slice(0, 4) : "") !== filters.year) return false;
    }
    if (filters.cityId && place && String(place.city_id) !== filters.cityId) return false;
    if (filters.kind && place && place.kind !== filters.kind) return false;
    if (filters.hasMedia && !(mediaByVisit.get(v.id) || []).length) return false;
    if (filters.q) {
      const hay = `${v.place_name_snapshot} ${(place && place.name) || ""} ${v.review}`;
      if (!hay.includes(filters.q)) return false;
    }
    return true;
  });
}

// 地点列表过滤：城市 / 类型 / 仅带媒体（该地点任一到访有媒体）/ 关键词（名+备注）
export function filterPlaces({ places, visits, media, filters }) {
  return places.filter((p) => {
    if (filters.cityId && String(p.city_id) !== filters.cityId) return false;
    if (filters.kind && p.kind !== filters.kind) return false;
    if (filters.hasMedia) {
      const ids = new Set(visits.filter((v) => v.place_id === p.id).map((v) => v.id));
      if (!media.some((m) => m.visit_id != null && ids.has(m.visit_id))) return false;
    }
    if (filters.q && !(p.name + " " + p.note).includes(filters.q)) return false;
    return true;
  });
}

// 到访时间显示：T -> 空格、截到分钟
export function fmtDate(visit) {
  const local = visit.at && visit.at.local;
  return local ? local.replace("T", " ").slice(0, 16) : "未记录时间";
}

// 星级：满 5 颗，无评分显示"未评分"
export function stars(n) {
  return n ? "★".repeat(n) + "☆".repeat(5 - n) : "未评分";
}

// label_stats（后端 dashboard.stats.label_stats，[{label, count}]）-> 附加静态图标
// 图标目录是前端打包的静态表（草案 §6.1），缺省用兜底「🏷」。
export function labelStatsWithIcon(labelStats, catalog = {}) {
  return (labelStats || []).map((ls) => ({
    label: ls.label,
    count: ls.count,
    icon: catalog[ls.label] || "🏷",
  }));
}