"""
标准等效映射表 + 属性行业知识库

find_equivalents(keywords) → 返回等效标准号列表（用于替代搜索）
ATTRIBUTE_KNOWLEDGE → 各属性维度的行业建议选项（用于属性追问）
"""

STANDARD_EQUIVALENTS: dict[str, list[str]] = {
    "DIN934":  ["ISO 4032", "GB/T 6170"],
    "DIN933":  ["ISO 4017", "GB/T 5783"],
    "DIN931":  ["ISO 4014", "GB/T 5782"],
    "DIN912":  ["ISO 4762", "GB/T 70.1"],
    "DIN125":  ["ISO 7089", "GB/T 97.1"],
    "DIN127":  ["ISO 7090", "GB/T 93"],
    "DIN985":  ["ISO 7042", "GB/T 6184"],
    "DIN982":  ["ISO 7042"],
    "DIN7991": ["ISO 10642"],
    "DIN7380": ["ISO 7380"],
    "DIN471":  ["ISO 5254-1"],
    "DIN472":  ["ISO 5254-2"],
    "ISO4032": ["DIN 934",  "GB/T 6170"],
    "ISO4017": ["DIN 933",  "GB/T 5783"],
    "ISO4014": ["DIN 931",  "GB/T 5782"],
    "ISO4762": ["DIN 912",  "GB/T 70.1"],
    "ISO7089": ["DIN 125",  "GB/T 97.1"],
    "ISO7090": ["DIN 127",  "GB/T 93"],
    "GBT6170": ["DIN 934",  "ISO 4032"],
    "GBT5783": ["DIN 933",  "ISO 4017"],
    "GBT5782": ["DIN 931",  "ISO 4014"],
}

_NORM_TO_EQUIVALENTS: dict[str, list[str]] = {}


def _normalize(s: str) -> str:
    return s.upper().replace(" ", "").replace("/", "").replace("-", "").replace(".", "")


def _build_index() -> None:
    for key, vals in STANDARD_EQUIVALENTS.items():
        _NORM_TO_EQUIVALENTS[_normalize(key)] = vals


_build_index()


def find_equivalents(keywords: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        norm = _normalize(kw)
        for equiv in _NORM_TO_EQUIVALENTS.get(norm, []):
            if equiv not in seen:
                seen.add(equiv)
                result.append(equiv)
    return result


ATTRIBUTE_KNOWLEDGE: dict[str, list[dict]] = {
    "材质等级": [
        {"value": "A2-70（304不锈钢）", "note": "最常用，适合室内/一般环境", "is_common": True},
        {"value": "A4-80（316不锈钢）", "note": "耐海水/化工腐蚀，溢价约30%", "is_common": False},
        {"value": "碳钢镀锌", "note": "强度高，成本低，需防锈", "is_common": False},
    ],
    "强度等级": [
        {"value": "8.8级", "note": "工业最常用，高强度螺栓标配", "is_common": True},
        {"value": "4.8级", "note": "普通强度，成本低", "is_common": False},
        {"value": "10.9级", "note": "超高强度，特殊受力场合", "is_common": False},
    ],
    "规格（螺纹直径）": [
        {"value": "M6",  "note": "",                 "is_common": False},
        {"value": "M8",  "note": "工业最常用规格",    "is_common": True},
        {"value": "M10", "note": "",                 "is_common": False},
        {"value": "M12", "note": "",                 "is_common": False},
        {"value": "M16", "note": "",                 "is_common": False},
    ],
    "表面处理": [
        {"value": "镀锌白",  "note": "通用防锈，成本低",  "is_common": True},
        {"value": "发黑",    "note": "外观好，防锈性弱",  "is_common": False},
        {"value": "达克罗",  "note": "耐腐蚀强，无氢脆", "is_common": False},
    ],
    "密封材质": [
        {"value": "丁腈橡胶（NBR）",   "note": "最通用，耐油，−30~120°C",   "is_common": True},
        {"value": "氟橡胶（FKM）",    "note": "耐高温耐化学品，−20~200°C", "is_common": False},
        {"value": "硅橡胶（VMQ）",    "note": "耐高低温，可选食品级",        "is_common": False},
        {"value": "三元乙丙（EPDM）", "note": "耐水/蒸汽，不耐油",          "is_common": False},
    ],
}
