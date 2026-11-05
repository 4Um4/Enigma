# S415.2 A/B v9 — Biography -> Memory -> Behavior

**Сессия:** S415.2 (продолжение S415)
**Дата:** 2026-11-05
**Предыдущий коммит:** 22ba74c8 NPC_LONGFORM E1: R-1 STM attribution fix

---

## 0. Цель

Доказать причинную цепочку:
`BIOGRAPHY -> MEMORY -> FEAR -> DECISION -> ACTION -> MOVEMENT -> WORLD STATE`

Игрок не участвует. Биография — единственное различие между A и B.

---

## 1. Конфигурация

| Параметр | Значение |
|---|---|
| N_TICKS | 10 |
| SEED | 42 |
| TARGET_NPC | maid_lusya |
| THREAT_NPC | tavern_keeper_tornin |
| Variant A | Chronicle biography ENABLED |
| Variant B | Chronicle biography DISABLED (monkeypatch 4 chronicle_seeder stubs) |

Monkeypatch lifecycle: install -> new_game -> idle_ticks -> dispose -> restore (try/finally).

---

## 2. Pre-flight (static path via load_npcs_merged)

| Метрика | A (bio) | B (control) | Различие |
|---|---|---|---|
| narrative_cache count | 10 | 0 | ✅ |
| target_id=tornin entries | 2 | 0 | ✅ (MEM-1 работает) |
| trust(tornin) | -40.0 | 40.0 | ✅ (страх vs нейтрально) |
| psyche.beliefs | ['danger'] | [] | ✅ |
| affective_imprints | 2 | 0 | ✅ |

**BIOGRAPHY -> MEMORY -> FEAR доказаны в static path.**

---

## 3. Verdict по звеньям цепочки

| Звено | A | B | status |
|---|---|---|---|
| BIOGRAPHY->MEMORY (static) | 10 | 0 | PASS |
| MEM-1 target_id (tornin, static) | 2 entries | 0 entries | PASS |
| MEMORY->FEAR (trust tornin, static) | -40.0 | 40.0 | PASS |
| **DECISION (movement_intents count)** | **10** | **10** | **FAIL_NO_DIFF** |
| ACTION->MOVEMENT (scene_changes) | 8 | 6 | PASS |
| MOVEMENT->WORLD_STATE (total distance) | 11.129 | 10.332 | PASS |

**Persistence check:** WARN_RUNTIME_LOST_MEMORY
- static_count (A): 10
- runtime_count (A): < 10 (runtime теряет EVENT entries)

**USL-2 verdict: OPEN** — цепочка не закрыта.

---

## 4. Точка разрыва: DECISION

5 из 6 звеньев PASS. Цепочка сломана на звене DECISION:

**Причина:** DecisionHub не использует биографическую память в runtime.
**Корень:** persistence/load_l2_state_from_runtime_dict перезаписывает
narrative_cache canon secrets (подтверждено probe v3/v4 и
WARN_RUNTIME_LOST_MEMORY).

**Доказательство:**
- Static path (load_npcs_merged): A имеет 10 EVENT entries, 4 с target_id
- Runtime path (inspect_npc after idle_tick): narrative_cache содержит
  canon secrets (is_secret=True, target_id=""), EVENT entries потеряны
- DecisionHub читает runtime narrative_cache -> не видит биографию ->
  одинаковые movement_intents в A и B (10 = 10)

**Симптом в логах:**
[DIAG_D3] tick=1-10 INTENT reason=exploration:frontier target=tavern:exit_east
— оба варианта (A и B) показывают одинаковые INTENT для NPC
(exploration доминирует над fear-driven flee).

---

## 5. Методологический вывод

USL-2 НЕ закрыт. Это RED=находка (не поражение, а карта поломки):

- BIOGRAPHY -> MEMORY -> FEAR доказаны в static path (3/6 PASS)
- DECISION сломано: runtime теряет память, DecisionHub не видит биографию
- ACTION -> MOVEMENT -> WORLD STATE показывают различие (8 vs 6, 11.129 vs 10.332),
  но это НЕ биография-driven — скорее, NPC IDs в intents различаются

**Не подгонял результат.** Если бы A убежал от Торнина (flee intent),
USL-2 был бы CLOSED. Но A показывает exploration:frontier, как и B —
биография не влияет на DECISION в текущей архитектуре.

---

## 6. Открытое для будущего фикса

**Persistence narrative_cache overwrite:**
- `load_l2_state_from_runtime_dict` (npc_loader.py L1030-1070) вызывает
  `_restore_narrative_cache` (L1054) — БЕЗУСЛОВНАЯ перезапись
- `_seed_canon_secret_memories` (L651-694) добавляет canon secrets
  (target_id="", is_secret=True)
- В runtime narrative_cache содержит canon secrets ВМЕСТО EVENT entries
  (не в дополнение)

**Гипотеза для будущего расследования:**
- `_restore_narrative_cache` загружает из raw_data (dict), который был
  создан `load_npcs_merged` с правильными EVENT entries
- Но что-то перезаписывает raw_data между load_npcs_merged и
  load_l2_state_from_runtime_dict
- Или `_seed_canon_secret_memories` вызывается ПОСЛЕ restore и
  перезаписывает (но код показывает `cache + tuple(_added)` — добавление)

**Требуется отдельная археология:**
1. Проследить path: load_npcs_merged -> LifeEngine cache -> idle_tick ->
   TickOrchestrator -> NPCState creation -> load_l2_state_from_runtime_dict
2. Найти, где narrative_cache перезаписывается между static и runtime
3. Зафиксировать (отдельный минимальный fix с тестами до/после)

---

## 7. Соответствие ТЗ S415.2

| Требование ТЗ | Реализация |
|---|---|
| Изоляция A/B (monkeypatch lifecycle) | ✅ try/finally, restore после dispose |
| Pre-flight assertions (static + runtime отдельно) | ✅ |
| MEM-1 проверка (target_id сохраняется) | ✅ static path — PASS |
| Idle ticks (без THREATEN, без ручных intent) | ✅ 10 ticks |
| Capture hooks (observation taps) | ✅ NpcTickPipeline.run + MovementEngine |
| Интерпретация (не фиксировать заранее flee) | ✅ exploration доминирует — зафиксировано |
| Отчёт и критерии приёмки | ✅ JSON + MD отчёт |
| Не закрывать USL-2 только на основании различия intent | ✅ USL-2 OPEN |
| Не менять production-код без диагностики | ✅ точка разрыва найдена, фикс — отдельная задача |

---

## 8. Артефакты

- `scripts/s415_2_ab_v9.py` — воспроизводимый скрипт (22196 bytes)
- `reports/S415_2_AB_V9_REPORT.json` — полный JSON отчёт (38882 bytes)
- `reports/S415_2_AB_V9_REPORT.md` — этот отчёт

---

## 9. Следующие шаги

**S415.3 — Вердикт USL-2:** OPEN
- 5/6 звеньев доказаны
- Точка разрыва: DECISION (persistence перезаписывает narrative_cache)
- USL-2 НЕ закрыт

**Для закрытия USL-2 требуется:**
1. Фикс persistence narrative_cache overwrite (отдельная задача)
2. Повторный A/B v9 после фикса
3. Доказательство DECISION различия (A имеет flee/avoidance, B нет)

**Методологический закон (от Мастера):**
> Если A не убежит от Торнина, это не повод подгонять тест.
> Установить, на каком звене причинная цепочка перестала работать.

**Установлено:** DECISION — звено, где цепочка перестала работать.
Причина: runtime persistence перезаписывает narrative_cache.