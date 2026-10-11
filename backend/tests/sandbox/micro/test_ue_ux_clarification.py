# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/micro/test_ue_ux_clarification.py
Назначение: UX-UE-01 Этап 1, ② (DP-3 v1 stateless, GO Тай) + R2 — контракт
    поля ответа хода ChatTurnResponse.clarification {reason, text, candidates}.
    R2: при RESOLVED — отсутствует (дефолт None + опущение ключа при
    сериализации); при non-RESOLVED — присутствует. Ограничение Этапа 1:
    routes-сериализация ключа — приёмка Этапа 2 (API-smoke/ручной прогон);
    здесь фиксируются модель-контракт и форма.
Зависимости: app.models.schemas
Запуск: cd backend; python -m pytest tests/sandbox/micro/test_ue_ux_clarification.py -q; cd ..
"""
import pytest

from app.models.schemas import ChatTurnResponse


def _fields(cls) -> dict:
    # Pydantic v1/v2-агностик
    return getattr(cls, "model_fields", None) or getattr(cls, "__fields__", {})


def _response() -> ChatTurnResponse:
    return ChatTurnResponse(
        dm_response="ok", npc_reactions=[], world_changes=[],
        journal_entry_id="", traces=[],
    )


@pytest.mark.xfail(strict=True, reason="UX-UE-01 ②: поле clarification не реализовано (Этап 2)")
def test_response_model_has_clarification_field():
    assert "clarification" in _fields(ChatTurnResponse)


def test_resolved_default_clarification_none():
    # Регресс-нуль (R2): RESOLVED-ход ничего не добавляет — уже зелёный
    resp = _response()
    assert getattr(resp, "clarification", None) is None


def test_clarification_shape_contract():
    # Форма (R2): {reason, text, candidates}; reason ≠ RESOLVED;
    # candidates — null | непустой список {npc_id, name} (None ≠ []).
    def check(c: dict) -> None:
        assert set(c.keys()) == {"reason", "text", "candidates"}
        assert c["reason"] != "RESOLVED"
        assert isinstance(c["text"], str) and c["text"]
        if c["candidates"] is not None:
            assert isinstance(c["candidates"], list) and c["candidates"]
            for item in c["candidates"]:
                assert set(item.keys()) == {"npc_id", "name"}

    check({"reason": "REFERENCE_AMBIGUOUS", "text": "…",
           "candidates": [{"npc_id": "guard_gate", "name": "стражник у ворот"},
                          {"npc_id": "guard_market", "name": "стражник на рынке"}]})
    check({"reason": "PARTIAL", "text": "…", "candidates": None})
    for bad in (
        {"reason": "RESOLVED", "text": "x", "candidates": None},  # RESOLVED запрещён
        {"reason": "PARTIAL", "candidates": None},                 # нет text
        {"reason": "PARTIAL", "text": "x", "candidates": []},      # [] не производится
        {"reason": "PARTIAL", "text": "x", "candidates": [{"id": "x"}]},  # форма элементов
    ):
        with pytest.raises(AssertionError):
            check(bad)