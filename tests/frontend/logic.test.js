// 看板纯函数测试（node --test，零依赖）。
// 数据契约来自后端 travel/store.py 序列化器；fixture 形态与其对齐。
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  countPending,
  filterPlaces,
  filterVisits,
  fmtDate,
  groupMediaByVisit,
  indexPlaces,
  labelStatsWithIcon,
  pendingMedia,
  stars,
  yearsFromVisits,
} from "../../frontend/logic.js";

// ---- fixture（与后端响应形态一致） ----
const places = [
  { id: 1, city_id: 101, kind: "scene", name: "宽窄巷子", note: "", lat: 30.66, lng: 104.05, visit_count: 2 },
  { id: 2, city_id: 101, kind: "shop", name: "李姐面馆", note: "无坐标", lat: null, lng: null, visit_count: 1 },
  { id: 3, city_id: 102, kind: "landmark", name: "广州塔", note: "", lat: 23.1, lng: 113.3, visit_count: 1 },
];

const visits = [
  { id: 10, place_id: 1, trip_id: null, at: { local: "2024-10-02T20:00:00", tz: "Asia/Shanghai", epoch: 100 }, rating: 4, review: "人多但值得", place_name_snapshot: "宽窄巷子", tags: [] },
  { id: 11, place_id: 1, trip_id: null, at: { local: "2025-02-15T18:30:00", tz: "Asia/Shanghai", epoch: 200 }, rating: 5, review: "夜景更好看了", place_name_snapshot: "宽窄巷子", tags: [] },
  { id: 12, place_id: 2, trip_id: null, at: { local: "2024-10-04T11:30:00", tz: "Asia/Shanghai", epoch: 150 }, rating: null, review: "", place_name_snapshot: "李姐面馆", tags: [] },
  { id: 13, place_id: 3, trip_id: null, at: { local: "2025-03-16T19:30:00", tz: "Asia/Shanghai", epoch: 300 }, rating: 4, review: "登塔看夜景", place_name_snapshot: "广州塔", tags: [] },
];

const media = [
  { id: 1, kind: "photo", status: "attached", visit_id: 10, file: "/api/media/1/file", thumb: "/api/media/1/thumb" },
  { id: 2, kind: "photo", status: "attached", visit_id: 10, file: "/api/media/2/file", thumb: "/api/media/2/thumb" },
  { id: 3, kind: "video", status: "attached", visit_id: 11, file: "/api/media/3/file", thumb: "/api/media/3/thumb" },
  { id: 4, kind: "photo", status: "pending", visit_id: null, file: "/api/media/4/file", thumb: "/api/media/4/thumb" },
  { id: 5, kind: "video", status: "pending", visit_id: null, file: "/api/media/5/file", thumb: "/api/media/5/thumb" },
];

const emptyFilters = { year: "", cityId: "", kind: "", hasMedia: false, q: "" };

// ---- yearsFromVisits ----
test("years：跨年去重、降序", () => {
  assert.deepEqual(yearsFromVisits(visits), ["2025", "2024"]);
});
test("years：空数组返回空列表", () => {
  assert.deepEqual(yearsFromVisits([]), []);
});
test("years：无 at.local 的到访不计年份", () => {
  const v = [{ id: 1, at: null }, { id: 2, at: { local: "2023-11-01T00:00:00" } }];
  assert.deepEqual(yearsFromVisits(v), ["2023"]);
});

// ---- indexPlaces / groupMediaByVisit ----
test("indexPlaces：按 id 建索引", () => {
  const byId = indexPlaces(places);
  assert.equal(byId.get(2).name, "李姐面馆");
});
test("groupMediaByVisit：按 visit 聚合，跳过待精分", () => {
  const g = groupMediaByVisit(media);
  assert.equal(g.get(10).length, 2);
  assert.equal(g.get(11).length, 1);
  assert.equal(g.has(4), false);
});

// ---- countPending / pendingMedia ----
test("countPending：只计 pending", () => {
  assert.equal(countPending(media), 2);
});
test("pendingMedia：仅返回 status=pending 项", () => {
  assert.deepEqual(pendingMedia(media).map((m) => m.id), [4, 5]);
});

