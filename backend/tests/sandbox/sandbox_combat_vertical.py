# backend/tests/sandbox/sandbox_combat_vertical.py
# Назначение: Осциллограф Каузальной Боевой Физики
# Проверяет: EventDTO(PLAYER_ATTACKED) -> ImpactEngine -> PhysiologyPayload(shock_impulse) -> ReactionSubscriber -> EmotionPayload(fear)
"""
Запуск: python backend/tests/sandbox/sandbox_combat_vertical.py

Вертикальный срез боевого пайплайна. Если страх не рождается из боли —
система мертва, и NPC будут улыбаться с отрезанными ушами.

TODO:
- Добавить больше логов и метрик для диагностики на каждом этапе.
- В будущем расширить тесты для проверки разных типов ударов, зон, и эмоциональных реакций (паника, гнев и т.д.).

"""

import logging
import os
import sys

# Добавляем папку backend в путь для импортов
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.delta_payloads import PhysiologyPayload
from app.models.idle_tick import NPCStateSnapshot
from app.models.impact import ImpactIntentDTO
from app.services.combat.impact_engine import resolve_physical_impact

log = logging.getLogger("COMBAT_SANDBOX")
logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")


def run_combat_sandbox() -> bool:
    """Запуск сценария Осциллографа Боевки. Возвращает True, если каузальный каскад работает."""
    log.info("⚡ Starting Combat Physiology Oscilloscope...")

    # 1. ДАННЫЕ: Игрок бьёт Люсю (как в логах)
    target_id = "maid_lusya"
    actor_id = "player"

    # Снапшот цели (Строго по контракту NPCStateSnapshot)
    target_snapshot = NPCStateSnapshot(
        npc_id=target_id,
        hp=80.0,
        max_hp=80.0,
        pain=0.0,
        fatigue=0.0,
        blood_loss=0.0,
        consciousness=1.0,
        injuries_by_zone={},
        base_abilities={"dexterity": 10.0, "strength": 10.0, "constitution": 10.0},
        modifiers={},
        statuses=[],
        stress=0.0,
        relationship_cache={"player": {"trust": 50.0, "fear": 20.0}},
        base_values={"player": 50.0},
        faction_affiliations=[],
    )

    # 2. ФОРМИРОВАНИЕ ИНТЕНТА: "Я откусываю люси ухо" -> PLAYER_ATTACKED
    impact_intent = ImpactIntentDTO(
        actor_id=actor_id,
        target_id=target_id,
        damage_type="slash",  # Укус/отрезание
        target_zone="head_ear_l",
        force=80.0,  # Высокая сила
    )

    # Снапшот атакующего (игрок)
    attacker_snapshot = NPCStateSnapshot(
        npc_id=actor_id,
        hp=100.0,
        max_hp=100.0,
        pain=0.0,
        fatigue=0.0,
        blood_loss=0.0,
        consciousness=1.0,
        injuries_by_zone={},
        base_abilities={"dexterity": 12.0, "strength": 15.0, "constitution": 12.0},
        modifiers={},
        statuses=[],
        stress=0.0,
        relationship_cache={},
        base_values={},
        faction_affiliations=[],
    )

    # ==========================================
    # 3. PHYSICAL LAYER: ImpactEngine (Pure Function)
    # ==========================================
    log.info(
        f"[PHYSICAL] Actor={actor_id} attacks Target={target_id} (force={impact_intent.force}, type={impact_intent.damage_type})"
    )

    try:
        # Сигнатура: (attacker, defender, intent, rng_seed)
        phys_deltas = resolve_physical_impact(
            attacker=attacker_snapshot, defender=target_snapshot, intent=impact_intent, rng_seed=42
        )
    except Exception as e:
        log.error(f"❌ FATAL: ImpactEngine crashed! Error: {e}")
        return False

    if not phys_deltas:
        log.error("❌ FATAL: ImpactEngine returned NO deltas. Combat is completely dead.")
        return False

    total_shock = 0.0
    for d in phys_deltas:
        payload = d.payload
        if isinstance(payload, PhysiologyPayload):
            log.info(
                f"  -> PHYSIOLOGY: hp_delta={payload.hp_delta:.1f}, pain={payload.pain_delta:.1f}, shock={payload.shock_impulse:.2f}, bleed={payload.blood_loss_delta:.2f}"
            )
            if payload.shock_impulse > 0:
                log.info("  ✅ Shock impulse generated!")
                total_shock += payload.shock_impulse
            else:
                log.warning("  ⚠️ NO SHOCK IMPULSE! ReactionSubscriber will be blind.")

    if total_shock == 0:
        log.error("❌ FATAL: Physical impact produced NO shock. Emotional cascade impossible.")
        return False

    # ==========================================
    # 4. COGNITIVE LAYER: ReactionSubscriber Logic (Каскад Force -> Pain -> Shock -> Emotion)
    # ==========================================
    log.info(f"[COGNITIVE] Processing shock_impulse={total_shock:.2f}")

    # Логика ADR-016: shock > 0.5 = panic, else fear
    emotion_tag = "fear"
    if total_shock > 0.5:
        emotion_tag = "panic"
        log.info("  -> EMOTION TAG: Panic triggered (shock > 0.5)!")
    else:
        log.info("  -> EMOTION TAG: Standard fear.")

    # Базовая формула реакции (из ReactionSubscriber)
    # stress_delta += shock * 30.0 * modifier, fear_delta += shock * 15.0 * modifier
    fear_delta = total_shock * 15.0
    stress_delta = total_shock * 30.0

    log.info(f"  -> EMOTION PAYLOAD: fear_delta={fear_delta:.2f}, stress_delta={stress_delta:.2f}, tag={emotion_tag}")

    if fear_delta > 0:
        log.info("✅ COMBAT PIPELINE ALIVE: Pain successfully generates Fear!")
        return True
    else:
        log.error("❌ FATAL: COMBAT PIPELINE DEAD: Pain does NOT generate Fear.")
        return False


if __name__ == "__main__":
    success = run_combat_sandbox()
    sys.exit(0 if success else 1)
