# ENIGMA NPC Authoring Integration v0.1 — археология и спецификация интеграции авторинга NPC с Map Editor / World & Asset Workbench

| Поле | Значение |
|---|---|
| **Статус** | DRAFT v0.1 — на вердикт владельца. Реализация не начата, код не менялся |
| **Дата** | 2026-10-29 |
| **База археологии** | ветка `V.0.5.4.4.8_Движемся_вперед_3` (корпус «Enigma-V.0.5.4.4.8_-_-_3», 572 .py в `backend/app`) |
| **Тип работы** | read-only археология кода + согласование спецификации; никаких правок production-кода, тестов, флагов, ADR и канонических хранилищ |
| **Заказчик** | владелец проекта (Мастер) |
| **Место в документообороте** | дочерний документ к `ENIGMA_MAP_EDITOR_ROADMAP_v1_4.md` (§5А.4–5А.5, §7.5, §10.5) и к `ENIGMA_ROADMAP_v4_12_WPS.md` (§13 CCH, §27 Map Editor integration, §0.2 Ступень 0). Не заменяет и не переписывает их |
| **Сопутствующие документы** | `ТЗ_преемнику_Map_Editor_S349.md`, `BLUEPRINT_FORMAT_SPEC_v1.md`, `TZ_CCH-02_Biography_State_Audit.md`, `ТЗ ПРИЕМНИКУ — Enigma _ CCH build-11R, кампания «silver_wolf».md` |
| **Как читать** | Все ссылки вида `file:line` проверены на коде базы археологии. Утверждения дорожных карт использованы как проектные контракты, а не как доказательство работающего кода: каждый пункт сверен с фактическим кодом |

> **Правило ветки (§10.6 roadmap редактора, `:1210`):** «наличие поля или кнопки не считается реализацией». Настоящий документ удерживает этот стандарт: везде, где возможно, различаются *существует и работает сквозным образом* / *существует частично* / *существует только в документе*.

---

## 0. Паспорт задания и границы документа

Исходное задание: провести архитектурную археологию ветки и детализировать интеграцию создания, настройки, размещения и запуска NPC в редакторе карт — так, чтобы автор мог создать или выбрать человека, который уже прожил часть жизни, описать его биографию естественным языком, проверить структуру, разместить NPC в мире и запустить его в существующую симуляцию без ручного программирования отдельного персонажа.

Настоящий документ закрывает пункты задания:

- **Блок A (§2)** — археологический отчёт: таблица БЫЛО / ФАКТИЧЕСКИЙ КОД / ПРОБЕЛ / ЦЕЛЕВОЙ КОНТРАКТ по семи направлениям задания §3;
- **Блок B (§3)** — диаграмма целевых границ (таблица «зона / владелец / канонический источник / запреты») для Character Authoring / Character Blueprint / Placement / Runtime State / Chronicle / Memory / Decision / Schedule / Visual Casting;
- **Блок C (§4)** — матрица текущих контрактов и пробелов с точными ссылками на код и документы;
- **UX-архитектура (§5)** — приоритетно детализированный минимальный UX-путь из задания §6, переиспользующий существующие интерфейсы;
- **Матрица интеграции (§6)** — требования с уникальными ID, зависимостями, владельцами контуров, этапами и критериями приёмки, покрывающими все 12 обязательных направлений задания §7;
- **Блок D (§7)** — предложение по интеграции существующих дорожных карт (включая проверенные на коллизии номера ME-R-630…633 и ME-E2E-10/11 — финальное присвоение за владельцем);
- **Блок E (§8)** — пошаговая последовательность реализации с предпосылками, рисками миграции и доказательствами закрытия;
- **Блок F (§9)** — перечень архитектурных решений, требующих вердикта владельца (по выбору владельца — только вопросы, без вариантов).

Документ **не** содержит: реализации, кода, изменений канонических хранилищ, новых хранилищ «на будущее», переписывания существующих дорожных карт.

---

## 1. Резюме для владельца (5 главных выводов)

**Вывод 1. Целевой процесс уже существует «на 70%» — но он разорван на три несмешивающихся потока, и его недостающие швы известны по имени в документах.** Контур личности живёт в `config/npc/` (трек CCH), контур размещения — в `frontend/map_editor/` (только 4 поля: `ref_id, position, room_id, sprite`), контур поведения — в backend. Мост между размещением и личностью — единственный строковый инвариант `individuals.id == editor.npcs[].ref_id` (`backend/app/services/npc/npc_loader.py:351-352, 407-409`). Ровно этот стык в дорожной карте редактора закрыт открытым гейтом §10.3 в.12 («граница с CCH/Authoring» → S-ME5) и вопросом в.13 («генерация NPC»). Спецификация ниже не создаёт новый процесс — она соединяет существующие CCH-конвейер, сеялку, Visual Casting и placement-механику в один авторский путь.

**Вывод 2. Канонический конвейер «человеческий текст → канон → стартовое состояние» работает и детерминирован, но применяется только при новой игре и сеет не всё.** Цепочка `author_text → LLM-декомпозиция (GBNF, temp=0) → LLM_DRAFT → подтверждение автора → канон JSON → сеялка → EventMemory/отношения/импринты/убеждения` закрыта сессиями CCH-0…CCH-7 (§0.2 родительского roadmap). Границы: сеялка берёт только `AUTHOR_CONFIRMED/AUTHOR_AUTHORED` (`backend/app/services/chronicle/chronicle_seeder.py:116-121`); `TRAIT_SEED`/`DESIRE_SEED`/`PORTRET` не сеются («ждут Character Calibration / Desire», `chronicle_seeder.py:366-386`); `BELIEF_SEED` отсекается закрытым реестром `BeliefType` (только DANGER/PLAYER_HOSTILE, `backend/app/models/npc/beliefs.py:45-53`); отношения на неразрешённую сущность молча не сеются (`chronicle_seeder.py:283-285`); опция `CREATE_NEW_NPC` — заглушка «вне скоупа» (`backend/app/api/routes_chronicle.py:570-579`).

**Вывод 3. Главный технический разрыв pipeline — персистентность личного состояния NPC.** Писатель `npc_runtime.json` / `runtime:{cid}` существует (`backend/app/services/game_loop/json_persistence_adapter.py:132-149`, `sqlite_persistence_adapter.py:169-189`), но **в тик-пути не вызывается**: `commit_phase.execute_persistence` → `atomic_commit_all` передаёт сцены без NPC-состояний (`backend/app/services/phases/commit_phase.py:94-146`; `backend/app/services/scene_state_manager.py:1318-1320` «Фаза 10 не пишет в БД напрямую»). Личное состояние (body_state, психика, narrative_cache) живёт в RAM-кэше `LifeEngine._npc_cache` (`backend/app/services/npc/life_engine.py:985-992`); между рестартами процесса переживают только позиции (в `scene_state.npc_positions`) и отношения. Подтверждение из собственного стенда проекта: «load_npc_runtime=None … NPC data NOT persisted» (`backend/tests/sandbox/SUPERBOX/drift_laboratory.py:763`). Пока это не закрыто, «жизнь NPC и сохранение последствий» (задание §4) не выдерживает перезапуска.

**Вывод 4. Редактор сегодня умеет только размещать готовых людей.** Создание NPC с нуля в UI отсутствует: палитра NPC = дропдаун из `config/npc/individuals` (`frontend/map_editor/data/npc_data.py:27-50`, дропдаун `frontend/map_editor/editor_core.py:429-453`); `NPC_PRESETS` (`frontend/map_editor/data_manager.py:648-679`) — легаси-фоллбэк спрайтов, не источник персонажей; Blueprint/Instance-механика (ME-1.3) покрывает только `objects` — `_fold_for_save` итерирует лишь по objects, NPC не сворачиваются (`data_manager.py:1247-1251, 1234-1278`). При этом правка психики/портретов из редактора пишет **напрямую в глобальный** `config/npc/individuals/<id>.json` (`npc_data.py:68-118`) — то есть одинакова для всех кампаний; per-campaign инстансов нет. `map_editor/characters/**` (зона Этапа 05, §9.2:940) не существует.

**Вывод 5. Обнаружены дубли источников истины и мёртвые поля — они не блокируют интеграцию, но должны получить вердикт до Этапа 05, чтобы новые контракты не легли на мусор.** Ключевые: отношения NPC↔NPC в двух источниках (`village_relations.json` vs хроника — канон вытесняет статик, `npc_loader.py:672-699, 698`); прошлое в двух источниках (`origin_events` vs канон — канон приоритетен, `npc_loader.py:981-991`); три несовпадающих значения HP у одного NPC (индивид / архетип 120 / константа 100); unit-баг `loyalty_true: 1.0` при шкале 0–100 у Борко (`config/npc/individuals/borko.json:45` → `int()` в `npc_loader.py:451-453`); мёртвые поля `hidden_truth`, top-level `hp/max_hp`, top-level `abilities`, `combat_stats`, `status_profile.power`; четыре источника одной и той же локации; ID-дрейф в тестовых данных (`npc_lusya`, `npc_1→player`). Полный список — §2.8.

**Что запрошено у владельца:** вердикты по списку §9 (13 вопросов), после — GO на Шаг 1 из §8. Ни один шаг §8 не исполняется без отдельного разрешения.

---

## 2. Блок A — Археологический отчёт

### 2.0. Сводная таблица БЫЛО / ФАКТИЧЕСКИЙ КОД / ПРОБЕЛ / ЦЕЛЕВОЙ КОНТРАКТ

Легенда статусов ФАКТА: **ЖИВО** (сквозным образом, с потребителями), **ЧАСТЬ** (существует, но неполно), **СПЯЩЕЕ** (схема/читатель есть, данных или писателя нет), **МЁРТВОЕ** (канал построен, потребителя нет), **НЕТ**.

