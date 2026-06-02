import re
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

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
    slotClarification: Optional[dict] = None
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
    parsed_slot = _parsed_slot_clarification(parsed)
    if parsed_slot:
        await _enrich_brand_only_category_options(parsed, parsed_slot)
        return ComparisonStructureResult(
            shouldCreateDraft=False,
            slotClarification=parsed_slot,
            parsedIntent=parsed,
        )

    slot_clarification = _comparison_slot_clarification(parsed, structure)
    if slot_clarification:
        return ComparisonStructureResult(
            shouldCreateDraft=False,
            slotClarification=slot_clarification,
            parsedIntent=parsed,
        )

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
    if (
        parsed.get("query_type") == "vague"
        and not parsed.get("keywords")
        and not parsed.get("l3_category")
        and not parsed.get("l4_category")
        and not parsed.get("brand")
        and not parsed.get("spec_keywords")
    ):
        return False
    return bool(
        parsed.get("keywords")
        or parsed.get("l3_category")
        or parsed.get("l4_category")
        or parsed.get("brand")
        or parsed.get("spec_keywords")
    )


def _parsed_slot_clarification(parsed: dict) -> Optional[dict]:
    if not parsed.get("need_clarification"):
        return None
    payload = parsed.get("slot_clarification")
    if not isinstance(payload, dict):
        return None
    missing = payload.get("missing")
    if not isinstance(missing, list) or not missing:
        return None
    return payload


def _is_category_dimension(item: dict) -> bool:
    return item.get("icon") == "📦" or "品类" in str(item.get("question") or "")


def _apply_brand_categories_to_slot(parsed: dict, slot: dict, categories: list[str]) -> bool:
    """brand-only 时,用 DB 查到的该品牌真实品类替换 slot 里品类维度的候选。

    纯函数,返回是否发生替换。
    - 仅当有 brand 且尚无明确品类(brand-only)时生效
    - 仅替换"品类"维度(icon 📦 或问句含"品类"),其它维度(型号/规格等)不动
    - categories 为空则不替换(DB 没有该品牌数据时保留原候选兜底)
    """
    if not parsed.get("brand"):
        return False
    if parsed.get("l3_category") or parsed.get("l4_category"):
        return False
    if not categories:
        return False
    missing = slot.get("missing")
    if not isinstance(missing, list):
        return False
    for item in missing:
        if _is_category_dimension(item):
            item["options"] = categories[:5]
            return True
    return False


async def _query_brand_categories(session, brand: str) -> list[str]:
    """查该品牌的真实经营 L3 品类(按 SKU 数降序)。

    第一步在 t_brand(主键 sid, brandName)按品牌名 + 字典别名 LIKE 找出品牌 sid
    (兼顾"美和""美和 TOHO""MyMRO | 美和"等多条记录);第二步在 v_item_info 视图
    (UNION 全 10 个商品分片 + 已过滤 deleted)按 brand_id 聚合 l3 品类。
    过滤用 brand_id(而非 brand_name),可下推到各分片走索引,全量约 0.1~0.4s。
    """
    from app.services.normalization import _seed_terms_for

    terms = _seed_terms_for(brand) or [brand]
    like_clauses = " OR ".join(f"brandName LIKE :t{i}" for i in range(len(terms)))
    like_params = {f"t{i}": f"%{term}%" for i, term in enumerate(terms)}
    brand_rows = await session.execute(
        text(f"SELECT sid FROM t_brand WHERE {like_clauses}"),
        like_params,
    )
    sids = [row[0] for row in brand_rows.fetchall()]
    if not sids:
        return []

    placeholders = ",".join(f":b{i}" for i in range(len(sids)))
    cat_params = {f"b{i}": sid for i, sid in enumerate(sids)}
    cat_rows = await session.execute(
        text(
            f"""
            SELECT l3_category_name, COUNT(*) AS cnt
            FROM v_item_info
            WHERE brand_id IN ({placeholders})
              AND l3_category_name IS NOT NULL
            GROUP BY l3_category_name
            ORDER BY cnt DESC
            LIMIT 6
            """
        ),
        cat_params,
    )
    return [row[0] for row in cat_rows.fetchall() if row[0]]


async def _fetch_brand_categories(brand: str) -> list[str]:
    """查该品牌的真实经营 L3 品类。失败/无数据返回空(不阻断主流程)。"""
    brand = (brand or "").strip()
    if not brand:
        return []
    from app.db.mysql import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            return await _query_brand_categories(session, brand)
    except Exception:
        return []


async def _enrich_brand_only_category_options(parsed: dict, slot: dict) -> None:
    """brand-only 且 slot 含品类维度时,用 DB 真实品类替换 LLM 凭空生成的品类候选。
    通用于所有品牌:用户只给品牌名时,品类候选来自该品牌在库里的真实经营品类。"""
    brand = parsed.get("brand")
    if not brand or parsed.get("l3_category") or parsed.get("l4_category"):
        return
    missing = slot.get("missing") or []
    if not any(_is_category_dimension(item) for item in missing):
        return
    categories = await _fetch_brand_categories(brand)
    _apply_brand_categories_to_slot(parsed, slot, categories)


