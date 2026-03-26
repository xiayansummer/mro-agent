import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.standard_mapping import find_equivalents

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

def test_multiple_keywords_one_standard():
    result = find_equivalents(["DIN931", "M8"])
    assert "ISO 4014" in result

def test_no_keywords():
    result = find_equivalents([])
    assert result == []

def test_no_duplicates():
    result = find_equivalents(["DIN934", "DIN934"])
    assert result.count("ISO 4032") == 1
