# ТЗ — S415: USL-2 A/B v9 (продолжение)

**Дата составления:** 2026-11-05
**Сессия-источник:** S415 (web-0f7468cd-...)
**Проект:** C:\DDD\Codex\VSC_Enigma\Enigma (ветвь V.0.5.4.5.6_Полшага_3)
**Предыдущий коммит (до S415.1):** `156a2d29 S414: F5 Biography Behavioral Proof (MEM-1..4, PARTIAL SUCCESS)`

---

## 0. Кратко — где мы находимся

USL-2: доказать причинную цепочку

```
BIOGRAPHY → MEMORY → FEAR → DECISION → ACTION → MOVEMENT → WORLD STATE
```

**Доказано на текущий момент:**

| Звено | Статус | Где |
|---|---|---|
| BIOGRAPHY → MEMORY | ✅ после S415.1 | narrative_cache=10, trust(tornin)=-40 |
| DECISION → ACTION → WORLD STATE | ✅ в S415 (A/B v8) | intent=flee → MacroMovementGoal → SceneChange → Δpos=5.63 units |
| MEMORY → FEAR → DECISION | ❌ НЕ доказано | A/B v8 был невалиден (narrative_cache=0 в обоих вариантах) |

**USL-2 НЕ закрыт.** Нужно провести A/B v9 с корректной изоляцией биографии.

---

## 1. Что сделано в этой сессии (S415)

### 1.1. S414 — закрыт ранее
- MEM-1 (target_id атрибуция EventMemory в canonical JSON)
- MEM-2 (target_hint для RELATIONSHIP)
- MEM-3 (npc_memory_modifiers wiring в DecisionHub.compute, L4-компликантный except)
- MEM-4 (risk.py NPC→NPC pressure обобщение)
- Commit `156a2d29` — PARTIAL SUCCESS: DECISION доказан, ACTION→WORLD STATE открыт

### 1.2. S415 — проведено расследование production call chain
**Карта готова:**

```
HubEventContext (player input/world event)
  → NpcTickPipeline.run (npc_tick_pipeline.py:125)
    → DecisionHub.compute (npc_tick_pipeline.py:1058 / world_tick_engine.py:210)
      → _resolve_target (decision_hub.py:1923)
    → _resolve_reactive_movement (npc_tick_pipeline.py:1637-1858)
      ├─ "approach" → LocalSteeringGoal | MacroMovementGoal
      └─ "flee"     → MacroMovementGoal(target_intent=flee, PRIORITY_REACTIVE)
    → TickMutation(movement_intents=[...]) (npc_tick_pipeline.py:1342)
  → TickOrchestrator phase 5
    → movement_bridge.process_movement_intents (movement_bridge.py:22-162)
      → MovementEngine.process_intents (movement_engine.py:140-280+)
        → SceneChange(field="local_position", target=npc_id, new_value={x,y})
          (sites: movement_engine.py L544, L749, L757, L1066, L1086, L1126, L1137)
      → orchestrator._apply_with_shadow_observation
        → npc_positions[npc_id]["local_position"] mutated
```

**Proactive path (world_tick_engine) — РАЗРЫВ:** `ProactiveDecision` идёт только в `r3_direct_builder` (DM-presentation), НЕ в MovementEngine. Это отдельный долг, не блокер USL-2.

### 1.3. S415 A/B v8 — проведён, результат невалиден
- Stimulus: `player_action("я угрожаю служанке Люсе")` → THREATEN
- A (bio) и B (control) **идентичны**: 5×flee, 4 movement_intents, Δdist=0.28
- Причина: `narrative_cache=0` в обоих вариантах — biography не загружалась

**Положительный побочный результат S415 A/B v8:** доказано
`DECISION → ACTION → WORLD STATE` (Lusya сдвинулась на 5.63 units, SceneChange применён).

### 1.4. S415.1 — найдена и исправлена корневая причина
**Баг:** `life_engine._apply_cch4_seed` (L1083-1110) сеял beliefs + imprints, но НЕ сеял
`narrative_cache`. Production path `TavernGameplayHarness` идёт через
`life_engine._load_npcs` (не через `npc_loader.load_npcs_merged`, который сеял полностью).

**Fix:** добавлен вызов `build_seed_memories` + запись в `_npc["narrative_cache"]`,
зеркально `load_npcs_merged` L370-382.

**Verify (`scripts/s415_1_verify.py`):**

| Метрика | До fix | После fix |
|---|---|---|
| narrative_cache (maid_lusya) | 0 | 10 ✅ |
| relationship_cache targets | [] | 4 targets ✅ |
| psyche.beliefs | 0 | 1 ✅ |
| affective_imprints | 0 | 2 ✅ |
| trust(tavern_keeper_tornin) | — | -40.0 ✅ |

