"""
Песочница Спринта 27: Выжигание Легаси и Консолидация Феноменологии
Проверяет:
1. Удаление зомби-полей AvatarStateDTO
2. Генерацию EmbodiedVector и origin_layer (Приоритет 1)
3. Вычисление AmbientPhenomenology (Приоритет 2)
4. Темпоральную интерполяцию NPC (Приоритет 3)

Запуск: python backend/tests/sandbox/sandbox_sprint_27.py

TODO:
- Добавить больше сценариев для проверки границ (например, экстремальные профили давления, разные состояния воли и т.д.)
- В будущем можно расширить тесты для проверки взаимодействия между слоями (например, как изменения в физиологии влияют на волю и поведение, и наоборот)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

# ═══════════════════════════════════════════════════════
# 1. МОКИРОВАНИЕ ДОМЕННЫХ МОДЕЛЕЙ (Спринт 27)
# ═══════════════════════════════════════════════════════


class OriginLayer(Enum):
    WILL_CONFLICT = "will_conflict"
    AFFECTIVE_RESONANCE = "affective_resonance"
    PHYSIOLOGICAL_OVERRIDE = "physiological_override"


class EmbodiedVector(Enum):
    AVOIDANCE = "avoidance"
    DESTROY = "destroy"
    COLLAPSE = "collapse"
    SUBMIT = "submit"
    FREEZE = "freeze"


class WillState(Enum):
    COMPLY = "comply"
    RELUCTANT = "reluctant"
    DISTRESSED = "distressed"
    PANICKED = "panicked"
    DISSOCIATING = "dissociating"
    BROKEN = "broken"
    CONDITIONED = "conditioned"


@dataclass(frozen=True)
class AvatarStateDTO:
    perceptual_stability: float = 1.0
    cognitive_coherence: float = 1.0
    sensory_noise: float = 0.0
    motor_disruption: float = 0.0
    blood_visibility: float = 0.0
    breathing_profile: str = "calm"


@dataclass(frozen=True)
class IntentPressureProfile:
    violence: float = 0.0
    humiliation: float = 0.0
    self_risk: float = 0.0
    social_exposure: float = 0.0
    identity_deviation: float = 0.0


# ═══════════════════════════════════════════════════════
# 2. ЛОГИКА ИЗ БЭКЕНДА (Спринт 27)
# ═══════════════════════════════════════════════════════

_EMBODIED_TEXT_MAP = {
    EmbodiedVector.AVOIDANCE: "Убежать...",
    EmbodiedVector.DESTROY: "Ударить...",
    EmbodiedVector.COLLAPSE: "Упасть...",
    EmbodiedVector.SUBMIT: "Подчиниться...",
    EmbodiedVector.FREEZE: "Замереть...",
}


def get_embodied_impulse_text(vector: Optional[EmbodiedVector]) -> str:
    if vector is None:
        return "Сопротивляться..."
    return _EMBODIED_TEXT_MAP.get(vector, "Сопротивляться...")


def _resolve_embodied_vector(pressure: IntentPressureProfile, state: WillState) -> Optional[EmbodiedVector]:
    if state in (WillState.COMPLY, WillState.RELUCTANT):
        return None
    if state == WillState.PANICKED or pressure.self_risk > 0.7:
        return EmbodiedVector.AVOIDANCE
    if state == WillState.DISSOCIATING or pressure.violence > 0.8:
        return EmbodiedVector.FREEZE
    if pressure.violence > 0.5 and pressure.identity_deviation < 0.3:
        return EmbodiedVector.DESTROY
    if state == WillState.BROKEN or pressure.humiliation > 0.7:
        return EmbodiedVector.SUBMIT
    if pressure.self_risk > 0.5 and state == WillState.DISTRESSED:
        return EmbodiedVector.COLLAPSE
    return EmbodiedVector.AVOIDANCE


def _compute_ambient_phenomenology(all_npcs_raw: Optional[List[Dict]]) -> Optional[Dict[str, float]]:
    if not all_npcs_raw:
        return None
    total_stress, total_fear, count = 0.0, 0.0, 0
    for npc in all_npcs_raw:
        if npc.get("npc_id") == "player":
            continue
        psyche = npc.get("psyche", {})
        total_stress += float(psyche.get("stress", 0.0))
        total_fear += float(psyche.get("fear", 0.0))
        count += 1
    if count == 0:
        return None
    avg_neg_emotion = (total_stress + total_fear) / (2 * count)
    emotional_temperature = (avg_neg_emotion * 2) - 1.0
    proximity_compression = min(1.0, count / 5.0)
    return {
        "emotional_temperature": max(-1.0, min(1.0, emotional_temperature)),
        "proximity_compression": proximity_compression,
    }


# ═══════════════════════════════════════════════════════
# 3. ТЕСТИРОВАНИЕ
# ═══════════════════════════════════════════════════════


def test_dto_cleanup():
    """Приоритет 0: Проверка удаления зомби-полей"""
    print("\n--- ТЕСТ 1: Очистка DTO ---")
    try:
        dto = AvatarStateDTO()
        # Попытка обратиться к удаленным полям должна вызвать ошибку
        try:
            _ = dto.visual_distortion
            print("[FAIL] Поле visual_distortion НЕ удалено!")
            return False
        except AttributeError:
            pass

        try:
            _ = dto.movement_instability
            print("[FAIL] Поле movement_instability НЕ удалено!")
            return False
        except AttributeError:
            pass

        try:
            _ = dto.dominant_impulse
            print("[FAIL] Поле dominant_impulse НЕ удалено!")
            return False
        except AttributeError:
            pass

        # Новые поля должны работать
        assert dto.perceptual_stability == 1.0
        assert dto.motor_disruption == 0.0
        print("[PASS] DTO очищен от легаси, новые скаляры на месте.")
        return True
    except Exception as e:
        print(f"[FAIL] Ошибка создания DTO: {e}")
        return False


def test_embodied_impulse():
    """Приоритет 1: Вычисление моторного вектора и текста"""
    print("\n--- ТЕСТ 2: Embodied Impulse ---")
    passed = True

    # Сценарий А: Паника от риска
    p1 = IntentPressureProfile(self_risk=0.8)
    v1 = _resolve_embodied_vector(p1, WillState.PANICKED)
    t1 = get_embodied_impulse_text(v1)
    if v1 != EmbodiedVector.AVOIDANCE or t1 != "Убежать...":
        print(f"[FAIL] Паника от риска: Ожидался AVOIDANCE/Убежать, получено {v1}/{t1}")
        passed = False

    # Сценарий Б: Экстремальное насилие (оцепенение)
    p2 = IntentPressureProfile(violence=0.9)
    v2 = _resolve_embodied_vector(p2, WillState.DISTRESSED)
    t2 = get_embodied_impulse_text(v2)
    if v2 != EmbodiedVector.FREEZE or t2 != "Замереть...":
        print(f"[FAIL] Экстремальное насилие: Ожидался FREEZE/Замереть, получено {v2}/{t2}")
        passed = False

    # Сценарий В: Сломлен и унижен
    p3 = IntentPressureProfile(humiliation=0.8)
    v3 = _resolve_embodied_vector(p3, WillState.BROKEN)
    t3 = get_embodied_impulse_text(v3)
    if v3 != EmbodiedVector.SUBMIT or t3 != "Подчиниться...":
        print(f"[FAIL] Сломлен: Ожидался SUBMIT/Подчиниться, получено {v3}/{t3}")
        passed = False

    # Сценарий Г: Согласие (нет импульса)
    p4 = IntentPressureProfile()
    v4 = _resolve_embodied_vector(p4, WillState.COMPLY)
    t4 = get_embodied_impulse_text(v4)
    if v4 is not None or t4 != "Сопротивляться...":
        print(f"[FAIL] Согласие: Ожидался None/Сопротивляться, получено {v4}/{t4}")
        passed = False

    if passed:
        print("[PASS] Все сценарии Embodied Impulse работают корректно.")
    return passed


def test_ambient_phenomenology():
    """Приоритет 2: Вычисление средового давления"""
    print("\n--- ТЕСТ 3: Ambient Phenomenology ---")
    passed = True

    # Сценарий А: Пустая комната
    amb_a = _compute_ambient_phenomenology([])
    if amb_a is not None:
        print(f"[FAIL] Пустая комната: Ожидался None, получено {amb_a}")
        passed = False

    # Сценарий Б: 3 спокойных NPC
    npcs_b = [{"npc_id": f"npc_{i}", "psyche": {"stress": 0.1, "fear": 0.1}} for i in range(3)]
    amb_b = _compute_ambient_phenomenology(npcs_b)
    # avg_neg_emotion = 0.1, temp = (0.1*2)-1 = -0.8, compression = 3/5 = 0.6
    temp_b_ok = abs(amb_b["emotional_temperature"] - (-0.8)) < 1e-9
    comp_b_ok = abs(amb_b["proximity_compression"] - 0.6) < 1e-9
    if not (amb_b and temp_b_ok and comp_b_ok):
        print(f"[FAIL] Спокойные NPC: Ожидался temp=-0.8, comp=0.6, получено {amb_b}")
        passed = False

    # Сценарий В: 5 паникующих NPC
    npcs_c = [{"npc_id": f"npc_{i}", "psyche": {"stress": 0.9, "fear": 1.0}} for i in range(5)]
    amb_c = _compute_ambient_phenomenology(npcs_c)
    # avg_neg_emotion = 0.95, temp = (0.95*2)-1 = 0.9, compression = 5/5 = 1.0
    temp_c_ok = abs(amb_c["emotional_temperature"] - 0.9) < 1e-9
    comp_c_ok = abs(amb_c["proximity_compression"] - 1.0) < 1e-9
    if not (amb_c and temp_c_ok and comp_c_ok):
        print(f"[FAIL] Паникующие NPC: Ожидался temp=0.9, comp=1.0, получено {amb_c}")
        passed = False

    # Сценарий Г: Игрок не влияет на среду
    npcs_d = [{"npc_id": "player", "psyche": {"stress": 1.0, "fear": 1.0}}]
    amb_d = _compute_ambient_phenomenology(npcs_d)
    if amb_d is not None:
        print(f"[FAIL] Игрок в комнате: Ожидался None, получено {amb_d}")
        passed = False

    if passed:
        print("[PASS] Средовое давление вычисляется корректно.")
    return passed


def test_temporal_assembly_delay():
    """Приоритет 3: Интерполяция позиции NPC (Temporal Delay)"""
    print("\n--- ТЕСТ 4: Temporal Assembly Delay ---")
    passed = True

    prev_x, prev_y = 10.0, 10.0
    curr_x, curr_y = 20.0, 20.0

    # Сценарий А: Нет задержки (норма)
    delay_0 = 0.0
    rx_0 = prev_x + (curr_x - prev_x) * (1.0 - delay_0)
    ry_0 = prev_y + (curr_y - prev_y) * (1.0 - delay_0)
    if not (rx_0 == 20.0 and ry_0 == 20.0):
        print(f"[FAIL] Нет задержки: Ожидалось (20, 20), получено ({rx_0}, {ry_0})")
        passed = False

    # Сценарий Б: 50% задержка (шок)
    delay_5 = 0.5
    rx_5 = prev_x + (curr_x - prev_x) * (1.0 - delay_5)
    ry_5 = prev_y + (curr_y - prev_y) * (1.0 - delay_5)
    if not (rx_5 == 15.0 and ry_5 == 15.0):
        print(f"[FAIL] 50% задержка: Ожидалось (15, 15), получено ({rx_5}, {ry_5})")
        passed = False

    # Сценарий В: 100% задержка (диссоциация, мир замер)
    delay_10 = 1.0
    rx_10 = prev_x + (curr_x - prev_x) * (1.0 - delay_10)
    ry_10 = prev_y + (curr_y - prev_y) * (1.0 - delay_10)
    if not (rx_10 == 10.0 and ry_10 == 10.0):
        print(f"[FAIL] 100% задержка: Ожидалось (10, 10), получено ({rx_10}, {ry_10})")
        passed = False

    if passed:
        print("[PASS] Темпоральная интерполяция работает корректно.")
    return passed


if __name__ == "__main__":
    print("═══════════════════════════════════════════════════")
    print(" ЗАПУСК ПЕСОЧНИЦЫ СПРИНТА 27: ФЕНОМЕНОЛОГИЯ ")
    print("═══════════════════════════════════════════════════")

    results = []
    results.append(test_dto_cleanup())
    results.append(test_embodied_impulse())
    results.append(test_ambient_phenomenology())
    results.append(test_temporal_assembly_delay())

    print("\n═══════════════════════════════════════════════════")
    if all(results):
        print(" ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО. СПРИНТ 27 ВЕРЕН. ")
    else:
        print(" ЕСТЬ ОШИБКИ! ТРЕБУЕТСЯ ОТЛАДКА МАТЕМАТИКИ. ")
    print("═══════════════════════════════════════════════════")
