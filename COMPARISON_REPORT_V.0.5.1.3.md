# Отчёт сравнения: V.0.5.1.3_Встроил_Кратковременную_память vs V.0.5.1.2_Встроил_ПАМЯТЬ_0.1и0.2

## Сводка

| Метрика | Значение |
|---------|----------|
| **Файлов изменено** | 32 (+ 3 новых) |
| **Строк добавлено** | +2 858 |
| **Строк удалено** | −309 |
| **Чистый прирост** | +2 549 строк |
| **Новые файлы** | `dialogue_session.py`, `location_templates.json`, `TODO.md` |

---

## Что было добавлено

### 1. Кратковременная память диалога (STM) — ФАЗА 0
**Файл:** `backend/app/services/memory/dialogue_session.py` (новый, 90 строк)

- Буфер последних **5 реплик** в RAM (не персистится)
- Ключ: `campaign_id:npc_id:session`
- **Keyword-based topic detection** (без LLM): подвал, гильдия, торговля, страж и т.д.
- **Emotional markers** для передачи в LLM-промпт
- Метод `to_prompt_block()` — текстуализация для контекста агента

### 2. Переработка игрового времени
**Файлы:** `game_loop.py`, `game_screen.py`, `constants.py`, `settings_dm.py`

- `game_time_minutes` → `game_time_seconds` (более точная гранулярность)
- **Диалог:** время = базовое + длина ввода игрока × `TIME_DIALOG_PER_CHAR` (скорость речи NPC ~10 симв/с), с `TIME_DIALOG_MAX` капом
- **Ходьба:** накопительное расстояние (метры) → точный расчёт времени через `walk_distance_accumulated`

### 3. Живая память NPC — ФАЗА 1
**Файлы:** `memory_manager.py`, `game_loop.py`, `npc_state.py`

- `MemoryManager.create_event_memory()` теперь принимает `importance` как параметр (переопределение для значимых событий)
- **Whitelist социальных интентов:** TALK, TRADE, HELP, ATTACK, FLEE, GIVE, ASK, THREATEN
- **NPC-NPC взаимодействия:** записываются с importance = 0.6 (формат: "Актор → Цель: Интент")
- **Player-NPC:** базовая важность по типу интента + emotion_boost (до +30% от emotion_delta)
- `narrative_cache` теперь передаётся как `narrative_hints` в verbalization context

### 4. Улучшения Telegraph / Idle Tick
**Файлы:** `game_screen.py`, `game_loop.py`

- **Cooldown телеграфов:** 30 секунд между событиями (`_TELEGRAPH_COOLDOWN_MS`)
- Фильтрация только **proactive** событий (`cause == "idle_pressure"`)
- **NPC name mapping** из конфигов (`config/npc/individuals/*.json`)
- Исправление: NPC не двигаются во время диалога (интервал 30 сек при `text_input.focused`)
- Пауза idle tick после получения ответа DM (+1 сек)

### 5. Verbalization / DM Pipeline
**Файлы:** `scene_outcome_builder.py`, `dm_contract_builder.py`, `verbalization_context.py`, `context_builder.py`, `dm_agent.py`

- `SceneOutcomeBuilder` теперь получает `_npc_profiles` (voice_profile, backstory, author_notes, gender)
- Передача `profile_l0` в NPC-контексты для DM агента
- `author_notes` и `gender` добавлены в verbalization context
- `raw_scene_events` накапливаются в `scene_state` (cross-tick восприятие, лимит 30)

### 6. API и Constants
**Файлы:** `api_client.py`, `routes.py`, `constants.py`

- Новые константы времени: `TIME_DIALOG_BASE`, `TIME_DIALOG_PER_CHAR`, `TIME_DIALOG_MAX`
- `api_client.py`: значительный рефакторинг (+87/−... строк)
- `routes.py`: обновление endpoint'ов

### 7. Данные и локации
- Новый файл: `backend/data/locations/location_templates.json`
- Обновлены логи (`enigma_20260425.jsonl`, `scene_changes_20260425.jsonl`)
- Обновлены campaign/session/world memory для кампании Open_road
- Обновлен `lusya.json` (конфиг NPC)

---

## Что было изменено / улучшено

| Файл | Изменения |
|------|-----------|
| `backend/game_loop.py` | +138/−... — время, память, idle tick, NPC loading |
| `backend/game_screen.py` | +73/−... — время ходьбы, телеграфы, name mapping |
| `backend/api_client.py` | +87/−... — рефакторинг клиента |
| `backend/app/services/verbalization/scene_outcome_builder.py` | +56/−... — npc_profiles, voice constraints |
| `saves/Open_road/npc_runtime.json` | +557/−... — обновлённые runtime-данные NPC |
| `backend/data/logs/enigma_20260425.jsonl` | +496 строк — новые логи сессий |
| `backend/data/logs/scene_changes_20260425.jsonl` | +789 строк — логи изменений сцен |

---

## Что было убрано / не используется

- Жёсткий список `_memorable_types` в `game_loop.py` — заменён на гибкую систему whitelist интентов + расчёт importance
- Прямой вызов `_load_npcs_with_runtime()` внутри цикла NPC — оптимизирован на единую загрузку
- Константное `TIME_DELTA_DIALOG` — заменено на динамический расчёт от длины ввода

---

## Объём проделанной работы

1. **Архитектура памяти:** Реализована ФАЗА 0 STM (кратковременная память) + расширена ФАЗА 1 долгосрочная память NPC
2. **Система времени:** Полный переход с минут на секунды, динамический расчёт времени диалога и ходьбы
3. **NPC когниция:** NPC теперь запоминают ВСЕ социальные взаимодействия (не только боевые), с взвешенной важностью
4. **Game Screen:** Telegraph cooldown, name mapping, корректная обработка idle tick во время диалога
5. **Verbalization Pipeline:** Полноценная передача профилей NPC (голос, предыстория, авторские заметки) в DM контекст
6. **Данные:** Накоплены новые сессионные логи и обновлены runtime-состояния

**Итого:** ~2 500+ строк нового/изменённого кода, 35 файлов, введение STM-модуля, переработка времени и памяти NPC.

