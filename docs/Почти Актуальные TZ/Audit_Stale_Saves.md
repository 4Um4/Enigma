# Аудит сохранений и кампаний — что удалить

**Дата аудита:** 2026-07-18  
**Источник:** `/home/z/my-project/upload/Enigma-V.0.5.3.4.8_drift.zip`

## Признайте сначала

Вы были правы по обоим пунктам:

1. **`docs/` — это идея, не проект.** Я ошибочно защищал проект на основе документации. 110+ ADR-файлов не делают игру рабочей — это просто описание того, как она **должна** работать.

2. **`campaign_memory_Open_road.jsonl`, который я анализировал — апрельские логи.** Реальные даты внутри файла: `2026-04-18` … `2026-04-25`. Это данные сессий **трёхмесячной давности**, которые вообще не отражают текущее состояние игры. Все мои выводы про "китайский язык", "подsciousное", "Борко у ворот" — это **анализ ghosts of the past**, не актуальной системы.

---

## Реальная ситуация

### Когда что использовалось

| Период | Что активно | Где видно |
|---|---|---|
| **2026-04-18 — 2026-04-28** | Игрок "Демеург" играл в кампанию Open_road через старую версию (с Mock-провайдером, потом qwen_7b) | `data/campaign_memory_Open_road.jsonl`, `data/session_memory_Open_road.jsonl`, `data/world_hidden_events_manual.jsonl` |
| **2026-06-09 — 2026-06-13** | Редактировалась карта Open_road, добавлены `city_gate`, `market_square`. Создана `my_cam` (06-09). Скомпилирован `spatial_registry.json` (06-13). | `frontend/map_editor/campaigns/Open_road/compiled/spatial_registry.json` (compiled_at=2026-06-13) |
| **2026-07-17 — 2026-07-18** | Активная разработка. Запускались cds_session. При старте игры **Open_road полностью сбрасывается** (см. `cds_session_20260718_121932.log` — `[NEW_GAME] Campaign 'Open_road' fully reset`). | `backend/logs/cds_session_*.log` (17 сессий за 2 дня) |

### Что подтверждено логами

В `cds_session_20260718_121932.log` (последняя сессия) видно:

```
2026-07-18 12:19:42 [SQLITE_PERSISTENCE] Campaign deleted: Open_road
2026-07-18 12:19:42 [NEW_GAME] SQLite cleared for 'Open_road'
2026-07-18 12:19:42 [NEW_GAME] Removed: .../saves/Open_road/campaign_state.json
2026-07-18 12:19:42 [NEW_GAME] Removed: .../saves/Open_road/player_avatar.json
2026-07-18 12:19:42 [NEW_GAME] Removed: .../saves/Open_road/npc_relationships.json
2026-07-18 12:19:42 [NEW_GAME] Removed: .../saves/Open_road/campaign_meta.json
2026-07-18 12:19:42 [NEW_GAME] Campaign 'Open_road' fully reset. Removed: ['sqlite:scene+runtime', 'campaign_state.json', 'player_avatar.json', 'npc_relationships.json', 'campaign_meta.json', 'sqlite:memories(56)']
```

**Это значит:** при старте игры `Open_road` — это **кампания-песочница**, которая полностью пересоздаётся. Сохранения в `saves/Open_road/` — это `tick=0`, **пустое стартовое состояние** после последнего сброса.

---

## Полный список устаревших файлов

### Категория A — Апрельские игровые сессии (то, что я по ошибке анализировал)

**Возраст:** 3 месяца. **Реальное игровое состояние тех сессий** — игрок "Демеург", который печатал "выыыыыыыыыыыыыыыыыыыф" и проверял работу. **Никакой ценности**, только шум.

