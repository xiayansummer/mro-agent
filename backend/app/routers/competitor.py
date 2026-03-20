from fastapi import APIRouter
from pydantic import BaseModel
from app.services.competitor_search import search_ehsy

router = APIRouter()


class CompetitorSearchRequest(BaseModel):
    query: str
    limit: int = 5


@router.get("/competitor/search")
async def competitor_search(q: str, limit: int = 5):
    results = await search_ehsy(q, limit=min(limit, 10))
    return {"source": "ehsy", "query": q, "results": results}
