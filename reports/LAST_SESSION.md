# ENIGMA Session State — 2026-10-11 18:53

Кампания: `?` | Игрок: `?`

## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА

Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами → **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). У других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---

## DNA — МЕТРИКИ ЗДОРОВЬЯ СИСТЕМЫ

_Сессия: 4.7 мин | Тиков: 0 | LLM-вызовов: 13_

| Метрика | Значение | Δ от прошлой | Интерпретация для LLM |
|---------|----------|--------------|----------------------|
| **SHI** (Simulation Health) | 0% | → +0.0% | ⛔ МЕРТВА: решений нет. Проверь DecisionHub.compute() |
| **NPI** (NPC Pipeline) | 0% | → +0.0% | нет данных о NPC |
| **OBI** (Obedience) | 0% | → +0.0% | нет директив в сессии — OBI не применим |
| **SCF** (Spatial Coherence) | 1.0 | → +0.0 | ✅ пространство целостно: граф загружен корректно |
| **ADR** (Debt Ratio) | 0.00 | → +0.0 | нет ADR-записей — невозможно оценить |
| **CVS** (Causal Velocity) | 2.75/мин | ↑ +2.2 | ✅ 2.75/мин: активная сессия |
| **PFI** (Pre-Bus Failure) | 0% | → +0.0% | ✅ норма: пред-шинных отказов нет — CDS видит всё |
| **Tracebacks** | 0 (AttrErr=0, TypeErr=0) | → | ✅ норма |
| **BCI** (Belief Crystallization) | 0 (idx=0.00) | → | ⚠️ Память не кристаллизуется (BCI=0) |
| **BPI** (Break Progress) | 0 (broken=0) | → | ⚠️ NPC не ломаются (BPI=0) |
| **NEI** (Need Urgency) | 0 (critical=0) | → | ⚠️ NPC слишком комфортны (NEI=0) |
| **DRI** (Response Integrity) | 100% | → +0.0% | ✅ LLM отвечает на все запросы |
| **DPI** (Dialogue Pipeline) | 100% | → +0.0% | ✅ Конвейер диалогов стабилен |

**Системные сигналы (требуют внимания):**
- SHI=0% при активных LLM-вызовах: игрок взаимодействует но NPC не решают — разрыв между R3_DIRECT и DecisionHub

_История: `reports/dna_history.jsonl` — 1294 записей_

## 🟢 КРАСНЫЕ ИНВАРИАНТЫ — ТИХИЕ ДЕГРАДАЦИИ

_Не обнаружено — игра жива._

**Источники проверки:**
- Runtime: `SimulationIntegrityError` в pipeline (не сработал)
- Post-mortem: `InvariantHealthChecker` в CausalObserver (не нашёл)
- Слой ДО: `python backend/tests/IPT.py` (запускается LLM до коммита)

## #1 — АРХИТЕКТОР КОДА (патчи, файлы, архитектура)

### Сейчас делает:
(не определено — обнови MUTATIONS.md)

### Активные баги требующие патча:
_(баги не обнаружены в этой сессии)_

