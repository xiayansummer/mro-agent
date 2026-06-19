"""对话内"比价结果精炼":把对已有结果的指令解析成结构化操作,并在已采集 offers 上执行。

parse_refinement / apply_refinement 都是纯函数,无 IO,便于单测。
保守原则:只有明确命中精炼操作符、且去掉操作符后无新商品名词残留,才返回命令;
否则返回 None,由 handle_message 回落"新建比价"路径——绝不劫持新比价。
"""
import re
from typing import Optional

from app.services.comparison_ranker import text_matches_brand

_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

_ASC = ("最便宜", "价格最低", "最低价", "价格从低到高", "便宜的", "低价", "价低")
_DESC = ("最贵", "价格最高", "最高价", "价格从高到低", "贵的", "高价")
_PLATFORM = (("京东工业品", "jd"), ("京东", "jd"), ("jd", "jd"),
             ("震坤行", "zkh"), ("zkh", "zkh"))

# 去掉操作符后,残留里属于"命令/连接/数量"的词不算新商品名词
_STOP = ("能不能", "可不可以", "可以", "帮我", "帮", "请", "选出", "挑出", "挑", "给我",
         "只看", "只要", "要", "去掉", "排除", "不要", "除了", "前", "取", "留", "按",
         "排序", "排", "之间", "之内", "以内", "以下", "以上", "左右", "的", "个", "元",
         "块", "这些", "结果", "里", "中", "和", "与", "一下", "看看", "想", "我")

_NUM_RE = r"(\d+(?:\.\d+)?|[一两二三四五六七八九十]+)"


def _to_int(tok: str) -> Optional[int]:
    if tok.isdigit():
        return int(tok)
    if tok in _CN_NUM:
        return _CN_NUM[tok]
    # 简单两位中文(如 十五)不在 v1 范围;返回 None
    return None


def _to_float(tok: str) -> Optional[float]:
    try:
        return float(tok)
    except ValueError:
        n = _to_int(tok)
        return float(n) if n is not None else None


_PLAT_CN = {"jd": "京东工业品", "zkh": "震坤行"}


def _brand_text(offer: dict) -> str:
    return f"{offer.get('title') or ''} {offer.get('brand') or ''}"


def apply_refinement(offers: list[dict], cmd: dict) -> list[dict]:
    """在已采集 offers 上执行精炼操作:过滤 → 排序 → 取前N,纯函数无 IO。"""
    out = list(offers)
    if cmd.get("platform"):
        out = [o for o in out if o.get("platform") == cmd["platform"]]
    if cmd.get("brandKeep"):
        out = [o for o in out if text_matches_brand(_brand_text(o), cmd["brandKeep"])]
    if cmd.get("brandDrop"):
        out = [o for o in out if not text_matches_brand(_brand_text(o), cmd["brandDrop"])]
    if cmd.get("priceMax") is not None:
        out = [o for o in out if o.get("priceValue") is not None and o["priceValue"] <= cmd["priceMax"]]
    if cmd.get("priceMin") is not None:
        out = [o for o in out if o.get("priceValue") is not None and o["priceValue"] >= cmd["priceMin"]]
    if cmd.get("sort") in ("asc", "desc"):
        # 无价(None)统一排末尾;asc 升序、desc 降序
        big = float("inf")
        out.sort(key=lambda o: (o.get("priceValue") is None,
                                (o.get("priceValue") if o.get("priceValue") is not None else big)
                                * (1 if cmd["sort"] == "asc" else -1)))
    if cmd.get("limit"):
        out = out[: cmd["limit"]]
    return out


def build_label(cmd: dict) -> str:
    """从 cmd 生成人可读的操作标签。"""
    parts = []
    if cmd.get("platform"):
        parts.append(_PLAT_CN[cmd["platform"]])
    if cmd.get("brandKeep"):
        parts.append(f"只看{cmd['brandKeep']}")
    if cmd.get("brandDrop"):
        parts.append(f"去掉{cmd['brandDrop']}")
    if cmd.get("priceMin") is not None and cmd.get("priceMax") is not None:
        parts.append(f"{cmd['priceMin']:g}–{cmd['priceMax']:g}元")
    elif cmd.get("priceMax") is not None:
        parts.append(f"≤{cmd['priceMax']:g}元")
    elif cmd.get("priceMin") is not None:
        parts.append(f"≥{cmd['priceMin']:g}元")
    if cmd.get("sort") == "asc":
        parts.append("按价格最低" + (f"取前{cmd['limit']}" if cmd.get("limit") else "排序"))
    elif cmd.get("sort") == "desc":
        parts.append("按价格最高" + (f"取前{cmd['limit']}" if cmd.get("limit") else "排序"))
    elif cmd.get("limit"):
        parts.append(f"取前{cmd['limit']}")
    return "、".join(parts) or "筛选"


