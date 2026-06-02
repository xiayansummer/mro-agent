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

    assert ranked[0]["id"] == "matched"
    assert ranked[0]["matchScore"] > ranked[1]["matchScore"]
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
