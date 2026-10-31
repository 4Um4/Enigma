ENIGMA Map Editor

**ME-2.1-G --- Architecture Review: Blueprint Editor**

*Статус: исследование (read-only). Код не изменяется, JSON не создаётся,
контракты WorldObject / AffordanceResolver / игровые потребители не
трогаются. После отчёта --- остановка. Реализация не начинается.*

  -----------------------------------------------------------------------
  **Поле**                            **Значение**
  ----------------------------------- -----------------------------------
  Этап roadmap                        ME-2.1-G (после E --- Category
                                      hierarchy)

  Порядок Master                      E → G → H → I → J → K → L

  Предыдущий коммит                   3cfb374e --- ME-2.1-E: Category
                                      hierarchy + multiple membership

  Базлайн                             111 тестов ME-2.1, ruff clean

  Источник фактов                     BLUEPRINT_FORMAT_SPEC_v1.md;
                                      ТЗ_преемнику S349; фактический код
                                      из paste-архива сессий S349--ME-2.1
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------
  **LEGEND --- достоверность:** \[V\] = проверено по фактическому коду
  (file:line). \[S\] = из summary предыдущей сессии (исходник недоступен
  в архиве). \[GAP\] = не верифицировано --- требует подсветки Master.
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------

**Результат 1. Карта текущей архитектуры**

Карта построена по двум слоям достоверности. Фактический код --- из
paste-архива сессий S349 и ME-2.1 (файлы Pasted Content\_\*.txt в
/upload). Шаги E и F создавались в сессиях, чьи исходники в архив не
попали --- для них указано \[S\] и требуется верификация по живому коду
на машине Master.

**1.1. AssetStore и BlueprintRecord \[V\]**

Файл: frontend/map_editor/assets/asset_store.py. Склад чертежей поверх
папки assets/. Read-only: загрузка из каталогов, никаких write-методов.

+-----------------------------------------------------------------------+
| \# asset_store.py:27-37 --- модульные константы ключей                |
|                                                                       |
| \_KEY_BLUEPRINT_ID = \"blueprint_id\"                                 |
|                                                                       |
| \_KEY_VERSION = \"version\"                                           |
|                                                                       |
| \_KEY_COMPAT = \"compat\"                                             |
|                                                                       |
| \_BLUEPRINTS_DIR = \"blueprints\"                                     |
|                                                                       |
| \_GLOBAL_CATALOGS_DIR = \"catalogs\"                                  |
|                                                                       |
| \_SOURCE_GLOBAL = \"global\"                                          |
|                                                                       |
| \_SOURCE_CAMPAIGN = \"campaign\"                                      |
|                                                                       |
| \# asset_store.py:40-46 --- громкий отказ загрузки                    |
|                                                                       |
| class AssetStoreError(RuntimeError): \...                             |
|                                                                       |
| \# asset_store.py:48-60 --- frozen dataclass, НЕ МУТИРУЕТ             |
|                                                                       |
| \@dataclass(frozen=True)                                              |
|                                                                       |
| class BlueprintRecord:                                                |
|                                                                       |
| data: dict \# полный JSON чертежа (все 6 слоёв)                       |
|                                                                       |
| version: int                                                          |
|                                                                       |
| source: str \# \"global:\<каталог\>\" \| \"campaign:\<кампания\>\"    |
|                                                                       |
| path: Path \# исходный файл на диске                                  |
|                                                                       |
| \@property                                                            |
|                                                                       |
| def blueprint_id(self) -\> str: return                                |
| str(self.data\[\_KEY_BLUEPRINT_ID\])                                  |
|                                                                       |
| \# asset_store.py:77+ --- AssetStore API                              |
|                                                                       |
| class AssetStore:                                                     |
|                                                                       |
| def \_\_init\_\_(self, base_dir, campaign_id=None): \...              |
|                                                                       |
| def load(self) -\> None: \... \# читает                               |
| catalogs/\*/blueprints/\*.json + \<campaign\>/                        |
|                                                                       |
| def get_blueprint(self, id) -\> Optional\[BlueprintRecord\]: \...     |
|                                                                       |
| def list_blueprints(self) -\> List\[str\]: \... \# sorted             |
|                                                                       |
| def get_resource(self, id) -\> Optional\[ResourceRecord\]: \...       |
|                                                                       |
| def list_resources(self) -\> List\[str\]: \...                        |
|                                                                       |
| def stats(self) -\> Tuple\[int, int, int\]: \... \# (bp, res,         |
| overrides)                                                            |
|                                                                       |
| \@property                                                            |
|                                                                       |
| def overrides(self) -\> List\[str\]: \... \# \"имя: global -\>        |
| campaign\"                                                            |
|                                                                       |
| \# НЕТ save_blueprint / add_blueprint / update_blueprint /            |
| delete_blueprint                                                      |
+=======================================================================+
+-----------------------------------------------------------------------+

  -----------------------------------------------------------------------
  **КРИТИЧЕСКАЯ НАХОДКА #1:** AssetStore не имеет write-API.
  BlueprintRecord --- frozen dataclass. Сегодня склад читается при старте
  (load()) и далее только get/list/stats. Blueprint Editor требует нового
  write-пути, которого нет.
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------

**Правила реестра (asset_store.py:159-201, \_register_blueprint):**

-   **Тип:** JSON-объект (не массив).

-   **Поля:** blueprint_id, version, compat --- обязательные. version и
    compat --- целые ≥ 1.

-   **Имя файла = blueprint_id:** blueprint_id == path.stem. Расхождение
    → проблема, AssetStoreError при load().

-   **Приоритет:** campaign-каталог перекрывает global при совпадении
    имени; перекрытие фиксируется в \_overrides (видимо проверкам).

-   **Приватность:** каталоги ДРУГИХ кампаний не загружаются ---
    приватность (спека §2).

**1.2. Формат Blueprint JSON на диске \[V spec / S actual\]**

Спецификация: BLUEPRINT_FORMAT_SPEC_v1.md (в /upload). 6 слоёв +
служебные поля. Фактические 30 файлов созданы на шаге ME-2.1-A; исходник
шага в архиве отсутствует --- структура ниже собрана из спеки и summary,
требует верификации по одному файлу на диске (см. GAP).