**⚠️ Коммит S415.1 НЕ подтверждён в этой сессии** — блок commit был отправлен,
вывод не получен. Приёмник должен сначала проверить `git log --oneline -3`:
- Если commit `S415.1: Chronicle lifecycle fix...` есть — продолжаем с S415.1a
- Если commit нет — выполнить commit-блок заново (см. раздел 3)

---

## 2. Что нужно сделать приёмнику

### Этап S415.1a — MEM-1 read-only verification

**Цель:** убедиться, что `EventMemory.target_id` корректно атрибутирован
для записей о Торнине, прежде чем проверять адресную memory в v9.

**Почему важно:** в verify S415.1 все 5 показанных samples имели `target_id=""`.
Если memory о насилии Торнина не адресована `tavern_keeper_tornin`, то
`recent_pressure` (risk.py) и `npc_memory_modifiers` (DecisionHub) не смогут
отнести fear к правильному target.

**Шаги:**

1. Прочитать `config/npc/chronicles/maid_lusya.json` — все EVENT entries
2. Для каждой EVENT entry проверить `object_id`:
   - `{"ref_kind": "RESOLVED", "npc_id": "tavern_keeper_tornin", ...}` → должен стать target_id
   - `{"ref_kind": "WHITE_SPOT", ...}` → законно пустой target_id (неразрешённая сущность)
   - `null` → зависит от семантики записи
3. Прочитать `chronicle_seeder.build_seed_memories` (L167-213) — строка 185:
   `target_id=_resolved_npc_id(e.object_id) or ""`
4. Прочитать `_resolved_npc_id` (L148) — понять, когда возвращает None
5. Проверить, какие EVENT entries maid_lusya **обязаны** иметь target_id=tornin:
   - "Торнин знает, что подвал используется гильдией, но притворяется"
   - "Торнин относился к Люсии как к..." (если это EVENT, а не RELATIONSHIP)
   - "Люся не защищена от избиений трактирщика" (EFFECT)
6. Сверить с выводом `inspect_npc("maid_lusya").narrative_cache` — какие target_id реально

**Вердикт:**
- Если записи о Торнине имеют `target_id=""` → MEM-1 не работает в production path,
  нужно исправить (возможно, `_resolved_npc_id` ломается на форме object_id)
- Если записи корректно адресованы → MEM-1 работает, переходим к v9

**Не расширять правила Seeder только ради target_id.** Каждое решение должно
соответствовать семантике исходной записи.

### Этап S415.2 — A/B v9

**Цель:** доказать `BIOGRAPHY → MEMORY → FEAR → DECISION → ACTION → MOVEMENT → WORLD STATE`.

**Критерии допуска (из директивы Мастера):**
- A действительно загружает биографическую память (narrative_cache>0)
- B действительно не загружает Chronicle-биографию (narrative_cache=0 или существенно меньше)
- Static legacy origin_events сохранены в обоих вариантах
- Условия A/B идентичны, кроме биографического источника
- Ни один вариант не получает искусственно заданный intent или action

**Stimulus:** idle ticks (как v7). НЕ THREATEN — он самостоятельно порождает flee
через reactive path, маскируя вклад biography.

**Monkeypatch lifecycle — критичное исправление vs v8:**
- v8 bug: `with chronicle_seeder_disabled(): harness = ...; harness.new_game()`
  context manager выходил ДО `new_game()` → патчи не активны во время загрузки
- v9 fix: патчи должны быть активны **во время `new_game()` И tick processing**
  использовать `try/finally` с явным restore после `harness.dispose()`

**Monkeypatch цели (4):**
```python
chronicle_seeder.build_seed_memories = lambda npc_id, doc: ()
chronicle_seeder.build_seed_relationships = lambda npc_id, doc: {}
chronicle_seeder.build_seed_imprints = lambda doc: []
chronicle_seeder.build_seed_beliefs = lambda doc: {}
```

**Pre-flight assertions (до основного эксперимента):**
```python
# Variant A
assert len(harness_A.inspect_npc("maid_lusya")["narrative_cache"]) > 0
assert "tavern_keeper_tornin" in harness_A.inspect_npc("maid_lusya")["relationship_cache"]

# Variant B
assert len(harness_B.inspect_npc("maid_lusya")["narrative_cache"]) == 0
# legacy origin_events могут дать небольшой cache — нужно сравнить с A
```

**Метрики для сравнения (с захватом до/после):**

| Метрика | A (bio) ожидаемо | B (control) ожидаемо |
|---|---|---|
| narrative_cache | 10 | 0 (или legacy минимум) |
| fear(Tornin) | 60 | baseline (~0) |
| trust(Tornin) | -40 | baseline |
| affective_imprints | присутствуют | отсутствуют |
| intent (после N idle ticks) | flee или avoidance | idle/observe |
| movement_intents | >0 | 0 |
| Δdistance(Lusya, Tornin) | >0 | ≈0 |

