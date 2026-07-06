# TZ-INFRA-1: Infrastructure Foundation + Bug Fix Registry

**Версия ТЗ:** 2.0 (расширенная — включает реестр всех найденных багов)
**Дата:** 2026-07-06
**Спринты:** S98 (P0), S99 (P1), S100+ (P2), S101+ (Bug Fixes)
**Статус:** Approved for implementation
**Предыдущий снимок:** V.0.5.3.3.7_Не_хватает_соединительной_ткани
**Текущий снимок:** V.0.5.3.3.8_Не_хватает_соединительной_ткани
**Источник расширения:** Глубокий анализ проекта V.0.5.3.3.8 + отчёты пользователя

---

## 1. Контекст

V.0.5.3.2.7 закрыла архитектурные долги (ТЗ-04 Spatial Authority, ТЗ-10 Pure Reducer, ADR-RCG routing через SceneChange). V.0.5.3.3.8 подтвердила: SHI=100%, PFI=0%, Causal Drift D локализован.

Но **6 инфраструктурных проблем + 58 багов** блокируют устойчивую разработку MVP «Люся» и делают игру фактически неработоспособной.

### Критические пользовательские симптомы (от игрока):

1. Время застывает на 12:02
2. NPC не двигаются
3. "Подойди ко мне" не работает
4. Кнопки промотки времени (1–4) не работают
5. LLM генерирует текст за NPC и автора в двух окнах с системными маркерами
6. NPC телепортируются (нет плавного движения)
7. Направление взгляда не отображается
8. Logs не попадают в GitHub

### Инфраструктурные проблемы:

1. Нет CI → любая регрессия ловится только локально
2. Нет mypy → type confusion при рефакторинге
3. AppAgent засоряет репо (1666 строк мёртвого кода)
4. Legacy dict растёт (59 точек двойной истины)
5. GameLoopBridge нарушает инкапсуляцию
6. Нет архитектурного QUICKSTART
7. Logs исключены из Git через `.gitignore`

---

## 2. Цель

Создать инфраструктурный фундамент И исправить все найденные баги, чтобы сделать игру работоспособной и устойчивой к регрессиям.

---

## 3. Не-цели

- Не закрывает Causal Drift D (отдельная задача — ADR-DRIFT-D)
- Не делает декомпозицию `tick_orchestrator.py` (отдельная задача)
- Не внедряет WorldScheduler (отдельная задача — ТЗ-09)

---

## 4. СВОДНЫЙ РЕЕСТР ОШИБОК (по приоритетам)

### P0 — Критические (блокируют игру) — 12 багов

| ID | Баг | Файл | Симптом | Категория |
|---|---|---|---|---|
| BUG-P0-01 | Время застывает на 12:02 | `tick_orchestrator.py:982-1007`, `scene_init.py:73-79` | `Calendar.advance` обрезает секунды, `game_time_seconds` не передаётся в `world_snapshot` | Backend Logic |
| BUG-P0-02 | NPC не двигаются | `scene_renderer.py:285-318`, `game_screen.py:267-316` | `velocity` всегда (0,0), `traversal_status` всегда IDLE | Frontend Render |
| BUG-P0-03 | "Подойди ко мне" не работает | `tick_orchestrator.py:518-584`, `npc_tick_pipeline.py:1130-1156` | `_is_npc_target` не срабатывает для target="player", player отсутствует в `npc_positions` | Backend Logic |
| BUG-P0-04 | Кнопки промотки времени не работают | `api_client.py:527-534`, `HttpGameGateway`, `DirectGameGateway` | `skip_time` не реализован в gateway'ях, метод `FallbackGateway.skip_time` вне тела класса | Frontend API |
| BUG-P0-05 | Дублирование текста LLM с системными маркерами | `game_screen.py:1050-1132`, `response_validator.py` | LLM генерирует `(whisper)`, `[internal]`, `*thought*`, дубль в message_log и облачке | Frontend+Backend |
| BUG-P0-06 | NPC телепортируются | `scene_renderer.py:285-318` | Нет lerp-интерполяции, snap к `local_position` | Frontend Render |
| BUG-P0-07 | Баг в `_point_near_line` | `editor_core.py:1838` | `(py - y1) * (py - y1)` вместо `(py - y1) * (y2 - y1)`, невозможно выделить стены | Map Editor |
| BUG-P0-08 | QUIT-баг в редакторе | `editor_core.py:913` | `running = False` (локальная) вместо `self._running = False` | Map Editor |
| BUG-P0-09 | NameError в `data_manager.py` | `data_manager.py:455` | `logger` не определён, маскирует реальные баги | Map Editor |
| BUG-P0-10 | NameError в `dm_agent.py` | `dm_agent.py:92,605,619,681,714` | `logger` не определён на уровне модуля | Backend Agent |
| BUG-P0-11 | Hex-цвет в `pygame.draw.circle` | `editor_core.py:2407` | `"#FFD700"` строка вместо `(R,G,B)` tuple, проходы не рисуются | Map Editor |
| BUG-P0-12 | Body state в неверной позиции | `scene_renderer.py:591` | `sw` (ширина) используется для Y-координаты | Frontend Render |

