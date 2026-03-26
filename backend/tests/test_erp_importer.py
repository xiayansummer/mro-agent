# backend/tests/test_erp_importer.py
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import openpyxl
from app.services.erp_importer import parse_column_map, parse_rows, aggregate_erp_data

def _make_excel(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def test_parse_column_map_chinese():
    headers = ["物料号", "物料描述", "品牌", "数量", "金额"]
    col = parse_column_map(headers)
    assert col["item_code"] == 0
    assert col["item_name"] == 1
    assert col["brand"] == 2
    assert col["qty"] == 3

def test_parse_column_map_english():
    headers = ["item_code", "item_name", "brand", "quantity"]
    col = parse_column_map(headers)
    assert col["item_code"] == 0
    assert col["brand"] == 2

def test_parse_column_map_missing_required():
    """没有任何可识别的必要列时返回空 dict"""
    col = parse_column_map(["col1", "col2"])
    assert "item_code" not in col and "item_name" not in col

def test_aggregate_brands():
    rows = [
        {"brand": "SMC",  "item_name": "O型圈",  "item_code": "001", "qty": "10"},
        {"brand": "SMC",  "item_name": "O型圈2", "item_code": "002", "qty": "5"},
        {"brand": "米思米","item_name": "螺栓",   "item_code": "003", "qty": "20"},
    ]
    result = aggregate_erp_data(rows)
    assert result["top_brands"][0] == "SMC"
    assert "米思米" in result["top_brands"]

def test_aggregate_empty():
    result = aggregate_erp_data([])
    assert result["top_brands"] == []
    assert result["top_specs"] == []
