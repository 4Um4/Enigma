#!/usr/bin/env python3
"""S398 — ADR-O-436 RECONCILIATION (doc-only). Код не менять."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def rw(path):
    b = path.read_bytes()
    bom = b.startswith(b'\xef\xbb\xbf')
    c = b.decode('utf-8-sig')
    has_crlf = '\r\n' in c
    c = c.replace('\r\n', '\n')
    return c, bom, has_crlf

def ww(path, c, bom, has_crlf):
    if has_crlf:
        c = c.replace('\n', '\r\n')
    data = c.encode('utf-8')
    if bom:
        data = b'\xef\xbb\xbf' + data
    path.write_bytes(data)

def ed(content, old, new, desc):
    n = content.count(old)
    if n == 0:
        print(f"FAIL: {desc} — not found"); sys.exit(1)
    if n > 1:
        print(f"FAIL: {desc} — {n} matches (not unique)"); sys.exit(1)
    print(f"OK: {desc}")
    return content.replace(old, new, 1)

# === ADR atlas ===
adr_path = ROOT / "docs" / "ADR (Architecture Decision Records).md"
adr, adr_bom, adr_crlf = rw(adr_path)

# A1: status
adr = ed(adr,
    "**Статус:** PROPOSED (готов к вердикту Мастера для C2) | **Сессия:** S396 |",
    "**Статус:** IMPLEMENTED (S398 reconciliation — фактическая реализация зафиксирована) | **Сессия:** S396 (предложение) → S398 (reconciliation) |",
    "A1: ADR-O-436 status PROPOSED -> IMPLEMENTED")

# A2: вставка раздела «Фактическая реализация» перед «Контракт»
A2_OLD = "**Контракт:**\n- Событие создаётся только после принятого решения NPC (DecisionHub.compute), не по score или присутствию игрока."

A2_NEW = """**Фактическая реализация (S398 reconciliation):**

Первоначальное предложение (выше) описывало планируемую архитектуру. Фактическая реализация отклоняется в трёх точках — все отклонения в лучшую сторону (канонические механизмы вместо новых сущностей).

**Producer:** `backend/app/services/phases/commit_phase.py:82-132` — НЕ `npc_tick_pipeline.py` (как в предложении). NpcTickPipeline — pure reducer (ADR-TZ09-1), не применяет состояние; публикация там создала бы сигнал о намерении, которое не стало состоянием. Фактическая точка — ПОСЛЕ финального `apply_batch` (где `_apply_intent` зафиксировал `state.intent_formed_at = current_tick`), ДО `scene_manager.commit`. Контракт: публикация только при `intent_formed_at == ctx.tick_number` (commit_phase.py:115) — кросс-тиковая идемпотентность без флагов и реестров.

**Identity:** canonical `next_event_identity(scene_state, event_type, source) -> (tick, ordinal)` (event_identity.py) — НЕ `MD5(type:source:intent_formed_at:0)` (как в предложении). Single Writer `next_event_identity` — единственный механизм identity в проекте (ADR-O-404); собственная формула создала бы DOUBLE TRUTH. event_id = (event_type, source, tick, ordinal); идемпотентность через `intent_formed_at == current_tick` (только при смене intent), не через event_id-дедуп.

**Delivery:** `backend/app/services/events/npc_addressing_delivery_subscriber.py` — двухфазная доставка (staging → commit), НЕ через `PROJECTION_EVENT_TYPES` (как в предложении). Subscriber подписан на `EventType.NPC_ADDRESSES_PLAYER`; staging в `TickCampaignContext.staged_events`; `commit_staged(campaign_id)` вызывается orchestrator ПОСЛЕ успешного Phase 10; `drain(campaign_id)` возвращает проекцию для API; `ack(campaign_id, event_id)` — idempotent. Thread-safe (threading.Lock). NPC_ADDRESSES_PLAYER в `EXCLUDED_EVENT_TYPES` (idle_event_projection.py:146) — НЕ в `PROJECTION_EVENT_TYPES`; отдельный delivery-контур, не двойная доставка через idle events.

