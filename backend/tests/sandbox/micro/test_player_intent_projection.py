"""
path: backend/tests/sandbox/micro/test_player_intent_projection.py
Назначение: G1 — контракты build_intent_projection (observation-only: без мутаций источника, только фактически существующие поля IntentResolution)
Зависимости: app.services.game_loop.phase_1_input
Основные сущности: build_intent_projection, resolve_player_intent

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_player_intent_projection.py -v --tb=short; cd ..
"""

import copy

from app.domain.intent_profile import ActionType, IntentSemanticField
from app.services.game_loop.phase_1_input import (
    build_intent_projection,
    resolve_player_intent,
)

_ALLOWED_KEYS = {
    "action", "target", "semantic_action", "target_reference", "target_id",
    "actor_id", "condition", "tool_reference", "target_zone", "proposition",
    "addressee", "zone_raw",
}


def _make_semantic_field() -> IntentSemanticField:
    # Production-путь (turn_pipeline:320→365): compressor возвращает поле.
    # Каноническое поле `action` (обязательное), НЕ deprecated-alias action_type.
    return IntentSemanticField(
        action=ActionType.ATTACK,
        raw_text="ударить Люсю",
        target="Люся",
    )


def _make_resolution():
    # Путь идентичен production: semantic_field передаётся ЯВНО;
    # player_dict=None — легальный early-return (pressure не вычисляется);
    # scene_context=None → Слой 2 честно вернёт "" (None-guard резолвера).
    # target="maid_lusya" — как в production: результат TARGET-extractor'а.
    return resolve_player_intent(
        raw_action="ударить Люсю",
        action_type="player_attacks",
        target="maid_lusya",
        player_dict=None,
        scene_context=None,
        semantic_field=_make_semantic_field(),
    )


def test_none_resolution_projects_none():
    assert build_intent_projection(None) is None


def test_factory_projection_structure():
    proj = build_intent_projection(_make_resolution())
    assert proj is not None
    assert set(proj.keys()) <= _ALLOWED_KEYS
    # G2-триада в данных: raw-ссылка vs extractor-цель vs Слой 2.
    # Расхождение трёх target-полей = то, что проекция обязана показывать.
    assert proj["action"] == "ATTACK"           # каноническое (fallback не сработал)
    assert proj["semantic_action"] == "ATTACK"  # семантика компрессора
    assert proj["target"] == "maid_lusya"       # extractor-результат (fallback Слоя 2)
    assert proj["target_reference"] == "Люся"   # сырая ссылка из текста
    assert proj["target_id"] == ""              # Слой 2 не резолвил (scene_context=None)
    assert proj["actor_id"] == "player"         # дефолт резолвера актора


def test_projection_does_not_mutate_source():
    resolution = _make_resolution()
    before = copy.deepcopy(resolution)
    proj = build_intent_projection(resolution)
    assert proj is not None
    proj["action"] = "MUTATED"
    assert resolution == before  # проекция не держит живых ссылок


def test_projection_rebuild_equal_not_identical():
    p1 = build_intent_projection(_make_resolution())
    p2 = build_intent_projection(_make_resolution())
    assert p1 == p2
    assert p1 is not p2


def test_uncertain_fallback_pair_and_key_omission():
    # UNCERTAIN → classifier-fallback: action берётся из action_type,
    # semantic_action остаётся "UNCERTAIN". Пара видна в проекции —
    # диагностическая ценность (оговорка Мастера по патчу 7).
    _sf = IntentSemanticField(action=ActionType.UNCERTAIN, raw_text="что-то странное")
    resolution = resolve_player_intent(
        raw_action="что-то странное",
        action_type="player_interacts",
        target="",
        player_dict=None,
        scene_context=None,
        semantic_field=_sf,
    )
    proj = build_intent_projection(resolution)
    assert proj is not None
    assert proj["action"] == "player_interacts"   # fallback на classifier
    assert proj["semantic_action"] == "UNCERTAIN" # сырое значение компрессора
    # §ENIGMA-003: значение никогда не существовало (None) → ключ опущен
    assert "target_reference" not in proj
    # Резолвер Слоя 2 ОТРАБОТАЛ и вернул "" — это факт «нет совпадения»,
    # не отсутствие поля. target_id="" (не None) → ключ присутствует.
    # Различие None vs "" = сигнал «запускался/не запускался» для G2.
    assert proj["target_id"] == ""