### P1 — Высокие (сильно портят опыт) — 18 багов

| ID | Баг | Файл | Симптом | Категория |
|---|---|---|---|---|
| BUG-P1-01 | Направление взгляда не работает | `game_screen.py:42-106,634`, `scene_renderer.py:435-458` | `inferences` всегда пустой, клик по NPC отключён (`and False`) | Frontend Logic |
| BUG-P1-02 | Logs не попадают в GitHub | `.gitignore` | `*.log`, `*.jsonl`, `backend/data/logs/` исключены | Infra |
| BUG-P1-03 | Дублирование констант в `constants.py` | `constants.py:87-207` | Все цветовые константы определены дважды | Frontend |
| BUG-P1-04 | Дублирование `ENTITY_SPRITE_MAP` | `sprite_registry.py:113-218` | Map и функция определены дважды | Map Editor |
| BUG-P1-05 | `FallbackGateway.skip_time` вне тела класса | `api_client.py:525-535` | Метод определён перед docstring, не становится атрибутом класса | Frontend API |
| BUG-P1-06 | Дубликат `confirmed_location_id` | `game_loop_bridge.py:51-53` | Поле dataclass определено дважды | Frontend API |
| BUG-P1-07 | Парсер спикеров ломается на NPC без name | `game_screen.py:1062-1065` | NPC без `name`/`display_name` не попадают в `known_names` | Frontend Logic |
| BUG-P1-08 | Парсер спикеров ломается на составных именах | `game_screen.py:1100-1106` | `startswith` не находит "Торнин" в "Торнин Серебряная Луна" | Frontend Logic |
| BUG-P1-09 | Эхо-фильтр слишком агрессивен | `game_screen.py:1086-1091` | `similarity > 0.60` ложно отфильтровывает валидные ответы | Frontend Logic |
| BUG-P1-10 | 4-я стена слишком агрессивна | `response_validator.py:109-114` | "Старик смотрит на игроков" → fallback | Backend |
| BUG-P1-11 | TEXTINPUT фильтрация WASD неполная | `game_screen.py:621-631` | Русская раскладка 'ц','ф','ы','в' не фильтруется | Frontend Input |
| BUG-P1-12 | `_draw_nodes()` никогда не вызывается | `editor_core.py:2540-2573` | Навигационные узлы не отображаются | Map Editor |
| BUG-P1-13 | `_show_view_menu()` вводит в заблуждение | `editor_core.py:634` | Метод просто переключает `show_grid` | Map Editor |
| BUG-P1-14 | Мёртвый код `and False` для клика мыши | `game_screen.py:634` | Клик по NPC отключён | Frontend Logic |
| BUG-P1-15 | `PgUp/PgDn` не реализованы | `editor_core.py` | Статус-бар показывает, но клавиши не работают | Map Editor |
| BUG-P1-16 | `infect` без автофокуса | `text_input.py:148-180` | Игрок не видит заражённый текст если поле не в фокусе | Frontend Input |
| BUG-P1-17 | `_select_at` дублирует `_try_select_existing` | `editor_core.py:1671-1732` | Мёртвый код, нигде не вызывается | Map Editor |
| BUG-P1-18 | Хардкод кампании "Open_road" | `editor_core.py:166-170` | Автооткрытие при запуске редактора | Map Editor |

