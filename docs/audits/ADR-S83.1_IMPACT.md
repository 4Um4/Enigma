# ADR-S83.1 Impact Audit: Tick = Pure Function Evaluation

> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs\Tasks\ADR (Architecture Decision Records).md`
> **Актуализация:** S83.1 — переход от reactive mutation к functional evaluation внутри тика.

---

## 1. Changed Domains

- **spatial** (scene_state: mutable dict → frozen snapshot)
- **npc/movement** (all_npcs_raw: shared reference → deepcopy)
- **tick** (TickOrchestrator.execute: process model → pure function model)
- **persistence** (apply_changes: mid-tick persist → single commit boundary)
- **memory** (LifeEngine._npc_cache: shallow copy → deepcopy isolation)

### Что изменила археология S83.1 в этих доменах:

| Домен | До S83.1 | После S83.1 |
|-------|----------|-------------|
| tick | `execute()` мутирует scene_state по ссылке | `execute()` работает от frozen snapshot |
| npc | `all_npcs_raw = npc_states` (same ref) | `all_npcs_raw = deepcopy(npc_states)` |
| spatial | `scene_state` shared mutable dict | `scene_state_in` = frozen, мутация запрещена |
| persistence | `apply_changes()` → `save_scene_state()` mid-tick | `save_scene_state()` только в Phase 10 |
| memory | `list(cached)` shallow copy | `deepcopy` на входе тика |

---

## 2. Downstream Consumers

### 2.1 Первичные (точки внедрения)

| Потребитель | Роль | Статус |
|-------------|------|--------|
| `TickOrchestrator.execute()` | freeze(snapshot) на входе тика | ⚠️ Ожидает реализации |
| `SceneStateManager.lock_for_tick()` | Возвращает frozen copy вместо mutable ref | ⚠️ Ожидает реализации |
| `LifeEngine.get_npc_states()` | `deepcopy` вместо `list(cached)` | ⚠️ Ожидает реализации |
| `SceneStateManager.apply_changes()` | Убрать `save_scene_state()` из тела | ⚠️ Ожидает реализации |

### 2.2 Вторичные (потребляют результат)

| Потребитель | Что читает | Изменение после S83.1 |
|-------------|------------|------------------------|
| `DecisionHub` | `all_npcs_raw` | Читает frozen snapshot, не мутированный state |
| `MovementEngine` | `scene_state` | Читает frozen snapshot |
| `WorldSnapshotBuilder` | `scene_state`, `all_npcs_raw` | Читает frozen snapshot |
| `StateApplicator` | `all_npcs_raw` для commit | Получает delta accumulator |
| `CDS` | логи, traces | Становится валидным наблюдателем (воспроизводимость) |

### 2.3 Критическое ограничение (Контракт S83.1)

> Внутри одного тика не существует "текущего мира".
> Существует только:
> - input_snapshot (прошлое)
> - output_snapshot (будущее)

---

## 3. Architecture: Tick = Pure Function Evaluation

### 3.1 Контракт

```text
Tick : Snapshot → Snapshot

Где:

1. Вход:
   input_snapshot = полностью immutable состояние мира на момент начала тика

2. Выполнение:
   tick(input_snapshot) = f(input_snapshot, intents, rules)

   запрещено:
   - любое изменение input_snapshot
   - любое чтение "частично уже изменённого state"
   - любые cross-phase mutations через ссылки

3. Выход:
   output_snapshot = единственный результат тика

4. Коммуникация фаз:
   только через:
   - phase_outputs (explicit delta structures)
   - НЕ через общие mutable ссылки

5. Persistence:
   происходит строго после завершения tick()
   и никогда внутри фаз
```

### 3.2 Эволюционный путь

| Фаза | Что | Когда |
|------|-----|-------|
| S83.1A (сейчас) | `deepcopy` на входе `execute()` + запрет мутации `scene_state` | Немедленно |
| S83.1B | Убрать `save_scene_state()` из `apply_changes()` — Single Commit Boundary | После A |
| S83.1C | Phase outputs как explicit communication channel | После B |
| S83.2 | `_TickContext` = immutable snapshot + delta accumulator | После стабилизации |

### 3.3 Критерий перехода A→B

S83.1A даёт изоляцию через deepcopy. Но мутации внутри тика всё ещё происходят in-place (на копии).
Переход к B нужен когда: подтверждено, что deepcopy не создаёт регрессий производительности.

### 3.4 Правило ENIGMA-002 (Two-Domain Rule)

Переход к S83.2 (structural snapshot model) невозможен пока:
1. Есть только один домен, страдающий от in-place мутации копии
2. Нет runtime-бага, который требует immutable TickContext для починки

Сегодня: L5 (mid-tick persist) — один домен, уже починен в S83.1B.
Переход к S83.2 преждевременен.

---

## 4. Каузальная топология (до и после)

### 4.1 До S83.1 (reactive mutation)

```text
execute(scene_state)          ← mutable dict, по ссылке
  │
  ├─ Phase 0: LifeEngine.tick()
  │   └─ МУТИРУЕТ scene_state напрямую
  │   └─ ctx.all_npcs_raw = npc_states  ← SAME REF
  │
  ├─ Phase 5: DecisionHub
  │   └─ ЧИТАЕТ УЖЕ ИЗМЕНЁННЫЙ scene_state  ← D1 DRIFT
  │   └─ tick_decisions(scene_state=ctx.scene_state)
  │
  ├─ Phase 8: Handlers
  │   └─ МУТИРУЕТ npc_dict напрямую       ← L1 LEAK
  │   └─ Кеш LifeEngine мутируется        ← L1 LEAK
  │
  └─ Phase 10: Persistence
      └─ all_npcs_raw[:] = snapshot        ← L2 IN-PLACE OVERWRITE
      └─ apply_batch() → финальная мутация
      └─ COMMIT
