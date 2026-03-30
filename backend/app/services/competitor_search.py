"""
Competitor price search — 西域 (ehsy.com)

Fetches search results from https://www.ehsy.com/search?k=<query>
and parses product name, price, SKU, and URL.
No authentication required; product data is in static HTML.
"""

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

EHSY_SEARCH_URL = "https://www.ehsy.com/search"
EHSY_BASE_URL = "https://www.ehsy.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


async def search_ehsy(query: str, limit: int = 5) -> list[dict]:
    """
    Search 西域 (ehsy.com) for a product and return structured results.

    Returns list of dicts with keys:
      name, price, unit, sku, url, delivery
    """
    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=True,
        ) as client:
            resp = await client.get(EHSY_SEARCH_URL, params={"k": query})
            resp.raise_for_status()
            html = resp.text

        return _parse_results(html, limit)

    except httpx.TimeoutException:
        logger.warning(f"ehsy search timeout for query: {query}")
        return []
    except Exception as e:
        logger.error(f"ehsy search error: {e}")
        return []


def _parse_results(html: str, limit: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Product cards are in <div class="product"> or similar containers
    # Try multiple selectors to be resilient to layout changes
    cards = (
        soup.select("div.product")
        or soup.select("li.product-item")
        or soup.select("[class*='product-card']")
    )

    for card in cards[:limit]:
        item = _parse_card(card)
        if item:
            results.append(item)

    # Fallback: try table rows if cards not found
    if not results:
        results = _parse_table_fallback(soup, limit)

    return results


def _parse_card(card) -> Optional[dict]:
    """Extract product info from a single product card element."""
    try:
        # SKU from data-text attribute on div.product
        sku = card.get("data-text") or None

        # Product name — from div.p-name a[title] (most reliable)
        name = None
        name_tag = card.select_one("div.p-name a[title]")
        if name_tag:
            name = name_tag.get("title", "").strip() or name_tag.get_text(strip=True)
        if not name:
            # Fallback: title attr on any product link
            for a in card.find_all("a", href=re.compile(r"/product-[A-Z0-9]+")):
                t = a.get("title", "").strip() or a.get_text(strip=True)
                if 5 < len(t) < 150:
                    name = t
                    break

        if not name:
            return None

        # Product URL
        url = None
        link_tag = card.select_one("a[href*='/product-']")
        if link_tag:
            href = link_tag.get("href", "")
            url = href if href.startswith("http") else EHSY_BASE_URL + href
            if not sku:
                m = re.search(r"/product-([A-Z0-9]+)", href)
                if m:
                    sku = m.group(1)

        # Price — div.price .yen is most reliable
        price = None
        price_tag = card.select_one("div.price .yen, div.price .now_money .yen")
        if price_tag:
            price_text = price_tag.get_text(strip=True).replace("¥", "").replace(",", "").strip()
            if re.match(r"[\d.]+", price_text):
                price = price_text
        if not price:
            m = re.search(r"¥\s*([\d,]+\.?\d*)", card.get_text())
            if m:
                price = m.group(1).replace(",", "")

        # Unit from product name (售卖规格: XX个/包)
        unit = None
        unit_match = re.search(r"售卖规格[：:]\s*\d+\s*(个|包|盒|套|件|条|卷|片|袋|瓶|桶|箱|只|副|对)", name)
        if not unit_match:
            unit_match = re.search(r"/(包|个|盒|套|件|条|卷|片|袋|瓶|桶|箱|只|副|对)", card.get_text())
        if unit_match:
            unit = unit_match.group(1)

        # Brand from .product-parameter li.high-light
        brand = None
        brand_tag = card.select_one(".product-parameter li.high-light")
        if brand_tag:
            brand = brand_tag.get_text(strip=True)

        # Delivery
        delivery = None
        stock_tag = card.select_one("i[class*='today'], i[class*='product-text']")
        if stock_tag:
            delivery = stock_tag.get_text(strip=True)

        return {
            "name": name[:100],
            "brand": brand,
            "price": price,
            "unit": unit,
            "sku": sku,
            "url": url,
            "delivery": delivery,
            "source": "西域",
        }

    except Exception as e:
        logger.debug(f"Card parse error: {e}")
        return None


def _parse_table_fallback(soup: BeautifulSoup, limit: int) -> list[dict]:
    """
    Fallback parser: scan all text for price patterns near product names.
    Used when card-based selectors don't match the page layout.
    """
    results = []
    # Find all product links pointing to /product-XXXXX
    for a in soup.find_all("a", href=re.compile(r"/product-[A-Z0-9]+")):
        if len(results) >= limit:
            break

        name = a.get_text(strip=True)
        if not (5 < len(name) < 120):
            continue

        href = a.get("href", "")
        url = href if href.startswith("http") else EHSY_BASE_URL + href
        sku_match = re.search(r"/product-([A-Z0-9]+)", href)
        sku = sku_match.group(1) if sku_match else None

        # Look for price in nearby text (parent or sibling elements)
        parent = a.find_parent()
        context = parent.get_text() if parent else ""
        price = None
        price_match = re.search(r"¥\s*([\d,]+\.?\d*)", context)
        if price_match:
            price = price_match.group(1).replace(",", "")

        results.append({
            "name": name[:80],
            "price": price,
            "unit": None,
            "sku": sku,
            "url": url,
            "delivery": None,
            "source": "西域",
        })

    return results