| # | Было (заявление дорожных карт / ожидание) | Фактический код (file:line) | Пробел | Целевой контракт |
|---|---|---|---|---|
| A1 | Размещение готовых NPC на карте — работающий механизм | **ЖИВО**: дропдаун из `config/npc/individuals` (`editor_core.py:429-453`), размещение (`tools/interaction.py:196-217`), CRUD (`data_manager.py:1715-1749`), undo (`core/commands.py:281-325`), drag (`editor_core.py:1186-1194, 1262-1271`), сериализация `npcs[{ref_id, position, room_id, sprite}]` (`campaigns/Open_road/locations/tavern.json:1596-1853`), валидатор (`schema_validator.py:242-280`) | `room_id` не пересчитывается при drag (`editor_core.py:1262-1266`); NPC не копируются (`editor_core.py:1278-1280`) | Placement = типизированная ссылка на личность; локальные переопределения — закрытый реестр (§6, NPC-I-04) |
| A2 | Character Blueprint с 9 группами слоёв (ME-R-401) | **НЕТ в коде**: только скелет в `BLUEPRINT_FORMAT_SPEC_v1.md:61-66` («слои заявлены, наполняются Этапом 05»); `map_editor/characters/**` отсутствует | Весь Этап 05; старт разрешён только после ME-GC-3 (`:949`) | ME-R-401/402/403/404 остаются основой; детализация — §6–§8 этого документа |
| A3 | Создание NPC с нуля в редакторе (§5А.4) | **НЕТ**: выбор только из существующих индивидов (`npc_data.py:27-50`); создание не реализовано | Нет ни UI, ни данных, ни конвейера «маска → канон» | Цикл: биография → канон через CCH → индивид-слой из компонентов (§8, Шаги 3–5) |
| A4 | Хранилище личности NPC | **ЖИВО**: `config/npc/individuals/*.json` (6 файлов) — id/name/name_forms/gender/tier/psyche/drives/status_profile/routine/activity_map/origin_events/visual_casting; наследование base→archetype→mixin→individual (`npc_loader.py:88-118, 318-335`) | Возраст не материализован: `birth_epoch`/`age_at_game_start` читаются (`npc_loader.py:479-484`), но в JSON не заданы; `game_start_age` только у `maid_lusya` | Каталог индивидов = единственный SSOT личности; возрастная ось обязательна (NPC-I-14) |
| A5 | Биография → история/состояние | **ЖИВО (новая игра)**: канон `config/npc/chronicles/*.json` → сеялка → EventMemory/relationships/imprints/beliefs (`chronicle_seeder.py:366-393`; `npc_loader.py:962-996`); легаси-фоллбэк `origin_events` при отсутствии канона (`npc_loader.py:515-553, 990-991`) | Сеются не все kind'ы (см. Вывод 2); гейт «только новая игра» закрывает resume-путь (`npc_loader.py:962-968`) | Материализация — только через сеялку; биография ≠ знания (NPC-I-07/10) |
| A6 | Память/убеждения/знания из прошлого | **ЧАСТЬ**: события → `EventMemory` с `tags=("chronicle:<entry_id>",)` — происхождение факта = тег (`chronicle_seeder.py:163-203`); KNOWLEDGE_LINK → изоляция «кого в знающих нет — записи не получает» (`:206-270`); BELIEF_SEED отсекается реестром BeliefType (`beliefs.py:45-53`); `NpcCausalBelief`/`cause_candidates` — слой 2 канона без runtime-потребителя (`routes_chronicle.py:790-794`) | Убеждения-смыслы, черты, мечты ждут контуров Calibration/Desire/CCH-03; память в решениях — «только числами» (§16.0 род. roadmap) | Никаких новых хранилищ; расширение существующих (§3, зоны Memory/Decision) |
| A7 | Перенос NPC между локациями | **ЖИВО**: RAM-очередь `_pending_transfers` (`tick_orchestrator.py:1225-1310`), инжект в целевую сцену (`:846-874`), атомарность (`scene_state_manager.py:888-929`), вычистка фантомов (`:590-630`); dict NPC переезжает ссылкой — психика/отношения не копируются | Персистентность личного состояния между рестартами **разорвана** (Вывод 3) | NPC-I-05: writer runtime-состояния в тик-пути + round-trip-тест |
| A8 | Расписание и его изменение обстоятельствами | **ЖИВО**: `routine.schedule` «HH:MM-HH:MM → activity» (`life_engine.py:2355-2370`), `update_routine` (`:1972-2268`), need-override приоритет 0.8 vs schedule 0.6 (`:1546-1740`), директивы игрока (`:2016-2022`), угроза/viability mask (`:2033-2037, 1874-1927`), кризис LifeProject (`:2070-2084`), Commitment Arbiter (`phases/simulation.py:122-135`) | Формат без дней недели/исключений; мост `_archetype`→`current_role` отсутствует — ролевые фильтры решений инертны для конфиговых NPC (`decision_hub.py:90-106, 1040-1045`) | Расписание = «обычная деятельность с причинными отклонениями» — контракт уже фактически выдержан; зафиксировать тестом (NPC-I-08) |
| A9 | Роли/архетипы/деятельности | **ЧАСТЬ**: архетипы несут только тело/маркеры/предметы (`config/npc/archetypes/guard.json`), расписания живут в индивидах; поведенческие диспозиции захардкожены (`domain/epistemic_dispositions.py:16-41`); каталог деятельностей = 2 записи (`activity_catalog.py:80-87`); Living Activity контур за флагом OFF (`desire_generator.py:42-48`) | Архетип ≠ поведенческая роль; рассинхрон реестров архетипов | Роль узла (ME-R-603, роли узлов уже в коде `editor_core.py:1424-1431`) + мост archetype→role (вопрос владельцу §9.9) |
| A10 | Внешность/Visual Casting | **ЖИВО**: `VisualCastingEditor` (`visual_casting_editor.py`, кроп/эмоции/направления/threshold/outline), сохранение в `visual_casting` индивида (`npc_data.py:68-83`) и локальный `sprite` в placement (`editor_core.py:1664-1699`); потребление игрой (`frontend/visual_casting_repository.py:28-37`, рендер карты `scene_renderer.py:61-78`) | Рендер карты берёт только направление «S» из словаря (`render/map_renderer.py:422-424`); у `goran.json` нет `visual_casting`; backend визуал не потребляет | Visual Casting не дублировать; довести потребление направлений — отдельно (вне NPC-интеграции) |
| A11 | Editor → simulation | **ЖИВО (сцена и пространство)**: `editor_locator.py:21-31` (два места поиска) → `scene_factory.py:49-285` (objects `:73-84`, npcs `:86-101`, player `:104-120`) → scene_state → SQLite/JSON; пространственный поток: `spatial_registry_builder` → `compiled/spatial_registry.json` → Spatial Oracle (`game_loop_bridge.py:152-190`) | Из `npcs[]` до runtime доезжают ровно 4 поля (`ref_id, position, room_id, sprite` — спрайт только фронтендом); round-trip редактор↔сейв **отсутствует** (S-ME1/ME-1.8 не закрыт, `ТЗ_преемнику:79-80`) | Два несмешивающихся потока сохраняются; расширение placement-полей — только через типизированные overrides (NPC-I-04) |
| A12 | Сохранение/загрузка | **ЧАСТЬ**: `campaign_state.json` + `saves/enigma_runtime.db` (прод-путь, `game_loop_builder.py:39-44`); позиции/активность/видимость NPC в `scene_state.npc_positions`; отношения — синхронизация между сценами (`scene_state_manager.py:289-292`) + миграция legacy (`relationship_state_store.py:291-377`) | Личное состояние NPC не пишется (Вывод 3); events_tick blob не заполняется в тик-пути (`sqlite_persistence_adapter.py:290-302`); WorldProjectionBuffer VERDICT=OFF (`scene_state_manager.py:1311-1316`) | NPC-I-05; диагностика готовности — NPC-I-11 |
| A13 | Chronicle в редакторе | **ЖИВО**: F7 → `ChronicleScreen` = тонкая обёртка над `ChronicleEditorCore` (`map_editor/chronicle/editor_screen.py:30-71`); ядро — 3 панели, F1/F2/Ctrl+G/F9/Shift+F9/Ctrl+O/Ctrl+D/Ctrl+U/Ctrl+S/C+1..4 (`chronicle_app.py:135-208`); транспорт — HTTP API (`chronicle_editor/api.py:13-19`) | Автономный запуск захардкожен на `silver_wolf` (`chronicle_app.py:886-891`); UX-1…UX-4 и UX-FIX-2..4 из §0.2 род. roadmap открыты | Chronicle = единственный контур биографии; не дублировать в Map Editor (зона «НЕ эта карта», `ME_ROADMAP:944`) |
| A14 | Catalog/шаблоны NPC | **ЧАСТЬ**: архетипы+миксины+base — backend-наследование (`npc_loader.py:88-118`); `NPC_PRESETS` редактора — легаси-спрайт-фоллбэк, не совпадает с реестром архетипов (`data_manager.py:648-679`) | Два несовпадающих реестра «типов NPC»; шаблоны/генерация ME-5.2 отсутствуют | Один реестр; шаблоны — через archetype+mixins (NPC-I-12) |
| A15 | Отчёт готовности NPC к запуску | **НЕТ**: валидатор `schema_validator.py:242-280` проверяет только placement-схему (ref_id уникален, координаты — числа, room_id существует); канонической связки «NPC готов к жизни» нет | Нет диагностики: канон канонизирован? возраст задан? расписание покрывает сутки? visual_casting есть? | NPC-I-11: readiness-отчёт как read-only диагностика + гейт перед симуляцией |
| A16 | Происхождение фактов в runtime | **ЧАСТЬ**: `tags=("chronicle:<entry_id>",)` на EventMemory — происхождение есть (`chronicle_seeder.py:163-203`); Character Debugger F11 — «СЕЙЧАС/ИСТОЧНИКИ» (CCH-4, `§0.2` род. roadmap; `windows/debug_window.py:15-19`) | DEBUG_MANIFEST определён, но не зарегистрирован (grep — только определение); эпистемический store in-memory (`npc/epistemic_store.py:14-18`) — не переживает сессию | Provenance через существующие теги; не строить второй источник (NPC-I-09/10) |

### 2.1. Где хранятся определения NPC, идентичность, характеристики, биография, исходные события

