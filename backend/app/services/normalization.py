"""Brand and category name normalization.

Normalization is two-layered:
1. LLM prompt-level: aliases injected as examples so the LLM tends to
   output canonical names directly.
2. Field-level safety net: post-parse exact-match lookup on the LLM's
   extracted brand/category fields. NEVER apply to raw query text — that
   would risk substring corruption (e.g. "电动工具" → "电动工具耗材").

For brand search expansion (catching DB rows with non-canonical spellings),
see `discover_brand_variants` — it scans DISTINCT brand_name on first call
per canonical, caches the cluster, and TTL-refreshes so new DB writes are
picked up without restart.
"""
import json
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

from sqlalchemy import text as _sql_text

_DATA_DIR = Path(__file__).parent.parent.parent / "data"

# TTL on the brand-cluster cache (seconds).
BRAND_CACHE_TTL = 3600

# Process-local caches (separate per uvicorn worker; TTL keeps them eventually consistent).
_ALL_BRANDS_CACHE: Optional[tuple[float, list[str]]] = None     # (expiry_ts, distinct brand_name list)
_BRAND_CLUSTER_CACHE: dict[str, tuple[float, list[str]]] = {}   # canonical → (expiry_ts, [variants])


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


def _signature(s: str) -> str:
    """Compact lowercase alphanumeric+CJK signature for fuzzy brand comparison.
    Strips spaces, slashes, parens, dashes, case differences."""
    return re.sub(r"[^a-z0-9一-鿿]", "", s.lower())


def _sigs_match(a: str, b: str) -> bool:
    """Two signatures are clustered if the shorter is a substring of the longer.
    Minimum 2 chars for CJK-bearing sigs, 3 chars for pure-ASCII to avoid false hits."""
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if not short:
        return False
    has_cjk = any("一" <= c <= "鿿" for c in short)
    min_len = 2 if has_cjk else 3
    return len(short) >= min_len and short in long


def _seed_terms_for(brand: str) -> list[str]:
    """Return canonical + dictionary aliases as the seed term list for cluster discovery.
    Accepts canonical OR alias input."""
    aliases_map = load_brand_aliases()
    if brand in aliases_map:
        return [brand] + aliases_map[brand]
    canonical = _build_alias_to_canonical().get(brand.lower())
    if canonical:
        return [canonical] + aliases_map.get(canonical, [])
    return [brand]


def _canonical_of(brand: str) -> str:
    """Resolve any alias to canonical (or echo back if unknown)."""
    if brand in load_brand_aliases():
        return brand
    return _build_alias_to_canonical().get(brand.lower(), brand)


async def _get_all_db_brands(session) -> list[str]:
    """Fetch DISTINCT brand_name from t_item_sample, cached per process for BRAND_CACHE_TTL."""
    global _ALL_BRANDS_CACHE
    now = time.time()
    if _ALL_BRANDS_CACHE and _ALL_BRANDS_CACHE[0] > now:
        return _ALL_BRANDS_CACHE[1]
    result = await session.execute(_sql_text(
        "SELECT DISTINCT brand_name FROM t_item_sample WHERE brand_name IS NOT NULL"
    ))
    brands = [row[0] for row in result.fetchall() if row[0]]
    _ALL_BRANDS_CACHE = (now + BRAND_CACHE_TTL, brands)
    return brands


async def discover_brand_variants(session, brand: Optional[str]) -> list[str]:
    """Discover all DB-side spellings clustered with the given brand.

    Approach: fetch DISTINCT brand_name (cached), compare signatures of every
    DB brand against the seed signature set (canonical + dictionary aliases).
    Returns the canonical-keyed cluster, cached per canonical for TTL.

    Catches case/punctuation/script variants automatically (e.g. NORBAR / 诺霸 /
    诺霸Norbar / 诺霸/Norbar all cluster). The dictionary still bridges
    cross-script (Chinese ↔ English), but only ~10-20 dict entries are needed
    since case/punctuation variants are auto-discovered.
    """
    if not brand:
        return []

    canonical = _canonical_of(brand)
    now = time.time()

    cached = _BRAND_CLUSTER_CACHE.get(canonical)
    if cached and cached[0] > now:
        return cached[1]

    seed_sigs = {_signature(t) for t in _seed_terms_for(brand) if _signature(t)}
    if not seed_sigs:
        return [brand]

    all_brands = await _get_all_db_brands(session)
    cluster: list[str] = []
    seen: set[str] = set()
    for db_brand in all_brands:
        db_sig = _signature(db_brand)
        if not db_sig or db_brand in seen:
            continue
        if any(_sigs_match(s, db_sig) for s in seed_sigs):
            cluster.append(db_brand)
            seen.add(db_brand)

    if canonical not in seen:
        cluster.append(canonical)

    _BRAND_CLUSTER_CACHE[canonical] = (now + BRAND_CACHE_TTL, cluster)
    return cluster


def invalidate_brand_cache() -> None:
    """Clear cluster + all-brands caches. Useful after DB writes or for tests."""
    global _ALL_BRANDS_CACHE
    _ALL_BRANDS_CACHE = None
    _BRAND_CLUSTER_CACHE.clear()


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