```

### 4.2 После S83.1 (pure function)

```text
execute(scene_state)
  │
  ├─ FREEZE: input_snapshot = deepcopy(scene_state)
  │          frozen_npcs = deepcopy(engine.get_npc_states())
  │
  ├─ Phase 0: LifeEngine.tick()
  │   └─ ЧИТАЕТ input_snapshot (read-only)
  │   └─ ПРОИЗВОДИТ phase_0_deltas
  │
  ├─ Phase 5: DecisionHub
  │   └─ ЧИТАЕТ input_snapshot (read-only)  ← NO DRIFT
  │   └─ ЧИТАЕТ phase_0_deltas (explicit)   ← VISIBLE TRANSITION
  │   └─ ПРОИЗВОДИТ phase_5_deltas
  │
  ├─ Phase 8: Handlers
  │   └─ ПРОИЗВОДИТ phase_8_deltas
  │   └─ Кеш LifeEngine НЕ мутируется      ← NO LEAK
  │
  └─ Phase 10: Single Commit
      └─ apply_all_deltas(input_snapshot, all_deltas)
      └─ output_snapshot = materialized result
      └─ COMMIT (один раз)
```

---

## 5. Runtime Impact

| Метрика | Значение | Примечание |
|---------|----------|------------|
| RAM: deepcopy scene_state | +~50KB per tick | Для таверны ~200 объектов |
| RAM: deepcopy all_npcs_raw | +~20KB per tick | ~10 NPC × ~2KB каждый |
| Latency: deepcopy | +0.5ms per tick | copy.deepcopy на средних структурах |
| Tick Latency total | +0.5-1ms | Приемлемо для tick-based симуляции |
| VRAM | 0 | Нет визуальных изменений |

---

## 6. Sandbox Tests

### 6.1 Snapshot Isolation Tests

| Тест | Что проверяет |
|------|---------------|
| `test_tick_freeze_isolation` | Phase 0 мутация не видна в Phase 5 input |
| `test_deepcopy_npc_independence` | Мутация npc_dict в pipeline не мутирует кеш LifeEngine |
| `test_scene_state_read_only` | scene_state неизменён после execute() если нет commit |

### 6.2 Single Commit Tests

| Тест | Что проверяет |
|------|---------------|
| `test_no_mid_tick_persist` | save_scene_state() не вызывается внутри фаз |
| `test_single_commit_on_success` | atomic_commit() вызывается ровно 1 раз |
| `test_no_commit_on_crash` | Если Phase 5 падает — диск не затронут |

### 6.3 Phase Communication Tests

| Тест | Что проверяет |
|------|---------------|
| `test_phase_outputs_explicit` | Фазы не общаются через shared references |
| `test_decision_hub_reads_frozen` | DecisionHub читает input_snapshot, не мутированный state |

---

## 7. Rollback

1. Убрать `deepcopy` на входе `execute()`
2. Вернуть `list(cached)` вместо `deepcopy(cached)` в `get_npc_states()`
3. Вернуть `save_scene_state()` в `apply_changes()`
4. Вернуть `all_npcs_raw = npc_states` (same ref)

Все изменения изолированы — rollback не ломает S82 (Spatial Authority).

---

## 8. При UNKNOWN / пустых кандидатах

Текущее поведение сохраняется — `LifeEngine` решает что делать:
- `centroid` текущей комнаты
- текущая позиция
- пропустить tick

---

## 9. Каузальные запреты (Taboos)

| # | Запрет | Причина |
|---|--------|---------|
| 317 | Мутация `scene_state` внутри `execute()` после freeze | Нарушение pure function контракта |
| 318 | Чтение "частично изменённого" state между фазами | Двойная истина внутри тика |
| 319 | `all_npcs_raw = npc_states` (same ref) | Ноль изоляции между фазами |
| 320 | `list(cached)` вместо `deepcopy(cached)` | Shallow copy = утечка мутаций в кеш |
| 321 | `save_scene_state()` внутри `apply_changes()` | Mid-tick persist = crash inconsistency |
| 322 | `apply_changes()` вне Phase 10 | Single Commit Boundary |
| 323 | `_TickContext.scene_state` как mutable reference | Frozen snapshot = read-only |
| 324 | Фаза читает state мимо `input_snapshot` | Скрытый канал мутации |
| 325 | `confirmed_location_id` используется для spatial logic внутри тика | Spatial oracle = per-tick, не per-phase |

---

## 10. Зависимости от предыдущих ADR

| Зависимость | Влияние на S83.1 |
|-------------|------------------|
| S82 (Spatial Authority) | Backend oracle работает per-request, не per-tick — нужно синхронизировать |
| S83.0 (Spatial Coherence) | idle/game_action единый oracle — должен читаться из snapshot |
| ADR-303 (Coordinate Truth) | Коллизии в world — snapshot должен содержать world coordinates |
| ADR-301 (Semantic Index) | classify + resolve должны работать от frozen snapshot |

---

*Версия: 1.0*
*Дата: 2026-06-14*
*Актуализация: S83.1 (Tick = Pure Function Evaluation)*