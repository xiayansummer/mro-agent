import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.chat_history import router as chat_history_router
from app.routers.comparison import router as comparison_router
from app.routers.competitor import router as competitor_router
from app.routers.extension import router as extension_router
from app.routers.feedback import router as feedback_router
from app.routers.inquiry import router as inquiry_router
from app.routers.profile import router as profile_router
from app.config import settings
from app.services.memory_service import memory_service

logger = logging.getLogger(__name__)

app = FastAPI(title="MRO AI Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(chat_history_router, prefix="/api")
app.include_router(comparison_router, prefix="/api")
app.include_router(competitor_router, prefix="/api")
app.include_router(extension_router, prefix="/api")
app.include_router(feedback_router, prefix="/api")
app.include_router(inquiry_router, prefix="/api")
app.include_router(profile_router, prefix="/api")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底未捕获异常:保证记日志(可观测)+ 统一错误信封;生产环境隐藏内部细节,
    避免各 router 未捕获异常直接落到框架默认 500、或泄露堆栈/实现细节。
    HTTPException 仍由 FastAPI 默认处理器处理,不受此影响。"""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    detail = "服务器内部错误，请稍后重试" if settings.is_production else f"{type(exc).__name__}: {exc}"
    return JSONResponse(status_code=500, content={"detail": detail})


@app.on_event("startup")
async def startup():
    if await memory_service.is_healthy():
        logger.info("Memos memory service: reachable")
        try:
            await memory_service._get_token()
            logger.info("Memos memory service: authenticated OK")
        except Exception as e:
            logger.warning(f"Memos memory service: auth failed — {e}")
    else:
        logger.warning("Memos memory service: unreachable (memory features disabled)")


@app.get("/health")
async def health():
    memos_ok = await memory_service.is_healthy()
    return {"status": "ok", "memory": "ok" if memos_ok else "unavailable"}