| Файл | Размер | Внутренние даты | Что внутри | Статус |
|---|---|---|---|---|
| `data/campaign_memory_Open_road.jsonl` | 53 KB / 80 строк | 2026-04-18 → 2026-04-25 | DM-ответы с китайским языком, англо-русскими гибридами, обрывами | **УДАЛИТЬ** |
| `data/session_memory_Open_road.jsonl` | 113 KB / 283 строк | 2026-04-18 → 2026-04-27 | Action events игрока "Демеург", дублированные 4× для всех NPC | **УДАЛИТЬ** |
| `data/world_hidden_events_manual.jsonl` | 4.4 KB / 33 строк | 2026-04-18 → 2026-04-28 | Пустые hidden events (все `"events": []`) | **УДАЛИТЬ** |
| `data/session_memory_Open_road` | 0 bytes | — | Пустой файл (без расширения) — артефакт | **УДАЛИТЬ** |

### Категория B — Устаревшие сохранения кампаний

**Возраст:** все сброшены при последнем старте. tick=0, данных нет.

| Файл | Что внутри | Статус |
|---|---|---|
| `saves/Open_road/campaign_state.json` | tick=0, location=tavern_silver_wolf, 6 NPC — **стартовое состояние после сброса** | **УДАЛИТЬ** (будет пересоздано) |
| `saves/Open_road/character_profiles.json` | 3 профиля, главный = "Демеург" (апрельский персонаж) | **УДАЛИТЬ** |
| `saves/Open_road/characters.json` | Апрельский персонаж "Демеург" | **УДАЛИТЬ** |
| `saves/my_cam/campaign_state.json` | tick=0, location=пусто, 6 NPC | **УДАЛИТЬ** (my_cam — тестовая кампания 2026-04-18) |
| `saves/my_cam/character_profiles.json` | 1 профиль "Михаил" (старый) | **УДАЛИТЬ** |
| `saves/my_cam/characters.json` | "Михаил" | **УДАЛИТЬ** |

### Категория C — Дублирующиеся/мёртвые директории

| Файл/директория | Что это | Статус |
|---|---|---|
| `saves/my_cam/` целиком | Тестовая кампания 2026-04-18, не используется | **УДАЛИТЬ ЦЕЛИКОМ** |
| `backend/saves/` (пустая) | Пустая директория | **УДАЛИТЬ** |
| `data/campaign_Open_road/npc_relationships.json` | Дубликат (оригинал в saves/, и есть SQLite) | **УДАЛИТЬ** |
| `data/campaign_tavern_silver_wolf/npc_relationships.json` | Старая кампания, не существует в редакторе (нет в `frontend/map_editor/campaigns/`) | **УДАЛИТЬ** |
| `data/campaigns/Open_road/campaign_state.json` | Старый формат `metadata: {}` — не используется кодом (json_persistence_adapter использует `saves/`) | **УДАЛИТЬ** |
| `data/locations/` (пустая) | Создана 05:52 (после распаковки) — пустая, leftover | **УДАЛИТЬ** |
| `backend/data/campaigns/test/campaign_state.json` | Тестовое сохранение, tick=0, 4 NPC — sandbox тест | **УДАЛИТЬ** |
| `backend/data/campaigns/test_campaign/campaign_state.json` | Тестовое сохранение, tick=10, 1 NPC (`npc_1`) — sandbox тест | **УДАЛИТЬ** |
| `backend/test_data/campaign_test_campaign/npc_relationships.json` | Тестовые данные, NPC "npc_1" — не игровой | **УДАЛИТЬ** |

### Категория D — Устаревшие тестовые кампании в редакторе

| Директория | Что внутри | Статус |
|---|---|---|
| `frontend/map_editor/campaigns/my_cam/` целиком | Создана 2026-04-18, последний modified_at=2026-06-09. **Нет в логах использования** (в `cds_session` только `Open_road`) | **УДАЛИТЬ ЦЕЛИКОМ** |
| `frontend/map_editor/campaigns/default/` | Содержит `tavern.json` и `tavern_silver_wolf.json`. `tavern_silver_wolf.json` — **битый UTF-8 BOM**. `tavern.json` — дубликат my_cam | **УДАЛИТЬ ЦЕЛИКОМ** |
| `frontend/map_editor/campaigns/tavern.json` (файл в корне campaigns/) | Дубликат `default/locations/tavern.json` (md5 идентичен) | **УДАЛИТЬ** |