def _comparison_slot_clarification(parsed: dict, structure: ComparisonStructure) -> Optional[dict]:
    missing = []
    spec = structure.specification
    product_type = spec.productType or structure.category.l3 or structure.category.l2 or "该产品"
    known = _known_params(parsed, structure)
    spec_text = " ".join(str(value) for value in (parsed.get("spec_keywords") or [])).lower()
    raw_text = " ".join(
        str(value)
        for value in [
            parsed.get("inferred_need") or "",
            *(parsed.get("keywords") or []),
            *(parsed.get("spec_keywords") or []),
        ]
    )

    if _is_threaded_fastener(structure):
        if not spec.size:
            missing.append({
                "key": "size",
                "icon": "📏",
                "question": "需要什么规格尺寸？",
                "options": ["M6", "M8", "M10", "M12", "其他规格"],
            })
        if _needs_strength_grade(parsed, structure, spec_text):
            missing.append({
                "key": "strength_grade",
                "icon": "⚙️",
                "question": "需要什么强度等级？",
                "options": _strength_options(structure),
            })
        if not spec.material and not any(token in raw_text for token in ["碳钢", "不锈钢", "304", "316", "合金钢"]):
            missing.append({
                "key": "material",
                "icon": "🔧",
                "question": "需要什么材质？",
                "options": ["碳钢", "304不锈钢", "316不锈钢", "合金钢", "其他材质"],
            })
    if _should_ask_brand(parsed, structure, len(missing)):
        missing.append({
            "key": "brand",
            "icon": "🏷️",
            "question": "有品牌偏好吗？",
            "options": _brand_options(structure),
        })
    if _should_ask_quantity(structure, len(missing)):
        missing.append({
            "key": "quantity",
            "icon": "📦",
            "question": "本次大概采购数量是多少？",
            "options": ["1件", "10件", "100件", "按平台起订量"],
        })

    if not missing:
        return None

    return {
        "summary": f"需要采购{product_type}，请先确认关键参数后再查询京东工业品和震坤行。",
        "known": known,
        "missing": missing[:3],
    }


def _known_params(parsed: dict, structure: ComparisonStructure) -> list[dict]:
    known = []
    spec = structure.specification
    if spec.productType:
        known.append({"label": "商品类型", "value": spec.productType})
    if spec.size:
        known.append({"label": "规格", "value": spec.size})
    if spec.material:
        known.append({"label": "材质", "value": spec.material})
    if spec.brand:
        known.append({"label": "品牌", "value": spec.brand})
    for keyword in parsed.get("spec_keywords") or []:
        value = str(keyword)
        if _STRENGTH_RE.search(value) and not any(item["label"] == "强度等级" for item in known):
            known.append({"label": "强度等级", "value": value})
    for attribute in spec.attributes:
        if not attribute.value:
            continue
        if any(item["value"] == attribute.value for item in known):
            continue
        known.append({"label": attribute.name, "value": attribute.value})
        if len(known) >= 5:
            break
    return known


def _is_threaded_fastener(structure: ComparisonStructure) -> bool:
    text = " ".join(
        value or ""
        for value in [
            structure.category.l2,
            structure.category.l3,
            structure.category.l4,
            structure.specification.productType,
        ]
    )
    return any(token in text for token in ["螺栓", "螺母", "螺钉", "螺丝"])


_STRENGTH_RE = re.compile(r"(?:\b\d{1,2}(?:\.\d)?\s*级\b|\b\d{1,2}(?:\.\d)?\s*grade\b)", re.I)


def _needs_strength_grade(parsed: dict, structure: ComparisonStructure, spec_text: str) -> bool:
    if _STRENGTH_RE.search(spec_text):
        return False
    if parsed.get("query_type") == "precise":
        return False
    text = " ".join(
        value or ""
        for value in [
            structure.category.l3,
            structure.category.l4,
            structure.specification.productType,
        ]
    )
    return any(token in text for token in ["螺栓", "螺母", "螺钉", "螺丝"])


def _strength_options(structure: ComparisonStructure) -> list[str]:
    text = " ".join(
        value or ""
        for value in [
            structure.category.l3,
            structure.category.l4,
            structure.specification.productType,
        ]
    )
    if "螺母" in text:
        return ["4级", "6级", "8级", "10级", "12级"]
    return ["4.8级", "8.8级", "10.9级", "12.9级", "其他等级"]


def _should_ask_brand(parsed: dict, structure: ComparisonStructure, missing_count: int) -> bool:
    if parsed.get("query_type") == "precise":
        return False
    if missing_count >= 3 or structure.specification.brand:
        return False
    text = " ".join(str(value) for value in [
        parsed.get("brand") or "",
        *(parsed.get("keywords") or []),
        *(parsed.get("spec_keywords") or []),
    ])
    if any(token in text for token in ["不限品牌", "任意品牌", "无品牌要求", "其他品牌"]):
        return False
    return _has_concrete_product_type(structure)


def _should_ask_quantity(structure: ComparisonStructure, missing_count: int) -> bool:
    if missing_count >= 3:
        return False
    constraints = structure.purchaseConstraints
    if constraints.quantity is not None or constraints.unit:
        return False
    return _has_concrete_product_type(structure)


def _has_concrete_product_type(structure: ComparisonStructure) -> bool:
    return bool(
        structure.specification.productType
        or structure.category.l3
        or structure.category.l4
    )


def _brand_options(structure: ComparisonStructure) -> list[str]:
    if _is_threaded_fastener(structure):
        return ["不限品牌", "晋亿", "固万基", "东明", "其他品牌"]
    return ["不限品牌", "国产品牌", "进口品牌", "指定品牌", "其他品牌"]


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
