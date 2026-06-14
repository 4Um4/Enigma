# ENIGMA Session State — 2026-06-14 22:29

Кампания: `Open_road` | Игрок: `Венус`

## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА

Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами → **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). У других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---

## DNA — МЕТРИКИ ЗДОРОВЬЯ СИСТЕМЫ

_Сессия: 0.6 мин | Тиков: 0 | LLM-вызовов: 4_

| Метрика | Значение | Δ от прошлой | Интерпретация для LLM |
|---------|----------|--------------|----------------------|
| **SHI** (Simulation Health) | 0% | → +0.0% | ⛔ МЕРТВА: решений нет. Проверь DecisionHub.compute() |
| **NPI** (NPC Pipeline) | 100% | → +0.0% | ✅ 2/2 NPC с реальными координатами |
| **OBI** (Obedience) | 0% | → +0.0% | нет директив в сессии — OBI не применим |
| **SCF** (Spatial Coherence) | 1.0 | ↑ +1.0 | ✅ пространство целостно: граф загружен корректно |
| **ADR** (Debt Ratio) | 0.00 | → +0.0 | нет ADR-записей — невозможно оценить |
| **CVS** (Causal Velocity) | 7.27/мин | ↑ +5.4 | ✅ 7.27/мин: активная сессия |
| **PFI** (Pre-Bus Failure) | 100% | → +0.0% | ⛔ 1 пред-шинных отказов — pipeline молча умирает, CDS слеп |

**Системные сигналы (требуют внимания):**
- SHI=0% при активных LLM-вызовах: игрок взаимодействует но NPC не решают — разрыв между R3_DIRECT и DecisionHub

_История: `reports/dna_history.jsonl` — 581 записей_

## #1 — АРХИТЕКТОР КОДА (патчи, файлы, архитектура)

### Сейчас делает:
72. ❌ `MovementIntent` без поля `domain`

### Активные баги требующие патча:
_(баги не обнаружены в этой сессии)_

### Последние изменения (git log -5):
  - abcf445 Save V.0.5.3.1.6 sky and earth
  - 95e3c20 docs: add branch DNA metric timeline
  - e898e8d snapshot: publish V.0.5.3.1.5 The Fool v2
  - 83e785c snapshot: update campaign_state.json
  - 6052a7f chore: ensure usurper.bundle is managed by git-lfs

### Последние записи MUTATIONS.md:
  - 70. ❌ Коммит состояния с NaN или sum(drives) != 1.0 (OntologyViolationError)
  - 71. ❌ Viability veto через `_drf_killed` или парсинг строк (только IntentDomain gate)
  - 72. ❌ `MovementIntent` без поля `domain`

### Файлы с активными TODO/FIXME:
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\calendar.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\behavior.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\constants.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\decision_context.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\embodied_trace.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\intent_profile.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\movement.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\domain\vital_state.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\affect.py
  - C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\cfrm.py

---

## #2 — АРХИТЕКТОР UI (pygame, рендеринг, визуал)

### Сейчас делает:
72. ❌ `MovementIntent` без поля `domain`

### Состояние рендеринга (из последней сессии игры):
- NPC с известными координатами (2):
  - `blacksmith_orm`: x=10.5 y=5.0
  - `tavern_keeper_tornin`: x=4.5 y=2.5
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
72. ❌ `MovementIntent` без поля `domain`

### Состояние симуляции (последняя сессия игры):

**Tick Pipeline:**
Тиков: 0 | Decisions > 0: 0/0 | LLM: 4 вызовов / 4 ответов | Симуляция: ✅ живёт
- LLM "Ничего не произошло": 0 раз
- LLM CJK-галлюцинации: 0 строк
- Стартап backend: ✅
- LLM сервер: ✅

**Предупреждения:**
  - ⚠️ КРИТИЧНО: 1 пред-шинных отказов (pipeline=0, causality=0, phase8=0, tick_orch=1) — CDS слеп к этим багам без Инварианта 3

**Movement Pipeline (по NPC):**
| NPC | Intent | Score | Traversal | Координаты | Виден игроку |
|-----|--------|-------|-----------|------------|--------------|
| blacksmith_orm | ? | 0.000 | ❌ | x=10.5 y=5.0 | ❌ |
| tavern_keeper_tornin | ? | 0.000 | ❌ | x=4.5 y=2.5 | ❌ |

**NPC с разрывом в pipeline (intent есть, traversal нет):**
  - _(нет разрывов в movement pipeline)_

### Каузальные разрывы:

_Каузальных разрывов не обнаружено_

### Архитектурный долг (не трогать без обсуждения):
- Stale Cognition: DecisionHub работает на state T-1. Требует ADR-059.
- Cognitive Overlay Layer: отдельный спринт.

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #2 — файлы frontend/)_