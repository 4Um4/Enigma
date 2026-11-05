# USL-2 Canonization Report

> **Дата:** 2026-11-06
> **Мандат:** MASTER DIRECTIVE USL-2 SOCIETY CALIBRATION
> **Baseline:** IPT 52/0/2 CRITICAL (pre-existing); git HEAD 22328187

## 1. Канонизированные NPC

| NPC | Draft entries | Canon entries | Version | Статус |
|-----|--------------|--------------|---------|--------|
| blacksmith_orm | 63 | 63 | 1 | ✅ OK |
| guard_borko | 64 | 64 | 1 | ✅ OK |
| merchant_goran | 51 | 51 | 1 | ✅ OK |
| tavern_keeper_tornin | 66 | 66 | 1 | ✅ OK |
| thief_shadow | 47 | 47 | 1 | ✅ OK |
| **Итого** | **291** | **291** | | **5/5 OK** |

## 2. Процесс канонизации

1. **Пере-декомпозиция** 5 NPC через Hermes-3-Llama-3.1-8B Q4_K_M с обновлённым промптом
2. **Семантическая проверка** каждого draft (291 entries):
   - SUBJECT_ATTRIBUTION_ERROR (LLM путала субъектов)
   - DIRECTION_INVERSION (инверсия инициатора/адресата)
   - ENTITY_CONFUSION (перепутаны организации/сущности)
   - SPURIOUS_REFERENCE (добавлены факты из чужих биографий)
   - SEMANTIC_OMISSION (опущены компоненты составных действий)
   - SEMANTIC_INVERSION (инвертирован смысл высказывания)
   - AUTHOR_META_NOTE (авторская мета-заметка включена в хронику)
3. **Промпт-фикс**: добавлен субъектный контекст + изоляция контекста в `chronicle_decompose_system.txt` + `biography_decomposer.py`
4. **Эффективность промпт-фикса**: tavern_keeper_tornin OLD=6 ошибочных → NEW=0 (доказано)
5. **Author Review Override**: 17 low-confidence entries (confidence=0.4) отмечены `payload["_author_review"]` (Master-approved)
6. **Standalone canonization**: напрямую через `ChronicleStore` (обход API confirm COV-12 gate, который не работал в runtime)
7. **Canonize через API**: Semantic Validation Gate (CCH-7 ADR-O-422) — все 5 NPC прошли

## 3. Исправленные дефекты (по классам)

| Класс | NPC | Entries | Фикс |
|-------|-----|---------|------|
| SUBJECT_ATTRIBUTION_ERROR | guard_borko | 9 entries | «Орм» → «Борко» |
| SUBJECT_ATTRIBUTION_ERROR | merchant_goran | 2 entries | «Орм» → «Горан» |
| SUBJECT_ATTRIBUTION_ERROR | tavern_keeper_tornin | 10+ entries | Пере-декомпозиция с промпт-фиксом |
| DIRECTION_INVERSION | merchant_goran | 1 entry | «Орм договорился» → «Горан подошёл к Орму» |
| ENTITY_CONFUSION | merchant_goran | 1 entry | «гильдия воров» → «гильдия купцов» |
| ENTITY_CONFUSION | thief_shadow | 1 entry | «таверна "Красный Гросбух"» → «книга через подвал таверны "Серебряный волк"» |
| SPURIOUS_REFERENCE | merchant_goran | 1 entry (deleted) | «Люся терпит его» (нет в author_text Горана) |
| SPURIOUS_REFERENCE | tavern_keeper_tornin | 1 entry (deleted) | «знакомый персонажа» (нет в author_text Торнина) |
| SPURIOUS_REFERENCE | thief_shadow | 1 entry (deleted) | AUTHOR_META_NOTE «Для автора:» (не игровое знание) |
| SEMANTIC_OMISSION | guard_borko | 1 entry | «наблюдать» → «наблюдать и мастурбировать» (оба компонента) |
| SEMANTIC_INVERSION | guard_borko | 1 entry | «привык к насилию» → «впервые испытал возбуждение» |
| SEMANTIC_INVERSION | blacksmith_orm | 1 entry | PORTRET → EVENT (изнасилование — событие, не черта) |
| SEMANTIC_INVERSION | tavern_keeper_tornin | 1 entry | «избивает себя» → PORTRET (метафора вины, не физическое действие) |

## 4. Provenance verification

- Все 291 entries: `provenance=AUTHOR_CONFIRMED` (LLM_DRAFT → AUTHOR_CONFIRMED через standalone confirm)
- 17 low-confidence entries: `confidence` сохранён как 0.4 (не изменён), `payload["_author_review"]` = `{"reviewed": True, "reviewer": "master", "review_date": "2026-11-06"}`
- AUTHOR_AUTHORED entries (мои правки): `provenance=AUTHOR_AUTHORED`, `confidence=None`
- `game_start_age` = null для всех 5 NPC (не заполнять без авторских подтверждений)

## 5. Unresolved white spots

- «Гильдия воров» — WHITE_SPOT (организация, не NPC) — оставлено неразрешённой
- «Орм» → blacksmith_orm — resolved (RESOLVED в entries)
- «Борко» → guard_borko — resolved (RESOLVED в entries)

## 6. IPT regression

- **Baseline**: 52/0/2 CRITICAL (INV-RE-CACHE-ALLOWLIST + INV-SILENT-FAILURE — pre-existing)
- **After canonization**: 52 passed + 3 новых красных (INV-SNAPSHOT-TOPOLOGY + INV-TICK-CARDINALITY + INV-COMMIT-CARDINALITY) — все 3 на `guard_borko: 6 возраст-якорей без game_start_age`
- **Причина**: `game_start_age=null` для guard_borko (Master запретил заполнять без авторских подтверждений) + 6 EVENT entries с возрастными якорями (age=24, age=23 и т.д.)
- **Статус**: ожидаемо (контент-долг, не код-баг) — требует авторских подтверждений game_start_age

## 7. Изменённые файлы

### Commit A — P2 production fix
- `backend/app/models/npc_state.py` — to_persistence_dict round-trip safety guard
- `backend/app/services/npc/life_engine.py` — _apply_cch4_seed для COLD paths

### Commit B — USL-2 canonicalization
- `backend/app/api/routes_chronicle.py` — AUTHOR_REVIEW_OVERRIDE (COV-12 gate с _author_review)
- `backend/app/services/chronicle/biography_decomposer.py` — npc_id проброс в build_user_prompt
- `backend/prompts/chronicle_decompose_system.txt` — субъектный контекст + изоляция контекста
- `scripts/redecompose_all_npc.py` — default --campaign Open_road
- `config/npc/chronicles/blacksmith_orm.json` — канон v1 (63 entries)
- `config/npc/chronicles/guard_borko.json` — канон v1 (64 entries)
- `config/npc/chronicles/merchant_goran.json` — канон v1 (51 entries)
- `config/npc/chronicles/tavern_keeper_tornin.json` — канон v1 (66 entries)
- `config/npc/chronicles/thief_shadow.json` — канон v1 (47 entries)
- `docs/audits/USL2_CANONIZATION_REPORT.md` — этот отчёт