### Категория E — Устаревшие/мёртвые файлы в корне

| Файл | Что это | Статус |
|---|---|---|
| `backend/config.json.deprecated` | Уже deprecated — явно помечен | **УДАЛИТЬ** |
| `backend/test_localsystem.txt` | Заметка про "странник как интерфейс" — draft | **УДАЛИТЬ** (или перенести в `docs/Почти Актуальные TZ/`) |

### Категория F — Старые логи (опционально)

| Директория | Размер | Даты | Статус |
|---|---|---|---|
| `backend/data/logs/scene_changes_20260702-16.jsonl` | ~85 MB суммарно | 2026-07-02 → 2026-07-16 | **УДАЛИТЬ ВСЕ КРОМЕ 20260718** (последний оставлен для аудита) |
| `backend/data/logs/enigma_20260702-16.jsonl` | ~6 MB | 2026-07-02 → 2026-07-16 | **УДАЛИТЬ ВСЕ КРОМЕ 20260717** |

---

## Что НЕ удалять (это актуальное)

### Категория G — Активная кампания

| Файл/директория | Почему оставить |
|---|---|
| `frontend/map_editor/campaigns/Open_road/` | **Единственная активная кампания**. spatial_registry compiled_at=2026-06-13. Используется в логах 2026-07-18 (`[SCENE] Campaign 'Open_road' reinitialized from editor`). |
| `frontend/map_editor/campaigns/Open_road/locations/tavern.json` | Актуальная локация `tavern_silver_wolf` |
| `frontend/map_editor/campaigns/Open_road/locations/city_gate.json` | Актуальная локация `city_gate` |
| `frontend/map_editor/campaigns/Open_road/locations/market_square.json` | Актуальная локация `market_square` |
| `frontend/map_editor/campaigns/Open_road/compiled/spatial_registry.json` | Скомпилированный реестр (compiled_at=2026-06-13) |

### Категория H — Конфиг NPCs (это данные, не сохранения)

| Файл | Почему оставить |
|---|---|
| `config/npc/individuals/*.json` (6 файлов) | Конфигурация NPC — это **данные игры**, не состояние сессии. lusya, borko, shadow, tornin, goran, orm — все используются. |
| `config/world/factions.json` | Конфиг фракций |
| `config/npc/social/village_relations.json` | Конфиг социальных связей |

### Категория I — Свежие логи

| Файл | Почему оставить |
|---|---|
| `backend/data/logs/scene_changes_20260718.jsonl` | Последний активный лог (mtime 05:55) |
| `backend/data/logs/enigma_20260717.jsonl` | Последний лог LLM-провайдера |
| `backend/data/logs/combat_log.jsonl` | Активный combat log (даты до 2026-07-18 12:22) |
| `backend/logs/cds_session_20260718_*.log` | Все сессии 18 июля — для аудита |
| `backend/logs/cds_session_20260717_*.log` | Все сессии 17 июля — для аудита |

---

## Сводка для удаления

| Категория | Кол-во файлов | Объём |
|---|---|---|
| A. Апрельские игровые сессии | 4 | ~170 KB |
| B. Устаревшие сохранения | 6 | ~? (маленькие JSON) |
| C. Дублирующиеся директории | 8 файлов + 3 папки | ~50 KB |
| D. Устаревшие редакторные кампании | 3 папки + 1 файл | ~70 KB |
| E. Мёртвые файлы в корне | 2 | ~? |
| F. Старые логи (опционально) | ~30 | ~90 MB |
| **ИТОГО** | **~53 файла + 6 папок** | **~90 MB** |

