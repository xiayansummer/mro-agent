import re
from typing import Any

from app.models.comparison import ComparisonStructure
from app.services.normalization import text_matches_brand

# 用户历史偏好(DPO)在排序里的硬加权:命中偏好品牌/品类时显著提分。
# 数值可调——调大让历史偏好对最终排序的影响更强。品牌权重高于品牌匹配(18),
# 这样当前未指定品牌时,历史偏好品牌能把对应 offer 顶上来。
_PREF_BRAND_BONUS = 25.0
_PREF_CATEGORY_BONUS = 10.0

# 相对过滤:展示阈值 = max(绝对地板, 最高分 × 比例)。高分场景(有强匹配)抬高阈值、滤掉
# 远不如它的离谱结果;低分场景(整体弱匹配)落到地板、不误杀,保住召回。两值都可调。
_MIN_DISPLAY_SCORE = 10.0      # 绝对地板:连这都不到的是纯噪声
_DISPLAY_SCORE_RATIO = 0.35    # 相对:低于"最高分 × 此比例"的视为不相关


def rank_external_offers(
    structure: ComparisonStructure | dict | None,
    offers: list[dict],
    preferences: dict | None = None,
) -> list[dict]:
    if not offers:
        return []

    normalized_structure = _structure_dict(structure)
    scored = [_score_offer(normalized_structure, offer, index, preferences) for index, offer in enumerate(offers)]
    ranked = sorted(
        scored,
        key=lambda offer: (
            -float(offer.get("matchScore") or 0),
            _price_sort_value(offer),
            int(offer.get("rawRank") or 9999),
        ),
    )

    # 用户指定了品牌时:只保留命中该品牌(含字典别名)的 offer,剔除杂牌。
    # 通用于所有品牌。若一个都没命中(平台未收录该品牌),兜底保留全部,
    # 避免给用户空列表。
    brand = _clean(normalized_structure.get("specification", {}).get("brand"))
    if brand:
        on_brand = [offer for offer in ranked if text_matches_brand(_offer_text(offer), brand)]
        if on_brand:
            ranked = on_brand

    # 相对过滤(见上方常量):有强匹配时抬高阈值滤离谱,整体弱匹配时落到地板保召回。
    if not ranked:
        return []
    top_score = ranked[0].get("matchScore") or 0  # ranked 已按 matchScore 降序
    threshold = max(_MIN_DISPLAY_SCORE, top_score * _DISPLAY_SCORE_RATIO)
    return [offer for offer in ranked if (offer.get("matchScore") or 0) >= threshold]


def _score_offer(structure: dict, offer: dict, index: int, preferences: dict | None = None) -> dict:
    haystack = _offer_text(offer)
    score = 0.0
    reasons = []

    product_type = _clean(structure.get("specification", {}).get("productType"))
    if product_type:
        # 程度化匹配:productType 多词时按命中词比例给分(全含 30、半含 15…),替代全词
        # 二元——电商标题不规范,要求所有词精确命中过严,会误杀相关结果(召回兜底)。
        pt_tokens = _tokens(product_type)
        if pt_tokens:
            hits = sum(1 for token in pt_tokens if _compact(token) in _compact(haystack))
            if hits == len(pt_tokens):
                score += 30
                reasons.append(f"产品类型匹配：{product_type}")
            elif hits:
                score += round(30 * hits / len(pt_tokens), 2)
                reasons.append(f"产品类型部分匹配：{product_type}")

    brand = _clean(structure.get("specification", {}).get("brand"))
    if brand and text_matches_brand(haystack, brand):
        score += 18
        reasons.append(f"品牌匹配：{brand}")

    model = _clean(structure.get("specification", {}).get("model"))
    if model and _compact(model) in _compact(haystack):
        score += 18
        reasons.append(f"型号匹配：{model}")

    material = _clean(structure.get("specification", {}).get("material"))
    if material and _compact(material) in _compact(haystack):
        score += 12
        reasons.append(f"材质匹配：{material}")

    size = _clean(structure.get("specification", {}).get("size"))
    if size and _size_matches(haystack, size):
        score += 16
        reasons.append(f"规格匹配：{size}")

    standard = _clean(structure.get("specification", {}).get("standard"))
    if standard and _compact(standard) in _compact(haystack):
        score += 8
        reasons.append(f"标准匹配：{standard}")

    for attribute in structure.get("specification", {}).get("attributes", []) or []:
        value = _clean(attribute.get("value"))
        if value and _attribute_matches(haystack, value):
            score += 6
            name = attribute.get("name") or "参数"
            reasons.append(f"{name}匹配：{value}")

    category_bonus = _category_match_bonus(structure, haystack)
    if category_bonus:
        score += category_bonus
        reasons.append("类目词匹配")

    if _stock_required(structure) and _looks_out_of_stock(offer):
        score -= 20
        reasons.append("库存不满足约束")

    # 用户历史偏好硬加权(DPO):命中偏好品牌/品类时显著提分。
    # 各取首个命中即可,避免同一 offer 因多个偏好项重复累加。
    if preferences:
        for pref_brand in preferences.get("brands") or []:
            if pref_brand and text_matches_brand(haystack, pref_brand):
                score += _PREF_BRAND_BONUS
                reasons.append(f"符合您的偏好品牌：{pref_brand}")
                break
        for pref_cat in preferences.get("categories") or []:
            if pref_cat and _clean(pref_cat).lower() in haystack:
                score += _PREF_CATEGORY_BONUS
                reasons.append(f"符合您的常用品类：{pref_cat}")
                break

    if offer.get("priceValue") is not None:
        score += 2
        reasons.append("含价格")

    ranked = dict(offer)
    ranked["matchScore"] = round(max(0.0, min(100.0, score)), 2)
    ranked["matchReasons"] = _dedupe(reasons) or ["按搜索结果相关性保留"]
    return ranked