Полный инвентарь хранилищ (читатели/писатели подтверждены grep'ом):

| Хранилище | Путь | Содержание | Читатели (file:line) | Писатели |
|---|---|---|---|---|
| Индивиды (SSOT личности) | `config/npc/individuals/*.json` (6: borko, goran, lusya, orm, shadow, tornin) | `id, name, name_forms, gender, tier, description, voice_profile, backstory, author_notes, status_profile, hidden_truth, drives, psyche, flags, location, activity_map, routine.schedule, hp/max_hp, origin_events, core_orientation, visual_casting, _archetype, _mixins` | `backend/app/services/npc/npc_loader.py:160,328,742,766`; `backend/app/services/chronicle/registry_builder.py:48`; `backend/app/services/input/intent_compressor.py:409`; `frontend/map_editor/data/npc_data.py:34,57,72,90,105`; `frontend/visual_casting_repository.py:28-37` | Редактор: `npc_data.py:68-83` (visual_casting), `:101-118` (psyche/drives) — **глобально, для всех кампаний** |
| Архетипы | `config/npc/archetypes/*.json` (7: `_base_humanoid` + 6 профессий) | `body_profile` (max_hp/abilities/base_ac), `visible_markers`, `carried_objects`; расписаний нет | `npc_loader.py:88-118` (наследование), `role_transition.py:118` | никто (read-only) |
| Миксины | `config/npc/mixins/veteran.json` | psyche-оверрайд, combat_stats, abilities | `npc_loader.py:105-108` | никто |
| Соц-база | `config/npc/social/village_relations.json` | матрица `relations[npc][target]{nature, base_trust, base_affection}` (0–1) | `npc_loader.py:176-191` (загрузка), `:194-273` (enrichment ×100) | никто |
| Хроники (канон прошлого) | `config/npc/chronicles/*.json` (6, ~1300–1800 строк) | `schema_version, chronicle_id, npc_ref, author_text, entries[], game_start_age, white_spots, event_groups, canonical*`; слои 2 (S366): `npc_beliefs[]`, `cause_candidates[]` | `chronicle_seeder.py:74-111`; `npc_loader.py:634-699, 967-996`; `routes_chronicle.py`; `chronicle_projections.py:90,612-614` | `chronicle_store.py:444-452` (save_canonical/save_draft) через API; UI Chronicle; `scripts/redecompose_all_npc.py` |
| Черновики хроник | `saves/<campaign>/chronicle_drafts/<npc_id>.json` | non-canonical `ChronicleDocument` | `chronicle_seeder.py:83` (drafts_root), `chronicle_app.py:304,338,474` | `routes_chronicle` (save_draft) |
| Канон секретов | `config/canon/truth_state_tavern.json` | секреты + `initial_holders` | `npc_loader.py:559-625` (`_seed_canon_secret_memories`) | никто |
| Голосовые архетипы | `config/canon/voice_archetypes/*.yaml` | voice_profile поверх individuals | `npc_loader.py:467-474` | никто |
| Editor-JSON локаций | `frontend/map_editor/campaigns/Open_road/locations/*.json` | геометрия + `npcs[{ref_id, position, room_id, sprite}]` | `data_manager.py:830-885`; `editor_locator.py:21-31`; `scene_factory.py:87-101` | `data_manager.py:1048, 1715-1749`; `campaign_manager.py:153-213` |
| Шаблоны редактора | `frontend/map_editor/location_templates/*.json` | дубликаты трёх локаций (ME-D15) | `data_manager.py:33` | редактор |
| Backend-шаблоны локаций (легаси) | `backend/data/locations/location_templates.json` | `npc_defaults` (не `npcs[]`), positions-граф, time_variants | `scene_factory.py:171-185`; `scene_state_manager.py:1428-1432, 1583` | никто (легаси) |
| Сейв сцены | `saves/<campaign>/campaign_state.json` + SQLite `saves/enigma_runtime.db` | `scene_state` c `npc_positions{id: {name, location_id, position, activity, visible, local_position, editor_room_id}}` | `scene_state_manager.py:467-475` | `:477-481` (JSON), Фаза 10/atomic_commit (SQLite) |
| Runtime-оверлей NPC | `saves/<campaign>/npc_runtime.json` | рекурсивный мерж поверх статики, индекс по `id` | `tick_utils.py:381-383`; `npc_loader.py:280-414` | **писатель в проде отсутствует** (Вывод 3) |
| Аватар игрока | `saves/<campaign>/player_avatar.json` | `{sheet, profile, state, dialog_journal}`; `state.npc_id = имя игрока` | `player_avatar_service.py:127-140` | `save_avatar` |
| Отношения v1 (легаси) | `saves/<campaign>/npc_relationships.json` | плоские directed-пары `{«npc→player»: {trust, fear}}` | `relationship_state_store.py:68-70, 291-377` (миграция v1→v2) | мигратор (переименование в `.migrated`) |

Схема элемента `origin_events[]` (пример `config/npc/individuals/goran.json:93-150`): `summary, secret_id?, importance, tags[], is_secret, known_by[], hidden_from[], accessibility, decay_rate, emotion_tag?`.

### 2.2. Как связаны NPC_PRESETS, npc_data.py, DataManager, данные кампаний, npcs в локациях, Chronicle Editor и Character Blueprint

- **NPC_PRESETS** (`frontend/map_editor/data_manager.py:648-679`) — легаси-словарь спрайт-фоллбэков по «типам» mage/warrior/person/thief/cow/knight; в деривации `ENTITY_SPRITE_MAP` участвует как второй приоритет после OBJECT_PRESETS и до NPC_SPRITE_MAP (`sprite_registry.py:215-227`). Как источник персонажей не используется: комментарий `data_manager.py:613-615` прямо говорит «используются в системе NPC, не размещаются как объекты».
- **`data/npc_data.py`** (118 строк, фасад, «NPC-логика перенесена» — `data_manager.py:5`): `load_npc_individuals()` (`:27-50`) читает `config/npc/individuals` → список `{id, name, filename}`; `save_npc_visual_casting` (`:68-83`) и `save_npc_calibration` (`:101-118`) пишут в те же JSON **напрямую** — это единственный канал правки личности из редактора.
- **DataManager** (`data_manager.py:756`) управляет только editor-JSON локаций: `load_all` (`:830-885`, `setdefault("npcs", []) :865`), миграция координат (`:929-994`), CRUD NPC (`add/remove/move_npc :1715-1749`), сохранение с write-gate валидатора (`:1048-1069`). Blueprint/Instance-свёртка (`_fold_for_save :1234-1278`) применяется **только к objects**.
- **Данные кампаний**: `campaign.json` — только 4 поля meta (имя/описание/даты, `campaigns/Open_road/campaign.json:1-6`); локации — отдельные файлы; синк в runtime — `campaign_manager.py:172-213` (копия в `saves/<кампания>/locations`, `build/staging`, форс-пересборка spatial_registry).
- **npcs в локациях**: массив записей `{ref_id, position{x,y}, room_id, sprite}` (пример `tavern.json:1596-1864`: maid_lusya, blacksmith_orm, tavern_keeper_tornin, merchant_goran, guard_borko, thief_shadow). Личности в placement нет — это уже соответствует целевой границе «карта хранит ссылку» (§3).
- **Chronicle Editor** встроен в редактор как режим F7 (`editor_core.py:189-190`, хоткей `core/event_handler.py:74`) и работает через HTTP API (`api.py:13-19`); кампания — из открытой сессии карт либо хардкод `silver_wolf` (`editor_screen.py:40-52`).
- **Character Blueprint** существует только как резерв спеки (`BLUEPRINT_FORMAT_SPEC_v1.md:61-66`) и строки таблицы §5А.5 (`ME_ROADMAP:519`). В коде — пусто.

### 2.3. Механизмы материализации биографии: что работает, что частично, что проектируется

Работает сквозным образом (подтверждено тестами и скриптами проекта):

```
[Автор] author_text (нумерованные пункты) — Ctrl+O импорт .md/.txt append-only
   → POST decompose (F1/F2/Ctrl+G): LLM capability=fact_extraction, temp=0, GBNF
     (backend/prompts/chronicle_decompose_system.txt; config/chronicle_decompose.gbnf;
      BiographyDecomposer — biography_decomposer.py:163-228)
   → LLM_DRAFT entries в черновик (routes_chronicle.py:235-324; нормализатор
     decomposition_normalizer.py:103-285 — fail-loud, вопросы автору)
   → резолюция вопросов C+1..4 (SELECT_EXISTING_NPC / CREATE_NEW_NPC / UNKNOWN_PERSON /
     LEAVE_WHITE_SPOT — routes_chronicle.py:466-612; WhiteSpot+перелинковка — S369)
   → confirm-author-entries: LLM_DRAFT → AUTHOR_CONFIRMED (confidence снят)
   → canonize F9: CCH-7 Semantic Gate (422 K_CONTRADICTION, registry_builder.py) +
     store.validate_document («Save = Contract», chronicle_store.py:348-394)
   → config/npc/chronicles/<npc>.json (канон)
   → сеялка build_full_seed (chronicle_seeder.py:366-393, только AUTHOR_*)
   → npc_loader new-game gate (npc_loader.py:962-996): EventMemory(day<0,
     tags=("chronicle:<entry_id>",)), relationship_cache, AffectiveImprint, psyche.beliefs
   → NPCState (L2 narrative_cache)
```

Частично реализовано:

- **BELIEF_SEED** → только закрытый реестр `BeliefType` (DANGER/PLAYER_HOSTILE, `beliefs.py:45-53`); промпт декомпозитора `belief_type` не запрашивает — belief'ы практически не сеются (зафиксировано в build-11R §4.4 как P3).
- **RELATIONSHIP** на неразрешённую сущность молча не сеется (`chronicle_seeder.py:283-285`).
- **TRAIT_SEED / DESIRE_SEED / PORTRET** — «ждут Character Calibration / Desire-контура» (`chronicle_seeder.py:366-386`).
- **NpcCausalBelief / cause_candidates** (слой 2 канона, S366) — хранятся, runtime их не потребляет (`routes_chronicle.py:790-794`).
- **Возраст**: `age_math` + `game_start_age` работают только при наличии якорей; у 5 из 6 NPC `game_start_age` отсутствует → ось деградирует к `SENTINEL_DAY` (`chronicle_seeder.py:124-141`).

Проектируется/отсутствует: CCH-02 целиком (PSYCH_EXTRACTION, ECR, PSC — каталога `config/npc/autobiographies/` нет); CCH-03 (механизмы); рантайм-половина canon-sync; связка L1Chronicle (runtime-дрифт черт, `npc/l1_chronicle.py:19-25`) ↔ хроника-биография.

### 2.4. Идентичность и передача между локациями, сохранение/загрузка

- **Стабильный ID**: `npc_id = individuals.id` (рукописная строка `merchant_goran` и т.п.). Инвариант «Entity Birth Contract» — `npc["npc_id"] = npc["id"]` (`npc_loader.py:351-352, 407-409`); `list_individual_ids` намеренно берёт id из JSON, а не stem файла («имя файла не есть идентичность», `npc_loader.py:730-754`). Цепочка: `individuals.id → editor npcs[].ref_id → scene_state.npc_positions[key] → npc_runtime.json id`. `entity_id` в перцепции = тот же npc_id (`player_cognition/spatial_layer.py:102`). `character_id` игрока = имя (`models/character.py:108`).
- **Перенос между локациями** (S186): желание → `MovementEngine` резолвит cross-loc intent по префиксу `target_node_id` (`spatial/movement_engine.py:305-332`) → boundary dwell → атомарный перенос в `_pending_transfers` (`tick_orchestrator.py:1225-1310`: `location_id` меняется, dict NPC переезжает ссылкой — психика/отношения не копируются) → инжект в начале тика целевой локации (`:846-874`). Защита: ATOMIC_GUARD легальных входов (`scene_state_manager.py:888-929`), вычистка чужих/«хаски» (`:590-630`), синхронизация отношений между сценами перед коммитом (`:289-292`).
- **Сохранение/загрузка**: прод — SQLite `saves/enigma_runtime.db` + JSON (`game_loop_builder.py:39-44`); сцены — per-location в `campaign_state.json`/SQLite (`json_persistence_adapter.py:51-76`); отношения v2 — в `scene_state["relationship_state"]` + миграция legacy (`relationship_state_store.py:291-377`); L1-хроника дрейфов — SQLite (ADR-L1-PERSIST); L2-память — `saves/enigma_memory.db`.
- **Разрыв**: личное состояние NPC (body_state/психика/narrative_cache) не пишется на диск в тик-пути (Вывод 3). Отношения выживают потому, что лежат в сцене; позиции — тоже. Проверять round-trip «рестарт → NPC помнит последствия» сейчас невозможно.
- **Round-trip редактор → симуляция → сохранение → редактор отсутствует**: ни один путь не импортирует `saves/` обратно в редактор; Blueprint-свёртка описана только для сохранения редактора (`BLUEPRINT §5.3`); стык «редактор/игра» — открытый гейт S-ME1 (`ТЗ_преемнику:79-80`).

### 2.5. Расписание и его связи с потребностями, ролями, деятельностями, решениями, действиями

- Источник — `individuals.routine.schedule` («"08:00-12:00": "working"», например `goran.json:82-90`); привязка деятельностей к точкам — `activity_map[activity] = {location, position, display}`. Валидация согласованности schedule×activity_map при старте — `core/schema_validator.py:33-51`.
- Потребитель движения — `LifeEngine.update_routine` (`life_engine.py:1972-2268`): смена `routine.current`, SceneChange, `MacroMovementGoal(reason="schedule:<act>")`; кросс-лок relocation (`:2154-2186`). Позиция резолвится: activity_map → SpatialService-роли узла → DEFAULT (`:2372-2528`).
- Потребности — три слоя: легаси-прокси needs (рост 0.08/тик, `life_engine.py:90-101, 1510-1544`; need-driven движение с приоритетом **0.8** против schedule **0.6**, `:1546-1740`); NeedEngine/EconomicProfile (NeedType 8 шт., NeedDrive при urgency>0.6, `economy/need_engine.py:126-150`; вызов в Фазе — `npc_tick_pipeline.py:434-448`); RE-нужды в `scene_state["relationship_state"]["needs"]` (`relationship_state_store.py:60-152`). Новый контур desires/activities (`desire_generator.py:30-107`, `activity_lifecycle_service.py`) — за флагами OFF (`desire_generator.py:42-48`), прод живёт на легаси-прокси.
- Отклонения от расписания (все bypass'ы уже реализованы): need override; приказ игрока `interrupts_routine` (`:2016-2022`); физическая угроза threat>0.7 → bypass, threat>0.3 → viability mask делает ROUTINE невалидным (`:2033-2037, 1874-1927`); паралич воли (`:1283-1303`); сон неприкосновенен для needs, но блокируется угрозой/стрессом (`:2116-2139`); живая деятельность глушит и need-, и schedule-трек (`:1330-1348`); кризис LifeProject (`:2070-2084`); Movement Lock ADR-130 (`:1305-1319`); Commitment Arbiter (`phases/simulation.py:122-135`).
- Решение→действие: `DecisionHub.compute` — utility-скоринг с 9 слоями модификаторов (`decision_hub.py:395-425, 366, 534-547`); входы — `DecisionContext` из `pressure_translator.py:52-130`, отношения SSOT (`_get_rel_value`, прямой доступ к кэшу запрещён как DOUBLE TRUTH, `decision_hub.py:1292-1295`), убеждения (`belief_modifier_resolver` → `npc_tick_pipeline.py:478-516`), эпистемика (`epistemic_context_resolver` → `:583-600`); результат → CommunicationIntent / движение / `StateDeltas` SSOT-факт решения (`npc_tick_pipeline.py:1069-1204`); применение — `StateApplicator` (единственный L2-writer, `state_applicator.py:74-96`).
- Разрывы: (1) формат расписания без календарных условий — «расписание смен» Люси существует только текстом в origin_event (`lusya.json:114`); (2) `_archetype` (англ.) не мапится на `current_role` (рус.) — `COMBAT_CAPABLE_ROLES` и эпистемические диспозиции работают от runtime-поля или hardcoded-таблиц (`decision_hub.py:90-106, 1040-1045`; `epistemic_dispositions.py:16-34`); (3) DecisionHub получает отношения по «player» в скоринге (`decision_hub.py:1294-1295`), NPC↔NPC входят опосредованно.

### 2.6. Пути загрузки и runtime-потребители редакторских данных

Два несмешивающихся потока:

1. **Сцена**: `locations/*.json` → `editor_locator.py:21-31` (ищет в `backend/data/campaigns/<id>/locations` и `frontend/map_editor/campaigns/<id>/locations`) → `scene_factory.build_initial_scene` (`:49-285`): objects из `objects[]` (`:73-84`), NPC из `npcs[]` (`:86-101`) — только `ref_id/position/room_id` → `npc_positions[ref_id] = {name (через `npc_display_name.py:17-48`), location_id, position, activity, visible, local_position, editor_room_id}`, игрок — псевдо-агент `"player"` (`:104-120`) → scene_state → сейвы. Снапшот FE — `NPCPositionDTO`, чужая локация/невидимые отфильтрованы (`world_snapshot_builder.py:267-335`).
2. **Пространство**: `spatial_registry_builder.py:81-340` → `compiled/spatial_registry.json` (chunks/adjacency/world_bounds) → `SpatialRegistry.get_or_load` (`spatial/spatial_registry.py:122-176`) → Spatial Oracle пересчитывает локацию игрока по мировым координатам (`game_loop_bridge.py:126-206`).
3. **Личность**: в редакторе не участвует — `config/npc` грузится мимо него (`load_npcs_merged`, `game_loop_builder.py:59-75`). В тик попадают NPC: `ControlSource.NPC_DECISION ∧ location_id == текущая ∧ жив` (`scripts/probe_alive_npcs.py:22-32`; `tick_orchestrator.py:388-394, 540-611`).
4. **Навигация NPC**: per-location граф из editor JSON — `graph_compiler.compile_graph` (`graph_compiler.py:44-397`); коллизии/проходимость — `_build_spatial_data` (`:585-688`).

### 2.7. Использование индивидуальных конфигов (проверено потребителями)

| Поле individuals | Статус | Потребители |
|---|---|---|
| `routine.schedule`, `activity_map` | ЖИВО | `life_engine.py:1336-1337, 1465, 1565, 2389-2407, 2355-2370` |
| `drives`, `psyche` | ЖИВО | `npc_loader.py:446-463` → NPCProfileL0 → DriveResolver L3 (`drive_resolver.py:24-83`) |
| `id/name/name_forms/gender/tier` | ЖИВО | loader `:487-490`; `player_target_extractor.py:642-652`; `consistency_service.py:58` |
| `voice_archetype_id/voice_profile` | ЖИВО (YAML перебивает строку) | `npc_loader.py:467-474` |
| `backstory/author_notes/description` | ЖИВО (LLM-промпты) | NPCProfileL0 `:496-497`; `scene_outcome_builder.py:484-485, 635`; `dialogue_executor.py:422` |
| `origin_events` | ЖИВО как legacy-фоллбэк | `npc_loader.py:515-553` (канон приоритетен, `:981-991`) |
| `core_orientation` | ЖИВО | `npc_loader.py:498`; bypass `life_engine.py:2082-2084`; `topic_extractor.py:136-147` |
| `status_profile` (wealth/faction_rank/title) | ЖИВО | `economy/profile_factory.py:40-44`; `tick_utils.py:140-141`; `dm_agent.py:465` |
| `carried_objects`, `visible_markers` | ЖИВО | `scene_init.py:53`; `recognition_layer.py:46-71`; `interpretation_layer.py:179-180` |
| `hidden_truth` | **МЁРТВОЕ** (0 полноценных потребителей; ADR-атлас подтверждает «BETRAYAL недостижим», `docs/ADR (Architecture Decision Records).md:871`; единственный частичный читатель `phases/decision.py:212` — см. §2.8 п.12) | — |
| `hp/max_hp` top-level | **МЁРТВОЕ** | N-23 FIX: `npc_loader.py:916`, `npc_state.py:814-816` — только body_state |
| `abilities` top-level, `combat_stats` (mixin) | **МЁРТВОЕ** | читается только `body_profile.abilities` (`tick_utils.py:149`, `combat_subscriber.py:347`) |
| `status_profile.power` | **МЁРТВОЕ** | 0 потребителей |
| `birth_epoch`/`age_at_game_start` | **СПЯЩЕЕ** | читатель есть (`npc_loader.py:479-484`), данных в JSON нет |
| `flags` | **МЁРТВОЕ/дубль** | `flags.is_dead` дублируется `body_state.life_status` |
| `visual_casting` | frontend-only | `visual_casting_repository.py:28-37`, `expression_resolver.py`, `workbench_screen.py:2789-2861` |
| `position/local_position` top-level (только orm.json) | рассинхрон с placement-данными | дублирует `npcs[]` placement |

### 2.8. Дубли, обходные пути, неиспользуемые поля, отсутствующие связи, повторные источники истины

1. **Отношения NPC↔NPC** — два источника: `village_relations.json` (шкала 0–1) и канонические `RELATIONSHIP`-записи (valence → ±40/30). Канон вытесняет статик: «village-статик вытеснен каноном (снимок)» (`npc_loader.py:672-699, 698`). Дубли пар tornin↔goran, goran↔borko существуют в обоих.
2. **Прошлое** — `origin_events[]` vs канонные `EVENT`: канон приоритетен («канон есть → seed вместо legacy», `npc_loader.py:981-991`). Легаси-путь держится сознательно.
3. **Биографическая фактура** — тройной ручной дубль: `backstory/author_notes/description` (individuals) vs `author_text` (хроника). Расхождение уже есть: goran.json:19 «купец средних лет» vs merchant_goran.json:5 «купец 40 лет».
4. **HP** — три источника: individuals top-level (мёртвое), архетип `body_profile.max_hp` (guard=120 — боевой источник), константа `BODY_STATE_HEALTHY.max_hp=100` (`npc_state.py:78-97`). У Борко одновременно «30»/«120»/«100».
5. **Unit-баг**: `borko.json:45` `"loyalty_true": 1.0` при шкале остальных 0–100 → `int(...)` в `npc_loader.py:451-453` → верность Борко = 1/100.
6. **Мёртвый резолвер имён**: `mvp_tavern_controller.py:251-253` glob'ит `config/npc/*.json` — в корне папки файлов нет → карта имён всегда пуста, кроме `{"player": "Игрок"}` (`:247`).
7. **Четыре источника одной локации**: `frontend/map_editor/campaigns/…/locations` (SSOT), `frontend/map_editor/location_templates/` (дубль, ME-D15), `backend/data/locations/location_templates.json` (fallback фабрики, `scene_state_manager.py:459-461`), `backend/data/campaigns/<id>/locations` (первый путь поиска `editor_locator.py:21-31`) + legacy `backend/data/campaigns/Open_road/campaign_state.json` (v0-сейв внутри data).
8. **ID-дрейф в тестовых данных**: `npc_lusya` (нет в реестре individuals) в `backend/data/campaigns/test_campaign/campaign_state.json`; легаси `npc_1→player` в `test_data/test_campaign/npc_relationships.json:2` — мигратор v1→v2 переносит ключ строкой без валидации реестра (`relationship_state_store.py:341-359`).
9. **Два реестра «типов NPC» редактора**: `NPC_PRESETS` (mage/warrior/cow/knight — их нет в `config/npc/archetypes/`) против реального реестра архетипов.
10. **Байт-в-байт дубль кампании** в `backend/tests/fixtures/campaign_open_road/`.
11. **Хардкоды**: кампания `Open_road` и target `bar` в Observatory (`editor_core.py:796-811` — долг ME-D6), кампания `silver_wolf` в автономном Chronicle (`chronicle_app.py:886-891`), а также `run_census.py:24,42-44` (no-op пути).
12. **Примечание к `hidden_truth`**: единственный формальный читатель — `phases/decision.py:212`; это не делает поле живым контрактом (секретность фактического прошлого обеспечивается `is_secret/known_by/hidden_from` EventMemory и KNOWLEDGE_LINK-изоляцией).

---

## 3. Блок B — Целевые границы хранения и ответственности

### 3.0. Несущие принципы (зафиксированы заданием §5, сверены с фактическим кодом)

1. **Определение личности NPC не хранится как каноническая конфигурация внутри `location.json`.** Фактически это уже так: `npcs[]` несёт только `ref_id/position/room_id/sprite` (`tavern.json:1596-1853`), личность — `config/npc/individuals`. Контракт закрепляется: расширение placement-данных — только через закрытый реестр типизированных локальных переопределений (как `_INSTANCE_OVERRIDE_KEYS` для objects, `data_manager.py:44-53`), а не «универсальный карман».
2. **Определение персонажа, размещение и динамическое runtime-состояние — три разных понятия.** Сегодня это три слоя: individuals (авторский), `npcs[]` (placement), `scene_state.npc_positions` + RAM-состояние (runtime). Таблица 3.1 разводит их по владельцам.
3. **Один NPC сохраняет идентичность при перемещении между локациями.** Уже реализовано на уровне dict-ссылки при S186-переносе (`tick_orchestrator.py:1225-1310`); спецификация требует, чтобы то же выдерживал диск (NPC-I-05).
4. **Не создавать параллельные хранилища биографии/памяти/убеждений/отношений.** Все целевые потоки в §6 идут через существующие: `config/npc/chronicles` (канон прошлого), EventMemory/L2 (память), BeliefState/CrystallizedBelief (убеждения), `relationship_state` SSOT (отношения). Anti-Bond правило §16.1.12 род. roadmap применяется буквально.
5. **Не дублировать Character Chronicle, Visual Casting и другие авторские контуры внутри Map Editor.** Зоны `chronicle/**` и `data/npc_data.py` в ME-roadmap уже помечены «НЕ эта карта» (`ME_ROADMAP:944`); настоящий документ не меняет это — он лишь определяет точки стыка (S-ME5 и новые ME-R-63x).
6. **Расписание не жёсткий сценарий.** Механика отклонений уже богаче целевого контракта (§2.5); новая работа не строится, существующая фиксируется тестом-инвариантом (NPC-I-08).
7. **Текстовая биография не назначает скрытое знание напрямую.** Единственный легальный путь знания — KNOWLEDGE_LINK с `learned_age` и изоляцией «кого в знающих нет — записи не получает» (`chronicle_seeder.py:206-270`); запрещён путь «фраза из биографии → совокупность секретов NPC» минуя декомпозицию и подтверждение автора (NPC-I-10).

### 3.1. Таблица целевых границ (блок B)

Колонки: зона владения / владелец (контур и кодовые зоны) / канонический источник / что зона хранит / чего зона хранить не должна / потребители / текущий статус.

| Зона | Владелец (контур, зоны) | Канонический источник | Хранит | Не хранит (запреты) | Потребители | Статус |
|---|---|---|---|---|---|---|
| **Character Authoring** (диалог автора с миром: биография, канонизация) | Трек CCH / Ветвь А; `services/chronicle/**`, `routes_chronicle.py`, UI `chronicle_editor/**` + F7-режим редактора | `author_text` в черновике → канон `config/npc/chronicles/<id>.json` | Человеческий текст, записи канона (10 kind), белые пятна, provenance, открытые вопросы, `game_start_age`, слои 2 (`npc_beliefs`, `cause_candidates`) | Runtime-состояние; поля placement; производные числа (скаляры вычисляет сеялка из структуры, не автор — §13.1 род. roadmap) | Сеялка, consistency_service, Debugger, проекции CCH-5 | ЖИВО |
| **Character Blueprint** (структура персонажа как сущности) | Этап 05 Map Editor / `map_editor/characters/**` (зона закреплена `ME_ROADMAP:940`) | Каталог: `config/npc/individuals` (индивид-слой) + `config/npc/archetypes` (base-слои) + шаблоны; Blueprint-схема — ревизия `BLUEPRINT_FORMAT_SPEC` | Типизированные слои персонажа (9 групп ME-R-401); ссылки на архетипы/миксины; `birth_epoch/age_at_game_start` | Placement-координаты; локальные спрайты; runtime-факты; дубли фактуры прошлого (уходит в Chronicle) | Редактор (мастер создания), `npc_loader` (наследование `:88-118`) | НЕТ (скелет спеки) |
| **Placement** (появление в мире) | Map Editor Этапы 01–04; `data_manager.py`, `tools/interaction.py`, `schema_validator.py` | `locations/<loc>.json → npcs[]` | `ref_id` (ссылка), `position`, `room_id`, локальный `sprite`; далее — типизированные overrides закрытого реестра | Личность/психика/биография; скрытые факты; расписание | `scene_factory.py:87-101`, рендер, валидатор | ЖИВО (4 поля) |
| **Runtime State** (текущее состояние сущности) | Backend Ветвь Б; `LifeEngine._npc_cache`, `scene_state`, SQLite runtime | RAM → `saves/…/campaign_state.json` (позиции), `npc_runtime.json` (личное), `enigma_runtime.db` | body_state, эмоции, стресс, intent, current_role, routine.current, narrative_cache (L2), wounds/conditions, локация | Авторские факты; канон; статика личности | DecisionHub, Memory, вербализация, Debugger «СЕЙЧАС» | ЧАСТЬ (персистентность разорвана — NPC-I-05) |
| **Chronicle** (канон прошлого = SSOT истории) | Трек CCH | `config/npc/chronicles/<id>.json` | Исторические события, RELATIONSHIP-семена, KNOWLEDGE_LINK, EFFECT-травмы, TRAIT/DESIRE/BELIEF-семена, white spots | Runtime-изменения (после старта игра пишет в память, не в канон); placement | Сеялка, проекции, Debugger «ИСТОЧНИКИ» | ЖИВО |
| **Memory** (память как история жизни) | Треки NL/MEM / Ветвь А; `MemoryManager` (единственный писатель, `npc_state.py:686`), SQLite `enigma_memory.db` | EventMemory (эпизодический SSOT, Закон 4.2.1) + MemoryCrystal (семантика) + CrystallizedBelief | Эпизоды с `day` (включая `day<0` из сеялки), теги происхождения `chronicle:<entry_id>`, консолидаты | WORLD TRUTH (§16.1.1: `WORLD TRUTH ≠ NPC MEMORY ≠ NPC BELIEF`); дубли канона; vector-архив (§16.1.9) | DecisionHub (модификаторы), вербализация, NL | ЧАСТЬ (MEM-пакеты открыты) |
| **Decision** (решение как причинная запись) | Ветвь А; `DecisionHub`, `pressure_translator`, `StateDeltas` | `StateDeltas` + causal ledger + L1 TraitDrift | Интенты, модификаторы (драйвы/эмоции/отношения/убеждения/эпистемика), SSOT-факт решения | Причины без provenance (§13.4 п.3 род. roadmap) | StateApplicator, L1, Debugger | ЖИВО |
| **Schedule** (обычная деятельность) | Ветвь Б (данные) + backend (исполнение) | `individuals.routine.schedule` + `activity_map`; роли узлов location.json | Интервалы времени → деятельности; привязка к узлам/локациям | Причинно-обусловленные отклонения (они порождаются runtime: угроза, потребности, директивы — §2.5); жёсткая сюжетная хореография | `LifeEngine.update_routine`, Commitment Arbiter | ЖИВО |
| **Visual Casting** (внешность) | Этап 02 Map Editor; `visual_casting_editor.py`, `sprite_registry.py`, `pixels/` | `individuals.visual_casting` (портреты/эмоции) + placement `sprite` (карта) + ресурсы каталога (после S-ME2) | Кропы, пороги, обводка, правила эмоций, направления | Семантика/личность; поведение | `visual_casting_repository`, `scene_renderer`, `map_renderer`, Workbench | ЖИВО |

### 3.2. Правила потоков между зонами (автор → хранилище → runtime)

| Поток | Легальный путь | Запрещённые пути |
|---|---|---|
| Биография в канон | author_text → decompose → подтверждение автора → canonize (гейты CCH-7 + «Save = Contract») | LLM_DRAFT в канон; автоматическая резолюция белых пятен; правка канона из Map Editor |
| Канон в стартовое состояние | сеялка при new_game (гейт «L2 пуста везде») | resume-подмешивание канона в живую кампанию; прямое вливание биографии в воспоминания/знания |
| Знание | KNOWLEDGE_LINK (два времени, изоляция знающих) + EpistemicRecord | «фраза биографии → секрет»; телепатия seed (`unknown ⇒ ноль записей`, запрет 5 §13.4) |
| Личность в размещение | `ref_id` — строковая ссылка на каталог | копия личности в location.json; переопределение psyche/biography на уровне локации |
| Размещение в симуляцию | editor JSON → scene_factory → scene_state | runtime-записи обратно в editor JSON (round-trip в обратную сторону — только отдельным вердиктом, NPC-I-05/§9) |
| Внешность | visual_casting (индивид) / sprite (placement) | рендер-данные как источник личности |
| Время | `historical_age` ↔ `birth_epoch` (age_math) | смешение исторического времени и времени знания (запрет 4 §13.4) |

---

## 4. Блок C — Матрица текущих контрактов и пробелов

Формат строки: узел → действующий контракт (код+документ) → пробел → целевое состояние → куда ложится (требование §6).

| Узел | Действующий контракт (факт) | Пробел | Целевое состояние | Требование |
|---|---|---|---|---|
| **Идентичность/ID** | `npc_id = individuals.id`; инвариант рождения `npc_loader.py:351-352, 407-409`; цепочка ref_id→scene→runtime | Нет реестра-каталога NPC: ref_id вне individuals даёт «позицию без сущности» (фантомы вычищаются `scene_state_manager.py:590-630`); ID-дрейф в тестовых данных (`npc_lusya`, `npc_1`) | Единый каталог (individuals) как реестр идентичности; валидация ref_id на месте размещения; запрет переименования без миграции | NPC-I-03 |
| **Биография** | Канон хроник; append-only импорт (`chronicle_app.py:384-444`); «Save = Contract» | Нет UI-пути «создать биографию для нового NPC» (ростер Chronicle = только существующие NPC, `api.py:28-37`; CREATE_NEW_NPC — заглушка `routes_chronicle.py:570-579`); ручной дубль фактуры в individuals (`backstory/description`) | Биография нового NPC создаётся тем же CCH-конвейером (черновик по npc_ref до материализации); дубль-поля individuals получают вердикт (§9.3) | NPC-I-01/02 |
| **Возраст/хронология** | `age_math` + `historical_age/learned_age` (два времени); `game_start_age` | `birth_epoch/age_at_game_start` пусты у всех 6; `game_start_age` есть только у maid_lusya → у 5 NPC возрастная ось деградирует (`chronicle_seeder.py:124-141`); `shield` Сеялка требует `game_start_age` fail-loud (ship-блокер Borko из build-11R §4) | Возрастная ось обязательна для каждого индивида; проверка в readiness | NPC-I-14 |
| **Характер** | `psyche/drives` → L0/L3 (`drive_resolver.py:24-83`); калибровочная панель редактора (`dialogs.py:135-297`) пишет в individuals | Правка из редактора глобальна (нет per-campaign инстансов); TRAIT_SEED не сеется | Вердикт о per-campaign (§9.2); черты — контур Calibration (вне этого документа) | NPC-I-13 |
| **Роли/архетипы** | Наследование base→archetype→mixin→individual (`npc_loader.py:88-118, 318-335`); роли узлов в редакторе (`editor_core.py:1424-1431`) | Мост `_archetype`→`current_role` отсутствует; диспозиции захардкожены (`epistemic_dispositions.py:16-34`); `NPC_PRESETS` ≠ архетипы | Мост archetype→role при загрузке; один реестр типов | NPC-I-12 |
| **Расписание** | `routine.schedule` + activity_map + богатые отклонения (§2.5) | Нет календарных условий; контракт «расписание ≠ сценарий» не зафиксирован тестом | Инвариант-тест: schedule не исполняется при угрозе/потребности/директиве | NPC-I-08 |
| **Отношения** | Канон RELATIONSHIP вытесняет village-статик (`npc_loader.py:672-699`); WriteGate; синхронизация между сценами (`scene_state_manager.py:289-292`) | RELATIONSHIP на неразрешённую сущность молча не сеется (`chronicle_seeder.py:283-285`); village_relations как второй источник | Валидатор канона ловит неразрешённые отношения до canonize; вердикт о судьбе village_relations (§9.3) | NPC-I-09 |
| **Память/знания** | KNOWLEDGE_LINK-изоляция (`chronicle_seeder.py:206-270`); теги `chronicle:<entry_id>`; MemoryManager — единственный писатель | Эпистемический store in-memory (`npc/epistemic_store.py:14-18`) не переживает сессию; runtime-половина canon-sync отсутствует | Знание с провенансом переживает рестарт (после NPC-I-05); canon-sync тест | NPC-I-10 |
| **Убеждения** | Закрытый реестр BeliefType (DANGER/PLAYER_HOSTILE); NpcCausalBelief в каноне | BELIEF_SEED практически не сеется; causal beliefs без runtime-потребителя (`routes_chronicle.py:790-794`) | Вердикт: расширять реестр или ждать BC-2 (§9.6) | NPC-I-09 |
| **Желания/потребности/действия** | Три слоя потребностей (§2.5); каталог деятельностей = 2 записи (`activity_catalog.py:80-87`) | DESIRES/ACTIVITY_LIFECYCLE за флагами OFF; DESIRE_SEED не сеется | Не трогать в этой интеграции; зависимость от COV-0/MOT-вердиктов | — (вне скоупа, отмечено) |
| **Внешность** | Visual Casting полный (`visual_casting_editor.py`); потребление в игре | `goran.json` без visual_casting; рендер карты только «S»; backend визуал не читает | Readiness проверяет наличие visual_casting или sprite-фоллбэка | NPC-I-11 |
| **Placement** | `npcs[{ref_id, position, room_id, sprite}]`; валидатор (`schema_validator.py:242-280`); Blueprint/Instance только для objects (`data_manager.py:1234-1278`) | NPC не участвуют в свёртке/развёртке; нет типизированных локальных переопределений; room_id не пересчитывается при drag | Механика ME-1.3 распространяется на npcs[]; закрытый реестр overrides | NPC-I-04 |
| **Сохранение/загрузка** | Позиции/отношения переживают; SQLite+JSON прод-путь | Личное состояние NPC не персистится (Вывод 3); round-trip редактор↔сейв отсутствует | Writer в тик-пути; round-trip-тест рестарта | NPC-I-05 |
| **Перенос между локациями** | S186 атомарный перенос (`tick_orchestrator.py:1225-1310`); защита фантомов | Перенос не тестируется как инвариант идентичности + незнания | Инвариант-тест: id/психика/отношения сохраняются; знания не появляются | NPC-I-06 |
| **Диагностика готовности** | Только схемная валидация placement | Нет readiness-отчёта «NPC готов к жизни» (канон/возраст/расписание/внешность/размещение) | Readiness-отчёт (read-only) + гейт перед запуском симуляции | NPC-I-11 |
| **Создание из компонентов** | Наследование backend-конфигов; carried_objects валидируются онтологией (`npc_loader.py:415-434`) | Нет UI-сборки; каждый новый «канонический» NPC сегодня — рукописный JSON + рукописная хроника | Сборка из archetype+mixins+индивид-слоя без Python-обработчика на персонажа; приёмка ME-E2E-4 | NPC-I-12 |

---

## 5. UX-архитектура: минимальный авторский путь в существующем Workbench (приоритетная детализация)

### 5.0. Принцип: не девять окон, а три существующие поверхности + один новый мастер

Задание §6 описывает целевой процесс из девяти шагов и прямо запрещает читать его как требование девяти отдельных окон. Инвентарь (§5.1) показывает, что у проекта уже есть три зрелые полноэкранные поверхности и один несформированный элемент:

1. **Карта + панель свойств** (MODE_WORLD/MODE_LOCAL) — размещение, геометрия, свойства выделенного; сюда же встроены CalibrationPanel (психика) и Visual Casting (портреты/спрайты).
2. **Chronicle (F7)** — авторская биография → декомпозиция → канонизация, уже полный цикл.
3. **Workbench (F12)** — окна по манифестам, включая журнал/наблюдение; Character Debugger (F11) существует как DEBUG_MANIFEST.
4. **Отсутствует единственный элемент** — мастер создания/выбора NPC, который собирает существующие поверхности в один путь.

Следовательно, целевой UX = «проводка» между готовыми контурами + один новый экран-мастер (зона Этапа 05, `map_editor/characters/**`) + один диагностический отчёт (readiness). Всё остальное — уже написанный код.

### 5.1. Инвентарь существующего UX, переиспользуемого по шагам задания §6

| Существующий интерфейс | Где | Что даёт целевому пути | Ограничение |
|---|---|---|---|
| Дропдауны инструментов, тулбар 10 кнопок | `editor_core.py:230-350, 429-453` | Шаг 6 (размещение): TOOL_NPC уже размещает выбранного из каталога | Выбор только из существующих индивидов |
| Панель свойств NPC | `property_builder.py:236-277` | Шаг 6: имя/ID/X/Y/комната, кнопки «Спрайт», «Портреты», «Калибровать психику», превью портрета | Нет блока «готовность» и локальных переопределений |
| CalibrationPanel (психика/драйвы) | `ui/dialogs.py:135-297`; сохранение `npc_data.py:101-118` | Шаг 4 (характер): слайдеры willpower/breakpoint/loyalty_true/control/significance/fear/desire | Пишет глобально в individuals (NPC-I-13) |
| VisualCastingEditor (2 режима) | `visual_casting_editor.py`; сохранение `npc_data.py:68-83` и `editor_core.py:1664-1699` | Шаг 5 (внешность): полный режим — 6 эмоций с приоритетами/evidence; simple — 8 направлений с авто-зеркалом; порог фона/обводка; live-превью | — |
| ChronicleEditorCore (F7) | `chronicle_app.py` (3 панели; клавиши `:135-208`) | Шаги 2–3 (биография и проверка): F1/F2/Ctrl+G декомпозиция, F9/Shift+F9 канонизация, Ctrl+O импорт истории, C+1..4 резолюция, Ctrl+D/Ctrl+U/Ctrl+S экспорты | Ростер = существующие NPC; CREATE_NEW_NPC заглушён; кампания-хардкод в автономном режиме |
| Валидатор локаций (write-gate) | `schema_validator.py:242-280` + блокировка сохранения `data_manager.py:1058-1064` | Прецедент «валидатор = гейт сохранения» для будущего readiness | Проверяет только схему placement |
| Workbench + WindowManifest | `manifests.py:41-72`, `registry.py:12-79`, окна `windows/*.py` | Шаг 9 (происхождение): окно Debugger (layer 4) по образцу; инвентарь окон уже манифест-дривен | DEBUG_MANIFEST не зарегистрирован |
| Character Debugger (CCH-4) | `GET /chronicle/{campaign}/{npc}/debug`; `debug_window.py:15-19` | Шаг 9: «СЕЙЧАС» (runtime) + «ИСТОЧНИКИ» (канон: entries/white_spots/beliefs counts) | Регистрация окна не завершена; UI-вёрстка не протестирована живым запуском (ограничения CCH-4 в §0.2 род. roadmap) |
| Observatory (Симуляция) | `editor_core.py:738-837` | Шаг 8 (живая проверка): POST `/api/spatial/observatory`, hash-based diff | Хардкоды `campaign_id: "Open_road"`, `target_id: "bar"` — долг ME-D6 |
| Роли узлов (bar/bed/workbench/market/guard_post/…) | `editor_core.py:1404-1452` | Шаг 4 (деятельности): расписание привязывается к осмысленным узлам (`activity_map` → `SpatialService.resolve_node`) | ME-R-603: самих распорядков в редакторе нет — они в individuals |
| Каталог индивидов | `config/npc/individuals` через `npc_data.py:27-50` | Шаг 1 (выбор существующего): ростер для дропдауна | Нет «создать нового» |

### 5.2. Целевой путь: девять шагов задания → конкретные поверхности

| Шаг задания | Поверхность | Что происходит технически | Что существует / что достраивается |
|---|---|---|---|
| **1. Создать нового или выбрать существующего** | Мастер NPC (новый, `map_editor/characters/**`) + существующий дропдаун TOOL_NPC | Выбор из каталога; «Новый NPC» → маска: имя/пол/tier/архетип/миксины/кампания → создаётся **каркас** (`individuals`-слой с наследованием) + пустой черновик хроники в `saves/<campaign>/chronicle_drafts/<new_id>.json` | Выбор — готово (`npc_data.py:27-50`). Каркас и CREATE_NEW_NPC — достроить (NPC-I-01/12); вопрос владельцу §9.4 |
| **2. Ввести биографию свободным текстом / досье** | ChronicleEditorCore (F7), уже вызывается для конкретного NPC | Ctrl+O импорт `.md/.txt` (append-only, сборник «## ИМЯ» раскладывается по NPC — `chronicle_app.py:301-347`) или прямой ввод; структурированное досье = записи ЛЕНТЫ | Готово целиком. Достройка: ростер Chronicle должен видеть «каркасного» NPC (один API) |
| **3. Проверить противоречия, пробелы, хронологию** | Тот же Chronicle: вердикты ✓/~/×, вопросы, CCH-7 гейт | Decompose → вопросы → (опционально) consistency; белые пятна остаются белыми | Готово. UX-1…UX-4 (§0.2 род. roadmap) — запланированные улучшения того же контура, не новая работа |
| **4. Характер, роли, обычная деятельность** | CalibrationPanel + панель свойств NPC + роли узлов | Психика/драйвы (готово); `routine.schedule`/`activity_map` — редактируемый блок в панели свойств (достройка: форма «интервал → деятельность → узел» с валидацией `core/schema_validator.py:33-51`); привязка к узлам-ролям уже в коде (`editor_core.py:1424-1431`) | Частично. Достройка: редактор расписания как часть Этапа 05/ME-R-603 |
| **5. Внешность через существующий Visual Casting** | VisualCastingEditor + pick_sprite | Портреты/эмоции → `visual_casting` индивида; спрайт карты → локальный `sprite` placement | Готово целиком |
| **6. Разместить на карте + допустимые локальные параметры** | TOOL_NPC + панель свойств | Существующее размещение; «локальные параметры» = типизированные overrides закрытого реестра (стартовый кандидат: `sprite` — уже есть; расширение только по вердикту) | Размещение готово; overrides — NPC-I-04; room_id при drag — микс-фикс |
| **7. Диагностический отчёт готовности** | Новая кнопка в панели свойств NPC → readiness-отчёт (read-only) | Проверки: (а) ref_id в каталоге; (б) хроника канонизирована (`canonical=true`, открытых вопросов 0); (в) возрастная ось (`game_start_age` или `birth_epoch/age_at_game_start`); (г) schedule покрывает сутки и согласован с activity_map (`core/schema_validator.py:33-51`); (д) visual_casting/sprite есть; (е) placement валиден; (ж) неразрешённые RELATIONSHIP/KNOWLEDGE-подсказки — 0 | НЕТ — построить (NPC-I-11). Валидатор-прецедент уже есть |
| **8. Запуск проверки в живой симуляции** | Observatory + ME-E2E-4 | Снятие хардкодов ME-D6 (кампания/таргет из открытой сессии); наблюдение: тик, деятельность, реакции | Частично; ME-D6 — микс-фикс, сам Observatory готов |
| **9. Происхождение фактов и причины поведения** | Character Debugger (F11) + provenance-теги памяти | «ИСТОЧНИКИ» показывает канон-записи; в runtime каждая seeded-память несёт `chronicle:<entry_id>` (`chronicle_seeder.py:163-203`) | Готово в backend; достройка: регистрация окна DEBUG_MANIFEST + завершение UI-приёмки CCH-4 |

**Сценарий автора целиком:** (выбор/создание) → F7: биография+проверка+канонизация → возврат TAB'ом на карту → панель NPC: психика, расписание, внешность → размещение кликом → «отчёт готовности» → ▶ Симуляция → при вопросах F11 Debugger. Ни одного нового хранилища; один новый экран (мастер), один новый отчёт, две достройки существующих панелей.

### 5.3. Диагностический отчёт готовности (readiness) — состав

Отчёт собирается read-only из существующих данных; каждый пункт — с fix_hint (прецедент CCH-7):

| Проверка | Источник данных | Блокирует запуск? |
|---|---|---|
| ref_id присутствует в каталоге `individuals` и уникален в локации | `npc_data.py`, `schema_validator.py:242-280` | Да |
| Хроника канонизирована (canonical=true, unresolved questions = 0, LLM_DRAFT = 0) | `chronicle_store.py:348-394` | Да (иначе seed будет легаси-fallback молча) |
| Возрастная ось задана (`game_start_age` в каноне или `birth_epoch/age_at_game_start` в индивиде) | `chronicle_seeder.py:124-141` (SENTINEL_DAY), `npc_loader.py:479-484` | Да (иначе возраст деградирует к сентинелу) |
| schedule покрывает сутки; каждая деятельность из schedule есть в activity_map с валидным узлом | `core/schema_validator.py:33-51` | Да |
| Портрет/спрайт доступны (visual_casting.fallback или локальный sprite или NPC_SPRITE_MAP) | `npc_data.py:17-24`, `sprite_registry.py:215-227` | Нет (warning) |
| RELATIONSHIP/KNOWLEDGE_LINK цели разрешены (нет `subject_hint`-висяков) | `chronicle_seeder.py:283-285`, consistency findings | Нет (warning со счётчиком «не сеется») |
| Локальное размещение валидно (room_id существует, координаты в комнате) | `schema_validator.py:242-280` | Да |
| Канон-секреты: NPC не числится в known_by секретов, на которые нет KNOWLEDGE_LINK | cross-check с `truth_state_tavern.json` (`npc_loader.py:559-625`) | Нет (warning, NPC-I-10) |

Отчёт не является новым источником истины: это проекция тех же канонических хранилищ (INV-DIAG-NOT-GAMESTATE — диагностика никогда не мутирует состояние, `architecture/diagnostics.yaml`).

### 5.4. Что UX сознательно не делает

- Не редактирует канон из карты: правки биографии — только через F7-режим (зона «НЕ эта карта», `ME_ROADMAP:944`).
- Не показывает скрытые факты в игровых поверхностях: Debugger — layer 4, presentation firewall (П6 §13.0 род. roadmap).
- Не создаёт per-campaign копии личности автоматически: вопрос о per-campaign инстансах — вердикт владельца (§9.2), а не дефолт поведения редактора.
- Не назначает знания NPC из текста биографии минуя KNOWLEDGE_LINK (NPC-I-10).

---

## 6. Матрица интеграции: требования, зависимости, владельцы, приёмка

ID-пространство: `NPC-I-xx` — уникальные идентификаторы требований интеграции в этом документе (не пересекаются с ME-R/ME-E2E/CCH/GC; финальное размещение в реестрах дорожных карт — §7). Правило приёмки задания §7: **тесты на заранее заданный сюжет запрещены**; каждый критерий проверяет архитектурный инвариант, причинную связь, сохранение идентичности или устойчивость поведения, без предписывания конкретных исходов.

| ID | Требование | Зависимости | Владелец контура | Этап | Критерий приёмки (инвариант, не сценарий) |
|---|---|---|---|---|---|
| **NPC-I-01** | Создание NPC с нуля: биография → структурированный черновик → подтверждение → материализация | NPC-I-03, NPC-I-14; CREATE_NEW_NPC-полный (routes_chronicle) | CCH (Ветвь А) + Map Editor Этап 05 | Шаги 3–5 §8 | Из человеческого текста без правки кода получается канон (только AUTHOR_*) и индивид-каркас; LLM-черновик без подтверждения автора не проникает ни в один канонический файл; белые пятна остаются белыми |
| **NPC-I-02** | Импорт/редактирование уже прожитой биографии | CCH Ctrl+O (готово) | CCH | Готово (регресс) | Импорт append-only; сборник «## ИМЯ» раскладывается по NPC; мировой слой уходит в `_world_author_layer.md` — без регрессий на 6 канонических NPC |
| **NPC-I-03** | Стабильная идентичность: единый каталог, инвариант ID | — | Map Editor Этап 01 (реестр) + backend | Шаг 3 §8 | `individuals.id == npcs[].ref_id == chronicle_id == npc_positions.key`; ref_id вне каталога = ошибка валидатора размещения; переименование без миграции запрещено; тест на фантом «ref_id без сущности» |
| **NPC-I-04** | Placement = типизированная ссылка; удаление ссылки без уничтожения личности | ME-1.3-механика (Blueprint/Instance) | Map Editor Этап 01→05 | Шаг 6 §8 | Удаление NPC с карты не трогает `individuals`/канон; свёртка/развёртка round-trip для npcs[] (механика `_fold_for_save` обобщена); переопределения — только из закрытого реестра ключей; неизвестный ключ = ошибка (прецедент AS-ME-2 «универсальный карман запрещён») |
| **NPC-I-05** | Сохранение/загрузка и round-trip личного состояния | Вердикт §9.1 | Backend (Ветвь Б) | Шаг 2 §8 | Писатель runtime-состояния вызывается в тик-пути; рестарт backend: body_state/психика/L2 не теряются; positions/отношения — без регрессий; тест-рестарт «типнул → рестарт → последствия живы» (инвариант причинности, не сюжет) |
| **NPC-I-06** | Перенос между локациями с сохранением идентичности и незнания | NPC-I-05 | Backend | Шаг 2 §8 | S186-перенос: id/психика/отношения переезжают; intent сбрасывается (без регресса); знание не появляется у сущности, не имевшей KNOWLEDGE_LINK/свидетельства; ATOMIC_GUARD без регрессий |
| **NPC-I-07** | История формирует текущее состояние (и только сеялкой) | Готово (CCH-4) | CCH | Регресс | Новая игра: seeded-память имеет `day<0` и тег `chronicle:<entry_id>`; resume-кампания не перечитывает канон (гейт сохраняется); травма даёт импринт decay=0; `unknown → X` не оставляет X записи |
| **NPC-I-08** | Расписание с причинными отклонениями | Готово (§2.5) | Backend | Регресс | Инвариант-тесты: threat>0.7/bypass; need≥0.5 приоритетнее schedule; `interrupts_routine` глушит расписание; сон не прерывается need'ом; Commitment Arbiter фильтрует schedule-интент |
| **NPC-I-09** | Цепочка опыт → память → убеждение → решение → последствие трассируема | NPC-I-05; вердикт §9.6 | Backend (Ветвь А) | После NPC-I-05 | Для seeded-события существует путь: entry_id → EventMemory (тег) → (если сеется) BeliefState → модификатор решения → StateDeltas → L1; цепочка читается Debugger'ом; отсутствие звена — легальный, но видимый разрыв (не молчание) |
| **NPC-I-10** | Нет утечки скрытых фактов в знания NPC | Готово (изоляция KNOWLEDGE_LINK) | CCH | Регресс | NPC, отсутствующий в `known_by`/KNOWLEDGE_LINK, не получает записи о секрете ни через origin-сеялку, ни через truth_state, ни через биографию; тест-щит «текст биографии не создаёт знание минуя канон» |
| **NPC-I-11** | Явная диагностика несовместимых/неполных данных | NPC-I-03, NPC-I-14 | Map Editor Этап 05 + CCH-данные | Шаг 3 §8 | Readiness-отчёт (§5.3) с fix_hint; блокирующие/предупреждающие уровни; отчёт read-only (INV-DIAG-NOT-GAMESTATE); «канон не канонизирован» и «возраст не задан» блокируют запуск через Observatory |
| **NPC-I-12** | Новый NPC из поддерживаемых компонентов — без Python-обработчика на персонажа | NPC-I-01, ME-5.2 | Map Editor Этап 05 + backend-наследование (готово) | Шаги 4–6 §8 | Собранный из archetype+mixins+индивид-слоя NPC тикается по общим конурам (Движение/потребности/решения); в коде нет ни одного `if npc_id == "new_person"`; добавление NPC = данные, не патч |
| **NPC-I-13** | Граница «глобальная личность vs per-campaign инстанс» | Вердикт §9.2 | Владелец | До Шага 4 | Вердикт зафиксирован (ADR/запись roadmap); поведение редактора (глобальная запись psyche/visual_casting) приведено в соответствие вердикту; если per-campaign — реализованы типизированные переопределения NPC-I-04 |
| **NPC-I-14** | Возраст и хронология обязательны | Вердикт §9.5 | CCH + Map Editor Этап 05 | Шаг 3 §8 | Каждый индивид имеет возрастную ось (game_start_age или birth_epoch/age_at_game_start); readiness блокирует запуск без неё; правила для 5 существующих NPC без оси — по вердикту §9.5 |

### 6.1. Соответствие двенадцати обязательным направлениям задания §7

Задание §7 требует покрыть 12 направлений — соответствие полное: создание с нуля (NPC-I-01), импорт/редактирование (NPC-I-02), стабильная идентичность (NPC-I-03), размещение/удаление ссылки (NPC-I-04), save/load и round-trip (NPC-I-05), перенос между локациями (NPC-I-06), история → состояние (NPC-I-07), расписание с реакцией на обстоятельства (NPC-I-08), причинная цепочка (NPC-I-09), отсутствие утечки скрытых фактов (NPC-I-10), диагностика (NPC-I-11), создание из компонентов без Python-обработчика (NPC-I-12). NPC-I-13/14 — производные инварианты, без которых четыре направления не проверяемы честно.

---

## 7. Блок D — Предложение по интеграции существующих дорожных карт

### 7.0. Проверка реестров на коллизии (выполнена на корпусе ветки)

- Реестр ME-R (`ME_ROADMAP` §10.5, строки 1106–1205, 1268–1292): максимум — **ME-R-629** (топ-10 универсальных свойств). Новые номера предлагаются с **ME-R-630**.
- Реестр ME-E2E (§10.6): максимум — **ME-E2E-9**. Новые сценарии — с **ME-E2E-10**.
- Реестр ME-D: ME-D1…D15 встречаются в текстах; новые долги в этом документе не присваиваются.
- В родительском roadmap гейты MAPEDIT-GC-01…05 уже существуют (§27.2); NPC-интеграция встраивается под ними, не дублируя.

Финальное присвоение номеров — за владельцем (§9.13). Ниже — предложения с точными местами вставки.

### 7.1. Что уже покрыто существующими требованиями (не дублировать)

| Тема интеграции | Уже покрыто | Где |
|---|---|---|
| Character Blueprint: 9 групп слоёв | ME-R-401, ME-5.1 | `ME_ROADMAP:1143, 781` |
| Шаблоны/наследование/генерация | ME-R-402, ME-5.2 (вопрос LLM-черновиков — в.13) | `:1144, 782` |
| Участник симуляции без предметного кода | ME-R-403, S-ME5, ME-E2E-4 | `:1145, 825, 1230-1234` |
| Биография ≠ знания; незнание — данные | ME-R-404, ME-5.3/5.4, ME-E2E-5 | `:1146, 785-786, 1236-1240` |
| Распорядки, роли узлов | ME-R-603 (роли узлов уже в коде) | `:1194, editor_core.py:1424-1431` |
| Заселение/популяция | ME-R-608 (отложено до ME-GC-2) | `:1197` |
| Миграция NPC за границу мира как событие | ME-R-622 | `:1177` |
| Граница треков с CCH/Authoring | §10.3 в.12 → S-ME5; зоны §9.2 | `:967, 944` |
| Chronicle-интеграция редактора | MAPEDIT-GC-02, §27.2 род. roadmap | `род. roadmap:4010` |
| Порядок этапов и гейты | ME-GC-1…6, S-ME1…S-ME6 | `ME_ROADMAP §7` |
| UX-долг Chronicle | UX-1…UX-4, UX-FIX-1…4 (§0.2 род. roadmap) | `род. roadmap:313-328` |

### 7.2. Предлагаемые новые требования в ME_ROADMAP (без переписывания существующих)

Вставка в §10.5 после блока ME-R-4xx (новые строки реестра, стиль реестра сохраняется):

| Предлагаемый ID | Формулировка | Этап | Критерий |
|---|---|---|---|
| **ME-R-630** | Каталог личности NPC: `config/npc/individuals` — единственный реестр идентичности; `ref_id` вне каталога — ошибка валидатора; переименование id — только через миграцию; возрастная ось обязательна (`game_start_age`/`birth_epoch/age_at_game_start`) | 01 (валидатор) → 05 | Размещение ref_id-фантома блокируется; readiness (ME-R-632) не требует ручной проверки каталога |
| **ME-R-631** | Placement NPC как типизированная ссылка: механика Blueprint/Instance (ME-1.3) распространяется на `npcs[]`; локальные переопределения — закрытый реестр ключей (старт: `sprite`); удаление ссылки не затрагивает личность | 01 контракт → 05 | Round-trip свёртки/развёртки npcs[]; неизвестный ключ override = ошибка; удаление с карты оставляет individuals/канон нетронутыми |
| **ME-R-632** | Отчёт готовности NPC (readiness): read-only проекция канона/каталога/placement с блокирующими и предупреждающими уровнями (состав — NPC-AUTH §5.3); гейт перед запуском проверки в симуляции | 05 | Запуск через Observatory блокируется при: не-канонизированной хронике, отсутствии возрастной оси, невалидном schedule×activity_map; отчёт не мутирует состояние |
| **ME-R-633** | Стык персистентности: личное runtime-состояние NPC переживает рестарт (writer в тик-пути + round-trip-тест); совместное с Ветвью Б | стык к S-ME5 (совместно с Б) | Рестарт backend сохраняет последствия (body_state/психика/L2); деградации позиций/отношений нет |

Новые сценарии §10.6 (стиль реестра сохраняется):

| Предлагаемый ID | Сценарий | Этап | PASS | FAIL |
|---|---|---|---|---|
| **ME-E2E-10** | Round-trip автора: создать NPC → биография → канонизация → размещение → запуск → изменения состояния → рестарт backend → тот же NPC в том же состоянии, id/психика/последствия intact; удалить с карты — личность и канон живы | 05 | Идентичность и последствия переживают полный цикл без правок кода | Личность «умеирает» при удалении placement; рестарт теряет состояние |
| **ME-E2E-11** | Незнание переживает перемещение: NPC без KNOWLEDGE_LINK на секрет переносится между локациями и перезапускается — записи о секрете не появляется; NPC из `known_by` сохраняет знание | 04–05 | Знание/незнание устойчивы к переносу и рестарту | Знание появляется после переноса/перезапуска |

### 7.3. Предлагаемые дополнения родительского roadmap (готовые фрагменты — вносит владелец)

Родительский roadmap не редактируется этим документом (ограничение задания). Готовые фрагменты:

1. **§27.1 (таблица компонентов)** — добавить строку: `| NPC authoring integration spec | docs/Почти Актуальные TZ/Редактор кампаний/ENIGMA_NPC_AUTHORING_INTEGRATION_v0_1.md |`.
2. **§27.2 (гейты)** — кандидат **MAPEDIT-GC-06**: «NPC-интеграция: реестр ME-R-630…633 и ME-E2E-10/11 зарегистрированы; готовность (readiness) подключена к запуску симуляции из редактора».
3. **§1.3 (реестр ТЗ)** — строка: `| Редактор кампаний/ENIGMA_NPC_AUTHORING_INTEGRATION_v0_1.md | §27; ME_ROADMAP §5А.4–5А.5, §7.5, §10.5 | При работе Этапа 05 / ME-R-630…633 / стыка S-ME5 |`.
4. **§0.2 Ступень 0 / Ступени UX-CHRONICLE-CLARITY** — связка: UX-4 («что сеется в игру») и readiness-отчёт ME-R-632 используют один и тот же диагностический слой; дублирование запрещено.
5. **§13.3 (строка UI)** — уточнение: «открыть хронику NPC по клику на размещённого NPC» (уже заявлено в род. roadmap `:2577`) реализуется передачей контекста карты в F7-режим (сейчас кампания берётся из сессии, `editor_screen.py:40-52`; NPC-контекст не передаётся).

### 7.4. Что менять в ME_ROADMAP сейчас (фактическая минимальная правка — выполнена)

По выбору владельца («Вставить») в `ENIGMA_MAP_EDITOR_ROADMAP_v1_4.md` добавлены три минимальные ссылки-цитаты (только добавление, без правки текста):

1. §5А.4 — блок-цитата после заголовка: детализация этапа и границы треков → этот документ;
2. §7.5 «Вход» — блок-цитата: спецификация стыка S-ME5 (археология, границы, последовательность, вердикты);
3. §10.5 после ME-R-404 — блок-цитата: кандидат-требования ME-R-630…633/ME-E2E-10/11 до присвоения владельцем.

---

## 8. Блок E — Пошаговая последовательность реализации

Каждый шаг: предпосылки → содержание → риски миграции → доказательство закрытия. **Старт любого шага — только по GO владельца.**

### Шаг 1 — Гигиена и реестр (read-only подготовка данных, без UI)

- **Предпосылки:** вердикты §9.3/§9.5/§9.7/§9.8 (судьба дублей и мёртвых полей, возрастная ось, unit-фикс loyalty_true, единый реестр типов).
- **Содержание:** устранение вердиктом-утверждённых дублей (origin_events → канон уже реализовано проекциями CCH-5; background-дубли façade-полей — по вердикту); реестр типов NPC один (NPC_PRESETS как спрайт-фоллбэк — помечен/вынесен); заполнение возрастной оси 5 существующим NPC; `goran.json` получает visual_casting или явный фоллбэк-вердикт; фиксация каталога individuals как реестра идентичности.
- **Риски миграции:** существующие сейвы ссылаются на те же id — изменения полей делать аддитивно; origin_events удалять только после двойной сверки с каноном (прецедент T-CCH-01 round-trip).
- **Доказательство закрытия:** `scripts/check_canon_sync.py` + readiness-проверки §5.3 зелёные на 6 канонических NPC; IPT без регрессий; отчёт в MUTATIONS.

### Шаг 2 — Персистентность runtime-состояния NPC (backend)

- **Предпосылки:** вердикт §9.1 (формат/место хранения личного состояния); зона Ветви Б.
- **Содержание:** подключение существующего писателя (`json_persistence_adapter.py:132-149` / `sqlite_persistence_adapter.py:169-189`) в Фазу 10/`atomic_commit_all` (сейчас NPC-состояния не передаются — Вывод 3); порядок загрузки не меняется (`load_npcs_merged` уже мержит); вычитка Double-Truth с `scene_state.npc_positions` (позиции остаются в сцене).
- **Риски миграции:** старые сейвы без runtime-слоя — должны грузиться как сейчас (мерж опционален по наличию файла); риск потери детерминизма replay — writer детерминирован по тику (прецедент запретов uuid4 в kernel-событиях, `tick_orchestrator.py:1662-1664`).
- **Доказательство закрытия:** тест-рестарт (NPC-I-05/06); тест-щит детерминизма; прогон дрифт-лаборатории — «NPC data persisted»; IPT зелёный.

### Шаг 3 — Каталог, валидация идентичности, readiness (редактор)

- **Предпосылки:** Шаг 1; ME-1.4-валидатор уже в коде (прецедент write-gate).
- **Содержание:** ME-R-630: валидатор ref_id↔каталог при размещении и сохранении; readiness-отчёт §5.3 (read-only, кнопка в панели свойств); блокирующие проверки для запуска через Observatory (после снятия хардкодов ME-D6).
- **Риски:** ложные блокировки на существующих кампаниях — режим «предупреждение» до первого цикла приёмки; расхождение шаблонов vs кампаний (ME-D15) не трогается этим шагом.
- **Доказательство закрытия:** отчёт для 6 канонических NPC без ложных блокировок; фантомный ref_id блокируется тестом; интеграция в `_quick_save`-контур опциональна (вердикт).

### Шаг 4 — Сборка NPC из компонентов + CREATE_NEW_NPC полный (стык CCH/ME)

- **Предпосылки:** вердикты §9.2 (per-campaign), §9.4 (где живёт создание), §9.6 (BeliefType), §9.9 (мост archetype→role); ME-5.2-механика.
- **Содержание:** мастер «Новый NPC» (каркас individuals: наследование archetype+mixins, возрастная ось, name_forms); полный CREATE_NEW_NPC в routes_chronicle (сейчас заглушка `:570-579`) — создание npc_ref+каркаса по вердикту §9.4; мост `_archetype`→`current_role` при загрузке (одна строка в `npc_loader` — по вердикту §9.9); редактор routine/activity_map в панели свойств.
- **Риски:** CREATE_NEW_NPC пересекает зоны ветвей — только через гейт стыковки (прецедент §R.5); название нового id — контракт реестра (slug-правило), чтобы не породить второй дрейф.
- **Доказательство закрытия:** NPC-I-01/12 приёмка; собранный из компонентов NPC тикается в F5-лаборатории (прецедент `lab_r001`); регресс 6 канонических NPC.

### Шаг 5 — Мастер-проводка UX-пути (сборка поверх готового)

- **Предпосылки:** Шаги 3–4; UX-1…UX-4 (род. roadmap) — параллельно.
- **Содержание:** проводка «мастер → F7 → панель → размещение → readiness → Observatory → F11»; передача NPC-контекста в F7-режим («открыть хронику по клику» — уже заявлено род. roadmap §13.3 `:2577`); регистрация DEBUG_MANIFEST в Workbench (CCH-4 хвост); снятие хардкодов ME-D6 (кампания/таргет из сессии).
- **Риски:** UI-вёрстка не покрывается юнит-тестами — приёмка живым запуском (ограничение CCH-4); presentation firewall (запрет 7 §13.4).
- **Доказательство закрытия:** сквозной прогон E2E-10 (черновик) вручную владельцем; grep-стражи изоляции зелёные.

### Шаг 6 — Типизированные локальные переопределения placement NPC

- **Предпосылки:** вердикт §9.2 (per-campaign); ME-1.3-механика обобщена.
- **Содержание:** ME-R-631: реестр ключей overrides для npcs[] (старт: `sprite`); свёртка/развёртка round-trip; микро-фикс room_id при drag (`editor_core.py:1262-1266`).
- **Риски:** свёртка не должна «уходить с чертежа» молча (прецедент BLUEPRINT §5.3 — лог); совместимость старых location.json — отсутствие ключей = дефолт.
- **Доказательство закрытия:** round-trip-тест npcs[]; регресс существующих трёх локаций побайтово (кроме добавленных явно).

### Шаг 7 — Гейт S-ME5 и приёмка (совместно с Ветвью Б/CCH)

- **Предпосылки:** ME-GC-3/ME-GC-4 зелёные (`:949, :671`); Шаги 1–6.
- **Содержание:** публикация Character Blueprint v1 + экспорт в NPC-контур; приёмка ME-E2E-4/10/11; закрытие в.12/в.13 вердиктами владельца.
- **Доказательство закрытия:** ME-GC-5 («персонаж без кода участвует в симуляции»), ME-E2E-4/10/11 зелёные; запись в MUTATIONS; самоочистка корпуса §1.3 по протоколу.

**Порядок и параллельность:** Шаг 2 (backend) независим от Шагов 3–6 (frontend) и может идти по Anti-Race Protocol параллельно; Шаг 4 требует вердиктов; Шаг 7 — всё предыдущее. Этапы 02–04 Map Editor (уровни/компоненты/проверка) идут по своей карте — NPC-интеграция встаёт после ME-GC-3 (это уже контракт `:949`), но Шаги 1–3 не ждут Этапов 02–04.

---

## 9. Блок F — Архитектурные решения, требующие вердикта владельца

По выбору владельца блок оформлен как перечень открытых вопросов без вариантов. Каждый вопрос содержит контекст и риск задержки, чтобы вердикт можно было вынести на фактах. **Ни один вопрос не закрывается исполнителем самостоятельно.**

1. **Персистентность личного состояния NPC.** Сейчас writer `npc_runtime.json`/`runtime:{cid}` существует, но не вызывается в тик-пути (`commit_phase.py:94-146`, подтверждение `drift_laboratory.py:763`). Нужен вердикт: считать ли «последствия переживают рестарт» контрактом S-ME5 (NPC-I-05) и когда его закрывать — до Этапа 05 или вместе с ним. Без него ME-E2E-10 непроверяем.
2. **Глобальная личность vs per-campaign инстансы.** Редактор пишет `psyche/drives/visual_casting` прямо в `config/npc/individuals` (`npc_data.py:68-118`) — правка меняет NPC во всех кампаниях. Требуется вердикт о модели (глобальный канон как сейчас / типизированные per-campaign переопределения через NPC-I-04 / гибрид) до Шага 4, иначе мастер создания зафиксирует случайное поведение.
3. **Судьба легаси-дублей.** Пять узлов дублирования подтверждены археологией (§2.8): origin_events vs канон; backstory/author_notes/description vs author_text; village_relations vs канон-RELATIONSHIP; truth_state vs KNOWLEDGE_LINK; location_templates в трёх местах. Нужен вердикт по каждому: что является каноном, что остаётся фоллбэком, что удаляется. Без вердикта readiness-отчёт будет сыпать ложными предупреждениями.
4. **CREATE_NEW_NPC: где рождается новый человек.** Опция в хронике сейчас заглушка «вне скоупа» (`routes_chronicle.py:570-579`), а редактор не умеет создавать. Нужно решение: кто владеет рождением npc_ref (CCH-контур при разборе биографии / мастер Map Editor / оба через общий сервис) и в какой момент появляется запись каталога.
5. **Возрастная ось для существующих NPC.** `game_start_age` задан только у maid_lusya; `birth_epoch/age_at_game_start` пусты везде; у 5 из 6 NPC возрастная ось деградирует к сентинелу (`chronicle_seeder.py:124-141`). Нужен вердикт: обязательность поля, источник значений для 5 NPC, правило для будущих.
6. **Реестр убеждений.** BELIEF_SEED почти не сеется из-за закрытого реестра BeliefType (DANGER/PLAYER_HOSTILE, `beliefs.py:45-53`), а слой 2 канона (NpcCausalBelief) не имеет runtime-потребителя (`routes_chronicle.py:790-794`). Нужен вердикт: расширять реестр / ждать BC-2 (Ступень 4) / оставить как есть с явной диагностикой «не сеется».
7. **Мёртвые поля и скрытые факты.** `hidden_truth` не имеет полноценного потребителя (§2.7), top-level `hp/max_hp`, `abilities`, `combat_stats`, `status_profile.power` — мертвы. Нужен вердикт: удалить / назначить владельцев / задокументировать как резерв. Отдельно: канал скрытого знания для runtime-секретов (сейчас продюсеров нет, §16.2.1 род. roadmap).
8. **Формат расписания.** `routine.schedule` не имеет дней недели/исключений; «расписание смен» Люси — только текст (`lusya.json:114`). Нужен вердикт: достаточно ли текущего формата для ME-R-603/608 или контракт v2 закладывается в Этап 01 (риск второй миграции формата — по уроку §5А.5).
9. **Мост archetype→role.** `COMBAT_CAPABLE_ROLES` и эпистемические диспозиции опираются на `current_role`/hardcode, а `_archetype` не мапится на роль при загрузке (`decision_hub.py:90-106, 1040-1045`; `epistemic_dispositions.py:16-34`). Нужен вердикт: мост при загрузке / перенос диспозиций в конфиг / статус-кво.
10. **Владелец readiness-отчёта.** Диагностический слой на стыке CCH-данных и placement: чей он (Этап 05 Map Editor / CCH-контур / общий диагностический контур §26 род. roadmap). Блокирует Шаг 3.
11. **Снятие хардкодов ME-D6 (Observatory `Open_road`/`bar`, Chronicle `silver_wolf`).** Когда снимать: до Шага 5 (иначе сквозной UX-путь неполон) или вместе с песочницей Этапа 04. Блокирует Шаг 8 UX-пути.
12. **Генерация полей NPC (в.13).** Дефолт в roadmap уже задан («детерминированные шаблоны с seed», `:1071`), вопрос LLM-черновиков открыт. Нужен явный вердикт до ME-5.2, чтобы NPC-I-01 и ME-5.2 не разошлись.
13. **Присвоение предложенных ID.** ME-R-630…633 и ME-E2E-10/11 проверены на коллизии (§7.0), но финальные номера и формулировки в реестрах — решение владельца; заодно вердикт о регистрации документа в §1.1/§1.3 родительского roadmap (фрагменты — §7.3).

---

## 10. Статус работы и следующий шаг

- Археология выполнена read-only на корпусе ветки `V.0.5.4.4.8_Движемся_вперед_3`; все существенные выводы подтверждены ссылками `file:line`, вызовами, схемами данных или тестами/скриптами проекта; код, тесты, флаги, ADR и канонические хранилища не менялись. Единственная правка — три добавленные ссылки-цитаты в `ENIGMA_MAP_EDITOR_ROADMAP_v1_4.md` (§5А.4, §7.5, §10.5) по выбору владельца «Вставить».
- Заявления дорожных карт сверены с кодом; расхождения отмечены в тексте (например, ME-1.4 `[ ]` в чеклисте §7.1 при фактически работающем валидаторе и журнале закрытия 2026-10-14, `ME_ROADMAP:685, 1103`).
- Спецификация не создаёт нового NPC-движка, не дублирует Character Chronicle / Visual Casting / Memory / Decision, не добавляет полей «на будущее»: каждая новая сущность в §6–§8 имеет владельца, этап и критерий приёмки.
- **Работа остановлена до GO.** Реализация начинается только после: (а) вердиктов по §9 (минимально необходимый набор для старта — вопросы 1, 2, 4, 5, 10); (б) отдельного разрешения владельца на Шаг 1 (§8).
