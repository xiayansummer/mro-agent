"""
震坤行爬虫原型验证
用 DrissionPage 控制浏览器，用 LLM 解析结果（不写死选择器）

运行方式：cd backend && python test_zkh_scraper.py
"""

import os, time, json
from dotenv import load_dotenv
from DrissionPage import ChromiumPage, ChromiumOptions
from openai import OpenAI

load_dotenv()

llm = OpenAI(api_key=os.getenv("AI_API_KEY"), base_url=os.getenv("AI_BASE_URL"))

# ── 启动浏览器 ───────────────────────────────────────────────────────────────

def make_browser() -> ChromiumPage:
    opts = ChromiumOptions()
    opts.headless(True)
    opts.set_argument("--no-sandbox")
    opts.set_argument("--disable-dev-shm-usage")
    opts.set_argument("--disable-blink-features=AutomationControlled")
    opts.set_user_agent(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    return ChromiumPage(addr_or_opts=opts)


# ── LLM 提取结构化数据 ────────────────────────────────────────────────────────

EXTRACT_PROMPT = """从以下震坤行搜索结果页面文本中，提取前5个产品的信息。

页面文本：
{text}

请返回 JSON 数组，每项包含：
- name: 产品名称
- price: 单价（字符串，含单位，如 "¥0.21/个" 或 "¥21.05/包(100个)"）
- brand: 品牌
- spec: 规格型号
- url: 产品链接（如果能从页面文本中找到）

如果某字段找不到就填 null。只返回 JSON，不要其他内容。"""


def llm_extract(page_text: str) -> list[dict]:
    try:
        resp = llm.chat.completions.create(
            model=os.getenv("AI_MODEL", "qwen3.5-plus"),
            messages=[{
                "role": "user",
                "content": EXTRACT_PROMPT.format(text=page_text[:4000])
            }],
            max_tokens=1000,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        print(f"  [LLM extract error] {e}")
        return []


# ── 主搜索逻辑 ────────────────────────────────────────────────────────────────

def search_zkh(keyword: str) -> list[dict]:
    page = make_browser()
    try:
        url = f"https://www.zkh.com/search?q={keyword}"
        print(f"  → 访问: {url}")
        page.get(url)
        time.sleep(3)  # wait for JS render

        # Check if redirected to login
        current_url = page.url
        print(f"  → 当前URL: {current_url}")
        if "login" in current_url or "signin" in current_url:
            print("  → 需要登录，退出")
            return []

        # Get visible text
        body_text = page.ele("tag:body").text
        print(f"  → 页面文本长度: {len(body_text)}")
        print(f"  → 文本前500字:\n{body_text[:500]}\n---")

        if len(body_text) < 100:
            print("  → 页面内容太少，可能被拦截")
            return []

        # LLM parse
        print("  → 调用 LLM 提取结构化数据...")
        results = llm_extract(body_text)
        return results

    finally:
        page.quit()


# ── 测试 ──────────────────────────────────────────────────────────────────────

TEST_KEYWORDS = [
    "M8x30 六角螺栓 不锈钢",
    "SKF 6205轴承",
]

def main():
    print("=== 震坤行爬虫原型验证 ===\n")
    for kw in TEST_KEYWORDS:
        print(f"{'='*50}")
        print(f"搜索: {kw}")
        print(f"{'='*50}")
        t = time.time()
        results = search_zkh(kw)
        elapsed = time.time() - t
        print(f"\n耗时: {elapsed:.1f}s")
        if results:
            print(f"找到 {len(results)} 个产品:")
            for i, r in enumerate(results, 1):
                print(f"  [{i}] {r.get('name','?')} | {r.get('price','?')} | {r.get('brand','?')} | {r.get('spec','?')}")
        else:
            print("未找到产品")
        print()


if __name__ == "__main__":
    main()
