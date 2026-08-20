# ADR-S82.0 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-S82.0` [STANDARD] **IMPACT**

﻿# ADR-S82.0 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-S82.0` [STANDARD] **IMPACT**
# ADR-S82.0 Impact Audit: Spatial Authority Contract

> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`
> **Актуализация:** S82 построил Spatial Reconciliation Loop — backend = deterministic oracle, frontend = sensor + physics.

---

## 1. Changed Domains

- **spatial** (SpatialRegistry: новый метод get_or_load(), кеш, версионирование)
- **api** (routes.py: Spatial Oracle logic, новое поле confirmed_location_id в response)
- **movement** (game_screen.py: _last_world_pos closure, world_x/y в API calls)
- **transport** (api_client.py: world_x/y через всю цепочку — 7 точек изменений)
- **dto** (schemas.py: ChatTurnRequest.world_position, GameActionResponse.confirmed_location_id)
- **bridge** (game_loop_bridge.py: world_x/y в turn(), oracle для Direct path)

---

## 2. Downstream Consumers

### 2.1 Первичные (точки внедрения)

| Потребитель | Что читает | Изменение |
|-------------|------------|-----------|
| `routes.py` | `request.get("world_x")`, `request.get("world_y")` | Новый spatial oracle path |
| `game_screen.py` | `result.response.confirmed_location_id` | Reconciliation loop |
| `SpatialRegistry` | `_registry_cache`, `get_or_load()` | Cached oracle с версионированием |

### 2.2 Вторичные (потребляют результат)

| Потребитель | Что читает | Влияние S82 |
|-------------|------------|-------------|
| `scene_state_manager` | `location_id` из ChatTurnRequest | Теперь authoritatively установлен oracle |
| `campaign_state.metadata["current_location"]` | Пишется routes.py | Самоисцеляющийся — обновляется при каждом API вызове |
| `game_loop` | `ChatTurnRequest.location` | Авторитетный — вычислен из world_position |
| `WorldSnapshotBuilder` | `location_id` из scene_state | Косвенно — через корректный location_id |
| `LifeEngine` | `location_id` для spatial service | Косвенно — правильный граф загружается |
| `NPC tick pipeline` | `location_id` для graph compilation | Косвенно — NPC в правильной локации |

### 2.3 Критическое ограничение

> Backend ВСЕГДА пересчитывает chunk из raw world_position. Никогда не доверяет prediction.
> Единственный канал пространственной истины: world_x/y → SpatialRegistry.find_chunks()

---

## 3. Runtime Impact

| Метрика | Значение | Примечание |
|---------|----------|------------|
| RAM: _registry_cache | +~5KB per campaign | Один SpatialRegistry в памяти, ключ = (registry, mtime) |
| Latency: oracle lookup | +0.1ms per API request | find_chunks() = O(N) по чанкам, N≤10 |
| Latency: cache hit | +0.01ms | dict lookup по campaign_id |
| Latency: cache miss | +5-10ms | JSON load + parse |
| Network: request size | +~40 bytes | Два float поля world_x, world_y |
| Network: response size | +~30 bytes | Поле confirmed_location_id |
| Tick impact | 0 | Oracle работает per-request, не per-tick |

---

## 4. Sandbox Tests

### 4.1 Spatial Registry Tests

| Тест | Что проверяет |
|------|---------------|
| `test_spatial_registry_find_chunks_tavern` | (5,5) → tavern_silver_wolf |
| `test_spatial_registry_find_chunks_city_gate` | (25,5) → city_gate |
| `test_spatial_registry_find_chunks_overlap` | (20,5) → city_gate + tavern (overlap zone) |
| `test_spatial_registry_get_or_load_caches` | Повторный вызов возвращает тот же объект |
| `test_spatial_registry_cache_invalidates_on_mtime` | При изменении файла кеш сбрасывается |
| `test_spatial_registry_get_or_load_returns_none_for_missing` | Несуществующая кампания → None |

### 4.2 API Contract Tests

| Тест | Что проверяет |
|------|---------------|
| `test_game_action_accepts_world_position` | POST /api/game/action с world_x/y |
| `test_spatial_oracle_updates_location` | world_position в city_gate → location=city_gate |
| `test_spatial_oracle_returns_confirmed_location_id` | Response содержит confirmed_location_id |
| `test_spatial_oracle_fallback_on_missing_registry` | Нет артефакта → использует saved location |
| `test_spatial_oracle_outside_all_chunks` | world_position за пределами → warning, saved location |

### 4.3 Reconciliation Tests

| Тест | Что проверяет |
|------|---------------|
| `test_confirmed_location_id_updates_scene_state` | confirmed ≠ current → scene_state updated |
| `test_confirmed_location_id_same_no_update` | confirmed == current → no change |
| `test_confirmed_location_id_none_no_update` | None → no change |

---

## 5. Rollback

1. Убрать `world_position` из `ChatTurnRequest`
2. Убрать oracle logic из `routes.py` (вернуть frozen metadata path)
3. Убрать `confirmed_location_id` из response
4. Убрать `world_x/y` из `_PendingAction` и всей api_client chain
5. Убрать `_last_world_pos` closure из game_screen.py
6. Убрать `get_or_load()` и `_registry_cache` из SpatialRegistry
7. Убрать `world_x/y` из game_loop_bridge.py

Все изменения изолированы — rollback не ломает S81 (Coordinate Truth).

---

## 6. Architectural Invariants Established

| # | Инвариант | Критичность |
|---|-----------|-------------|
| S82-I1 | Backend ВСЕГДА пересчитывает chunk из world_position | КРИТИЧЕСКИЙ |
| S82-I2 | Frontend НИКОГДА не пишет location_id напрямую (кроме reconciliation) | КРИТИЧЕСКИЙ |
| S82-I3 | world_position = PRIMARY spatial input. player_position = LEGACY | ВЫСОКИЙ |
| S82-I4 | (0,0) — валидная координата. Проверять is not None, не != 0 | ВЫСОКИЙ |
| S82-I5 | predicted_chunk_id НЕ существует в API контракте | ВЫСОКИЙ |
| S82-I6 | SpatialRegistry кеш версионируется по mtime | СРЕДНИЙ |
| S82-I7 | Backend НИКОГДА не перемещает игрока | КРИТИЧЕСКИЙ |

---

## 7. Taboos (added by S82)

| # | Запрет | Причина |
|---|--------|---------|
| 308 | Frontend пишет scene_state["location_id"] напрямую (кроме reconciliation) | Нарушение ownership |
| 309 | Backend доверяет frontend prediction без пересчёта | Деградация к trust-based модели |
| 310 | predicted_chunk_id в API контракте | Второй голос интерпретации мира |
| 311 | world_x != 0.0 как sentinel check | (0,0) — валидная координата |
| 312 | SpatialRegistry.load() на каждый API запрос | IO-per-request |
| 313 | Кеш реестра без версионирования | Stale geometry после пересборки |
| 314 | player_position используется для spatial logic | LEGACY, world_position = PRIMARY |

---

*Версия: 1.0*
*Дата: 2026-05-27*
*Автор: S82 (преемник S81)*


Files: N/A
