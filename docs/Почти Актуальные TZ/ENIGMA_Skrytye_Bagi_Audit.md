# ENIGMA — СКРЫТЫЕ БАГИ: Глубокий аудит NPC-поведения

**Проект:** ENIGMA / The Fool, V.0.5.3.4.5
**Дата:** 15 июля 2026
**Повод:** Создатель спросил: «А во всех моих ТЗ точно перечислены все баги? Может, по факту всё поведение НПС забаговано, а не только то что уже очевидно?»
**Ответ:** Да. Гипотеза полностью подтвердилась. Найдено **36 недокументированных багов** (16 UNDOC + 20 DEEP), из них **13 CRITICAL**. Существующие ТЗ покрывают только верхушку.

---

## 0. КРАТКИЙ ВЕРДИКТ

**NPC-поведение системно сломано на уровне записи состояния.** Pipeline ВЫЧИСЛЯЕТ правильно (Phase 9.1 считает `new_load`, Phase 9 кристаллизует belief, DecisionHub скорит intents) — но WRITE PATHS молча сломаны:
- Case mismatches (UPPERCASE vs lowercase intent keys)
- Unreachable branches (EmotionPayload handler в неправильном if)
- Wrong-kwarg TypeErrors маскируются try/except
- Missing persistence (CrystallizedBeliefStore in-memory only)

**Каждая подсистема сообщает успех изолированно.** Orchestrator логирует `intent=FLEE score=0.83`. NPC стоит на месте с HP=100, эмоцией neutral, памятью об атаке, стёртой при следующем reload.

**ВТорник 14 июля 2026 (последняя сессия):** из 7 NPC — 0 двигались, 0 говорили, 0 меняли эмоции, 0 меняли отношения. Combat: 0/N атак нанесли урон. DM: 100% ответов "Ничего не произошло".

---

## 1. СТАТИСТИКА АУДИТА

| Метрика | Значение |
|---|---|
| Существующих ТЗ | 14 + 3 установочных |
| Багов в существующих ТЗ | 58 (TZ-INFRA-1) + 6 blockers (TZ_Aktualizirovano) |
| **Недокументированных багов найдено** | **36** |
| — Runtime (UNDOC-001…016) | 16 (6 CRITICAL) |
| — Pipeline architectural (DEEP-001…020) | 20 (7 CRITICAL) |
| Pytest: всего тестов | 861 |
| Pytest: проходит | 737 (85.5%) |
| Pytest: падает | **114 (13.2%)** |
| Pytest: пропущено (known broken) | 11 |
| Тестов со stealth-skip (переименованы `_skip_`) | 1 |
| TODO/FIXME в NPC pipeline | 35+ |
| `verify_autonomous_world.py` существует? | **НЕТ** |
| ADR-O "Pressure → Emotion" pipeline реализован? | **НЕТ** |

---

## 2. ТОП-13 CRITICAL БАГОВ (не описаны ни в одном ТЗ)

### UNDOC-001 — DM Agent: UnboundLocalError на каждом ходе
- **Файл:** `backend/app/agents/dm_agent.py:149, 277`
- **Симптом:** `SceneStateManager` импортируется внутри `if _is_session_start: if _scene_state:` блока, но используется в другом пути кода → `UnboundLocalError` → ловится try/except → пустой `scene_block` → DM без контекста сцены
- **Evidence:** 3,327 вхождений в 13 `enigma_*.jsonl` файлах
- **Время фикса:** 5 минут (вынести импорт из условного блока)
- **Почему не в ТЗ:** Это регрессия, появившаяся после рефакторинга

### UNDOC-002 — DM: "Ничего не произошло" на 100% команд
- **Файл:** `backend/causal_validation.log`
- **Симптом:** DM отвечает "Ничего не произошло" на ВСЕ команды игрока — атаки, комплименты, покупки, угрозы, вопросы
- **Evidence:** 49 вхождений в логе
- **Время фикса:** 30 минут (после UNDOC-001)
- **Почему не в ТЗ:** Симптом списали на "LLM тупит", а это код-баг

