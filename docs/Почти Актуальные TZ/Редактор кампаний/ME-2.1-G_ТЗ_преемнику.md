# ТЗ преемнику: Map Editor / Asset Workbench — вход после ME-2.1-G Architecture Review

**Автор передачи:** сессия ME-2.1-G (Ветвь Б, Asset Workbench) · **Дата:** 2026-10-31 · **База проекта:** V.0.5.4.5.0
**Адресат:** агент, принимающий редакторную линию на реализацию Blueprint Editor. **Статус:** исполняемая передача.
**Нарушение протокола входа (§2) = потеря контекста = повторение оплаченных ошибок.**

---

## 1. Где мы (факты, не рассказы)

**Канон линии:** `docs/Почти Актуальные TZ/Редактор кампаний/ENIGMA_MAP_EDITOR_ROADMAP_v1_4.md` —
операционная карта Workbench (Build/Create/Define & Test, 6 этапов, реестры ME-D/ME-R/ME-E2E).
**Дорожная карта пропатчена этой сессией** (`fix_roadmap_v1_4.ps1` применён): добавлены строки
журнала §10.4 для ME-2.1 A-F+E, Game Preview (F11), World Map Interaction Audit; исправлены
счётчики OBJECT_PRESETS (~25 → 30), статус ME-2.1 (`[ ]` → `[~]`), в.8.

**Состояние на передачу:**
- **ME-2.1 A-F+E закрыты** (~11 коммитов, 111 тестов, ruff clean):
  | Шаг | Коммит | Тесты | Что |
  |---|---|---|---|
  | A. Populate | `f931c9a1` | 22 | 30 Blueprint JSON в `assets/catalogs/base/blueprints/` |
  | B. Derive | `ecbc35c0` | 19 | `OBJECT_PRESETS` mutable + `refresh_object_presets` |
  | C+D. CatalogIndex+Validator | `828ec573` | 39 | Query-слой + 4-уровневая валидация |
  | F. Catalog UI | `70fc1341` + 4 фикса | 20 | `CatalogPanel` F3 toggle |
  | E. Hierarchy | `3cfb374e` | 11 | `categories[]` + prefix-match + multiple membership |
- **ME-2.1-G Architecture Review завершён** (без реализации): отчёт
  `download/ME-2.1-G_Architecture_Review.docx` (67 КБ, 21 страница). Карта архитектуры,
  таблица 22 полей × 6 атрибутов, 10 рисков, контракт `BlueprintEditor`, план 10 подэтапов
  G-1…G-10, ~50 тестов. **Реализация НЕ начата — ждёт GO Master.**
- **Game Preview (F11)** реализован вне нумерации ME-x.y: `render/geometry_builder.py`
  (новый, `build_geometry()` — единый для SpatialDataLoader и scene_bridge),
  `editor_core._draw_game_preview()`, F11 toggle, стрелки — pan.
- **WORLD-MAP-INTERACTION-AUDIT** реализован вне нумерации: `render/placement_diagnostic.py`
  (новый), overlap визуализация в `map_renderer.draw_world()`, drag integrity, snapping 1.0m.
- Вердикты Мастера канонизированы в roadmap §10.5 (ME-R-623…628).

## 2. Протокол входа (по порядку, до любого кода)

1. `РЕЖИМ РАБОТЫ.md` — целиком: §3 (археология, чтение .md целиком), §3.6, §3.8 (IPT),
   §3.12 (окно тишины), §4 (формат БЫЛО/СТАЛО), §11 (Anti-Race).
2. `Правила Фикса БАГОВ.md` — Части 0–XIV (симптом ≠ причина; ROOT_CAUSE_CONFIDENCE).
3. Roadmap v1_4 (пропатченная): шапка → §0.4 → §9 (лестница, гейты, GO) → §7.2 чеклист
   Этапа 02 → §10.4 (журнал — новые строки ME-2.1 A-G) → §10.5 (ME-R).
4. `BLUEPRINT_FORMAT_SPEC_v1.md` — спека 6 слоёв (geometry/appearance/physics/function/
   semantics/metadata) + §5 (экземпляр) + §6 (версии).
5. `ME-2.1-G_Architecture_Review.docx` — **обязательно целиком**: карта архитектуры,
   таблица полей, 10 рисков (R1: AssetStore read-only; R2: default_properties gap),
   контракт `EditSession`/`SaveResult`/`BlueprintEditor`, план G-1…G-10.
