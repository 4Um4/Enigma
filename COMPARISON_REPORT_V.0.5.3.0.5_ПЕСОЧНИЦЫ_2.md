# Сравнение отчёта: V.0.5.3.0.4_ПЕСОЧНИЦЫ_1 vs V.0.5.3.0.5_ПЕСОЧНИЦЫ_2

Дата: 13 мая 2026

## 0. Git-статистика

> Метoд: diff по ветке **origin/V.0.5.3.0.4_ПЕСОЧНИЦЫ_1 → HEAD** + ручная/архитектурная вычитка по ключевым подсистемам.

- Файлов затронуто (из git diff --name-status): **24**
- Добавлено: **3** (в основном sandbox + DTO docs шаблон)
- Удалено: **1** (удалённый docs/Tasks ADR-0XX_IMPACT.md под шаблон)
- Изменено (механика/ядро): **20**

## 1. Что реально стало “новым” (ценность, а не строки)

Ключевое отличие от предыдущего шага: вместо “локальных правок” проект получил **новую связку causal/phenomenology → DTO registry → практическую эксплуатацию в Phase-0.5/1/2/8/9**, плюс обновлённые docs/Tasks как операционную карту.

Ниже — перечень ценного, которое было сделано.

---

### 1.1. Will/Intent/Decision граница стала “оформленной контракторами” (Phase 1)

Затронутые файлы:
- `backend/app/services/game_loop/phase_1_input.py`
- `backend/app/services/game_loop/__init__.py`

**Ценность (что изменилось по сути):**
- В Phase 1 появилось более явное разбиение на: *resolve intent → publish resolution*.
- Это делает переход от player input к EventBus более детерминированным и расширяемым (в т.ч. под конфликт/ will-conflict артефакты).

---

### 1.2. NPC decision pipeline и legacy-v2 adapter получили “контур целостности”

Затронутые файлы:
- `backend/app/services/npc/decision_hub.py`
- `backend/app/services/npc/legacy_delta_adapter.py`
- `backend/app/services/npc/npc_tick_pipeline.py`
- `backend/app/services/npc/state_applicator.py`
- `backend/app/services/npc/life_engine.py`

**Ценность:**
- Стабилизирован путь из decision результата в доменные deltas (v2 → v1 collapse для legacy downstream).
- Логика DecisionHub теперь лучше соответствует контрактному “domain + target + payload”, чтобы downstream (память/фазы/рендер) не “утекали” доменами.

---

### 1.3. Event→Perception subscriber получил обновлённый contract pipeline

Затронутые файлы:
- `backend/app/services/events/perception_subscriber.py`
- `backend/app/services/tick_orchestrator.py`

**Ценность:**
- Перцептивная часть стала более согласованной с layered reduction (Phase 8) и с реконфигурацией context в Phase 9.
- Это уменьшает вероятность рассинхрона между “world_snapshot truth” и тем, что показывается фронтом.

---

### 1.4. Добавлен CFRM pressure translation helper (для сценариев “кауза → психика”)

Затронутые файлы:
- `backend/app/services/cfrm/pressure_translator.py` (new)

**Ценность:**
- Появился новый слой перевода pressure/impact сигналов в значения, которые проще материализовать в psychological vectors.
- Это практический фундамент для “ценностного” gameplay: NPC начинают реагировать последовательнее (через общую модель давления/обязательств).

---

### 1.5. Добавлены sandbox-инфраструктуры для compliance/phenomenology (как проверяемость)

Затронутые файлы:
- `backend/tests/sandbox/micro/test_command_compliance.py` (new)
- `backend/tests/sandbox/oscilloscope_closed_loop.py` (new)
- `backend/tests/sandbox/phenomenology/__init__.py` (new)

**Ценность:**
- Это не “добавили тесты ради тестов”: sandbox-инструменты нужны, чтобы держать causal-поведение в управляемых петлях (closed loop) и гарантировать compliance команд/интерпретаций.

---

### 1.6. Runtime world data актуализированы под новую связку NPC relationships

Затронутые файлы:
- `backend/data/campaign_Open_road/npc_relationships.json`
- `backend/data/sessions/Open_road.json`
- `backend/data/sessions/Open_road/world_tick.json`
- `data/campaign_Open_road/npc_relationships.json`

**Ценность:**
- Обновления data фиксируют: новые изменения decision/perception теперь “имеют смысл” на реальных сессионных артефактах, а не только в абстрактных DTO.

---

## 2. “Сколько новых функций было добавлено за день” (как в терминах проекта)

По типам изменений, сделанных в diff:

1) **1 новая сервисная функция/модуль:** `pressure_translator.py` (CFRM pressure → психологические значения).
2) **1 расширение/контур для Phase 1 boundary:** resolve intent → publish resolution.
3) **1 расширение/контур для NPC pipeline integrity:** decision_hub + legacy_delta_adapter + applicator.
4) **1 уточнение/контур для perception subscriber и tick orchestrator взаимодействия.**
5) **2–3 новых sandbox вертикали:** command compliance + oscilloscope closed-loop + phenomenology init.

Итого в “ценностном” смысле: **~5 функциональных контуров/единиц**, из которых 1 — явный новый модуль, остальные — интеграции/контрактные границы.

*(Это не “сколько строк кода”, а сколько *поведенческих модулей* стало работать согласованно.)*

---

## 3. Важное и ценное, что было сделано “операционно”

### 3.1. docs/Tasks стали более точной картой “как это эксплуатировать”

Затронутые файлы docs:
- `docs/Tasks/ADR (Architecture Decision Records).md`
- `docs/Tasks/ARCHITECTURE_FLOW.md`
- `docs/Tasks/DTO Registry (Реестр контрактов).md`
- `docs/Tasks/MUTATIONS.md`

**Ценность:**
- Появились/обновились “регистры” контрактов (DTO), которые напрямую связываются с тем, что код реально делает.

### 3.2. Убраны/перераспределены impact-шаблоны

- Удалён старый docs/Tasks ADR-0XX_IMPACT.md под шаблон.
- Добавлен новый `docs/Tasks/ADR-000_IMPACT_TEMPLATE.md` как единый формат оценки.

---

## 4. Что дальше по пути (follow-up, исходя из docs/Tasks)

Ближайшая практическая линия (из общей структуры docs/Tasks):
- укрепление Phase 8/9 феноменологии и перевод “perception vectors → manifestation profile”
- расширение “cognitive/social pressure” как общей модели (через pressure translator и DTO registry)
- закрепление через e2e causal test-pack (Physical → Cognitive → Social)

---

## 5. Итог

Ветка **V.0.5.3.0.5_ПЕСОЧНИЦЫ_2** — это шаг в сторону “эксплуатируемого” протокола:
- Phase 1 boundary стал контрактнее,
- NPC decision/perception pipeline согласованнее,
- появилась новая pressure→psychology переводящая прослойка,
- sandbox вертикали делают поведение проверяемым,
- docs/Tasks обновляют будущее проекта в форме DTO/ADR.