// ---- filterVisits ----
test("filterVisits：不过滤时原样返回", () => {
  assert.equal(filterVisits({ visits, places, media, filters: emptyFilters }).length, 4);
});
test("filterVisits：按年份过滤", () => {
  const out = filterVisits({ visits, places, media, filters: { ...emptyFilters, year: "2024" } });
  assert.deepEqual(out.map((v) => v.id), [10, 12]);
});
test("filterVisits：按城市过滤", () => {
  const out = filterVisits({ visits, places, media, filters: { ...emptyFilters, cityId: "101" } });
  assert.deepEqual(out.map((v) => v.id), [10, 11, 12]);
});
test("filterVisits：按类型过滤（shop）", () => {
  const out = filterVisits({ visits, places, media, filters: { ...emptyFilters, kind: "shop" } });
  assert.deepEqual(out.map((v) => v.id), [12]);
});
test("filterVisits：仅带媒体", () => {
  const out = filterVisits({ visits, places, media, filters: { ...emptyFilters, hasMedia: true } });
  assert.deepEqual(out.map((v) => v.id), [10, 11]); // visit 12 无媒体
});
test("filterVisits：关键词命中快照/现名/评价", () => {
  assert.equal(filterVisits({ visits, places, media, filters: { ...emptyFilters, q: "夜景" } }).length, 2);
  assert.equal(filterVisits({ visits, places, media, filters: { ...emptyFilters, q: "宽窄" } }).length, 2); // 快照+现名
});
test("filterVisits：组合条件（年份+类型）", () => {
  const out = filterVisits({ visits, places, media, filters: { ...emptyFilters, year: "2024", kind: "scene" } });
  assert.deepEqual(out.map((v) => v.id), [10]);
});

// ---- filterPlaces ----
test("filterPlaces：按城市过滤", () => {
  const out = filterPlaces({ places, visits, media, filters: { ...emptyFilters, cityId: "102" } });
  assert.deepEqual(out.map((p) => p.id), [3]);
});
test("filterPlaces：按类型过滤", () => {
  const out = filterPlaces({ places, visits, media, filters: { ...emptyFilters, kind: "landmark" } });
  assert.deepEqual(out.map((p) => p.id), [3]);
});
test("filterPlaces：仅带媒体", () => {
  const out = filterPlaces({ places, visits, media, filters: { ...emptyFilters, hasMedia: true } });
  assert.deepEqual(out.map((p) => p.id), [1]); // 宽窄有媒体；李姐面馆与广州塔（visit 无媒体）被排除
});
test("filterPlaces：关键词命中文名或备注", () => {
  assert.equal(filterPlaces({ places, visits, media, filters: { ...emptyFilters, q: "面馆" } }).length, 1);
  assert.equal(filterPlaces({ places, visits, media, filters: { ...emptyFilters, q: "无坐标" } }).length, 1);
});

// ---- fmtDate / stars ----
test("fmtDate：T 转空格并截到分钟", () => {
  assert.equal(fmtDate({ at: { local: "2024-10-02T20:30:45" } }), "2024-10-02 20:30");
});
test("fmtDate：无时间显示占位", () => {
  assert.equal(fmtDate({ at: null }), "未记录时间");
});
test("stars：满 5 颗、缺星补 ☆、无评分显示占位", () => {
  assert.equal(stars(5), "★★★★★");
  assert.equal(stars(4), "★★★★☆");
  assert.equal(stars(null), "未评分");
});

// ---- labelStatsWithIcon ----
const LABEL_ICONS = { 爬山: "🏔", 古镇: "🏘", 美食: "🍜" };
test("labelStatsWithIcon：附加静态图标", () => {
  const out = labelStatsWithIcon(
    [{ label: "爬山", count: 3 }, { label: "古镇", count: 2 }],
    LABEL_ICONS
  );
  assert.deepEqual(out, [
    { label: "爬山", count: 3, icon: "🏔" },
    { label: "古镇", count: 2, icon: "🏘" },
  ]);
});
test("labelStatsWithIcon：目录外标签用兜底图标", () => {
  const out = labelStatsWithIcon([{ label: "自定义X", count: 1 }], LABEL_ICONS);
  assert.equal(out[0].icon, "🏷");
});
test("labelStatsWithIcon：空数组/缺省返回空", () => {
  assert.deepEqual(labelStatsWithIcon([], LABEL_ICONS), []);
  assert.deepEqual(labelStatsWithIcon(undefined, LABEL_ICONS), []);
});