6. `MUTATIONS.md` — МЕТА + строка ME-2.1-G + хвост.
7. Базлайн: `ruff check frontend/` = 0; compileall; pytest `map_editor/tests/` = 111 тестов
   GREEN (A+B+C+D+E+F); `editor_launcher.py` запускается.

**Базлайн-факты сессии-автора:** ME-2.1 111/111; ruff 0; docx отчёт 21 страница проверен
(24 таблицы, код-блоки моноширинны, плейсхолдеров нет).

## 3. Карта кодовой поверхности (что трогаешь)

| Файл | Содержание после ME-2.1-G |
|---|---|
| `frontend/map_editor/assets/asset_store.py` | `AssetStore` (read-only!), `BlueprintRecord` (frozen dataclass), `ResourceRecord`, `AssetStoreError`. **R1: НЕТ write-API** — `save_blueprint` / `add_blueprint` / `delete_blueprint` нужно добавить (подэтап G-1). Правила: filename=blueprint_id, version/compat int≥1, campaign overrides global |
| `frontend/map_editor/assets/catalog_index.py` | `CatalogIndex` — query-слой на AssetStore: search/filter/get_preview/list_categories/list_tags/list_category_tree (Step E). НЕ второй storage — rebuild на refresh() |
| `frontend/map_editor/assets/resource_validator.py` | `ResourceValidator` — 4 уровня (L1 structural / L2 resource / L3 editor compat / L4 runtime compat). `ValidationResult` не булев (errors/warnings/infos). `can_place` / `fully_supported` свойства |
| `frontend/map_editor/ui/catalog_panel.py` | `CatalogPanel` (~384 строки) — F3 toggle, 250px left, search + category buttons (3-char labels) + card list + `on_place` callback. Открывает → refresh_object_presets + refresh_entity_sprite_map |
| `frontend/map_editor/data_manager.py` | `_HARDCODED_OBJECT_PRESETS` (legacy); `OBJECT_PRESETS = dict(...)` (mutable); `refresh_object_presets(asset_store)` + `_derive_presets_from_assetstore()` + `_blueprint_to_preset()` (Step B). Валидаторная семья S349 внутри |
| `frontend/map_editor/sprite_registry.py` | `SpriteRegistry` + `ENTITY_SPRITE_MAP = _derive_entity_sprite_map()` (деривация из 3 домов + `_PRESET_SPRITE_FALLBACK`); `refresh_entity_sprite_map()` (Step B) |
| `frontend/map_editor/editor_core.py` | Ядро UI; `preview_active` (F11), `_preview_cam_offset`, `_dragging_location`, `catalog_panel` (F3), `_catalog_place(bp_id)`, `_draw_game_preview()` |
| `frontend/map_editor/core/event_handler.py` | F11 (Game Preview toggle, MODE_LOCAL), F3 (catalog toggle), каталог event routing, MOUSEBUTTONUP (save + toast), MOUSEMOTION (screen_to_world + snap) |
| `frontend/map_editor/render/geometry_builder.py` | `build_geometry(editor_data)` → (walls, obstacles) — единый для SpatialDataLoader (game) и scene_bridge (preview). `split_wall_by_openings()` |
| `frontend/map_editor/render/scene_bridge.py` | `build_perceived_scene(loc)` — теперь вызывает `build_geometry(loc)`, совпадает с игрой |
| `frontend/map_editor/render/placement_diagnostic.py` | `rectangles_2d_overlap()`, `detect_2d_overlaps()`, `snap_location_position()` (SNAP_THRESHOLD=1.0m) |
| `frontend/map_editor/render/map_renderer.py` | `draw_world()` — overlap визуализация (красный fill + border + area label) |
| `frontend/map_editor/assets/catalogs/base/blueprints/*.json` | 30 Blueprint JSON: 6 слоёв + tags + categories[] + default_properties в metadata. **R2: default_properties НЕ маппятся в function.components** |

## 4. Главная очередь: ME-2.1-G — Blueprint Editor (GO Master обязателен)

**Порядок и состав — из `ME-2.1-G_Architecture_Review.docx` (Результат 5):**

