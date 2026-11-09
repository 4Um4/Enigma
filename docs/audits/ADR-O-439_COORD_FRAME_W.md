# ADR-O-439 — Координатный контракт W (Единый мировой фрейм файла)

> **Тип:** ONTOLOGY (ADR-O) — онтологический сдвиг системы координат
> **Статус:** ACCEPTED (P1-01 ROADMAP, 2026-11-09)
> **Сессия:** S439 (max существующих ADR = 438, Anti-Race §11 соблюдён)
> **ROADMAP:** ENIGMA_ROADMAP_восстановление_редактора_мира_runtime.md, §D.1.2, §P1-01
> **Блокирующий:** любой координатный пункт Фазы 1 (P1-02/P1-03/P1-04) требует этого ADR
> **Единый атлас:** docs/ADR (Architecture Decision Records).md → DOM-04: SPATIAL & LOCOMOTION

---

## Контекст

Система координат ENIGMA расщеплена: editor JSON, frontend-runtime и backend-runtime потребляют координаты в разных фреймах без согласованного контракта. Это корень проблемы P1 (стартовая сцена: игрок «у городских ворот» вместо интерьера таверны) — C-P1 ROADMAP.

### Сквозная проверка (D.1.1 ROADMAP)

Для каждого поля прослежены: кто создаёт → кто читает → кто преобразует → сколько раз → фрейм на этапе → возврат в JSON/сейв.

Файлы проверки: tavern.json, city_gate.json, market_square.json, стартовые шаблоны, compiled/spatial_registry.json, runtime campaign_state.json, пути новой игры (routes.py:1431-1460 → campaign_lifecycle → scene_factory), загрузки сейва (_enrich_local_positions), движения NPC (phases/motion.py, tick_orchestrator), игрока (game_screen, velocity/waypoint), восприятия (spatial_service.get_zone_id, world_topology_provider), отрисовки и пикинга (geometry_builder, scene_renderer, game_screen:2661-2697).

### Ключевой инвариант (B-07 ROADMAP)

`frame(сущностей в scene_state) == frame(геометрии файла)`

Сегодняшний код игрока (local_to_world +origin) корректен ТОЛЬКО если spawn в JSON локальный, а геометрия мировая — т.е. требует расщеплённого файла, который редактор создать не может (B-03).

### Evidence (B-01…B-08 ROADMAP)

| ID | Факт | Статус |
|---|---|---|
| B-01 | Флаг global_coords не читается рантаймом вообще; только редактор + docstring'и | VERIFIED |
| B-02 | ContextResolver.local_to_world/world_to_local — безусловные сдвиги ±origin | VERIFIED |
| B-03 | Миграция редактора _migrate_to_global_coords сдвигает ВСЁ → ставит global_coords=true. Контракт редактора — единый мировой фрейм | VERIFIED |
| B-04 | create_location создаёт player_spawn = origin+(1,1) — мировой; согласовано с B-03 | VERIFIED |
| B-05 | Геометрия коллизий потребляется рендером «как записано» (без сдвига) | VERIFIED |
| B-06 | Backend фрейм-агностичен: узлы/комнаты/waypoint'ы/local_position — в одном фрейме файла | VERIFIED |
| B-07 | Ключевой инвариант: frame(сущностей) == frame(геометрии файла) | VERIFIED |
| B-08 | Данные трёх локаций гетерогенны. P0-02 T0-c: 77 полей tavern.json, 0 мировых (0%), 100% локальных | VERIFIED |

---

## Decision (контракт W)

Единый согласованный контракт, совместимый с:
- редактором (миграция B-03, create_location B-04, валидатор B-20/требование global_coords=true)
- требованием ТЗ «единая система мировых координат» для World Editor
- фрейм-агностичным backend'ом (B-06)

### Правила W1–W7

| Правило | Содержание |
|---|---|
| **W1** | Все координатные поля файла (walls, objects, nodes, rooms, passages, labels, npcs, player_spawn) хранятся в ОДНОМ фрейме — мировом при global_coords=true; локальном — только как временный легаси до миграции |
| **W2** | Backend фрейм-агностичен: frame(scene_state.entities) == frame(файла). Изменений в graph_compiler/SpatialService/движении НЕ требуется |
| **W3** | Фронтенд-конверсии (local_to_world/world_to_local) — фрейм-осознанные: при global_coords=true → identity; при false → ±origin (легаси). Флаг из editor JSON или compiled-артефакта (предпочтительно — один источник) |
| **W4** | Оракул и камера продолжают работать в мировых координатах (не меняются) |
| **W5** | Сейв: local_position в фрейме файла; при первом запуске после W — одноразовая миграция существующих сейвов (сдвиг на origin локации, версия сейва, бэкап). Node-id ссылки не затрагиваются |
| **W6** | Рендер NPC «сырой» (0 преобразований) — при W корректно автоматически; отдельная конверсия из RCA-1 F2 НЕ вводится |
| **W7** | Валидатор (P3-02) кодифицирует W1: фрейм-нарушение — error/warning по уровням D.1.4 |

---

## Отвергнутые альтернативы

### Вариант H — «гибридный фрейм» (геометрия мировая, сущности локальные в одном файле)

Соответствует сегодняшнему поведению кода, но:
1. Противоречит миграции/валидатору/create_location редактора
2. Противоречит требованию ТЗ «единая система мировых координат»
3. Делает холст редактора расщеплённым (стены и NPC на одной канве в разных фреймах)
4. Требует вечной пары правил «какое поле в каком фрейме» в каждом новом потребителе

**Вердикт:** REJECTED по совокупности.

### «Учить build_geometry читать фактический фрейм» (RCA-1 F1-альтернатива)

