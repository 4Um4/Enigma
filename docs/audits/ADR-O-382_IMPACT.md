# ADR-O-382 Impact Audit — Intelligence Queue: Non-Blocking Dialogue Extraction
> production-форма ADR-O-377 · закрытие DEBT-RE-D2A. Атлас: `docs/ADR (Architecture Decision Records).md` (ADR-O-382, вставка после O-377). Досье: `docs/audits/D8P_PRE_FLIGHT.md` (археология §2, Anti-Bond §3, вердикты владельца §13). Номер = max+1 по свежему чтению атласа на момент записи.

## Суть решения (ратифицировано владельцем)
Разрыв сцепки «момент события ↔ момент LLM-интерпретации» для dialogue-экстракции.
Единственный LLM-вызов домена — `DialogueUpdateExtractor.extract`
(npc_dialogue_subscriber.py:131), сегодня исполняемый в потоке публикатора
NPC_SPOKE. При `D8P_ENABLED=1`: подписчик enqueue'ит IntelligenceTask
(event_id, campaign_id, speaker, listener, text, stm_before, parent_tick;
task_id детерминированный H(...), uuid4 запрещён) неблокирующе и немедленно
пишет STM-ход с placeholder (`intent="dialogue"` — существующая семантика
деградации); исполнение — FIFO через СУЩЕСТВУЮЩИЙ max_workers=1 executor-рельс;
результат → STALE-гейт → применение ТОЛЬКО через MemoryManager session API.

## Four Boundaries (владелец, дословно)
- **router.py — NO TOUCH** (зона forensic-соседей; слой строится НАД guard'ом;
  при ON loop-вызов LLM становится недостижим by construction).
- **DeltaGate — NO TOUCH** (WHITELIST psyche-скаляров не расширяется;
  session-семантика ≠ psyche — мост между доменами запрещён).
- **MemoryManager — legal application authority** (единственный писатель
  session-памяти, Закон 4.1.2; LLM не становится state authority).
- **TaskScheduler pool — existing execution rail** (max_workers=1; второго
  LLM execution domain НЕТ; сигнатуры не меняются).

## Changed Domains
- game_loop (инъекция очереди; enqueue-точка = подписчик, не продюсер)
- memory (session-enrichment отложенного применения)
- llm-execution (декупляция потока интерпретации от публикатора)

## Downstream Consumers
- MemoryManager session API (add_dialogue_turn/add_claim/add_open_question/topic)
- DialogueUpdateExtractor (контракт вызова неизменен; контекст — worker)
- Router (только worker-ветка; RE-D2 guard недостижим при ON)

## Runtime Impact
- RAM: очередь + lifecycle-множества идемпотентности (~KBs)
- Tick latency: −(3.3–4.3с sync-экстракции из стека подписчика при ON); enqueue ≈ 0
- OFF (default) = байтово идентичное поведение (INV-D8P-NOOP)

## STALE-контракт (Q2б)
`current_tick − parent_tick > D8P_MAX_AGE_TICKS` (старт 3; calibration, не
онтология) OR session отсутствует OR required actor invalid/dead/out-of-world →
discard НАБЛЮДАЕМО (лог + счётчик; состояние STALE_DISCARDED). Тихий discard —
табу (O-377).

## Idempotency (Q5)
one event.id → ≤1 IntelligenceTask → ≤1 applied DialogueUpdate. Lifecycle:
ENQUEUED / EXECUTED / APPLIED / STALE_DISCARDED / FAILED — наблюдаемая история
исполнения ≠ инвариант состояния. Собственный реестр очереди, НЕ TaskState
диалоговых задач.

## Rollback
`D8P_ENABLED=OFF` = полный no-op (прецеденты W3_G2_ENABLED/BC1_ENABLED).
RAM-only, персистенции нет — удаление слоя бесследно.

## Sandbox Tests
- Приёмка (план, по методологии causal_state_test/bc1): A/B/C/D-группы, громкие
  падения; метрика = wall-clock + lifecycle-счётчики задач, НЕ впечатление
- IPT-кандидаты: INV-D8P-NOOP / INV-LLM-LOOP-EXILE / INV-D8P-TRACE-ONCE /
  INV-D8P-STALE-OBSERVABLE (досье §10)
- Baseline ДО (гейт перед кодом): R1 = `wait 20` wall-clock в живом uvicorn БЕЗ
  отцепления экстрактора; R2 = loop-семантика (исторически красный, S248);
  красный = норма для замера ДО; R1-зелёный НЕ опровергает D8P (§13.2 досье)

## Anti-Bond (Р17-П1)
Уникальная работа: разрыв сцепки «LLM-интерпретация ↔ поток/время публикатора» +
позднее применение через stale-гейт. Полная таблица — досье §3.

## Координация
- Forensic-соседи: router.py / AST-tombstone — их зона, только чтение
- W-track: coordination-якорь 6ad6e819 (их game_loop-хвост B1.4 в моём S247
  коммите; их routes-половина в дереве — их проводка замкнёт приёмник)
- Владелец TaskScheduler (S203.4): executor-рельс как есть, сигнатуры не меняются
- REBASE/генерализация примитивов отложена (§ENIGMA-002, вердикт D2A)