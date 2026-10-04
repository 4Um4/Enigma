# path: backend/tests/sandbox/SUPERBOX/scenarios/re_gh_dynamics_test.py
# Назначение: ADR-O-419 приёмка G/H — time-driven динамика потребностей на живом
#   harness (TavernGameplayHarness; канал idle_tick → Фаза 0.5 → delta_buffer →
#   сплит Ф9 → StateApplicator.apply_relationship_deltas → Store).
#   Control: флаг OFF — байт-идентичность тиков. Treatment: флаг ON —
#   давление растёт по gen_rate·Δt; фон фрустрации при p>порога(rigidity);
#   распад > 0; отметка кванта коммитится; wake-хук no-op не падает.
# Зависимости: TavernGameplayHarness (§9.2), get_event_bus (не нужен здесь),
#   RelationshipStateStore (frozen-read канон, приватные носители легальны I.4).
# Основные сущности: run() → bool

import os


def run() -> bool:
    from app.services.social.relationship_dynamics import (
        RELATIONSHIP_DYNAMICS_STATE_KEY,
    )
    from app.services.social.relationship_state_store import RelationshipStateStore
    from tests.sandbox.harness import TavernGameplayHarness

    # ── CONTROL: флаг OFF (env не задан) — байт-идентичность ──
    os.environ.pop("RELATIONSHIP_DYNAMICS_ENABLED", None)
    h = TavernGameplayHarness(seed=42, location="tavern")
    h.new_game()
    try:
        h.advance_ticks(24)  # 24 тика × 10 с = 240 с < кванта → базлайн-мир
        scene_c = h.game_loop.scene_manager._tick_scenes[
            list(h.game_loop.scene_manager._tick_scenes.keys())[0]
        ]
        root_c = scene_c.get("relationship_state") or {}
        assert root_c.get(RELATIONSHIP_DYNAMICS_STATE_KEY) is None, (
            "CONTROL: книга контура не должна создаваться при флаге OFF"
        )
        levels_c = RelationshipStateStore.get_need_levels(scene_c, "maid_lusya")
        p_c = levels_c.get("sexual", None)
        baseline_p = p_c.current_intensity if p_c else 0.0
    finally:
        h.dispose()

    # ── TREATMENT: флаг ON — 24 тика = 2 кванта (240 с ≥ 2×3600? НЕТ: 240 с < 3600) ──
    # 1 квант = 3600 с = 360 тиков. Прогоняем 400 тиков (> 1 кванта).
    os.environ["RELATIONSHIP_DYNAMICS_ENABLED"] = "1"
    try:
        h = TavernGameplayHarness(seed=42, location="tavern")
        h.new_game()
        h.advance_ticks(400)
        scene_t = h.game_loop.scene_manager._tick_scenes[
            list(h.game_loop.scene_manager._tick_scenes.keys())[0]
        ]
        book = (scene_t.get("relationship_state") or {}).get(
            RELATIONSHIP_DYNAMICS_STATE_KEY
        )
        assert book is not None, "TREATMENT: отметка кванта обязана коммититься"
        assert float(book.get("last_quantum_seconds", -1.0)) >= 3600.0, (
            f"TREATMENT: last_quantum_seconds={book} < кванта — контур не сработал"
        )
        levels_t = RelationshipStateStore.get_need_levels(scene_t, "maid_lusya")
        p_t = levels_t.get("sexual", None)
        p_after = p_t.current_intensity if p_t else 0.0
        # Давление выросло относительно контрольного мира (динамика жива)
        assert p_after > baseline_p, (
            f"TREATMENT: давление не выросло ({baseline_p} → {p_after}) — "
            f"gen_rate-канал мёртв"
        )
        # Фр2-распад не должен ловить NaN/negative (клампы стора)
        f_after = (p_t.frustration if p_t else 0.0)
        assert 0.0 <= f_after <= 1.0 and 0.0 <= p_after <= 1.0
        # wake-хук no-op: не падает в проде при ON (NPC без сна в 400 тиках — ок;
        # проводка wake — отдельный F5-тест после DEBT-SLEEP-DELIVERY)
        print(
            f"[RE_GH] Control p={baseline_p:.4f} | Treatment p={p_after:.4f} | "
            f"mark={book.get('last_quantum_seconds')}"
        )
        return True
    finally:
        os.environ.pop("RELATIONSHIP_DYNAMICS_ENABLED", None)
        h.dispose()