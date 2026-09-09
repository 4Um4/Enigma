# ENIGMA Session State — 2026-09-09 20:28

Кампания: `?` | Игрок: `?`

## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА

Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами → **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). У других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---

## DNA — МЕТРИКИ ЗДОРОВЬЯ СИСТЕМЫ

_Сессия: 2.7 мин | Тиков: 18 | LLM-вызовов: 58_

| Метрика | Значение | Δ от прошлой | Интерпретация для LLM |
|---------|----------|--------------|----------------------|
| **SHI** (Simulation Health) | 100% | → +0.0% | ✅ норма: NPC активно принимают решения |
| **NPI** (NPC Pipeline) | 71% | ↓ -14.3% | ⚠️ 5/7 NPC с координатами: есть потери в traversal |
| **OBI** (Obedience) | 0% | → +0.0% | нет директив в сессии — OBI не применим |
| **SCF** (Spatial Coherence) | 1.0 | → +0.0 | ✅ пространство целостно: граф загружен корректно |
| **ADR** (Debt Ratio) | 0.00 | → +0.0 | нет ADR-записей — невозможно оценить |
| **CVS** (Causal Velocity) | 21.18/мин | ↑ +9.6 | ✅ 21.18/мин: активная сессия |
| **PFI** (Pre-Bus Failure) | 0% | → +0.0% | ✅ норма: пред-шинных отказов нет — CDS видит всё |
| **Tracebacks** | 5 (AttrErr=0, TypeErr=0) | → | ⚠️ КРИТИЧНО: невидимые регрессии (Tracebacks) |
| **BCI** (Belief Crystallization) | 549 (idx=30.50) | → | ✅ Убеждения формируются |
| **BPI** (Break Progress) | 160 (broken=0) | → | ✅ Давление доходит |
| **NEI** (Need Urgency) | 0 (critical=0) | → | ⚠️ NPC слишком комфортны (NEI=0) |
| **DRI** (Response Integrity) | 100% | → +0.0% | ✅ LLM отвечает на все запросы |
| **DPI** (Dialogue Pipeline) | 100% | → +0.0% | ✅ Конвейер диалогов стабилен |

_История: `reports/dna_history.jsonl` — 1115 записей_

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
  - bac0c6d6 V.0.5.3.9.8_RoadMap_2: полное сохранение проекта (сессия 2026-09-05); актуализация версий до 0.5.3.9.8 (version.txt, pyproject, frontend/constants, README, ENIGMA_ROADMAP). Р-В (SpeechExposure, GC-DIALOGUE-01): SSOT exposure_radius в communication (лестница secret/whisper/normal/loud/shout/private; normal=6.0 — parity D1 с ACTION_PERCEPTION_RADIUS, loud=10.0 — D2); IntentEventAdapter D3: secret→whisper (адресат слышит вплотную), loud→public; DialogueMaterializer D4: солилоквий-сентинел → whisper + SSOT-радиус; WorkingMemory NPC_SPOKE: radius из SSOT (999-дефолт запрещён ADR-148); routes scene_state → единый приёмник GameLoop.save_scene_state (R2-В/S244, anti-writer G3, whitelist-семантика субсумирована by construction). Mypy-доводка 641→608: 33 мелочи закрыты без вмешательства в логику (аннотации __init__/update/_init_db/main, X|None-дефолты, no-any-return → bool()/float(), var-annotated словари, TYPE_CHECKING-совместимые импорты). Гейты: тесты Р-В micro 10/10, micro-suite 11/11, импорты ядра OK. Примечание: unstaged-патчи сессии восстановлены из байткод-анализа __pycache__ после случайного checkout — routes/working_memory_tick байт-в-байт, communication/adapter/materializer dis-эквивалентны (расхождение только в формулировках комментариев).
  - a92278cc P-A/P-B: speech-tube sanitation (soliloquy sentinel + write-gate + listener membrane)
  - b72a6eac S250: Embodied Constraint фронт закрыт за сессию (PRE-FLIGHT→V1→GREEN); процесс-урок: гейт≠барьер без exit-ветвления, патчи только БЫЛО/СТАЛО
  - 93d03fad ADR-O-383: §5d-строка закрытия Embodied Constraint (GREEN, гейт-цитаты, red-commit-уроки)
  - a0cc0d42 ADR-O-383 V1 fix2 + GREEN: модульные константы (F821 self закрыт), старый availability-хвост оракула удалён (immutable-evidence-маркер в файле); GC-09B-full GREEN — chronic-body→feasibility→behavior замкнут (RED→ADR→V1→GREEN за сессию). Гейты зелёные ДО коммита: ruff 0, файл-прогон 2/2, IPT 45/45

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
- NPC с известными координатами (5):
  - `guard_borko`: x=11.0 y=10.0
  - `merchant_goran`: x=7.8 y=5.8
  - `maid_lusya`: x=10.5 y=6.5
  - `blacksmith_orm`: x=5.5 y=6.0
  - `tavern_keeper_tornin`: x=10.5 y=3.0
- NPC без координат (lerp не работает, 2):
  - `thief_shadow` (intent=warn)
  - `player` (intent=flee)
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
Тиков: 18 | Decisions > 0: 5/18 | LLM: 58 вызовов / 56 ответов | Симуляция: ❌ МЕРТВА
- LLM "Ничего не произошло": 0 раз
- LLM CJK-галлюцинации: 0 строк
- Стартап backend: ✅
- LLM сервер: ❌ (не доступен при старте)

**Предупреждения:**
  - ⚠️ КРИТИЧНО: все тики вернули 0 decisions — симуляция заморожена

**Movement Pipeline (по NPC):**
| NPC | Intent | Score | Traversal | Координаты | Виден игроку |
|-----|--------|-------|-----------|------------|--------------|
| blacksmith_orm | request_service | 0.761 | ✅ | x=5.5 y=6.0 | ❌ |
| guard_borko | flee | 3.630 | ✅ | x=11.0 y=10.0 | ❌ |
| maid_lusya | flee | 3.739 | ✅ | x=10.5 y=6.5 | ❌ |
| merchant_goran | flee | 3.140 | ✅ | x=7.8 y=5.8 | ❌ |
| player | flee | 1.219 | ✅ | None | ❌ |
| tavern_keeper_tornin | flee | 3.066 | ✅ | x=10.5 y=3.0 | ❌ |
| thief_shadow | warn | 1.190 | ✅ | None | ❌ |

**NPC с разрывом в pipeline (intent есть, traversal нет):**
  - _(нет разрывов в movement pipeline)_

### Каузальные разрывы:

#### [BREAK-1] Симуляция заморожена
**Симптом:** все тики вернули 0 decisions
**Файл для проверки:** `backend/app/services/npc/decision_hub.py`
**PowerShell:** `Select-String -Path "backend/app/services/npc/decision_hub.py" -Pattern "def compute"`

### Архитектурный долг (не трогать без обсуждения):
- Stale Cognition: DecisionHub работает на state T-1. Требует ADR-059.
- Cognitive Overlay Layer: отдельный спринт.

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #2 — файлы frontend/)_