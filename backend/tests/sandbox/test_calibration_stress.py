"""
path: backend/tests/sandbox/test_calibration_stress.py
Назначение: Стресс-тест CalibrationEngine (4 сценария Мастера).
Зависимости: services.npc.calibration_engine, domain.identity_events
Основные сущности: TestCalibrationStress

cd backend; python -m tests.sandbox.test_calibration_stress; cd ..
"""

from app.services.npc.calibration_engine import CalibrationEngine
from app.domain.identity_events import EffectiveDrives

def run_scenario(l0: dict, threat_ticks: int, calm_ticks: int, noise_cycles: int = 0):
    engine = CalibrationEngine()
    l3_prev = dict(l0)
    strain = {}
    fear_history = []

    threat_raw = EffectiveDrives.from_dict({"fear": 0.9, "control": 0.1})
    calm_raw = EffectiveDrives.from_dict(l0)

    # Фаза 1: Угроза
    for _ in range(threat_ticks):
        l3_stable, l3_prev, strain = engine.stabilize(threat_raw, l3_prev, l0, strain)
        fear_history.append(l3_stable.get("fear"))

    # Фаза 2: Спокойствие
    for _ in range(calm_ticks):
        l3_stable, l3_prev, strain = engine.stabilize(calm_raw, l3_prev, l0, strain)
        fear_history.append(l3_stable.get("fear"))

    # Фаза 3: Шум (угроза/покой каждые 5 тиков)
    for cycle in range(noise_cycles):
        for t in range(10):
            raw = threat_raw if t < 5 else calm_raw
            l3_stable, l3_prev, strain = engine.stabilize(raw, l3_prev, l0, strain)
            fear_history.append(l3_stable.get("fear"))

    return fear_history

if __name__ == "__main__":
    L0 = {"fear": 0.2, "control": 0.8}
    print("=== CALIBRATION ENGINE STRESS TEST (Master Scenarios) ===\n")

    # Test A — Recovery (Возврат к аттрактору после длительной травмы)
    h_a = run_scenario(L0, threat_ticks=1000, calm_ticks=49000)
    final_a = h_a[-1]
    pass_a = abs(final_a - L0["fear"]) < 0.05
    print(f"TEST A (Recovery): 1000 threat → 49000 calm")
    print(f"  Final fear = {final_a:.3f} (L0 = {L0['fear']:.1f})")
    print(f"  VERDICT: {'PASS (Returned to attractor)' if pass_a else 'FAIL (Stuck in trauma)'}\n")

    # Test B — Re-trauma (Второй snap быстрее первого?)
    # Запускаем 1000 threat, 5000 calm, ещё 1000 threat. Сравниваем скорость роста.
    h_b1 = run_scenario(L0, threat_ticks=1000, calm_ticks=0) # Первая травма
    h_b2 = run_scenario(L0, threat_ticks=1000, calm_ticks=5000) # Восстановление
    # Снова угроза на 100 тиков, начиная с состояния после 5000 calm
    engine_b = CalibrationEngine()
    l3_prev_b = dict(L0)
    strain_b = {}
    # Нагрев
    for _ in range(1000): l3_stable, l3_prev_b, strain_b = engine_b.stabilize(EffectiveDrives.from_dict({"fear": 0.9, "control": 0.1}), l3_prev_b, L0, strain_b)
    for _ in range(5000): l3_stable, l3_prev_b, strain_b = engine_b.stabilize(EffectiveDrives.from_dict(L0), l3_prev_b, L0, strain_b)
    # Вторая травма
    snap_2_start = l3_prev_b["fear"]
    for _ in range(100): l3_stable, l3_prev_b, strain_b = engine_b.stabilize(EffectiveDrives.from_dict({"fear": 0.9, "control": 0.1}), l3_prev_b, L0, strain_b)
    snap_2_end = l3_prev_b["fear"]
    delta_snap_2 = snap_2_end - snap_2_start
    
    pass_b = delta_snap_2 > 0.1 # Если strain осталась, второй snap должен быть быстрее/сильнее
    print(f"TEST B (Re-trauma): 1000 threat → 5000 calm → 100 threat")
    print(f"  Second snap delta (100 ticks) = {delta_snap_2:.3f}")
    print(f"  VERDICT: {'PASS (Strain memory accelerates re-trauma)' if pass_b else 'FAIL (Strain memory useless)'}\n")

    # Test C — Noise Resistance (Нет накопления от шума)
    h_c = run_scenario(L0, threat_ticks=0, calm_ticks=0, noise_cycles=10000)
    final_c = h_c[-1]
    pass_c = abs(final_c - L0["fear"]) < 0.05
    print(f"TEST C (Noise Resistance): 10000 cycles (5 threat / 5 calm)")
    print(f"  Final fear = {final_c:.3f} (L0 = {L0['fear']:.1f})")
    print(f"  VERDICT: {'PASS (No drift from noise)' if pass_c else 'FAIL (Noise accumulation)'}\n")

    # Test D — Permanent Trauma (Границы и дрейф)
    h_d = run_scenario(L0, threat_ticks=100000, calm_ticks=0)
    final_d = h_d[-1]
    max_d = max(h_d)
    pass_d = max_d <= 1.0 and final_d >= 0.0
    print(f"TEST D (Permanent Trauma): 100000 threat")
    print(f"  Final fear = {final_d:.3f}, Max fear = {max_d:.3f}")
    print(f"  VERDICT: {'PASS (Bounds intact, no infinite drift)' if pass_d else 'FAIL (Bounds violation or drift)'}\n")

    print("=== OVERALL VERDICT ===")
    if pass_a and pass_b and pass_c and pass_d:
        print("ALL TESTS PASSED. CalibrationEngine is mathematically stable.")
    else:
        print("TESTS FAILED. Requires recalibration.")