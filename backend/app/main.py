import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.chat import router as chat_router
from app.routers.competitor import router as competitor_router
from app.routers.feedback import router as feedback_router
from app.routers.inquiry import router as inquiry_router
from app.routers.profile import router as profile_router
from app.services.memory_service import memory_service

logger = logging.getLogger(__name__)

app = FastAPI(title="MRO AI Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")
app.include_router(competitor_router, prefix="/api")
app.include_router(feedback_router, prefix="/api")
app.include_router(inquiry_router, prefix="/api")
app.include_router(profile_router, prefix="/api")


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
