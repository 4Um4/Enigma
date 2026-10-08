"""
path: /project/reports/s330_dossier_update.py
Назначение: Дозапись досье S330 результатами probe-3 + статусы вердикта Мастера.
    Точечные правки: строка статуса в шапку, §6.1 (obstacle снят), +§10.
Запуск: python reports/s330_dossier_update.py
"""
from pathlib import Path

F = Path(__file__).resolve().parents[1] / "backend" / "reports" / "s330_probe_dossier.md"
text = F.read_text(encoding="utf-8")

S1 = "## 1. Метод"
assert text.count(S1) == 1, "якорь шапки"
STATUS = ("\n> **Статус (вердикт Мастера):** ROOT CAUSE CONFIRMED / FIX OWNER HOLD — "
          "фикс не исполнялся; владелец не назначен; калибровка 2.0→2.108 без "
          "доказательства порога запрещена.\n")
assert "ROOT CAUSE CONFIRMED" not in text
text = text.replace(S1, STATUS + "\n" + S1, 1)

O1 = "- obstacle_id блокирующего препятствия не снят (solver-local; хоп (10.5,6.5)→(6.0,8.0))"
assert text.count(O1) == 1, "якорь §6.1"
O1N = ("- obstacle_id снят probe-3: obj_11 rect(7.35,6.65,w=1.30,h=0.70), "
       "clearance=-0.350; JUMP-кандидат entry(9.00,7.00)→exit(7.00,7.67)")
text = text.replace(O1, O1N, 1)

SEC10 = """

## 10. PROBE-3 — развилка A/B/C (мандат Мастера; s330_probe3_fork_abc)
- Obstacle: obj_11 (мебель между right_table и main_hall_west); прямой луч
  WALK-нечист (clearance -0.350) → единственный локальный обход = JUMP
  h_dist≈2.108 > дефолт max_jump_distance 2.0 → GAP_TOO_WIDE. Высота
  препятствия 1.0 == дефолт max_jump_height — проходит (отказ чисто по
  дистанции, CONF механики закрыт числом kernel).
- Ветка A (movement: capability-aware ревизия маршрута): ПРАВДОПОДОБНА —
  right_table→main_hall тем же телом ACCEPTED в том же тике (probe-2 tick 8);
  остаток main_hall→bar_west→bar_area — хопы ≈1.41/2.24 либо чистый WALK.
  Полный по-хопный прогона альтернативы НЕТ (S140 next-hop семантика;
  find_path получает уже переписанный target первого хопа) — доказательство
  существования полной альтернативы за владельцем фикса.
- Ветка B (калибровка): порог 2.0 введён e3f6377a (V.0.5.3.5.5 full snapshot)
  БЕЗ калибровочного следа; ADR-O-333_IMPACT отсутствует → порог не
  подтверждённая калибровка и не доказанный мировой закон. Калибровка
  допустима ТОЛЬКО как политика порога по отдельному вердикту (прецедент
  CALIBRATION_CANDIDATE ADR-O-383) — самостоятельным фиксом не является.
- Ветка C (топология/данные): obj_11 + связи main_hall_west (прямой хоп 6.9
  выбирается A*, альтернатива 7.8) — вопрос данных к world-editor.
- Дрейф платформы: релиз 58b2389e (v0.5.4.3.0) втянул probe1-артефакты/сценарий
  в main; S336 закрыта (ADR-O-422, IPT 51/51 — чужой RED починен их контуром);
  roadmap v4.3 → v4.6 (канон-сверка LC/§9.10 — на v4.6).
"""
assert "## 10. PROBE-3" not in text
text = text.rstrip("\n") + "\n" + SEC10
F.write_text(text, encoding="utf-8")
print("OK: досье дописано (статус-шапка, §6.1, §10)")