### UNDOC-003 — Combat: урон не применяется
- **Файл:** `backend/data/logs/combat_log.jsonl`
- **Симптом:** 24+ успешных attack rolls (dmg 2-6) — HP остаётся 100 на 15+ атаках
- **Время фикса:** 1 час (после DEEP-007)
- **Почему не в ТЗ:** ТЗ-08 CalibrationEngine говорит "combat works", но не проверяет apply

### UNDOC-005 — Session memory: 80 дней потеряно
- **Файл:** `backend/data/session_memory_Open_road.jsonl`
- **Симптом:** Последняя запись 2026-04-25, текущая сессия 2026-07-14 → 3 месяца контекста молча утеряно
- **Время фикса:** 2 часа
- **Почему не в ТЗ:** Никто не мониторил session_memory continuity

### UNDOC-009 — NPC: никогда не двигаются визуально
- **Файл:** session reports 2026-07-14, 2026-07-13, 2026-07-11
- **Симптом:** Все NPC показывают `Traversal: ❌` в каждой сессии. Позиция в логе обновляется, но визуально NPC не двигается
- **Время фикса:** 2-3 часа (rendering pipeline)
- **Почему не в ТЗ:** Списали на "BUG-P0-02 movement/lerp" — а это другой слой

### DEEP-002 — Crystallized beliefs: молча игнорируются DecisionHub
- **Файл:** `backend/app/services/npc/crystallized_belief_modifier_resolver.py`
- **Симптом:** Resolver возвращает UPPERCASE intent keys (`"FLEE"`, `"WARN"`), но `Intent` enum — lowercase (`"flee"`, `"warn"`). DecisionHub `if intent in scores` никогда не матчит → **L2.5 имеет нулевой эффект на поведение**
- **Время фикса:** 30 минут (привести к lowercase)
- **Почему не в ТЗ:** Архитектурный — не виден без трассировки

### DEEP-004 — Somatic Veto + Extreme Compression: обходятся молча
- **Файл:** `backend/app/services/npc/pressure_translator.py:60-72`
- **Симптом:** Constraints с UPPERCASE keys (`"ATTACK"`, `"FLEE"`); DecisionHub scores — lowercase. NPC в экстремальной боли/шоке/кровопотере продолжает атаковать. Плюс ссылка на несуществующий `Intent.RESIST`
- **Время фикса:** 30 минут
- **Почему не в ТЗ:** ТЗ-08 CalibrationEngine не проверяет somatic veto

### DEEP-005 — Will-broken NPC: теряет ВСЕ state mutations
- **Файл:** `backend/app/services/npc/state_applicator.py:211-219`
- **Симптом:** `TraitDriftEvent(npc_id=..., trait=..., delta=..., source=..., tick=...)` — но dataclass поля: `tick_id/target_id/source_id/effect_value/...`. Поднимает TypeError, ловится outer try/except, возвращает original state → **каждый delta того tick молча откатывается**
- **Время фикса:** 15 минут
- **Почему не в ТЗ:** try/except маскирует

### DEEP-006 — Affective load: НИКОГДА не записывается в state
- **Файл:** `backend/app/services/npc/state_applicator.py:780`
- **Симптом:** Phase 9.1 эмиттит `EmotionPayload(affective_load=new_load)` с `source="sel_trace_commit"`. Но handler вложен в `if _ema_delta != 0.0:` (всегда False для EmotionPayload). Альтернативный путь требует `source == "affective_decay"`. **Phase 9.1 — декоративна. `state.affective_load` может только decay, никогда grow**
- **Время фикса:** 1 час
- **Почему не в ТЗ:** Эмоции "работают" в логе, но не в state

