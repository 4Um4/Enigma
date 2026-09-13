# path: /project/backend/tests/gameplay/test_p6_discovery_bridge.py
"""
Файл: backend/tests/gameplay/test_p6_discovery_bridge.py
Назначение: P6 Шаг 1 — ядро DiscoveryBridge (T1/T2/T4/T9).
    T1 позитив: REVEAL -> IDENTIFIED + LevelChangeEvent + mark_discovered
    T2 идемпотентность: повторный REVEAL; HINT при CLUE
    T4 негатив: DENY/REDIRECT -> observation only
    T9 чистота: map_surface — детерминизм + немутация входа
Зависимости: app.domain.disclosure, app.domain.player_epistemics,
    app.models.player_epistemic_state,
    app.services.player_cognition.discovery_bridge
"""

from app.domain.disclosure import DisclosureLevel
from app.domain.player_epistemics import (
    CLUE,
    IDENTIFIED,
    UNKNOWN,
    SurfaceEvent,
    SurfaceKind,
)
from app.models.player_epistemic_state import PlayerEpistemicState
from app.services.player_cognition.discovery_bridge import (
    DiscoveryBridge,
    map_surface,
)


class _FakeTruth:
    """Duck-тип TruthState по контракту mark_discovered (гвард + set).
    Реальная модель не конструируется: шаг не зависит от формы Secret."""

    def __init__(self, *secret_ids: str) -> None:
        self.secrets = {sid: object() for sid in secret_ids}
        self.discovered_secrets = set()

    def mark_discovered(self, secret_id: str) -> None:
        if secret_id in self.secrets:
            self.discovered_secrets.add(secret_id)


def _reveal_surface() -> SurfaceEvent:
    return SurfaceEvent(
        kind=SurfaceKind.DIALOGUE_OUTCOME,
        tick=5,
        source_id="borko",
        secret_id="borko_negligence",
        disclosure_level=DisclosureLevel.REVEAL,
        subject_hint="караван",
    )


# ── T1: позитив ─────────────────────────────────────────────────────────
def test_t1_reveal_to_identified_with_event_and_mark() -> None:
    state = PlayerEpistemicState()
    truth = _FakeTruth("borko_negligence")
    bridge = DiscoveryBridge(state, truth)

    updates = bridge.process(_reveal_surface())

    assert len(updates) == 1
    update = updates[0]
    assert update.from_level == UNKNOWN
    assert update.to_level == IDENTIFIED
    assert update.level_changed is True
    assert update.marked_discovered is True
    assert update.level_change is not None
    assert update.level_change.from_level == UNKNOWN
    assert update.level_change.to_level == IDENTIFIED
    assert update.level_change.surface_kind == SurfaceKind.DIALOGUE_OUTCOME
    assert "borko_negligence" in truth.discovered_secrets
    assert state.level("borko_negligence") == IDENTIFIED
    assert len(state.observations) == 1
    assert state.observations[0].secret_id == "borko_negligence"


# ── T2: идемпотентность ─────────────────────────────────────────────────
def test_t2_repeated_reveal_and_hint_at_clue_are_idempotent() -> None:
    state = PlayerEpistemicState()
    truth = _FakeTruth("borko_negligence")
    bridge = DiscoveryBridge(state, truth)

    bridge.process(_reveal_surface())
    updates_repeat = bridge.process(_reveal_surface())
    assert updates_repeat[0].level_changed is False
    assert updates_repeat[0].marked_discovered is False
    assert state.level("borko_negligence") == IDENTIFIED
    # observation накапливается (журнал игрока), уровень — нет
    assert len(state.observations) == 2

    # HINT при CLUE: целевой уровень не выше текущего -> перехода нет
    state2 = PlayerEpistemicState()
    truth2 = _FakeTruth("borko_negligence")
    bridge2 = DiscoveryBridge(state2, truth2)
    bridge2.process(
        SurfaceEvent(
            kind=SurfaceKind.DIALOGUE_OUTCOME,
            tick=6,
            source_id="borko",
            secret_id="borko_negligence",
            disclosure_level=DisclosureLevel.PARTIAL,
        )
    )
    assert state2.level("borko_negligence") == CLUE
    updates_hint = bridge2.process(
        SurfaceEvent(
            kind=SurfaceKind.DIALOGUE_OUTCOME,
            tick=7,
            source_id="borko",
            secret_id="borko_negligence",
            disclosure_level=DisclosureLevel.HINT,
        )
    )
    assert state2.level("borko_negligence") == CLUE
    assert updates_hint[0].level_changed is False
    assert updates_hint[0].marked_discovered is False
    assert truth2.discovered_secrets == set()


# ── T4: негатив ─────────────────────────────────────────────────────────
def test_t4_deny_and_redirect_are_observation_only() -> None:
    state = PlayerEpistemicState()
    truth = _FakeTruth("borko_negligence")
    bridge = DiscoveryBridge(state, truth)

    for level in (DisclosureLevel.DENY, DisclosureLevel.REDIRECT):
        updates = bridge.process(
            SurfaceEvent(
                kind=SurfaceKind.DIALOGUE_OUTCOME,
                tick=8,
                source_id="borko",
                secret_id="borko_negligence",
                disclosure_level=level,
                subject_hint="караван",
            )
        )
        assert updates[0].level_changed is False
        assert updates[0].marked_discovered is False
        assert updates[0].level_change is None
        assert updates[0].observation is not None

    assert state.level("borko_negligence") == UNKNOWN
    assert truth.discovered_secrets == set()
    assert len(state.observations) == 2


# ── T9: чистота ─────────────────────────────────────────────────────────
def test_t9_map_surface_is_pure_and_deterministic() -> None:
    surface = _reveal_surface()
    snapshot = (
        surface.kind,
        surface.tick,
        surface.source_id,
        surface.secret_id,
        surface.disclosure_level,
        surface.content_class,
        surface.subject_hint,
    )

    assert map_surface(surface) == map_surface(surface)  # детерминизм

    # немутация входа (frozen DTO: поля неизменны после вызова)
    assert (
        surface.kind,
        surface.tick,
        surface.source_id,
        surface.secret_id,
        surface.disclosure_level,
        surface.content_class,
        surface.subject_hint,
    ) == snapshot

    # два прогона на чистых state/truth дают структурно идентичные updates
    surface_a = _reveal_surface()
    surface_b = _reveal_surface()
    result_a = DiscoveryBridge(
        PlayerEpistemicState(), _FakeTruth("borko_negligence")
    ).process(surface_a)
    result_b = DiscoveryBridge(
        PlayerEpistemicState(), _FakeTruth("borko_negligence")
    ).process(surface_b)
    assert result_a == result_b
    assert surface_a == surface_b
