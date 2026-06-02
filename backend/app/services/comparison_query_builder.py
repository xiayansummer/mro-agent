from app.models.comparison import ComparisonSearchTerms, ComparisonStructure

MAX_TERMS_PER_PLATFORM = 3
MAX_SPEC_TOKENS = 4


def build_search_terms(structure: ComparisonStructure) -> ComparisonSearchTerms:
    terms = _build_ordered_terms(structure)
    return ComparisonSearchTerms(jd=terms[:MAX_TERMS_PER_PLATFORM], zkh=terms[:MAX_TERMS_PER_PLATFORM])


def _build_ordered_terms(structure: ComparisonStructure) -> list[str]:
    product_type = _clean_token(
        structure.specification.productType
        or structure.category.l4
        or structure.category.l3
        or structure.category.l2
    )
    if not product_type:
        return []

    brand = _clean_token(structure.specification.brand)
    model = _clean_token(structure.specification.model)
    spec_tokens = _spec_tokens(structure)

    candidates = []
    if brand:
        candidates.append(_join_tokens([brand, product_type, model, *spec_tokens]))
        candidates.append(_join_tokens([brand, product_type, model, *spec_tokens[:2]]))
        candidates.append(_join_tokens([brand, product_type, model]))
    else:
        candidates.append(_join_tokens([product_type, model, *spec_tokens]))
        candidates.append(_join_tokens([product_type, *spec_tokens[:2]]))

    if structure.category.l3 and _clean_token(structure.category.l3) != product_type:
        candidates.append(_join_tokens([structure.category.l3, *spec_tokens[:2]]))

    return _dedupe([term for term in candidates if term])


def _spec_tokens(structure: ComparisonStructure) -> list[str]:
    spec = structure.specification
    tokens = [
        spec.standard,
        spec.material,
        spec.size,
    ]
    tokens.extend(attr.value for attr in spec.attributes)
    return _dedupe(_clean_token(token) for token in tokens if _clean_token(token))[:MAX_SPEC_TOKENS]


def _join_tokens(tokens: list[str | None]) -> str:
    return " ".join(_dedupe(token for token in (_clean_token(token) for token in tokens) if token))


def _clean_token(token: str | None) -> str:
    return " ".join(str(token).strip().split()) if token else ""


def _dedupe(tokens) -> list[str]:
    seen = set()
    result = []
    for token in tokens:
        if not token or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result
