from app import platforms


def test_registry_has_four_platforms_incl_1688():
    # 注册表始终覆盖全量 4 平台(Literal 校验/别名/中文名/collector 都据此),
    # 后端因此"认识"1688;是否默认触发由 default 开关另行控制(见下)。
    assert set(platforms.PLATFORM_REGISTRY) == {"jd", "zkh", "ehsy", "1688"}


def test_default_platforms_all_four_after_1688_rollout():
    # 2026-07-13 扩展 1688 端到端校准通过,default 翻 True → 比价默认四平台。
    # (default 开关架构保留,将来新平台仍可先 False 灰度、验证后翻 True。)
    assert platforms.DEFAULT_PLATFORMS == ["jd", "zkh", "ehsy", "1688"]
    assert all(platforms.PLATFORM_REGISTRY[p]["default"] for p in ("jd", "zkh", "ehsy", "1688"))


def test_alias_to_id_maps_all_aliases():
    m = platforms.alias_to_id()
    assert m["京东工业品"] == "jd" and m["京东"] == "jd" and m["jd"] == "jd"
    assert m["1688"] == "1688" and m["阿里巴巴"] == "1688" and m["阿里"] == "1688" and m["alibaba"] == "1688"


def test_aliases_ordered_longest_first():
    ordered = platforms.aliases_by_length_desc()
    assert ordered.index("京东工业品") < ordered.index("京东")  # 长别名先,避免子串误匹配
    assert ordered.index("阿里巴巴") < ordered.index("阿里")


def test_alias_pattern_is_regex_alternation():
    pat = platforms.platform_alias_pattern()
    assert "京东工业品" in pat and "1688" in pat and pat.count("|") >= 8


def test_extension_platform_ids_excludes_server_ehsy():
    ids = platforms.extension_platform_ids()
    assert ids == {"jd", "zkh", "1688"}  # ehsy 是 server