Второй источник истины фрейма в рендере. REJECTED (согласуется с RCA-1; второй источник запрещён Уставом).

### RCA-1 F1+F2 (отвергнутая формулировка)

- F1 (RCA-1): сдвинуть в мировой фрейм всё, включая npcs и player_spawn — **сохраняется** как направление для данных (P1-03)
- F2 (RCA-1): дополнительно конвертировать NPC local_position через local_to_world — **REJECTED**: после F1 координаты NPC уже мировые → F2 прибавляет origin ВТОРОЙ раз → двойной сдвиг. Доказательство: после F1 player_spawn=(33.24,16.93) мировой; scene_factory копирует как есть; фронт local_to_world(+25.03,+5.02) → (58.27,21.95) — вне footprint таверны.

**Замена F2 → F2′ (P1-02 ROADMAP):** фрейм-осознанные конверсии (W3) — при едином мировом фрейме конверсия сущностей = identity.

---

## Уровни диагностики валидатора (D.1.4 — для P3-02)

| Уровень | Что относится (примеры) |
|---|---|
| **ERROR** | координатное поле вне обоих фреймов; spawn вне footprint при непустых rooms; ссылка на несуществующий узел/стену |
| **WARNING** | поле в локальном фрейме при global_coords=true (для tavern сегодня — вся геометрия); пересечение footprint'ов (площадное) |
| **INFO** | легальная геометрия за пределами footprint: выходы/переходы, boundary-элементы, выносные объекты — НЕ блокируется |

---

## Проверенные особо (D.1.3 ROADMAP)

| Сценарий | Следствие W |
|---|---|
| Новая игра | scene_factory копирует мировой spawn как есть → identity-конверсия → мировая точка ∈ footprint → оракул подтверждает tavern |
| Загрузка сейва | W5-миграция; _enrich_local_positions остаётся корректным (источники в фрейме файла) |
| CONTINUE | metadata player_world_x/y — мировые; reconcile с identity-конверсией вырождается в безопасный passthrough |
| Движение NPC | backend пишет в фрейме файла (мировом) → perceived/waypoint'ы мировые → рендер «сырым» корректен |
| Восприятие | get_zone_id(local_position) с мировыми координатами и мировыми rooms — корректен |
| Пикинг | клик-камера от _player_xy — после W3 игрок мировая → клик-камера совпадает с рендер-камерой |
| city_gate/market_square | нормализуются ТА ЖЕ процедурой, что tavern, но отдельными скриптами ПОСЛЕ валидатора P3-02 |

---

## Changed Domains

- **frontend/world_context.py** — ContextResolver.local_to_world/world_to_local (P1-02)
- **frontend/map_editor/campaigns/Open_road/locations/tavern.json** — нормализация (P1-03)
- **frontend/map_editor/location_templates/tavern.json** — origin=(0,0), самосогласован (НЕ мигрируется)
- **backend/app/services/scene_state_manager.py** — W5-миграция сейвов (P1-04)
- **frontend/map_editor/data_manager.py** — _migrate_to_global_coords (B-03)
- **frontend/map_editor/schema_validator.py** — W1-проверки (P3-02)
- **compiled/spatial_registry.json** — пересборка после P1-03 (поле global_coords в chunks)

## Downstream Consumers

- game_screen.py — local_to_world call-sites (:711, :1218, :1236, :1725-1740, :2256, :2661-2697)
- scene_renderer.py — NPC rendering «сырым» local_position (B-12)
- geometry_builder.py — walls/objects «как записано» (B-05)
- graph_compiler.py — фрейм-агностичен (B-06)
- spatial_service.py — get_zone_id с frame(local_position) == frame(rooms)
- scene_factory.py — копирует player_spawn как есть
- editor_locator.py — _find_starting_location читает JSON напрямую
- 4 потребителя [0] в find_chunks — world_context.py:245, routes.py:1030, game_loop_bridge.py:172, game_loop.py:1318

## Runtime Impact

- RAM: 0 (нет новых данных; флаг global_coords уже в JSON)
- Latency: 0 (identity-конверсия быстрее сдвига)
- VRAM: 0

## Sandbox Tests

- **P0-02 T0-c baseline** (зафиксирован ДО W): 77 полей tavern.json, 0 мировых (0%), 100% локальных — нарушение W1
- **После P1-03** (нормализация): T0-c должен начать падать с сообщением «P1-03 applied» — индикатор успешного закрытия
- **После P1-02** (фрейм-осознанные конверсии): new unit-тесты — файл-мир (identity), файл-легаси (сдвиг), отсутствие чанка (identity)

## Rollback

ADR-O-439 — документ, не код. Откат = статус → REJECTED + reverting всех пунктов P1-02/P1-03/P1-04, которые на него ссылаются. Без кода для revert.

## Связанные ADR

- ADR-O-201 (Causal Kernel Architecture) — backend фрейм-агностичность (B-06)
- ADR-O-301 (KernelRNG) — детерминизм, не координаты
- ADR-130 (Traversal ownership) — traversal «как записано» в фрейме файла

## Связанные пункты ROADMAP

- **P1-01** (этот ADR) — принять контракт W до правок координат
- **P1-02** — фрейм-осознанные конверсии (W3 в коде)
- **P1-03** — нормализация tavern.json в мировой фрейм (W1 в данных)
- **P1-04** — миграция сейвов (W5)
- **P3-02** — валидатор координатного фрейма (W7 + D.1.4)

## Источник

ENIGMA_ROADMAP_восстановление_редактора_мира_runtime.md, §D.1 (строки 196-253), §B.1 (B-01…B-08), §C-P1 (корневая причина).