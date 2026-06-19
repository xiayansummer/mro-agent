# backend/app/services/ehsy_comparison_source.py
"""西域(ehsy)比价源适配器:把 search_ehsy 的原始结果映射成 ExternalOffer dict。

纯映射,不排序(排序在 start_draft 注入处用 rank_external_offers 做,与 jd/zkh 写入路径对称)。
出错优雅降级返回 []。
"""
import hashlib
import logging
from typing import Optional

from app.services.competitor_search import search_ehsy

logger = logging.getLogger(__name__)

_EHSY_SEARCH_FALLBACK = "https://www.ehsy.com/"


def _to_external_offer(p: dict, raw_rank: int) -> Optional[dict]:
    name = (p.get("name") or "").strip()
    if not name:
        return None
    sku = p.get("sku")
    raw_price = p.get("price")
    try:
        price_value = float(raw_price) if raw_price not in (None, "") else None
    except (ValueError, TypeError):
        price_value = None
    unit = p.get("unit")
    price_text = None
    if raw_price not in (None, ""):
        price_text = f"¥{raw_price}/{unit}" if unit else f"¥{raw_price}"
    offer_id = f"ehsy-{sku}" if sku else f"ehsy-{hashlib.md5(name.encode()).hexdigest()[:12]}"
    return {
        "id": offer_id,
        "platform": "ehsy",
        "title": name[:100],
        "brand": p.get("brand"),
        "priceText": price_text,
        "priceValue": price_value,
        "unitText": unit,
        "unitComparable": False,
        "deliveryText": p.get("delivery"),
        "productUrl": p.get("url") or _EHSY_SEARCH_FALLBACK,
        "platformSku": str(sku) if sku else None,
        "rawRank": raw_rank,
    }


async def fetch_ehsy_offers(search_term: str, limit: int = 8) -> list[dict]:
    """抓西域并映射成未排序 ExternalOffer dict;任何异常→[](降级)。"""
    try:
        raw = await search_ehsy(search_term, limit=limit)
    except Exception:
        logger.warning("ehsy fetch failed for %r", search_term, exc_info=True)
        return []
    offers = []
    for i, p in enumerate(raw):
        o = _to_external_offer(p, i)
        if o:
            offers.append(o)
    return offers
