# M4 P7 DISCLOSURE VERBALIZATION — EAVESDROP LABEL — HANDOFF
# Сессия: S259 (2026, ветка Говорим_2) · Статус: CLOSED / GREEN / ACCEPTED
# Вердикт-основа: санкция Мастера (P7-A + P7-B запускать; P7-C исключён;
#   «LLM не имеет права самостоятельно определить, что NPC решил раскрыть»)

---

## 1. ПЯТЬ ДОКАЗАННЫХ ЗВЕНЬЕВ

| Звено | Доказано | Тест |
|---|---|---|
| Вердикт до слов | _resolve_disclosure_verdict — ЕДИНСТВЕННОЕ вычисление decide_disclosure на реплику, до LLM; гейты E1 дословно | T-P7-3 (monkeypatch-счётчик: ровно 1) |
| Директива в промпте | [ДИРЕКТИВА РАСКРЫТИЯ: LEVEL] сериализуется в user_prompt; LLM вербализует, не решает | T-P7-1/2 (FakeRouter захватывает промпт) |
| Эмит из вычисленного | _emit_dialogue_outcome = проекция без вычисления; DOUBLE TRUTH вердикта запрещён | T-P7-1/7 (DIALOGUE_OUTCOME по вердикту) |
| Метка по провенансу | secret_id = KnowledgeItem спикера (retrieve_knowledge, P3-резолвер); FULL ⇔ exposure ∈ {secret, whisper} → IDENTIFIED; normal → CLUE | T-P7-4/5 (production path: реальный NPC-словарь harness) |
| Наследие E2 | без проводки/знания/при ошибке → (None, None) → observation only; монополия Bridge; Р1 | T-P7-6/6b/8 (unwired · no-knowledge · монотонность двух каналов) |

## 2. КАНОНИЧЕСКИЕ ЗАКОНЫ (S259)

VERDICT PRECEDES WORDS — decide_disclosure выносится ДО вербализации,
   ровно один раз на реплику; вердикт = данные (промпт + surface).
EAVESDROP LABEL IS PROVENANCE — метка подслушанного = знание спикера
   (KnowledgeItem.secret_id), не текст; FULL ⇔ {secret, whisper}.
ЭМИТ ИЗ ВЫЧИСЛЕННОГО — второй вызов decide_disclosure «для события»
   = DOUBLE TRUTH вердикта; эмит — проекция, не вычисление.

## 3. КАРТА ПРОВОДКИ (production)

E1-контур (адресованный вопрос):
  QueuedTask(DIALOGUE) → DialogueExecutor.execute
    → _resolve_disclosure_verdict [гейты E1: bridge · target=="player" ·
        providers · NPCState(owner) · fail-open]
        retrieve_knowledge(items[0]) → decide_disclosure → DisclosureOutcome
    → LLM: user_prompt += [ДИРЕКТИВА РАСКРЫТИЯ: LEVEL ...]
    → точка доставки → _emit_dialogue_outcome(verdict) → Bridge
  ⚠ DEBT-E1-WIRING: TaskScheduler строится БЕЗ epistemic-параметров;
    set_epistemic_wiring никем не вызывается → в production E1-контур
    молчит (P7-A тест-доказан). Асимметрия «наблюдение сильнее вопроса».

E2-контур (подслушанное слово):
  NPC_SPOKE → NpcDialogueSubscriber.on_npc_spoke
    → мембрана S128/Р-Г → append_journal → [гварды E2:
      listener≠player ∧ speaker≠player]
    → _resolve_eavesdrop_label: retrieve_knowledge(speaker) →
      secret_id; FULL ⇔ payload.exposure ∈ {secret, whisper}
    → SurfaceEvent(EAVESDROP, secret_id, content_class) → Bridge
  wiring: game_loop:446 — subject_resolver = extract_subject

Mapper (не менялся, ожили ветки): FULL → IDENTIFIED (mark по Р1);
  секрет без FULL → CLUE; без метки → observation only (E2-наследие).

## 4. ЧТО НАМЕРЕННО НЕ ПОСТРОЕНО

P7-C (exposure-политика DecisionHub: хардкод from_semantic("normal")
:372 — секретная речь как класс не производится; FULL достижим через
солилоквий-сентинель) · E1 production-wiring (DEBT — СЛЕДУЮЩИЙ СРЕЗ,
санкционирован Мастером) · synthesize канон-текста при REVEAL (выбрана
директива; пересмотр при LLM-тече) · валидация реплики против директивы
через DialogueContractViolation (при первом runtime-инциденте) · дедуп
observation · items[1..n] (P5 — один item, канонизировано).

