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
            filter_expr = f'tag = "{uid_tag}"'
            if extra_tag:
                filter_expr += f' && tag = "{extra_tag}"'

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
    ) -> None:
        """
        Called after each conversation turn to save a structured summary memo.
        This is fire-and-forget — failures are logged but not raised.
        """
        uid_tag = _uid_tag(user_id)

        # Build category breadcrumb for tagging
        categories = [
            intent.get("l2_category_name", ""),
            intent.get("l3_category_name", ""),
            intent.get("l4_category_name", ""),
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

    # ── Public: High-level read ────────────────────────────────────────────

    async def get_user_context(self, user_id: str, limit: int = 3) -> str:
        """
        Retrieve recent session memos for a user and format them as a
        context string for injection into the intent-parsing prompt.

        Returns empty string if no memos exist or Memos is unavailable.
        """
        uid_tag = _uid_tag(user_id)
        memos = await self.list_memos(uid_tag, extra_tag="session", limit=limit)
        if not memos:
            return ""

        parts = []
        for memo in memos:
            raw = memo.get("content", "")
            # Strip the tag line at the bottom to keep context clean
            lines = [ln for ln in raw.splitlines() if not ln.startswith("#uid-")]
            text = "\n".join(lines).strip()
            if len(text) > 400:
                text = text[:400] + "…"
            parts.append(text)

        return "【该用户近期采购记录】\n\n" + "\n\n---\n\n".join(parts)

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

def _uid_tag(user_id: str) -> str:
    """Derive a short, tag-safe string from a user_id UUID."""
    return f"uid-{user_id.replace('-', '')[:8]}"


# ── Module-level singleton ──────────────────────────────────────────────────

memory_service = MemoryService()