1. **G-1. AssetStore write-API** — добавить `save_blueprint_atomic` / `add_blueprint` /
   `delete_blueprint`. tmp → validate → test-load → rename. Без UI. Покрывает R1, R3, R8, R9.
   Тесты: T1 (validate failure → original intact), T2 (round-trip unknown fields), T8
   (broken JSON isolation).
2. **G-2. BlueprintEditor core (no UI)** — `EditSession`, `SaveResult`, `VersionConflict`,
   `BlueprintEditor.open/save/cancel/new_from`. Интеграция с ResourceValidator + CatalogIndex
   + refresh-цепочка. Покрывает R1, R3, R5. Тесты: T1, T3, T4, T5, T6.
3. **G-3. UI: read-only view** — CatalogPanel integration: double-click card → opens editor
   panel (read-only). Live validation display. Dirty indicator.
4. **G-4. UI: editable active layers** — geometry / appearance / physics. Number inputs,
   checkboxes, dropdowns. Save button (disabled on errors).
5. **G-5. UI: categories multiselect** — tree-view из `list_category_tree()`, checkbox
   multi-select, auto-derive legacy category. Верифицирует Step E (R8).
6. **G-6. UI: metadata + default_properties (R2)** — label/icon editable; default_properties
   как raw JSON с предупреждением «семантика не формализована». Cross-check с
   function.components — warning при дублировании. **НЕ переносить поля автоматически.**
7. **G-7. History + override banner** — `.history/<id>.<version>.json` перед save;
   override banner при открытии global с campaign-перекрытием.
8. **G-8. New-from clone** — «New from…» → deepcopy → new_id → save as new file.
9. **G-9. Selective propagation hint** — toast при save: «N экземпляров типа X в локации
   не обновлены». Без auto-update (это шаг J).
10. **G-10. Integration tests + smoke** — полный цикл: open → edit → validate → save →
    catalog refresh → place instance → Game Preview (F11) → visual check.

## 5. Архитектурные риски (из Architecture Review)

**R1 КРИТИЧНЫЙ** — AssetStore не имеет write-API. BlueprintRecord frozen.
**R2 КРИТИЧНЫЙ** — default_properties в metadata, не маппится в function.components.
**R3 ВЫСОКИЙ** — цепочка 4 кэшей (AssetStore → CatalogIndex → OBJECT_PRESETS → ENTITY_SPRITE_MAP).
**R4 ВЫСОКИЙ** — существующие экземпляры на картах не ссылаются на чертёж (дизайн §5.3).
**R5 СРЕДНИЙ** — нет обнаружения конфликтов версии.
**R6 СРЕДНИЙ** — emoji в metadata.icon не рендерятся в consolas (баг шага F).
**R7 СРЕДНИЙ** — привязка к стене 3 формы (ME-1.5 — чужой этап).
**R8 НИЗКИЙ** — Step E (categories[]) исходно не верифицирован в архиве — проверить по
живому коду: `list_category_tree`, `refresh_object_presets`.
**R9 НИЗКИЙ** — AssetStoreError при load() ломает весь склад.
**R10 НИЗКИЙ** — категории кампании перекрывают global (override) — UI обязан показывать.

## 6. Контракт Blueprint Editor (предлагаемый — из Architecture Review Результат 4)

```python
# frontend/map_editor/assets/blueprint_editor.py (предлагается)

@dataclass
class EditSession:
    blueprint_id: str
    original: dict          # deepcopy(record.data) на момент open
    working: dict           # мутируется UI
    opened_version: int     # record.version на момент open
    dirty: bool             # working != original (deep compare)

@dataclass
class SaveResult:
    ok: bool
    version: int | None = None
    blocked_by: list[ValidationIssue] = field(default_factory=list)
    conflict: VersionConflict | None = None
    cache_stale: bool = False

class BlueprintEditor:
    def __init__(self, asset_store, catalog_index, validator): ...
    def open(self, blueprint_id: str) -> EditSession: ...
    def update_field(self, session, path: str, value: Any) -> list[ValidationIssue]: ...
    def validate(self, session) -> ValidationResult: ...
    def save(self, session) -> SaveResult: ...   # atomic: validate → version-check → tmp → test-load → rename → reload-all-caches
    def cancel(self, session) -> None: ...
    def new_from(self, source_id: str, new_id: str) -> EditSession: ...
```

