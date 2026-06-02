from collections import defaultdict
import re as _re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FILE_TYPE_MAP = {
    "301": "技术资料",
    "302": "认证证书",
    "303": "检测报告",
    "305": "相关文档",
}


# ── 名称 → sid 解析(过滤用 id 列才能下推到商品分片走索引)──────────────────


async def _resolve_brand_sids(session: AsyncSession, brand: str) -> list[int]:
    """品牌名 + 字典别名 → t_brand.sid 列表。下游用 brandId IN(...) 过滤可下推。"""
    if not brand:
        return []
    from app.services.normalization import _seed_terms_for

    terms = _seed_terms_for(brand) or [brand]
    like = " OR ".join(f"brandName LIKE :t{i}" for i in range(len(terms)))
    params = {f"t{i}": f"%{t}%" for i, t in enumerate(terms)}
    rows = (await session.execute(text(f"SELECT sid FROM t_brand WHERE {like}"), params)).fetchall()
    return [r[0] for r in rows]


async def _resolve_category_sid(session: AsyncSession, name: str, level: int) -> int | None:
    """品类名 + 层级 → t_category.sid。下游用 category{n}Id = sid 过滤可下推。"""
    if not name:
        return None
    row = (await session.execute(
        text("SELECT sid FROM t_category WHERE categoryName = :n AND categoryLevel = :l LIMIT 1"),
        {"n": name, "l": level},
    )).fetchone()
    return row[0] if row else None


async def attach_files(session: AsyncSession, sku_results: list[dict]) -> list[dict]:
    """Batch-query v_item_file and attach file info to each SKU result."""
    codes = [s["item_code"] for s in sku_results]
    if not codes:
        return sku_results

    placeholders = ",".join([f":c{i}" for i in range(len(codes))])
    query = f"""
        SELECT item_code, origin_file_name, file_path, file_type
        FROM v_item_file
        WHERE item_code COLLATE utf8mb4_general_ci IN ({placeholders})
          AND is_published = 1
    """
    params = {f"c{i}": c for i, c in enumerate(codes)}
    rows = (await session.execute(text(query), params)).fetchall()

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


_STANDARD_PREFIXES = _re.compile(
    r'^(DIN|ISO|GB|JIS|ASTM|ANSI|BS|NF|UNI|UNE|SS|EN|AS|CSA|SAE|ASME)\d',
    _re.IGNORECASE,
)


def _looks_like_model_number(s: str) -> bool:
    """Heuristic: mixed letters+digits, ≥5 chars → likely a machine/equipment model.
    Excludes international standard numbers (DIN931, ISO4762, …)."""
    if _STANDARD_PREFIXES.match(s):
        return False
    return bool(
        _re.match(r'^[A-Za-z0-9\-_.]{5,}$', s)
        and _re.search(r'[A-Za-z]', s)
        and _re.search(r'[0-9]', s)
    )


# 商品分片原表字段(分片内 WHERE 过滤用这些原始列名;id 过滤可下推、中文 LIKE 正常)。
_SHARD_COLS = (
    "itemCode, itemName, brandId, specificAtion, mfgSku, "
    "category1Id, category2Id, category3Id, category4Id, itemDesc"
)


def _items_union(inner_where: str) -> str:
    """把过滤条件下推到每个商品分片的 WHERE,再 UNION ALL。

    ⚠️ 中文 LIKE 必须在分片内(原表列)做。MySQL 对 UNION ALL derived table 在
    *外层* 做中文 LIKE 会被优化器吞掉(恒返回 0,与字节/collation 无关),实测验证。
    所以这里不查 v_item_info 视图,而是分片内过滤后再 UNION。
    """
    parts = [
        f"SELECT {_SHARD_COLS} FROM t_item_info{('_%d' % i) if i else ''} "
        f"WHERE deleted = 0 AND ({inner_where})"
        for i in range(10)
    ]
    return " UNION ALL ".join(parts)


async def _query_items(session: AsyncSession, inner_where: str, params: dict, limit: int) -> list:
    """分片内过滤 → UNION → 外层 LEFT JOIN 出 brand/category 名称(展示用)。"""
    union = _items_union(inner_where)
    sql = f"""
        SELECT u.itemCode, u.itemName, b.brandName, u.specificAtion, u.mfgSku,
               c1.categoryName, c2.categoryName, c3.categoryName, c4.categoryName, u.itemDesc
        FROM ({union}) u
        LEFT JOIN t_brand b ON b.sid = u.brandId
        LEFT JOIN t_category c1 ON c1.sid = u.category1Id
        LEFT JOIN t_category c2 ON c2.sid = u.category2Id
        LEFT JOIN t_category c3 ON c3.sid = u.category3Id
        LEFT JOIN t_category c4 ON c4.sid = u.category4Id
        LIMIT :limit
    """
    return (await session.execute(text(sql), {**params, "limit": limit})).fetchall()


def _row_to_item(row) -> dict:
    return {
        "item_code": row[0], "item_name": row[1], "brand_name": row[2],
        "specification": row[3], "mfg_sku": row[4],
        "l1_category_name": row[5], "l2_category_name": row[6],
        "l3_category_name": row[7], "l4_category_name": row[8],
        "attribute_details": row[9],
    }


