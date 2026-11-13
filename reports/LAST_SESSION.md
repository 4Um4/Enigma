# ENIGMA Session State — 2026-11-14 00:17

Кампания: `?` | Игрок: `?`

## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА

Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами → **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). У других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---

## DNA — МЕТРИКИ ЗДОРОВЬЯ СИСТЕМЫ

_Сессия: 1.6 мин | Тиков: 48 | LLM-вызовов: 4_

| Метрика | Значение | Δ от прошлой | Интерпретация для LLM |
|---------|----------|--------------|----------------------|
| **SHI** (Simulation Health) | 100% | → +0.0% | ✅ норма: NPC активно принимают решения |
| **NPI** (NPC Pipeline) | 100% | → +0.0% | ✅ 6/6 NPC с реальными координатами |
| **OBI** (Obedience) | 0% | → +0.0% | нет директив в сессии — OBI не применим |
| **SCF** (Spatial Coherence) | 1.0 | → +0.0 | ✅ пространство целостно: граф загружен корректно |
| **ADR** (Debt Ratio) | 0.00 | → +0.0 | нет ADR-записей — невозможно оценить |
| **CVS** (Causal Velocity) | 2.47/мин | ↑ +1.1 | ✅ 2.47/мин: активная сессия |
| **PFI** (Pre-Bus Failure) | 2% | ↓ +0.9% | ⚠️ 1 пред-шинных отказов — CDS слеп к части крахов |
| **Tracebacks** | 0 (AttrErr=0, TypeErr=0) | → | ✅ норма |
| **BCI** (Belief Crystallization) | 240 (idx=5.00) | → | ✅ Убеждения формируются |
| **BPI** (Break Progress) | 333 (broken=0) | → | ✅ Давление доходит |
| **NEI** (Need Urgency) | 0 (critical=0) | → | ⚠️ NPC слишком комфортны (NEI=0) |
| **DRI** (Response Integrity) | 100% | → +0.0% | ✅ LLM отвечает на все запросы |
| **DPI** (Dialogue Pipeline) | 100% | → +0.0% | ✅ Конвейер диалогов стабилен |

_История: `reports/dna_history.jsonl` — 1346 записей_

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
  - 862aaeba S425-errata: [ALARM] RESOLVED (WIP=67a13349+ad706efb); IPT 55/0/0 @ e9762397; drop one-shot scripts
  - 4f74171e docs(ADR-O-441): NPC Runtime Persistence Recovery — atlas entry + impact audit
  - a0de49ea S424-2: ResponseValidator — TZ priority 3 World-State Integrity checks
  - e9762397 S425: A3 INFRA CLOSED / formation -> A3.1 (doc-only, вариант D)
  - ad706efb S424: Lumimaid SSOT prompts + GBNF grammar — BIO 0.7544, CMP 0.4875, composite 62.15

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
- NPC с известными координатами (6):
  - `guard_borko`: x=36.6 y=9.4
  - `merchant_goran`: x=46.4 y=15.3
  - `maid_lusya`: x=35.4 y=9.2
  - `blacksmith_orm`: x=46.4 y=15.3
  - `thief_shadow`: x=67.0 y=11.0
  - `tavern_keeper_tornin`: x=31.5 y=10.5
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
Тиков: 48 | Decisions > 0: 2/48 | LLM: 4 вызовов / 0 ответов | Симуляция: ✅ живёт
- LLM "Ничего не произошло": 0 раз
- LLM CJK-галлюцинации: 0 строк
- Стартап backend: ✅
- LLM сервер: ❌ (не доступен при старте)

**Предупреждения:**
  - ⚠️ LLM вызывалась но ни разу не ответила — проверь llm_server
  - ⚠️ КРИТИЧНО: 1 пред-шинных отказов (pipeline=0, causality=0, phase8=1, tick_orch=0) — CDS слеп к этим багам без Инварианта 3

**Movement Pipeline (по NPC):**
| NPC | Intent | Score | Traversal | Координаты | Виден игроку |
|-----|--------|-------|-----------|------------|--------------|
| blacksmith_orm | help | 0.649 | ✅ | x=46.4 y=15.3 | ❌ |
| guard_borko | flee | 0.768 | ✅ | x=36.6 y=9.4 | ❌ |
| maid_lusya | flee | 1.337 | ✅ | x=35.4 y=9.2 | ❌ |
| merchant_goran | idle | 0.000 | ✅ | x=46.4 y=15.3 | ❌ |
| tavern_keeper_tornin | flee | 0.580 | ✅ | x=31.5 y=10.5 | ❌ |
| thief_shadow | observe | 0.417 | ✅ | x=67.0 y=11.0 | ❌ |

**NPC с разрывом в pipeline (intent есть, traversal нет):**
  - _(нет разрывов в movement pipeline)_

### Каузальные разрывы:

_Каузальных разрывов не обнаружено_

### Архитектурный долг (не трогать без обсуждения):
- Stale Cognition: DecisionHub работает на state T-1. Требует ADR-059.
- Cognitive Overlay Layer: отдельный спринт.

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #2 — файлы frontend/)_