**Контракт НЕ затрагивает:** WorldObject (чистый домен), AffordanceResolver (runtime),
game_screen.py / world_context.py (гейт S-ME1). Все новые типы — в
`frontend/map_editor/assets/`.

## 7. Безопасность — 10 сценариев (из Architecture Review Этап 3)

1. Ошибка в поле не уничтожает оригинал (tmp → rename).
2. Неизвестные поля сохраняются (dict round-trip, не типизированная модель).
3. Некорректная ссылка на ресурс блокирует save (ResourceValidator L2 error).
4. Конфликт версии обнаруживается (version compare перед rename).
5. Отмена не оставляет частично изменённое состояние (deepcopy(original), tmp cleanup).
6. Каталог обновляется только после успешной записи (refresh в шаге 6, не ранее).
7. Существующие экземпляры не меняются автоматически (дизайн §5.3; toast о N экземплярах).
8. Один битый JSON не ломает склад (test_store.load() перед rename).
9. Override кампании видим (баннер в UI).
10. blueprint_id == filename (rename запрещён в v1, edit-only).

## 8. Открытые вопросы — только Master решает

1. **Порядок G-1…G-10** — подтвердить или изменить.
2. **R2 (default_properties)** — оставить как raw JSON с предупреждением (предложение
   архитектора) или формализовать маппинг сейчас (open/locked → opener/lockable;
   durability → physics; visibility_through → semantics)?
3. **GAP — верифицировать [S]-утверждения** по живому коду шагов E и F перед стартом
   реализации: `list_category_tree` существует? `refresh_object_presets` работает?
   `CatalogPanel` source соответствует описанию?
4. **Hotkey** — F4 для Blueprint Editor (F2/F3/F11 заняты)? Или кнопка в каталоге?
5. **Sprite atlas content** — bones=heart, sign_flophouse=gates (известный баг, отдельная
   задача, НЕ блокирует G).

## 9. Известные RED/хвосты на входе (не твои, не трогай)

- `test_p2_provenance_origin_vs_seeded` — известный RED, вердикт Мастера, владелец CCH-4.
- Sprite atlas content mismatches (bones, sign_flophouse) — контентный баг, не кодовый.
- WIP соседних сессий — эскалация Мастеру, не чинить.

## 10. Процессные уроки серии ME-2.1 (оплачено — не повторяй)

1. **Один пакет правок = один коммит.** Расхождение message↔содержимое не чинится без
   переписывания истории.
2. **Architecture Review БЕЗ реализации** — отдельный артефакт (docx). Реализация —
   следующий GO, не в той же сессии.
3. **[V] vs [S] vs [GAP]** — достоверность фактов. [V] = проверено по коду (file:line);
   [S] = из summary (исходник недоступен); [GAP] = не верифицировано. Перед стартом
   реализации — все [S] и [GAP] проверить по живому коду.
4. **ruff + pytest перед каждым коммитом.** Hook может упасть на ЧУЖОМ файле —
   верифицируй свой коммит постфактум (`git show --stat HEAD`).
5. **Механика — Мастеру вопросами; архитектура и код — тебе.**
6. **AssetStore read-only** — не пытаться «просто обновить dict в record.data».
   BlueprintRecord frozen. Write-путь — отдельный метод с атомарностью.
7. **default_properties — НЕ механический перенос.** R2 — решение Master, не архитектора.

## 11. Гейт закрытия твоего шага

Закрытие шага G-N = гейт шага + строка журнала §10.4 roadmap (5-колоночный формат!) +
галочка в чеклисте §7.2 + строка в MUTATIONS + обновление MISSING_TEXTURES (если трогал
спрайты). Один подэтап → один коммит → один набор тестов.

**Критерий успеха линии (вертикальный тест):** новый чертёж создаётся из существующего
через `new_from` без кода; правка полей валидируется на лету; save атомарен (ошибка в
поле не портит оригинал); каталог обновляется после save; существующие экземпляры на
карте не меняются автоматически (toast показывает N); конфликт версии обнаруживается.

*Передал: сессия ME-2.1-G Architecture Review. Удачи. Читай §2 до конца — каждый пункт
этого списка кем-то оплачен. **После отчёта — стоп. Реализация — следующий GO.***