### P2 — Средние (косметика и производительность) — 16 багов

| ID | Баг | Файл | Симптом | Категория |
|---|---|---|---|---|
| BUG-P2-01 | Дубликат `self.current_z` в `_copy_selection` | `editor_core.py:852-853` | Сброс этажа при копировании | Map Editor |
| BUG-P2-02 | Шрифт создаётся в цикле | `scene_renderer.py:473` | `SysFont` при каждом hover | Frontend Perf |
| BUG-P2-03 | `format_world_date` каждый кадр | `game_screen.py:1371-1374` | Строка пересоздаётся без кэша | Frontend Perf |
| BUG-P2-04 | `DirectGameGateway.send_action` — мёртвый код | `api_client.py:437-441` | Код после `return` | Frontend API |
| BUG-P2-05 | `GameGateway.new_game` — реализация в Protocol | `api_client.py:103-105` | `self._t.post` в Protocol | Frontend API |
| BUG-P2-06 | `GameGateway.skip_time` — реализация в Protocol | `api_client.py:121-125` | Аналогично | Frontend API |
| BUG-P2-07 | `_time_scale` не используется | `game_screen.py:495` | Переменная объявлена, не меняется | Frontend |
| BUG-P2-08 | `walk_distance_accumulated` без эффекта | `game_screen.py:730-739` | `pass` — накопление без результата | Frontend |
| BUG-P2-09 | `_prev_npc_positions` не очищается при смене локации | `scene_renderer.py:41` | Устаревшие позиции NPC | Frontend |
| BUG-P2-10 | `npc_speech_bubbles` не очищается при выходе | `game_screen.py:367` | Старые облачка при повторном входе | Frontend |
| BUG-P2-11 | Дубликат проверки cache в `life_engine.py` | `life_engine.py:596-603` | Одинаковый код дважды | Backend |
| BUG-P2-12 | J/О переключение конфликтует с TEXTINPUT | `game_screen.py:546` | `event.unicode == 'о'` срабатывает на KeyDown | Frontend Input |
| BUG-P2-13 | `save_scene_state` блокирует основной цикл | `game_screen.py:881-884` | HTTP POST синхронно в main loop | Frontend Perf |
| BUG-P2-14 | `BODY_STATE_HEALTHY` для всех NPC | `game_loop/__init__.py:496-501` | Боль сбрасывается при перезагрузке | Backend |
| BUG-P2-15 | `PerceptionConfig` с хардкод-значениями | `game_screen.py:1191-1196` | `stress=10.0, hp=100` всегда | Frontend |
| BUG-P2-16 | `_build_perceived_scene` каждый кадр | `game_screen.py:1197` | Пересоздание без кэша | Frontend Perf |

### P3 — Низкие (debug spam и полировка) — 12 багов

