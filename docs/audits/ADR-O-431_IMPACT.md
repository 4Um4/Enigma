# ADR-O-431 Impact Audit

> Детальный аудит одного ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`.
> Эпоха: ME-1.5 (S387). Основания: ME-D3 триформ-wall_id устарел после миграции данных; S129 rotation-хак снят; S143 root-wall_id контракт сохранён как единственная форма.

---

## 0. ADR Card

- **ID:** ADR-O-431
- **Тип:** ONTOLOGY (ADR-O)
- **Статус:** ACCEPTED
- **Затронутые домены:** spatial (editor JSON schema), rendering (map_editor), world loading (world_context)
- **Предшественники:** ADR-303 (Coordinate Truth), S129 (rotation=wall_id hack — DEPRECATED), S143 (root wall_id contract — PRESERVED), ME-D3 (triform reader — transitional)
- **Сессия внедрения:** S387 (коммит a52ecbd8)

---

## 1. Контекст и проблема

Контракт `wall_id` (привязка двери/окна/прохода к стене) исторически жил в **трёх формах одновременно**:

1. **Root-форма (S143):** `obj["wall_id"] = "wall_2"` — добавлено как «честный» контракт для `graph_compiler`.
2. **Properties-форма (legacy):** `obj["properties"]["wall_id"] = "wall_2"` — изначальная форма, дублировалась при S143.
3. **Rotation-хак S129:** `obj["rotation"] = "wall_2"` — строка в числовом поле, контракт со старым рендерером.

Триформ-ридер `_object_wall_id()` (data_manager.py:691-720) искал привязку по цепочке `root → properties → rotation`, чтобы не терять данные при любой форме хранения. Это работало, но:
- **Дубль данных** в `add_object` и `add_passage` (запись во все три формы сразу).
- **Скрытая связь** между числовым полем `rotation` и строковым `wall_id` (нельзя отличить реальный поворот от хака).
- **Легаси-массив `portals`** в 4 JSON-файлах параллельно с passage-объектами в `objects` — 8 переходов дублировались.

Параллельно: код редактора (`data_manager.py:864` комментарий «portals удалены») уже не использовал массив, но данные и 7 точек в коде остались.

## 2. Принятое решение

### 2.1 Единая форма wall_id (root)

`wall_id` хранится **только** в `obj["wall_id"]`. Свойства `properties.wall_id` и `rotation == wall_id` запрещены.

- `add_object(wall_id=...)`: пишет только `obj["wall_id"]`.
- `add_passage(wall_id=...)`: `rotation=0`, `obj["wall_id"] = wall_id`.
- `world_context.py:343`: `explicit_wall_id = obj.get("wall_id")` (fallback на `properties.wall_id` удалён).
- `_object_wall_id()` триформ-ридер **оставлен** как обратный compat-ридер для старых файлов (снятие — ME-1.6 после подтверждения отсутствия потребителей старых форм).

### 2.2 Удаление легаси-массива `portals`

- Из 4 JSON-файлов массив `portals` мигрирован в `objects` как `door_transition` (8 переходов).
- Из `data_manager.py` удалено 7 точек обращения к `loc["portals"]`.
- Из `map_renderer.py` (2 точки) и `property_builder.py` (1 точка) — аналогично.
- `create_location()` больше не создаёт ключ `portals` в шаблоне.
- README.md: из JSON-схемы локации убран пример с `portals`.

### 2.3 Миграционный скрипт

`backend/scripts/me15_migrate.py` — идемпотентный, один проход:
- passage-объекты: `properties.wall_id` → root, `rotation==wall_id` → 0.
- массив `portals` → миграция в `objects` (по id, без дублей) → удаление ключа.

## 3. Changed Domains

- **Spatial (editor JSON schema):** контракт `wall_id` сужен с 3 форм до 1 (root).
- **Rendering (map_editor):** поиск портала для подсветки и подсчёт — через `objects` с фильтром по `_PASSAGE_TYPES`.
- **World loading (world_context):** fallback на `properties.wall_id` удалён; игра доверяет root-форме.
- **Data migration:** 4 JSON-файла кампании Open_road + 1 шаблон.

## 4. Downstream Consumers

- **`graph_compiler`** (game backend) — читает `obj["wall_id"]` для разрезания стены проёмом. **Не затронут** (root-форма — его нативный контракт S143).
- **`world_context.SpatialDataLoader`** — читает `obj.get("wall_id")`. **Изменён** (строка 343): fallback удалён, но после миграции данных fallback больше не нужен.
- **`map_renderer`** — рендер портала по позиции. **Изменён**: ищет в `objects` с фильтром `_PASSAGE_TYPES`, а не в `portals`.
- **`property_builder`** — UI-свойства портала. **Изменён**: читает `p["name"]` и `p.get("properties", {}).get("target_file", "")` вместо `p["label"]` и `p["target"]`.
- **`_object_wall_id()`** (data_manager:691-720) — триформ-ридер. **НЕ удалён** (compat для legacy-файлов вне кампании Open_road). Снятие — ME-1.6 после аудита.

## 5. Runtime Impact

- **Latency:** без изменений — чтение `obj.get("wall_id")` быстрее триформ-ридера на 2 проверки.
- **VRAM:** без изменений.
- **Disk:** 4 JSON-файла уменьшены (удалён массив `portals` + дублирующие поля `properties.wall_id`).
- **Backward compat:** `_object_wall_id()` обеспечивает чтение старых файлов (если найдутся) — данные не теряются.

## 6. Sandbox Tests

- `frontend/map_editor/tests/test_me15_normalization.py` — 5 тестов:
  - `test_add_passage_writes_wall_id_root_only` — passage: wall_id в root, без дубликата, rotation != wall_id.
  - `test_add_object_with_wall_id_writes_root_only` — add_object: wall_id только в root.
  - `test_save_drops_portals_key` — save не пишет `portals`.
  - `test_round_trip_preserves_wall_id_root` — load→save→load: wall_id выживает в одной форме.
  - `test_migrated_campaign_locations_have_no_portals` — все локации Open_road без `portals`.
- Регрессия: `test_scale_parity.py` 12/12 PASS (геометрия не затронута).
- IPT: 54 passed / 0 failed (0 CRITICAL).

## 7. Rollback

- `git revert a52ecbd8` — возвращает триформ-ридер в активное состояние, легаси-portals в данные.
- Или точечно: восстановить `properties.wall_id` и `rotation=wall_id` в `add_object`/`add_passage`, вернуть fallback в `world_context.py:343`.
- Миграционный скрипт `me15_migrate.py` необратим для данных (перезаписывает JSON) — перед rollback восстановить JSON из git: `git checkout a52ecbd8~1 -- frontend/map_editor/campaigns/ frontend/map_editor/location_templates/`.

## 8. Риски

- **Скрытые потребители старых форм** — не найдены. После ME-1.5.1: `graph_compiler.py:611` упрощён до `obj.get("wall_id")`, `world_context.py:343` упрощён в ME-1.5. `_object_wall_id()` остаётся как compat-слой в data_manager (ME-1.6 снимет).
- **Legacy-файлы вне кампании** — после ME-1.5.1 аудит `backend/data/sessions`, `backend/saves`, `backend/test_data`: 0 wall_id, 0 rotation=wall_*, 0 properties.wall_id. Сейвы не хранят editor-геометрию — риска нет.
- **Rotation-хак S129 как детектор** — после ME-1.5.1: 0 вхождений `rotation=wall_*` в данных (было 6, мигрированы). grep `isinstance.*rotation.*str` пуст.

## 9. Открытые вопросы (ME-1.6) — РЕШЕНЫ после ME-1.5.1

- ✅ Все live-данные в root-форме: 12 wall_id мест в campaigns+templates, 0 в properties, 0 rotation=wall_* (аудит Этапа B).
- ✅ Нет runtime-потребителей старых форм: `graph_compiler:611` и `world_context:343` упрощены. Единственный consumer триформ-логики — `_object_wall_id()` в data_manager (3 точки вызова: 747, 1472, 1710).
- ✅ Save-файлы не содержат editor-геометрии: 0 wall_id в `backend/data/sessions`, `backend/saves`, `backend/test_data`. Риска потери данных при загрузке старых сейвов нет.
- **Вывод:** ME-1.6 (удаление `_object_wall_id()`) — безопасна. Замена на прямой `obj.get("wall_id")` в 3 точках вызова.

## 10. Канонические ссылки

- Коммит: `a52ecbd8`
- Сессия: S387
- ТЗ: «Map editor следуй карте» (ветвь Б)
- Предыдущий ADR по map_editor: ADR-303 (Coordinate Truth)
- Связанные инциденты: S129 (DEPRECATED), S143 (PRESERVED), S348/S349 (ME-D3 триформ-ридер)