### DEEP-013 — CrystallizedBeliefStore: in-memory only
- **Файл:** `backend/app/services/npc/crystallized_belief_store.py`
- **Симптом:** Нет SQLite backing (в отличие от L1Chronicle). При каждом рестарте сервера / реинстанциации orchestrator — все L2.5 beliefs вытираются. **NPC получают амнезию между сессиями**
- **Время фикса:** 4 часа
- **Почему не в ТЗ:** Никто не тестировал restart persistence для beliefs

### DEEP-001 — ResolutionEngine: 380 строк мёртвого кода
- **Файл:** `backend/app/services/npc/resolution_engine.py`
- **Симптом:** Никогда не вызывается из production. Вся подсистема outcome-band/surprise/gap-learning — теоретическая. NPC никогда не производят `surprise_emotion`, никогда не учатся на gap
- **Время фикса:** 4-8 часов (реально внедрить)
- **Почему не в ТЗ:** Описано в ADR, но не помечено как TODO

### DEEP-015 — ExpectationStore: никогда не инстанциируется
- **Файл:** `backend/app/services/npc/expectation_store.py`
- **Симптом:** Active Inference / Free Energy Principle подсистема (~150 строк) подключена через `getattr(self, "_expectation_store", None)` — всегда возвращает None. Bonus: `_logger` не определён (только `logger`) → NameError на первой DB ошибке
- **Время фикса:** 2 часа
- **Почему не в ТЗ:** ADR описывает, код не подключен

### Missing ADR-O "Pressure → Emotion" pipeline
- **Файл:** `backend/tests/sandbox/phenomenology/_skip_test_affective_pressure.py`
- **Симптом:** Тест переименован с `_skip_` prefix чтобы скрыть от pytest. При принудительном запуске падает с `ModuleNotFoundError: app.services.affective.emotion_resolution` и `pressure_derivation` — обе функции **реализованы только в этом disabled файле**
- **Время фикса:** 1-2 дня (реализовать pressure → emotion pipeline)
- **Почему не в ТЗ:** ADR-O описан, но код не написан; тест скрыт

---

## 3. ARCHITECTURAL ISSUES (системные, не точечные)

### 3.1. Write-path системно сломан
Pipeline COMPUTES correctly, но WRITE PATHS молча сломаны в 4 местах:
- Case mismatch: UPPERCASE vs lowercase (DEEP-002, DEEP-004)
- Unreachable branch: handler в неправильном if (DEEP-006)
- Wrong-kwarg TypeError маскируется try/except (DEEP-005)
- Missing persistence (DEEP-013)

### 3.2. Мёртвый код выдают за рабочий
- ResolutionEngine (380 строк) — никогда не вызывается
- ExpectationStore (150 строк) — никогда не инстанциируется
- RoleTransition.execute_transition — никогда не вызывается (DEEP-016)
- DialogueQueue (priority + cooldown + rate limit) — TaskScheduler использует raw ThreadPoolExecutor (DEEP-018)
- sound_bleeds_to_adjacent — упоминается в Дополнении B как мёртвый код

### 3.3. Type system lies
- TypedDict говорит X, код читает Y
- `AttackResult.attack_total` vs код читает `total_attack` (DEEP-007 / impact_engine)
- `PlayerDistortionInputs.hp/max_hp` vs код читает `effective_hp/effective_max_hp` (cognitive_distortion)
- `NPCStateSnapshot.body_state` (TypedDict) vs код читает `npc["body_state"]` (physiology_decay_handler)
- `TraitDriftEvent` dataclass: kwargs не совпадают с вызовом

### 3.4. False sense of safety
- `InvariantHealthChecker` репортит 0 нарушений, постмортем находит 3 CRITICAL invariant broken (UNDOC-008)
- SHI metric = 100% — вводит в заблуждение
- `verify_autonomous_world.py` НЕ существует — TZ_Aktualizirovano §3.7 ссылается на несуществующий файл

