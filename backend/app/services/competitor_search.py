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
        # Product name — find the most prominent link/text
        name = None
        name_tag = card.select_one("a.product-name, a[href*='/product-'], .product-title a")
        if name_tag:
            name = name_tag.get_text(strip=True)
        if not name:
            # Fallback: first <a> with reasonable text length
            for a in card.find_all("a", href=True):
                text = a.get_text(strip=True)
                if 5 < len(text) < 120:
                    name = text
                    break

        if not name:
            return None

        # Product URL
        url = None
        link_tag = card.select_one("a[href*='/product-']")
        if link_tag and link_tag.get("href"):
            href = link_tag["href"]
            url = href if href.startswith("http") else EHSY_BASE_URL + href

        # Price — look for ¥ pattern
        price = None
        price_text = card.get_text()
        price_match = re.search(r"西域价[：:]\s*¥\s*([\d,]+\.?\d*)", price_text)
        if not price_match:
            price_match = re.search(r"¥\s*([\d,]+\.?\d*)", price_text)
        if price_match:
            price = price_match.group(1).replace(",", "")

        # Unit (包/个/盒/套)
        unit = None
        unit_match = re.search(r"/(包|个|盒|套|件|条|卷|片|袋|瓶|桶)", price_text)
        if unit_match:
            unit = unit_match.group(1)

        # 西域订货号 (SKU)
        sku = None
        sku_match = re.search(r"西域订货号[：:]\s*([A-Z0-9]+)", price_text)
        if sku_match:
            sku = sku_match.group(1)
        if not sku and url:
            # Extract from URL: /product-XXXXX
            url_match = re.search(r"/product-([A-Z0-9]+)", url)
            if url_match:
                sku = url_match.group(1)

        # Delivery estimate
        delivery = None
        delivery_match = re.search(r"预计出货[日期：:\s]*([\d\-~]+\s*个?工作日?)", price_text)
        if delivery_match:
            delivery = delivery_match.group(1).strip()

        return {
            "name": name[:80],
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
