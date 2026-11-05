# F5 / USL-2 — Biography Behavioral Proof (S414)

**Дата:** 2026-11-05  
**Сессия:** S414 (F5 Headless Laboratory, ветвь Б)  
**Статус:** PARTIAL SUCCESS — DECISION PROVEN, ACTION→WORLD STATE OPEN  

## 0. История эксперимента

### Этап 1: Первоначальный F5 — ОТРИЦАТЕЛЬНЫЙ результат

A/B v2: одинаковый intent=`seek_ally` с/без biography. 4 точки разрыва найдены:
1. target_id='' в EventMemory — страх не атрибутирован к NPC
2. RELATIONSHIP entries без target_hint — seeder не резолвит
3. npc_memory_modifiers НЕ передаётся в DecisionHub — memory мертва
4. risk.py HARDCODED "player" — NPC→NPC pressure не учитывается

### Этап 2: MEM-1—MEM-3 исправления

- MEM-1: object_id добавлен в 4 EVENT entries (Tornin/Orm)
- MEM-2: target_hint добавлен в 2 RELATIONSHIP entries (Tornin)
- Fix A+B: target_hint fallback + fear для negative valence + SEED_FEAR_NEGATIVE=60.0
- MEM-3: npc_memory_modifiers wiring в DecisionHub.compute

### Этап 3: A/B v7 — PARTIAL SUCCESS

- A (с biography): intent=`idle`, target=`tavern_keeper_tornin`, fear=60, trust=-40
- B (control — 3 monkeypatches): intent=`seek_ally`, target=`maid_lusya`, fear=0, trust=40

**Biography ВЛИЯЕТ на поведение.**

## 1. Цепочка — состояние звеньев

| Звено | Статус | Доказательство |
|---|---|---|
| SOURCE BIOGRAPHY | ✅ | maid_lusya.json, 10 EVENT entries |
| CANONICAL EVENT | ✅ | 10 EVENT entries (is_recurring, target_id) |
| SEEDED MEMORY | ✅ | narrative_cache=10 (vs 7 в control) |
| COGNITIVE AVAIL | ✅ | trust=-40, fear=60 (vs trust=40, fear=0) |
| DECISION | ✅ | intent='idle', target='tavern_keeper_tornin' |
| ACTION | ❌ | intent='idle' — нет action |
| WORLD STATE | ❌ | не проверено |

## 2. A/B methodology — контроль B

B содержит 7 narrative_cache из legacy origin_events (static NPC config). Это НЕ "NPC без памяти", а "NPC без Chronicle-биографии". Допустимый контроль для проверки добавочного эффекта нового биографического пути.

Control monkeypatches (3): _apply_chronicle_seed_to_dict, build_seed_memories, build_seed_relationships.

## 3. MEM track — статус

| Этап | Статус |
|---|---|
| MEM-1 (target_id) | ✅ CLOSED |
| MEM-2 (target_hint) | ✅ CLOSED |
| MEM-3 (npc_memory_modifiers) | ✅ CLOSED |
| MEM-4 (risk.py NPC→NPC) | ❌ OPEN |
| F5 DECISION | ✅ PROVEN |
| F5 ACTION→WORLD STATE | ❌ OPEN |

## 4. USL-2 статус

НЕ закрыт. DECISION доказан, ACTION→WORLD STATE открыт.