| ID | Баг | Файл | Симптом | Категория |
|---|---|---|---|---|
| BUG-P3-01 | Debug print в `tick_orchestrator.py` | `tick_orchestrator.py:428` | `print` каждый тик | Backend Debug |
| BUG-P3-02 | Debug print в `life_engine.py` | `life_engine.py:1296` | Хардкод `guard_borko` | Backend Debug |
| BUG-P3-03 | Debug print в `game_screen.py` (50+) | `game_screen.py:766,787,917,862,997-1004` | `[FRAME_RENDER]`, `[TICK_SYNC]`, `[DIAG_MERGE]` spam | Frontend Debug |
| BUG-P3-04 | Debug print в `game_loop/__init__.py` | `game_loop/__init__.py:856,967` | `[TRAV_CHECK_P2]`, `[DIAG_MERGE]` | Backend Debug |
| BUG-P3-05 | Красный fill debug-ассерт | `game_screen.py:1228` | `screen.fill((200,0,0))` каждый кадр | Frontend Debug |
| BUG-P3-06 | `logger.warning` на хот-пути | `integration.py:56,75` | CFRM_P2_SKIP каждый тик | Backend Debug |
| BUG-P3-07 | Хардкод `duration_ticks=2` | `post_decision.py:117` | Все атаки одинаковое окно подготовки | Backend Logic |
| BUG-P3-08 | `move.target_npc_id` сбрасывается после submit | `game_screen.py:665-668` | Игрок не знает об ошибке | Frontend |
| BUG-P3-09 | Фильтр `resp != "Ничего не произошло"` хрупкий | `game_screen.py:1050` | Не учитывает точку/пробелы | Frontend Logic |
| BUG-P3-10 | `_idle_tick_result` как list | `game_screen.py:488` | Потеря результата при гонке потоков | Frontend |
| BUG-P3-11 | `_w2s` не использует zoom | `scene_renderer.py:179` | Несоответствие с editor | Frontend |
| BUG-P3-12 | Приоритет NPC перед стенами | `editor_core.py:1610-1618` | NPC у стены блокирует выделение стены | Map Editor |

**ИТОГО: 58 багов** (12 P0 + 18 P1 + 16 P2 + 12 P3)

---

## 5. Патч Set A — CI/CD Foundation (P0)

### A.1: GitHub Actions workflow

**Файл:** `.github/workflows/test.yml` (новый)

**Требования:**
- Trigger: push на любую ветку + pull request
- Matrix: Python 3.11, 3.12
- OS: ubuntu-latest
- Steps:
  1. Checkout
  2. Setup Python
  3. `pip install -r backend/requirements.txt`
  4. `pip install pymorphy3`
  5. `cd backend && python -m pytest tests/ --tb=short --junitxml=test_results.xml`
  6. Upload test_results.xml as artifact
  7. `python scripts/lint_wall_clock.py`

**Критерий готовности:** push → green checkmark в GitHub.

### A.2: SUPERBOX regression gate

**Файл:** `.github/workflows/superbox.yml` (новый)

**Требования:**
- Trigger: push на `V.0.5.3.*` ветки + manual dispatch
- Steps:
  1. Запуск `python -m tests.sandbox.SUPERBOX.run drift replay_determinism` (timeout 5 min)
  2. Парсинг output на `[DRIFT][D]` / `[DRIFT][C]` / `[DRIFT][E]`
  3. Fail если есть structural drift

### A.3: pytest конфигурация cleanup

**Файлы:** `backend/pytest.ini` + `backend/pyproject.toml`

**Требования:**
- Удалить дублирование конфигурации
- Оставить только `pyproject.toml`
- Добавить `--strict-markers`
- Добавить `--ignore=backend/tests/sandbox/test_causal_bridge_integration.py`
- Исправить `test_spatial_service.py` collection error

**Критерий готовности:** `pytest --collect-only` — 0 errors.

---

## 6. Патч Set B — Code Cleanup (P1)

### B.1: Удаление AppAgent

**Файлы:** удалить `backend/AppAgent/` целиком (12 .py файлов, 1666 строк)

```bash
git rm -r backend/AppAgent/
```

### B.2: pygame в requirements.txt

**Файл:** `backend/requirements.txt`

Добавить `pygame==2.6.1`.

### B.3: Logs в Git (BUG-P1-02)

**Файл:** `.gitignore`

**Было:**
```gitignore
*.log
*.jsonl
backend/data/logs/
```

**Стало:**
```gitignore
# Runtime logs — kept for debugging
!backend/logs/
backend/logs/*.db
backend/logs/*.db-shm
backend/logs/*.db-wal
!backend/data/logs/
backend/data/logs/*.db
```

**Действия:**
1. Распаковать `backend/logs.rar` → `backend/logs/`
2. Создать `backend/logs/.gitkeep`
3. Создать `backend/data/logs/.gitkeep`
4. `git add backend/logs/ backend/data/logs/`
5. Commit