def _structure_dict(structure: ComparisonStructure | dict | None) -> dict:
    if structure is None:
        return {}
    if isinstance(structure, ComparisonStructure):
        return structure.model_dump(mode="json")
    return structure


def _offer_text(offer: dict) -> str:
    values = [
        offer.get("title"),
        offer.get("brand"),
        offer.get("specText"),
        offer.get("unitText"),
        offer.get("stockText"),
        offer.get("deliveryText"),
        offer.get("platformSku"),
    ]
    return " ".join(_clean(value) for value in values if value).lower()


def _category_match_bonus(structure: dict, haystack: str) -> float:
    category = structure.get("category", {})
    score = 0.0
    for key in ("l4", "l3", "l2"):
        value = _clean(category.get(key))
        if value and _contains_all_tokens(haystack, value):
            score += 4
            break
    return score


def _contains_all_tokens(haystack: str, needle: str) -> bool:
    tokens = _tokens(needle)
    if not tokens:
        return False
    compact_haystack = _compact(haystack)
    return all(_compact(token) in compact_haystack for token in tokens)


def _attribute_matches(haystack: str, value: str) -> bool:
    return _size_matches(haystack, value) or _compact(value) in _compact(haystack)


def _size_matches(haystack: str, size: str) -> bool:
    compact_haystack = _compact(haystack).lower()
    compact_size = _compact(size).lower()
    if compact_size in compact_haystack:
        return True
    normalized_size = compact_size.replace("×", "x").replace("*", "x")
    normalized_haystack = compact_haystack.replace("×", "x").replace("*", "x")
    if normalized_size in normalized_haystack:
        return True
    match = re.match(r"m(\d+)(?:x(\d+(?:\.\d+)?))?", normalized_size, re.I)
    if not match:
        return False
    diameter = match.group(1)
    length = match.group(2)
    if f"m{diameter}" not in normalized_haystack:
        return False
    return not length or re.search(rf"(?:x|\*){re.escape(length)}(?:mm)?\b", normalized_haystack)


def _price_sort_value(offer: dict) -> float:
    if offer.get("unitComparable") and offer.get("normalizedUnitPrice") is not None:
        return float(offer["normalizedUnitPrice"])
    if offer.get("priceValue") is not None:
        return float(offer["priceValue"]) * 1.2
    return 10**12


def _stock_required(structure: dict) -> bool:
    return structure.get("purchaseConstraints", {}).get("requireInStock") is True


def _looks_out_of_stock(offer: dict) -> bool:
    stock_text = _clean(offer.get("stockText"))
    return bool(re.search(r"无货|缺货|售罄|下架", stock_text))


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[\s,，/|｜]+", _clean(value)) if token]


def _compact(value: str) -> str:
    # 统一小写:_offer_text(haystack)已转小写,这里也必须小写,否则含大写字母的英文
    # 参数(型号 HSZ-622A、标准 DIN933 等)子串匹配会失效。
    return re.sub(r"\s+", "", _clean(value)).lower()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
