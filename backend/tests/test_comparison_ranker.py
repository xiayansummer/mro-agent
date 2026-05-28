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
