"""平台注册表:平台 id / 中文名 / NL 别名 / 采集方式 / 是否默认 的单一真源。

加新平台只在这里加一条数据;refine 的过滤指令、默认列表、扩展 vs 服务端路由、
前端文案(经 label map)全部从此派生,不再散落硬编码。

`default` 是灰度开关:后端始终"认识"注册表里的所有平台(Literal 校验、别名过滤、
中文名、collector 路由都覆盖全量),但只有 default=True 的平台进 DEFAULT_PLATFORMS、
成为比价默认触发的平台。新平台上线可先 default=False(仅在用户显式勾选时触发,现网
零影响),等采集端(如扩展)铺开后再翻 True 即成默认平台。
"""
import re

PLATFORM_REGISTRY: dict[str, dict] = {
    "jd":   {"cn": "京东工业品", "aliases": ["京东工业品", "京东", "jd"],            "collector": "extension", "default": True},
    "zkh":  {"cn": "震坤行",     "aliases": ["震坤行", "zkh"],                       "collector": "extension", "default": True},
    "ehsy": {"cn": "西域",       "aliases": ["西域", "ehsy"],                        "collector": "server",    "default": True},
    # 1688:2026-07-13 扩展 1688 采集端到端校准通过(真机跑通 搜索→GBK→解析→回传→排序),
    # 翻 default=True 正式进默认——比价默认四平台(jd/zkh/ehsy/1688)。
    "1688": {"cn": "阿里巴巴1688", "aliases": ["1688", "阿里巴巴", "阿里", "alibaba"], "collector": "extension", "default": True},
}

# 全量已注册平台:build_search_terms 为所有平台预生成检索词(都复用同一批降级词),
# 使"用户显式勾选的非默认平台"(如灰度期的 1688)也有词可用;是否真正触发比价由
# 选中平台(默认取 DEFAULT_PLATFORMS)决定,未选中的平台其词只是存着不用,现网零影响。
ALL_PLATFORMS: list[str] = list(PLATFORM_REGISTRY)

# 默认触发比价的平台(default=True 的子集)。灰度期 1688 不在其中。
DEFAULT_PLATFORMS: list[str] = [pid for pid, meta in PLATFORM_REGISTRY.items() if meta["default"]]


def alias_to_id() -> dict[str, str]:
    return {alias: pid for pid, meta in PLATFORM_REGISTRY.items() for alias in meta["aliases"]}


def id_to_cn() -> dict[str, str]:
    return {pid: meta["cn"] for pid, meta in PLATFORM_REGISTRY.items()}


def aliases_by_length_desc() -> list[str]:
    aliases = [a for meta in PLATFORM_REGISTRY.values() for a in meta["aliases"]]
    return sorted(aliases, key=len, reverse=True)


def platform_alias_pattern() -> str:
    return "|".join(re.escape(a) for a in aliases_by_length_desc())


def cn_names() -> set[str]:
    return {meta["cn"] for meta in PLATFORM_REGISTRY.values()}


def extension_platform_ids() -> set[str]:
    return {pid for pid, meta in PLATFORM_REGISTRY.items() if meta["collector"] == "extension"}
