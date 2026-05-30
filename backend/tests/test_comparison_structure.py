import pytest

from app.models.comparison import (
    ComparisonCategory,
    ComparisonSpecification,
    ComparisonStructure,
)
from app.services import comparison_structure
from app.services.comparison_query_builder import build_search_terms


@pytest.mark.asyncio
async def test_build_comparison_structure_for_clear_procurement_need(monkeypatch):
    async def fake_parse_intent(*args, **kwargs):
        return {
            "l1_category": "紧固密封 框架结构",
            "l2_category": "螺栓螺母",
            "l3_category": "六角头螺栓",
            "l4_category": None,
            "keywords": ["外六角螺栓"],
            "spec_keywords": ["M8", "304", "30mm"],
            "brand": None,
            "query_type": "precise",
            "attribute_gaps": [],
        }

    monkeypatch.setattr(comparison_structure, "parse_intent", fake_parse_intent)

    result = await comparison_structure.build_comparison_structure("M8 304 外六角螺栓 30mm 买100个")

    assert result.shouldCreateDraft is True
    assert result.structure is not None
    assert result.structure.category.l1 == "紧固密封 框架结构"
    assert result.structure.category.l2 == "螺栓螺母"
    assert result.structure.category.l3 == "六角头螺栓"
    assert result.structure.specification.productType == "外六角螺栓"
    assert result.structure.specification.size == "M8"
    assert result.structure.specification.material == "304"
    assert result.structure.purchaseConstraints.quantity == 100
    assert result.structure.purchaseConstraints.unit == "个"
    assert result.structure.searchTerms.jd[0] == "外六角螺栓 304 M8 30mm"


@pytest.mark.asyncio
async def test_build_comparison_structure_asks_fastener_strength_before_draft(monkeypatch):
    async def fake_parse_intent(*args, **kwargs):
        return {
            "l1_category": "紧固密封 框架结构",
            "l2_category": "螺栓螺母",
            "l3_category": "六角螺母",
            "l4_category": None,
            "keywords": ["六角螺母"],
            "spec_keywords": ["M8"],
            "brand": None,
            "query_type": "broad_spec",
            "attribute_gaps": ["强度等级", "材质"],
        }

    monkeypatch.setattr(comparison_structure, "parse_intent", fake_parse_intent)

    result = await comparison_structure.build_comparison_structure("M8 六角螺母")

    assert result.shouldCreateDraft is False
    assert result.slotClarification is not None
    missing = result.slotClarification["missing"]
    assert any(item["key"] == "strength_grade" for item in missing)
    assert any("8级" in item["options"] for item in missing if item["key"] == "strength_grade")


@pytest.mark.asyncio
async def test_build_comparison_structure_allows_fastener_after_chip_answer(monkeypatch):
    async def fake_parse_intent(*args, **kwargs):
        return {
            "l1_category": "紧固密封 框架结构",
            "l2_category": "螺栓螺母",
            "l3_category": "六角螺母",
            "l4_category": None,
            "keywords": ["六角螺母"],
            "spec_keywords": ["M8", "8级", "304", "不限品牌"],
            "brand": None,
            "query_type": "broad_spec",
            "attribute_gaps": [],
        }

    monkeypatch.setattr(comparison_structure, "parse_intent", fake_parse_intent)

    result = await comparison_structure.build_comparison_structure("M8 8级 304 不限品牌 六角螺母")

    assert result.shouldCreateDraft is True
    assert result.slotClarification is None


@pytest.mark.asyncio
async def test_build_comparison_structure_rejects_non_procurement_message(monkeypatch):
    async def fake_parse_intent(*args, **kwargs):
        return {
            "l1_category": None,
            "l2_category": None,
            "l3_category": None,
            "l4_category": None,
            "keywords": [],
            "spec_keywords": [],
            "brand": None,
            "query_type": "vague",
            "attribute_gaps": [],
        }

    monkeypatch.setattr(comparison_structure, "parse_intent", fake_parse_intent)

    result = await comparison_structure.build_comparison_structure("你好")

    assert result.shouldCreateDraft is False
    assert result.structure is None
    assert "产品名称" in result.guidance


@pytest.mark.asyncio
async def test_build_comparison_structure_rejects_low_confidence_without_product_type(monkeypatch):
    async def fake_parse_intent(*args, **kwargs):
        return {
            "l1_category": None,
            "l2_category": None,
            "l3_category": None,
            "l4_category": None,
            "keywords": [],
            "spec_keywords": ["M8"],
            "brand": None,
            "query_type": "broad_spec",
            "attribute_gaps": ["产品类型"],
        }

    monkeypatch.setattr(comparison_structure, "parse_intent", fake_parse_intent)

    result = await comparison_structure.build_comparison_structure("M8")

    assert result.shouldCreateDraft is False
    assert "工业品类" in result.guidance


def test_build_search_terms_prioritizes_brand_and_core_specs():
    structure = ComparisonStructure(
        category=ComparisonCategory(
            l1="紧固密封 框架结构",
            l2="螺栓螺母",
            l3="六角头螺栓",
        ),
        specification=ComparisonSpecification(
            productType="外六角螺栓",
            brand="固万基",
            material="304",
            size="M8",
            standard="DIN933",
        ),
    )

    terms = build_search_terms(structure)

    assert terms.jd[0] == "固万基 外六角螺栓 DIN933 304 M8"
    assert terms.jd[1] == "外六角螺栓 DIN933 304 M8"
    assert 2 <= len(terms.jd) <= 3
    assert terms.jd == terms.zkh
    assert all("紧固密封 框架结构" not in term for term in terms.jd)


def test_build_search_terms_omits_empty_brand():
    structure = ComparisonStructure(
        category=ComparisonCategory(l3="O型圈"),
        specification=ComparisonSpecification(productType="O型圈", size="30×3.1mm"),
    )

    terms = build_search_terms(structure)

    assert terms.jd[0] == "O型圈 30×3.1mm"
    assert all("None" not in term for term in terms.jd)
