import pytest
from pydantic import ValidationError

from app.models.comparison import (
    ComparisonDraftStatus,
    ComparisonStructure,
    ExternalOffer,
)


def test_comparison_structure_defaults():
    structure = ComparisonStructure()

    assert structure.category.confidence == 0.0
    assert structure.specification.attributes == []
    assert structure.purchaseConstraints.preferredPlatforms == ["jd", "zkh", "ehsy"]
    assert structure.searchTerms.jd == []
    assert structure.searchTerms.zkh == []


def test_external_offer_required_fields_and_defaults():
    offer = ExternalOffer(
        id="jd-1",
        platform="jd",
        title="M8 不锈钢六角螺栓",
        unitComparable=False,
        productUrl="https://example.com/item",
        imageUrl="https://example.com/image.jpg",
        rawRank=1,
        matchScore=85,
    )

    assert offer.currency == "CNY"
    assert offer.imageUrl == "https://example.com/image.jpg"
    assert offer.matchReasons == []


def test_external_offer_rejects_unknown_platform():
    with pytest.raises(ValidationError):
        ExternalOffer(
            id="bad-1",
            platform="other",
            title="x",
            unitComparable=False,
            productUrl="https://example.com/item",
            rawRank=1,
            matchScore=0,
        )


def test_comparison_status_values_are_stable():
    assert ComparisonDraftStatus.NEEDS_CONFIRMATION == "needs_confirmation"
    assert ComparisonDraftStatus.TASK_CREATED == "task_created"


def test_platform_accepts_ehsy():
    o = ExternalOffer(
        id="ehsy-X1", platform="ehsy", title="3M 口罩", unitComparable=False,
        productUrl="https://www.ehsy.com/product-X1", rawRank=0, matchScore=0.0,
    )
    assert o.platform == "ehsy"


def test_structure_default_platforms_include_ehsy():
    s = ComparisonStructure()
    assert s.purchaseConstraints.preferredPlatforms == ["jd", "zkh", "ehsy"]
