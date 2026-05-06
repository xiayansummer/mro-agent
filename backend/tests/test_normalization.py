from app.services.normalization import (
    load_brand_aliases,
    load_category_synonyms,
    normalize_brand,
    normalize_category,
    build_brand_examples_prompt,
    build_category_examples_prompt,
)


def test_load_brand_aliases_returns_dict():
    aliases = load_brand_aliases()
    assert isinstance(aliases, dict)
    assert "美和" in aliases
    assert "TOHO" in aliases["美和"]


def test_normalize_brand_canonical_unchanged():
    assert normalize_brand("美和") == "美和"


def test_normalize_brand_alias_to_canonical():
    assert normalize_brand("TOHO") == "美和"
    assert normalize_brand("美和TOHO") == "美和"
    assert normalize_brand("toho") == "美和"  # case-insensitive


def test_normalize_brand_unknown_unchanged():
    assert normalize_brand("不存在的牌子") == "不存在的牌子"


def test_normalize_brand_none_returns_none():
    assert normalize_brand(None) is None
    assert normalize_brand("") == ""


def test_normalize_category_canonical_unchanged():
    assert normalize_category("物料搬运 存储包装") == "物料搬运 存储包装"


def test_normalize_category_synonym_mapped():
    assert normalize_category("搬运") == "物料搬运 存储包装"
    assert normalize_category("搬运产品") == "物料搬运 存储包装"


def test_normalize_category_no_substring_pollution():
    """'电动工具' must NOT become '电动工具 工具耗材' — substring danger zone."""
    # The function only matches whole-string equality, never substring
    assert normalize_category("电动工具") == "电动工具"
    assert normalize_category("我要搬运车") == "我要搬运车"


def test_brand_examples_prompt_contains_canonical_and_aliases():
    prompt = build_brand_examples_prompt()
    assert "美和" in prompt
    assert "TOHO" in prompt
    assert "→" in prompt or "←" in prompt


def test_category_examples_prompt_contains_synonyms():
    prompt = build_category_examples_prompt()
    assert "搬运" in prompt
    assert "物料搬运" in prompt


# ── discover_brand_variants ─────────────────────────────────────────────────

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.normalization import (
    discover_brand_variants,
    invalidate_brand_cache,
    _signature,
    _sigs_match,
)


@pytest.fixture(autouse=True)
def _clear_brand_cache():
    invalidate_brand_cache()
    yield
    invalidate_brand_cache()


def _mock_session(distinct_brands: list[str]):
    session = AsyncMock()
    res = MagicMock()
    res.fetchall.return_value = [(b,) for b in distinct_brands]
    session.execute.return_value = res
    return session


def test_signature_strips_punctuation_and_case():
    assert _signature("Norbar (诺霸)") == "norbar诺霸"
    assert _signature("ARMSTRONG/阿姆斯壮") == "armstrong阿姆斯壮"
    assert _signature("3M.") == "3m"


def test_sigs_match_substring():
    assert _sigs_match("诺霸", "诺霸norbar")        # CJK substring 2+ chars
    assert _sigs_match("norbar", "诺霸norbar")      # ASCII substring 3+ chars
    assert _sigs_match("armstrong", "armstrong阿姆斯壮")
    assert not _sigs_match("xy", "abxydef")          # ASCII < 3 chars
    assert not _sigs_match("abc", "xyz")             # no overlap


@pytest.mark.asyncio
async def test_discover_clusters_norbar_variants():
    session = _mock_session([
        "诺霸", "Norbar", "NORBAR", "诺霸Norbar", "诺霸/Norbar",
        "阿姆斯壮", "Armstrong",  # different cluster — should NOT match
    ])
    variants = await discover_brand_variants(session, "诺霸")
    assert "诺霸" in variants
    assert "Norbar" in variants
    assert "NORBAR" in variants
    assert "诺霸Norbar" in variants
    assert "诺霸/Norbar" in variants
    assert "阿姆斯壮" not in variants
    assert "Armstrong" not in variants


@pytest.mark.asyncio
async def test_discover_resolves_alias_input():
    """Input 'Norbar' (an alias) should also discover the 诺霸 cluster."""
    session = _mock_session(["诺霸", "NORBAR", "诺霸Norbar"])
    variants = await discover_brand_variants(session, "Norbar")
    assert "诺霸" in variants
    assert "NORBAR" in variants


@pytest.mark.asyncio
async def test_discover_unknown_brand_returns_db_matches():
    """Unknown brand 'XYZ' still returns DB rows whose signature contains 'xyz'."""
    session = _mock_session(["XYZ Industries", "abcXYZdef", "Other"])
    variants = await discover_brand_variants(session, "XYZ")
    assert "XYZ Industries" in variants
    assert "abcXYZdef" in variants
    assert "Other" not in variants


@pytest.mark.asyncio
async def test_discover_caches_per_canonical():
    """Second call for same canonical should NOT re-query the DB."""
    session = _mock_session(["诺霸", "Norbar"])
    await discover_brand_variants(session, "诺霸")
    await discover_brand_variants(session, "诺霸")
    assert session.execute.call_count == 1  # only the first call hits DB


@pytest.mark.asyncio
async def test_discover_empty_brand_returns_empty():
    session = AsyncMock()
    assert await discover_brand_variants(session, "") == []
    assert await discover_brand_variants(session, None) == []
    session.execute.assert_not_called()
