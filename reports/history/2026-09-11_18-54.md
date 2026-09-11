# ENIGMA Session State — 2026-09-11 18:54

Кампания: `?` | Игрок: `?`

## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА

Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами → **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). У других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---

## DNA — МЕТРИКИ ЗДОРОВЬЯ СИСТЕМЫ

_Сессия: 0.1 мин | Тиков: 0 | LLM-вызовов: 0_

| Метрика | Значение | Δ от прошлой | Интерпретация для LLM |
|---------|----------|--------------|----------------------|
| **SHI** (Simulation Health) | 0% | ↓ -100.0% | ⛔ МЕРТВА: решений нет. Проверь DecisionHub.compute() |
| **NPI** (NPC Pipeline) | 0% | ↓ -71.4% | нет данных о NPC |
| **OBI** (Obedience) | 0% | → +0.0% | нет директив в сессии — OBI не применим |
| **SCF** (Spatial Coherence) | 1.0 | → +0.0 | ✅ пространство целостно: граф загружен корректно |
| **ADR** (Debt Ratio) | 0.00 | → +0.0 | нет ADR-записей — невозможно оценить |
| **CVS** (Causal Velocity) | 0.00/мин | ↓ -21.2 | LLM не вызывалась: сессия без действий игрока |
| **PFI** (Pre-Bus Failure) | 0% | → +0.0% | ✅ норма: пред-шинных отказов нет — CDS видит всё |
| **Tracebacks** | 0 (AttrErr=0, TypeErr=0) | → | ✅ норма |
| **BCI** (Belief Crystallization) | 0 (idx=0.00) | → | ⚠️ Память не кристаллизуется (BCI=0) |
| **BPI** (Break Progress) | 0 (broken=0) | → | ⚠️ NPC не ломаются (BPI=0) |
| **NEI** (Need Urgency) | 0 (critical=0) | → | ⚠️ NPC слишком комфортны (NEI=0) |
| **DRI** (Response Integrity) | 100% | → +0.0% | ✅ LLM отвечает на все запросы |
| **DPI** (Dialogue Pipeline) | 100% | → +0.0% | ✅ Конвейер диалогов стабилен |

**Системные сигналы (требуют внимания):**
- NPI упал на -71%: spatial pipeline деградировал между сессиями

_История: `reports/dna_history.jsonl` — 1117 записей_

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
  - e1182e95 V.0.5.4.0.0_Потребности_2: полное сохранение проекта; актуализация версий до 0.5.4.0.0 (version.txt, pyproject, frontend/constants, README). Mypy-доводка 584->545: 39 мелочей закрыты без вмешательства в логику (Optional-дефолты, -> None, no-any-return через bool()/float()/cast(), var-annotated словари, class-level аттрибуты singleton, аннотации choice/choices). Гейты: ruff по всем 15 затронутым файлам OK, импорты ядра OK, 179 pytest passed (combat/content_policy/action_commitment/decision_calibration/commitment_ssm/speech_exposure micro). Долг сессии: артефакты Р-Г GC-DIALOGUE-01 (npc_dialogue_subscriber радиус-журнал, test_self_talk_sentinel регрессия), логи аудита/сцен/world_tick, diagnostics-пробы, ADR-O-384/385 impact, ТЗ mvp_secret_tavern.
  - b702d4fc chore: догоняющие артефакты сессии (логи аудита/сцен, world_tick) + обновление eat_vertical_test после прогона sandbox
  - 7b4b4805 Living Activity R1: роль переживает round-trip (to_persistence_dict пишет current_role, from_legacy читает runtime-роль с фолбэком status_profile.title — гейт COMBAT_CAPABLE_ROLES больше не видит пустую роль, 62 ambush Торнина закрыты); мини-ADR #3: EventType.ACTIVITY_OUTCOME (observation-only, эмиттер _publish_outcome, проводка в память — открытый пункт); наблюдаемая занятость: _emit_label_change пишет npc_positions.activity (сон-прецедент), r3_direct_builder читает ярлык; + test_activity_visibility (25/25 micro), sandbox-сценарий eat_vertical_test
  - 182024ac chore: удалить mypy_report.txt из репозитория (временный артефакт mypy-прогона, путь закрыт в .gitignore)
  - 84b5e01a V.0.5.3.9.9_Потребности_1: полное сохранение проекта (сессия 2026-09-09); актуализация версий до 0.5.3.9.9 (version.txt, pyproject, frontend/constants, README). Living Activity: домен activity/desire, desire_generator, activity_catalog, activity_lifecycle_service + тесты. Mypy-доводка 604→573: 31 мелочь закрыта без вмешательства в логику (аннотации lifespan/root/load_npcs, _llama_state dict[str, Any], var-annotated в body/time_skip_executor/experiment_runner/content_policy/adr_parser/layered_memory, str | None в routes). Гейты: импорты ядра OK, micro-suite 14/14.

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
Тиков: 0 | Decisions > 0: 0/0 | LLM: 0 вызовов / 0 ответов | Симуляция: ✅ живёт
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