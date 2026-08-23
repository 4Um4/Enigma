# SUPERBOX-ACTION-INTEGRITY — findings (S216-gate, Stage 2A)

Прогон: 3 сценария × 120+30 тиков, enforcement=ON (верифицирован), temp-изоляция миров.
Инъекции runtime (после тика 0): hunger=0.9 / sleep_pressure=0.95 / activity_map.working→nonexistent.
LLM-слой недоступен (llama-server down) — на behavioral-гейт движений не влияет;
async-воркеры в backoff-цикле (вклад в Y-REPLAY).

## GREEN (инварианты связки Registry+Arbitration)
- ✅ R6: FAILED освобождает ownership (fail()=True, released=True) — страх
  permanently-locked Мастера не подтвердился
- ✅ G1/G4/G5/G7: ноль нарушений во всех тиках всех сценариев — ≤1 commitment,
  ≤1 traversal, нет terminal-in-active, нет superseded при enforcement
- ✅ Все 31 terminal во всех сценариях = COMPLETED/EXECUTING — ни одного
  INTERRUPTED при enforcement (реплика A/B-результата S203.2 в новых мирах)

## YELLOW (диагностика — входы спринтов)
- ⚠️ Y-SETTLED (ГЛАВНАЯ, вход S203.6): B2 — post-terminal churn. NPC в
  DEEP_SLEEP с активным движением (proactive_offer_job t=150, EXECUTING).
  Settled-state контракта нет: ни паузы, ни приоритета телесного состояния.
  S203.6 Settled State — доказанно необходимый слой (главный вопрос Мастера
  закрыт: НЕ свобода-и-покой, а непрерывный churn).
- ⚠️ Y-CHURN-RHYTHM (вход S203.6): интервал terminal→новый commitment = 2–3
  тика (ровно duration traversal) во ВСЕХ сценариях, без пауз. Механизм:
  candidate-поток (proactive-social + schedule) заполняет каждое освободившееся
  окно немедленно.
- ⚠️ Y-NEED (вход S203-D): hunger=0.9 инъекция подтверждена, но hunger-cause
  commitments = 0; schedule:eating доминирует. Расписание маскирует
  потребность: need-каскад не работает сквозь schedule. (Гипотеза 60% —
  требует микрозонда в S203-D.)
- ⚠️ Y-RESOLVER (вход S203.3): сломанная activity_map (working→nonexistent)
  НЕ останавливает NPC — резолв идёт fallback-цепочкой мимо карты. As-is
  resolver-путей больше, чем карта описывает.
- ⚠️ Y-REPLAY (долг, DEBT-QUIESCE-класс): длины последовательностей
  расходятся (10 vs 11) при идентичных стартах. Источник — async-слой
  (R4A/backoff при недоступном LLM), не связка. Переквалифицировано из RED:
  behavioral-деградации нет, infra-детерминизм — отдельная тема.

## RED (архитектурный провал)
- (пусто)

## Границы: D/E/F исключены (S203-E). LLM-зависимое поведение не гейтится.

## Вердикт: связка Registry+Arbitration поведенчески чиста (RED=0).
S203.6 Settled State — доказанный следующий слой. S203.3 получает вход:
resolver fallback-пути + (опционально) сон-владение как executor-вопрос.
