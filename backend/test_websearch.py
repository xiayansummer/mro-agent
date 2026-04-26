"""
路线 A 可行性验证：DashScope enable_search + agent_max
测试 qwen3.5-plus 能否从西域、震坤行、京东工业品搜到真实价格

运行方式：
  cd backend
  python test_websearch.py
"""

import os
import time
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("AI_API_KEY"),
    base_url=os.getenv("AI_BASE_URL"),
)

MODEL = "qwen3.5-plus"

# 测试用的几个典型工业品查询
TEST_CASES = [
    {
        "product": "M8×30 六角头螺栓 不锈钢 A2-70",
        "sites": ["西域(xiyukeji.cn)", "震坤行(zkh.com)", "京东工业品(jd.com)"],
    },
    {
        "product": "SKF 深沟球轴承 6205-2RS",
        "sites": ["西域(xiyukeji.cn)", "震坤行(zkh.com)", "京东工业品(jd.com)"],
    },
]

SEARCH_PROMPT = """请在以下平台上搜索产品「{product}」的当前价格和库存情况：
1. 西域(xiyukeji.cn)
2. 震坤行(zkh.com)
3. 京东工业品(jd.com)

对每个平台，请提供：
- 产品名称（尽量接近搜索词）
- 单价（含单位）
- 产品链接
- 是否有货

如果某平台搜不到，也请说明。请直接输出结构化结果，不要废话。"""


def test_search(product: str) -> dict:
    prompt = SEARCH_PROMPT.format(product=product)

    start = time.time()
    try:
        # agent_max (Web Extractor) requires streaming=True
        stream = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            extra_body={
                "enable_search": True,
                "search_options": {"search_strategy": "agent_max"},
            },
            max_tokens=1500,
            stream=True,
        )
        chunks = []
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                chunks.append(delta.content)
        elapsed = time.time() - start
        return {"ok": True, "content": "".join(chunks), "elapsed": elapsed}
    except Exception as e:
        elapsed = time.time() - start
        return {"ok": False, "error": str(e), "elapsed": elapsed}


def main():
    print(f"=== 路线 A 可行性验证 ===")
    print(f"模型: {MODEL}")
    print(f"策略: enable_search + agent_max\n")

    for case in TEST_CASES:
        product = case["product"]
        print(f"{'='*60}")
        print(f"查询: {product}")
        print(f"{'='*60}")

        result = test_search(product)
        print(f"耗时: {result['elapsed']:.1f}s")

        if result["ok"]:
            print(f"\n--- 模型返回 ---\n{result['content']}")
        else:
            print(f"\n[错误] {result['error']}")

        print()


if __name__ == "__main__":
    main()
