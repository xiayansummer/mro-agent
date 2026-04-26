"""
用户画像路由
POST /api/profile/import  — 上传采购历史 Excel/CSV，写入 #preference memo
"""
import logging

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException

from app.routers.auth import require_user_id
from app.services.erp_importer import parse_rows, aggregate_erp_data
from app.services.memory_service import memory_service, _uid_tag

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/profile/import")
async def import_erp_history(
    file: UploadFile = File(...),
    user_id: str = Depends(require_user_id),
):
    effective_uid = user_id
    filename = file.filename or ""
    if not any(filename.lower().endswith(ext) for ext in (".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls / .csv 格式")

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件大小不能超过 10 MB")

    rows = parse_rows(file_bytes, filename)
    if not rows:
        raise HTTPException(status_code=422, detail="无法识别文件列名，请确保含产品编码或产品名称列")

    summary = aggregate_erp_data(rows)
    logger.info(
        f"ERP import: user={effective_uid[:8]}, rows={summary['total_records']}, "
        f"brands={summary['top_brands']}"
    )

    uid_tag = _uid_tag(effective_uid)
    content = (
        f"## 用户偏好摘要（ERP导入）\n"
        f"偏好品牌：{', '.join(summary['top_brands'])  if summary['top_brands']  else '暂无'}\n"
        f"常用规格：{', '.join(summary['top_specs'])   if summary['top_specs']   else '暂无'}\n"
        f"导入记录数：{summary['total_records']}\n\n"
        f"#{uid_tag} #preference #erp-import"
    )

    old = await memory_service.list_memos(uid_tag, extra_tag="preference", limit=10)
    for memo in old:
        await memory_service._delete_memo(memo.get("name", ""))

    await memory_service.create_memo(content)

    return {
        "status": "ok",
        "total_records": summary["total_records"],
        "top_brands": summary["top_brands"],
        "top_specs": summary["top_specs"],
        "message": f"已导入 {summary['total_records']} 条采购记录，偏好摘要已更新",
    }
