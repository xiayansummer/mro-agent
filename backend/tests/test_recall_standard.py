"""比价召回链路标准回归测试(workflow 设计的多品类典型查询)。
严格锁定每个典型查询的 searchTerms 与排序/过滤行为;改召回相关代码后跑此套件回归。

已知局限(不在此套件内打补丁,见 project_mro_recall_root_cause):
- productType 被 LLM 拆词(如"防电弧绝缘手套"→"防电弧手套 绝缘手套")时,与连写的真实标题
  匹配偏低,最对口商品可能未排首;品类叫法差异(O型圈 vs O型密封圈)可能漏召。
  需 productType 匹配鲁棒性的单独改进,届时更新本套件。"""
import json

import pytest

from app.models.comparison import ComparisonStructure, ComparisonSpecification, ComparisonCategory
from app.services.comparison_query_builder import build_search_terms, MAX_TERMS_PER_PLATFORM
from app.services.comparison_ranker import rank_external_offers

CASES = json.loads("""
[
  {
    "name": "meihe_chain_hoist_hsz622a_recall",
    "spec": {
      "productType": "手拉葫芦",
      "brand": "美和",
      "model": "HSZ-622A",
      "size": "2吨",
      "attributes": [
        {
          "name": "起升高度",
          "value": "3米"
        }
      ]
    },
    "l3": "手拉葫芦",
    "offers": [
      {
        "id": "off-01",
        "title": "美和 手拉葫芦 HSZ-622A 2吨 3米 环链 工业起重",
        "priceValue": 268,
        "rawRank": 1
      },
      {
        "id": "off-02",
        "title": "美和 环链手拉葫芦 2吨 3米 手扳葫芦 起重工具",
        "priceValue": 255,
        "rawRank": 2
      },
      {
        "id": "off-03",
        "title": "美和 手拉葫芦 2t 工业级 起重链条 倒链",
        "priceValue": 239,
        "rawRank": 3
      },
      {
        "id": "off-04",
        "title": "美和 手拉葫芦 HSZ-622A 5吨 6米 重型",
        "priceValue": 560,
        "rawRank": 4
      },
      {
        "id": "off-05",
        "title": "美和 电动葫芦 220V 1吨 钢丝绳 微型电葫芦",
        "priceValue": 1180,
        "rawRank": 5
      },
      {
        "id": "off-06",
        "title": "手拉葫芦 通用型 2吨 3米 家用起重倒链 无品牌",
        "priceValue": 95,
        "rawRank": 6
      },
      {
        "id": "off-07",
        "title": "手拉葫芦专用链条 起重链 8mm 配件",
        "priceValue": 35,
        "rawRank": 7
      },
      {
        "id": "off-08",
        "title": "劳保棉纱手套 防滑耐磨 工地通用 12双",
        "priceValue": 29,
        "rawRank": 8
      },
      {
        "id": "off-09",
        "title": "美的 电饭煲 4L 智能家用厨房电器",
        "priceValue": 199,
        "rawRank": 9
      }
    ],
    "keep": [
      "off-01",
      "off-02",
      "off-03",
      "off-04"
    ],
    "drop": [
      "off-05",
      "off-06",
      "off-07",
      "off-08",
      "off-09"
    ],
    "first": "off-01",
    "must_inc": [
      "手拉葫芦",
      "美和 手拉葫芦"
    ]
  },
  {
    "name": "防电弧绝缘手套-多词品类降级与京东召回回归",
    "spec": {
      "productType": "防电弧手套 绝缘手套",
      "standard": "Class 00",
      "attributes": [
        {
          "name": "耐压",
          "value": "500V"
        }
      ]
    },
    "l3": "绝缘手套",
    "offers": [
      {
        "id": "jd-1",
        "title": "霍尼韦尔 防电弧绝缘手套 Class 00 耐压500V 低压带电作业绝缘橡胶手套",
        "priceValue": 289,
        "rawRank": 1
      },
      {
        "id": "jd-2",
        "title": "双安 0级绝缘手套 Class 00 500V 电工低压防触电橡胶手套",
        "priceValue": 96,
        "rawRank": 2
      },
      {
        "id": "jd-3",
        "title": "蜀峰 12kV 高压绝缘手套 电工绝缘橡胶手套 带电作业防护手套",
        "priceValue": 158,
        "rawRank": 3
      },
      {
        "id": "jd-4",
        "title": "代尔塔 防电弧手套 防火阻燃焊接手套 耐高温作业手套",
        "priceValue": 210,
        "rawRank": 4
      },
      {
        "id": "jd-5",
        "title": "3M 一次性丁腈检查手套 食品级 防油防滑 100只盒装",
        "priceValue": 39.9,
        "rawRank": 5
      },
      {
        "id": "jd-6",
        "title": "得力 劳保棉纱线手套 防滑耐磨工地搬运手套 12双装",
        "priceValue": 18.5,
        "rawRank": 6
      },
      {
        "id": "jd-7",
        "title": "正泰 家用配电箱 12回路 强电箱 PZ30 暗装空开盒",
        "priceValue": 75,
        "rawRank": 7
      },
      {
        "id": "jd-8",
        "title": "电工绝缘胶垫 5mm厚 配电室绝缘地胶 1米×5米 黑色",
        "priceValue": 460,
        "rawRank": 8
      }
    ],
    "keep": [
      "jd-1",
      "jd-2",
      "jd-3",
      "jd-4"
    ],
    "drop": [
      "jd-5",
      "jd-6",
      "jd-7",
      "jd-8"
    ],
    "first": "jd-2",
    "must_inc": [
      "绝缘手套"
    ]
  },
  {
    "name": "M8不锈钢六角螺母-召回链路回归(规格材质匹配+不相关紧固件过滤)",
    "spec": {
      "productType": "六角螺母",
      "material": "304不锈钢",
      "size": "M8",
      "attributes": []
    },
    "l3": "螺母",
    "offers": [
      {
        "id": "off_perfect",
        "title": "304不锈钢外六角螺母 GB/T6170 M8 六角螺帽 100个装",
        "priceValue": 12.8,
        "rawRank": 1
      },
      {
        "id": "off_316_m8",
        "title": "316不锈钢六角螺母 M8 加厚螺帽 防锈耐腐蚀 50只",
        "priceValue": 18,
        "rawRank": 2
      },
      {
        "id": "off_ss_nut_nosize",
        "title": "304不锈钢六角螺母大全 M3-M12 多规格混装盒",
        "priceValue": 9.9,
        "rawRank": 3
      },
      {
        "id": "off_nut_carbon_nomat",
        "title": "六角螺母 M8 镀锌发黑 GB6170 工业紧固 500个",
        "priceValue": 6.5,
        "rawRank": 4
      },
      {
        "id": "off_ss_bolt",
        "title": "304不锈钢内六角螺栓 杯头螺丝 圆柱头 盒装",
        "priceValue": 22,
        "rawRank": 5
      },
      {
        "id": "off_zip_tie",
        "title": "尼龙扎带 自锁式塑料束线带 4x200mm 黑色 250根",
        "priceValue": 9.9,
        "rawRank": 6
      },
      {
        "id": "off_cup",
        "title": "家用304不锈钢保温杯 真空便携 大容量水杯",
        "priceValue": 59,
        "rawRank": 7
      },
      {
        "id": "off_tape",
        "title": "电工绝缘PVC胶带 黑色阻燃防水 10卷装",
        "priceValue": 8.8,
        "rawRank": 8
      }
    ],
    "keep": [
      "off_perfect",
      "off_316_m8",
      "off_ss_nut_nosize",
      "off_nut_carbon_nomat"
    ],
    "drop": [
      "off_ss_bolt",
      "off_zip_tie",
      "off_cup",
      "off_tape"
    ],
    "first": "off_perfect",
    "must_inc": [
      "六角螺母"
    ]
  },
  {
    "name": "外六角螺栓-304-DIN933-M8-召回回归",
    "spec": {
      "productType": "外六角螺栓",
      "material": "304",
      "size": "M8",
      "standard": "DIN933",
      "attributes": []
    },
    "l3": "螺栓",
    "offers": [
      {
        "id": "jd-001",
        "title": "外六角螺栓 304不锈钢 DIN933 M8*30 全牙六角头螺丝 50个",
        "priceValue": 0.35,
        "rawRank": 1
      },
      {
        "id": "jd-002",
        "title": "304不锈钢外六角螺栓 DIN933 M8x50 六角头螺栓螺丝",
        "priceValue": 0.42,
        "rawRank": 2
      },
      {
        "id": "zkh-101",
        "title": "外六角螺栓 304不锈钢 GB5783 M8x40 全牙紧固件",
        "priceValue": 0.38,
        "rawRank": 3
      },
      {
        "id": "jd-003",
        "title": "外六角螺栓 碳钢镀锌 8.8级 DIN933 M8x30 高强度",
        "priceValue": 0.12,
        "rawRank": 4
      },
      {
        "id": "zkh-102",
        "title": "外六角螺栓 304不锈钢 多规格可选 标准件紧固件",
        "priceValue": 0.55,
        "rawRank": 5
      },
      {
        "id": "jd-004",
        "title": "内六角圆柱头螺钉 304不锈钢 M6x20 杯头螺丝",
        "priceValue": 0.22,
        "rawRank": 6
      },
      {
        "id": "jd-005",
        "title": "电工绝缘胶带 PVC 阻燃 黑色 18mm*20m 10卷",
        "priceValue": 3.5,
        "rawRank": 7
      },
      {
        "id": "zkh-103",
        "title": "晨光中性笔 0.5mm 黑色子弹头 办公签字笔 12支/盒",
        "priceValue": 9.9,
        "rawRank": 8
      }
    ],
    "keep": [
      "jd-001",
      "jd-002",
      "zkh-101",
      "jd-003",
      "zkh-102"
    ],
    "drop": [
      "jd-004",
      "jd-005",
      "zkh-103"
    ],
    "first": "jd-001",
    "must_inc": [
      "外六角螺栓"
    ]
  },
  {
    "name": "o-ring_30x3.1mm_no_brand_recall",
    "spec": {
      "productType": "O型圈",
      "size": "30×3.1mm"
    },
    "l3": "O型圈",
    "offers": [
      {
        "id": "off-strong-1",
        "title": "进口丁腈橡胶O型圈 NBR 30×3.1mm 耐油密封圈 工业级",
        "priceValue": 1.8,
        "rawRank": 1
      },
      {
        "id": "off-strong-2",
        "title": "O型圈 氟橡胶FKM 30*3.1mm 高温耐腐蚀密封圈",
        "priceValue": 3.5,
        "rawRank": 2
      },
      {
        "id": "off-part-1",
        "title": "O型圈密封圈 多规格丁腈橡胶圈 耐油耐磨 工业通用",
        "priceValue": 0.5,
        "rawRank": 3
      },
      {
        "id": "off-part-2",
        "title": "硅胶O型圈 食品级密封圈 外径30mm 整包装",
        "priceValue": 12,
        "rawRank": 4
      },
      {
        "id": "off-part-3",
        "title": "O型密封圈套装 200只盒装 常用尺寸混装维修盒",
        "priceValue": 25,
        "rawRank": 5
      },
      {
        "id": "off-drop-1",
        "title": "304不锈钢内六角螺栓 M8×30 GB/T70.1 100只",
        "priceValue": 18,
        "rawRank": 6
      },
      {
        "id": "off-drop-2",
        "title": "电工绝缘胶带 PVC黑色 18mm×30m 防水阻燃",
        "priceValue": 4.5,
        "rawRank": 7
      },
      {
        "id": "off-drop-3",
        "title": "深沟球轴承 6203 内径17mm 高速静音",
        "priceValue": 8,
        "rawRank": 8
      }
    ],
    "keep": [
      "off-strong-1",
      "off-strong-2",
      "off-part-1",
      "off-part-2"
    ],
    "drop": [
      "off-drop-1",
      "off-drop-2",
      "off-drop-3",
      "off-part-3"
    ],
    "first": "off-strong-1",
    "must_inc": [
      "O型圈"
    ]
  },
  {
    "name": "绝缘手套-单核心宽品类-无型号无品牌-召回回归",
    "spec": {
      "productType": "防电弧 绝缘手套",
      "size": "11号",
      "attributes": [
        {
          "name": "电压等级",
          "value": "12kV"
        },
        {
          "name": "防护类别",
          "value": "0级"
        }
      ]
    },
    "l3": "绝缘手套",
    "offers": [
      {
        "id": "o1",
        "title": "双安 12kV电工绝缘手套 0级带电作业防电弧橡胶手套 11号 一双",
        "priceValue": 139,
        "rawRank": 1
      },
      {
        "id": "o2",
        "title": "代尔塔 绝缘手套电工专用 12kV 防触电橡胶手套 0级 11号 劳保",
        "priceValue": 128,
        "rawRank": 2
      },
      {
        "id": "o3",
        "title": "耐高压绝缘手套 25kV 电工劳保防电橡胶手套 11号 高压作业",
        "priceValue": 95,
        "rawRank": 3
      },
      {
        "id": "o4",
        "title": "绝缘手套 电工防护橡胶手套 通用型 11号 一双",
        "priceValue": 46,
        "rawRank": 4
      },
      {
        "id": "o5",
        "title": "防电弧服 阻燃电焊工作服 12cal 防护套装",
        "priceValue": 320,
        "rawRank": 5
      },
      {
        "id": "o6",
        "title": "一次性丁腈检查手套 无粉 100只装 实验室防护",
        "priceValue": 39,
        "rawRank": 6
      },
      {
        "id": "o7",
        "title": "劳保棉纱手套 防滑耐磨工地线手套 24双装",
        "priceValue": 18,
        "rawRank": 7
      },
      {
        "id": "o8",
        "title": "电工绝缘胶垫 5mm 绝缘地毯 配电室高压绝缘垫",
        "priceValue": 210,
        "rawRank": 8
      }
    ],
    "keep": [
      "o1",
      "o2",
      "o3",
      "o4"
    ],
    "drop": [
      "o5",
      "o6",
      "o7",
      "o8"
    ],
    "first": "o1",
    "must_inc": [
      "绝缘手套"
    ]
  }
]
""")


