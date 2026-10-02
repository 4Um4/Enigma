"""path: /project/backend/tests/micro/test_fast_phantom_attack.py

Назначение: P1/RC2 (вердикт Мастера) — fast-фантомный ATTACK:
    вопрос с существительным-объектом не должен нести causal ATTACK,
    когда LLM-слой уверенно классифицирует иначе и fast-пропозиция
    снята как фантом. Настоящий ATTACK не ломается; мёртвая LLM —
    честная деградация (action остаётся, ADR-113).
Зависимости: app.services.input.intent_compressor, app.domain.intent_profile.
Запуск: cd backend; python -m pytest tests/micro/test_fast_phantom_attack.py -v; cd ..
"""

from app.domain.intent_profile import ActionType, IntentSemanticField
from app.services.input.intent_compressor import IntentCompressor


def _fast_attack_field(target="денег"):
    """Fast-фантом: ATTACK с пропозицией на нерезолвнутую сущность."""
    from app.domain.epistemology import Predicate, Proposition

    return IntentSemanticField(
        action=ActionType.ATTACK,
        raw_text="Эй! а денег дашь?",
        proposition=Proposition(
            subject_id="player", predicate=Predicate.ATTACKED, object_id=target
        ),
    )


class _FakeLLMClient:
    """LLM-слой: DIALOGUE (реальный класс вопроса)."""

    async def compress_intent(self, raw_text, scene_context, dialogue_session):
        return {
            "action": "DIALOGUE",
            "speech_act": "question",
            "requested_outcome": "give money",
            "semantic_acts": [
                {"type": "QUESTION", "params": {"topic": "give money"}}
            ],
        }


def _compressor_with_llm():

    c = IntentCompressor.__new__(IntentCompressor)
    c._llm_client = _FakeLLMClient()
    return c


def test_phantom_attack_corrected_to_llm_class():
    c = _compressor_with_llm()
    fast = _fast_attack_field("денег")
    # нерезолвнутая сущность ("денег" не в npc_positions) → фантом-детект
    out = c._enrich(fast, {"action": "DIALOGUE"}, {"npc_positions": {}})
    assert out.action != ActionType.ATTACK, (
        f"RC2: фантомный ATTACK не скорректирован (action={out.action})"
    )
    assert out.proposition is None  # фантом снят


def test_real_attack_not_broken():
    """Настоящий ATTACK: пропозиция на резолвнутого NPC — action не трогается."""
    c = _compressor_with_llm()
    from app.domain.epistemology import Predicate, Proposition

    fast = IntentSemanticField(
        action=ActionType.ATTACK,
        raw_text="ударить Горана",
        proposition=Proposition(
            subject_id="player", predicate=Predicate.ATTACKED, object_id="goran"
        ),
    )
    # "goran" резолвнут (в npc_positions) → пропозишн-ветка не срабатывает
    out = c._enrich(
        fast, {"action": "ATTACK"}, {"npc_positions": {"merchant_goran": {}}}
    )
    assert out.action == ActionType.ATTACK


def test_dead_llm_honest_degradation():
    """Мёртвая LLM: compress возвращает fast как есть (ADR-113) —
    фантомный ATTACK остаётся, но это документированная деградация."""

    c = IntentCompressor.__new__(IntentCompressor)

    class _Dead:
        async def compress_intent(self, *a, **k):
            raise RuntimeError("LLM dead")

    c._llm_client = _Dead()
    fast = _fast_attack_field("денег")
    # fast_incomplete: proposition с нерезолвнутой сущностью → True → LLM
    # падает → llm None → fast остаётся (по контракту compress:471)
    # Проверяем контракт _enrich-гейта напрямую: без llm-словаря коррекции нет.
    out = c._enrich(fast, {}, {"npc_positions": {}})
    assert out.action == ActionType.ATTACK  # честная деградация