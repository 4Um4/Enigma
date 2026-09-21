# ADR-O-400 Impact Audit: Incremental PatternDetector State (Watermark)

> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: docs/ADR (Architecture Decision Records).md
> **Сессия:** S273 | **Статус:** ACTIVE (A/B пройден: 24×10k RED→YELLOW, −33% p95; oracle 11/11; production=ON, OFF=rollback switch)
> **Зона:** L1.5 (PatternDetector) + Фаза 9 (integration.py:410) | **Rule 28-зона:** чтение хроники, append-only не затрагивается

## Проблема (измеренная, датасет v1.3)

`integration.py:410` — единственный call site `query_raw(_npc_id)` (per-caller атрибуция: 100%).
Вызов без `t_from` → дефолт 0 (`l1_chronicle.py:296`) → каждое срабатывание Фазы 9 сканирует
ВСЮ хронику каждого NPC (O(жизнь) × O(N)). Измеренные следствия: History-tax onset после ~3000 тиков
(~+10 мс/тик за 1000 тиков истории), q_raw доля L1-потока 42→78% по оси H, RED на 24×10k (p95=219).

## Equivalence Gate (S273, вердикт Мастера: CONDITIONAL GO)

`detect(H1+H2)` заменяем на `update(state(H1), H2) → detect_from_state()` — легально ТОЛЬКО потому,
что PatternDetector математически допускает достаточную статистику: агрегаты per-source
(n, cumulative, Σx, Σx², last_sign, sign_flips, first_seen) полностью определяют результат.
Текущий `EvidenceOfPersistence` (3 поля) достаточной статистикой НЕ является — наивный watermark
отвергнут на гейте. Семь вопросов гейта закрыты живым чтением (pattern_detector.py, 136 строк целиком).

## Контракты (обязательные, нарушение = FAIL)

### 1. Exactness Contract
- `statistics.variance` — ЭТАЛОН (внутренняя точная арифметика).
- Аккумуляторы Σx, Σx² — ТОЛЬКО Fraction (float = рациональное с двоичным знаменателем;
  Fraction-накопление точно). Welford / float-Σ² в первой реализации ЗАПРЕЩЕНЫ.
- `cumulative_effect` — сохраняем последовательное float-сложение оригинала (порядок потока),
  НЕ переходим на Fraction: equivalence требует совпадения float-результата, а он
  достигается той же последовательностью операций.
- Гипотеза `float(exact_fraction) == float(statistics.variance(...))` — ПРОВЕРЯЕТСЯ ТЕСТОМ,
  не постулируется. Тест: property-based на случайных потоках (hypothesis, прецедент INV-PBT).

### 2. Order Contract
- Порядок событий внутри source_id сохраняется (flips — последовательные пары).
- `first_seen` (глобальный порядковый номер первого появления source) определяет порядок
  evidence_list — candidate обязан выдать идентичный порядок.
- Downstream BeliefCrystallizationEngine получает список в том же порядке.

### 3. Persistence Contract
- watermark-state — per (npc_id, source_id), живёт в scene_state → Фаза 10 atomic commit
  (прецедент EpistemicStore S193: RAM + round-trip + проекция; собственной SQLite НЕЛЬЗЯ —
  анти-паттерн ExpectationStore).
- Fraction сериализуется как (numerator, denominator) — целые; ключи — константы модуля (§12.1).
- Round-trip exact: from_dict(to_dict(state)) == state — обязательный тест.

### 4. No Semantic Shortcut
- `EvidenceOfPersistence` НЕ расширяется (frozen-контракт домена неприкосновенен).
- Новый объект — отдельный watermark state (внутренний для PatternDetector-контура).
- `query_evidence` не удаляется и не рефакторится в этой итерации (dead-code кандидат — отдельная заметка).
- Append-only L1 (Rule 28) не затрагивается: меняется ТОЛЬКО объём повторного чтения.

### 5. Equivalence Oracle (тест-гейт ДО benchmark)
Для одинаковых потоков: detect(H1+H2) vs update(state(H1), H2):
- количество evidence — равно;
- порядок evidence — равен;
- source_id, cumulative_effect, behavior_variance — равны побитово (float ==, не approx);
- плюс PBT на случайных H1/H2-разбиениях.

### 6. Tick-monotonicity Contract (ветка 2: tail-read)
- Watermark = `last_seen_tick` per NPC (max tick_id, переданный в detect ранее).
- Чтение хвоста: `query_raw(npc_id, t_from=last_seen_tick + 1)`.
- Предпосылка: L1-записи tick-монотонны (все 9 писателей коммитят с текущим тиком — верифицировано).
- Детекция нарушения: событие с `tick_id <= last_seen_tick` в хвосте → RuntimeError (громко, не молча).
- Порядок evidence: архив-ветка (SQL ORDER BY) + RAM-ветка (insertion) — срез сохраняет
  относительный порядок полного потока; шов архив/RAM покрывается A/B 24×10k (archive-события живые).

## A/B-гейт (после прохождения oracle)

Baseline (зафиксирован в датасете v1.3, НЕ перемеряется): 24×3000, 24×10k, 60×3000 (LLM-off).
Candidate: те же точки, DRIFT_NO_LLM=1, тот же инструмент (scale_instrument.py).
**Гейт: canonical causal skeleton equality. Расхождение = NO-GO независимо от ускорения.**
Только после skeleton: p50/p95/RAM/L1 — сравнение с baseline.

## Rollback

Flag default OFF = полный no-op (прецедент S203.1 shadow). Точка включения — env/config.
Откат = выключение флага; state в scene_state совместим по forward-чтению (лишние ключи игнорируются ядром).

## Downstream Consumers

- BeliefCrystallizationEngine (L2.5) — вход неизменен (тот же List[EvidenceOfPersistence], тот же порядок).
- CrystallizedBelief / ADR-O-307 (асимметричная травма) — не затронуты.
- memory_manager._resonance.detect — ДРУГОЙ детектор, не затронут.
- W-IR: существующие тесты pattern_detector (test_pattern_detector_math_correct и др.) обязаны
  остаться зелёными в обоих режимах флага.

## Taboo

- ❌ Float-аккумуляторы Σx²/Welford без ADR-изменения exactness contract.
- ❌ Расширение EvidenceOfPersistence.
- ❌ Удаление/рефакторинг query_evidence в этой итерации.
- ❌ Изменение append-only L1 (Rule 28).
- ❌ Собственная SQLite-персистенция watermark-state.
- ❌ Включение флага без пройденного oracle + skeleton equality.
- ❌ Приблизительные сравнения (approx) в equivalence-тестах — только побитовые.




