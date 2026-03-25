"""
Memory Service — Memos-backed long-term memory for MRO Agent.

Write path: after each conversation turn, save a structured summary memo.
Read path:  before intent parsing, retrieve recent relevant memos as context.

Memo tagging convention:
  #uid-{user_id[:8]}   — identifies which user owns this memo
  #session             — conversation turn summary
  #preference          — distilled user preference (written later in Phase 5)
  #project             — user-defined project context (written manually in Memos UI)
"""

import asyncio
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(self):
        self._token: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    # ── Internal: HTTP client ──────────────────────────────────────────────

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=settings.MEMOS_URL,
            timeout=httpx.Timeout(10.0, connect=5.0),
        )

    async def _auth_headers(self) -> dict:
        token = await self._get_token()
        return {"Authorization": f"Bearer {token}"}

    # ── Internal: Auth ─────────────────────────────────────────────────────

    async def _get_token(self) -> str:
        """Return a valid bearer token, authenticating if necessary."""
        if self._token:
            return self._token

        # Option A: static access token configured in .env
        if settings.MEMOS_ACCESS_TOKEN:
            self._token = settings.MEMOS_ACCESS_TOKEN
            return self._token

        # Option B: sign in with username/password
        async with self._make_client() as client:
            # Try sign-in first (normal case after first run)
            try:
                resp = await client.post(
                    "/api/v1/auth/signin",
                    json={
                        "username": settings.MEMOS_USERNAME,
                        "password": settings.MEMOS_PASSWORD,
                        "neverExpire": True,
                    },
                )
                if resp.status_code == 200:
                    self._token = resp.json().get("accessToken")
                    logger.info("Memos: signed in successfully")
                    return self._token
            except Exception as e:
                logger.debug(f"Memos sign-in attempt failed: {e}")

            # First run: register admin account (only works when no users exist)
            try:
                resp = await client.post(
                    "/api/v1/auth/signup",
                    json={
                        "username": settings.MEMOS_USERNAME,
                        "password": settings.MEMOS_PASSWORD,
                    },
                )
                if resp.status_code == 200:
                    self._token = resp.json().get("accessToken")
                    logger.info("Memos: created admin account successfully")
                    return self._token
            except Exception as e:
                logger.debug(f"Memos sign-up attempt failed: {e}")

        raise RuntimeError(
            "Failed to authenticate with Memos. "
            "Set MEMOS_ACCESS_TOKEN in .env or ensure Memos is running."
        )

    # ── Public: Core CRUD ──────────────────────────────────────────────────

    async def create_memo(self, content: str) -> Optional[dict]:
        """Create a PRIVATE memo. Returns the created memo dict or None on failure."""
        try:
            headers = await self._auth_headers()
            async with self._make_client() as client:
                resp = await client.post(
                    "/api/v1/memos",
                    json={"content": content, "visibility": "PRIVATE"},
                    headers=headers,
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"Memos create_memo {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Memos create_memo failed: {e}")
        return None

    async def list_memos(
        self,
        uid_tag: str,
        extra_tag: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        List memos for a given uid_tag, newest first.
        Optionally filter by an additional tag.
        """
        try:
            headers = await self._auth_headers()
            filter_expr = f'"{uid_tag}" in tags'
            if extra_tag:
                filter_expr += f' && "{extra_tag}" in tags'

            async with self._make_client() as client:
                resp = await client.get(
                    "/api/v1/memos",
                    params={"pageSize": limit, "filter": filter_expr},
                    headers=headers,
                )
                if resp.status_code == 200:
                    return resp.json().get("memos", [])
                logger.warning(f"Memos list_memos {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Memos list_memos failed: {e}")
        return []

    # ── Public: High-level write ───────────────────────────────────────────

    async def save_session_summary(
        self,
        user_id: str,
        user_message: str,
        intent: dict,
        results: list,
        response_mode: str,
        query_type: str = "",
    ) -> None:
        """
        Called after each conversation turn to save a structured summary memo.
        This is fire-and-forget — failures are logged but not raised.
        """
        uid_tag = _uid_tag(user_id)

        # Build category breadcrumb for tagging
        categories = [
            intent.get("l2_category", ""),
            intent.get("l3_category", ""),
            intent.get("l4_category", ""),
        ]
        category_str = " > ".join(c for c in categories if c)
        category_tag = (
            category_str.replace(" > ", "-").replace(" ", "-").lower()
            if category_str
            else "unknown"
        )

        keywords = intent.get("keywords") or []
        brand = intent.get("brand", "") or ""
        spec_keywords = intent.get("spec_keywords") or []

        # Top-5 SKU lines
        sku_lines = ""
        if results:
            sku_lines = "\n".join(
                f"- `{s.get('item_code', '')}` {s.get('item_name', '')[:50]}"
                f"  ({s.get('brand_name', '') or ''})"
                for s in results[:5]
            )

        sku_section = ("**展示产品（前5）：**\n" + sku_lines) if sku_lines else "**无匹配产品**"

        content = f"""## 采购查询记录

**用户问题：** {user_message}

**识别品类：** {category_str or "未识别"}
**关键词：** {", ".join(keywords) if keywords else "无"}
**规格要求：** {", ".join(spec_keywords) if spec_keywords else "无"}
**品牌要求：** {brand or "无"}
**查询类型：** {query_type or "unknown"}
**匹配数量：** {len(results)} 个产品
**响应类型：** {response_mode}

{sku_section}

#{uid_tag} #session #{category_tag}"""

        logger.info(f"Memos: saving session summary for user {user_id[:8]}, mode={response_mode}")
        try:
            result = await self.create_memo(content)
            if result:
                logger.info(f"Memos: saved OK — memo name={result.get('name')}")
            else:
                logger.warning(f"Memos: create_memo returned None for user {user_id[:8]}")
        except Exception as e:
            logger.error(f"Memos: save_session_summary exception: {e}", exc_info=True)

    # ── Public: High-level write (feedback) ───────────────────────────────

    async def save_feedback(
        self,
        user_id: str,
        action: str,          # "liked" | "disliked"
        item_code: str,
        item_name: str,
        brand_name: str = "",
        l2_category: str = "",
        l3_category: str = "",
        specification: str = "",
    ) -> None:
        """Save a 👍/👎 product feedback memo. Fire-and-forget."""
        uid_tag = _uid_tag(user_id)
        action_label = "👍 感兴趣" if action == "liked" else "👎 不符合需求"
        category_str = " > ".join(c for c in [l2_category, l3_category] if c)

        content = f"""## 产品反馈

**操作：** {action_label}
**产品：** {item_name}
**编码：** `{item_code}`
**品牌：** {brand_name or "未知"}
**品类：** {category_str or "未知"}
**规格：** {specification or "未知"}

#{uid_tag} #feedback #{action}"""

        logger.info(f"Memos: saving feedback {action} for {item_code}, user {user_id[:8]}")
        try:
            result = await self.create_memo(content)
            if result:
                logger.info(f"Memos: feedback saved — memo name={result.get('name')}")
        except Exception as e:
            logger.error(f"Memos: save_feedback exception: {e}", exc_info=True)

    # ── Public: High-level read ────────────────────────────────────────────

    async def get_user_context(self, user_id: str, limit: int = 3) -> str:
        """
        Retrieve recent session memos + feedback memos for a user and format
        them as a context string for injection into the intent-parsing prompt.
        """
        uid_tag = _uid_tag(user_id)

        # Fetch session history and feedback in parallel
        session_memos, feedback_memos = await asyncio.gather(
            self.list_memos(uid_tag, extra_tag="session", limit=max(limit, 6)),
            self.list_memos(uid_tag, extra_tag="feedback", limit=15),
        )

        parts = []

        # ── Expertise level from session history ────────────────────────
        expertise_level = _compute_expertise(session_memos)
        if expertise_level != "unknown":
            level_label = {"expert": "专家", "intermediate": "中级", "novice": "新手"}.get(expertise_level, expertise_level)
            level_hint = {
                "expert": "用户有丰富采购经验，熟悉规格参数和标准编号，直接给出精准结果，无需过多引导。",
                "intermediate": "用户有一定经验，了解品类，但有时需要确认规格细节。",
                "novice": "用户是采购新手，需要引导式追问，解释产品类型区别，帮助逐步明确需求。",
            }.get(expertise_level, "")
            parts.append(f"【用户专业程度】级别：{level_label}（{expertise_level}）\n{level_hint}")

        # ── Session history ──────────────────────────────────────────────
        if session_memos:
            session_parts = []
            for memo in session_memos[:limit]:
                raw = memo.get("content", "")
                lines = [ln for ln in raw.splitlines() if not ln.startswith("#uid-")]
                text = "\n".join(lines).strip()
                if len(text) > 400:
                    text = text[:400] + "…"
                session_parts.append(text)
            parts.append("【该用户近期采购记录】\n\n" + "\n\n---\n\n".join(session_parts))

        # ── Feedback preferences ─────────────────────────────────────────
        if feedback_memos:
            liked_brands: dict[str, int] = {}
            liked_categories: dict[str, int] = {}
            disliked_items: list[str] = []

            for memo in feedback_memos:
                raw = memo.get("content", "")
                is_liked = "#liked" in raw
                fields: dict[str, str] = {}
                for line in raw.splitlines():
                    for key in ("**品牌：**", "**品类：**", "**产品：**", "**规格：**"):
                        if line.startswith(key):
                            fields[key] = line.replace(key, "").strip()

                brand = fields.get("**品牌：**", "")
                category = fields.get("**品类：**", "")
                product = fields.get("**产品：**", "")

                if is_liked:
                    if brand and brand != "未知":
                        liked_brands[brand] = liked_brands.get(brand, 0) + 1
                    if category and category != "未知":
                        # Use top-level category only
                        top_cat = category.split(" > ")[0]
                        liked_categories[top_cat] = liked_categories.get(top_cat, 0) + 1
                else:
                    if product and product != "未知":
                        disliked_items.append(product[:30])

            pref_lines = []
            if liked_brands:
                top_brands = sorted(liked_brands, key=liked_brands.get, reverse=True)[:5]
                pref_lines.append(f"偏好品牌：{', '.join(top_brands)}")
            if liked_categories:
                top_cats = sorted(liked_categories, key=liked_categories.get, reverse=True)[:4]
                pref_lines.append(f"常用品类：{', '.join(top_cats)}")
            if disliked_items:
                pref_lines.append(f"曾排除产品：{', '.join(disliked_items[:3])}")

            if pref_lines:
                parts.append("【该用户产品偏好（来自历史反馈）】\n\n" + "\n".join(pref_lines))

        return "\n\n".join(parts) if parts else ""

    # ── Public: Health check ───────────────────────────────────────────────

    async def is_healthy(self) -> bool:
        """Ping Memos healthz endpoint. Returns False if unreachable."""
        try:
            async with self._make_client() as client:
                resp = await client.get("/healthz", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    def invalidate_token(self) -> None:
        """Force re-authentication on next request (e.g. after 401)."""
        self._token = None


# ── Helpers ────────────────────────────────────────────────────────────────

def _compute_expertise(session_memos: list[dict]) -> str:
    """
    Infer user expertise from recent session memos.
    Returns: "expert" | "intermediate" | "novice" | "unknown"

    Signals:
      Expert:      query_type=precise, has spec_keywords, uses standard numbers
      Novice:      query_type=application/vague, no spec_keywords, broad questions
      Intermediate: mixed
    """
    if not session_memos:
        return "unknown"

    expert_score = 0
    novice_score = 0

    for memo in session_memos:
        raw = memo.get("content", "")

        # query_type signal
        if "**查询类型：** precise" in raw:
            expert_score += 2
        elif "**查询类型：** broad_spec" in raw:
            expert_score += 1
        elif "**查询类型：** application" in raw:
            novice_score += 1
        elif "**查询类型：** vague" in raw:
            novice_score += 2

        # spec_keywords signal
        for line in raw.splitlines():
            if line.startswith("**规格要求：**"):
                spec_val = line.replace("**规格要求：**", "").strip()
                if spec_val and spec_val != "无":
                    # Has real spec keywords (DIN, M8, ISO, etc.)
                    expert_score += 1
                else:
                    novice_score += 1
                break

    total = expert_score + novice_score
    if total < 2:
        return "unknown"

    ratio = expert_score / total
    if ratio >= 0.7:
        return "expert"
    elif ratio >= 0.4:
        return "intermediate"
    else:
        return "novice"


def _uid_tag(user_id: str) -> str:
    """Derive a short, tag-safe string from a user_id UUID."""
    return f"uid-{user_id.replace('-', '')[:8]}"


# ── Module-level singleton ──────────────────────────────────────────────────

memory_service = MemoryService()
