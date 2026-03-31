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


import re as _re


def _looks_like_model_number(s: str) -> bool:
    """Heuristic: mixed letters+digits, ≥5 chars → likely a machine/equipment model number."""
    return bool(
        _re.match(r'^[A-Za-z0-9\-_.]{5,}$', s)
        and _re.search(r'[A-Za-z]', s)
        and _re.search(r'[0-9]', s)
    )


async def search_skus(session: AsyncSession, parsed_intent: dict, limit: int = 20) -> list[dict]:
    params = {}

    # Category filters (always AND-ed)
    cat_conditions = []
    for i, key in enumerate(["l1_category", "l2_category", "l3_category", "l4_category"]):
        col = f"{key}_name"
        value = parsed_intent.get(key)
        if value:
            cat_conditions.append(f"{col} LIKE :cat_{i}")
            params[f"cat_{i}"] = f"%{value}%"

    # Keyword matching on item_name — ANY keyword must match (OR), not all (AND).
    keywords = parsed_intent.get("keywords", [])
    kw_clause = ""
    if keywords:
        kw_clauses = [f"item_name LIKE :kw_{i}" for i in range(len(keywords))]
        kw_clause = f"({' OR '.join(kw_clauses)})"
        for i, kw in enumerate(keywords):
            params[f"kw_{i}"] = f"%{kw}%"

    # Spec keywords: split into model numbers (mfg_sku only) vs regular specs (all fields).
    # Model numbers (e.g. MFB381125) match mfg_sku ALONE — they don't require item_name match.
    # Regular specs (e.g. M8, DIN931, 304) are AND-ed with keyword filter as before.
    spec_keywords = parsed_intent.get("spec_keywords", [])
    model_numbers = [sk for sk in spec_keywords if _looks_like_model_number(sk)]
    regular_specs = [sk for sk in spec_keywords if not _looks_like_model_number(sk)]

    regular_spec_clauses = []
    for i, sk in enumerate(regular_specs):
        regular_spec_clauses.append(
            f"(item_name LIKE :sk_{i} OR specification LIKE :sk_{i}"
            f" OR mfg_sku LIKE :sk_{i} OR attribute_details LIKE :sk_{i})"
        )
        params[f"sk_{i}"] = f"%{sk}%"

    model_clauses = []
    for i, mn in enumerate(model_numbers):
        model_clauses.append(f"mfg_sku LIKE :mn_{i}")
        params[f"mn_{i}"] = f"%{mn}%"

    # Brand filter
    brand = parsed_intent.get("brand")
    brand_clause = ""
    if brand:
        brand_clause = "brand_name LIKE :brand"
        params["brand"] = f"%{brand}%"

    # Build WHERE clause:
    # Standard path: cat_filters AND kw_filter AND regular_spec_filters AND brand_filter
    # Compatibility path: cat_filters AND mfg_sku_model_filter (no kw_filter required)
    # Result: cat_filters AND (standard_path OR compat_path)

    standard_parts = []
    if kw_clause:
        standard_parts.append(kw_clause)
    standard_parts.extend(regular_spec_clauses)
    if brand_clause:
        standard_parts.append(brand_clause)

    if model_clauses:
        # Compatibility search: mfg_sku match alone is sufficient (bypasses keyword filter)
        compat_condition = f"({' OR '.join(model_clauses)})"
        if standard_parts:
            standard_condition = " AND ".join(standard_parts)
            main_condition = f"(({standard_condition}) OR {compat_condition})"
        else:
            main_condition = compat_condition
    else:
        if standard_parts:
            main_condition = " AND ".join(standard_parts)
        else:
            main_condition = ""

    all_conditions = cat_conditions[:]
    if main_condition:
        all_conditions.append(main_condition)

    if not all_conditions:
        return []

    where_clause = " AND ".join(all_conditions)
    query = f"""
        SELECT item_code, item_name, brand_name, specification, mfg_sku,
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
            "mfg_sku": row[4],
            "l1_category_name": row[5],
            "l2_category_name": row[6],
            "l3_category_name": row[7],
            "l4_category_name": row[8],
            "attribute_details": row[9],
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


async def find_alternatives(session: AsyncSession, parsed_intent: dict, limit: int = 10) -> list[dict]:
    """
    Find similar products when exact match fails.
    Ignores spec_keywords and brand — searches only by product type + category.
    """
    keywords = parsed_intent.get("keywords", [])
    l3 = parsed_intent.get("l3_category")
    l2 = parsed_intent.get("l2_category")

    for attempt in [
        {"l3_category": l3, "keywords": keywords[:1]} if l3 else None,
        {"l2_category": l2, "keywords": keywords[:1]} if l2 else None,
        {"keywords": keywords[:1]} if keywords else None,
    ]:
        if not attempt:
            continue
        results = await search_skus(session, attempt, limit)
        if results:
            return results

    return []