### 3.5. Player = NPC pipeline баг
- Player entity попадает в NPC pipeline
- DecisionHub назначает player'у intents `spread_rumor`, `call_for_help`, `change_role`
- Player имеет `coords=None` в каждой сессии
- Это **не тестовая уязвимость, а продакшен-баг** (UNDOC-010/011)

### 3.6. Тесты не ловят баги
- 861 тест, 737 проходит — но INTEGRATION тестов мало
- `test_tick_orchestrator_full_loop` не проверяет, что state реально мутирует
- `IPT.py` (Invariant Probe Tests) проверяет только happy path idle_tick
- Нет теста "запусти тик, проверь что HP NPC изменился"
- Нет теста "запусти тик, проверь что emotion изменилась"

---

## 4. СРАВНЕНИЕ: ЧТО ТЗ ОБЕЩАЕТ vs ЧТО КОД ДЕЛАЕТ

| ТЗ обещает | Код делает | Разрыв |
|---|---|---|
| NPC кристаллизует beliefs → меняет поведение (TZ_Aktualizirovano) | Beliefs кристаллизуются, но **не влияют на behavior** (DEEP-002) | CRITICAL |
| Somatic veto: NPC в боли не атакует (Causal Contract §49) | Constraints вычисляются, но **не матчатся** (DEEP-004) | CRITICAL |
| Affective pipeline: emotion меняется от событий (TZ-01 DecisionHub) | Phase 9.1 эмиттит, но **не записывается** в state (DEEP-006) | CRITICAL |
| Cross-session memory continuity (Устав §12) | L2.5 beliefs **in-memory only**, стираются на рестарте (DEEP-013) | CRITICAL |
| Combat: damage applied to HP (TZ-INFRA-1 BUG-P0-XX) | Damage **не применяется** (UNDOC-003) | CRITICAL |
| Player ≠ NPC (Устав §17 Epistemological Orthogonality) | Player **в NPC pipeline**, получает NPC intents (UNDOC-010) | CRITICAL |
| DM has scene context (TZ_Autonomy §3) | DM **не имеет** scene context (UNDOC-001) | CRITICAL |
| Active Inference / Free Energy (ADR-O) | ExpectationStore **никогда не инстанциируется** (DEEP-015) | HIGH |
| ResolutionEngine: gap learning | **Мёртвый код**, 380 строк (DEEP-001) | HIGH |
| Role transitions: NPC меняет социальную роль | **Мёртвый код** (DEEP-016) | HIGH |
| DialogueQueue: priority + cooldown + rate limit | **Мёртвый код**, TaskScheduler uses raw ThreadPool (DEEP-018) | HIGH |
| Pressure → Emotion pipeline (ADR-O-XX) | **Не реализован**, тест скрыт `_skip_` | CRITICAL |

---

## 5. КОРНЕВАЯ ПРИЧИНА — один абзац

NPC-поведение ENIGMA системно сломано **не в вычислениях, а в записи состояния**. Pipeline корректно считает intents, emotions, beliefs, damage — но write paths молча сломаны в 4 архитектурных местах (case mismatch, unreachable branch, masked TypeError, missing persistence). Каждая подсистема репортит успех изолированно; orchestrator логирует `intent=FLEE score=0.83`; NPC стоит на месте с HP=100, emotion neutral, памятью об атаке, стёртой при следующем reload. Тесты это не ловят, потому что 737 проходящих тестов проверяют подсистемы изолированно, а интеграционных тестов на "state реально мутировал" нет. `verify_autonomous_world.py`, который должен был это ловить, **не существует** — TZ_Aktualizirovano §3.7 ссылается на файл, которого нет в репозитории.

---

## 6. АКТУАЛИЗИРОВАННЫЙ ПОРЯДОК ВЫПОЛНЕНИЯ (с учётом скрытых багов)

