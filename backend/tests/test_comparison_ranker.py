from app.models.comparison import (
    ComparisonCategory,
    ComparisonSpecification,
    ComparisonStructure,
    SpecificationAttribute,
)
from app.services.comparison_ranker import rank_external_offers


def test_rank_external_offers_prioritizes_spec_match_over_low_price():
    structure = ComparisonStructure(
        category=ComparisonCategory(l3="六角头螺栓"),
        specification=ComparisonSpecification(
            productType="外六角螺栓",
            material="304",
            size="M8",
            attributes=[SpecificationAttribute(name="规格", value="M8")],
        ),
    )
    offers = [
        {
            "id": "cheap-wrong",
            "title": "普通碳钢螺丝 M6",
            "priceValue": 0.1,
            "unitComparable": False,
            "rawRank": 1,
        },
        {
            "id": "matched",
            "title": "304不锈钢外六角螺栓 M8x40",
            "priceValue": 8,
            "unitComparable": False,
            "rawRank": 2,
        },
    ]

    ranked = rank_external_offers(structure, offers)
    ids = [o["id"] for o in ranked]

    # 规格匹配的保留并排第一;完全不匹配的低分(cheap-wrong, < 10)被过滤掉
    assert ids[0] == "matched"
    assert "cheap-wrong" not in ids
    assert any("规格匹配" in reason for reason in ranked[0]["matchReasons"])


def test_rank_external_offers_uses_price_only_as_tie_breaker():
    structure = ComparisonStructure(
        specification=ComparisonSpecification(productType="口罩", brand="3M"),
    )
    offers = [
        {
            "id": "expensive",
            "title": "3M 口罩 N95",
            "priceValue": 20,
            "unitComparable": False,
            "rawRank": 1,
        },
        {
            "id": "cheap",
            "title": "3M 口罩 N95",
            "priceValue": 10,
            "unitComparable": False,
            "rawRank": 2,
        },
    ]

    ranked = rank_external_offers(structure, offers)

    assert ranked[0]["id"] == "cheap"
    assert ranked[0]["matchScore"] == ranked[1]["matchScore"]


def test_rank_filters_off_brand_when_brand_specified():
    """指定品牌时,只保留命中该品牌(含别名)的商品,杂牌剔除。通用于所有品牌。"""
    structure = ComparisonStructure(
        specification=ComparisonSpecification(productType="手拉葫芦", brand="美和"),
    )
    offers = [
        {"id": "miwa", "title": "美和TOHO 手拉葫芦1吨3米", "priceValue": 200, "rawRank": 1},
        {"id": "zaba1", "title": "沪工手拉葫芦1吨", "priceValue": 50, "rawRank": 2},
        {"id": "zaba2", "title": "一马当先倒链手拉葫芦", "priceValue": 60, "rawRank": 3},
    ]
    ranked = rank_external_offers(structure, offers)
    assert [o["id"] for o in ranked] == ["miwa"]


def test_rank_brand_match_via_alias_kept():
    """标题只写英文别名(TOHO)的真品牌商品也应保留。"""
    structure = ComparisonStructure(
        specification=ComparisonSpecification(productType="手拉葫芦", brand="美和"),
    )
    offers = [
        {"id": "toho", "title": "TOHO 手拉葫芦 1T", "priceValue": 180, "rawRank": 1},
        {"id": "zaba", "title": "沪工手拉葫芦", "priceValue": 50, "rawRank": 2},
    ]
    ranked = rank_external_offers(structure, offers)
    assert [o["id"] for o in ranked] == ["toho"]


def test_rank_keeps_all_when_no_brand_match_fallback():
    """平台完全没有该品牌时,兜底保留全部(不返回空列表)。"""
    structure = ComparisonStructure(
        specification=ComparisonSpecification(productType="手拉葫芦", brand="美和"),
    )
    offers = [
        {"id": "zaba1", "title": "沪工手拉葫芦1吨", "priceValue": 50, "rawRank": 1},
        {"id": "zaba2", "title": "一马当先倒链手拉葫芦", "priceValue": 60, "rawRank": 2},
    ]
    ranked = rank_external_offers(structure, offers)
    assert len(ranked) == 2


def test_rank_no_brand_filter_when_brand_absent():
    """未指定品牌 → 不做品牌过滤,全部保留。"""
    structure = ComparisonStructure(
        specification=ComparisonSpecification(productType="手拉葫芦"),
    )
    offers = [
        {"id": "a", "title": "沪工手拉葫芦", "priceValue": 50, "rawRank": 1},
        {"id": "b", "title": "美和TOHO 手拉葫芦", "priceValue": 200, "rawRank": 2},
    ]
    ranked = rank_external_offers(structure, offers)
    assert len(ranked) == 2


def test_preference_brand_boosts_offer_ranking():
    """用户历史偏好品牌(DPO 硬加权)→ 命中 offer 显著加分、顶到前面。"""
    structure = ComparisonStructure(
        specification=ComparisonSpecification(productType="手拉葫芦"),
    )
    offers = [
        {"id": "other", "title": "沪工 手拉葫芦 2吨", "priceValue": 90, "rawRank": 1},
        {"id": "preferred", "title": "美和 手拉葫芦 2吨", "priceValue": 100, "rawRank": 2},
    ]
    # 无偏好:两者 productType 都匹配,按价格 other(90<100) 在前
    baseline = rank_external_offers(structure, offers)
    assert baseline[0]["id"] == "other"
    # 有偏好"美和":preferred 被偏好加分顶到第一
    ranked = rank_external_offers(
        structure, offers, preferences={"brands": ["美和"], "categories": []}
    )
    assert ranked[0]["id"] == "preferred"
    assert any("偏好品牌" in r for r in ranked[0]["matchReasons"])
    pref_score = next(o["matchScore"] for o in ranked if o["id"] == "preferred")
    base_score = next(o["matchScore"] for o in baseline if o["id"] == "preferred")
    assert pref_score > base_score


def test_preference_none_leaves_scoring_unchanged():
    """preferences=None → 不加偏好分,行为与原来一致。"""
    structure = ComparisonStructure(
        specification=ComparisonSpecification(productType="手拉葫芦"),
    )
    offers = [{"id": "a", "title": "美和 手拉葫芦", "priceValue": 10, "rawRank": 1}]
    ranked = rank_external_offers(structure, offers, preferences=None)
    assert not any("偏好品牌" in r for r in ranked[0]["matchReasons"])


def test_low_match_score_offers_filtered_out():
    """匹配度 < 10 的离谱结果(连产品类型都没匹配上)不展示。"""
    structure = ComparisonStructure(
        specification=ComparisonSpecification(productType="手拉葫芦"),
    )
    offers = [
        {"id": "good", "title": "手拉葫芦 2吨", "priceValue": 100, "rawRank": 1},
        {"id": "junk", "title": "螺丝刀套装", "priceValue": 5, "rawRank": 2},
    ]
    ranked = rank_external_offers(structure, offers)
    ids = [o["id"] for o in ranked]
    assert "good" in ids
    assert "junk" not in ids  # 仅含价格(+2) < 10,被滤
