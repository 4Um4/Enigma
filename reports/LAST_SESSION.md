# ENIGMA Session State — 2026-11-23 22:09

Кампания: `?` | Игрок: `?`

## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА

Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами → **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). У других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---

## DNA — МЕТРИКИ ЗДОРОВЬЯ СИСТЕМЫ

_Сессия: 0.9 мин | Тиков: 46 | LLM-вызовов: 4_

| Метрика | Значение | Δ от прошлой | Интерпретация для LLM |
|---------|----------|--------------|----------------------|
| **SHI** (Simulation Health) | 100% | → +0.0% | ✅ норма: NPC активно принимают решения |
| **NPI** (NPC Pipeline) | 86% | → +0.0% | ⚠️ 6/7 NPC с координатами: есть потери в traversal |
| **OBI** (Obedience) | 0% | → +0.0% | нет директив в сессии — OBI не применим |
| **SCF** (Spatial Coherence) | 1.0 | → +0.0 | ✅ пространство целостно: граф загружен корректно |
| **ADR** (Debt Ratio) | 0.00 | → +0.0 | нет ADR-записей — невозможно оценить |
| **CVS** (Causal Velocity) | 4.27/мин | ↑ +0.9 | ✅ 4.27/мин: активная сессия |
| **PFI** (Pre-Bus Failure) | 0% | → +0.0% | ✅ норма: пред-шинных отказов нет — CDS видит всё |
| **Tracebacks** | 0 (AttrErr=0, TypeErr=0) | → | ✅ норма |
| **BCI** (Belief Crystallization) | 336 (idx=7.30) | → | ✅ Убеждения формируются |
| **BPI** (Break Progress) | 321 (broken=0) | → | ✅ Давление доходит |
| **NEI** (Need Urgency) | 0 (critical=0) | → | ⚠️ NPC слишком комфортны (NEI=0) |
| **DRI** (Response Integrity) | 100% | → +0.0% | ✅ LLM отвечает на все запросы |
| **DPI** (Dialogue Pipeline) | 100% | → +0.0% | ✅ Конвейер диалогов стабилен |

_История: `reports/dna_history.jsonl` — 1410 записей_

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
  - 70080db9 Волна B финал: продюсер npc_reactions нормализован к строкам (F-1, B-FIN1); release/idle-guards реестра SQ (B5-FIN); unit-тесты Spatial Context Unification (12)
  - f5e4d339 chore: релиз V.0.5.4.7.1 Говори!_3 — полное сохранение локального проекта
  - bcf55957 feat(epistemic): integrate recursive attribution with DecisionHub (EPISTEMIC-005-07)
  - 4e45cc95 feat(epistemic): implement recursive attribution model (EPISTEMIC-005-06)
  - 369eb1bd fix: mypy type annotations and ruff W293/I001/W292 in epistemology.py and epistemic_store.py

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
  - `guard_borko`: x=28.4 y=7.3
  - `merchant_goran`: x=38.3 y=16.5
  - `maid_lusya`: x=33.4 y=7.4
  - `blacksmith_orm`: x=42.2 y=15.7
  - `thief_shadow`: x=63.1 y=11.6
  - `tavern_keeper_tornin`: x=41.3 y=6.9
- NPC без координат (lerp не работает, 1):
  - `player` (intent=?)
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
Тиков: 46 | Decisions > 0: 3/46 | LLM: 4 вызовов / 8 ответов | Симуляция: ✅ живёт
- LLM "Ничего не произошло": 0 раз
- LLM CJK-галлюцинации: 0 строк
- Стартап backend: ✅
- LLM сервер: ❌ (не доступен при старте)

**Предупреждения:**
  - _(нет)_

**Movement Pipeline (по NPC):**
| NPC | Intent | Score | Traversal | Координаты | Виден игроку |
|-----|--------|-------|-----------|------------|--------------|
| blacksmith_orm | help | 0.568 | ✅ | x=42.2 y=15.7 | ❌ |
| guard_borko | flee | 0.835 | ✅ | x=28.4 y=7.3 | ❌ |
| maid_lusya | flee | 1.095 | ✅ | x=33.4 y=7.4 | ❌ |
| merchant_goran | flee | 0.611 | ✅ | x=38.3 y=16.5 | ❌ |
| player | ? | 0.000 | ✅ | None | ❌ |
| tavern_keeper_tornin | talk | 0.749 | ✅ | x=41.3 y=6.9 | ❌ |
| thief_shadow | observe | 0.629 | ✅ | x=63.1 y=11.6 | ❌ |

**NPC с разрывом в pipeline (intent есть, traversal нет):**
  - _(нет разрывов в movement pipeline)_

### Каузальные разрывы:

_Каузальных разрывов не обнаружено_

### Архитектурный долг (не трогать без обсуждения):
- Stale Cognition: DecisionHub работает на state T-1. Требует ADR-059.
- Cognitive Overlay Layer: отдельный спринт.

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #2 — файлы frontend/)_