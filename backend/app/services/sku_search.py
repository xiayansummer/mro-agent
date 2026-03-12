from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FILE_TYPE_MAP = {
    "301": "技术资料",
    "302": "认证证书",
    "303": "检测报告",
    "305": "相关文档",
}


async def attach_files(session: AsyncSession, sku_results: list[dict]) -> list[dict]:
    """Batch-query t_item_file_sample and attach file info to each SKU result."""
    codes = [s["item_code"] for s in sku_results]
    if not codes:
        return sku_results

    placeholders = ",".join([f":c{i}" for i in range(len(codes))])
    query = f"""
        SELECT item_code, origin_file_name, file_path, file_type
        FROM t_item_file_sample
        WHERE item_code COLLATE utf8mb4_general_ci IN ({placeholders})
          AND is_published = 1
    """
    params = {f"c{i}": c for i, c in enumerate(codes)}

    result = await session.execute(text(query), params)
    rows = result.fetchall()

    # Group files by item_code
    files_by_code: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        item_code, file_name, file_url, file_type = row[0], row[1], row[2], str(row[3])
        files_by_code[item_code].append({
            "file_name": file_name,
            "file_url": file_url,
            "file_type_label": FILE_TYPE_MAP.get(file_type, "其他文档"),
        })

    for sku in sku_results:
        sku["files"] = files_by_code.get(sku["item_code"], [])

    return sku_results


async def search_skus(session: AsyncSession, parsed_intent: dict, limit: int = 20) -> list[dict]:
    conditions = []
    params = {}

    # Category filters
    for i, key in enumerate(["l1_category", "l2_category", "l3_category", "l4_category"]):
        col = f"{key}_name"
        value = parsed_intent.get(key)
        if value:
            conditions.append(f"{col} LIKE :cat_{i}")
            params[f"cat_{i}"] = f"%{value}%"

    # Keyword matching on item_name (product type keywords)
    keywords = parsed_intent.get("keywords", [])
    for i, kw in enumerate(keywords):
        conditions.append(f"item_name LIKE :kw_{i}")
        params[f"kw_{i}"] = f"%{kw}%"

    # Spec keywords match across item_name, specification, and attribute_details
    spec_keywords = parsed_intent.get("spec_keywords", [])
    for i, sk in enumerate(spec_keywords):
        conditions.append(
            f"(item_name LIKE :sk_{i} OR specification LIKE :sk_{i} OR attribute_details LIKE :sk_{i})"
        )
        params[f"sk_{i}"] = f"%{sk}%"

    # Brand filter
    brand = parsed_intent.get("brand")
    if brand:
        conditions.append("brand_name LIKE :brand")
        params["brand"] = f"%{brand}%"

    if not conditions:
        return []

    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT item_code, item_name, brand_name, specification,
               l1_category_name, l2_category_name, l3_category_name, l4_category_name,
               attribute_details
        FROM t_item_sample
        WHERE {where_clause}
        LIMIT :limit
    """
    params["limit"] = limit

    result = await session.execute(text(query), params)
    rows = result.fetchall()

    return [
        {
            "item_code": row[0],
            "item_name": row[1],
            "brand_name": row[2],
            "specification": row[3],
            "l1_category_name": row[4],
            "l2_category_name": row[5],
            "l3_category_name": row[6],
            "l4_category_name": row[7],
            "attribute_details": row[8],
        }
        for row in rows
    ]


async def relaxed_search(session: AsyncSession, parsed_intent: dict, limit: int = 20) -> list[dict]:
    """Fallback search with progressively relaxed conditions."""

    # Step 1: Drop spec_keywords (keep product type + categories)
    relaxed = {**parsed_intent, "spec_keywords": []}
    results = await search_skus(session, relaxed, limit)
    if results:
        return results

    # Step 2: Drop l4 category
    relaxed = {**relaxed, "l4_category": None}
    results = await search_skus(session, relaxed, limit)
    if results:
        return results

    # Step 3: Drop l3+l4
    relaxed = {**relaxed, "l3_category": None}
    results = await search_skus(session, relaxed, limit)
    if results:
        return results

    # Step 4: Just keywords on item_name (no categories, no specs)
    keywords = parsed_intent.get("keywords", [])
    if keywords:
        relaxed = {"keywords": keywords, "brand": parsed_intent.get("brand")}
        results = await search_skus(session, relaxed, limit)
        if results:
            return results

    # Step 5: Try individual keywords
    for kw in keywords:
        relaxed = {"keywords": [kw]}
        results = await search_skus(session, relaxed, limit)
        if results:
            return results

    return []