```
═══════════════════════════════════════════════════════════════════════
 ФАЗА -1 — ЭКСТРЕННЫЙ ФИКС СКРЫТЫХ БАГОВ (1-2 спринта, ДО ВСЕГО)
═══════════════════════════════════════════════════════════════════════

 ПРИОРИТЕТ P0 — 5 багов, ~6 часов (разблокируют всё остальное):
 ───────────────────────────────────────────────────────────────────
  -1.1. UNDOC-001: вынести SceneStateManager import из условного блока
        в dm_agent.py:149 → разблокирует DM
  -1.2. UNDOC-002: после -1.1 проверить — DM должен перестать отвечать
        "Ничего не произошло"
  -1.3. DEEP-002: lowercase keys в CrystallizedBeliefModifierResolver
        → L2.5 начнёт влиять на behavior
  -1.4. DEEP-004: lowercase constraint keys в pressure_translator.py
        → Somatic Veto начнёт работать
  -1.5. DEEP-006: вынести sel_trace_commit handler из _ema_delta branch
        в state_applicator.py:780 → emotion начнёт меняться

 ПРИОРИТЕТ P1 — 4 бага, ~10 часов (критично для persistence):
 ───────────────────────────────────────────────────────────────────
  -1.6. DEEP-005: исправить TraitDriftEvent kwargs в state_applicator
  -1.7. DEEP-013: добавить SQLite backing для CrystallizedBeliefStore
  -1.8. UNDOC-003: после DEEP-007 — combat damage начнёт применяться
  -1.9. UNDOC-005: session_memory continuity — 80 дней потеряно

 ПРИОРИТЕТ P2 — 3 бага, ~1 день (тестовая инфраструктура):
 ───────────────────────────────────────────────────────────────────
  -1.10. Создать backend/scripts/verify_autonomous_world.py
         (TZ_Aktualizirovano §3.7 ссылается, файла нет)
  -1.11. Расширить IPT.py: добавить интеграционные тесты
         "state реально мутировал после тика"
  -1.12. Исправить InvariantHealthChecker (UNDOC-008 — false negative)

 ПРИОРИТЕТ P3 — 3 бага, ~3-5 дней (реализация мёртвого кода):
 ───────────────────────────────────────────────────────────────────
  -1.13. Реализовать ADR-O "Pressure → Emotion" pipeline
         (тест скрыт в _skip_test_affective_pressure.py)
  -1.14. Подключить ResolutionEngine (DEEP-001) или удалить
  -1.15. Подключить ExpectationStore (DEEP-015) или удалить

 ПРИОРИТЕТ P4 — 2 бага, ~2 дня (изоляция player от NPC pipeline):
 ───────────────────────────────────────────────────────────────────
  -1.16. UNDOC-010/011: вынести player из NPC pipeline
  -1.17. UNDOC-009: rendering — NPC визуально не двигаются

═══════════════════════════════════════════════════════════════════════
 ПОСЛЕ ФАЗЫ -1: 3 тривиальные правки (прежняя Фаза 0)
═══════════════════════════════════════════════════════════════════════
  0.1. decision_hub.py:1443 — добавить "survival" в _direction_intents
  0.2. scene_state_manager.py:762 — заменить return "tavern" на raise
  0.3. routes.py:596 — передать campaign_id в load_npcs_merged()

═══════════════════════════════════════════════════════════════════════
 ДАЛЕЕ — прежний порядок (Таверна → установочник → Сценарий №2):
═══════════════════════════════════════════════════════════════════════
  Ф1. Закрытие AWC (npc_conversation.py + CI/CD + routine)
  Ф2. Stage 1-2 (emergent cycle)
  Ф3. Stage 3 (мини-игра, tavern-hardcoded)
  Ф4. Stage 4 (полировка)
  Ф5?. Content Policy (опционально)
  Ф6. Установочник
  Ф7. Чистовой релиз Таверны → заморозить ветку

  ─── после релиза Таверны ───

  Ф8. Дополнение B (multi-location tick)
  Ф9. Сценарная архитектура (Часть A нового ТЗ)
  Ф10-12. Сценарий №2 «Конфликт Ткацкого Цеха»
```

