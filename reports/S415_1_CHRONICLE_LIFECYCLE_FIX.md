# S415.1 — Chronicle Lifecycle Fix: narrative_cache seeding in life_engine path

**Сессия:** S415.1 (продолжение S415)
**Ветка:** V.0.5.4.5.6_Полшага_3
**Дата:** 2026-11-05
**Предыдущий коммит:** 156a2d29 S414: F5 Biography Behavioral Proof (MEM-1..4, PARTIAL SUCCESS)

---

## 0. Контекст

USL-2: доказать причинную цепочку
`BIOGRAPHY -> MEMORY -> FEAR -> DECISION -> ACTION -> MOVEMENT -> WORLD STATE`.

**Доказано до S415.1:**
- BIOGRAPHY -> MEMORY: блокировано (narrative_cache=0 в production path)
- DECISION -> ACTION -> WORLD STATE: доказано в S415 A/B v8
- MEMORY -> FEAR -> DECISION: НЕ доказано (A/B v8 невалиден)

**Корневая причина невалидности A/B v8:** `life_engine._apply_cch4_seed` сеял
beliefs + imprints, но НЕ сеял `narrative_cache`. Production path
`TavernGameplayHarness` идёт через `life_engine._load_npcs` (не через
`npc_loader.load_npcs_merged`, который сеял полностью).

---

## 1. Fix

**Файл:** `backend/app/services/npc/life_engine.py`
**Метод:** `_apply_cch4_seed` (L1083-1132)

**БЫЛО:** метод сеял beliefs + imprints через `_apply_chronicle_seed_to_dict`,
но НЕ сеял `narrative_cache`. life_engine path (harness.new_game) никогда
не получал memories.

**СТАЛО:** после `_apply_chronicle_seed_to_dict` добавлен блок
(зеркально `load_npcs_merged` L370-382):

    _doc = _cseed.canonical_chronicle(_npc_id)
    if _doc:
        _memories = _cseed.build_seed_memories(_npc_id, _doc)
        if _memories:
            _cache_list = []
            for _item in _memories:
                _d = {**_item.__dict__, "_memory_type": type(_item).__name__}
                # tuple -> list для сериализации (tags/known_by/hidden_from)
                ...
                _cache_list.append(_d)
            _npc["narrative_cache"] = _cache_list

**Принцип:** зеркально `load_npcs_merged` L370-382 — единый контракт
seeding для обоих production paths.

---

## 2. Verify

**Скрипт:** `scripts/s415_1_verify.py`
**Команда:** `python ..\scripts\s415_1_verify.py`
**Exit code:** 0

**Результаты (`maid_lusya` после idle_tick):**

| Метрика | До fix (A/B v8) | После fix (verify) |
|---|---|---|
| narrative_cache | 0 | 10 |
| relationship_cache targets | [] | 4 targets |
| psyche.beliefs | 0 | 1 |
| affective_imprints | 0 | 2 |
| trust(tavern_keeper_tornin) | - | -40.0 |

**Все NPC narrative_cache:**
- guard_borko: 10
- merchant_goran: 7
- maid_lusya: 10
- blacksmith_orm: 10
- thief_shadow: 8
- tavern_keeper_tornin: 10
- player: 0 (корректно — нет биографии)

**narrative_cache samples (maid_lusya, первые 5):**
- target_id="", summary="Люся знает тайный ход в подвал гильдии воров"
- target_id="", summary="Тень приказал Люсе быть готовой к большому делу"
- target_id="", summary="Торнин знает, что подвал используется гильдией, но притворяется"
- target_id="", summary="Люся спит с кузнецом Ормом, а Борко подглядывает"
- target_id="", summary="семью убили бандиты"

**relationship_cache details (maid_lusya):**
- tavern_keeper_tornin: trust=-40.0
- thief_shadow: trust=30.0
- guard_borko: trust=30.0
- blacksmith_orm: trust=30.0

---

## 3. Гейты

- **ruff:** `python -m ruff check app/services/npc/life_engine.py` — All checks passed!
- **IPT:** 52 passed / 0 skipped / 2 failed (2 CRITICAL) — оба CRITICAL чужие:
  - `INV-RE-CACHE-ALLOWLIST` — `services/npc/npc_loader.py` (GROWTH, чужой WIP)
  - `INV-SILENT-FAILURE` — `dialogue_executor.py:390` (P5-B, чужой контур)
- **Дельта-метод:** вклад ветви А = 0 (прецедент S325)

---

## 4. Открытый вопрос для S415.1a (MEM-1)

Все 5 показанных `narrative_cache` samples имеют `target_id=""`. Это
критично для `recent_pressure` (risk.py) и `npc_memory_modifiers`
(DecisionHub) — они не смогут отнести fear к правильному target.

**Гипотезы:**
1. `chronicle_seeder.build_seed_memories` не резолвит `object_id` в `target_id`
   для некоторых EVENT entries
2. `_resolved_npc_id` возвращает None для RESOLVED refs
3. Maid_lusya EVENT entries с object_id=tavern_keeper_tornin не получают target_id

**Шаги S415.1a:**
1. Прочитать `config/npc/chronicles/maid_lusya.json` — все EVENT entries + их object_id
2. Прочитать `chronicle_seeder.build_seed_memories` (L167-213) + `_resolved_npc_id` (L148)
3. Проверить: какие EVENT entries ДОЛЖНЫ иметь target_id=tornin
4. Сверить с `inspect_npc("maid_lusya").narrative_cache`
5. Если target_id пуст у записей о Торнине -> MEM-1 не работает в production
   path -> фикс `_resolved_npc_id`
6. Если корректно -> MEM-1 работает -> переход к S415.2 (A/B v9)

---

## 5. Pending

- **S415.1a** — MEM-1 read-only verification (target_id атрибуция)
- **S415.2** — A/B v9 (idle ticks, правильный monkeypatch lifecycle)
- **S415.3** — Вердикт USL-2