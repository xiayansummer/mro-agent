"""
批量询价路由
POST /api/inquiry/upload      — 上传 Excel/CSV，解析为结构化行(不做库内匹配)
POST /api/inquiry/compare-row — 对一行需求触发三平台外部比价(京东/震坤行/西域)
GET  /api/inquiry/template    — 下载询价模板
"""
import io
import csv
import os
import uuid
from typing import Optional

import openpyxl
import xlrd
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.routers.auth import require_user_id
from app.services.comparison_structure import build_comparison_structure
from app.services.comparison_draft_service import create_draft, _require_db_user_id
from app.services.comparison_task_service import start_draft

router = APIRouter()

MAX_ROWS = 200

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
    if not name_lower.endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="不支持的文件格式，请上传 .xlsx / .xls / .csv")
    try:
        if name_lower.endswith(".xlsx"):
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            ws = wb.active
            raw = [[str(cell.value or "").strip() for cell in row] for row in ws.iter_rows()]
        elif name_lower.endswith(".xls"):
            wb = xlrd.open_workbook(file_contents=content)
            ws = wb.sheet_by_index(0)
            raw = [[str(ws.cell_value(r, c)).strip() for c in range(ws.ncols)] for r in range(ws.nrows)]
        else:  # .csv
            text = content.decode("utf-8-sig", errors="replace")
            reader = csv.reader(io.StringIO(text))
            raw = [row for row in reader]
    except Exception as e:
        # 后缀合法但内容损坏/非真实表格 → 400 而非未捕获的 500
        raise HTTPException(status_code=400, detail="文件无法解析，请确认是有效的 .xlsx / .xls / .csv 文件") from e
    return parse_rows_from_sheet(raw)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/inquiry/upload")
async def upload_inquiry(
    file: UploadFile = File(...),
    user_id: str = Depends(require_user_id),  # noqa: ARG001 — auth gate, value not used
):
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:  # 5MB limit
        raise HTTPException(status_code=400, detail="文件过大，请控制在 5MB 以内")

    rows = parse_excel_bytes(content, file.filename or "upload.xlsx")
    if not rows:
        raise HTTPException(
            status_code=422,
            detail="未能识别到有效数据行。请确认文件包含「需求品名」「需求型号」等列标题。"
        )

    # 只解析为结构化行,不做库内匹配;外部比价由前端逐行调 /inquiry/compare-row
    return {
        "total": len(rows),
        "filename": file.filename,
        "rows": [{"index": i + 1, "input": row} for i, row in enumerate(rows)],
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


@router.post("/inquiry/compare-row")
async def compare_inquiry_row(
    row: dict = Body(...),
    user_id: str = Depends(require_user_id),
):
    """对询价表的一行需求,按需触发一次三平台外部比价(京东/震坤行/西域)。

    复用现有比价流程:拼 query → build_comparison_structure(空上下文+不追问)
    → create_draft(inquiry- 前缀 session,不写 t_chat_message、不污染对话历史)
    → start_draft。返回 taskId,前端轮询 GET /api/comparison/tasks/{taskId}。
    """
    品名 = (row.get("需求品名") or "").strip()
    品牌 = (row.get("需求品牌") or "").strip()
    型号 = (row.get("需求型号") or "").strip()
    query = " ".join(p for p in [品牌, 品名, 型号] if p)
    if not query:
        return {"ok": False, "guidance": "该行无品名,无法外部比价"}

    result = await build_comparison_structure(
        query, conversation_context=[], memory_context="", skip_clarification=True
    )
    if not result.shouldCreateDraft or not result.structure:
        return {"ok": False, "guidance": result.guidance or "该行需求过于宽泛,无法外部比价,请补充品名/型号"}

    db_user_id = _require_db_user_id(user_id)
    session_id = f"inquiry-{db_user_id}-{uuid.uuid4().hex}"
    draft = await create_draft(
        user_id=user_id, session_id=session_id, raw_query=query, structure=result.structure
    )
    task = await start_draft(draft["id"], user_id)
    if not task:
        return {"ok": False, "guidance": "比价任务创建失败,请重试"}
    return {"ok": True, "taskId": task["id"], "draftId": draft["id"]}
