# RC8 Determinism RCA — S313 (Understanding Track)

> Статус: RCA закрыт, развилка (ii) вердикта Мастера принята. RC8/RC3 → backlog до стабильного inference path.
> Формат: хроника invalidated-эксперимента + установленное экспериментом (без недоказанных причин).

## 1. Контекст

RC8 (provenance false-positive) — ownership provenance перенесён из consumer в canonicalization:
ASK_PROVENANCE — канонический semantic type (контракт промпта → валидатор → consumer → relevance).
Consumer keyword-детектор удалён; regression lock: consumer не читает слова topic (test_b3).
Для валидного A/B (STATE-A без few-shot vs STATE-B с few-shot) требовался детерминированный sampling path.

## 2. Archaeology inference path

- Comprehension-клиент (LlamaCppCompressorClient) идёт собственным HTTP-путём в обход GenerationParams.
- Было: temperature=0.1, seed отсутствовал. Детерминированный seed-прецедент существовал только в _complete_via_server (DM-путь): KernelRNG(tick=0, npc_id="llama_cpp", salt=prompt).
- Патч: temperature 0.1→0.0 + seed=KernelRNG(salt=user_prompt) — только comprehension-путь; DM/вербализация (0.9) не тронуты.

## 3. Хроника детерминизм-замеров

| # | Условия | Результат |
|---|---------|-----------|
| Det-1 | temperature=0+seed, два прогона подряд | Байт-идентичны (GREEN, 84458=84458 байт) |
| A/B-попытка | marker-check нарушен: оба прогона на few-shot | Diff непустой ВНЕ RC8-домена (SELF_INTRO/MULTI флипают) |
| Det-2 | идентичное состояние, два прогона подряд | **RED: 5+ расхождений** (MULTI ×2, «Мю ВАн», GEN/AB-boundary) |

## 4. Установленное экспериментом

**Current inference path demonstrated non-reproducible canonical output despite temperature=0 + fixed seed.**

- Первый GREEN переклассифицирован: неустойчивое наблюдение, не свойство системы.
- Run-to-run шум доминирует над эффектом промпт-изменений → prompt A/B методологически невозможен на этом path.
- Детерминизм ≠ semantic correctness (терминологическая граница вердикта).
- Причина (batch/cache/runtime llama.cpp server) — ГИПОТЕЗА, отдельное infrastructure investigation.

## 5. Решения вердикта

- Развилка (ii): RC8/RC3 → BACKLOG до стабильного inference path (Qwen3-8B A/B — горизонт).
- ASK_PROVENANCE infrastructure остаётся в production (works-when-emitted; замки 8/8).
- Few-shot RC8 (3 контрастные строки): PRESENT / EFFECT UNPROVEN.
- Probe corpus v0 + det-check: постоянный протокол. det-check RED → semantic experiment STOP.
- Отсутствие semantic-патчей вследствие невалидного A/B — сознательно.

## 6. Контрастные данные (фрагменты сводок)

- GEN-PROV (unseen provenance): 0/3 → ASK_PROVENANCE в обоих состояниях; тема при этом несёт provenance-семантику («learn who informed...»).
- «Кто рассказал Люсе про меня?» → ASK_PROVENANCE{about:имя игрока} — канонизация пограничной фразы точная (single hit).
- «Кто уже Трахался с Люсей?» → ложно ASK_PROVENANCE (контракт-строка «НЕ использовать для третьих лиц» не удержала).
- LIVE live-flutter класс «Я X»: probe-стабильно SELF_INTRODUCTION (9/9), live-флаттер — та же детерминистская граница (до фикса).
- RC2-фикс живой регресс: «ударить Горана» → ATTACK сохранён (падежный резолв), фантом «денег» → DIALOGUE (override по гейту).

## 7. Инструмент

- tests/sandbox/SUPERBOX/scenarios/semantic_probe_corpus.py — probe corpus v0 (~70 реплик: 6 классов + contrast pairs + human corpus Оператора + GEN-наборы).
- Протокол: det-check (два прогона, Compare-Object полных сводок) GREEN → только потом A/B → independent generalization.
- Правило корпусов: exploratory (живая речь, поиск дыр) ≠ generalization (независимые формулировки класса перед production-фиксом).