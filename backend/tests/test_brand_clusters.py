"""Tests the SQL building logic of search_brand_clusters.

We don't hit a real DB here — we mock AsyncSession and assert the SQL
shape and parameters. Real DB integration is verified manually during
Phase 8 deployment.
"""
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services.sku_search import search_brand_clusters


@pytest.mark.asyncio
async def test_search_brand_clusters_groups_by_l3():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        ("手拉葫芦", 8),
        ("电动葫芦", 3),
        ("钢丝绳", 12),
    ]
    mock_session.execute.return_value = mock_result

    clusters = await search_brand_clusters(mock_session, "美和")

    # SQL must use GROUP BY (verified by inspecting the call)
    sql_text = str(mock_session.execute.call_args[0][0])
    assert "GROUP BY" in sql_text.upper()
    assert "ORDER BY" in sql_text.upper()
    assert "l3_category_name" in sql_text

    # Brand parameter should be passed
    params = mock_session.execute.call_args[0][1]
    assert params == {"brand": "美和", "lim": 10}

    # Returns list of (l3_name, count) tuples in order from DB
    assert clusters == [("手拉葫芦", 8), ("电动葫芦", 3), ("钢丝绳", 12)]


@pytest.mark.asyncio
async def test_search_brand_clusters_empty_brand_returns_empty():
    mock_session = AsyncMock()
    clusters = await search_brand_clusters(mock_session, "")
    assert clusters == []
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_search_brand_clusters_no_results():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_session.execute.return_value = mock_result

    clusters = await search_brand_clusters(mock_session, "未知品牌")
    assert clusters == []
