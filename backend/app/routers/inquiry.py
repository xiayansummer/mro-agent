"""
批量询价路由
POST /api/inquiry/upload  — 上传 Excel/CSV，批量匹配 SKU，返回结构化结果
GET  /api/inquiry/template — 下载询价模板
"""
import asyncio
import io
import csv
import os
from typing import Optional

import openpyxl
import xlrd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.db.mysql import AsyncSessionLocal
from app.services.sku_search import search_skus, relaxed_search

router = APIRouter()

MAX_ROWS = 200
CONCURRENCY = 8  # max parallel DB queries

# ── Excel / CSV parsing ───────────────────────────────────────────────────────

HEADER_ALIASES = {
    "需求品名": ["需求品名", "品名", "产品名称", "名称", "product"],
    "需求品牌": ["需求品牌", "品牌", "brand"],
    "需求型号": ["需求型号", "型号", "规格", "spec", "model"],
    "采购数量": ["采购数量", "数量", "qty", "quantity"],
}


def normalize_header(h: str) -> Optional[str]:
    h = h.strip().lower().replace(" ", "")
    for canonical, aliases in HEADER_ALIASES.items():
        if any(h == a.lower().replace(" ", "") for a in aliases):
            return canonical
    return None


def find_header_row(rows: list[list[str]]) -> tuple[Optional[dict], int]:
    """Return (col_map, header_row_index). col_map: canonical_name → col_index."""
    for ri, row in enumerate(rows):
        col_map = {}
        for ci, cell in enumerate(row):
            canon = normalize_header(cell)
            if canon:
                col_map[canon] = ci
        if "需求品名" in col_map or "需求型号" in col_map:
            return col_map, ri
    return None, -1


def parse_rows_from_sheet(raw_rows: list[list[str]]) -> list[dict]:
    col_map, header_idx = find_header_row(raw_rows)
    if col_map is None:
        return []

    results = []
    for row in raw_rows[header_idx + 1:]:
        if not any(c.strip() for c in row):
            continue
        entry = {}
        for canon, ci in col_map.items():
            entry[canon] = row[ci].strip() if ci < len(row) else ""
        # Skip fully empty rows
        if not entry.get("需求品名") and not entry.get("需求型号"):
            continue
        results.append(entry)
        if len(results) >= MAX_ROWS:
            break
    return results


def parse_excel_bytes(content: bytes, filename: str) -> list[dict]:
    name_lower = filename.lower()
    if name_lower.endswith(".xlsx"):
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        ws = wb.active
        raw = [[str(cell.value or "").strip() for cell in row] for row in ws.iter_rows()]
    elif name_lower.endswith(".xls"):
        wb = xlrd.open_workbook(file_contents=content)
        ws = wb.sheet_by_index(0)
        raw = [[str(ws.cell_value(r, c)).strip() for c in range(ws.ncols)] for r in range(ws.nrows)]
    elif name_lower.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        raw = [row for row in reader]
    else:
        raise HTTPException(status_code=400, detail="不支持的文件格式，请上传 .xlsx / .xls / .csv")
    return parse_rows_from_sheet(raw)


# ── Batch SKU search ──────────────────────────────────────────────────────────

def row_to_intent(row: dict) -> dict:
    品名 = row.get("需求品名", "")
    品牌 = row.get("需求品牌", "")
    型号 = row.get("需求型号", "")

    keywords = [kw.strip() for kw in 品名.split() if kw.strip()] if 品名 else []
    # Split 型号 by common delimiters to extract spec tokens
    import re
    spec_tokens = re.split(r"[\s,，×x*×/]+", 型号) if 型号 else []
    spec_keywords = [t for t in spec_tokens if t.strip()]

    return {
        "keywords": keywords,
        "brand": 品牌 or None,
        "spec_keywords": spec_keywords,
    }


async def search_one_row(db_session, row: dict, idx: int) -> dict:
    intent = row_to_intent(row)
    results = await search_skus(db_session, intent, limit=5)
    if not results:
        results = await relaxed_search(db_session, intent, limit=5)
    return {
        "index": idx + 1,
        "input": row,
        "matches": results,
        "match_count": len(results),
        "matched": len(results) > 0,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/inquiry/upload")
async def upload_inquiry(file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:  # 5MB limit
        raise HTTPException(status_code=400, detail="文件过大，请控制在 5MB 以内")

    rows = parse_excel_bytes(content, file.filename or "upload.xlsx")
    if not rows:
        raise HTTPException(
            status_code=422,
            detail="未能识别到有效数据行。请确认文件包含「需求品名」「需求型号」等列标题。"
        )

    # Batch search with bounded concurrency
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def search_with_sem(row, idx):
        async with semaphore:
            async with AsyncSessionLocal() as db:
                return await search_one_row(db, row, idx)

    results = await asyncio.gather(*[search_with_sem(row, i) for i, row in enumerate(rows)])

    matched_count = sum(1 for r in results if r["matched"])
    return {
        "total": len(results),
        "matched": matched_count,
        "filename": file.filename,
        "rows": results,
    }


@router.get("/inquiry/template")
async def download_template():
    template_path = os.path.join(os.path.dirname(__file__), "..", "..", "static", "询价选型模板.xls")
    template_path = os.path.abspath(template_path)
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="模板文件不存在")
    return FileResponse(
        template_path,
        media_type="application/vnd.ms-excel",
        filename="询价选型模板.xls",
    )
