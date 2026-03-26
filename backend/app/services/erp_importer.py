"""
ERP 历史数据导入服务。
支持 Excel (.xlsx/.xls) 和 CSV 格式。
只做聚合，不保存原始数据（隐私保护）。
"""
import csv
import io
import logging
import re
from typing import Any

import openpyxl

logger = logging.getLogger(__name__)

_COLUMN_ALIASES: dict[str, list[str]] = {
    "item_code": ["物料号", "产品编码", "物料编号", "item_code", "code", "sku", "料号"],
    "item_name": ["物料描述", "产品名称", "品名", "item_name", "name", "description", "物料名称"],
    "brand":     ["品牌", "品牌名", "brand", "brand_name", "厂家"],
    "qty":       ["数量", "采购数量", "quantity", "qty", "用量"],
    "amount":    ["金额", "采购金额", "amount", "price", "费用"],
    "date":      ["日期", "采购日期", "date", "创建日期"],
}


def parse_column_map(headers: list[str]) -> dict[str, int]:
    col_map: dict[str, int] = {}
    normalized_headers = [h.strip().lower() for h in headers]
    for field, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            try:
                idx = normalized_headers.index(alias.lower())
                col_map[field] = idx
                break
            except ValueError:
                continue
    return col_map


def parse_rows(file_bytes: bytes, filename: str) -> list[dict[str, Any]]:
    if filename.lower().endswith(".csv"):
        return _parse_csv(file_bytes)
    return _parse_excel(file_bytes)


def _parse_excel(file_bytes: bytes) -> list[dict[str, Any]]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers = [str(c).strip() if c is not None else "" for c in next(rows_iter)]
    except StopIteration:
        return []
    col_map = parse_column_map(headers)
    if not col_map:
        return []
    result = []
    for row in rows_iter:
        record: dict[str, Any] = {}
        for field, idx in col_map.items():
            if idx < len(row) and row[idx] is not None:
                record[field] = str(row[idx]).strip()
        if record:
            result.append(record)
    return result


def _parse_csv(file_bytes: bytes) -> list[dict[str, Any]]:
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    try:
        headers = [h.strip() for h in next(reader)]
    except StopIteration:
        return []
    col_map = parse_column_map(headers)
    if not col_map:
        return []
    result = []
    for raw_row in reader:
        record: dict[str, Any] = {}
        for field, idx in col_map.items():
            if idx < len(raw_row) and raw_row[idx].strip():
                record[field] = raw_row[idx].strip()
        if record:
            result.append(record)
    return result


def aggregate_erp_data(rows: list[dict[str, Any]]) -> dict:
    brand_count: dict[str, int] = {}
    spec_count: dict[str, int] = {}
    total = len(rows)
    for row in rows:
        brand = (row.get("brand") or "").strip()
        if brand and brand not in ("未知", "—", "-", ""):
            brand_count[brand] = brand_count.get(brand, 0) + 1
        name = (row.get("item_name") or "").strip()
        for match in re.findall(r"\bM\d+\b", name, re.IGNORECASE):
            spec_count[match.upper()] = spec_count.get(match.upper(), 0) + 1
    top_brands = sorted(brand_count, key=brand_count.get, reverse=True)[:5]
    top_specs  = sorted(spec_count,  key=spec_count.get,  reverse=True)[:5]
    return {
        "top_brands": top_brands,
        "top_categories": [],
        "top_specs": top_specs,
        "total_records": total,
    }