## 5. ФАЙЛОВАЯ КАРТА

Новые (1): tests/gameplay/test_p7_disclosure_verbalization.py (9 тестов)
Модифицированные (3): dialogue_executor.py (~104) ·
  npc_dialogue_subscriber.py (~60) · game_loop/__init__.py (импорт +
  1 wiring-строка :446)
НЕ ТРОНУТЫ: discovery_bridge · player_epistemics(DTO) · DecisionHub ·
  ClaimEventSubscriber · DialogueMaterializer · SSOT радиусов · все
  тесты E1/E2/E3/P5.

## 6. ACCEPTANCE EVIDENCE

RED    6F/3P — ТОЧНЫЙ прогноз (2× AssertionError нет директивы +
       4× TypeError нет контракта subject_resolver); пины 3/3.
GREEN  9/9 · production-path сквозной (реальный harness).
REGRESSION: targeted 25/25 · tests/gameplay 70/71 (FAILED = gc09b-R2,
       pre-existing, git-доказано).
T5     GREEN-0: легитимный вызывающий mark_discovered — 1 (bridge).
ruff   автофикс-инцидент (6 fixed в файлах сессии; поведение не
       изменилось); 15 remaining = pre-existing game_loop (scope-freeze).
IPT    ИТОГО: 45 passed / 0 failed (0 CRITICAL). TIME-FREEZER (CRITICAL
       pre-existing) закрыт ПАРАЛЛЕЛЬНОЙ сессией в окне S259 (не присвоен).

H-CLOSURE RECORD (флип INV-DIALOGUE-STM, полная цепочка):
  красный Z2 при зелёном G6-3 → реестр заморожен → бисекция W5 (без 3
  файлов 🟢) / W6 (без game_loop 🟢) / W7 (аргумент выкл 🟢, импорт
  невиновен; V3 признан невалидным — франкенштейн) → зонды W9-W11 →
  МЕХАНИЗМ: MEMBRANE-CUT d=7.3 — позиционная хрупкость инварианта
  (async-недетерминизм позиций к тику 39); с wiring 4 зелёных прогона
  подряд; причинная связь дельты НЕ подтверждена. FLAKE-CANDIDATE →
  очередь; IPT не ретушировался молча.

## 7. ОТКРЫТАЯ ОЧЕРЕДЬ

DEBT-E1-WIRING (СЛЕДУЮЩИЙ — санкционирован) · P7-C (отдельная сессия) ·
FLAKE INV-DIALOGUE-STM (сетап-фикс с санкцией) · X-STABILITY gc00_97 ·
gc09b-R2 · ruff-ордера.

## 8. НЕ ДЕЛАТЬ

1. НЕ переоткрывать: P5/P6, E1/E2/E3, монополию, мембраны.
2. НЕ вызывать decide_disclosure второй раз «для события».
3. НЕ парсить текст реплики для метки.
4. НЕ расширять гварды E1/E2; НЕ трогать DiscoveryBridge/DTO без приказа.
5. НЕ менять SSOT радиусов. 6. НЕ ретушировать flaky/gc09b молча.
7. P7-C — только отдельной сессией с PRE-FLIGHT.

## 9. УРОКИ

D-P7-ISO-PARTIAL — контрактную пару (wiring+consumer) изолируют вместе.
D-P7-RUFF-AUTOFIX — ruff fix=true мутирует файлы; touched-lines гейт
   снимается ПОСЛЕ прогона.
D-P7-ANCHOR — якорь БЫЛО из свежего чтения, не из памяти.
D-P7-SAMPLE-SIZE — «детерминированно» = 3+ различающихся прогона.
D-P7-IPT-BASELINE — baseline-IPT в начале сессии обязателен.

## ХРОНИКА

Досье S256 → выбор Мастера: P7 → А1-А8 (карта построено/не построено;
найдены хардкод normal и E1-gap) → санкция → RED 6F/3P → патчи → GREEN
9/9 → 25/25 → wiring Б-5 → 70/71 → H: флип STM → W5-W7 бисекция →
W9-W11 зонды (flake, механизм) → санация → IPT 45/0 → реестр → досье.

*Источник: полный протокол сессии. Контактный артефакт: это досье.*
