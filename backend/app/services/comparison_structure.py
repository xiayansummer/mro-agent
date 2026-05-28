import re
from typing import Optional

from pydantic import BaseModel, Field

from app.models.comparison import (
    ComparisonCategory,
    ComparisonSpecification,
    ComparisonStructure,
    PurchaseConstraints,
    SpecificationAttribute,
)
from app.services.comparison_query_builder import build_search_terms
from app.services.intent_parser import parse_intent


class ComparisonStructureResult(BaseModel):
    shouldCreateDraft: bool
    structure: Optional[ComparisonStructure] = None
    guidance: Optional[str] = None
    parsedIntent: dict = Field(default_factory=dict)


async def build_comparison_structure(
    user_message: str,
    conversation_context: list[dict] | None = None,
    memory_context: str = "",
) -> ComparisonStructureResult:
    parsed = await parse_intent(
        user_message,
        conversation_context=conversation_context,
        memory_context=memory_context,
    )

    if not _has_procurement_object(parsed):
        return ComparisonStructureResult(
            shouldCreateDraft=False,
            guidance="请提供要采购的产品名称或型号规格，例如：M8 304 外六角螺栓 30mm。",
            parsedIntent=parsed,
        )

    structure = _structure_from_intent(user_message, parsed)
    if structure.category.confidence < 0.35 and not structure.specification.productType:
        return ComparisonStructureResult(
            shouldCreateDraft=False,
            guidance="暂时无法识别明确的工业品类，请补充产品名称、型号或关键规格。",
            parsedIntent=parsed,
        )

    structure.searchTerms = build_search_terms(structure)
    return ComparisonStructureResult(
        shouldCreateDraft=True,
        structure=structure,
        parsedIntent=parsed,
    )


def _structure_from_intent(user_message: str, parsed: dict) -> ComparisonStructure:
    category = ComparisonCategory(
        l1=parsed.get("l1_category"),
        l2=parsed.get("l2_category"),
        l3=parsed.get("l3_category"),
        l4=parsed.get("l4_category"),
        confidence=_category_confidence(parsed),
    )
    specification = ComparisonSpecification(
        productType=_product_type(parsed),
        brand=parsed.get("brand"),
        model=_first_model_keyword(parsed.get("spec_keywords") or []),
        material=_first_matching(parsed.get("spec_keywords") or [], _MATERIAL_RE),
        size=_first_matching(parsed.get("spec_keywords") or [], _SIZE_RE),
        standard=_first_matching(parsed.get("spec_keywords") or [], _STANDARD_RE),
        attributes=_attributes_from_spec_keywords(parsed.get("spec_keywords") or []),
        missing=list(parsed.get("attribute_gaps") or []),
    )
    return ComparisonStructure(
        category=category,
        specification=specification,
        purchaseConstraints=_purchase_constraints(user_message),
    )


def _has_procurement_object(parsed: dict) -> bool:
    if parsed.get("query_type") == "vague" and not parsed.get("keywords") and not parsed.get("l3_category"):
        return False
    return bool(
        parsed.get("keywords")
        or parsed.get("l3_category")
        or parsed.get("l4_category")
        or parsed.get("brand")
        or parsed.get("spec_keywords")
    )


def _category_confidence(parsed: dict) -> float:
    score = 0.0
    if parsed.get("l1_category"):
        score += 0.25
    if parsed.get("l2_category"):
        score += 0.25
    if parsed.get("l3_category"):
        score += 0.35
    if parsed.get("l4_category"):
        score += 0.10
    if parsed.get("keywords"):
        score += 0.05
    if parsed.get("query_type") in {"application", "vague"}:
        score -= 0.15
    return max(0.0, min(1.0, score))


def _product_type(parsed: dict) -> Optional[str]:
    keywords = [kw for kw in parsed.get("keywords") or [] if kw]
    if keywords:
        return " ".join(keywords[:2])
    return parsed.get("l4_category") or parsed.get("l3_category") or parsed.get("l2_category")


_STANDARD_RE = re.compile(r"^(?:DIN|ISO|GB|JIS|ASTM|ANSI|BS|EN|ASME|SAE)\s*[\w.-]+$", re.I)
_SIZE_RE = re.compile(r"^(?:M\d+(?:[×x*]\d+)?|\d+(?:\.\d+)?\s*(?:mm|cm|m|寸|英寸)?|\d+[×x*]\d+.*)$", re.I)
_MATERIAL_RE = re.compile(r"(?:304|316|201|碳钢|不锈钢|合金钢|黄铜|铜|铝|橡胶|硅胶|PTFE|四氟|尼龙)", re.I)


def _attributes_from_spec_keywords(spec_keywords: list[str]) -> list[SpecificationAttribute]:
    attributes = []
    for keyword in spec_keywords:
        if _STANDARD_RE.match(keyword):
            name = "标准"
        elif _MATERIAL_RE.search(keyword):
            name = "材质"
        elif _SIZE_RE.match(keyword):
            name = "规格"
        else:
            name = "参数"
        attributes.append(SpecificationAttribute(name=name, value=keyword))
    return attributes


def _first_matching(values: list[str], pattern: re.Pattern) -> Optional[str]:
    for value in values:
        if pattern.search(value):
            return value
    return None


def _first_model_keyword(values: list[str]) -> Optional[str]:
    for value in values:
        if _STANDARD_RE.match(value) or _MATERIAL_RE.search(value) or _SIZE_RE.match(value):
            continue
        if re.search(r"[A-Za-z]", value) and re.search(r"\d", value):
            return value
    return None


def _purchase_constraints(user_message: str) -> PurchaseConstraints:
    quantity, unit = _extract_quantity(user_message)
    return PurchaseConstraints(quantity=quantity, unit=unit)


def _extract_quantity(user_message: str) -> tuple[Optional[float], Optional[str]]:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(个|只|件|套|盒|包|支|米|kg|公斤|箱|卷)", user_message, re.I)
    if not match:
        return None, None
    value = float(match.group(1))
    if value.is_integer():
        value = int(value)
    return value, match.group(2)
