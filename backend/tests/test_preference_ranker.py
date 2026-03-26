import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.preference_ranker import rank_by_preference

MEMORY_WITH_BRAND = """
【该用户产品偏好（来自历史反馈）】

偏好品牌：SMC, 米思米
常用品类：螺栓螺母
"""

def _sku(code, brand, l2="螺栓螺母"):
    return {"item_code": code, "item_name": f"产品{code}",
            "brand_name": brand, "l2_category_name": l2}

def test_preferred_brand_moves_to_top():
    results = [_sku("A001", "未知品牌"), _sku("A002", "SMC")]
    ranked = rank_by_preference(results, MEMORY_WITH_BRAND)
    assert ranked[0]["item_code"] == "A002"

def test_preferred_category_boosts_score():
    results = [
        _sku("A001", "X", l2="密封圈"),
        _sku("A002", "Y", l2="螺栓螺母"),
    ]
    ranked = rank_by_preference(results, MEMORY_WITH_BRAND)
    assert ranked[0]["item_code"] == "A002"

def test_empty_memory_preserves_order():
    results = [_sku("A001", "X"), _sku("A002", "Y")]
    ranked = rank_by_preference(results, "")
    assert [r["item_code"] for r in ranked] == ["A001", "A002"]

def test_empty_results_returns_empty():
    assert rank_by_preference([], MEMORY_WITH_BRAND) == []

def test_tiebreak_preserves_original_order():
    results = [_sku("A001", "未知"), _sku("A002", "未知")]
    ranked = rank_by_preference(results, MEMORY_WITH_BRAND)
    assert [r["item_code"] for r in ranked] == ["A001", "A002"]