**Критерий готовности:** `git status` показывает файлы в `backend/logs/`.

---

## 7. Патч Set C — Type Safety (P1)

### C.1: mypy configuration

**Файл:** `backend/pyproject.toml`

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
show_error_codes = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false

[[tool.mypy.overrides]]
module = "tests.sandbox.*"
ignore_errors = true
```

### C.2: mypy в CI

**Файл:** `.github/workflows/test.yml`

```yaml
- name: Type check (mypy)
  run: |
    pip install mypy
    cd backend && mypy app/ --strict
```

### C.3: Поэтапное внедрение

1. **Этап 1:** `mypy app/domain/`
2. **Этап 2:** `mypy app/models/`
3. **Этап 3:** `mypy app/services/state/`
4. **Этап 4:** `mypy app/services/npc/`
5. **Этап 5:** `mypy app/services/`
6. **Этап 6:** `mypy app/`

---

## 8. Патч Set D — Legacy NPC Dict Migration (P2)

### D.1: Inventory legacy usage

**Файл:** `docs/audits/ADR-LEGACY-IMPACT.md` (новый)

Задокументировать все 59 точек использования `from_legacy`/`write_to_legacy`/`state.hp`.

### D.2: Этапы миграции

1. Убрать `state.hp` из `state_interpreter.py:216,228`
2. Убрать `state.hp` из `phase_6_avatar.py:86`
3. Убрать `state.hp` из `player_avatar_service.py:249`
4. Пометить `NPCState.hp` как `@deprecated`
5. Через 2 спринта — удалить поле `hp`

**Критерий готовности:** `grep -rn "state\.hp\b" backend/app/` → 0.

---

## 9. Патч Set E — GameLoopBridge Refactor (P2)

### E.1: Eliminate `asyncio.run()` per turn

**Файл:** `frontend/game_loop_bridge.py`

Event loop reuse pattern:
- Один persistent event loop в отдельном потоке
- `asyncio.run_coroutine_threadsafe(coro, loop)` для вызовов

### E.2: Eliminate `_tick_scene` access

**Файл:** `frontend/game_loop_bridge.py:256`

Добавить в `GameLoop` public method:
```python
def apply_changes(self, campaign_id: str, changes: list, scene_state: dict) -> None:
    self.scene_manager.apply_changes(campaign_id, changes, scene_state)
