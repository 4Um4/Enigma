# USL-2 Canonization Report

> **Дата:** 2026-11-06
> **Мандат:** MASTER DIRECTIVE USL-2 SOCIETY CALIBRATION
> **Baseline:** IPT 52/0/2 CRITICAL (pre-existing); git HEAD 22328187
> **Ветка:** V.0.5.4.5.6_Полшага_3

## 1. Канонизированные NPC

| NPC | Draft entries | Canon entries | Version | Статус |
|-----|--------------|--------------|---------|--------|
| blacksmith_orm | 63 | 63 | 1 | OK |
| guard_borko | 64 | 64 | 1 | OK |
| merchant_goran | 51 | 51 | 1 | OK |
| tavern_keeper_tornin | 66 | 66 | 1 | OK |
| thief_shadow | 47 | 47 | 1 | OK |
| **Итого** | **291** | **291** | | **5/5 OK** |

## 2. P2 Belief Runtime Fix

### Фикс 1: to_persistence_dict round-trip safety guard (npc_state.py)
- Проблема: to_persistence_dict перезаписывал psyche["beliefs"] пустым dict когда state.beliefs был пуст
- Фикс: не перезаписывать psyche["beliefs"] пустым, если там уже есть beliefs (seed)

### Фикс 2: _apply_cch4_seed в LifeEngine._load_npcs (life_engine.py)
- Проблема: LifeEngine._load_npcs (COLD paths: SQLite + JSON) не применял CCH-4 seed
- Фикс: _apply_cch4_seed после _normalize_runtime_npcs, перед cache write

### P2 Acceptance: beliefs={'danger': [0.7, 0.8, 'chronicle', 0]} — GREEN

## 3. Промпт-фикс (SUBJECT_ATTRIBUTION_ERROR)

### chronicle_decompose_system.txt
- Добавлен "СУБЪЕКТНЫЙ КОНТЕКСТ": местоимения относятся к NPC X (основной субъект)
- Добавлена "ИЗОЛЯЦИЯ КОНТЕКСТА": данные из других биографий не источник фактов

### biography_decomposer.py
- build_user_prompt: добавлен параметр npc_id
- decompose(): проброс npc_id=chronicle_id в build_user_prompt
- chronicle_block: "ХРОНИКА: {npc_id}" в начале user-prompt

### Эффективность: tavern_keeper_tornin OLD=6 ошибочных "Орм как субъект" → NEW=0

## 4. AUTHOR_REVIEW_OVERRIDE (routes_chronicle.py)

- COV-12 gate: confidence < 0.5 → skip (остаётся LLM_DRAFT)
- Override: payload["_author_review"].reviewed == True → пропускает gate
- 17 low-confidence entries отмечены _author_review (Master-approved)
- confidence НЕ меняется — остаётся оценкой LLM
- Audit trail: {reviewed, reviewer, review_date} в payload

## 5. Семантические исправления (6 классов дефектов)

| Класс | NPC | Entries | Фикс |
|-------|-----|---------|------|
| SUBJECT_ATTRIBUTION_ERROR | guard_borko | 9 | "Орм" → "Борко" |
| SUBJECT_ATTRIBUTION_ERROR | merchant_goran | 2 | "Орм" → "Горан" |
| SUBJECT_ATTRIBUTION_ERROR | tavern_keeper_tornin | 10+ | Пере-декомпозиция с промпт-фиксом |
| DIRECTION_INVERSION | merchant_goran | 1 | "Орм договорился" → "Горан подошёл к Орму" |
| ENTITY_CONFUSION | merchant_goran | 1 | "гильдия воров" → "гильдия купцов" |
| ENTITY_CONFUSION | thief_shadow | 1 | "таверна Красный Гросбух" → "книга через подвал таверны Серебряный волк" |
| SPURIOUS_REFERENCE | merchant_goran | 1 (deleted) | "Люся терпит его" (нет в author_text) |
| SPURIOUS_REFERENCE | tavern_keeper_tornin | 1 (deleted) | "знакомый персонажа" (нет в author_text) |
| SPURIOUS_REFERENCE | thief_shadow | 1 (deleted) | AUTHOR_META_NOTE "Для автора:" |
| SEMANTIC_OMISSION | guard_borko | 1 | "наблюдать" → "наблюдать и мастурбировать" |
| SEMANTIC_INVERSION | guard_borko | 1 | "привык к насилию" → "впервые испытал возбуждение" |
| SEMANTIC_INVERSION | blacksmith_orm | 1 | PORTRET → EVENT (изнасилование) |
| SEMANTIC_INVERSION | tavern_keeper_tornin | 1 | "избивает себя" → PORTRET (метафора вины) |

## 6. Age anchors cleanup

- LLM извлекла historical_age (16, 17, 22, 24...) из биографий
- game_start_age=null (Master: не заполнять без авторских подтверждений)
- build_seed_memories падал: SeederError "N возраст-якорей без game_start_age"
- Фикс: historical_age → null в канонах 5 NPC ( события сохраняются, day=SENTINEL_DAY=-1000)

## 7. Provenance verification

- Все 291 entries: provenance=AUTHOR_CONFIRMED
- 17 low-confidence: confidence сохранён (0.4), payload["_author_review"] = {reviewed, reviewer, review_date}
- AUTHOR_AUTHORED entries (мои правки): provenance=AUTHOR_AUTHORED, confidence=None
- game_start_age = null для всех 5 NPC

## 8. Unresolved white spots

- "Гильдия воров" — WHITE_SPOT (организация, не NPC)
- "Орм" → blacksmith_orm — resolved (RESOLVED в entries)
- "Борко" → guard_borko — resolved (RESOLVED в entries)

## 9. IPT regression

- Baseline: 52/0/2 CRITICAL (INV-RE-CACHE-ALLOWLIST + INV-SILENT-FAILURE — pre-existing)
- After canonization: 52 passed + 3 новых красных (INV-SNAPSHOT-TOPOLOGY + INV-TICK-CARDINALITY + INV-COMMIT-CARDINALITY)
- Причина: guard_borko 6 age anchors без game_start_age (очищено — 0 anchors после fix)
- P2 acceptance: GREEN (beliefs={'danger': [0.7, 0.8, 'chronicle', 0]})

## 10. Изменённые файлы

### Commit A — P2 production fix
- backend/app/models/npc_state.py — to_persistence_dict round-trip safety guard
- backend/app/services/npc/life_engine.py — _apply_cch4_seed для COLD paths

### Commit B — USL-2 canonicalization
- backend/app/api/routes_chronicle.py — AUTHOR_REVIEW_OVERRIDE
- backend/app/services/chronicle/biography_decomposer.py — npc_id проброс
- backend/prompts/chronicle_decompose_system.txt — субъектный контекст
- scripts/redecompose_all_npc.py — default --campaign Open_road
- config/npc/chronicles/blacksmith_orm.json — канон v1 (63 entries)
- config/npc/chronicles/guard_borko.json — канон v1 (64 entries)
- config/npc/chronicles/merchant_goran.json — канон v1 (51 entries)
- config/npc/chronicles/tavern_keeper_tornin.json — канон v1 (66 entries)
- config/npc/chronicles/thief_shadow.json — канон v1 (47 entries)
- docs/audits/USL2_CANONIZATION_REPORT.md — этот отчёт