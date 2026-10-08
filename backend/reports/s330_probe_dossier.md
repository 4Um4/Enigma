# S330-TARGETED-PROBE — Досье точки потери движения деятельности (TAKE → engine_changes=0)

> Исполнитель: преемник S334. Мандат Мастера (дословно): «targeted-probe → установить
> точку потери движения → только потом выбирать владельца фикса». Проба = диагностика,
> фикс не исполнялся. Базлайн: v0.5.4.2.9 (e9fdb3a4) + 97ce8052 + 7e0f6a6c
> + 61dd3787 + 289c4e45 (TZ-CC-01 Phase 0, параллельная S336: WIP в chronicle-файлах;
> IPT RED INV-SILENT-FAILURE decomposition_normalizer.py:157 — чужой контур, не тронут).


> **Статус (вердикт Мастера):** ROOT CAUSE CONFIRMED / FIX OWNER HOLD — фикс не исполнялся; владелец не назначен; калибровка 2.0→2.108 без доказательства порога запрещена.

## 1. Метод
Два одноразовых log-only зонда (untracked, паттерн ObservabilityTap ADR-O-361;
ноль правок прод-кода): s330_probe1_gate_trace (гейты B1/B1.5/B3 + traversal/
commitment/pos-дампы), s330_probe2_planner_trace (_compile_traversal_plan +
LocalTraversalPlanner.compile_plan: тело, хоп, reason, clearance). Eat-мир
production: fixture, temp-saves, env-пара флагов, hunger 0.9 fail-loud read-back.
Валидность: probe1 — два независимых прогона с идентичными маркерами (A/A);
probe2 — детерминизм байт-в-байт (clearance=0.10818510677891968 во всех повторах).

## 2. Точка потери (полная цепь, FAIL_STAGE=MATERIALIZE)
1. activity_lifecycle_service._build_goal:212-220 → MacroMovementGoal
   target=tavern:bar_area, reason=activity:eat:d:food:wo_4eb400e3f1cfa459,
   body_capabilities=ДЕФОЛТ (поле не задаётся, movement.py:65 default_factory)
2. Гейт① арбитр simulation.py:130-135 — PASS (active_commitments у Торнина пуст)
3. Гейт② movement_bridge.py:100-108 — PASS (в resolved каждый тик)
4. B1 pre-gate movement_engine:109-138 — ACCEPT (right_table ≠ bar_area)
5. B1.5 :209-233 — чисто (транзиты завершаются честно; зомби-MOVING нет)
6. A* (S140 route-aware): путь до bar_area существует; первый хоп →
   tavern:main_hall_west (10.5,6.5)→(6.0,8.0), dist≈4.74; маршрут 6.9 < альт. 7.8
7. Локальный план хопа: WALK заблокирован препятствием → JUMP-кандидат
   horizontal_distance ≈ 2.108
8. TraversalTransitionKernel._evaluate_jump:62-68: 2.108 > body.max_jump_distance
   (2.0, дефолт) → GAP_TOO_WIDE, shortfall 0.108 (5.4%)
9. S131.1 HARD_REJECT movement_engine:867-871 (геометрия доступна → A*-fallback
   запрещён by design) → REJECTED(GAP_TOO_WIDE)
10. movement_engine:1095-1097: return [] — proposal не рождается
11. Шаг деятельности не материализуется → переэмиссия каждый тик (13 подряд,
    probe1) → ACTIVITY_TIMEOUT_TICKS=60 → терминал без success (E6/E7/E8)

## 3. Контролируемая пара (+третий член), один NPC/тик/тело
- tick 8: activity:eat right_table→main_hall_west → REJECTED GAP_TOO_WIDE (2.108>2.0)
- tick 8: proactive_seek_ally right_table→main_hall → ACCEPTED (JUMP ≈1.05 < 2.0)
- maid_lusya, тот же activity-рельс kitchen→node_16 → чистый WALK 3.27 → SUCCESS
⇒ рельс/узел/арбитры/тело валидны; отказ = геометрия конкретного хопа × порог тела.

## 4. Опровергнутые гипотезы
Зомби-MOVING (B1.5) · B1-COLLAPSE activity-цели · узел bar_area отсутствует
(campaign.json:204/tavern.json:187 существуют) · «дефолт-тело не прыгает»
(can_jump=True, дошел до дистанционной ветки kernel) · drop event_compiler:741-747
/ SSM:955-963 (недостижимы как первый отказ — proposal не рождается) ·
config-override тела (греп body_capabilities по данным: 0 вхождений).

## 5. Root cause statement
ROOT_CAUSE_CONFIDENCE: 90 (воспроизводимый сценарий + прямой лог ×13 +
найденный сайт сравнения — три условия Части IX).
Точка потери: MovementEngine._compile_traversal_plan → REJECTED(GAP_TOO_WIDE) →
return [] (:1091-1097); причина рождается в kernel:62-68.
Механизм: capability-blind A* + финальный локальный отказ без ревизии маршрута
→ петля переэмиссии → таймаут-терминал.

## 6. Открытые точки (владельцу фикса)
- obstacle_id снят probe-3: obj_11 rect(7.35,6.65,w=1.30,h=0.70), clearance=-0.350; JUMP-кандидат entry(9.00,7.00)→exit(7.00,7.67)
- GAP_TOO_WIDE ∉ movement_contract M000-M008 — дыра классификации причин
- Латентная асимметрия продюсеров тела (_build_goal vs npc_tick_pipeline:1171) —
  сегодня нейтральна, кандидат мини-ADR
- Семейное сходство с Дефектом №3 S330 (guarding_gate) — НЕ проверялось (CONF<40)
- Системность: 78 GAP_TOO_WIDE/20 тиков по всем NPC (corner_table→main_hall_west
  horizontal 2.154) — хоп восток→запад через main_hall_west отказывает системно

## 7. Варианты владельца фикса (факты; выбор — вердикт Мастера)
A. Movement-домен: ревизия маршрута при локальном REJECTED (capability-aware
   next-hop; альтернативный маршрут через main_hall→bar_west правдоподобен, не проверен)
B. Калибровка: max_jump_distance 2.0 vs мировой гэп 2.108 (shortfall 5.4%;
   прецедент CALIBRATION_CANDIDATE ADR-O-383)
C. Данные/топология: препятствие, о которое чиркает прямой луч (снять obstacle_id)
D. Activity-продюсер: проброс body_capabilities (латентная нога; отказ сам не снимает)

## 8. Артефакты
backend/reports/s330_probe1_gate_trace.txt (+stdout, stdout_run1);
backend/reports/s330_probe2_planner_trace.txt (+stdout); оба зонда в
backend/tests/sandbox/SUPERBOX/scenarios/ (untracked); входы: eat_vertical_recheck,
d3_probe_mass200, досье S330 (9e18f7cd).

## 9. Честность приборов
stdout-счётчик probe2 «CTP-REJECTED[tornin]=0» ошибочен (CTP-OUT без имени NPC) —
источник истины артефакт (пары CTP-IN/OUT); метки тиков probe2 смещены на init-тик.


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
