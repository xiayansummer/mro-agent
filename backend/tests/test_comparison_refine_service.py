from app.services.comparison_refine_service import parse_refinement


def test_sort_asc_with_topn_chinese_numeral():
    cmd = parse_refinement("能不能选出价格最低的五个")
    assert cmd is not None
    assert cmd["sort"] == "asc"
    assert cmd["limit"] == 5
    assert cmd["platform"] is None and cmd["brandKeep"] is None


def test_sort_asc_arabic_topn():
    cmd = parse_refinement("最便宜的3个")
    assert cmd["sort"] == "asc" and cmd["limit"] == 3


def test_sort_desc():
    cmd = parse_refinement("按价格从高到低排序")
    assert cmd["sort"] == "desc" and cmd["limit"] is None


def test_brand_keep():
    cmd = parse_refinement("只看3M")
    assert cmd["brandKeep"] == "3M" and cmd["brandDrop"] is None


def test_brand_drop():
    cmd = parse_refinement("排除霍尼韦尔")
    assert cmd["brandDrop"] == "霍尼韦尔"


def test_platform_drop_negation():
    cmd = parse_refinement("去掉震坤行的")   # 去掉 zkh = 只看 jd(仅两平台)
    assert cmd["platform"] == "jd"


def test_price_max():
    cmd = parse_refinement("50元以下的")
    assert cmd["priceMax"] == 50.0 and cmd["priceMin"] is None


def test_price_range():
    cmd = parse_refinement("20到50元之间")
    assert cmd["priceMin"] == 20.0 and cmd["priceMax"] == 50.0


def test_platform_filter():
    cmd = parse_refinement("只看京东工业品")
    assert cmd["platform"] == "jd"


def test_composition_platform_sort_limit():
    cmd = parse_refinement("京东上最便宜的3个")
    assert cmd["platform"] == "jd" and cmd["sort"] == "asc" and cmd["limit"] == 3


def test_label_present():
    cmd = parse_refinement("最便宜的5个")
    assert isinstance(cmd["label"], str) and cmd["label"]


# —— 否定样本:必须回落新品路径(None) ——
def test_new_product_plain_returns_none():
    assert parse_refinement("防尘口罩") is None


def test_new_product_with_brand_and_spec_returns_none():
    assert parse_refinement("美和2吨手拉葫芦") is None


def test_operator_plus_product_noun_returns_none():
    # "最便宜的电钻":含新商品名词残留 → 不劫持,回落新品
    assert parse_refinement("最便宜的电钻") is None


def test_empty_and_greeting_returns_none():
    assert parse_refinement("") is None
    assert parse_refinement("你好") is None
