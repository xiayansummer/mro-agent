from fastapi import APIRouter, Depends

from app.routers.auth import require_user_id
from app.services.competitor_search import search_ehsy

router = APIRouter()


@router.get("/competitor/search")
async def competitor_search(
    q: str,
    limit: int = 5,
    user_id: str = Depends(require_user_id),
):
    results = await search_ehsy(q, limit=max(1, min(limit, 10)))
    return {"source": "ehsy", "query": q, "results": results}
