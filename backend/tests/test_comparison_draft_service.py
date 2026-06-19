import json
from datetime import datetime

import pytest

from app.models.comparison import (
    ComparisonCategory,
    ComparisonDraftStatus,
    ComparisonSpecification,
    ComparisonStructure,
    PurchaseConstraints,
)
from app.services import comparison_draft_service


class FakeResult:
    def __init__(self, row=None, rowcount=1):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row


class FakeSession:
    rows = {}
    last_insert = None
    last_update = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement, params):
        sql = str(statement)
        if "INSERT INTO comparison_drafts" in sql:
            self.__class__.last_insert = params
            self.__class__.rows[(params["id"], params["uid"])] = _row_from_params(params)
            return FakeResult()
        if "UPDATE comparison_drafts" in sql:
            self.__class__.last_update = params
            key = (params["id"], params["uid"])
            if key not in self.__class__.rows:
                return FakeResult(rowcount=0)
            old = self.__class__.rows[key]
            self.__class__.rows[key] = (
                old[0],
                old[1],
                old[2],
                params["structure_json"],
                params["selected_platforms"],
                params["search_terms_json"],
                old[6],
                params["status"],
                old[8],
                old[9],
            )
            return FakeResult(rowcount=1)
        if "SELECT id, chat_session_id" in sql:
            return FakeResult(self.__class__.rows.get((params["id"], params["uid"])))
        raise AssertionError(f"unexpected SQL: {sql}")

    async def commit(self):
        return None


def _row_from_params(params):
    now = datetime(2026, 1, 1)
    return (
        params["id"],
        params["sid"],
        params["raw_query"],
        params["structure_json"],
        params["selected_platforms"],
        params["search_terms_json"],
        None,
        params["status"],
        now,
        now,
    )


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    FakeSession.rows = {}
    FakeSession.last_insert = None
    FakeSession.last_update = None
    monkeypatch.setattr(comparison_draft_service, "AsyncSessionLocal", FakeSession)


def _structure():
    return ComparisonStructure(
        category=ComparisonCategory(l3="六角头螺栓"),
        specification=ComparisonSpecification(productType="外六角螺栓", material="304", size="M8"),
        purchaseConstraints=PurchaseConstraints(preferredPlatforms=["jd"]),
    )


@pytest.mark.asyncio
async def test_create_draft_persists_structure_and_search_terms():
    draft = await comparison_draft_service.create_draft(
        user_id="u7",
        session_id="s1",
        raw_query="M8 304 外六角螺栓",
        structure=_structure(),
    )

    inserted = FakeSession.last_insert
    structure_json = json.loads(inserted["structure_json"])

    assert inserted["uid"] == 7
    assert inserted["status"] == ComparisonDraftStatus.NEEDS_CONFIRMATION.value
    assert json.loads(inserted["selected_platforms"]) == ["jd"]
    assert json.loads(inserted["search_terms_json"])["jd"][0] == "外六角螺栓 304 M8"
    assert structure_json["searchTerms"]["jd"][0] == "外六角螺栓 304 M8"
    assert draft["id"].startswith("cmp_draft_")
    assert draft["sessionId"] == "s1"
    assert draft["searchTerms"]["jd"][0] == "外六角螺栓 304 M8"


@pytest.mark.asyncio
async def test_create_draft_from_message_returns_slot_clarification(monkeypatch):
    class StructureResult:
        shouldCreateDraft = False
        structure = None
        guidance = None
        parsedIntent = {"query_type": "broad_spec"}
        slotClarification = {
            "summary": "需要采购 M8 六角螺母",
            "known": [{"label": "规格", "value": "M8"}],
            "missing": [
                {
                    "key": "strength_grade",
                    "icon": "⚙️",
                    "question": "需要什么强度等级？",
                    "options": ["4级", "8级", "10级"],
                }
            ],
        }

    async def fake_build_comparison_structure(*args, **kwargs):
        return StructureResult()

    monkeypatch.setattr(
        comparison_draft_service,
        "build_comparison_structure",
        fake_build_comparison_structure,
    )

    result = await comparison_draft_service.create_draft_from_message(
        user_id="u7",
        session_id="s1",
        message="M8 六角螺母",
    )

    assert result["shouldCreateDraft"] is False
    assert result["slotClarification"]["missing"][0]["key"] == "strength_grade"


@pytest.mark.asyncio
async def test_get_draft_is_scoped_by_user_id():
    created = await comparison_draft_service.create_draft("u7", "s1", "query", _structure())

    assert await comparison_draft_service.get_draft(created["id"], "u8") is None
    assert (await comparison_draft_service.get_draft(created["id"], "u7"))["id"] == created["id"]


@pytest.mark.asyncio
async def test_update_draft_regenerates_search_terms_and_platforms():
    created = await comparison_draft_service.create_draft("u7", "s1", "query", _structure())
    updated_structure = ComparisonStructure(
        category=ComparisonCategory(l3="O型圈"),
        specification=ComparisonSpecification(productType="O型圈", size="30×3.1mm"),
    )

    updated = await comparison_draft_service.update_draft_structure(
        draft_id=created["id"],
        user_id="u7",
        structure=updated_structure,
        selected_platforms=["jd", "zkh"],
    )

    assert updated["structure"]["searchTerms"]["jd"][0] == "O型圈 30×3.1mm"
    assert updated["selectedPlatforms"] == ["jd", "zkh"]
    assert json.loads(FakeSession.last_update["search_terms_json"])["zkh"][0] == "O型圈 30×3.1mm"


@pytest.mark.asyncio
async def test_create_draft_empty_preferred_platforms_falls_back_to_jd_zkh_ehsy():
    """当 preferredPlatforms 为空列表时，create_draft 应兜底为 ["jd", "zkh", "ehsy"]（含西域）。"""
    structure = ComparisonStructure(
        category=ComparisonCategory(l3="轴承"),
        specification=ComparisonSpecification(productType="深沟球轴承", size="6205"),
        purchaseConstraints=PurchaseConstraints(preferredPlatforms=[]),
    )

    draft = await comparison_draft_service.create_draft(
        user_id="u7",
        session_id="s1",
        raw_query="6205 深沟球轴承",
        structure=structure,
    )

    inserted = FakeSession.last_insert
    assert json.loads(inserted["selected_platforms"]) == ["jd", "zkh", "ehsy"]
    assert draft["selectedPlatforms"] == ["jd", "zkh", "ehsy"]


@pytest.mark.asyncio
async def test_update_draft_empty_preferred_platforms_falls_back_to_jd_zkh_ehsy():
    """当 update_draft_structure 的 selected_platforms=None 且 preferredPlatforms 为空时，
    应兜底为 ["jd", "zkh", "ehsy"]（含西域）。"""
    created = await comparison_draft_service.create_draft("u7", "s1", "query", _structure())

    updated_structure = ComparisonStructure(
        category=ComparisonCategory(l3="轴承"),
        specification=ComparisonSpecification(productType="深沟球轴承", size="6205"),
        purchaseConstraints=PurchaseConstraints(preferredPlatforms=[]),
    )

    updated = await comparison_draft_service.update_draft_structure(
        draft_id=created["id"],
        user_id="u7",
        structure=updated_structure,
        selected_platforms=None,
    )

    assert json.loads(FakeSession.last_update["selected_platforms"]) == ["jd", "zkh", "ehsy"]
    assert updated["selectedPlatforms"] == ["jd", "zkh", "ehsy"]