+-----------------------------------------------------------------------+
| {                                                                     |
|                                                                       |
| \"blueprint_id\": \"door\", // = path.stem, обязательное              |
|                                                                       |
| \"version\": 1, // целое \>= 1                                        |
|                                                                       |
| \"compat\": 1, // целое \>= 1                                         |
|                                                                       |
| \"type\": \"door\", // тип пресета (для OBJECT_PRESETS)               |
|                                                                       |
| \"category\": \"wall_object\", // \[S\] Step E: ещё categories\[\]    |
| (массив)                                                              |
|                                                                       |
| \"categories\": \[\"wall_object/opening\", \"transition/portal\"\],   |
| // \[S\] Step E                                                       |
|                                                                       |
| \"tags\": \[\"door\", \"portal\", \"wooden\"\],                       |
|                                                                       |
| \"geometry\": { \"source\": \"primitive\", \"size\":                  |
| {\"w\":1.0,\"h\":0.2,\"d\":0},                                        |
|                                                                       |
| \"rotation_mode\": \"mirror\", \"requires_wall\": true },             |
|                                                                       |
| \"appearance\": { \"color\": \"#D2691E\", \"show_name\": true,        |
|                                                                       |
| \"sprite\": \[\"Deadbeat/deadbeat_b\", 3, 9\] },                      |
|                                                                       |
| \"physics\": { \"passability\": {\"walk\":true,\"jump_over\":false,   |
|                                                                       |
| \"crawl_under\":false,\"climb_on\":false,                             |
|                                                                       |
| \"walk_around\":true},                                                |
|                                                                       |
| \"cover\": 0.0, \"height\": 2.2 },                                    |
|                                                                       |
| \"function\": { \"components\": \[\] }, // \[S\] пустой у большинства |
|                                                                       |
| \"semantics\": { }, // \[S\] наполняется на Этапе 03                  |
|                                                                       |
| \"metadata\": { \"label\": \"Дверь\", \"icon\": \"\...\",             |
|                                                                       |
| \"default_properties\": { // \[S\] сохранены тут                      |
|                                                                       |
| \"open\": true, \"locked\": false,                                    |
|                                                                       |
| \"durability\": 20, \"visibility_through\": 0.1                       |
|                                                                       |
| } }                                                                   |
|                                                                       |
| }                                                                     |
+=======================================================================+
+-----------------------------------------------------------------------+

  -----------------------------------------------------------------------
  **КРИТИЧЕСКАЯ НАХОДКА #2:** default_properties сохранены в metadata, НЕ
  маппятся в function.components (summary шага A: «default_properties
  preserved in metadata, not mapped to function.components»). Спека §4.4
  предписывает маппинг: open/locked → opener/lockable; durability →
  physics.durability; visibility_through → semantics.perceivability. Это
  неразрешённый семантический разрыв --- редактор НЕ должен механически
  переносить поля, но обязан показать расхождение Master.
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------

**1.3. Шесть слоёв и реальные потребители \[V spec\]**

  ---------------------------------------------------------------------------------------------------------------------------------------------
  **Слой**          **Поля (v1)**                                                   **Потребители (верифицировано)**     **Примечание**
  ----------------- --------------------------------------------------------------- ------------------------------------ ----------------------
  geometry          size{w,h,d}, source (primitive\|imported), rotation_mode,       geometry_builder.build_geometry();   Спека §4.1; parts\[\]
                    requires_wall, parts\[\]                                        SpatialDataLoader (game);            пуст в v1 (объект =
                                                                                    scene_bridge (preview);              одна часть)
                                                                                    DataManager.get_resolved_object() →  
                                                                                    size                                 

  appearance        color, show_name, sprite \[лист,кол,стр\] \|                    SpriteRegistry (деривация            Спека §4.2; sprite ---
                    \[лист,x,y,w,h,порог,обводка\], variants\[\], animations?       ENTITY_SPRITE_MAP); map_renderer     ссылка на
                                                                                    (отрисовка); ResourceValidator L2    pixels/\<sheet\>.png
                                                                                    (файл существует)                    

  physics           passability{walk,jump_over,crawl_under,climb_on,walk_around},   geometry_builder (препятствия);      Спека §4.3; дефолты в
                    cover, height, mass?, movable?, durability?, collision_mode     DataManager →                        чертеже, экземпляр не
                                                                                    passability/cover/height в старый    дублирует
                                                                                    словарь; ResourceValidator L1        
                                                                                    (passability ключи)                  

  function          components: \[{type, \...}\]. Типы v1: storage, opener,         DataManager → проекция в properties  Спека §4.4;
                    lockable, ownership, surface, light_source                      (opener→open, lockable→locked);      наполняется на Этапе
                                                                                    AffordanceResolver (runtime, backend 03
                                                                                    --- НЕ редактор)                     

  semantics         owner?, origin?, value?, legality?, history?, knowledge_seeds?, DataManager → проекция в properties  Спека §4.6;
                    perceivability{visibility_through, sound_attenuation}?          (visibility_through,                 knowledge_seeds ---
                                                                                    sound_attenuation); Triple Membrane  только стартовые, до
                                                                                    (runtime --- НЕ редактор)            игры

  metadata          label, icon, default_properties (legacy), versioning?, автор?   CatalogIndex.get_preview (label,     Спека §2;
                                                                                    icon, sprite); CatalogPanel UI;      default_properties ---
                                                                                    refresh_object_presets →             переходный артефакт
                                                                                    OBJECT_PRESETS \[S\]                 ME-1.6
  ---------------------------------------------------------------------------------------------------------------------------------------------

**1.4. default_properties --- критический разбор \[V\]**

Поле живёт в OBJECT_PRESETS (data_manager.py:141+) и, по summary,
продублировано в metadata чертежа. Структура РАЗНАЯ для разных типов ---
это не схема, а набор ad-hoc ключей. Каждый ключ имеет своего
потребителя в runtime, но маппинг на слои спецификации не доказан для
всех.

  -------------------------------------------------------------------------------------------------------------------------------------------
  **Ключ**             **Тип**     **Где встречается       **Семантика**     **Канон (спека)**          **Предлагаемый слой**
                                   (значения)**                                                         
  -------------------- ----------- ----------------------- ----------------- -------------------------- -------------------------------------
  open                 bool        door, door_transition   Открыто/закрыто   opener.states (спека §4.4) function.components\[opener\]

  locked               bool        door, door_transition   Заперто           lockable{key_ref} (§4.4)   function.components\[lockable\]

  durability           int         door(20), window(15),   Прочность         physics.durability (§4.3)  physics.durability
                                   door_transition(25)                                                  

  visibility_through   float 0..1  door(0.1), window(0.8), Заметность сквозь semantics.perceivability   semantics.perceivability
                                   gap(1.0),               объект            (§4.6)                     
                                   door_transition(0.0),                                                
                                   portal_magic(0.5)                                                    

  sound_attenuation    float 0..1  window(0.3), gap(0.0)   Затухание звука   semantics.perceivability   semantics.perceivability
                                                                             (§4.6)                     

  direction            up\|down    stairs_up, stairs_down, Направление       НЕ в спеке v1 явно         GAP --- требует решения Master
                                   ladder                  перехода                                     

  target_file          str         door_transition,        Целевая локация   transition/portal (§4.4    function.components\[transition\]
                                   portal_magic            перехода          --- нет явно)              

  target_portal        str         door_transition,        Целевой портал    transition/portal          function.components\[transition\]
                                   portal_magic                                                         

  opacity              float       window(0.3)             Непрозрачность    appearance? physics? ---   GAP --- требует решения Master
                                                                             НЕ в спеке v1              

  destructible         bool        window(True)            Разрушаемость     destructible{\...} (спека  Зарезервировано, не активировать
                                                                             §7 --- резерв v1.1)        

  light_radius         float       light_source \[S\]      Радиус света      light_source{\...} (§4.4)  function.components\[light_source\]

  temperature          int K       light_source \[S\]      Температура света light_source{\...} (§4.4)  function.components\[light_source\]
  -------------------------------------------------------------------------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **ВЫВОД:** Часть default_properties имеет доказанный маппинг
  (open/locked/durability/visibility_through/sound_attenuation). Часть
  --- НЕ доказана (direction, opacity --- нет в спеке v1). Редактор
  обязан показывать два класса по-разному: первый --- как редактируемые
  проекции компонентов; второй --- как raw-поля metadata с
  предупреждением «семантика не формализована».
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------

