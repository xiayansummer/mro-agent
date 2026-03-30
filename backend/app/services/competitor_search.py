"""
Competitor price search — 西域 (ehsy.com) via mobile app API

Calls the m2.ehsy.com JSON API used by the ehsy mobile app.
No HTML scraping — returns structured product data directly.
"""

import base64
import hashlib
import json
import logging
import time
from typing import Optional

import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

logger = logging.getLogger(__name__)

EHSY_API_BASE = "https://m2.ehsy.com/"
EHSY_SEARCH_PATH = "pb/product/search/filter"
EHSY_PRODUCT_URL = "https://www.ehsy.com/product-{sku}"

# AES key material (from app JS bundle)
_AES_GLOBAL_SECRET = "GvcaHhBsKa9kkHmf"


def _md5hex(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


def _ehsy_verify() -> str:
    """
    Generate the ehsy-verify auth header required by the app API.
    Algorithm reversed from app JS bundle (module eec8 / aes_gobal function).
    """
    timestamp = str(int(time.time()))
    chars = list(_md5hex(timestamp))
    chars[2] = "e"
    chars[6] = "h"
    chars[12] = "6"
    chars[25] = "b"
    plaintext = "".join(chars) + timestamp
    key_bytes = bytes.fromhex(_md5hex(_AES_GLOBAL_SECRET))
    cipher = AES.new(key_bytes, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(plaintext.encode("utf-8"), 16))
    return base64.b64encode(encrypted).decode()


HEADERS = {
    "User-Agent": "ehsy/4.7.19 (iPhone; iOS 17.0; Scale/3.00)",
    "Accept": "application/json",
    "Accept-Language": "zh-Hans-CN;q=1",
    "Content-Type": "application/x-www-form-urlencoded",
}


async def search_ehsy(query: str, limit: int = 5) -> list[dict]:
    """
    Search 西域 (ehsy.com) via the mobile app API.

    Returns list of dicts with keys:
      name, price, unit, sku, url, brand, delivery, source
    """
    try:
        search_body = json.dumps({"keywords": query}, ensure_ascii=False)
        form_data = {
            "search": search_body,
            "sortType": "",
            "start": "0",
            "rows": str(min(limit * 2, 20)),  # fetch extra, filter down
            "cityId": "",
            "fuzzy": "false",
            "unchange": "false",
            "token": "",
            "createFrom": "",
        }
        headers = {**HEADERS, "ehsy-verify": _ehsy_verify()}

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=5.0),
        ) as client:
            resp = await client.post(
                EHSY_API_BASE + EHSY_SEARCH_PATH,
                data=form_data,
                headers=headers,
            )
            resp.raise_for_status()
            body = resp.json()

        if str(body.get("mark")) != "0":
            logger.warning(f"ehsy API non-zero mark: {body.get('mark')} {body.get('message')}")
            return []

        products = body.get("data", {}).get("queryPage", {}).get("data", [])
        return _parse_products(products, limit)

    except httpx.TimeoutException:
        logger.warning(f"ehsy API timeout for query: {query}")
        return []
    except Exception as e:
        logger.error(f"ehsy API error: {e}")
        return []


def _parse_products(products: list, limit: int) -> list[dict]:
    results = []
    for p in products[:limit]:
        item = _parse_product(p)
        if item:
            results.append(item)
    return results


def _parse_product(p: dict) -> Optional[dict]:
    try:
        name = p.get("productName", "")
        if not name:
            return None

        sku_code = p.get("skuCode") or p.get("platFormSku") or ""
        url = EHSY_PRODUCT_URL.format(sku=sku_code) if sku_code else None

        # Price: use salePrice (after-tax price shown to user), fall back to marketPrice
        price = p.get("salePrice") or p.get("marketPrice") or None
        unit = p.get("saleUom") or None
        brand = p.get("brandName") or None

        # Delivery: realDeliveryTime is in working days
        delivery = None
        delivery_days = p.get("realDeliveryTime")
        if delivery_days is not None:
            delivery = f"{delivery_days}个工作日"

        return {
            "name": name[:100],
            "brand": brand,
            "price": str(price) if price else None,
            "unit": unit,
            "sku": str(sku_code) if sku_code else None,
            "url": url,
            "delivery": delivery,
            "source": "西域",
        }
    except Exception as e:
        logger.debug(f"Product parse error: {e}")
        return None
