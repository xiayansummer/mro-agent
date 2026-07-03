"""ERP 商品库(d_mymro_pms)只读查询:品牌→经营品类等。

把原先散在 comparison_structure(NL→结构转换层)里的 ERP 物理表访问收敛到这里,
使 comparison_structure 不再认识 SQL / t_brand.sid / v_item_info / AsyncSessionLocal。
ERP schema 变动(见 [[project_mro_erp_db]])只影响本模块一处。
"""
from sqlalchemy import text

from app.db.mysql import AsyncSessionLocal
from app.services.normalization import _seed_terms_for


async def _query_brand_categories(session, brand: str) -> list[str]:
    """查该品牌的真实经营 L3 品类(按 SKU 数降序)。

    第一步在 t_brand(主键 sid, brandName)按品牌名 + 字典别名 LIKE 找出品牌 sid
    (兼顾"美和""美和 TOHO""MyMRO | 美和"等多条记录);第二步在 v_item_info 视图
    (UNION 全 10 个商品分片 + 已过滤 deleted)按 brand_id 聚合 l3 品类。
    过滤用 brand_id(而非 brand_name),可下推到各分片走索引,全量约 0.1~0.4s。
    """
    terms = _seed_terms_for(brand) or [brand]
    like_clauses = " OR ".join(f"brandName LIKE :t{i}" for i in range(len(terms)))
    like_params = {f"t{i}": f"%{term}%" for i, term in enumerate(terms)}
    brand_rows = await session.execute(
        text(f"SELECT sid FROM t_brand WHERE {like_clauses}"),
        like_params,
    )
    sids = [row[0] for row in brand_rows.fetchall()]
    if not sids:
        return []

    placeholders = ",".join(f":b{i}" for i in range(len(sids)))
    cat_params = {f"b{i}": sid for i, sid in enumerate(sids)}
    cat_rows = await session.execute(
        text(
            f"""
            SELECT l3_category_name, COUNT(*) AS cnt
            FROM v_item_info
            WHERE brand_id IN ({placeholders})
              AND l3_category_name IS NOT NULL
            GROUP BY l3_category_name
            ORDER BY cnt DESC
            LIMIT 6
            """
        ),
        cat_params,
    )
    return [row[0] for row in cat_rows.fetchall() if row[0]]


async def fetch_brand_categories(brand: str) -> list[str]:
    """查该品牌的真实经营 L3 品类。失败/无数据返回空(不阻断主流程)。"""
    brand = (brand or "").strip()
    if not brand:
        return []
    try:
        async with AsyncSessionLocal() as session:
            return await _query_brand_categories(session, brand)
    except Exception:
        return []