---

## 7. ПОЧЕМУ СКРЫТЫЕ БАГИ НЕ ПОПАЛИ В ТЗ

### 7.1. ТЗ писались по симптомам, не по трассировке
TZ-INFRA-1 — 58 багов — это всё **видимые** баги (кнопка не работает, time freeze, LLM markers в UI). Скрытые баги (case mismatch, unreachable branch) **невидимы** без трассировки кода.

### 7.2. Тесты не ловят интеграции
737 проходящих тестов проверяют подсистемы **изолированно**. Когда DecisionHub тестируется — он получает mock beliefs. Когда CrystallizedBeliefModifierResolver тестируется — он получает mock intents. Никто не тестирует **вместе**.

### 7.3. `try/except` маскирует баги
StateApplicator оборачивает всё в try/except — если TraitDriftEvent падает, состояние молча откатывается. Это design choice ("не ронять тик"), но он маскирует баги.

### 7.4. `verify_autonomous_world.py` не существует
TZ_Aktualizirovano §3.7 ссылается на файл `backend/scripts/verify_autonomous_world.py`. **Файла нет.** Директории `backend/scripts/` нет. AWC-точки D/E/F/G/H не имеют автоматизированной проверки.

### 7.5. Скрытые тесты (`_skip_` prefix)
`_skip_test_affective_pressure.py` — pytest не собирает файлы с `_skip_` prefix. ADR-O "Pressure → Emotion" pipeline никогда не реализован, тест скрыт переименованием вместо удаления или `@pytest.mark.skip` с причиной.

### 7.6. False sense of safety
- `InvariantHealthChecker` репортит 0 нарушений — но сам checker не проверяет нужные invariant'ы (UNDOC-008)
- SHI=100% — но метрика определена так, что 100% = "всё работает", а реально 100% = "мы не измеряем"

### 7.7. ADR описаны, но не реализованы
- ADR-O "Pressure → Emotion" — описан, не реализован
- ADR-O "Active Inference / Free Energy" — описан (ExpectationStore), код не подключён
- ADR-O "ResolutionEngine gap learning" — описан, 380 строк мёртвого кода
- ADR-O "RoleTransition" — описан, код не подключён

---

## 8. РЕКОМЕНДАЦИИ К СОЗДАТЕЛЮ

### 8.1. Создать новое ТЗ: TZ_RUNTIME_AUDIT_UNDOCUMENTED_BUGS.md
Зафиксировать все 36 багов (UNDOC-001…016 + DEEP-001…020) с evidence и шагами фикса. Без этого ТЗ любой следующий разработчик (или AI-агент) снова споткнётся о те же скрытые баги.

### 8.2. ФАЗА -1 — первой
Прежде чем Фаза 0 (тривиальные правки) и Фаза 1 (AWC) — сделать Фазу -1 (5 P0 багов, 6 часов). Без них:
- DM не отвечает (UNDOC-001/002) → нельзя тестировать Stage 1-2
- L2.5 не влияет на behavior (DEEP-002) → нельзя тестировать emergent cycle
- Somatic veto не работает (DEEP-004) → нельзя тестировать combat
- Emotion не меняется (DEEP-006) → нельзя тестировать AffectiveIntegrator

### 8.3. Создать `verify_autonomous_world.py`
TZ_Aktualizirovano §3.7 ссылается, файла нет. Это критическая инфраструктурная дыра — без скрипта AWC-точки D-H непроверяемы.

### 8.4. Расширить IPT.py интеграционными тестами
Текущие 5 invariant probe tests проверяют только happy path idle_tick. Нужны:
- `test_state_actually_mutates_after_tick` — HP меняется после attack
- `test_emotion_actually_mutates_after_event` — emotion меняется после события
- `test_belief_actually_affects_decision` — crystallized belief меняет intent choice
- `test_memory_survives_restart` — L2.5 beliefs сохраняются между сессиями

