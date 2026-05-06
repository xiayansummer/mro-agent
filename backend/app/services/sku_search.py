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


_STANDARD_PREFIXES = _re.compile(
    r'^(DIN|ISO|GB|JIS|ASTM|ANSI|BS|NF|UNI|UNE|SS|EN|AS|CSA|SAE|ASME)\d',
    _re.IGNORECASE,
)


def _looks_like_model_number(s: str) -> bool:
    """Heuristic: mixed letters+digits, ≥5 chars → likely a machine/equipment model number.
    Explicitly excludes international standard numbers (DIN931, ISO4762, GB5782, etc.)
    which should be searched in specification/attribute_details, not mfg_sku only.
    """
    if _STANDARD_PREFIXES.match(s):
        return False
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

    # Brand filter — expand to all DB-side spellings clustered with this brand.
    # Discovery is cached per canonical (TTL ~1h) so subsequent searches don't re-scan.
    brand = parsed_intent.get("brand")
    brand_clause = ""
    if brand:
        from app.services.normalization import discover_brand_variants
        variants = await discover_brand_variants(session, brand)
        if variants:
            likes = []
            for i, v in enumerate(variants):
                key = f"brand_v{i}"
                likes.append(f"brand_name LIKE :{key}")
                params[key] = f"%{v}%"
            brand_clause = "(" + " OR ".join(likes) + ")"

    # When model numbers are present, run a dedicated compatibility search first.
    # This guarantees model-matched products appear at the top of results,
    # regardless of how many other products match the standard keyword filters.
    compat_results = []
    seen_codes: set[str] = set()

    if model_clauses:
        compat_parts = list(cat_conditions)  # respect category filters
        compat_parts.append(f"({' OR '.join(model_clauses)})")
        compat_query = f"""
            SELECT item_code, item_name, brand_name, specification, mfg_sku,
                   l1_category_name, l2_category_name, l3_category_name, l4_category_name,
                   attribute_details
            FROM t_item_sample
            WHERE {' AND '.join(compat_parts)}
            LIMIT :limit
        """
        compat_params = {k: v for k, v in params.items()}
        compat_params["limit"] = limit
        compat_result = await session.execute(text(compat_query), compat_params)
        for row in compat_result.fetchall():
            compat_results.append({
                "item_code": row[0], "item_name": row[1], "brand_name": row[2],
                "specification": row[3], "mfg_sku": row[4],
                "l1_category_name": row[5], "l2_category_name": row[6],
                "l3_category_name": row[7], "l4_category_name": row[8],
                "attribute_details": row[9],
            })
            seen_codes.add(row[0])

    # Standard search (keyword + regular specs + categories)
    standard_parts = []
    if kw_clause:
        standard_parts.append(kw_clause)
    standard_parts.extend(regular_spec_clauses)
    if brand_clause:
        standard_parts.append(brand_clause)

    all_conditions = cat_conditions[:]
    if standard_parts:
        all_conditions.append(" AND ".join(standard_parts))

    if not all_conditions and not compat_results:
        return []

    standard_results = []
    remaining = limit - len(compat_results)
    if all_conditions and remaining > 0:
        where_clause = " AND ".join(all_conditions)
        params["limit"] = remaining
        query = f"""
            SELECT item_code, item_name, brand_name, specification, mfg_sku,
                   l1_category_name, l2_category_name, l3_category_name, l4_category_name,
                   attribute_details
            FROM t_item_sample
            WHERE {where_clause}
            LIMIT :limit
        """
        result = await session.execute(text(query), params)
        for row in result.fetchall():
            if row[0] not in seen_codes:
                standard_results.append({
                    "item_code": row[0], "item_name": row[1], "brand_name": row[2],
                    "specification": row[3], "mfg_sku": row[4],
                    "l1_category_name": row[5], "l2_category_name": row[6],
                    "l3_category_name": row[7], "l4_category_name": row[8],
                    "attribute_details": row[9],
                })

    # Compat results first (model-matched), then standard results
    return compat_results + standard_results


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


async def search_brand_clusters(
    session: AsyncSession,
    brand: str,
    limit: int = 10,
) -> list[tuple[str, int]]:
    """Brand-only fallback: return [(l3_category_name, sku_count), ...] for the brand.

    Performs DB-side GROUP BY to avoid LIMIT-truncation skew. The first
    sample of N rows could all belong to one L3, masking the brand's
    other categories — that's why we aggregate in SQL, not memory.
    """
    if not brand:
        return []
    from app.services.normalization import discover_brand_variants
    variants = await discover_brand_variants(session, brand)
    if not variants:
        return []
    placeholders = ",".join(f":b{i}" for i in range(len(variants)))
    params: dict = {f"b{i}": v for i, v in enumerate(variants)}
    params["lim"] = limit
    result = await session.execute(
        text(
            f"""
            SELECT l3_category_name, COUNT(*) AS cnt
            FROM t_item_sample
            WHERE brand_name IN ({placeholders})
              AND l3_category_name IS NOT NULL
            GROUP BY l3_category_name
            ORDER BY cnt DESC
            LIMIT :lim
            """
        ),
        params,
    )
    return [(row[0], int(row[1])) for row in result.fetchall()]
