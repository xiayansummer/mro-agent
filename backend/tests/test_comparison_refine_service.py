from app.services.comparison_refine_service import parse_refinement, build_label


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


# —— I-1: 品牌 token 收紧 —— 只能捕获品牌本身,不能把后续商品名词吞入 token
def test_brand_keep_tight_cjk():
    """只看霍尼韦尔 → 品牌 token 精确为 '霍尼韦尔'"""
    cmd = parse_refinement("只看霍尼韦尔")
    assert cmd is not None
    assert cmd["brandKeep"] == "霍尼韦尔"


def test_brand_keep_tight_mixed():
    """只看3M → 品牌 token 精确为 '3M'(含字母数字的品牌仍可捕获)"""
    cmd = parse_refinement("只看3M")
    assert cmd is not None
    assert cmd["brandKeep"] == "3M"


def test_brand_keep_with_product_noun_returns_none():
    """只看霍尼韦尔品牌的手套 → 品牌=霍尼韦尔,残留'手套'(CJK 2字) → 保守 None"""
    assert parse_refinement("只看霍尼韦尔品牌的手套") is None


def test_brand_drop_tight_cjk():
    """排除霍尼韦尔 → brandDrop 精确为 '霍尼韦尔'"""
    cmd = parse_refinement("排除霍尼韦尔")
    assert cmd is not None
    assert cmd["brandDrop"] == "霍尼韦尔"


def test_brand_drop_with_product_noun_returns_none():
    """排除霍尼韦尔的产品 → 品牌=霍尼韦尔,残留'产品' → 保守 None"""
    assert parse_refinement("排除霍尼韦尔的产品") is None


# —— I-2: 标签价格整数化 —— 50.0 元应展示为 '50元' 不带 .0
def test_label_price_integer_format():
    """priceMax=50.0 的命令,标签应包含 '50元' 而非 '50.0元'"""
    cmd = parse_refinement("50元以下的")
    assert cmd is not None
    assert "50元" in cmd["label"]
    assert "50.0元" not in cmd["label"]


def test_build_label_price_integer_direct():
    """直接测试 build_label 对整数值价格的格式化"""
    label = build_label({"priceMax": 50.0, "priceMin": None,
                         "platform": None, "brandKeep": None, "brandDrop": None,
                         "sort": None, "limit": None})
    assert "50元" in label
    assert "50.0" not in label
