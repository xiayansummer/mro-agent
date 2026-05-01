"""Brand and category name normalization.

Normalization is two-layered:
1. LLM prompt-level: aliases injected as examples so the LLM tends to
   output canonical names directly.
2. Field-level safety net: post-parse exact-match lookup on the LLM's
   extracted brand/category fields. NEVER apply to raw query text — that
   would risk substring corruption (e.g. "电动工具" → "电动工具耗材").
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_DATA_DIR = Path(__file__).parent.parent.parent / "data"


@lru_cache(maxsize=1)
def load_brand_aliases() -> dict[str, list[str]]:
    with (_DATA_DIR / "brand_aliases.json").open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_category_synonyms() -> dict[str, str]:
    with (_DATA_DIR / "category_synonyms.json").open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _build_alias_to_canonical() -> dict[str, str]:
    """Reverse map: lowercased alias → canonical brand."""
    out: dict[str, str] = {}
    for canonical, aliases in load_brand_aliases().items():
        out[canonical.lower()] = canonical
        for alias in aliases:
            out[alias.lower()] = canonical
    return out


def normalize_brand(brand: Optional[str]) -> Optional[str]:
    """Map any alias (case-insensitive, exact whole string) to the canonical brand."""
    if not brand:
        return brand
    return _build_alias_to_canonical().get(brand.lower(), brand)


def normalize_category(category: Optional[str]) -> Optional[str]:
    """Map a synonym (exact whole-string match) to standard L1/L2 name."""
    if not category:
        return category
    return load_category_synonyms().get(category, category)


def build_brand_examples_prompt() -> str:
    """Render the brand-alias section to inject into intent_parser system prompt."""
    lines = ["常见品牌别名（请直接输出标准名作为 brand 字段值）:"]
    for canonical, aliases in load_brand_aliases().items():
        if aliases:
            lines.append(f"- {canonical} ← {' / '.join(aliases)}")
    return "\n".join(lines)


def build_category_examples_prompt() -> str:
    """Render the category-synonym section to inject into intent_parser system prompt."""
    lines = ["常见品类同义（请直接归一到标准 L1/L2 名）:"]
    for syn, std in load_category_synonyms().items():
        lines.append(f"- {syn} → {std}")
    return "\n".join(lines)
