// 路书编辑器纯函数：与 app.js 的路书视图逐行对应，拆出以便 node:test 无浏览器测试。
// 数据契约：后端 store 序列化器（routebook detail：name/mode/preset/points/stops/geometry/mileage_km/
// mileage_manual；point：name/lat/lng/pos_kind/stop_type/stop_name/stop_note）。

export const MODES = ["driving", "cycling", "walking"];

export const MODE_LABELS = { driving: "自驾", cycling: "骑行", walking: "徒步" };

export const STOP_TYPE_LABELS = {
  charging: "充电",
  fuel: "加油",
  scene: "景点",
  lodging: "食宿",
};

export function modeLabel(mode) {
  return MODE_LABELS[mode] || mode || "—";
}

export function stopLabel(p) {
  return p && p.stop_type ? STOP_TYPE_LABELS[p.stop_type] || p.stop_type : null;
}

// 每模式 3 档预设（与后端 routing._PRESET_MULT 键对齐）
export function presetOptions(mode) {
  const map = {
    driving: [["balanced", "均衡"], ["fast", "偏高速"], ["scenic", "走风景"]],
    cycling: [["balanced", "均衡"], ["greenway", "偏绿道"], ["fast", "偏快捷"]],
    walking: [["balanced", "均衡"], ["offroad", "走野路"], ["fast", "偏快捷"]],
  };
  return (map[mode] || map.driving).map(([key, label]) => ({ key, label }));
}

// 后端 point → 编辑器点（snake → camel + hasCoords）
export function normalizePoints(rawPoints) {
  return (rawPoints || []).map((p) => ({
    id: p.id,
    name: p.name || "",
    lat: p.lat ?? null,
    lng: p.lng ?? null,
    posKind: p.pos_kind || "none",
    hasCoords: p.lat != null && p.lng != null,
    stopType: p.stop_type || null,
    stopName: p.stop_name || "",
    stopNote: p.stop_note || "",
  }));
}

// 编辑器点 → API 载荷（camel → snake；去掉纯前端 id）
export function pointsToPayload(points) {
  return (points || []).map((p) => ({
    name: p.name || "",
    lat: p.lat ?? null,
    lng: p.lng ?? null,
    pos_kind: p.posKind || "none",
    stop_type: p.stopType || null,
    stop_name: p.stopName || "",
    stop_note: p.stopNote || "",
  }));
}

export function emptyEditorState() {
  return {
    id: null,
    name: "",
    mode: "driving",
    preset: "balanced",
    points: [],
    stops: [],
    line: null,
    source: "engine",
    overrideGeo: null,
    drawMode: false,
    mileageKm: null,
    mileageManual: false,
    dirty: false,
    error: "",
    nav: null,
  };
}

// 编辑器状态机（纯函数；每次 dispatch 返回新状态）
export function editorReducer(state, action) {
  const s = state || emptyEditorState();
  switch (action.type) {
    case "load": {
      const book = action.book || {};
      const points = normalizePoints(book.points);
      const geo = book.geometry && book.geometry.geojson ? book.geometry.geojson : null;
      const source = (book.geometry && book.geometry.source) || "engine";
      return {
        ...emptyEditorState(),
        id: book.id ?? null,
        name: book.name || "",
        mode: book.mode || "driving",
        preset: book.preset || "balanced",
        points,
        stops: (book.stops || []).map((x) => ({ ...x })),
        line: source === "engine" ? geo : null,
        overrideGeo: source === "override" ? geo : null,
        mileageKm: book.mileage_km ?? null,
        mileageManual: !!book.mileage_manual,
      };
    }
    case "setName":
      return { ...s, name: action.name || "", dirty: true };
    case "setMode": {
      const mode = action.mode;
      return { ...s, mode, preset: presetOptions(mode)[0].key, dirty: true };
    }
    case "setPreset":
      return { ...s, preset: action.preset, dirty: true };
    case "addPoint": {
      const pts = s.points.map((p) => ({ ...p }));
      pts.push({
        id: action.id,
        name: action.name || "",
        lat: action.lat,
        lng: action.lng,
        posKind: "exact",
        hasCoords: true,
        stopType: null,
        stopName: "",
        stopNote: "",
      });
      return { ...s, points: pts, dirty: true };
    }
    case "movePoint": {
      const i = s.points.findIndex((p) => p.id === action.id);
      if (i < 0) return s;
      const pts = s.points.map((p) => ({ ...p }));
      pts[i] = { ...pts[i], lat: action.lat, lng: action.lng, posKind: "exact", hasCoords: true };
      return { ...s, points: pts, dirty: true };
    }
    case "removePoint":
      return { ...s, points: s.points.filter((p) => p.id !== action.id), dirty: true };
    case "setStopType": {
      const i = s.points.findIndex((p) => p.id === action.id);
      if (i < 0) return s;
      const pts = s.points.map((p) => ({ ...p }));
      pts[i] = { ...pts[i], stopType: action.stopType || null };
      return { ...s, points: pts, dirty: true };
    }
    case "renamePoint": {
      const i = s.points.findIndex((p) => p.id === action.id);
      if (i < 0) return s;
      const pts = s.points.map((p) => ({ ...p }));
      pts[i] = { ...pts[i], name: action.name || "" };
      return { ...s, points: pts, dirty: true };
    }
    case "setManualMileage":
      return { ...s, mileageKm: action.km ?? null, mileageManual: action.km != null, dirty: true };
    case "setDrawMode":
      return { ...s, drawMode: !!action.on, dirty: true };
    case "drawVertex": {
      const coords = s.overrideGeo && s.overrideGeo.coordinates ? s.overrideGeo.coordinates.slice() : [];
      coords.push([action.lng, action.lat]);
      return { ...s, overrideGeo: { type: "LineString", coordinates: coords }, source: "override", dirty: true };
    }
    case "applyOverride":
      return { ...s, line: s.overrideGeo, source: "override", drawMode: false, dirty: true };
    case "clearOverride":
      return { ...s, overrideGeo: null, line: null, source: "engine", drawMode: false, dirty: true };
    case "setNav":
      return { ...s, nav: action.nav, dirty: false };
    case "setError":
      return { ...s, error: action.error || "", dirty: false };
    case "saved":
      return { ...s, dirty: false };
    default:
      return s;
  }
}