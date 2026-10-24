# ENIGMA — Handoff S367 → S368 (завещание)

**Дата:** 2026-10-25 | **От:** архитектор S365→S366→S367 | **Кому:** новый архитектор S368
**Принцип:** независимая археология с нуля. Проверяй кодом и воспроизводимым тестом, не доверяй предположениям.

## 1. Состояние ветки А
- S365 CLOSED; S366 CLOSED; S367 CLOSED (2026-10-25)
- IPT 53/0, 0 CRITICAL; L4 чисто; backward-compat 109/109 (8 suites)

## 2. Контракты (НЕ релитигировать)
**S366 (4-слойная причинность):** СЛОЙ1 `ChronicleEntry.causes`; СЛОЙ2 `npc_beliefs: NpcCausalBelief`; СЛОЙ3 `cause_candidates: CauseCandidate`; СЛОЙ4 endpoints link-causes/resolve-cause-candidate/record-npc-belief. `CauseKind` не расширять; `ClarificationOption` для причинности запрещён. T-CCH-CL-01 заменён 17 тестами.
**S367 (roster-инъекция):** `BiographyDecomposer(roster_provider=None)` lazy `get_display_names`. Backstop в `normalize(..., roster=None)`: только RELATIONSHIP/EFFECT target_hint; exact match; `roster=None` отключает. name_hint/observed_hint/about_hint НЕ backstopятся. `_is_identity_question_for`: exact target_span==hint.

## 3. Ограничения (зафиксированы, НЕ дефекты)
1. Exact match, не fuzzy — inflected forms (Тенью) → form-mismatch noise (не засчитывается в gate).
2. NpcCausalBelief (S366 СЛОЙ2) хранится, но не в мышлении NPC — будущий рубеж.
3. S367 LLM-часть smoke не проверена (llama-server недоступен standalone); IPT поднимает свой. LLM-rule-3 compliance не доказана.
4. SPAN_OVERLAP (S366) не реализован (нет CauseKind.PORTRET).
5. TARGET_HINT_MATCH (S366) — диагностический признак.

## 4. Хвосты
- `[CONFIG] qwen_3_5_9b не найдена` (S366 smoke) — рассинхрон LLM-конфига; не диагностировался; кандидат в §7-хвосты.
- S367 LLM-rule-3 compliance — запустить smoke под живым llama-server вне IPT.

## 5. Границы (актуальны для S368)
`routes_chronicle.py` — минимально; схема канона/MODEL_REGISTRY/`_VAGUE_RELATION_MARKERS` — не трогать без ADR; источник истины — данные + контракт, не предположение о модели.

## 6. S368 — brief
**Наблюдение:** WithAge=0 для всех NPC, несмотря на regex-якорь.
**Принцип Мастера:** сначала выяснить — возраст не извлекается, или извлекается но теряется ниже. Два разных дефекта.
**Шаг 0 — археология пути:** биография → regex-якоря → prompt → decompose-результат → normalize → сохранение → источник WithAge. На каждом переходе: код, формат, где пусто/теряется, что значит WithAge и где считается.
**Не предполагай regex виноват.** Возможные причины: якоря не в prompt / LLM игнорит / normalizer не извлекает age / ChronicleEntry.historical_age не пишется / WithAge из другого источника.
**Ограничения:** не менять код до диагноза; не добавлять regex/эвристики без доказательства; не менять схему/MODEL_REGISTRY; не маскировать дефект изменением WithAge; не использовать пропущенные проверки как доказательство.
**Перед APPROVE:** (1) определение WithAge; (2) трассировка NPC; (3) место потери ИЛИ доказательство сохранения-без-учёта; (4) воспроизводящий тест; (5) БЫЛО→ОЖИДАЕТСЯ→ФАКТИЧЕСКИ; (6) план + регрессии.
**S368 OPEN до диагноза + исправления.**

## 7. Артефакты
Патчеры: `scripts/s36{6,7}_apply_*.py`, `scripts/s367_doc_sync.py`, `scripts/s366_doc_sync.py`. Тесты: `backend/tests/micro/test_s36{6,7}_*.py`. Smoke: `scripts/s367_smoke_guard_borko.py`. IPT: `scripts/ipt_s367.log`. Изменённые исходники: `biography_decomposer.py`, `decomposition_normalizer.py`, `chronicle_decompose_system.txt`, `domain/chronicle.py`, `services/chronicle/chronicle_store.py`, `api/routes_chronicle.py` (S366 + L4-fix).

## 8. Уроки
1. CRLF-нормализация в патчерах обязательна (Windows-репо) — matcher на \n по CRLF даёт 0 hits.
2. IPT обязателен до закрытия route-слоя (ловит то, что микротесты не видят).
3. Смена архитектора на границах этапов — этот handoff.

---
*Завещание закрыто. S368 принимает новый архитектор с независимой археологией.*