**Hook'и для capture (из v8, рабочие):**
- `NpcTickPipeline.run` → capture `mutation.movement_intents` + `mutation.npc_deltas`
- `MovementEngine.process_intents` → capture returned `List[SceneChange]`

**Методологический закон (от Мастера):**
> Если A не убежит от Торнина, это не повод подгонять тест под ожидаемый результат.
> Мы должны установить, на каком звене причинная цепочка перестала работать.

Если A не даёт flee:
1. Проверить narrative_cache (BIOGRAPHY → MEMORY)
2. Проверить fear/trust в NPCState (MEMORY → FEAR)
3. Проверить DecisionHub scores_trace (FEAR → DECISION)
4. Проверить movement_intents (DECISION → ACTION)
5. Проверить SceneChange (ACTION → WORLD STATE)

### Этап S415.3 — Вердикт USL-2

После v9:
- Если все звенья доказаны → USL-2 закрыт, предложить Мастеру масштабирование
  биографий на следующие 5 NPC
- Если цепочка сломана на конкретном звене → зафиксировать точку разрыва,
  НЕ подгонять результат

---

## 3. Коммит-блок S415.1 (если коммит ещё не выполнен)

```powershell
& {
    $ErrorActionPreference = "Continue"
    if ((Split-Path (Get-Location) -Leaf) -eq "backend") { Set-Location .. }

    # Проверка — был ли уже коммит
    $log = & git log --oneline -3 2>&1
    if ($log -match "S415.1") {
        Write-Output "S415.1 commit already exists:"
        Write-Output $log
        exit 0
    }

    # Ruff
    Set-Location backend
    & python -m ruff check app/services/npc/life_engine.py 2>&1
    Set-Location ..

    # IPT (норма: 52 passed / 2 failed CRITICAL — оба чужие)
    Set-Location backend
    & python tests/IPT.py 2>&1 | Select-Object -Last 10
    Set-Location ..

    # Commit
    & git add backend/app/services/npc/life_engine.py scripts/s415_1_verify.py reports/S415_1_CHRONICLE_LIFECYCLE_FIX.md
    $msg = @"
S415.1: Chronicle lifecycle fix — narrative_cache seeding in life_engine path

ROOT CAUSE: life_engine._apply_cch4_seed сеял beliefs + imprints, но НЕ сеял
narrative_cache. Production path TavernGameplayHarness идёт через
life_engine._load_npcs (не через npc_loader.load_npcs_merged).

FIX: _apply_cch4_seed теперь вызывает build_seed_memories + пишет
_npc["narrative_cache"], зеркально load_npcs_merged L370-382.

Verify: maid_lusya narrative_cache 0→10, trust(tornin)=-40, beliefs/imprints populated.
"@
    $tmp = "$env:TEMP\s415_1_msg.txt"
    Set-Content -Path $tmp -Value $msg -Encoding UTF8 -NoNewline
    & git commit -F $tmp
    Remove-Item $tmp -Force
    & git log --oneline -2
}
```

**Важно:** `reports/S415_1_CHRONICLE_LIFECYCLE_FIX.md` должен существовать.
Если нет — приёмник должен создать его (содержимое есть в архиве сессии).

---

## 4. Ключевые файлы и точки

### Изменённые мной файлы (в этом git workspace)

| Файл | Изменение | Статус |
|---|---|---|
| `backend/app/services/npc/life_engine.py` | `_apply_cch4_seed` fix | 🔲 commit pending |
| `scripts/s415_1_verify.py` | новый verify script | 🔲 commit pending |
| `reports/S415_1_CHRONICLE_LIFECYCLE_FIX.md` | новый отчёт | 🔲 commit pending |
| `scripts/s415_ab_v8.py` | A/B v8 скрипт (невалидный, но полезный как reference) | не коммитить (можно удалить или оставить как артефакт) |

### Чужие файлы (НЕ трогать)

- `backend/app/services/execution/dialogue_executor.py` — P5-B
- `backend/app/services/npc/npc_loader.py` — GROWTH (INV-RE-CACHE-ALLOWLIST)
- `backend/app/models/npc_state.py`, `game_loop.py` — параллельные сессии

### Ключевые file:line для v9