def parse_refinement(message: str) -> Optional[dict]:
    text = (message or "").strip()
    if not text:
        return None
    work = text
    cmd = {"platform": None, "brandKeep": None, "brandDrop": None,
           "priceMin": None, "priceMax": None, "sort": None, "limit": None, "label": ""}
    matched = False

    def consume(span: str):
        nonlocal work
        work = work.replace(span, " ", 1)

    # 平台(先判否定:"去掉/不要/排除 震坤行"=只看另一平台;仅两平台)
    _neg_plat = re.search(r"(去掉|不要|排除|除了)\s*(京东工业品|京东|震坤行)", work)
    if _neg_plat:
        cmd["platform"] = "zkh" if "京东" in _neg_plat.group(2) else "jd"
        consume(_neg_plat.group(0)); matched = True
    else:
        for kw, plat in _PLATFORM:
            if kw in work:
                cmd["platform"] = plat
                consume(kw)
                matched = True
                break

    # 价位:区间 / 上限 / 下限
    m = re.search(_NUM_RE + r"\s*[-到~至]\s*" + _NUM_RE + r"\s*元?", work)
    if m:
        a, b = _to_float(m.group(1)), _to_float(m.group(2))
        if a is not None and b is not None:
            cmd["priceMin"], cmd["priceMax"] = min(a, b), max(a, b)
            consume(m.group(0)); matched = True
    if cmd["priceMax"] is None:
        m = re.search(_NUM_RE + r"\s*元?\s*(以下|以内)|低于\s*" + _NUM_RE + r"|不超过\s*" + _NUM_RE, work)
        if m:
            tok = next((g for g in m.groups() if g), None)
            cmd["priceMax"] = _to_float(tok) if tok else None
            if cmd["priceMax"] is not None:
                consume(m.group(0)); matched = True
    if cmd["priceMin"] is None:
        m = re.search(_NUM_RE + r"\s*元?\s*以上|高于\s*" + _NUM_RE + r"|超过\s*" + _NUM_RE, work)
        if m:
            tok = next((g for g in m.groups() if g), None)
            cmd["priceMin"] = _to_float(tok) if tok else None
            if cmd["priceMin"] is not None:
                consume(m.group(0)); matched = True

    # 排序
    for kw in _ASC:
        if kw in work:
            cmd["sort"] = "asc"; consume(kw); matched = True; break
    if cmd["sort"] is None:
        for kw in _DESC:
            if kw in work:
                cmd["sort"] = "desc"; consume(kw); matched = True; break

    # 取前N: "前N(个)" 或 "N个"
    m = re.search(r"前\s*" + _NUM_RE + r"\s*个?|" + _NUM_RE + r"\s*个", work)
    if m:
        tok = next((g for g in m.groups() if g), None)
        n = _to_int(tok) if tok else None
        if n:
            cmd["limit"] = n; consume(m.group(0)); matched = True

    # 品牌:保留 / 剔除(平台已先消费,避免"只看京东"被当品牌)
    # 品牌 token 必须收紧:不允许跨过 的/品牌/标点/空白/行末,避免把商品名词吞入品牌
    if cmd["brandKeep"] is None:
        m = re.search(r"(只看|只要|要)\s*([^\s,，。的品]+?)(?:品牌|的|[,，。]|$)", work)
        if m and m.group(2) not in {"", "京东", "震坤行"}:
            cmd["brandKeep"] = m.group(2); consume(m.group(0)); matched = True
    m = re.search(r"(去掉|排除|不要|除了)\s*([^\s,，。的品]+?)(?:品牌|的|[,，。]|$)", work)
    if m and m.group(2):
        cmd["brandDrop"] = m.group(2); consume(m.group(0)); matched = True

    if not matched:
        return None

    # 保守残留检查:去掉操作符+品牌参数后,剩下若有"新商品名词"(≥2 连续 CJK 非停用词)→ None
    residue = work
    for w in _STOP:
        residue = residue.replace(w, " ")
    for b in (cmd["brandKeep"], cmd["brandDrop"]):
        if b:
            residue = residue.replace(b, " ")
    residue = re.sub(r"[0-9\.\-~到至,，。、!！?？:：\s]", "", residue)
    # 残留里若有连续 ≥2 个中文,视为新商品名词,放弃精炼(回落新品)
    if re.search(r"[一-鿿]{2,}", residue):
        return None

    cmd["label"] = build_label(cmd)
    return cmd
