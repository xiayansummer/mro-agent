"""Tests the SQL building logic of search_brand_clusters.

We mock AsyncSession (no real DB) and exercise both DB calls:
  1. The DISTINCT brand_name scan inside discover_brand_variants
  2. The aggregate GROUP BY in search_brand_clusters

Real DB integration is verified manually during deployment.
"""
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services.sku_search import search_brand_clusters
from app.services.normalization import invalidate_brand_cache


def _make_session(distinct_brands: list[str], cluster_rows: list[tuple]):
    """Build a mocked AsyncSession that returns `distinct_brands` on the first
    execute() (the brand-list scan) and `cluster_rows` on the second (the GROUP BY)."""
    session = AsyncMock()
    distinct_result = MagicMock()
    distinct_result.fetchall.return_value = [(b,) for b in distinct_brands]
    cluster_result = MagicMock()
    cluster_result.fetchall.return_value = cluster_rows
    session.execute.side_effect = [distinct_result, cluster_result]
    return session


@pytest.fixture(autouse=True)
def _clear_brand_cache():
    invalidate_brand_cache()
    yield
    invalidate_brand_cache()


@pytest.mark.asyncio
async def test_search_brand_clusters_groups_by_l3():
    session = _make_session(
        distinct_brands=["美和", "TOHO", "美和TOHO", "无关品牌"],
        cluster_rows=[("手拉葫芦", 8), ("电动葫芦", 3), ("钢丝绳", 12)],
    )

    clusters = await search_brand_clusters(session, "美和")

    # 2 calls: distinct scan + cluster query
    assert session.execute.call_count == 2

    # Cluster query is the second call
    sql_text = str(session.execute.call_args_list[1][0][0])
    assert "GROUP BY" in sql_text.upper()
    assert "ORDER BY" in sql_text.upper()
    assert "l3_category_name" in sql_text
    assert "IN (" in sql_text

    # Variants discovered: 美和, TOHO, 美和TOHO (signature-clustered); excludes "无关品牌"
    cluster_params = session.execute.call_args_list[1][0][1]
    variant_values = {v for k, v in cluster_params.items() if k.startswith("b")}
    assert "美和" in variant_values
    assert "TOHO" in variant_values
    assert "美和TOHO" in variant_values
    assert "无关品牌" not in variant_values
    assert cluster_params["lim"] == 10

    assert clusters == [("手拉葫芦", 8), ("电动葫芦", 3), ("钢丝绳", 12)]


@pytest.mark.asyncio
async def test_search_brand_clusters_empty_brand_returns_empty():
    session = AsyncMock()
    clusters = await search_brand_clusters(session, "")
    assert clusters == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_search_brand_clusters_no_results():
    session = _make_session(
        distinct_brands=["未知品牌"],
        cluster_rows=[],
    )
    clusters = await search_brand_clusters(session, "未知品牌")
    assert clusters == []


@pytest.mark.asyncio
async def test_search_brand_clusters_respects_limit_param():
    """Non-default limit must be bound through to :lim, not hardcoded."""
    session = _make_session(
        distinct_brands=["美和"],
        cluster_rows=[],
    )
    await search_brand_clusters(session, "美和", limit=5)

    cluster_params = session.execute.call_args_list[1][0][1]
    assert cluster_params["lim"] == 5