### 8.5. Решить: реализовать или удалить мёртвый код
3 подсистемы описаны в ADR, но не подключены:
- ResolutionEngine (380 строк)
- ExpectationStore (150 строк)
- RoleTransition.execute_transition

Для каждой — решение: реализовать (если нужно для Сценария №1/№2) или удалить (если не нужно). Текущее состояние — худшее из миров: код есть, не работает, вводит в заблуждение.

### 8.6. Audit existing 114 failing tests
114 тестов падают (13% от 861). Это означает, что код дрейфовал от тестов. Нужно: либо починить тесты, либо обновить под новый код. Список top-10 падающих тестов в `/home/z/my-project/work/pytest_audit.md`.

---

## 9. СЛЕДУЮЩИЕ КОНКРЕТНЫЕ ШАГИ (порядок)

### Сегодня (6 часов = Фаза -1 P0)
1. `dm_agent.py:149` — вынести `from ...scene_state_manager import SceneStateManager` из `if _is_session_start:` блока наверх
2. Запустить DM-тест — должен перестать отвечать "Ничего не произошло"
3. `crystallized_belief_modifier_resolver.py` — все UPPERCASE intent keys → lowercase
4. `pressure_translator.py:60-72` — все UPPERCASE constraint keys → lowercase; убрать `Intent.RESIST`
5. `state_applicator.py:780` — вынести `sel_trace_commit` handler из `if _ema_delta != 0.0:` блока
6. `pytest backend/tests/` → регрессия должна остаться прежней или улучшиться

### Завтра-послезавтра (10 часов = Фаза -1 P1)
7. `state_applicator.py:211-219` — исправить `TraitDriftEvent` kwargs (`tick=...` → `tick_id=...`, `trait=...` → `target_id=...`, etc.)
8. Добавить SQLite backing в `crystallized_belief_store.py`
9. После DEEP-007 фикса — combat damage начнёт применяться
10. `session_memory_Open_road.jsonl` — проверить writer, 80 дней потеряно

### На неделе (3-5 дней = Фаза -1 P2-P4)
11. Создать `backend/scripts/verify_autonomous_world.py` (реализовать AWC проверку)
12. Расширить `IPT.py` интеграционными тестами
13. Реализовать ADR-O "Pressure → Emotion" pipeline
14. Вынести player из NPC pipeline (UNDOC-010/011)
15. Regression: 861 тестов → целимся в 800+ проходящих

### Только после Фазы -1
16. Фаза 0 (тривиальные правки survival/raise/campaign_id)
17. Фаза 1 (AWC + npc_conversation.py + CI/CD)
18. ... далее по прежнему порядку

---

## Приложения

- **Приложение A:** `/home/z/my-project/work/runtime_audit.md` — 16 UNDOC багов с evidence из логов
- **Приложение B:** `/home/z/my-project/work/pytest_audit.md` — 114 падающих тестов, 11 skipped, 35+ TODO
- **Приложение C:** `/home/z/my-project/work/pipeline_deep_audit.md` — 20 DEEP багов с архитектурным анализом
- **Приложение D:** `/home/z/my-project/worklog.md` — журнал мульти-агентной верификации (4 агента)
- **Приложение E:** `/home/z/my-project/work/tz_docs_summary.md` — карта 14 существующих ТЗ
- **Приложение F:** `/home/z/my-project/work/wave1_status.md` — статус Wave 1 по коду
- **Приложение G:** `/home/z/my-project/work/wave3_status.md` — статус Части A нового ТЗ
- **Приложение H:** `/home/z/my-project/work/wave2_4_5_status.md` — статус Wave 2/4/5
- **Приложение I:** `/home/z/my-project/work/audit_verification.md` — верификация фактов аудита нового ТЗ
- **Приложение J:** `/home/z/my-project/work/installer_docs_summary.md` — сводка по 3 установочным TZ