**Frontend lifecycle:** C3-A2-UI-2 (commit d252d6d1) — `game_screen.py:1260-1329`: stale re-delivery guard (intent_formed_at comparison), stale removal (old events with older intent_formed_at), безусловный ACK (try/except sibling guard), изоляция кампаний (reset в run()). 9 контрактов в `backend/tests/micro/test_npc_addressing_lifecycle.py`.

**Коммиты:**
- C2 (producer): `afb20bf2` — "ADR-O-436: NPC_ADDRESSES_PLAYER producer (LC-IMPL-3 Ступень A) — C2"
- C3-A1 (delivery subscriber + ruff cleanup): `7723e3ac` — "C3-A1: Ruff cleanup (F401/W292/I001/F841)"; delivery subscriber wiring в `b0415813` (full-save)
- C3-A2-UI-2 (frontend lifecycle): `d252d6d1` — "C3-A2: manage NPC addressing indicator lifecycle"

**Тест producer re-entry:** `backend/tests/micro/test_npc_addresses_player.py:270` — `def test_C1_same_intent_next_tick_no_republish(bus)` — проверяет, что тот же intent на следующем тике НЕ вызывает повторную публикацию. **НАЙДЕН** — пробела нет.

**Расхождения с предложением (все — в лучшую сторону):**
1. Точка публикации: `npc_tick_pipeline` → `commit_phase.py` (после фиксации состояния, не в pure reducer)
2. Identity: `MD5(формула)` → `next_event_identity` (canonical Single Writer, не DOUBLE TRUTH)
3. Delivery: `PROJECTION_EVENT_TYPES` → отдельный `npc_addressing_delivery_subscriber` (разделение контуров, не двойная доставка)

