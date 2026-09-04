# backend/tests/test_reaction_subscriber.py
"""
Тесты ReactionSubscriber — прямые эмоциональные реакции наблюдателей.

Проверяет:
  1. Protocol compliance (name, drain_events, handle)
  2. Модификатор реакции на основе личности NPC
  3. Правила реакций для разных event types
  4. Маршрутизация trust_delta (intent_target для player, social_target для NPC)
  5. Исключение источника события из реакций
  6. Пустые events → пустой результат
  7. perceiving_npcs из shared_context

path: backend/tests/test_reaction_subscriber.py
Назначение: Тесты ReactionSubscriber (Phase8Handler) — эмоциональные реакции наблюдателей
Зависимости: pytest, app.services.events.reaction_subscriber, app.models.phase8, app.models.state_delta, app.domain.events, app.services.events.event_bus
Основные сущности: TestReactionSubscriber, TestReactionModifier, TestReactionRules
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.domain.events import EventDTO
from app.models.phase8 import Phase8Context, Phase8Result
from app.services.events.event_bus import EventBus
from app.services.events.reaction_subscriber import (
    _REACTION_EVENT_TYPES,
    _REACTION_RULES,
    ReactionSubscriber,
    _compute_reaction_modifier,
)

# ── Фикстуры ───────────────────────────────────────────────────────────────


def _make_event(
    event_type: str = "player_attacks",
    source: str = "player",
    intensity: float | None = None,
) -> EventDTO:
    """Создаёт тестовый EventDTO."""
    payload: dict = {}
    if intensity is not None:
        payload["intensity"] = intensity
    return EventDTO(
        id=uuid.uuid4(),
        type=event_type,
        source=source,
        timestamp=0.0,
        payload=payload,
        visibility="public",
        radius=10.0,
        persistence_level="working",
    )


def _make_npc(
    npc_id: str = "npc_1",
    stress: float = 30.0,
    willpower: float = 50.0,
    fear_drive: float = 0.25,
) -> dict:
    """Создаёт тестовый NPC dict."""
    return {
        "id": npc_id,
        "psyche": {
            "stress": stress,
            "willpower": willpower,
        },
        "drives": {
            "control": 0.25,
            "significance": 0.25,
            "fear": fear_drive,
            "desire": 0.25,
        },
    }


class _FakeSharedContext:
    """Минимальный shared_context для тестов."""

    def __init__(
        self,
        perceiving_npcs: list[str] | None = None,
        scene_state: dict | None = None,
    ):
        self.perceiving_npcs = perceiving_npcs
        self.scene_state = scene_state or {}


def _make_ctx(
    all_npcs_raw: list[dict] | None = None,
    shared_context: Any = None,
) -> Phase8Context:
    """Создаёт тестовый Phase8Context."""
    return Phase8Context(
        all_npcs_raw=all_npcs_raw or [_make_npc()],
        all_npc_contexts=[],
        shared_context=shared_context,
        campaign_id="test",
        tick_ctx=None,
    )


def _create_subscriber() -> ReactionSubscriber:
    """Создаёт ReactionSubscriber с моком EventBus."""
    bus = MagicMock(spec=EventBus)
    bus.subscribe = MagicMock()
    return ReactionSubscriber(bus)


# ── Protocol compliance ───────────────────────────────────────────────────


class TestReactionSubscriberProtocol:
    """Проверяет соответствие Phase8Handler Protocol."""

    def test_name_property(self):
        sub = _create_subscriber()
        assert sub.name == "reaction"

    def test_drain_events_returns_list(self):
        sub = _create_subscriber()
        result = sub.drain_events()
        assert isinstance(result, list)

    def test_drain_events_clears_buffer(self):
        sub = _create_subscriber()
        # Ручная инъекция событий в буфер
        sub._pending_events.append(_make_event())
        first = sub.drain_events()
        assert len(first) == 1
        second = sub.drain_events()
        assert len(second) == 0

    def test_handle_returns_phase8_result(self):
        sub = _create_subscriber()
        ctx = _make_ctx()
        result = sub.handle([], ctx)
        assert isinstance(result, Phase8Result)


# ── Пустые события ───────────────────────────────────────────────────────


class TestReactionEmptyEvents:
    """Пустые events → пустой результат."""

    def test_no_events_returns_empty_result(self):
        sub = _create_subscriber()
        ctx = _make_ctx()
        result = sub.handle([], ctx)
        assert result.deltas == []
        assert result.events_processed == 0

    def test_no_perceiving_npcs_returns_empty(self):
        sub = _create_subscriber()
        npc = _make_npc("npc_1")
        # perceiving_npcs=[] — явный пустой список, fallback не сработает
        ctx = _make_ctx(
            all_npcs_raw=[npc],
            shared_context=_FakeSharedContext(perceiving_npcs=[]),
        )
        result = sub.handle([_make_event()], ctx)
        assert result.deltas == []


# ── Модификатор реакции ──────────────────────────────────────────────────


class TestReactionModifier:
    """Проверяет _compute_reaction_modifier на основе личности NPC."""

    def test_average_npc_modifier(self):
        """Средний NPC: stress=50, fear=0.25, willpower=50 → modifier ≈ 0.5."""
        npc = _make_npc(stress=50.0, willpower=50.0, fear_drive=0.25)
        mod = _compute_reaction_modifier(npc)
        # composure=0.5, composure_factor=0.75, fear_factor=1.0, willpower_factor=0.667
        # 0.75 * 1.0 * 0.667 ≈ 0.5
        assert 0.4 < mod < 0.6

    def test_cowardly_npc_higher_modifier(self):
        """Трусливый NPC реагирует сильнее."""
        coward = _make_npc(stress=70.0, willpower=30.0, fear_drive=0.5)
        average = _make_npc(stress=30.0, willpower=50.0, fear_drive=0.25)
        assert _compute_reaction_modifier(coward) > _compute_reaction_modifier(average)

    def test_brave_npc_lower_modifier(self):
        """Храбрый NPC реагирует слабее."""
        brave = _make_npc(stress=10.0, willpower=80.0, fear_drive=0.1)
        average = _make_npc(stress=30.0, willpower=50.0, fear_drive=0.25)
        assert _compute_reaction_modifier(brave) < _compute_reaction_modifier(average)

    def test_missing_fields_uses_defaults(self):
        """Отсутствующие поля → дефолты, не краш."""
        npc = {"id": "minimal"}
        mod = _compute_reaction_modifier(npc)
        assert isinstance(mod, float)
        assert mod > 0


# ── Правила реакций ──────────────────────────────────────────────────────


class TestReactionRules:
    """Проверяет, что правила генерируют корректные дельты."""

    def test_attack_generates_stress_and_fear(self):
        """Атака → стресс + страх + потеря доверия (v3: 3 дельты —
        EMOTION + SOCIAL + PERCEPTION witness через DeltaGate)."""
        sub = _create_subscriber()
        npc = _make_npc("npc_1")
        ctx = _make_ctx(
            all_npcs_raw=[npc],
            shared_context=_FakeSharedContext(perceiving_npcs=["npc_1"]),
        )
        result = sub.handle([_make_event("player_attacks", "player")], ctx)
        assert len(result.deltas) == 3
        # EMOTION дельта (стресс)
        emotion_d = [d for d in result.deltas if d.domain is not None and d.domain.value == "emotion"][0]
        assert emotion_d.npc_id == "npc_1"
        assert emotion_d.stress_delta > 0
        # SOCIAL дельта (страх, доверие)
        social_d = [d for d in result.deltas if d.domain is not None and d.domain.value == "social"][0]
        assert social_d.npc_id == "npc_1"
        assert social_d.fear_delta > 0
        assert social_d.trust_delta < 0
        assert social_d.intent_target == "player"
        # PERCEPTION witness-дельта (E2.0-b/D3: свидетель насилия → threat_gradient)
        perception_d = [d for d in result.deltas if d.domain is not None and d.domain.value == "perception"]
        assert len(perception_d) == 1
        assert perception_d[0].npc_id == "npc_1"
        assert perception_d[0].payload.threat_gradient_delta > 0

    def test_help_reduces_stress_and_increases_trust(self):
        """Помощь → снижение стресса + рост доверия (v2: 2 дельты)."""
        sub = _create_subscriber()
        npc = _make_npc("npc_1")
        ctx = _make_ctx(
            all_npcs_raw=[npc],
            shared_context=_FakeSharedContext(perceiving_npcs=["npc_1"]),
        )
        result = sub.handle([_make_event("help", "player")], ctx)
        assert len(result.deltas) == 2
        # EMOTION дельта
        emotion_d = [d for d in result.deltas if d.domain is not None and d.domain.value == "emotion"][0]
        assert emotion_d.stress_delta < 0
        # SOCIAL дельта
        social_d = [d for d in result.deltas if d.domain is not None and d.domain.value == "social"][0]
        assert social_d.trust_delta > 0

    def test_saved_life_reduces_fear(self):
        """Спасение жизни → снижение страха + рост доверия (v2: 2 дельты)."""
        sub = _create_subscriber()
        npc = _make_npc("npc_1")
        ctx = _make_ctx(
            all_npcs_raw=[npc],
            shared_context=_FakeSharedContext(perceiving_npcs=["npc_1"]),
        )
        result = sub.handle([_make_event("saved_life", "player")], ctx)
        # saved_life даёт stress и fear/trust → 2 дельты
        assert len(result.deltas) == 2
        # Ищем SOCIAL дельту (fear, trust)
        social_d = [d for d in result.deltas if d.domain is not None and d.domain.value == "social"][0]
        assert social_d.fear_delta < 0
        assert social_d.trust_delta > 0

    def test_unknown_event_type_skipped(self):
        """Неизвестный event_type → нет дельт."""
        sub = _create_subscriber()
        npc = _make_npc("npc_1")
        ctx = _make_ctx(
            all_npcs_raw=[npc],
            shared_context=_FakeSharedContext(perceiving_npcs=["npc_1"]),
        )
        result = sub.handle([_make_event("unknown", "player")], ctx)
        assert result.deltas == []


# ── Маршрутизация trust ──────────────────────────────────────────────────


class TestReactionTrustRouting:
    """Проверяет маршрутизацию trust_delta по источнику события."""

    def test_player_source_uses_intent_target(self):
        """Действие игрока → intent_target="player" (в SOCIAL дельте)."""
        sub = _create_subscriber()
        npc = _make_npc("npc_1")
        ctx = _make_ctx(
            all_npcs_raw=[npc],
            shared_context=_FakeSharedContext(perceiving_npcs=["npc_1"]),
        )
        result = sub.handle([_make_event("player_attacks", "player")], ctx)
        social_d = [d for d in result.deltas if d.domain is not None and d.domain.value == "social"][0]
        assert social_d.intent_target == "player"
        assert social_d.social_target is None

    def test_npc_source_uses_social_target(self):
        """Действие NPC → social_target=npc_id (в SOCIAL дельте)."""
        sub = _create_subscriber()
        source_npc = _make_npc("npc_attacker")
        observer_npc = _make_npc("npc_observer")
        ctx = _make_ctx(
            all_npcs_raw=[source_npc, observer_npc],
            shared_context=_FakeSharedContext(perceiving_npcs=["npc_observer"]),
        )
        result = sub.handle([_make_event("combat", source="npc_attacker")], ctx)
        # npc_attacker — источник, исключён. npc_observer — наблюдатель
        # v3: 3 дельты (PERCEPTION + EMOTION + SOCIAL)
        assert len(result.deltas) == 3
        social_d = [d for d in result.deltas if d.domain is not None and d.domain.value == "social"][0]
        assert social_d.npc_id == "npc_observer"
        assert social_d.social_target == "npc_attacker"
        assert social_d.intent_target is None


# ── Исключение источника ─────────────────────────────────────────────────


class TestReactionSourceExclusion:
    """Источник события не реагирует на собственное действие."""

    def test_source_npc_excluded(self):
        """NPC-источник не получает дельт от своего действия."""
        sub = _create_subscriber()
        npc = _make_npc("npc_1")
        ctx = _make_ctx(
            all_npcs_raw=[npc],
            shared_context=_FakeSharedContext(perceiving_npcs=["npc_1"]),
        )
        result = sub.handle([_make_event("combat", source="npc_1")], ctx)
        assert result.deltas == []

    def test_player_source_excluded_as_npc(self):
        """Игрок не в all_npcs_raw → не получит дельту (корректно)."""
        sub = _create_subscriber()
        npc = _make_npc("npc_1")
        ctx = _make_ctx(
            all_npcs_raw=[npc],
            shared_context=_FakeSharedContext(perceiving_npcs=["npc_1"]),
        )
        result = sub.handle([_make_event("player_attacks", source="player")], ctx)
        # v3: 3 дельты (EMOTION + SOCIAL + PERCEPTION witness) для npc_1,
        # player не в all_npcs_raw
        assert all(d.npc_id != "player" for d in result.deltas)
        assert len(result.deltas) == 3


# ── Множественные наблюдатели ────────────────────────────────────────────


class TestReactionMultipleObservers:
    """Несколько наблюдателей → дельты для каждого."""

    def test_two_observers_get_deltas(self):
        sub = _create_subscriber()
        npc_a = _make_npc("npc_a")
        npc_b = _make_npc("npc_b")
        ctx = _make_ctx(
            all_npcs_raw=[npc_a, npc_b],
            shared_context=_FakeSharedContext(perceiving_npcs=["npc_a", "npc_b"]),
        )
        result = sub.handle([_make_event("player_attacks")], ctx)
        # v3: 2 наблюдателя * 3 домена (EMOTION + SOCIAL + PERCEPTION) = 6 дельт
        assert len(result.deltas) == 6
        npc_ids = {d.npc_id for d in result.deltas}
        assert npc_ids == {"npc_a", "npc_b"}

    def test_different_personalities_different_deltas(self):
        """Разные личности → разные величины дельт."""
        sub = _create_subscriber()
        coward = _make_npc("coward", stress=70, willpower=30, fear_drive=0.5)
        brave = _make_npc("brave", stress=10, willpower=80, fear_drive=0.1)
        ctx = _make_ctx(
            all_npcs_raw=[coward, brave],
            shared_context=_FakeSharedContext(perceiving_npcs=["coward", "brave"]),
        )
        result = sub.handle([_make_event("player_attacks")], ctx)
        # v2: фильтруем EMOTION дельты для проверки stress_delta
        emotion_deltas = [d for d in result.deltas if d.domain is not None and d.domain.value == "emotion"]
        by_id = {d.npc_id: d for d in emotion_deltas}
        # Трус получает больше стресса
        assert by_id["coward"].stress_delta > by_id["brave"].stress_delta


# ── Perceiving NPCs fallback ─────────────────────────────────────────────


class TestReactionPerceivingFallback:
    """Fallback на всех NPC, если perceiving_npcs не установлен."""

    def test_fallback_all_npcs_when_no_perceiving(self):
        sub = _create_subscriber()
        npc_a = _make_npc("npc_a")
        npc_b = _make_npc("npc_b")
        # shared_context без perceiving_npcs
        ctx = _make_ctx(
            all_npcs_raw=[npc_a, npc_b],
            shared_context=_FakeSharedContext(perceiving_npcs=None),
        )
        result = sub.handle([_make_event("player_attacks")], ctx)
        # v3: 2 NPC * 3 домена (EMOTION + SOCIAL + PERCEPTION witness)
        assert len(result.deltas) == 6

    def test_fallback_all_npcs_when_no_shared_context(self):
        sub = _create_subscriber()
        npc_a = _make_npc("npc_a")
        ctx = _make_ctx(
            all_npcs_raw=[npc_a],
            shared_context=None,
        )
        result = sub.handle([_make_event("player_attacks")], ctx)
        # v3: 1 NPC * 3 домена (EMOTION + SOCIAL + PERCEPTION witness)
        assert len(result.deltas) == 3


# ── Интенсивность ────────────────────────────────────────────────────────


class TestReactionIntensity:
    """Интенсивность масштабирует дельты."""

    def test_high_intensity_larger_deltas(self):
        sub = _create_subscriber()
        npc = _make_npc("npc_1")
        ctx = _make_ctx(
            all_npcs_raw=[npc],
            shared_context=_FakeSharedContext(perceiving_npcs=["npc_1"]),
        )
        low = sub.handle([_make_event(intensity=0.3)], ctx)
        high = sub.handle([_make_event(intensity=1.0)], ctx)
        # v2: Фильтруем EMOTION дельты для сравнения stress_delta
        low_emotion = [d for d in low.deltas if d.domain is not None and d.domain.value == "emotion"][0]
        high_emotion = [d for d in high.deltas if d.domain is not None and d.domain.value == "emotion"][0]
        assert high_emotion.stress_delta > low_emotion.stress_delta

    def test_intensity_from_payload(self):
        """Интенсивность из payload.priority."""
        sub = _create_subscriber()
        npc = _make_npc("npc_1")
        ctx = _make_ctx(
            all_npcs_raw=[npc],
            shared_context=_FakeSharedContext(perceiving_npcs=["npc_1"]),
        )
        event = _make_event(intensity=0.5)
        result = sub.handle([event], ctx)
        # v3: EMOTION + SOCIAL + PERCEPTION witness (player_attacks)
        assert len(result.deltas) == 3
        # Проверяем EMOTION дельту
        emotion_d = [d for d in result.deltas if d.domain is not None and d.domain.value == "emotion"][0]
        assert emotion_d.stress_delta != 0.0


# ── Реакционные типы событий ─────────────────────────────────────────────


class TestReactionEventTypes:
    """Проверяет, что подписка покрывает ключевые типы."""

    def test_reaction_types_covers_threats(self):
        """Все угрозы покрыты."""
        threat_types = {
            "player_attacks",
            "player_attack",
            "player_attacked",
            "player_threatens",
            "combat",
            "intimidation",
            "betrayal",
        }
        covered = {et.value.lower() for et in _REACTION_EVENT_TYPES}
        assert threat_types.issubset(covered)

    def test_reaction_types_covers_positive(self):
        """Позитивные события покрыты."""
        positive = {"help", "saved_life"}
        covered = {et.value for et in _REACTION_EVENT_TYPES}
        assert positive.issubset(covered)

    def test_reaction_rules_match_event_types(self):
        """Для каждого _REACTION_EVENT_TYPES есть правило."""
        for et in _REACTION_EVENT_TYPES:
            assert et.value.lower() in _REACTION_RULES, f"Нет правила для {et.value}"