**1.5. categories\[\] и иерархия \[S --- Step E\]**

Step E (коммит 3cfb374e) добавил поле categories\[\] (массив строк с
/-иерархией) и сохранил старое category (строка) для обратной
совместимости. CatalogIndex Step C (исходник верифицирован) имел только
category + tags. Step E расширил filter() до prefix-match и добавил
list_category_tree(). Исходник Step E в архиве отсутствует --- ниже
реконструкция из summary.

+-----------------------------------------------------------------------+
| \# CatalogIndex Step C --- верифицировано (catalog_index.py:27-145)   |
|                                                                       |
| class CatalogIndex:                                                   |
|                                                                       |
| def \_\_init\_\_(self, asset_store): self.refresh()                   |
|                                                                       |
| def refresh(self): \... \# rebuild \_entries, \_by_category, \_by_tag |
|                                                                       |
| def search(self, query: str) -\> list\[str\]: \... \# по              |
| id/label/tags                                                         |
|                                                                       |
| def filter(self, category=None, tags=None) -\> list\[str\]: \... \#   |
| exact category + ALL tags                                             |
|                                                                       |
| def get_preview(self, id) -\> dict \| None: \... \#                   |
| {id,label,tags,category,type,sprite,icon}                             |
|                                                                       |
| def list_categories(self) -\> list\[str\]: \...                       |
|                                                                       |
| def list_tags(self) -\> list\[str\]: \...                             |
|                                                                       |
| def list_all(self) -\> list\[str\]: \...                              |
|                                                                       |
| def get_category_count(self, cat) -\> int: \...                       |
|                                                                       |
| def get_tag_count(self, tag) -\> int: \...                            |
|                                                                       |
| \@property                                                            |
|                                                                       |
| def count(self) -\> int: \...                                         |
|                                                                       |
| \# CatalogIndex Step E --- \[S\] реконструкция из summary             |
|                                                                       |
| \# + categories: list\[str\] в entry (из data\[\"categories\"\])      |
|                                                                       |
| \# + filter(category=X) → prefix match: \"furniture\" matches         |
| \"furniture/indoor\"                                                  |
|                                                                       |
| \# + list_category_tree() → {parent: \[children\]}                    |
|                                                                       |
| \# + multiple membership: door in                                     |
| \[\"wall_object/opening\",\"transition/portal\"\]                     |
+=======================================================================+
+-----------------------------------------------------------------------+

Примеры categories\[\] (summary): table → \[furniture/indoor\]; door →
\[wall_object/opening, transition/portal\] --- множественная
принадлежность. Дерево категорий строится из дочерних строк отсечением
последнего сегмента после /.

**1.6. ResourceValidator --- 4 уровня \[V\]**

Файл: frontend/map_editor/assets/resource_validator.py. Полный исходник
верифицирован (resource_validator.py:173-365). Валидация НЕ булева ---
ValidationResult с issues\[\] (error/warning/info).

  -------------------------------------------------------------------------------------------------------------------------------------
  **Уровень**       **Severity**      **Что проверяет**                                                        **Метод**
  ----------------- ----------------- ------------------------------------------------------------------------ ------------------------
  L1 Structural     error             Поля: blueprint_id, version, compat. Слои: geometry, appearance,         validate_blueprint →
                                      physics. geometry.size.{w,h,d} \> 0.                                     \_check_structural
                                      physics.passability.{walk,jump_over,crawl_under,climb_on,walk_around}.   

  L2 Resource       error / warning   appearance.sprite: None → warning (фолбэк). Не list или длина ≠ 3,7 →    validate_blueprint →
                                      error. sheet_key не строка → error. Файл pixels/\<sheet\>.png не         \_check_resources
                                      существует → error.                                                      

  L3 Editor compat  warning           type не задан → warning. type не в OBJECT_PRESETS → warning (НЕ error    validate_blueprint →
                                      --- допускает новые типы).                                               \_check_editor_compat
                                                                                                               (импорт OBJECT_PRESETS)

  L4 Runtime compat info              Архетип не в \_KNOWN_ARCHETYPES = {door, chair, container, bed, lever,   validate_blueprint →
                                      weapon} → info (декоративный, без FSM). НЕ блокирует.                    \_check_runtime_compat
  -------------------------------------------------------------------------------------------------------------------------------------

*Свойства ValidationResult: can_place (нет error), fully_supported (нет
error и warning), errors/warnings/infos --- фильтры.
validate_all(asset_store) → dict\[id, ValidationResult\].*

**1.7. Цепочка обновления кэшей \[S\]**

После любого изменения чертежа должны обновиться 4 слоя. Исходники
refresh-функций (data_manager.py, sprite_registry.py) в архиве
отсутствуют --- реконструкция из summary.

+-----------------------------------------------------------------------+
| \# Цепочка обновления (порядок важен):                                |
|                                                                       |
| AssetStore.load() \# 1. Перечитать JSON с диска                       |
|                                                                       |
| └─ \_register_blueprint × N \# rebuild \_blueprints dict              |
|                                                                       |
| CatalogIndex.refresh() \# 2. Перестроить индекс                       |
|                                                                       |
| └─ for bp in store.list: read data \# rebuild \_entries,              |
| \_by_category, \_by_tag                                               |
|                                                                       |
| refresh_object_presets(asset_store) \# 3. \[S\] data_manager.py       |
|                                                                       |
| └─ \_derive_presets_from_assetstore() \# rebuild OBJECT_PRESETS из    |
| AssetStore                                                            |
|                                                                       |
| └─ OBJECT_PRESETS.clear(); .update() \# in-place mutation (НЕ rebind) |
|                                                                       |
| └─ fallback: \_HARDCODED_OBJECT_PRESETS                               |
|                                                                       |
| refresh_entity_sprite_map() \# 4. \[S\] sprite_registry.py            |
|                                                                       |
| └─ \_derive_entity_sprite_map() \# rebuild ENTITY_SPRITE_MAP из       |
| OBJECT_PRESETS                                                        |
|                                                                       |
| └─ dict(\_PRESET_SPRITE_FALLBACK) \# 7 типов фолбэка                  |
+=======================================================================+
+-----------------------------------------------------------------------+

  -----------------------------------------------------------------------
  **РИСК #3:** Цепочка из 4 слоёв. Если любой промежуточный падает, кэши
  рассинхронизированы. Сегодня CatalogPanel открывается с вызовом
  refresh_object_presets + refresh_entity_sprite_map \[S\] --- это точка,
  где рассинхрон уже случался. Write-путь редактора обязан делать
  обновление атомарно (см. §Контракт).
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------

**1.8. CatalogPanel UI контракт \[S --- Step F\]**

Файл: frontend/map_editor/ui/catalog_panel.py (\~384 строки). Исходник в
архиве отсутствует --- реконструкция из summary + точечные ссылки в
editor_core.py:379-384 (верифицировано).

+-----------------------------------------------------------------------+
| \# editor_core.py:379-384 \[V\]                                       |
|                                                                       |
| self.catalog_panel = CatalogPanel(                                    |
|                                                                       |
| catalog_x, catalog_y, catalog_w, catalog_h,                           |
|                                                                       |
| Path(\_\_file\_\_).parent / \"assets\", \# AssetStore base            |
|                                                                       |
| Path(\_\_file\_\_).parent / \"pixels\", \# ResourceValidator base     |
|                                                                       |
| )                                                                     |
|                                                                       |
| self.catalog_panel.on_place = lambda bp_id:                           |
| self.\_catalog_place(bp_id)                                           |
|                                                                       |
| \# CatalogPanel \[S\]:                                                |
|                                                                       |
| \# - F3 toggle, left side 250px                                       |
|                                                                       |
| \# - on open: refresh_object_presets() + refresh_entity_sprite_map()  |
|                                                                       |
| \# - search field, category buttons (3-char labels), card list        |
|                                                                       |
| \# - card: label + sprite thumbnail + tags                            |
|                                                                       |
| \# - click card → on_place(bp_id) callback                            |
|                                                                       |
| \# - \_catalog_place(bp_id): set selected_object_type + TOOL_OBJECT   |
+=======================================================================+
+-----------------------------------------------------------------------+

*Горячие клавиши: F3 --- каталог, F11 --- Game Preview, F2 ---
переименовать. Точек интеграции для нового редактора: on_place callback
(контракт вызова) + catalog_panel как holder панели. Модальных окон в
редакторе сегодня нет --- Blueprint Editor будет первым модальным
компонентом.*

**Результат 2. Таблица редактируемых полей и потребителей**

Каждое поле чертежа --- с предложенным UI-контролем и уровнем валидации.
Поля без доказанного потребителя помечены GAP. Поля function/semantics в
v1 преимущественно пустые --- редактор показывает их как
«зарезервировано до Этапа 03», не активирует.

  ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  **JSON path**                                                           **Потребитель (верифицировано)**          **Поведение сейчас**              **UI-контроль**       **Валидация**
  ----------------------------------------------------------------------- ----------------------------------------- --------------------------------- --------------------- -------------------
  blueprint_id                                                            AssetStore.\_register_blueprint (filename Read-only после создания; rename  Text field, disabled  L1 error if
                                                                          match); CatalogIndex key; location.json   = migrate file + update instances в edit-mode; только   missing/empty;
                                                                          instance reference                                                          при create-new        filename match
                                                                                                                                                                            enforced

  version                                                                 AssetStore.\_register_blueprint; future:  Инкремент при каждом сохранении   Auto-field, read-only L1 error if not int
                                                                          instance migration                        (предлагается)                    в UI; показ + счётчик ≥ 1

  compat                                                                  AssetStore.\_register_blueprint; future:  Инкремент при breaking-change     Auto-field,           L1 error if not int
                                                                          runtime gate                              слоёв (geometry/physics/function) read-only; показ      ≥ 1

  type                                                                    DataManager.get_resolved_object;          Должен быть известным или новым;  Dropdown известных    L3 warning if
                                                                          SpriteRegistry деривация;                 влияет на sprite fallback         типов + «new type...» unknown (allows
                                                                          ResourceValidator L3                                                        опция                 new)

  category (legacy)                                                       CatalogIndex \_by_category (Step C exact  Сохраняется для обратной          Auto-derived from     L1 warning if
                                                                          match)                                    совместимости; = categories\[0\]  categories\[\];       absent (deprecated)
                                                                                                                    parent                            read-only             

  categories\[\]                                                          CatalogIndex filter (prefix);             Step E; мультипринадлежность      Multi-select tree     L1 error if empty;
                                                                          list_category_tree; multiple membership   (door в 2 категориях)             checkboxes (from      L1 warning if no
                                                                                                                                                      list_category_tree)   parent prefix match

  tags\[\]                                                                CatalogIndex \_by_tag; search()           Произвольные строки               Tag editor            L1 warning if empty
                                                                                                                                                      (add/remove chips)    

  geometry.size.{w,h,d}                                                   geometry_builder; SpatialDataLoader;      w,h --- план; d --- глубина (z);  Number inputs (float, L1 error if ≤ 0 or
                                                                          DataManager → size                        все \> 0                          step 0.1, min 0.1)    non-numeric

  geometry.source                                                         geometry_builder (выбор пути)             v1: всегда primitive; imported    Radio: primitive (v1) L1 error if not in
                                                                                                                    --- ME-R-628 (Create)             / imported (disabled, {primitive,
                                                                                                                                                      future)               imported}

  geometry.rotation_mode                                                  editor_core rotation handling;            mirror --- для door/window        Dropdown              L1 warning if
                                                                          map_renderer                              (привязка к стене)                                      absent

  geometry.requires_wall                                                  DataManager.\_validate_location_objects   True для                          Checkbox              L1 error if True
                                                                          (wall_id rule)                            door/window/gap/door_transition                         but no wall_id at
                                                                                                                                                                            placement

  appearance.color                                                        map_renderer fallback (если нет sprite)   Используется когда sprite=None    Color picker          L1 warning if
                                                                                                                                                                            invalid HEX

  appearance.show_name                                                    map_renderer (подпись)                    True по умолчанию                 Checkbox              ---

  appearance.sprite                                                       SpriteRegistry; map_renderer;             None → fallback                   Sprite picker (sheet  L2 error if file
                                                                          ResourceValidator L2                      (\_PRESET_SPRITE_FALLBACK, 7      dropdown + tile grid  missing; L2 error
                                                                                                                    типов)                            preview)              if wrong
                                                                                                                                                                            length/type

  physics.passability.{walk,jump_over,crawl_under,climb_on,walk_around}   geometry_builder (obstacles);             Все 5 обязательны                 5 checkboxes (matrix) L1 error if any
                                                                          SpatialDataLoader; AffordanceResolver                                                             missing
                                                                          (runtime)                                                                                         

  physics.cover                                                           DataManager → cover; combat runtime       0 = нет укрытия; 0.8 = барная     Number input (0..1,   L1 warning if out
                                                                                                                    стойка                            step 0.1)             of range

  physics.height                                                          DataManager → height; LOS runtime         0.1 = люк; 4.0 = ель              Number input (float,  L1 warning if ≤ 0
                                                                                                                                                      step 0.1, min 0.01)   

  function.components\[\]                                                 DataManager → projection to properties;   v1: пустой у большинства;         Component editor      L1 warning if empty
                                                                          AffordanceResolver (runtime)              default_properties сохранены      (add/remove typed     (info-only в v1)
                                                                                                                    отдельно \[GAP\]                  components) --- Этап  
                                                                                                                                                      03                    

  semantics.perceivability.{visibility_through, sound_attenuation}        DataManager → projection; Triple Membrane В default_properties \[GAP\] ---  Number inputs (0..1)  L1 warning if
                                                                          (runtime)                                 не в semantics                    --- Этап 03 активация absent but type
                                                                                                                                                                            implies
                                                                                                                                                                            (door/window/gap)

  metadata.label                                                          CatalogIndex.get_preview; CatalogPanel UI Русский текст; отображается в     Text field            L1 warning if empty
                                                                                                                    каталоге                                                

  metadata.icon                                                           CatalogPanel card                         Emoji в пресетах; consolas шрифт  Text field (emoji     --- (известный баг
                                                                                                                    не рендерит emoji \[V --- баг     picker) или путь к    рендера)
                                                                                                                    шага F\]                          PNG                   

  metadata.default_properties                                             DataManager → projection to properties;   Сохранены в metadata, не маппятся Raw JSON editor с     L4 info: «семантика
                                                                          refresh_object_presets \[S\]              в function.components \[S\]       предупреждением «не   не доказана для
                                                                                                                                                      формализовано»        direction, opacity»
  ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

**Семантика полей (отдельно для читаемости):**

  -----------------------------------------------------------------------------------------------------------
  **JSON path**                                                           **Семантика**
  ----------------------------------------------------------------------- -----------------------------------
  blueprint_id                                                            Идентификатор чертежа = имя файла

  version                                                                 Версия чертежа (целое ≥ 1)

  compat                                                                  Минимальная поддерживаемая версия
                                                                          формата

  type                                                                    Тип пресета (ключ в OBJECT_PRESETS)

  category (legacy)                                                       Одна категория (строка)

  categories\[\]                                                          Массив иерархических категорий с /

  tags\[\]                                                                Теги для поиска

  geometry.size.{w,h,d}                                                   Размеры (float \> 0)

  geometry.source                                                         primitive \| imported

  geometry.rotation_mode                                                  free \| mirror \| fixed

  geometry.requires_wall                                                  bool --- объект требует стену

  appearance.color                                                        HEX цвет

  appearance.show_name                                                    bool

  appearance.sprite                                                       \[sheet, col, row\] \| \[sheet, x,
                                                                          y, w, h, threshold, stroke\]

  physics.passability.{walk,jump_over,crawl_under,climb_on,walk_around}   5 bool --- как NPC проходит объект

  physics.cover                                                           float 0..1 --- укрытие

  physics.height                                                          float --- высота в метрах

  function.components\[\]                                                 Массив компонентов {type, \...}

  semantics.perceivability.{visibility_through, sound_attenuation}        Заметность/звук сквозь объект

  metadata.label                                                          Человекочитаемое имя

  metadata.icon                                                           Emoji или путь

  metadata.default_properties                                             Legacy dict \[GAP\]
  -----------------------------------------------------------------------------------------------------------

**Результат 3. Архитектурные риски**

  ----------------------------------------------------------------------------------------------------
  **\#**         **Severity**   **Риск**               **Следствие / требование**      **Приоритет**
  -------------- -------------- ---------------------- ------------------------------- ---------------
  R1             КРИТИЧНЫЙ      AssetStore не имеет    Нельзя «просто обновить»        Высокий
                                write-API.             чертёж. Требуется новый метод   
                                BlueprintRecord ---    save_blueprint(record) /        
                                frozen.                add_blueprint /                 
                                                       delete_blueprint с гарантией    
                                                       атомарности (tmp-file +         
                                                       rename). Без этого редактор не  
                                                       существует.                     

  R2             КРИТИЧНЫЙ      default_properties в   Редактор показывает raw JSON →  Высокий
                                metadata, не маппится  Master правит «вслепую» без     
                                в function.components. валидации. Риск: правка         
                                                       open=true в metadata не меняет  
                                                       function.components\[opener\] → 
                                                       runtime берёт старое → тихий    
                                                       дефект.                         

  R3             ВЫСОКИЙ        Цепочка из 4 кэшей     Любой сбой в середине →         Высокий
                                (AssetStore →          рассинхрон. Сегодня refresh     
                                CatalogIndex →         вызывается при открытии         
                                OBJECT_PRESETS →       каталога \[S\]; write-путь      
                                ENTITY_SPRITE_MAP).    требует транзакции: write →     
                                                       reload ALL or rollback.         

  R4             ВЫСОКИЙ        Существующие           Правка чертежа НЕ влияет на уже Средний
                                экземпляры на картах   размещённые объекты (они ---    (дизайн, не
                                не ссылаются на чертёж полные dict\'ы). Это дизайн     баг)
                                явно (старая форма).   (спека §5.3), но Master должен  
                                                       видеть: правка door.json не     
                                                       обновит двери в уже сохранённых 
                                                       локациях.                       

  R5             СРЕДНИЙ        Нет обнаружения        Два редактора (или редактор +   Средний
                                конфликтов версии.     игра) могут разойтись. Спека §6 
                                                       требует: «ни один экземпляр не  
                                                       теряет свойство молча».         
                                                       Редактор обязан хранить version 
                                                       читаемого файла и сравнивать    
                                                       перед записью.                  

  R6             СРЕДНИЙ        Emoji в metadata.icon  Карточки каталога показывают    Низкий
                                не рендерятся в        «?» вместо иконки. Редактор     (визуальный)
                                consolas \[V --- шаг   должен использовать тот же      
                                F\].                   шрифт и тот же fallback; правка 
                                                       icon в редакторе наследует баг. 

  R7             СРЕДНИЙ        Привязка к стене --- 3 ME-1.5 не закрыт. Редактор      Средний (чужой
                                формы (root wall_id /  правит requires_wall в          этап)
                                properties.wall_id /   geometry, но не wall_id (это    
                                rotation-хак).         поле экземпляра). Опасность:    
                                                       правка requires_wall=true для   
                                                       типа, экземпляры которого без   
                                                       стены --- валидатор ловит, но   
                                                       пользователь не видит.          

  R8             НИЗКИЙ         Шаг E (categories\[\]) Все \[S\]-утверждения о Step E  Низкий
                                исходно не             требуют проверки по живому коду (процедурный)
                                верифицирован в        перед реализацией редактора.    
                                архиве.                Если list_category_tree         
                                                       отсутствует или работает иначе  
                                                       --- multiselect-дерево нужно    
                                                       строить по-другому.             

  R9             НИЗКИЙ         AssetStoreError при    Один битый JSON ломает всё.     Низкий
                                load() --- весь склад  Редактор должен isolировать     
                                недоступен.            правку: save в temp, validate,  
                                                       только потом move. Не           
                                                       полагаться на load() после      
                                                       сохранения.                     

  R10            НИЗКИЙ         Категории кампании     Редактор может править global   Низкий
                                перекрывают global     чертёж, не зная, что кампания   
                                (override).            его перекрыла. UI обязан        
                                                       показывать overrides перед      
                                                       правкой.                        
  ----------------------------------------------------------------------------------------------------

**Этап 2. Архитектурные решения (предложения)**

**2.1. Редактирование шести слоёв**

-   **Активные слои:** geometry, appearance, physics --- полностью
    редактируемые в v1 (поля верифицированы, потребители активны).

-   **Зарезервированные:** function.components\[\] --- UI показывает
    структуру, но добавление компонентов требует Этапа 03
    (AffordanceResolver). В v1 --- read-only с пометкой
    «зарезервировано».

-   **Частичные:** semantics --- поля perceivability активируются (есть
    потребитель в DataManager);
    owner/origin/value/history/knowledge_seeds --- read-only до Этапа
    03.

-   **Metadata:** metadata.label/icon/categories/tags --- редактируемые.
    metadata.default_properties --- raw JSON с предупреждением (R2).

**2.2. Сохранение неизвестных и неподдерживаемых полей**

Принцип round-trip: редактор читает JSON → правит известные поля →
сохраняет ВСЕ поля (известные + неизвестные). Реализация: работать с
dict, не с типизированной моделью. Неизвестные ключи в верхнем уровне и
в каждом слое сохраняются как есть. Редактор НЕ пересоздаёт JSON из
модели --- он мутирует загруженный dict.

+-----------------------------------------------------------------------+
| \# Контракт: load → mutate → save                                     |
|                                                                       |
| record = store.get_blueprint(id) \# BlueprintRecord.data --- dict     |
|                                                                       |
| working_copy = deepcopy(record.data) \# НЕ мутируем оригинал          |
|                                                                       |
| \# \... UI правит known поля в working_copy \...                      |
|                                                                       |
| \# unknown поля остаются нетронутыми                                  |
|                                                                       |
| write_atomic(tmp_path, working_copy) \# tmp → rename → final          |
+=======================================================================+
+-----------------------------------------------------------------------+

**2.3. Multiselect категорий из иерархии**

UI: дерево категорий (из CatalogIndex.list_category_tree()) с
checkboxами. Leaf-узлы --- выбираемые; parent-узлы --- раскрываемые.
Выбор leaf добавляет строку в categories\[\]. Множественный выбор
разрешён (door в 2 категориях). При сохранении category (legacy) =
parent первого элемента categories\[0\].

**2.4. default_properties --- без механического переноса**

Принцип: НЕ переносить поля автоматически между metadata и слоями.
Редактор показывает ДВЕ секции:

-   **Секция A:** «Компоненты (канон)» --- function.components\[\] с
    типизированными полями. Правка здесь обновляет function.
    Активируется на Этапе 03.

-   **Секция B:** «Legacy default_properties» --- raw JSON редактор с
    предупреждением. Правка здесь обновляет metadata.default_properties.
    Валидация: только структурная (JSON-синтаксис), без семантики.

  -----------------------------------------------------------------------
  **РИСК R2 --- mitigation:** При сохранении редактор сверяет: если
  default_properties содержит ключ, у которого есть доказанный маппинг
  (open/locked/durability/visibility_through/sound_attenuation) ---
  показывать Master предупреждение «поле дублирует компонент; правка в
  одном месте не обновит другое». НЕ автоматически синхронизировать ---
  Master решает.
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------

**2.5. Live validation**

При каждом изменении поля --- вызов
ResourceValidator.validate_blueprint(working_copy). Результат
показывается в панели: ошибки --- красным, warning --- жёлтым, info ---
серым. Кнопка «Save» disabled пока есть errors. Warnings не блокируют
(но показываются в toast перед save).

**2.6. Dirty state и отмена**

Реализация: working_copy + original_copy. dirty = working_copy !=
original_copy (deep compare). UI: в заголовке «\*» перед именем при
dirty. Esc --- запрос на отмену (если dirty --- modal confirm «Discard
changes?»). Ctrl+Z --- undo последнего изменения поля (история на уровне
полей, не глобальный undo).

**2.7. Атомарное сохранение**

+-----------------------------------------------------------------------+
| def save_blueprint_atomic(record, new_data):                          |
|                                                                       |
| \# 1. Validate                                                        |
|                                                                       |
| result = validator.validate_blueprint(new_data)                       |
|                                                                       |
| if result.errors:                                                     |
|                                                                       |
| raise SaveBlocked(result.errors)                                      |
|                                                                       |
| \# 2. Version check (R5)                                              |
|                                                                       |
| current = store.get_blueprint(record.blueprint_id)                    |
|                                                                       |
| if current.version != record.version: \# кто-то поменял               |
|                                                                       |
| raise VersionConflict(current.version, record.version)                |
|                                                                       |
| \# 3. Write to tmp                                                    |
|                                                                       |
| tmp = record.path.with_suffix(\'.json.tmp\')                          |
|                                                                       |
| tmp.write_text(json.dumps(new_data, indent=2, ensure_ascii=False),    |
|                                                                       |
| encoding=\'utf-8\')                                                   |
|                                                                       |
| \# 4. Validate tmp file loads cleanly (R9)                            |
|                                                                       |
| test_store = AssetStore(base_dir)                                     |
|                                                                       |
| test_store.load() \# если упадёт --- tmp остался, оригинал цел        |
|                                                                       |
| \# 5. Atomic rename                                                   |
|                                                                       |
| tmp.replace(record.path)                                              |
|                                                                       |
| \# 6. Reload all caches (R3)                                          |
|                                                                       |
| store.load()                                                          |
|                                                                       |
| catalog_index.refresh()                                               |
|                                                                       |
| refresh_object_presets(store)                                         |
|                                                                       |
| refresh_entity_sprite_map()                                           |
|                                                                       |
| return SaveResult(ok=True, version=new_data\[\'version\'\])           |
+=======================================================================+
+-----------------------------------------------------------------------+

**2.8. Контроль версии и конфликтов**

При открытии редактора: record.version сохраняется в session. При save:
сравнение с текущим store.get_blueprint(id).version. Если расхождение
--- VersionConflict с показом: «файл изменён снаружи; ваша версия N,
текущая M; reload или overwrite?». Master решает. Авто-overwrite
запрещён.

**2.9. Обновление зависимых индексов и кэшей**

Порядок обновления (см. 2.7, шаг 6): AssetStore.load() →
CatalogIndex.refresh() → refresh_object_presets(store) →
refresh_entity_sprite_map(). Если любой шаг падает --- откат: tmp-файл
удаляется, store остаётся в последнем хорошем состоянии, пользователь
видит ошибку. Кэши НЕ обновляются частично.

**2.10. Создание новых Blueprint на основе существующих**

UI: «New from...» → выбор существующего чертежа → deepcopy →
blueprint_id = \<new\> (требуется уникальный) → version=1, compat=1 →
открыть в редакторе. Сохранение создаёт новый файл \<new\>.json. НЕ
мутирует исходный. Имя файла = blueprint_id (правило реестра).

**2.11. Резервирование исходного Blueprint и история**

Перед каждым save: копия оригинала в
assets/catalogs/\<cat\>/.history/\<id\>.\<old_version\>.json. История не
блокирует save (async write). При reload --- .history игнорируется
AssetStore.\_load_catalog (фильтр glob \*.json → glob \*.json без
/.history/). Восстановление --- ручное (Master копирует файл обратно).

**Этап 3. Безопасность --- сценарии**

  ------------------------------------------------------------------------------------------------------
  **\#**            **Сценарий**      **Контракт**                **Тест**
  ----------------- ----------------- --------------------------- --------------------------------------
  S1                Ошибка в одном    Save идёт в tmp → validate  Тест T1: забить geometry.size.w=-1 →
                    поле не           → rename. Оригинал не       Save blocked → оригинал идентичен
                    уничтожает        трогается до успешного      (byte-compare).
                    исходный          rename. Если validate       
                    Blueprint.        падает --- tmp удаляется,   
                                      оригинал цел.               

  S2                Неизвестные поля  Редактор работает с dict,   Тест T2: добавить поле
                    сохраняются.      не типизированной моделью.  \"\_custom\":\"x\" в JSON → открыть →
                                      Неизвестные ключи проходят  закрыть без правок → сохранить → поле
                                      через deepcopy в tmp без    на месте.
                                      изменений. round-trip test. 

  S3                Некорректная      ResourceValidator L2:       Тест T3:
                    ссылка на ресурс  appearance.sprite file not  sprite=\[\'Nonexistent/sheet\',0,0\] →
                    блокирует         found → error → Save        Save blocked → error виден в панели.
                    сохранение.       disabled. Master видит      
                                      «Sprite file not found:     
                                      \<sheet\>».                 

  S4                Конфликт версии   save_blueprint_atomic       Тест T4: открыть редактор → изменить
                    обнаруживается.   сравнивает record.version с файл снаружи → Save → VersionConflict
                                      store.current.version.      показан.
                                      Расхождение →               
                                      VersionConflict exception → 
                                      UI modal.                   

  S5                Отмена не         Esc → confirm discard →     Тест T5: править 3 поля → Esc → reopen
                    оставляет         working_copy =              → все поля = оригинал.
                    частично          deepcopy(original).         
                    изменённое        dirty=false. tmp-файл (если 
                    состояние.        был) удаляется. Кэши не     
                                      трогались.                  

  S6                Обновление        CatalogIndex.refresh /      Тест T6: monkeypatch refresh to raise
                    каталога только   refresh_object_presets /    → save завершается (файл на диске) →
                    после успешной    refresh_entity_sprite_map   UI показывает «saved but cache stale,
                    записи.           вызываются ПОСЛЕ rename     reload editor».
                                      (шаг 6 в 2.7). Если rename  
                                      упал --- кэши не тронуты.   
                                      Если refresh упал --- файл  
                                      уже сохранён, но кэш        
                                      устарел; показывать         
                                      ошибку + предложить reload  
                                      редактора.                  

  S7                Существующие      По дизайну (спека §5.3):    Тест T7: разместить door → править
                    экземпляры на     экземпляры --- полные       door.json (color) → экземпляр в
                    карте не меняются dict\'ы в location.json.    локации НЕ меняется (deepcompare).
                    автоматически.    Правка door.json не         
                                      обновляет уже размещённые   
                                      двери. Редактор показывает  
                                      toast при save: «N          
                                      экземпляров типа \'door\' в 
                                      открытой локации не         
                                      обновлены. Selective        
                                      propagation --- шаг J».     

  S8                Один битый JSON   save в tmp +                Тест T8: сохранить чертёж с syntax
                    не ломает весь    test_store.load() перед     error (monkeypatch) →
                    склад.            rename. Если новый файл     test_store.load() падает → rename не
                                      ломает load --- tmp         выполняется → оригинал цел.
                                      удаляется, rename           
                                      отменяется, оригинал цел.   

  S9                Override кампании При открытии редактора:     Тест T9: создать campaign override →
                    видим.            если store.overrides        открыть global в редакторе → баннер
                                      содержит id --- UI          виден.
                                      показывает баннер «Этот     
                                      чертёж перекрыт каталогом   
                                      кампании \<X\>. Правка      
                                      global не повлияет на       
                                      кампанию».                  

  S10               Имя файла =       Save проверяет path.stem == Тест T10: попытка изменить
                    blueprint_id.     blueprint_id. Rename        blueprint_id в UI → поле disabled.
                                      blueprint_id → перемещение  
                                      файла + обновление всех     
                                      ссылок в location.json (но  
                                      это 超出 v1; в v1 rename    
                                      запрещён, edit-only).       
  ------------------------------------------------------------------------------------------------------

**Результат 4. Предлагаемый контракт Blueprint Editor**

Контракт --- минимальный набор типов и функций, который покрывает все 10
сценариев безопасности. Не вводит новых источников истины: AssetStore
остаётся SSOT, CatalogIndex --- запросным слоем, ResourceValidator ---
единственным валидатором.

+-----------------------------------------------------------------------+
| \# frontend/map_editor/assets/blueprint_editor.py (предлагается)      |
|                                                                       |
| \@dataclass                                                           |
|                                                                       |
| class EditSession:                                                    |
|                                                                       |
| \"\"\"Открытая сессия правки одного чертежа.\"\"\"                    |
|                                                                       |
| blueprint_id: str                                                     |
|                                                                       |
| original: dict \# deepcopy(record.data) на момент open                |
|                                                                       |
| working: dict \# мутируется UI                                        |
|                                                                       |
| opened_version: int \# record.version на момент open                  |
|                                                                       |
| dirty: bool \# working != original (deep compare)                     |
|                                                                       |
| \@property                                                            |
|                                                                       |
| def changed_fields(self) -\> list\[str\]: \... \# paths вида          |
| \"geometry.size.w\"                                                   |
|                                                                       |
| \@dataclass                                                           |
|                                                                       |
| class SaveResult:                                                     |
|                                                                       |
| ok: bool                                                              |
|                                                                       |
| version: int \| None = None                                           |
|                                                                       |
| blocked_by: list\[ValidationIssue\] = field(default_factory=list)     |
|                                                                       |
| conflict: \"VersionConflict \| None\" = None                          |
|                                                                       |
| cache_stale: bool = False \# файл сохранён, но refresh упал           |
|                                                                       |
| class VersionConflict(Exception):                                     |
|                                                                       |
| def \_\_init\_\_(self, expected: int, actual: int): \...              |
|                                                                       |
| class BlueprintEditor:                                                |
|                                                                       |
| \"\"\"Контракт редактора: open / edit / validate / save /             |
| cancel.\"\"\"                                                         |
|                                                                       |
| def \_\_init\_\_(self, asset_store: AssetStore,                       |
|                                                                       |
| catalog_index: CatalogIndex,                                          |
|                                                                       |
| validator: ResourceValidator): \...                                   |
|                                                                       |
| def open(self, blueprint_id: str) -\> EditSession:                    |
|                                                                       |
| \"\"\"Load record → deepcopy → EditSession. Запоминает version.\"\"\" |
|                                                                       |
| def update_field(self, session: EditSession,                          |
|                                                                       |
| path: str, value: Any) -\> list\[ValidationIssue\]:                   |
|                                                                       |
| \"\"\"Set field by dotted path. Returns live-validation issues.\"\"\" |
|                                                                       |
| def validate(self, session: EditSession) -\> ValidationResult:        |
|                                                                       |
| \"\"\"Full ResourceValidator pass on working copy.\"\"\"              |
|                                                                       |
| def save(self, session: EditSession) -\> SaveResult:                  |
|                                                                       |
| \"\"\"Atomic: validate → version-check → tmp → test-load → rename →   |
|                                                                       |
| reload-all-caches. Never partial.\"\"\"                               |
|                                                                       |
| def cancel(self, session: EditSession) -\> None:                      |
|                                                                       |
| \"\"\"Discard working. No cache touch. tmp cleanup if any.\"\"\"      |
|                                                                       |
| def new_from(self, source_id: str, new_id: str) -\> EditSession:      |
|                                                                       |
| \"\"\"Clone blueprint under new_id. new_id must be unique.\"\"\"      |
|                                                                       |
| \# UI-слой (CatalogPanel integration) --- отдельно, не в контракте:   |
|                                                                       |
| \# - toggle: F4 (предлагается) или кнопка в каталоге                  |
|                                                                       |
| \# - open: double-click card в CatalogPanel → editor.open(bp_id)      |
|                                                                       |
| \# - on_save_success: catalog_panel.refresh() + toast                 |
|                                                                       |
| \# - on_save_blocked: показать errors в панели                        |
+=======================================================================+
+-----------------------------------------------------------------------+

*Контракт НЕ затрагивает: WorldObject (чистый домен), AffordanceResolver
(runtime), game_screen.py / world_context.py (гейт S-ME1). Все новые
типы живут в frontend/map_editor/assets/ --- рядом с AssetStore /
CatalogIndex / ResourceValidator.*

**Результат 5. План реализации --- последовательные подэтапы**

Подэтапы маленькие, каждый покрывает один риск или одну функцию. После
каждого --- коммит + тесты. Порядок выбран по зависимости: сначала
write-путь (R1), потом UI, потом безопасность, потом default_properties
(R2 --- отдельный, требует решения Master).

  -----------------------------------------------------------------------------------------------------------------
  **\#**         **Подэтап**          **Что делает**                       **Покрывает    **Тесты**
                                                                           риски**        
  -------------- -------------------- ------------------------------------ -------------- -------------------------
  G-1            AssetStore write-API Добавить save_blueprint_atomic /     R1, R3, R8, R9 T1, T2, T8 (atomicity,
                                      add_blueprint / delete_blueprint в                  round-trip, broken-load
                                      AssetStore. tmp → validate →                        isolation)
                                      test-load → rename. Без UI.                         

  G-2            BlueprintEditor core EditSession, SaveResult,             R1, R3, R5     T1, T3, T4, T5, T6
                 (no UI)              VersionConflict,                                    (validate-blocks,
                                      BlueprintEditor.open/save/cancel.                   version-conflict,
                                      Интеграция с ResourceValidator +                    cancel-clean,
                                      CatalogIndex + refresh-цепочка.                     cache-stale)

  G-3            UI: read-only view   CatalogPanel integration:            ---            UI smoke: open → see
                                      double-click card → opens editor                    fields → Esc closes clean
                                      panel с текущими полями (read-only).                
                                      Live validation display. Dirty                      
                                      indicator.                                          

  G-4            UI: editable active  Редактирование geometry / appearance ---            T1, T3 (validate-blocks
                 layers               / physics. Number inputs,                           на size ≤ 0, missing
                                      checkboxes, dropdowns. Save button                  sprite)
                                      (disabled on errors).                               

  G-5            UI: categories       Tree-view из                         R8 (verifies   T: multiselect →
                 multiselect          CatalogIndex.list_category_tree().   Step E)        categories\[\]
                                      Checkbox multi-select. Auto-derive                  round-trip; multiple
                                      legacy category field.                              membership preserved

  G-6            UI: metadata +       metadata.label/icon --- editable.    R2             T: правка
                 default_properties   metadata.default_properties --- raw  (mitigation,   default_properties.open →
                 (R2)                 JSON editor с предупреждением        не фикс)       warning «дублирует
                                      «семантика не формализована».                       function.opener»
                                      Cross-check с function.components                   
                                      --- warning при дублировании.                       

  G-7            History + override   .history/\<id\>.\<version\>.json     R10, R4        T9 (override banner); T:
                 banner               перед save. Override banner при      (visibility)   .history created, не
                                      открытии global с                                   загружается AssetStore
                                      campaign-перекрытием.                               

  G-8            New-from clone       «New from...» → deepcopy → new_id →  ---            T: clone → new file
                                      save as new file.                                   exists, original
                                                                                          unchanged

  G-9            Selective            При save: toast «N экземпляров типа  R4             T7 (instances unchanged)
                 propagation hint     X в локации не обновлены». Без                      
                 (bridge to шаг J)    auto-update (это шаг J).                            

  G-10           Integration tests +  Полный цикл: open → edit → validate  ---            E2E: правка color →
                 smoke                → save → catalog refresh → place                    каталог обновился → новый
                                      instance → Game Preview (F11) →                     экземпляр нужного цвета
                                      visual check.                                       
  -----------------------------------------------------------------------------------------------------------------

**Результат 6. Тесты --- сохранность данных и целостность AssetStore**

Тесты разбиты по гарантированным свойствам. Каждый тест --- атомарный
(один assert на свойство). Имена --- на уровне контракта (не на уровне
UI). Все тесты пишутся в frontend/map_editor/tests/.

**6.1. Atomicity (write-путь)**

-   T1: validate failure → save blocked → original byte-identical

-   T2: round-trip --- unknown fields preserved (load → save → load →
    deep-equal)

-   T8: broken JSON in tmp → test_store.load() raises → rename skipped →
    original intact

**6.2. Validation gating**

-   T3: missing sprite file → SaveResult.ok=False, blocked_by has error

-   T3b: geometry.size.w=0 → SaveResult.ok=False (L1 structural)

-   T3c: missing physics.passability.walk → SaveResult.ok=False

-   T3d: unknown type → SaveResult.ok=True (L3 warning, not error)

**6.3. Version conflict**

-   T4: external change between open and save → VersionConflict raised

-   T4b: same version → save succeeds

**6.4. Cancel cleanliness**

-   T5: edit 3 fields → cancel → reopen → all fields = original

-   T5b: tmp file removed after cancel

-   T5c: caches untouched after cancel (CatalogIndex.count unchanged)

**6.5. Cache coherence**

-   T6: successful save → CatalogIndex sees new fields (search by new
    tag)

-   T6b: successful save → OBJECT_PRESETS refreshed
    (refresh_object_presets called)

-   T6c: successful save → ENTITY_SPRITE_MAP refreshed (new sprite
    visible)

-   T6d: refresh failure → SaveResult.cache_stale=True, file still saved

**6.6. Instance isolation (design invariant)**

-   T7: edit door.json color → existing door instance in location
    unchanged

-   T7b: place new instance after edit → new instance has new color

**6.7. Override visibility**

-   T9: campaign overrides global → editor on global shows override
    banner

-   T9b: editor on campaign override → no banner (this IS the override)

**6.8. Hierarchy + multiple membership (Step E regression)**

-   T10: door.categories =
    \[\'wall_object/opening\',\'transition/portal\'\] preserved

-   T10b: filter(\'wall_object\') matches door (prefix)

-   T10c: filter(\'furniture\') does NOT match door

-   T10d: list_category_tree() stable after save

**6.9. default_properties mitigation (R2)**

-   T11: edit default_properties.open → warning shown (duplicates
    function.opener)

-   T11b: edit default_properties.direction → no warning (no proven
    mapping)

-   T11c: default_properties round-trip preserved (raw JSON)

**6.10. New-from clone**

-   T12: clone door → new_id=\'door_red\' → new file door_red.json
    exists

-   T12b: original door.json byte-identical after clone

-   T12c: cloned blueprint appears in CatalogIndex after save

**6.11. History**

-   T13: save → .history/\<id\>.\<old_version\>.json created

-   T13b: AssetStore.load() ignores .history/ (count unchanged)

-   T13c: history file = exact copy of pre-save original

**6.12. Regression --- existing 111 tests**

-   T14: all ME-2.1 tests (A+B+C+D+E+F) still pass after editor added

-   T14b: ruff clean on new files

**Заключение**

Отчёт завершён. Реализация не начинается --- по условию ТЗ. Следующий
шаг --- решение Master по порядку подэтапов G-1...G-10 и по открытым
вопросам:

-   **Порядок:** Подтвердить порядок G-1 (write-API) → G-2 (core) → G-3
    (UI read) → ...

-   **Решение Master:** R2 (default_properties) --- оставить как raw
    JSON с предупреждением (предложение) или формализовать маппинг
    сейчас?

-   **GAP:** Верифицировать \[S\]-утверждения по живому коду шагов E и F
    --- особенно list_category_tree и refresh_object_presets.

-   **Hotkey:** F4 --- горячая клавиша для Blueprint Editor (F2/F3/F11
    заняты).

  -----------------------------------------------------------------------
  **СТОП.** Реализация не начинается. Жду GO Master на подэтап G-1 (или
  иной по усмотрению).
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------