**Контракт:**
- Событие создаётся только после принятого решения NPC (DecisionHub.compute), не по score или присутствию игрока."""

adr = ed(adr, A2_OLD, A2_NEW, "A2: insert Fakticheskaya realizatsiya section")

# A3: краткая реестр-запись
A3_OLD = 'Status: PROPOSED (S396 — готов к вердикту Мастера для C2; runtime-тесты pending)\nFiles: ``backend/app/services/events/event_types.py``, ``backend/app/services/game_loop/idle_event_projection.py``, ``backend/app/services/npc/npc_tick_pipeline.py``'

A3_NEW = 'Status: IMPLEMENTED (S398 — фактическая реализация зафиксирована; producer: commit_phase.py:82-132; delivery: npc_addressing_delivery_subscriber; identity: next_event_identity; frontend: C3-A2-UI-2 d252d6d1)\nFiles: ``backend/app/services/events/event_types.py`` (enum), ``backend/app/services/phases/commit_phase.py`` (producer:82-132), ``backend/app/services/events/npc_addressing_delivery_subscriber.py`` (delivery), ``backend/app/services/events/tick_campaign_context.py`` (staging), ``backend/app/services/tick_orchestrator.py`` (wiring:179-184,254,795,868), ``backend/app/domain/tick.py`` (TickResultDTO:288), ``frontend/game_screen.py`` (C3-A2-UI-2:1260-1329), ``backend/tests/micro/test_npc_addresses_player.py`` (producer tests), ``backend/tests/micro/test_npc_addressing_lifecycle.py`` (9 lifecycle контрактов)'

adr = ed(adr, A3_OLD, A3_NEW, "A3: registry entry status + files")

ww(adr_path, adr, adr_bom, adr_crlf)

# === Roadmap ===
rm_path = ROOT / "docs" / "ENIGMA_ROADMAP_v4_12_WPS.md"
rm, rm_bom, rm_crlf = rw(rm_path)

rm = ed(rm,
    "(источник события — NPC_ADDRESSES_PLAYER; pending C2)",
    "(источник события — NPC_ADDRESSES_PLAYER; C2 реализован — commit afb20bf2, ADR-O-436 status IMPLEMENTED per S398)",
    "B1: §15.2 pending C2 -> C2 реализован")

rm = ed(rm,
    "ADR-O-436 — источник события NPC_ADDRESSES_PLAYER, pending C2-C5;",
    "ADR-O-436 — источник события NPC_ADDRESSES_PLAYER, C2 реализован commit afb20bf2 / ADR-O-436 IMPLEMENTED per S398; C3-C5 pending;",
    "B2: §15.5 pending C2-C5 -> C2 реализован; C3-C5 pending")

B3_ANCHOR = "game_screen.py addressing parsing block 1260-1329, rendering 2238-2241 | — |"
B3_ROW = "\n| S398 | ADR-O-436 RECONCILIATION — статус PROPOSED → IMPLEMENTED; раздел «Фактическая реализация» (producer: commit_phase.py; identity: next_event_identity; delivery: npc_addressing_delivery_subscriber; frontend: C3-A2-UI-2); тест producer re-entry найден (test_C1_same_intent_next_tick_no_republish) | (doc-only) | GREEN | ADR атлас + roadmap §15.2/§15.5/§10.3 + MUTATIONS S398; код НЕ тронут | — |"

if B3_ANCHOR not in rm:
    print(f"FAIL: B3 — anchor not found"); sys.exit(1)
if rm.count(B3_ANCHOR) > 1:
    print(f"FAIL: B3 — anchor not unique ({rm.count(B3_ANCHOR)} matches)"); sys.exit(1)
rm = rm.replace(B3_ANCHOR, B3_ANCHOR + B3_ROW, 1)
print("OK: B3: §10.3 add S398 row")

ww(rm_path, rm, rm_bom, rm_crlf)

# === MUTATIONS ===
mut_path = ROOT / "docs" / "MUTATIONS.md"
mut, mut_bom, mut_crlf = rw(mut_path)

C1_ANCHOR = "· ✅ · без runtime-тестов (pending C2-C5) · коммит <SHA> (DOC-ONLY)"
C1_ROW = "\n- **S398** ADR-O-436 RECONCILIATION (ветвь Б; doc-only): ADR-O-436 status PROPOSED → IMPLEMENTED. PRE-FLIGHT C2 (S397) установил, что контур NPC_ADDRESSES_PLAYER уже полностью реализован: producer в commit_phase.py:82-132 (НЕ npc_tick_pipeline как в предложении — pure reducer не публикует); identity через canonical next_event_identity (НЕ MD5-формула — DOUBLE TRUTH риск); delivery через npc_addressing_delivery_subscriber (двухфазный staging→commit, НЕ PROJECTION_EVENT_TYPES — разделение контуров); frontend C3-A2-UI-2 (game_screen.py:1260-1329, commit d252d6d1). Тест producer re-entry НАЙДЕН: test_npc_addresses_player.py:270 test_C1_same_intent_next_tick_no_republish. Расхождения с предложением — все в лучшую сторону (канонические механизмы вместо новых сущностей). Коммиты C2/C3-A1/C3-A2-UI-2: afb20bf2 / 7723e3ac / d252d6d1 (b0415813 full-save). Правки: ADR атлас (status + раздел «Фактическая реализация» + registry), roadmap §15.2/§15.5/§10.3, MUTATIONS S398. Первоначальное предложение ADR сохранено как историческая часть. Код НЕ тронут. · ✅ · без ADR (reconciliation существующего) · коммит <SHA> (DOC-ONLY)"

if C1_ANCHOR not in mut:
    print(f"FAIL: C1 — anchor not found"); sys.exit(1)
if mut.count(C1_ANCHOR) > 1:
    print(f"FAIL: C1 — anchor not unique"); sys.exit(1)
mut = mut.replace(C1_ANCHOR, C1_ANCHOR + C1_ROW, 1)
print("OK: C1: MUTATIONS add S398 row")

mut = ed(mut,
    "Записей: 248 |",
    "Записей: 249 |",
    "C1-meta: MUTATIONS counter 248 -> 249")

ww(mut_path, mut, mut_bom, mut_crlf)

print()
print("=== S398 EDITS APPLIED ===")
print(f"  {adr_path}")
print(f"  {rm_path}")
print(f"  {mut_path}")