def _build(case):
    spec = dict(case["spec"])
    attrs = spec.pop("attributes", []) or []
    cat = ComparisonCategory(l3=case["l3"]) if case.get("l3") else ComparisonCategory()
    return ComparisonStructure(category=cat, specification=ComparisonSpecification(attributes=attrs, **spec))


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_search_terms_invariants(case):
    terms = build_search_terms(_build(case))
    assert terms.jd == terms.zkh
    assert 1 <= len(terms.jd) <= MAX_TERMS_PER_PLATFORM, terms.jd
    model = case["spec"].get("model")
    if model:
        assert all(model not in t for t in terms.jd), ("型号不应进搜索词", terms.jd)
    for kw in case["must_inc"]:
        assert any(kw in t for t in terms.jd), ("缺核心召回词", kw, terms.jd)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_ranking_invariants(case):
    ranked = rank_external_offers(_build(case), [dict(o) for o in case["offers"]])
    kept = {o["id"] for o in ranked}
    assert ranked, "结果不应为空"
    assert ranked[0]["id"] == case["first"], ("强相关应排第一", [(o["id"], o["matchScore"]) for o in ranked])
    assert set(case["keep"]) <= kept, ("应保留却被滤", sorted(set(case["keep"]) - kept))
    assert set(case["drop"]).isdisjoint(kept), ("应丢弃却保留", sorted(set(case["drop"]) & kept))
