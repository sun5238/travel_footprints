import * as maplibregl from "/vendor/maplibre/maplibre-gl.mjs";
import {
  countPending,
  filterPlaces,
  filterVisits,
  fmtDate as tfFmtDate,
  groupMediaByVisit,
  indexPlaces,
  labelStatsWithIcon,
  pendingMedia,
  stars as tfStars,
  yearsFromVisits,
} from "/logic.js";
import {
  emptyEditorState,
  editorReducer,
  modeLabel as rbModeLabel,
  pointsToPayload,
  presetOptions as rbPresetOptions,
} from "/logic_routebook.js";

const { createApp, ref, reactive, computed, onMounted, watch, nextTick } = Vue;

async function api(path, options = {}) {
  const res = await fetch("/api" + path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch (_e) {
      /* 保留 statusText */
    }
    throw new Error(detail);
  }
  return res;
}

const ICON_TRASH =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2m1 0v14H7V6"/><path d="M10 11v6M14 11v6"/></svg>';
const ICON_DOWNLOAD =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16"/></svg>';
const ICON_UPLOAD =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 21V9m0 0l-4 4m4-4l4 4M4 3h16"/></svg>';
const ICON_BOARD =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>';
const ICON_GEAR =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.9l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.9-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1-1.6 1.7 1.7 0 00-1.9.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.9 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.6-1 1.7 1.7 0 00-.3-1.9l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.9.3h.1a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5h.1a1.7 1.7 0 001.9-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.9v.1a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/></svg>';
const KIND_LABEL = { scene: "景点", shop: "店铺", landmark: "地标" };

// M2 活动标签静态目录（草案 §6.1，前端打包，非数据库表）；新标签走目录扩充 + 自由输入
const LABEL_ICONS = {
  爬山: "🏔",
  徒步: "🥾",
  骑行: "🚴",
  露营: "⛺",
  漂流: "🚣",
  越野跑: "🏃",
  滑雪: "🎿",
  溯溪: "💧",
  古镇: "🏘",
  美食: "🍜",
  古迹: "🏛",
  海滩: "🏖",
  雪山: "❄",
  演出: "🎭",
  城市漫游: "🚶",
};