| Что | Где |
|---|---|
| `_apply_cch4_seed` (fixed) | `life_engine.py:1083-1130` |
| `_apply_chronicle_seed_to_dict` | `npc_loader.py:716-738` |
| `load_npcs_merged` (эталон полного seeding) | `npc_loader.py:307-463` |
| `build_seed_memories` | `chronicle_seeder.py:167-213` |
| `_resolve_reactive_movement` (flee/approach) | `npc_tick_pipeline.py:1637-1858` |
| `_MOVE_INTENTS` set | `npc_tick_pipeline.py:1155` |
| `DecisionHub.compute` reactive call | `npc_tick_pipeline.py:1058` |
| `movement_bridge.process_movement_intents` | `movement_bridge.py:22-162` |
| `MovementEngine.process_intents` | `movement_engine.py:140-280` |
| `harness.new_game()` | `tests/gameplay/harness.py:111-148` |
| `harness.inspect_npc` | `tests/gameplay/harness.py:285-290` |
| `harness.player_action` | `tests/gameplay/harness.py:262` |
| `harness.advance_ticks` | `tests/gameplay/harness.py:206` |

### maid_lusya biography (релевантные entries)

| # | kind | object_id | summary |
|---|---|---|---|
| 5 | RELATIONSHIP | null | "Торнин относился к Люсии как к..." |
| 7 | EVENT | tavern_keeper_tornin | (truncated) |
| 8 | EVENT | tavern_keeper_tornin | (age=0) |
| 9 | RELATIONSHIP | null | nature="вражда", valence="negative" |
| 11 | EFFECT | null | "Люся не защищена от избиений трактирщика" |
| 22 | DESIRE_SEED | null | "сбежать от всех проблем на юг" |

---

## 5. Известные ограничения и подводные камни

1. **Proactive path разрыв** — `WorldTickResult.decisions` идут только в DM-presentation
   (`r3_direct_builder`), НЕ в MovementEngine. Не блокер для USL-2 (используем reactive path).

2. **`reset_campaign` wipe** (`life_engine.py:972`) — `npc["narrative_cache"] = []`.
   `TavernGameplayHarness.new_game()` НЕ вызывает `game_loop.new_game()`, поэтому
   wipe не срабатывает. Но если v9 будет использовать иной harness — учесть.

3. **LLM offline** — `llama-server` не запущен, все LLM-вызовы падают с `ConnectionRefusedError`.
   v9 должен работать **LLM-free** (idle ticks не требуют LLM для decision).
   Если v9 будет использовать player_action — может потребоваться offline-LLM mock.

4. **IPT known failures** (чужие, не блокеры):
   - `INV-RE-CACHE-ALLOWLIST` — `npc_loader.py` (GROWTH)
   - `INV-SILENT-FAILURE` — `dialogue_executor.py:390` (P5-B)

5. **CCH_SEED warnings** в логах — корректная валидация неполных canonical entries,
   НЕ баги seeder.

6. **`target_id=""` в memories** — возможная проблема MEM-1 в production path.
   Проверить в S415.1a.

---

## 6. Принятые методологические принципы

1. **Не подгонять тест под ожидаемый результат.** Если A не убежит — искать сломанное звено.
2. **Изолированные коммиты.** S415.1 (lifecycle fix) — отдельно от S415.2 (A/B v9).
3. **Не смешивать изменения.** Fix + эксперимент + monkeypatch — разные коммиты.
4. **Read-only сначала.** Перед любым изменением — трассировка и понимание.
5. **Не расширять правила Seeder ради метрик.** Каждое решение соответствует семантике записи.
6. **Не создавать новые хранилища истины.** Использовать существующие production-path.
7. **Чужие файлы не трогать.** Проверять git ownership перед изменениями.

---

## 7. Ожидаемый финальный артефакт

После успешного S415.2:
- `reports/S415_2_USL2_AB_V9_PROOF.md` — отчёт A/B v9 с полной цепочкой
- `scripts/s415_2_ab_v9.py` — воспроизводимый эксперимент
- `artifacts/s415/ab_v9/` — JSON-артефакты (decisions, movement_intents, scene_changes, positions)
- Commit `S415.2: USL-2 A/B v9 — full causal chain proven` (или `OPEN` с указанием разрыва)

Если USL-2 закрыт → Мастер рассматривает масштабирование биографий на следующие 5 NPC.

---

## 8. Quick-start для приёмника

```powershell
# 1. Проверить состояние
cd C:\DDD\Codex\VSC_Enigma\Enigma
git log --oneline -3
git status --short

# 2. Если S415.1 не закоммичен — выполнить блок из раздела 3

# 3. S415.1a — MEM-1 verify (read-only)
#    Прочитать maid_lusya.json EVENT entries, сверить target_id

# 4. S415.2 — написать s415_2_ab_v9.py
#    (idle ticks, правильный monkeypatch lifecycle, pre-flight assertions)

# 5. Провести v9, зафиксировать вердикт
```

---

**Конец ТЗ.**
