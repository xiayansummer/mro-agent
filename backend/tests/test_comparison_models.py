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
    assert structure.purchaseConstraints.preferredPlatforms == ["jd", "zkh"]
    assert structure.searchTerms.jd == []
    assert structure.searchTerms.zkh == []


def test_external_offer_required_fields_and_defaults():
    offer = ExternalOffer(
        id="jd-1",
        platform="jd",
        title="M8 不锈钢六角螺栓",
        unitComparable=False,
        productUrl="https://example.com/item",
        rawRank=1,
        matchScore=85,
    )

    assert offer.currency == "CNY"
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
