// 路书编辑器纯函数测试（node --test，零依赖）。
// 数据契约来自后端 store 序列化器；fixture 形态与其对齐。
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  emptyEditorState,
  editorReducer,
  modeLabel,
  normalizePoints,
  pointsToPayload,
  presetOptions,
  stopLabel,
} from "../../frontend/logic_routebook.js";

const PTS = [
  { id: 1, name: "成都", lat: 30.65, lng: 104.06, pos_kind: "exact", stop_type: null, stop_name: "", stop_note: "" },
  { id: 2, name: "映秀", lat: 31.05, lng: 103.56, pos_kind: "exact", stop_type: "charging", stop_name: "映秀充电站", stop_note: "国网" },
  { id: 3, name: "无坐标点", lat: null, lng: null, pos_kind: "none", stop_type: null, stop_name: "", stop_note: "" },
];

test("presetOptions 每模式 3 档，骑行含偏绿道", () => {
  const driving = presetOptions("driving");
  assert.deepEqual(driving.map((p) => p.key), ["balanced", "fast", "scenic"]);
  const cycling = presetOptions("cycling");
  assert.equal(cycling.length, 3);
  assert.ok(cycling.some((p) => p.key === "greenway"));
  assert.equal(cycling[1].label, "偏绿道");
  // 未知模式退回自驾
  assert.equal(presetOptions("void")[0].key, "balanced");
});

test("modeLabel 中文化", () => {
  assert.equal(modeLabel("cycling"), "骑行");
  assert.equal(modeLabel("void"), "void");
});

test("stopLabel 映射停靠类型", () => {
  assert.equal(stopLabel({ stop_type: "charging" }), "充电");
  assert.equal(stopLabel({ stop_type: null }), null);
});

test("normalizePoints snake→camel 且标记有/无坐标", () => {
  const pts = normalizePoints(PTS);
  assert.equal(pts.length, 3);
  assert.equal(pts[0].posKind, "exact");
  assert.equal(pts[0].hasCoords, true);
  assert.equal(pts[2].hasCoords, false);
  assert.equal(pts[1].stopType, "charging");
});

test("pointsToPayload camel→snake 且不带前端 id", () => {
  const editor = normalizePoints(PTS);
  const payload = pointsToPayload(editor);
  assert.equal(payload[1].stop_type, "charging");
  assert.equal(payload[0].pos_kind, "exact");
  assert.equal("id" in payload[0], false);
});

test("editorReducer load 填充状态并还原几何来源", () => {
  const state = editorReducer(emptyEditorState(), {
    type: "load",
    book: {
      id: 7, name: "骑行", mode: "cycling", preset: "greenway",
      mileage_km: 9.0, mileage_manual: false,
      geometry: { source: "engine", geojson: { type: "LineString", coordinates: [[100, 30], [101, 30]] } },
      points: PTS, stops: [],
    },
  });
  assert.equal(state.id, 7);
  assert.equal(state.mode, "cycling");
  assert.equal(state.preset, "greenway");
  assert.equal(state.mileageKm, 9.0);
  assert.equal(state.line.type, "LineString");
  assert.equal(state.source, "engine");
  assert.equal(state.overrideGeo, null);
});

test("editorReducer 手工覆盖线：drawVertex→applyOverride→clearOverride", () => {
  let s = emptyEditorState();
  s = editorReducer(s, { type: "drawVertex", lng: 100, lat: 30 });
  s = editorReducer(s, { type: "drawVertex", lng: 101, lat: 30.5 });
  assert.equal(s.source, "override");
  assert.deepEqual(s.overrideGeo.coordinates, [[100, 30], [101, 30.5]]);
  s = editorReducer(s, { type: "applyOverride" });
  assert.equal(s.line.type, "LineString");
  assert.equal(s.source, "override");
  s = editorReducer(s, { type: "clearOverride" });
  assert.equal(s.line, null);
  assert.equal(s.source, "engine");
});

test("editorReducer 途经点增删移动（纯函数，不改原状态）", () => {
  const s0 = editorReducer(emptyEditorState(), { type: "load", book: { points: PTS } });
  const before = s0.points[0].lng;
  const s1 = editorReducer(s0, { type: "movePoint", id: 1, lat: 31, lng: 110 });
  assert.equal(s1.points[0].lng, 110);
  assert.equal(s0.points[0].lng, before); // 原状态未被改
  const s2 = editorReducer(s1, { type: "removePoint", id: 2 });
  assert.equal(s2.points.length, 2);
  assert.ok(s2.points.every((p) => p.id !== 2));
  const s3 = editorReducer(s2, { type: "addPoint", id: 99, lat: 33, lng: 108 });
  assert.equal(s3.points.length, 3);
  assert.equal(s3.points[2].posKind, "exact");
});

test("editorReducer 途经点改名", () => {
  const s0 = editorReducer(emptyEditorState(), { type: "load", book: { points: PTS } });
  const s1 = editorReducer(s0, { type: "renamePoint", id: 1, name: "成都市区" });
  assert.equal(s1.points[0].name, "成都市区");
  // 未知 id 不动
  const s2 = editorReducer(s1, { type: "renamePoint", id: 999, name: "x" });
  assert.equal(s2.points[1].name, "映秀");
});

test("editorReducer load 以服务端为准（后端重算已保手动值）", () => {
  const s = editorReducer(emptyEditorState(), { type: "setManualMileage", km: 88.5 });
  assert.equal(s.mileageKm, 88.5);
  assert.equal(s.mileageManual, true);
  const reloaded = editorReducer(s, { type: "load", book: { mileage_km: 9.0, mileage_manual: false } });
  assert.equal(reloaded.mileageKm, 9.0);
  assert.equal(reloaded.mileageManual, false);
});