createApp({
  setup() {
    const view = ref("board");
    const tab = ref("timeline");
    const dashboard = ref({ stats: {}, lit_cities: [], recent_trips: [] });
    const cities = ref([]);
    const places = ref([]);
    const visits = ref([]);
    const mediaList = ref([]);
    const selectedCityId = ref(null);
    const selectedPlaceId = ref(null);
    const toastMsg = ref("");

    const filters = reactive({ year: "", cityId: "", kind: "", hasMedia: false, q: "" });
    const addCityName = ref("");
    const addPlaceName = ref("");
    const addPlaceKind = ref("scene");
    const visitForm = reactive({ date: "", rating: 5, review: "" });
    const pickedFiles = ref([]);
    const busy = ref(false);

    let map = null;
    const citiesSourceId = "cities";
    const placesSourceId = "places";

    const placeById = computed(() => indexPlaces(places.value));
    const mediaByVisit = computed(() => groupMediaByVisit(mediaList.value));
    const placeOfVisit = (v) => placeById.value.get(v.place_id);
    const years = computed(() => yearsFromVisits(visits.value));
    const pendingCount = computed(() => countPending(mediaList.value));
    const labelCards = computed(() =>
      labelStatsWithIcon((dashboard.value.stats && dashboard.value.stats.label_stats) || [], LABEL_ICONS)
    );

    const filteredVisits = computed(() =>
      filterVisits({ visits: visits.value, places: places.value, media: mediaList.value, filters })
    );

    const filteredPlaces = computed(() =>
      filterPlaces({ places: places.value, visits: visits.value, media: mediaList.value, filters })
    );

    const selectedPlace = computed(() =>
      selectedPlaceId.value != null ? placeById.value.get(selectedPlaceId.value) : null
    );

    const selectedPlaceVisits = computed(() =>
      visits.value
        .filter((v) => v.place_id === selectedPlaceId.value)
        .sort((a, b) => ((a.at && a.at.epoch) || 0) - ((b.at && b.at.epoch) || 0))
    );

    const selectedCityVisits = computed(() =>
      visits.value.filter(
        (v) => selectedCityId.value != null && placeOfVisit(v) && placeOfVisit(v).city_id === selectedCityId.value
      )
    );

    function toast(msg) {
      toastMsg.value = msg;
      setTimeout(() => (toastMsg.value = ""), 2600);
    }

    async function loadAll() {
      try {
        dashboard.value = await (await api("/dashboard")).json();
        cities.value = await (await api("/cities")).json();
        visits.value = await (await api("/visits")).json();
        mediaList.value = await (await api("/media")).json();
        await loadPlaces();
      } catch (e) {
        toast(String(e.message || e));
      }
    }

    async function loadPlaces() {
      const params = new URLSearchParams({ lit: "1" });
      if (selectedCityId.value != null) params.set("city_id", String(selectedCityId.value));
      places.value = await (await api("/places?" + params.toString())).json();
      if (selectedPlaceId.value != null && !places.value.some((p) => p.id === selectedPlaceId.value)) {
        selectedPlaceId.value = null;
      }
    }

    function ensureMap() {
      if (map) return;
      map = new maplibregl.Map({
        container: "map",
        center: [104.06, 30.67],
        zoom: 3.6,
        style: {
          version: 8,
          sources: {},
          layers: [{ id: "bg", type: "background", paint: { "background-color": "#e8edf3" } }],
        },
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
      map.on("click", (e) => {
        const features = map.queryRenderedFeatures(e.point, { layers: ["city-glow", "place-dot"] });
        if (features.length) {
          const p = features[0].properties;
          if (p.role === "city") selectCityById(Number(p.id));
          else selectPlaceById(Number(p.id));
        }
      });
      map.on("mousemove", (e) => {
        const features = map.queryRenderedFeatures(e.point, { layers: ["city-glow", "place-dot"] });
        map.getCanvas().style.cursor = features.length ? "pointer" : "";
      });
    }

    function syncMapSources() {
      ensureMap();
      const litCities = dashboard.value.lit_cities || [];
      const cityFeatures = litCities
        .filter((c) => c.lat != null && c.lng != null)
        .map((c) => ({
          type: "Feature",
          properties: { id: c.id, name: c.name, visit_count: c.visit_count, role: "city" },
          geometry: { type: "Point", coordinates: [c.lng, c.lat] },
        }));
      const placeFeatures = filteredPlaces.value
        .filter((p) => p.lat != null && p.lng != null)
        .map((p) => ({
          type: "Feature",
          properties: { id: p.id, name: p.name, kind: p.kind, role: "place" },
          geometry: { type: "Point", coordinates: [p.lng, p.lat] },
        }));

      const setSource = (id, data) => {
        if (map.getSource(id)) map.getSource(id).setData(data);
        else {
          map.addSource(id, { type: "geojson", data });
          if (id === citiesSourceId) {
            map.addLayer({
              id: "city-glow",
              type: "circle",
              source: id,
              paint: {
                "circle-color": "#f59e0b",
                "circle-radius": ["interpolate", ["linear"], ["get", "visit_count"], 1, 14, 40, 34],
                "circle-opacity": 0.85,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 2,
              },
            });
          } else {
            map.addLayer({
              id: "place-dot",
              type: "circle",
              source: id,
              paint: {
                "circle-color": [
                  "match",
                  ["get", "kind"],
                  "shop",
                  "#c2410c",
                  "landmark",
                  "#6d28d9",
                  "#0f766e",
                ],
                "circle-radius": 8,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 1.5,
              },
            });
          }
        }
      };
      setSource(citiesSourceId, { type: "FeatureCollection", features: cityFeatures });
      setSource(placesSourceId, { type: "FeatureCollection", features: placeFeatures });

      const pts = [...cityFeatures, ...placeFeatures];
      if (pts.length) {
        const bounds = new maplibregl.LngLatBounds();
        for (const f of pts) bounds.extend(f.geometry.coordinates);
        map.fitBounds(bounds, { padding: 60, maxZoom: 10 });
      }
    }

    function selectCityById(id) {
      selectedCityId.value = id;
      selectedPlaceId.value = null;
      loadPlaces();
    }

    function selectCity(city) {
      selectCityById(city.id);
    }

    function selectPlaceById(id) {
      selectedPlaceId.value = id;
      tab.value = "timeline";
    }

    function selectPlace(place) {
      selectPlaceById(place.id);
    }

    async function addCity() {
      if (!addCityName.value.trim()) return;
      try {
        const city = await (await api("/cities", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ name: addCityName.value.trim() }),
        })).json();
        addCityName.value = "";
        cities.value = await (await api("/cities")).json();
        selectedCityId.value = city.id;
        await loadPlaces();
        toast("已添加城市");
      } catch (e) {
        toast(String(e.message || e));
      }
    }

    async function addPlace() {
      if (!addPlaceName.value.trim() || selectedCityId.value == null) return;
      try {
        const place = await (await api("/places", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            name: addPlaceName.value.trim(),
            kind: addPlaceKind.value,
            city_id: selectedCityId.value,
          }),
        })).json();
        addPlaceName.value = "";
        await loadPlaces();
        selectPlaceById(place.id);
        toast("已添加地点");
      } catch (e) {
        toast(String(e.message || e));
      }
    }

    function onPickFiles(e) {
      pickedFiles.value = Array.from(e.target.files || []);
    }

    async function addVisit() {
      if (!selectedPlace.value) return;
      busy.value = true;
      try {
        const visit = await (await api(`/places/${selectedPlace.value.id}/visits`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            at_local: visitForm.date || null,
            rating: Number(visitForm.rating) || null,
            review: visitForm.review,
          }),
        })).json();
        for (const file of pickedFiles.value) {
          await uploadSingle(file, visit.id);
        }
        pickedFiles.value = [];
        visitForm.review = "";
        await loadAll();
        toast("已记录到访");
      } catch (e) {
        toast(String(e.message || e));
      } finally {
        busy.value = false;
      }
    }

    async function uploadSingle(file, visitId) {
      const form = new FormData();
      form.append("file", file);
      if (visitId != null) form.append("visit_id", String(visitId));
      await api("/media", { method: "POST", body: form });
    }

    async function removePlace(place) {
      if (!window.confirm(`删除地点「${place.name}」及其到访记录？`)) return;
      await api(`/places/${place.id}`, { method: "DELETE" });
      if (selectedPlaceId.value === place.id) selectedPlaceId.value = null;
      await loadAll();
    }

    async function removeVisit(visit) {
      if (!window.confirm("删除这条到访记录？")) return;
      await api(`/visits/${visit.id}`, { method: "DELETE" });
      await loadAll();
    }

    async function removeMedia(item) {
      if (!window.confirm("删除这条媒体？")) return;
      await api(`/media/${item.id}`, { method: "DELETE" });
      await loadAll();
    }

    async function exportBackup() {
      const res = await api("/backup");
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = res.headers.get("content-disposition")
        ? "travel-footprints-backup.zip"
        : "travel-footprints-backup.zip";
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      toast("已导出备份");
    }

    async function doRestore(e) {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      if (!window.confirm("整体恢复会覆盖当前全部数据，确认继续？")) return;
      const form = new FormData();
      form.append("file", file);
      try {
        await api("/restore", { method: "POST", body: form });
        await loadAll();
        toast("恢复完成");
      } catch (err) {
        toast(String(err.message || err));
      } finally {
        e.target.value = "";
      }
    }

    const fmtDate = tfFmtDate;
    const stars = tfStars;

    // ---------- M4 路书（ADR-0008） ----------
    const rbView = ref("list");
    const rbList = ref([]);
    const rbName = ref("");
    const rbFilter = ref("");
    const rbBusy = ref(false);
    const rbEditor = ref(emptyEditorState());
    let rbMap = null;
    let rbMarkers = [];

    const filteredRbList = computed(() =>
      rbFilter.value ? rbList.value.filter((b) => b.mode === rbFilter.value) : rbList.value
    );

    function rbSet(action) {
      rbEditor.value = editorReducer(rbEditor.value, action);
    }

    async function loadRbList() {
      rbList.value = await (await api("/routebooks")).json();
    }

    async function createRb() {
      if (!rbName.value.trim()) return;
      rbBusy.value = true;
      try {
        const book = await (await api("/routebooks", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ name: rbName.value.trim(), mode: "driving" }),
        })).json();
        rbName.value = "";
        await loadRbList();
        await openRb(book.id);
        toast("已新建路书");
      } catch (e) {
        toast(String(e.message || e));
      } finally {
        rbBusy.value = false;
      }
    }

    async function openRb(id) {
      rbBusy.value = true;
      try {
        const book = await (await api(`/routebooks/${id}`)).json();
        rbSet({ type: "load", book });
        rbView.value = "editor";
        await nextTick();
        ensureRbMap();
        syncRbMap();
      } catch (e) {
        toast(String(e.message || e));
      } finally {
        rbBusy.value = false;
      }
    }

    function backToRbList() {
      rbView.value = "list";
      rbSet({ type: "clearOverride" });
      removeRbMap();
      loadRbList();
    }

    async function saveRb() {
      const s = rbEditor.value;
      if (!s.id) return;
      rbBusy.value = true;
      try {
        const book = await (await api(`/routebooks/${s.id}`, {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ name: s.name, mode: s.mode, preset: s.preset }),
        })).json();
        rbSet({ type: "load", book });
        await loadRbList();
        toast("已保存");
      } catch (e) {
        toast(String(e.message || e));
      } finally {
        rbBusy.value = false;
      }
    }

    async function patchRbPoints() {
      const s = rbEditor.value;
      if (!s.id) return;
      const book = await (await api(`/routebooks/${s.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          points: pointsToPayload(s.points),
          stops: s.stops.map((st) => ({
            name: st.name || "",
            lat: st.lat ?? null,
            lng: st.lng ?? null,
            pos_kind: st.posKind || "none",
            stop_type: st.stop_type || "scene",
            stop_note: st.stop_note || "",
          })),
        }),
      })).json();
      rbSet({ type: "load", book });
      await loadRbList();
    }

    async function recalcRb() {
      const s = rbEditor.value;
      if (!s.id) return;
      rbBusy.value = true;
      try {
        const book = await (await api(`/routebooks/${s.id}/recalc`, { method: "POST" })).json();
        rbSet({ type: "load", book });
        await loadRbList();
        toast("已重算");
      } catch (e) {
        rbSet({ type: "setError", error: String(e.message || e) });
        toast(String(e.message || e));
      } finally {
        rbBusy.value = false;
      }
    }

    function onRbMapClick(e) {
      const s = rbEditor.value;
      if (!s.id) return;
      const { lng, lat } = e.lngLat;
      if (s.drawMode) {
        rbSet({ type: "drawVertex", lng, lat });
      } else {
        rbSet({ type: "addPoint", id: Date.now(), lat, lng });
        patchRbPoints();
      }
    }

    function ensureRbMap() {
      if (rbMap) return;
      rbMap = new maplibregl.Map({
        container: "rb-map",
        center: [104.06, 30.67],
        zoom: 5,
        style: {
          version: 8,
          sources: {},
          layers: [{ id: "rb-bg", type: "background", paint: { "background-color": "#e8edf3" } }],
        },
      });
      rbMap.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
      rbMap.on("click", onRbMapClick);
      rbMap.on("mousemove", (e) => {
        const f = rbMap.queryRenderedFeatures(e.point, { layers: ["rb-route"] });
        rbMap.getCanvas().style.cursor = f.length ? "pointer" : "";
      });
    }

    function removeRbMap() {
      if (!rbMap) return;
      rbMap.remove();
      rbMap = null;
      rbMarkers = [];
    }

    function syncRbMap() {
      ensureRbMap();
      const s = rbEditor.value;
      const line = s.overrideGeo || s.line || null;
      const fc = line
        ? { type: "FeatureCollection", features: [{ type: "Feature", geometry: line, properties: {} }] }
        : { type: "FeatureCollection", features: [] };
      if (rbMap.getSource("rb-line")) rbMap.getSource("rb-line").setData(fc);
      else {
        rbMap.addSource("rb-line", { type: "geojson", data: fc });
        rbMap.addLayer({
          id: "rb-route",
          type: "line",
          source: "rb-line",
          paint: {
            "line-color": s.source === "override" ? "#0d9488" : "#2563eb",
            "line-width": 3,
            "line-opacity": 0.9,
          },
        });
      }
      for (const m of rbMarkers) m.remove();
      rbMarkers = [];
      for (const p of s.points) {
        if (!p.hasCoords) continue;
        const marker = new maplibregl.Marker({ draggable: true, color: s.source === "override" ? "#0d9488" : "#2563eb" })
          .setLngLat([p.lng, p.lat])
          .addTo(rbMap);
        marker.on("dragend", () => {
          const ll = marker.getLngLat();
          rbSet({ type: "movePoint", id: p.id, lat: ll.lat, lng: ll.lng });
          patchRbPoints();
        });
        rbMarkers.push(marker);
      }
    }

    async function removeRb(book) {
      if (!window.confirm(`删除路书「${book.name}」？`)) return;
      await api(`/routebooks/${book.id}`, { method: "DELETE" });
      await loadRbList();
    }

    async function downloadRes(rel, filename) {
      const res = await api(rel);
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    }

    async function exportRbGpx() {
      await downloadRes(`/routebooks/${rbEditor.value.id}/export.gpx`, "routebook.gpx");
      toast("已导出 GPX");
    }

    async function exportRbZip() {
      await downloadRes(`/routebooks/${rbEditor.value.id}/export`, `routebook-${rbEditor.value.id}.zip`);
      toast("已导出路书 zip");
    }

    async function importRb(e) {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const form = new FormData();
      form.append("file", file);
      try {
        await api("/routebooks/import", { method: "POST", body: form });
        await loadRbList();
        toast("已导入路书（新建一本，同名不覆盖）");
      } catch (err) {
        toast(String(err.message || err));
      } finally {
        e.target.value = "";
      }
    }

    async function loadRbNav() {
      const s = rbEditor.value;
      if (!s.id) return;
      rbSet({ type: "setNav", nav: await (await api(`/routebooks/${s.id}/nav`)).json() });
      toast("已生成导航交接");
    }

    function rbSetStopType(p, e) {
      rbSet({ type: "setStopType", id: p.id, stopType: e.target.value || null });
      patchRbPoints();
    }

    function rbRenamePoint(p, e) {
      rbSet({ type: "renamePoint", id: p.id, name: e.target.value });
      patchRbPoints();
    }

    function removeRbPoint(p) {
      rbSet({ type: "removePoint", id: p.id });
      patchRbPoints();
    }

    function openRbNav(href) {
      if (!window.confirm("此操作会打开外部导航应用（在线动作），确认继续？")) return;
      window.open(href, "_blank", "noreferrer");
    }

    function setRbManualMileage(e) {
      const v = e.target.value;
      rbSet({ type: "setManualMileage", km: v !== "" ? Number(v) : null });
      const s = rbEditor.value;
      if (!s.id) return;
      (async () => {
        try {
          const body = v !== "" ? { mileage_km: Number(v) } : {};
          if (Object.keys(body).length) {
            await api(`/routebooks/${s.id}`, {
              method: "PATCH",
              headers: { "content-type": "application/json" },
              body: JSON.stringify(body),
            });
          }
          await loadRbList();
        } catch (err) {
          toast(String(err.message || err));
        }
      })();
    }

    function applyOverrideRb() {
      const s = rbEditor.value;
      if (!s.id) return;
      rbSet({ type: "applyOverride" });
      if (!s.overrideGeo) return;
      (async () => {
        try {
          const book = await (await api(`/routebooks/${s.id}`, {
            method: "PATCH",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              geometry_source: "override",
              geometry_json: JSON.stringify(s.overrideGeo),
            }),
          })).json();
          rbSet({ type: "load", book });
          await loadRbList();
          toast("已应用覆盖线");
        } catch (err) {
          toast(String(err.message || err));
        }
      })();
    }

    function clearOverrideRb() {
      const s = rbEditor.value;
      if (!s.id) return;
      rbSet({ type: "clearOverride" });
      (async () => {
        try {
          const book = await (await api(`/routebooks/${s.id}`, {
            method: "PATCH",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ geometry_source: "engine" }),
          })).json();
          rbSet({ type: "load", book });
          await loadRbList();
        } catch (err) {
          toast(String(err.message || err));
        }
      })();
    }

    watch(
      () =>
        JSON.stringify({
          pts: rbEditor.value.points,
          line: rbEditor.value.line,
          ov: rbEditor.value.overrideGeo,
          src: rbEditor.value.source,
        }),
      () => {
        if (rbView.value === "editor") syncRbMap();
      }
    );

    onMounted(async () => {
      await loadAll();
      ensureMap();
      await nextTick();
      syncMapSources();
    });

    watch([dashboard, filteredPlaces], () => syncMapSources());

    return {
      view,
      tab,
      dashboard,
      cities,
      places: filteredPlaces,
      visits: filteredVisits,
      mediaList,
      selectedCityId,
      selectedPlace,
      selectedPlaceVisits,
      toastMsg,
      filters,
      years,
      pendingCount,
      labelCards,
      KIND_LABEL,
      addCityName,
      addPlaceName,
      addPlaceKind,
      visitForm,
      pickedFiles,
      busy,
      ICON_TRASH,
      ICON_DOWNLOAD,
      ICON_UPLOAD,
      ICON_BOARD,
      ICON_GEAR,
      citiesFilterOptions: computed(() => cities.value),
      selectCity,
      selectPlace,
      addCity,
      addPlace,
      addVisit,
      onPickFiles,
      removePlace,
      removeVisit,
      removeMedia,
      exportBackup,
      doRestore,
      fmtDate,
      stars,
      mediaOf: (visitId) => mediaByVisit.value.get(visitId) || [],
      allPendingMedia: computed(() => pendingMedia(mediaList.value)),
      // M4 路书
      rbView,
      rbList,
      rbName,
      rbFilter,
      rbBusy,
      rbEditor,
      filteredRbList,
      rbModeLabel,
      rbPresetOptions,
      createRb,
      openRb,
      backToRbList,
      saveRb,
      recalcRb,
      removeRb,
      exportRbGpx,
      exportRbZip,
      importRb,
      loadRbNav,
      rbSet,
      rbSetStopType,
      rbRenamePoint,
      removeRbPoint,
      setRbManualMileage,
      applyOverrideRb,
      clearOverrideRb,
      openRbNav,
    };
  },
  template: `
    <div class="topbar">
      <div class="brand">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 21c-4-3.5-7-6.8-7-10a7 7 0 0114 0c0 3.2-3 6.5-7 10z"/><circle cx="12" cy="10" r="2.5"/></svg>
        <span>旅行足迹</span>
      </div>
      <div class="nav-group">
        <button class="nav-btn" :class="{active: view==='board'}" @click="view='board'">看板</button>
        <button class="nav-btn" :class="{active: view==='routebooks'}" @click="view='routebooks'">路书</button>
        <button class="nav-btn" :class="{active: view==='settings'}" @click="view='settings'">设置</button>
      </div>
      <div class="topbar-right">
        <span v-if="pendingCount" class="badge" title="待精分的媒体">待精分 {{ pendingCount }}</span>
      </div>
    </div>

    <div v-if="view==='board'" class="board">
      <aside class="filters panel">
        <h2>过滤</h2>
        <div class="field">
          <label>年份</label>
          <select v-model="filters.year">
            <option value="">全部</option>
            <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
          </select>
        </div>
        <div class="field">
          <label>城市</label>
          <select v-model="filters.cityId">
            <option value="">全部</option>
            <option v-for="c in cities" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
          </select>
        </div>
        <div class="field">
          <label>类型</label>
          <select v-model="filters.kind">
            <option value="">全部</option>
            <option value="scene">景点</option>
            <option value="shop">店铺</option>
            <option value="landmark">地标</option>
          </select>
        </div>
        <div class="field">
          <label>关键词</label>
          <input v-model="filters.q" placeholder="地点或评价" />
        </div>
        <div class="field">
          <label><input type="checkbox" v-model="filters.hasMedia" /> 仅带照片/视频</label>
        </div>
        <div class="field">
          <label>新城市</label>
          <input v-model="addCityName" placeholder="城市名" @keyup.enter="addCity" />
        </div>
        <button class="primary" style="width:100%" @click="addCity">添加城市</button>
      </aside>

      <section class="map-area panel">
        <div class="stats">
          <div class="stat"><div class="num">{{ dashboard.stats.cities_lit || 0 }}</div><div class="cap">点亮城市</div></div>
          <div class="stat"><div class="num">{{ dashboard.stats.places || 0 }}</div><div class="cap">地点</div></div>
          <div class="stat"><div class="num">{{ dashboard.stats.visits || 0 }}</div><div class="cap">到访</div></div>
          <div class="stat"><div class="num">{{ dashboard.stats.media || 0 }}</div><div class="cap">媒体</div></div>
        </div>
        <div v-if="labelCards.length" class="label-stats">
          <div v-for="ls in labelCards" :key="ls.label" class="stat">
            <div class="num">{{ ls.icon }} {{ ls.count }}</div>
            <div class="cap">{{ ls.label }}</div>
          </div>
        </div>
        <div id="map" class="map"></div>
      </section>

      <aside class="detail">
        <div class="panel" style="padding:12px">
          <div class="tabs">
            <button class="tab" :class="{active: tab==='timeline'}" @click="tab='timeline'">时间轴</button>
            <button class="tab" :class="{active: tab==='places'}" @click="tab='places'">地点</button>
            <button class="tab" :class="{active: tab==='photos'}" @click="tab='photos'">照片墙</button>
          </div>
        </div>

        <div v-if="tab==='places'" class="panel" style="padding:12px">
          <h2>地点 <span class="muted">({{ places.length }})</span></h2>
          <div v-if="!places.length" class="empty">暂无已点亮的地点</div>
          <div v-for="p in places" :key="p.id" class="place-row" :class="{sel: selectedPlace && p.id===selectedPlace.id}" @click="selectPlace(p)">
            <div class="place-head">
              <span class="kind-dot" :class="'kind-'+p.kind"></span>
              <strong>{{ p.name }}</strong>
              <span class="muted">{{ KIND_LABEL[p.kind] }}</span>
              <span class="muted">{{ p.city ? '' : '' }}</span>
              <button class="icon" style="margin-left:auto" title="删除地点" @click.stop="removePlace(p)" v-html="ICON_TRASH"></button>
            </div>
            <div class="muted">{{ p.visit_count }} 次到访</div>
          </div>
        </div>

        <div v-if="tab==='timeline'" class="panel" style="padding:12px">
          <h2>时间轴 <span class="muted">({{ visits.length }})</span></h2>
          <div v-if="!visits.length" class="empty">没有匹配的记录</div>
          <div v-for="v in visits" :key="v.id" class="timeline-item">
            <div class="timeline-when">{{ fmtDate(v) }}</div>
            <div style="min-width:0">
              <div><strong>{{ v.place_name_snapshot }}</strong> <span class="stars">{{ stars(v.rating) }}</span></div>
              <div v-if="v.review" class="muted">{{ v.review }}</div>
              <div class="actions" style="margin-top:6px">
                <button class="icon" title="删除" @click="removeVisit(v)" v-html="ICON_TRASH"></button>
              </div>
            </div>
          </div>
        </div>

        <div v-if="tab==='photos'" class="panel" style="padding:12px">
          <h2>照片墙</h2>
          <div v-if="!mediaList.length" class="empty">还没有媒体</div>
          <div class="media-grid">
            <template v-for="m in mediaList" :key="m.id">
              <a :href="m.file" target="_blank" rel="noreferrer">
                <img v-if="m.kind==='photo'" :src="m.thumb" loading="lazy" :alt="'媒体'+m.id" />
                <video v-else :src="m.file" muted preload="metadata"></video>
              </a>
              <button :style="{'grid-column':'1 / -1'}" class="muted" @click="removeMedia(m)">删除 #{{ m.id }}</button>
            </template>
          </div>
          <div v-if="allPendingMedia.length" class="muted" style="margin-top:8px">{{ allPendingMedia.length }} 条待精分，后续版本支持归位</div>
        </div>

        <div class="panel" style="padding:12px">
          <h2 v-if="selectedPlace">{{ selectedPlace.name }}</h2>
          <div v-else class="empty">先从地图或列表选择一个地点</div>
          <template v-if="selectedPlace">
            <div class="muted" style="margin-bottom:8px">{{ selectedPlace.city ? '' : '' }}到访 {{ selectedPlaceVisits.length }} 次</div>
            <div v-for="v in selectedPlaceVisits" :key="v.id" class="visit-row">
              <div class="place-head">
                <span class="stars">{{ stars(v.rating) }}</span>
                <span class="muted">{{ fmtDate(v) }}</span>
                <button class="icon" style="margin-left:auto" title="删除" @click="removeVisit(v)" v-html="ICON_TRASH"></button>
              </div>
              <div v-if="v.review" class="muted">{{ v.review }}</div>
              <div v-if="mediaOf(v.id).length" class="media-grid" style="margin-top:8px">
                <a v-for="m in mediaOf(v.id)" :key="m.id" :href="m.file" target="_blank" rel="noreferrer">
                  <img v-if="m.kind==='photo'" :src="m.thumb" loading="lazy" :alt="'媒体'+m.id" />
                  <video v-else :src="m.file" muted preload="metadata"></video>
                </a>
              </div>
            </div>

            <div style="margin-top:10px;border-top:1px solid var(--line);padding-top:10px">
              <div class="form-inline">
                <div class="field">
                  <label>日期时间</label>
                  <input type="datetime-local" v-model="visitForm.date" />
                </div>
                <div class="field">
                  <label>评分</label>
                  <select v-model.number="visitForm.rating">
                    <option :value="1">1</option>
                    <option :value="2">2</option>
                    <option :value="3">3</option>
                    <option :value="4">4</option>
                    <option :value="5">5</option>
                  </select>
                </div>
                <div class="field wide">
                  <label>评价</label>
                  <textarea v-model="visitForm.review"></textarea>
                </div>
                <div class="field wide">
                  <label>照片 / 视频</label>
                  <input type="file" multiple accept="image/*,video/*" @change="onPickFiles" />
                  <span v-if="pickedFiles.length" class="muted">{{ pickedFiles.length }} 个文件</span>
                </div>
              </div>
              <button class="primary" :disabled="busy" @click="addVisit">记录到访并上传</button>
            </div>
          </template>
        </div>

        <div v-if="selectedCityId != null && !selectedPlace" class="panel" style="padding:12px">
          <h2>新地点</h2>
          <div class="field">
            <label>地点名</label>
            <input v-model="addPlaceName" placeholder="如 宽窄巷子 / 李姐面馆" />
          </div>
          <div class="field">
            <label>类型</label>
            <select v-model="addPlaceKind">
              <option value="scene">景点</option>
              <option value="shop">店铺</option>
              <option value="landmark">地标</option>
            </select>
          </div>
          <button @click="addPlace">添加地点</button>
        </div>
      </aside>
    </div>

    <div v-else-if="view==='settings'" class="settings">
      <div class="panel">
        <h2>数据</h2>
        <div class="field"><label>数据根目录</label><input :value="'服务器本地（travel_data）'" disabled /></div>
        <div class="actions">
          <button class="primary" @click="exportBackup" v-html="ICON_DOWNLOAD + ' 导出备份'"></button>
          <label class="button" style="display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:8px;padding:6px 12px;cursor:pointer">
            <span v-html="ICON_UPLOAD"></span> 恢复
            <input type="file" accept=".zip" style="display:none" @change="doRestore" />
          </label>
        </div>
        <div class="muted" style="margin-top:10px">恢复为整体覆盖，媒体文件会原样还原。</div>
      </div>
      <div class="panel">
        <h2>概览</h2>
        <div class="timeline-item" v-for="t in dashboard.recent_trips" :key="t.id">
          <div class="timeline-when">{{ (t.start && t.start.local || '').slice(0,10) }} ~ {{ (t.end && t.end.local || '').slice(0,10) }}</div>
          <div><strong>{{ t.name }}</strong></div>
        </div>
      </div>
    </div>

    <div v-else class="routebooks">
      <div v-if="rbView==='list'" class="panel" style="padding:14px;width:min(640px,100%)">
        <h2>路书 <span class="muted">({{ filteredRbList.length }})</span></h2>
        <div class="field">
          <label>新路书</label>
          <input v-model="rbName" placeholder="给路书起个名" @keyup.enter="createRb" />
        </div>
        <button class="primary" :disabled="rbBusy" style="width:100%" @click="createRb">新建路书</button>
        <div class="field" style="margin-top:10px">
          <label>按模式筛选</label>
          <select v-model="rbFilter">
            <option value="">全部</option>
            <option value="driving">自驾</option>
            <option value="cycling">骑行</option>
            <option value="walking">徒步</option>
          </select>
        </div>
        <div class="field">
          <label><span v-html="ICON_UPLOAD"></span> 导入路书 zip</label>
          <input type="file" accept=".zip" @change="importRb" />
        </div>
        <div v-if="!filteredRbList.length" class="empty">暂无路书</div>
        <div v-for="b in filteredRbList" :key="b.id" class="place-row">
          <div class="place-head">
            <strong style="cursor:pointer" @click="openRb(b.id)">{{ b.name }}</strong>
            <span class="muted">{{ rbModeLabel(b.mode) }} · {{ b.preset }}</span>
            <span class="muted">{{ b.mileage_km ?? '—' }} km</span>
            <button class="icon" style="margin-left:auto" title="删除路书" @click.stop="removeRb(b)" v-html="ICON_TRASH"></button>
          </div>
        </div>
      </div>

      <div v-else class="rb-editor" style="display:flex;flex-wrap:wrap;gap:14px;padding:14px">
        <div class="panel" style="padding:14px;flex:1 1 100%">
          <div class="tabs">
            <button class="tab" @click="backToRbList">← 返回列表</button>
            <span style="margin-left:auto" class="muted">{{ rbEditor.id ? '#'+rbEditor.id : '新建' }}</span>
          </div>
          <div class="form-inline" style="margin-top:10px">
            <div class="field">
              <label>名称</label>
              <input :value="rbEditor.name" placeholder="未命名" @input="rbSet({type:'setName',name:$event.target.value})" />
            </div>
            <div class="field">
              <label>模式</label>
              <select :value="rbEditor.mode" @change="rbSet({type:'setMode',mode:$event.target.value})">
                <option value="driving">自驾</option>
                <option value="cycling">骑行</option>
                <option value="walking">徒步</option>
              </select>
            </div>
            <div class="field">
              <label>档位</label>
              <select :value="rbEditor.preset" @change="rbSet({type:'setPreset',preset:$event.target.value})">
                <option v-for="o in rbPresetOptions(rbEditor.mode)" :key="o.key" :value="o.key">{{ o.label }}</option>
              </select>
            </div>
            <div class="field">
              <label>里程 km（手动）</label>
              <input type="number" :value="rbEditor.mileageKm ?? ''" @change="setRbManualMileage($event)" />
            </div>
          </div>
          <div class="actions" style="margin-top:10px">
            <button class="primary" :disabled="rbBusy" @click="saveRb">保存</button>
            <button :disabled="rbBusy" @click="recalcRb">引擎重算</button>
            <button v-html="ICON_DOWNLOAD+' GPX'" @click="exportRbGpx"></button>
            <button v-html="ICON_DOWNLOAD+' 路书 zip'" @click="exportRbZip"></button>
            <button @click="loadRbNav">导航交接</button>
          </div>
          <div class="muted" style="margin-top:8px;font-size:12px">
            {{ rbEditor.drawMode ? '手绘中：点击地图加顶点' : '点击地图添加途经点；拖动标记可微调' }}
            <template v-if="rbEditor.source==='override'"> · 当前为手绘覆盖线（重算不会覆盖）</template>
            <template v-else> · 当前为引擎线</template>
          </div>
        </div>

        <div class="panel" style="padding:0;flex:1 1 58%;min-width:320px">
          <div id="rb-map" class="map" style="height:440px;border-radius:8px;overflow:hidden"></div>
        </div>

        <div class="panel" style="padding:14px;flex:1 1 34%;min-width:260px">
          <h2>途经点 <span class="muted">({{ rbEditor.points.length }})</span></h2>
          <div class="actions" style="margin-bottom:8px">
            <button @click="rbSet({type:'setDrawMode',on:!rbEditor.drawMode})">手绘覆盖线</button>
            <button v-if="rbEditor.overrideGeo" @click="applyOverrideRb">应用覆盖线</button>
            <button v-if="rbEditor.overrideGeo" @click="clearOverrideRb">清除覆盖线</button>
          </div>
          <div v-if="!rbEditor.points.length" class="empty">尚无途经点，点击地图添加</div>
          <div v-for="(p,i) in rbEditor.points" :key="p.id" class="place-row">
            <div class="place-head">
              <span class="muted">{{ i===0?'起点':(i===rbEditor.points.length-1?'终点':'途经') }}</span>
              <input :value="p.name" placeholder="名称" style="width:110px" @input="rbRenamePoint(p,$event)" />
              <select :value="p.stopType || ''" style="width:88px" @change="rbSetStopType(p,$event)">
                <option value="">无停靠</option>
                <option value="charging">充电</option>
                <option value="fuel">加油</option>
                <option value="scene">景点</option>
                <option value="lodging">食宿</option>
              </select>
              <span v-if="p.hasCoords" class="muted" style="font-size:11px">{{ p.lat.toFixed(4) }},{{ p.lng.toFixed(4) }}</span>
              <span v-else class="muted" style="font-size:11px;color:var(--warn)">无坐标</span>
              <button class="icon" title="删除途经点" @click="removeRbPoint(p)" v-html="ICON_TRASH"></button>
            </div>
          </div>
        </div>

        <div v-if="rbEditor.nav" class="panel" style="padding:14px;flex:1 1 100%">
          <h2>导航交接</h2>
          <div class="actions">
            <a v-if="rbEditor.nav.tencent" class="button" :href="rbEditor.nav.tencent" @click.prevent="openRbNav(rbEditor.nav.tencent)">腾讯地图</a>
            <a v-if="rbEditor.nav.amap" class="button" :href="rbEditor.nav.amap" @click.prevent="openRbNav(rbEditor.nav.amap)">高德地图</a>
            <span class="muted" style="font-size:12px">在线动作，默认关，逐次确认后才会打开外部导航</span>
          </div>
          <textarea readonly style="width:100%;height:110px">{{ rbEditor.nav.text }}</textarea>
        </div>
      </div>
    </div>

    <div v-if="toastMsg" class="toast">{{ toastMsg }}</div>
  `,
}).mount("#app");
