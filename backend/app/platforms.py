"""平台注册表:平台 id / 中文名 / NL 别名 / 采集方式 的单一真源。

加新平台只在这里加一条数据;refine 的过滤指令、默认列表、扩展 vs 服务端路由、
前端文案(经 label map)全部从此派生,不再散落硬编码。
"""
import re

PLATFORM_REGISTRY: dict[str, dict] = {
    "jd":   {"cn": "京东工业品", "aliases": ["京东工业品", "京东", "jd"],            "collector": "extension"},
    "zkh":  {"cn": "震坤行",     "aliases": ["震坤行", "zkh"],                       "collector": "extension"},
    "ehsy": {"cn": "西域",       "aliases": ["西域", "ehsy"],                        "collector": "server"},
    "1688": {"cn": "阿里巴巴1688", "aliases": ["1688", "阿里巴巴", "阿里", "alibaba"], "collector": "extension"},
}

DEFAULT_PLATFORMS: list[str] = list(PLATFORM_REGISTRY)


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
