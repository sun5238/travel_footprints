"""S7: 导航交接纯函数（腾讯 routeplan 多模式深链 / 高德前后端深链 / 文本兜底）。

深链是「在线动作、默认关、逐次确认」——本纯函数只负责构造 URL，是否触网由调用方定。
"""

from __future__ import annotations

from travel.nav import nav_links

S = {"name": "重庆", "lat": 29.56, "lng": 106.55, "pos_kind": "exact"}
VIA = {"name": "仁寿", "lat": 29.99, "lng": 104.13, "pos_kind": "exact"}
E = {"name": "成都", "lat": 30.65, "lng": 104.06, "pos_kind": "exact"}
ANNOT = {"name": "某停车点", "lat": None, "lng": None, "pos_kind": "none"}


def test_tencent_driving_url_with_vias():
    links = nav_links("自驾路书", "driving", [S, VIA, E])
    url = links["tencent"]
    assert url is not None and "uri/v1/routeplan" in url
    assert "mode=driving" in url
    assert f"to={E['lat']:.6f},{E['lng']:.6f}" in url
    assert f"from={S['lat']:.6f},{S['lng']:.6f}" in url
    assert f"via={VIA['lat']:.6f},{VIA['lng']:.6f}" in url
    assert "referer=" in url


def test_tencent_cycling_uses_riding():
    links = nav_links("骑行", "cycling", [S, E])
    assert links["tencent"] is not None
    assert "mode=riding" in links["tencent"]


def test_amap_driving_url():
    links = nav_links("自驾", "driving", [S, E])
    url = links["amap"]
    assert url is not None and "uri.amap.com/navigation" in url
    assert "mode=driving" in url
    assert f"to={E['lat']:.6f},{E['lng']:.6f}" in url


def test_amap_cycling_falls_back_to_text():
    links = nav_links("骑行", "cycling", [S, VIA, E])
    assert links["amap"] is None
    assert links["text"]


def test_text_fallback_lists_all_points_in_order():
    links = nav_links("x", "walking", [S, ANNOT, E])
    text = links["text"]
    assert "重庆" in text and "某停车点" in text and "成都" in text
    assert text.index("重庆") < text.index("某停车点") < text.index("成都")


def test_walking_supported_on_both():
    links = nav_links("徒步", "walking", [S, E])
    assert links["tencent"] and "mode=walking" in links["tencent"]
    assert links["amap"] and "mode=walking" in links["amap"]