```

**Критерий готовности:** `grep "_loop\.scene_manager\|_loop\._tick_scene" frontend/` → 0.

---

## 10. Патч Set F — QUICKSTART (P1)

### F.1: Архитектурный QUICKSTART документ

**Файл:** `docs/QUICKSTART.md` (новый)

Структура:
1. «Один ход игрока» — end-to-end trace
2. «Карта файлов» — какие файлы читать первыми
3. «Debug triage» — если что-то сломалось
4. «Глоссарий» — 20 ключевых терминов

---

## 11. Патч Set G — Критические баги (P0)

> **Подробные инструкции по исправлению каждого бага — в файле `FIX_GUIDE.md`**

### G.1: Исправление времени (BUG-P0-01)

**Файлы:** `backend/app/core/calendar.py`, `backend/app/services/tick_orchestrator.py`, `backend/app/services/game_loop/scene_init.py`, `frontend/game_screen.py`

**Суть:**
1. `Calendar.advance` не должен обрезать секунды
2. `game_time_seconds` должен гарантированно передаваться в `world_snapshot`
3. Fallback в frontend при отсутствии `game_time_seconds`

### G.2: Исправление движения NPC (BUG-P0-02, BUG-P0-06)

**Файлы:** `backend/app/services/spatial/movement_engine.py`, `frontend/scene_renderer.py`, `frontend/game_screen.py`

**Суть:**
1. Backend всегда отправляет `velocity` в `npc_positions`
2. Frontend lerp-интерполяция в `_draw_npcs` (fallback режим 3)
3. Унификация скорости игрока и NPC (8 м/сек)

### G.3: Исправление "подойди ко мне" (BUG-P0-03)

**Файлы:** `backend/app/services/tick_orchestrator.py`, `backend/app/services/npc/npc_tick_pipeline.py`

**Суть:**
1. Fast Path для target="player" в `_process_player_dm_action`
2. Гарантировать player в `npc_positions` с `local_position`
3. Fallback на `player_spatial` в `_resolve_reactive_movement`

### G.4: Исправление промотки времени (BUG-P0-04, BUG-P1-05)

**Файлы:** `frontend/api_client.py`

**Суть:**
1. Добавить `skip_time` в `HttpGameGateway`
2. Добавить `skip_time` в `DirectGameGateway`
3. Исправить `FallbackGateway.skip_time` (вынести из docstring)

### G.5: Исправление дублирования текста LLM (BUG-P0-05)

**Файлы:** `frontend/game_screen.py`, `backend/app/services/verbalization/response_validator.py`

**Суть:**
1. Фильтр системных маркеров `(whisper)`, `[internal]`, `*thought*`
2. Дедупликация NPC речи (не в message_log если уже в облачке)
3. Усилить валидатор

### G.6: Исправление багов редактора (BUG-P0-07, P0-08, P0-09, P0-11)

**Файлы:** `frontend/map_editor/editor_core.py`, `frontend/map_editor/data_manager.py`

**Суть:**
1. `_point_near_line`: `(py-y1)*(y2-y1)` вместо `(py-y1)*(py-y1)`
2. QUIT: `self._running = False` вместо `running = False`
3. `data_manager.py`: добавить `import logging; logger = logging.getLogger(__name__)`
4. Hex-цвета → RGB tuple в `_draw_passages`

### G.7: Исправление NameError в dm_agent (BUG-P0-10)

**Файл:** `backend/app/agents/dm_agent.py`

Добавить после импортов:
```python
import logging
logger = logging.getLogger(__name__)
```

### G.8: Исправление позиции body state (BUG-P0-12)

**Файл:** `frontend/scene_renderer.py:591`

Заменить `sw` на `sh` (или `self.screen.get_height()`).

---

## 12. Патч Set H — Высокоприоритетные баги (P1)

> **Подробные инструкции — в `FIX_GUIDE.md`**

### H.1: Направление взгляда (BUG-P1-01)

**Суть:**
1. Восстановить клик по NPC (убрать `and False`)
2. Заполнять `inferences` в `_build_perceived_scene`
3. Альтернативный источник — proximity (если NPC в радиусе 5м)

### H.2: Дублирование констант (BUG-P1-03, P1-04)

Удалить дубликаты в `constants.py` и `sprite_registry.py`.

### H.3: Дубликаты в api_client (BUG-P1-05, P1-06)

Исправить `FallbackGateway.skip_time` и `TurnResult.confirmed_location_id`.

### H.4: Парсер спикеров (BUG-P1-07, P1-08, P1-09)

1. Fallback на `npc_id_to_display(npc_id)`
2. Сортировка по длине + проверка первого слова
3. Порог similarity 0.80 вместо 0.60

### H.5: Валидатор 4-й стены (BUG-P1-10)

Уточнить паттерны, использовать word boundaries.

### H.6: TEXTINPUT фильтрация (BUG-P1-11)

Расширить `_WASD_KEY_TEXT` для русской раскладки.

### H.7: Редактор (BUG-P1-12, P1-13, P1-14, P1-15, P1-17, P1-18)

1. Включить `_draw_nodes()` в `_draw_local()`
2. Реализовать `_show_view_menu()` или переименовать
3. Убрать `and False` для клика мыши
4. Реализовать `PgUp/PgDn` для смены этажа
5. Удалить `_select_at` (мёртвый код)
6. Убрать хардкод "Open_road"

### H.8: text_input infect (BUG-P1-16)

Добавить `self._focused = True` в `infect()`.

---

## 13. Патч Set I — Средние баги (P2)

> **Подробные инструкции — в `FIX_GUIDE.md`**

- BUG-P2-01: Удалить дубликат `self.current_z`
- BUG-P2-02: Кэшировать шрифт `font_tooltip` в `__init__`
- BUG-P2-03: Кэшировать `format_world_date`
- BUG-P2-04: Удалить мёртвый код после `return`
- BUG-P2-05, P2-06: Заменить тела Protocol на `...`
- BUG-P2-07, P2-08: Удалить неиспользуемые переменные
- BUG-P2-09: Очищать `_prev_npc_positions` при смене локации
- BUG-P2-10: Очищать `npc_speech_bubbles` при выходе
- BUG-P2-11: Удалить дубликат проверки cache
- BUG-P2-12: Убрать `event.unicode == 'о'`
- BUG-P2-13: Вынести `save_scene_state` в отдельный поток
- BUG-P2-14: Проверять persistence перед инъекцией HEALTHY
- BUG-P2-15: Читать stress/hp из `avatar_state`
- BUG-P2-16: Кэшировать PerceivedScene с хэшем scene_state

---

## 14. Патч Set J — Низкоприоритетные баги (P3)

> **Подробные инструкции — в `FIX_GUIDE.md`**

- BUG-P3-01 — P3-06: Заменить все `print` на `logger.debug` с throttling
- BUG-P3-07: Вынести `duration_ticks` в конфиг оружия
- BUG-P3-08: Сохранять цель до подтверждения от backend
- BUG-P3-09: Нормализовать перед сравнением
- BUG-P3-10: Использовать `threading.Lock` для `_idle_tick_result`
- BUG-P3-11: Документировать отсутствие zoom
- BUG-P3-12: Alt+клик для принудительного выделения стены

---

## 15. Сводная таблица ТЗ

| Патч | Приоритет | Время (сессии) | Зависимости |
|---|---|---|---|
| A.1 GitHub Actions test | P0 | 1 | — |
| A.2 SUPERBOX gate | P0 | 1 | A.1 |
| A.3 pytest config cleanup | P0 | 1 | — |
| B.1 Удалить AppAgent | P1 | 0.5 | — |
| B.2 pygame в requirements | P1 | 0.1 | — |
| B.3 Logs в Git | P1 | 0.5 | — |
| C.1 mypy config | P1 | 0.5 | — |
| C.2 mypy в CI | P1 | 0.5 | C.1, A.1 |
| C.3 mypy поэтапно | P2 | 3-5 | C.1 |
| D.1 Legacy inventory | P2 | 1 | — |
| D.2 Legacy миграция | P2 | 3-5 | D.1 |
| E.1 asyncio.run refactor | P2 | 2 | — |
| E.2 _tick_scene encapsulation | P2 | 1 | — |
| F.1 QUICKSTART doc | P1 | 2 | — |
| **G.1-G.8 Критические баги** | **P0** | **3-4** | — |
| **H.1-H.8 Высокие баги** | **P1** | **3-4** | G.* |
| **I.* Средние баги** | **P2** | **2-3** | — |
| **J.* Низкие баги** | **P3** | **1-2** | — |

**Итого:** ~25-30 сессий = ~4-5 недель при темпе 6 сессий/неделю.

---

## 16. Порядок внедрения

### Спринт S98 (P0 Infrastructure, 3-4 сессии)

1. A.1 + A.2 + A.3 — CI/CD foundation
2. B.1 + B.2 + B.3 — cleanup (включая Logs в Git)
3. Запустить CI → зафиксировать baseline

### Спринт S99 (P0 Bug Fixes, 3-4 сессии)

4. **G.1** — Время (BUG-P0-01)
5. **G.4** — Промотка времени (BUG-P0-04)
6. **G.3** — "Подойди ко мне" (BUG-P0-03)
7. **G.2** — NPC движение + lerp (BUG-P0-02, P0-06)
8. **G.5** — Дублирование текста LLM (BUG-P0-05)
9. **G.6** — Баги редактора (BUG-P0-07, P0-08, P0-09, P0-11)
10. **G.7** — NameError dm_agent (BUG-P0-10)
11. **G.8** — Позиция body state (BUG-P0-12)

### Спринт S100 (P1, 4-5 сессий)

12. C.1 + C.2 — mypy config + CI
13. F.1 — QUICKSTART документ
14. **H.1** — Направление взгляда (BUG-P1-01)
15. **H.2-H.8** — Остальные P1 баги

### Спринт S101+ (P2-P3, параллельно)

16. D.1 + D.2 — Legacy миграция
17. E.1 + E.2 — GameLoopBridge refactor
18. C.3 — mypy на остальной код
19. **I.*** — Средние баги
20. **J.*** — Низкие баги

---

## 17. Критерии готовности

### S98 (P0 Infra)

- [ ] `.github/workflows/test.yml` существует и green
- [ ] `.github/workflows/superbox.yml` существует
- [ ] `pytest --collect-only` — 0 errors
- [ ] `backend/AppAgent/` удалён
- [ ] `pygame==2.6.1` в `requirements.txt`
- [ ] `backend/logs/` в Git (BUG-P1-02 закрыт)

### S99 (P0 Bugs)

- [ ] Время идёт: 60 idle_tick → +60 минут игрового времени (BUG-P0-01)
- [ ] Кнопки 1–4 проматывают время (BUG-P0-04)
- [ ] "Подойди ко мне" двигает NPC (BUG-P0-03)
- [ ] NPC плавно движутся без телепортации (BUG-P0-02, P0-06)
- [ ] DM ответ без `(whisper)`, `[internal]` (BUG-P0-05)
- [ ] Клик по стене выделяет стену (BUG-P0-07)
- [ ] Закрытие окна редактора через крестик (BUG-P0-08)
- [ ] Проходы рисуются в редакторе (BUG-P0-11)
- [ ] Body state виден в правильной позиции (BUG-P0-12)

### S100 (P1)

- [ ] `mypy app/domain/` — 0 errors
- [ ] `docs/QUICKSTART.md` существует
- [ ] Направление взгляда работает (BUG-P1-01)
- [ ] Нет дублирования констант (BUG-P1-03, P1-04)
- [ ] `skip_time` работает во всех gateway (BUG-P1-05)

### S101+ (P2-P3)

- [ ] `grep -rn "state\.hp\b" backend/app/` → 0
- [ ] `grep "_loop\.scene_manager" frontend/` → 0
- [ ] Нет `print` spam в stdout при игре (BUG-P3-01 — P3-06)
- [ ] Все P2/P3 баги закрыты

---

## 18. Связанные документы

- `docs/Диаграммы игры/FIX_GUIDE.md` — **Инструкция по починке игры** (подробные шаги для каждого бага)
- `docs/audits/ADR-DRIFT-D` — Causal Drift D
- `docs/audits/ADR-LEGACY-IMPACT.md` — Legacy inventory
- `docs/QUICKSTART.md` — архитектурный QUICKSTART
- `docs/Tasks/ТЗ/03_KNOWN_ISSUES_AND_BUGS.md` — баг-реестр
- `reports/LAST_SESSION.md` — текущее состояние симуляции

---

## 19. ADR-PRE-FLIGHT CHECKLIST

Перед внедрением каждого патча:

- [ ] PIPELINE_OBJECT определён
- [ ] OWNER определён
- [ ] CREATE → READ → TRANSFORM → APPLY → COMMIT → PROJECT реконструирован
- [ ] Single Source of Truth проверен
- [ ] Ownership boundaries проверены
- [ ] DTO и runtime contracts проверены
- [ ] FAIL_STAGE идентифицирован
- [ ] H1/H2/H3 с confidence построены
- [ ] FIX_SCOPE выбран минимальным
- [ ] Документы обновлены
- [ ] Локальные тесты/SUPERBOX пройдены
- [ ] Commit на named branch

---

**TZ-INFRA-1 v2.0 готов к внедрению.**

Начать с S98: A.1 → A.3 → B.1 → B.2 → B.3 → A.2 → S99: G.1-G.8 → S100: H.1-H.8 → S101+: I.*, J.*