async def search_skus(session: AsyncSession, parsed_intent: dict, limit: int = 20) -> list[dict]:
    # 分片内 WHERE 用原表字段(itemName / brandId / category{n}Id / specificAtion / mfgSku / itemDesc)
    params: dict = {}

    # 品类:名称 → sid → category{n}Id = sid(可下推)。解析不到 sid 说明库里没这个
    # 品类,直接返回空,让上层 relaxed_search 接手。
    base_conditions = []
    for level, key in enumerate(["l1_category", "l2_category", "l3_category", "l4_category"], start=1):
        value = parsed_intent.get(key)
        if value:
            sid = await _resolve_category_sid(session, value, level)
            if sid is None:
                return []
            base_conditions.append(f"category{level}Id = :cat_{level}")
            params[f"cat_{level}"] = sid

    keywords = parsed_intent.get("keywords", [])
    kw_clause = ""
    if keywords:
        kw_clauses = [f"itemName LIKE :kw_{i}" for i in range(len(keywords))]
        kw_clause = f"({' OR '.join(kw_clauses)})"
        for i, kw in enumerate(keywords):
            params[f"kw_{i}"] = f"%{kw}%"

    spec_keywords = parsed_intent.get("spec_keywords", [])
    model_numbers = [sk for sk in spec_keywords if _looks_like_model_number(sk)]
    regular_specs = [sk for sk in spec_keywords if not _looks_like_model_number(sk)]

    regular_spec_clauses = []
    for i, sk in enumerate(regular_specs):
        regular_spec_clauses.append(
            f"(itemName LIKE :sk_{i} OR specificAtion LIKE :sk_{i}"
            f" OR mfgSku LIKE :sk_{i} OR itemDesc LIKE :sk_{i})"
        )
        params[f"sk_{i}"] = f"%{sk}%"

    model_clauses = []
    for i, mn in enumerate(model_numbers):
        model_clauses.append(f"mfgSku LIKE :mn_{i}")
        params[f"mn_{i}"] = f"%{mn}%"
        params[f"mn_eq_{i}"] = mn

    # 品牌:名称 → sid 列表 → brandId IN(可下推)
    brand = parsed_intent.get("brand")
    brand_clause = ""
    if brand:
        brand_sids = await _resolve_brand_sids(session, brand)
        if brand_sids:
            ph = ", ".join(f":brand_s{i}" for i in range(len(brand_sids)))
            for i, s in enumerate(brand_sids):
                params[f"brand_s{i}"] = s
            brand_clause = f"brandId IN ({ph})"

    # 型号优先:先做一轮型号兼容搜索,保证型号命中的商品置顶。
    compat_results = []
    seen_codes: set = set()

    if model_clauses:
        compat_inner = []
        if brand_clause:
            compat_inner.append(brand_clause)
        eq_in = ", ".join(f":mn_eq_{i}" for i in range(len(model_numbers)))
        eq_where = " AND ".join(compat_inner + [f"mfgSku IN ({eq_in})"])
        rows = await _query_items(session, eq_where, params, limit)
        is_exact = bool(rows)
        if not rows:
            like_where = " AND ".join(compat_inner + [f"({' OR '.join(model_clauses)})"])
            rows = await _query_items(session, like_where, params, limit)
        for row in rows:
            item = _row_to_item(row)
            if is_exact:
                item["_exact_match"] = True
            compat_results.append(item)
            seen_codes.add(row[0])

    # 标准搜索(品类 + 关键词 + 普通规格 + 品牌)
    standard_inner = list(base_conditions)
    sp = []
    if kw_clause:
        sp.append(kw_clause)
    sp.extend(regular_spec_clauses)
    if brand_clause:
        sp.append(brand_clause)
    if sp:
        standard_inner.append(" AND ".join(sp))

    if not standard_inner and not compat_results:
        return []

    standard_results = []
    remaining = limit - len(compat_results)
    if standard_inner and remaining > 0:
        inner_where = " AND ".join(standard_inner)
        rows = await _query_items(session, inner_where, params, remaining)
        for row in rows:
            if row[0] not in seen_codes:
                standard_results.append(_row_to_item(row))

    return compat_results + standard_results


async def relaxed_search(session: AsyncSession, parsed_intent: dict, limit: int = 20) -> list[dict]:
    """Fallback search with progressively relaxed conditions."""
    relaxed = {**parsed_intent, "spec_keywords": []}
    results = await search_skus(session, relaxed, limit)
    if results:
        return results

    relaxed = {**relaxed, "l4_category": None}
    results = await search_skus(session, relaxed, limit)
    if results:
        return results

    relaxed = {**relaxed, "l3_category": None}
    results = await search_skus(session, relaxed, limit)
    if results:
        return results

    keywords = parsed_intent.get("keywords", [])
    if keywords:
        relaxed = {"keywords": keywords, "brand": parsed_intent.get("brand")}
        results = await search_skus(session, relaxed, limit)
        if results:
            return results

    for kw in keywords:
        relaxed = {"keywords": [kw]}
        results = await search_skus(session, relaxed, limit)
        if results:
            return results

    return []


async def search_brand_clusters(
    session: AsyncSession,
    brand: str,
    limit: int = 10,
) -> list[tuple[str, int]]:
    """Brand-only fallback: return [(l3_category_name, sku_count), ...] for the brand.

    品牌名 → t_brand.sid → v_item_info(全 10 分片视图)按 brand_id 聚合 l3 品类。
    这里只按 brand_id 过滤 + 按 l3_category_name 聚合(无中文 LIKE),走视图无碍。
    """
    sids = await _resolve_brand_sids(session, brand)
    if not sids:
        return []
    placeholders = ",".join(f":b{i}" for i in range(len(sids)))
    params: dict = {f"b{i}": s for i, s in enumerate(sids)}
    params["lim"] = limit
    rows = (await session.execute(
        text(
            f"""
            SELECT l3_category_name, COUNT(*) AS cnt
            FROM v_item_info
            WHERE brand_id IN ({placeholders})
              AND l3_category_name IS NOT NULL
            GROUP BY l3_category_name
            ORDER BY cnt DESC
            LIMIT :lim
            """
        ),
        params,
    )).fetchall()
    return [(row[0], int(row[1])) for row in rows]
