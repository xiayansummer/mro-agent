"""
偏好排序器：从 memory_context 字符串解析用户偏好信号，对 SKU 结果列表重排序。
纯函数，无外部依赖。
"""


def rank_by_preference(results: list[dict], memory_context: str) -> list[dict]:
    if not memory_context or not results:
        return results

    prefs = _parse_preferences(memory_context)

    def preference_score(item: dict) -> int:
        score = 0
        brand = (item.get("brand_name") or "").strip()
        l2 = (item.get("l2_category_name") or "").strip()
        if brand and brand in prefs["liked_brands"]:
            score += 2 * prefs["liked_brands"][brand]
        if l2 and l2 in prefs["liked_categories"]:
            score += prefs["liked_categories"][l2]
        return score

    indexed = list(enumerate(results))
    indexed.sort(key=lambda x: (-preference_score(x[1]), x[0]))
    return [item for _, item in indexed]


def _parse_preferences(memory_context: str) -> dict:
    liked_brands: dict[str, int] = {}
    liked_categories: dict[str, int] = {}

    for line in memory_context.splitlines():
        line = line.strip()
        if line.startswith("偏好品牌："):
            for brand in line[len("偏好品牌："):].split(","):
                b = brand.strip()
                if b and b not in liked_brands:
                    liked_brands[b] = 1
        elif line.startswith("常用品类："):
            for cat in line[len("常用品类："):].split(","):
                c = cat.strip()
                if c and c not in liked_categories:
                    liked_categories[c] = 1

    return {"liked_brands": liked_brands, "liked_categories": liked_categories}