### Последние изменения (git log -5):
  - 8b69e1d2 S345: CCH-4 — history scroll (wheel, 22-row window; Borco-24th-item verdict), roster display_name (name from individuals config; cyrillic-header resolver for collection import), silent-failure fix in get_display_names (IPT INV-SILENT-FAILURE caught bare except), collection import per-NPC routing + world author layer (_world_author_layer.md); IPT 52/52
  - 2c6cbb89 COV-2/cosmetic: W292 newline factory.py (вердикт GO)
  - 31387976 COV-2/D61-бэкенд: детектор отказа (pool_backoff_status + /llm/outage — доказанный backoff немедленно, health-only через дебаунс фронта) + настоящий рестарт в server_lifecycle (сериализация lock, kill только проверенного llama-server по PID, защита занятого порта, поллинг /health до 200, успех => сброс backoff) + прод-роут /api/llm/restart (debug-алиас сохранён) + main.py делегирует спавн + T-D61 x10
  - 7317f6c7 S346-reg: закрытие Understanding Engine фронта — строка S346 (8 коммитов: контракт/автопик/fail-closed гейт/per-act инфраструктура/A/B-данные/эскалация/ORDER-гейт); три защитных эффекта замкнуты фальсификаторами; языковая граница Qwen2.5-7B честно зафиксирована (negated не распознаётся тремя путями — не объявлено решённым); хвосты: UX-фронт (вердикты Мастера приняты), S122/RC3, fast-path, пример-итерация; попутно восстановлена PROV_B-запись S343-реестра (COV-контур уведомлён); МЕТА 228→229 по грепу правила 5
  - c1283454 S-UE-fix3: мини-fix №3 (вердикт Мастера, изолированный diff) — контракт гейта приведён в соответствие с фактическим состоянием интерпретации: неразобранная негация закрывает исполнение ORDER-актов, не только world-changing (находка 5.2: 'Не говори ему…' = RESOLVED — противоречие контракту безопасности; спасение акты=[] было случайным). КОРНЕВОЙ ДИАГНОЗ (догма-зонд): _content_words len>2-фильтр отрезал частицы 'не/ни' ('Не бей его.' -> {'бить','он'}, hit=False) — фильтр легитимен для сверки имён (предлоги), фатален для частиц; фикс: параметр keep_short (существующие вызовы байт-неизменны, negation-детекция — keep_short=True). Контракт: частица ЕСТЬ ∧ ни один акт не разобрал negated -> не-RESOLVED; позитивный ORDER без частицы = RESOLVED (обычные приказы не блокируются); LLM negated=False разблокирует (мост). Тесты: 6/6 (ORDER+не=блок / позитив ORDER=RESOLVED / ATTACK+не=PARTIAL / легаси-акты / мост negated=False / world-changing-без-target). Параллельная серия: PERACT-запись ушла в HEAD их fixup'ом 92ab49dc (смешанное авторство, зафиксировано); ВОССТАНОВЛЕНА утраченная там же запись ENIGMA_PROV_B (вербатим из 1e12c105, S343-реестр; их тотал-лауэркейс-инцидент удалил её вместе с правками Региона-B) — closes INV-FLAG-REGISTRY, COV-контур уведомлен этой строкой. Гейты: fix3 6/6, UE-сьюта 31/31, боевые 43/43, lint_flags 0 (registry=54), IPT 52/0

### Последние записи MUTATIONS.md:
  - (MUTATIONS.md не найден)

### Файлы с активными TODO/FIXME:
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\constants.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\constants.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\decision_context.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\intent_profile.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\vital_state.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\affect.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\cfrm.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\locomotion.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\npc_state.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\phase8.py

---

## #2 — АРХИТЕКТОР UI (pygame, рендеринг, визуал)

### Сейчас делает:
(не определено — обнови MUTATIONS.md)

### Состояние рендеринга (из последней сессии игры):
- NPC с известными координатами (0):
  - _(нет данных о координатах — SNAPSHOT-паттерн не сработал)_
- NPC без координат (lerp не работает, 0):
  - _(нет)_
- Граф-fallback локаций: нет

### Визуальные аномалии:
- spatial_fallback triggered: ✅ нет
- Узлы не найдены (NPC не могут добраться до цели): 0

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #3 — файлы backend/app/services/)_

---

## #3 — АРХИТЕКТОР СИМУЛЯЦИИ (NPC, тики, давление, решения)

### Сейчас делает:
(не определено — обнови MUTATIONS.md)

### Состояние симуляции (последняя сессия игры):

**Tick Pipeline:**
Тиков: 0 | Decisions > 0: 0/0 | LLM: 13 вызовов / 13 ответов | Симуляция: ✅ живёт
- LLM "Ничего не произошло": 0 раз
- LLM CJK-галлюцинации: 0 строк
- Стартап backend: ✅
- LLM сервер: ❌ (не доступен при старте)

**Предупреждения:**
  - _(нет)_

**Movement Pipeline (по NPC):**
_Нет данных по NPC_

**NPC с разрывом в pipeline (intent есть, traversal нет):**
  - _(нет разрывов в movement pipeline)_

### Каузальные разрывы:

_Каузальных разрывов не обнаружено_

### Архитектурный долг (не трогать без обсуждения):
- Stale Cognition: DecisionHub работает на state T-1. Требует ADR-059.
- Cognitive Overlay Layer: отдельный спринт.

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #2 — файлы frontend/)_