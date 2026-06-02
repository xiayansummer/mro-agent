import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services import sku_search


def _exec(rows):
    res = MagicMock()
    res.fetchall.return_value = rows
    res.fetchone.return_value = rows[0] if rows else None
    return res


@pytest.mark.asyncio
async def test_resolve_brand_sids_uses_t_brand_with_aliases():
    session = AsyncMock()
    session.execute.return_value = _exec([(3286,), (31204,), (62481,)])
    sids = await sku_search._resolve_brand_sids(session, "美和")
    assert sids == [3286, 31204, 62481]
    sql = str(session.execute.call_args[0][0]).lower()
    assert "t_brand" in sql and "brandname like" in sql


@pytest.mark.asyncio
async def test_resolve_brand_sids_empty_returns_empty():
    session = AsyncMock()
    assert await sku_search._resolve_brand_sids(session, "") == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_category_sid_with_level():
    session = AsyncMock()
    session.execute.return_value = _exec([(400650,)])
    sid = await sku_search._resolve_category_sid(session, "葫芦绞车", 3)
    assert sid == 400650
    sql = str(session.execute.call_args[0][0]).lower()
    assert "t_category" in sql and "categorylevel" in sql


@pytest.mark.asyncio
async def test_resolve_category_sid_not_found():
    session = AsyncMock()
    session.execute.return_value = _exec([])
    assert await sku_search._resolve_category_sid(session, "查无此品类", 3) is None


@pytest.mark.asyncio
async def test_search_brand_clusters_uses_view_and_brand_id():
    session = AsyncMock()
    session.execute.side_effect = [
        _exec([(3286,), (31204,)]),                       # _resolve_brand_sids
        _exec([("组合吊索具", 5623), ("葫芦绞车", 905)]),   # 视图聚合
    ]
    clusters = await sku_search.search_brand_clusters(session, "美和")
    assert clusters == [("组合吊索具", 5623), ("葫芦绞车", 905)]
    assert session.execute.call_count == 2
    sql2 = str(session.execute.call_args_list[1][0][0]).lower()
    assert "v_item_info" in sql2 and "brand_id in" in sql2


@pytest.mark.asyncio
async def test_search_brand_clusters_no_brand_match():
    session = AsyncMock()
    session.execute.side_effect = [_exec([])]
    assert await sku_search.search_brand_clusters(session, "查无此牌") == []
    assert session.execute.call_count == 1


@pytest.mark.asyncio
async def test_search_skus_resolves_category_name_to_id_filter():
    """category 用名称→sid→id 列过滤(可下推),不再用 *_category_name = 名称。"""
    session = AsyncMock()
    session.execute.side_effect = [
        _exec([(400650,)]),  # _resolve_category_sid('葫芦绞车',3)
        _exec([("ITEM1", "美和TOHO 手拉葫芦", "美和", "1吨", "MFG1", "l1", "l2", "葫芦绞车", "l4", "attr")]),  # 主查询
    ]
    results = await sku_search.search_skus(session, {"l3_category": "葫芦绞车", "keywords": ["葫芦"]})
    assert results and results[0]["item_code"] == "ITEM1"
    main_sql = str(session.execute.call_args_list[-1][0][0]).lower()
    assert "t_item_info" in main_sql  # 分片 UNION(中文 LIKE 下推到分片内)
    assert "category3id =" in main_sql  # 原表 id 列过滤,非名称


@pytest.mark.asyncio
async def test_search_skus_unknown_category_returns_empty():
    """品类名解析不到 sid → 直接返回空(快速失败到 relaxed_search)。"""
    session = AsyncMock()
    session.execute.side_effect = [_exec([])]  # _resolve_category_sid 查不到
    results = await sku_search.search_skus(session, {"l3_category": "不存在", "keywords": ["x"]})
    assert results == []
