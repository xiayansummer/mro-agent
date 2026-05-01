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
