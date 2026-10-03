"""S5: GPX 1.1 `<rte>` 导出纯函数（含无坐标点跳过与 XML 转义）。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from travel.gpx import routebook_to_gpx

PTS = [
    {"name": "成都", "lat": 30.65, "lng": 104.06, "pos_kind": "exact"},
    {"name": "都 江&堰<桥>", "lat": 30.99, "lng": 103.62, "pos_kind": "exact"},
    {"name": "无坐标", "lat": None, "lng": None, "pos_kind": "none"},
    {"name": "四姑娘山", "lat": 31.2, "lng": 102.9, "pos_kind": "city"},
]


def test_gpx_root_and_namespace():
    xml_text = routebook_to_gpx("成都骑行", PTS)
    root = ET.fromstring(xml_text)
    assert root.tag == "{http://www.topografix.com/GPX/1/1}gpx"
    assert root.attrib["version"] == "1.1"


def test_single_rte_with_name():
    root = ET.fromstring(routebook_to_gpx("成都骑行", PTS))
    rtes = root.findall("{http://www.topografix.com/GPX/1/1}rte")
    assert len(rtes) == 1
    name = rtes[0].find("{http://www.topografix.com/GPX/1/1}name")
    assert name is not None and name.text == "成都骑行"


def test_rtept_ignores_coords_less_points():
    root = ET.fromstring(routebook_to_gpx("成都骑行", PTS))
    rtes = root.findall("{http://www.topografix.com/GPX/1/1}rte")
    rtepts = rtes[0].findall("{http://www.topografix.com/GPX/1/1}rtept")
    # 有坐标 3 个，无坐标点被跳过
    assert len(rtepts) == 3


def test_rtept_coords_and_name():
    root = ET.fromstring(routebook_to_gpx("成都骑行", PTS))
    rtept = root.findall("{http://www.topografix.com/GPX/1/1}rte/rte")
    rtepts = root.iter("{http://www.topografix.com/GPX/1/1}rtept")
    first = next(rtepts)
    assert abs(float(first.attrib["lat"]) - 30.65) < 1e-6
    assert abs(float(first.attrib["lon"]) - 104.06) < 1e-6
    name = first.find("{http://www.topografix.com/GPX/1/1}name")
    assert name is not None and name.text == "成都"


def test_xml_escaping_of_special_chars():
    root = ET.fromstring(routebook_to_gpx("成都骑行", PTS))
    rtepts = list(root.iter("{http://www.topografix.com/GPX/1/1}rtept"))
    second_name = rtepts[1].find("{http://www.topografix.com/GPX/1/1}name")
    assert second_name is not None
    assert second_name.text == "都 江&堰<桥>"
    # 原文 XML 不含裸 & / <（已转义）
    xml_text = routebook_to_gpx("成都骑行", PTS)
    assert "&堰" not in xml_text and "<桥>" not in xml_text