---

## Команды удаления (для подтверждения перед выполнением)

```bash
cd /home/z/my-project/work/Enigma-V.0.5.3.4.8_drift

# Категория A — Апрельские игровые сессии
rm -f data/campaign_memory_Open_road.jsonl
rm -f data/session_memory_Open_road.jsonl
rm -f data/world_hidden_events_manual.jsonl
rm -f data/session_memory_Open_road  # пустой файл без расширения

# Категория B — Устаревшие сохранения
rm -f saves/Open_road/campaign_state.json
rm -f saves/Open_road/character_profiles.json
rm -f saves/Open_road/characters.json
rm -rf saves/my_cam/

# Категория C — Дублирующиеся директории
rm -rf backend/saves/  # пустая
rm -rf data/campaign_Open_road/
rm -rf data/campaign_tavern_silver_wolf/
rm -rf data/campaigns/  # содержит только один устаревший campaign_state.json
rm -rf data/locations/  # пустая
rm -rf backend/data/campaigns/test/
rm -rf backend/data/campaigns/test_campaign/
rm -rf backend/test_data/campaign_test_campaign/

# Категория D — Устаревшие редакторные кампании
rm -rf frontend/map_editor/campaigns/my_cam/
rm -rf frontend/map_editor/campaigns/default/
rm -f frontend/map_editor/campaigns/tavern.json  # дубликат

# Категория E — Мёртвые файлы в корне
rm -f backend/config.json.deprecated
rm -f backend/test_localsystem.txt

# Категория F — Старые логи (опционально — оставить только 20260717 и 20260718)
rm -f backend/data/logs/scene_changes_2026070{2,3,4,5,6}.jsonl
rm -f backend/data/logs/scene_changes_2026071{0,1,2,3,4,5,6}.jsonl
rm -f backend/data/logs/enigma_2026070{2,3,4,5,6}.jsonl
rm -f backend/data/logs/enigma_2026071{0,1,2,3,4,5,6}.jsonl
```

**Примечание:** После удаления нужно проверить, что `backend/test_data/` не используется тестами. Если используется — восстановить `campaign_test_campaign/npc_relationships.json` из git или переписать тесты.

---

## После очистки — что делать

1. **Запустить игру заново** — `Open_road` создаст свежие `saves/Open_road/` с `tick=0`, чистым SQLite, без апрельского мусора
2. **Проверить, что `my_cam` нигде не упоминается в коде** — `rg "my_cam" backend/ frontend/` должен вернуть пустоту
3. **Проверить, что `test_campaign` не используется тестами** — `rg "test_campaign" backend/tests/` должен вернуть пустоту
4. **Обновить README/QUICKSTART** — указать, что `Open_road` — единственная каноническая кампания
5. **Зафиксировать в ADR-O-327**: "Single Campaign Authority — в проекте существует только одна кампания `Open_road`. Все остальные (`my_cam`, `default`, `test`, `test_campaign`) — устаревшие и удалены. Создание новых кампаний только через map_editor."

---

## Извинение

Извините за некорректный анализ в прошлый раз. Я взял апрельский лог 3-месячной давности и сделал из него выводы о текущем состоянии игры. Это моя ошибка — нужно было сначала проверить **внутренние timestampы** файлов, а не их mtime (которые все 2026-07-18 из-за распаковки zip).

Реальное состояние игры сейчас — это `cds_session_20260718_121932.log` (последняя сессия), где:
- Open_road сбрасывается и инициализируется заново
- 6 NPC появляются на стартовых позициях
- DialogueExecutor работает через qwen_7b
- За 2 минуты игры — 0 EQUIVALENCE_VIOLATION, 35 DRIFT

Это и есть актуальная картина. Апрельские "китайские реплики" — не текущая проблема, а исторический артефакт.

---

*Аудит сохранён в `/home/z/my-project/download/Audit_Stale_Saves.md`*
