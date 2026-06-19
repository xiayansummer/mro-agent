# backend/tests/test_ehsy_comparison_source.py
import pytest
from app.services import ehsy_comparison_source as mod
from app.services.ehsy_comparison_source import _to_external_offer, fetch_ehsy_offers


def _raw():
    return {"name": "3M 防尘口罩，9501V+ 售卖规格：1只", "brand": "3M",
            "price": "4", "unit": "只", "sku": "CMN420",
            "url": "https://www.ehsy.com/product-CMN420", "delivery": "7个工作日", "source": "西域"}


def test_map_normal():
    o = _to_external_offer(_raw(), 0)
    assert o["platform"] == "ehsy"
    assert o["id"] == "ehsy-CMN420"
    assert o["platformSku"] == "CMN420"
    assert o["priceValue"] == 4.0
    assert o["unitComparable"] is False
    assert o["unitText"] == "只"
    assert o["deliveryText"] == "7个工作日"
    assert o["title"].startswith("3M")
    assert "¥4" in o["priceText"]


def test_map_missing_price():
    r = _raw(); r["price"] = None
    o = _to_external_offer(r, 1)
    assert o["priceValue"] is None
    assert o["priceText"] is None


def test_map_missing_sku_stable_id_and_url_fallback():
    r = _raw(); r["sku"] = None; r["url"] = None
    o1 = _to_external_offer(r, 0)
    o2 = _to_external_offer(r, 0)
    assert o1["id"] == o2["id"]           # 稳定(md5,非进程内 hash)
    assert o1["id"].startswith("ehsy-")
    assert o1["platformSku"] is None
    assert o1["productUrl"].startswith("https://www.ehsy.com")


def test_map_empty_name_dropped():
    r = _raw(); r["name"] = ""
    assert _to_external_offer(r, 0) is None


@pytest.mark.asyncio
async def test_fetch_maps_and_indexes(monkeypatch):
    async def fake_search(q, limit=8):
        return [_raw(), {**_raw(), "name": "安可护 口罩", "sku": "SFW179"}]
    monkeypatch.setattr(mod, "search_ehsy", fake_search)
    out = await fetch_ehsy_offers("防尘口罩")
    assert [o["rawRank"] for o in out] == [0, 1]
    assert {o["platformSku"] for o in out} == {"CMN420", "SFW179"}


@pytest.mark.asyncio
async def test_fetch_degrades_on_error(monkeypatch):
    async def boom(q, limit=8):
        raise RuntimeError("api down")
    monkeypatch.setattr(mod, "search_ehsy", boom)
    assert await fetch_ehsy_offers("x") == []
