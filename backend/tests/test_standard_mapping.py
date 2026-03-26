import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.standard_mapping import find_equivalents, ATTRIBUTE_KNOWLEDGE

def test_din934_returns_iso_and_gb():
    result = find_equivalents(["DIN934"])
    assert "ISO 4032" in result
    assert "GB/T 6170" in result

def test_case_insensitive():
    result = find_equivalents(["din934"])
    assert "ISO 4032" in result

def test_spaces_ignored():
    result = find_equivalents(["DIN 934"])
    assert "ISO 4032" in result

def test_unknown_standard_returns_empty():
    result = find_equivalents(["UNKNOWN999"])
    assert result == []

def test_multiple_matching_standards():
    # Both DIN934 and DIN931 are known standards — results should contain equivalents for both
    result = find_equivalents(["DIN934", "DIN931"])
    assert "ISO 4032" in result   # from DIN934
    assert "ISO 4014" in result   # from DIN931

def test_no_keywords():
    result = find_equivalents([])
    assert result == []

def test_no_duplicates():
    result = find_equivalents(["DIN934", "DIN934"])
    assert result.count("ISO 4032") == 1

def test_gb_dotted_value_as_input():
    # Values returned from find_equivalents (e.g. "GB/T 70.1") should themselves be resolvable
    result = find_equivalents(["GB/T 70.1"])
    # GB/T 70.1 is not in STANDARD_EQUIVALENTS so should return empty — documents the current behavior
    assert result == []

def test_attribute_knowledge_structure():
    required_keys = {"材质等级", "强度等级", "规格（螺纹直径）", "表面处理", "密封材质"}
    assert required_keys.issubset(set(ATTRIBUTE_KNOWLEDGE.keys()))
    for key, options in ATTRIBUTE_KNOWLEDGE.items():
        assert options, f"{key} should have at least one option"
        for opt in options:
            assert "value" in opt, f"option in {key} missing 'value'"
            assert "note" in opt, f"option in {key} missing 'note'"
            assert "is_common" in opt, f"option in {key} missing 'is_common'"
