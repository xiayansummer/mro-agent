import pytest
from pydantic import ValidationError

from app.models.comparison import (
    ComparisonDraftStatus,
    ComparisonSearchTerms,
    ComparisonStructure,
    ExternalOffer,
    PurchaseConstraints,
)


def test_comparison_structure_defaults():
    structure = ComparisonStructure()

    assert structure.category.confidence == 0.0
    assert structure.specification.attributes == []
    # 默认四平台(1688 已 default=True,详见 test_platforms)
    assert structure.purchaseConstraints.preferredPlatforms == ["jd", "zkh", "ehsy", "1688"]
    assert structure.searchTerms.get("jd") == []
    assert structure.searchTerms.get("zkh") == []


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
    assert s.purchaseConstraints.preferredPlatforms == ["jd", "zkh", "ehsy", "1688"]


def test_search_terms_is_dict_and_dumps_flat():
    st = ComparisonSearchTerms({"jd": ["a"], "zkh": ["b"], "1688": ["c"], "ehsy": ["d"]})
    assert st.get("1688") == ["c"]
    assert st.get("缺失") == []
    assert st.model_dump(mode="json") == {"jd": ["a"], "zkh": ["b"], "1688": ["c"], "ehsy": ["d"]}


def test_search_terms_reads_legacy_jd_zkh_only():
    # 存量 DB 里只有 jd/zkh,反序列化应正常、缺失平台取空
    st = ComparisonSearchTerms.model_validate({"jd": ["x"], "zkh": ["y"]})
    assert st.get("jd") == ["x"] and st.get("1688") == []


def test_preferred_platforms_default_includes_1688():
    # 1688 端到端校准通过后已进默认四平台。
    default = PurchaseConstraints().preferredPlatforms
    assert default == ["jd", "zkh", "ehsy", "1688"]
