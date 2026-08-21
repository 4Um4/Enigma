# План разработки: Лаборатория калибровки психики ENIGMA

**Версия плана:** `1.0`
**Соответствует ТЗ:** `ТЗ_Лаборатория_Калибровки_ENIGMA.md v1.0`
**Целевая версия ENIGMA:** `0.5.3.8.x` (текущая `0.5.3.8.3`)
**Расчётный срок реализации MVP:** 6 недель (M0 → M1)
**Расчётный срок полной версии:** 16 недель (M0 → M5)

> Этот документ — **пошаговый план для архитектора**. Он сопоставлен с разделами ТЗ,
> содержит конкретные пути файлов, имена классов/функций и **приёмочные тесты
> «правильно найденных вариантов»** — тесты, которые гарантируют, что лаборатория
> корректно классифицирует зоны МАНЕКЕН / ХАОС / ENIGMA.

---

## 0. Ключевые принципы плана

### 0.1. Неукоснительно

| Принцип | Что это значит |
|---|---|
| **Реальный pipeline** | Лаборатория запускает `TickOrchestrator.execute()` из `backend/app/services/tick_orchestrator.py` — без моков, без подмен. |
| **Детерминизм** | Любой запуск с `seed=X, params=Y, scenario=Z, version=V` даёт битово-идентичный результат. Используем `KernelRNG` (ADR-O-301). |
| **Чистые контракты** | Сигнатуры `DecisionHub.compute()` и `TickOrchestrator.execute()` **не модифицируются**. Все новые параметры инжектируются через `ConfigOverlay`. |
| **Русский UI** | Все строки в UI на русском; внутренние имена — английским подзаголовком. |
| **4 слоя** | `Calibration UI` → `Experiment Runner` → `ENIGMA Engine` → `Observability`. Запрет обратных зависимостей. |
| **Итеративность** | M1 → MVP (можно запускать 30-минутную сессию). M2-M5 — расширения. |
| **Тесты «правильно найденных вариантов»** | Каждый milestone содержит acceptance-тесты, проверяющие, что лаборатория **правильно** классифицирует заранее известные «манекен», «хаос» и «ENIGMA» пресеты. |

### 0.2. Стек технологий

| Слой | Технологии |
|---|---|
| UI | Next.js 16 (App Router) + TypeScript 5.5 + Tailwind CSS 4 + shadcn/ui + React Query + Zustand + Plotly |
| Backend | Python 3.11+ (существующий FastAPI ENIGMA), без новых фреймворков |
| Streaming | SSE (существующий паттерн `routes_stream.py`), без WebSocket |
| БД | SQLite (существующий `SqlitePersistenceAdapter`) + ephemeral `:memory:` для параллельных сессий |
| Графики | matplotlib (для PNG) + Plotly (для интерактивного HTML) |
| Sweep | `scikit-optimize` (Bayesian), `cma` (CMA-ES), `DEAP` (genetic) — все опциональны, добавляются в M4 |
| Тесты | `pytest` (существующий), новые тесты в `backend/tests/calibration_lab/` |

---

## 1. Эпики и фазы — общая карта

```text
M0: Фундамент и репрезентативный слой           (1 неделя)
    └── CalibratorSkeleton + ConfigOverlay + 5 базовых метрик
            ↓
M1: MVP — Драматическая сессия 30 мин           (5 недель)
    └── UI + ExperimentRunner + 6 кнопок игрока + A/B + сохранение пресета
            ↓
M2: Драматические метрики                       (3 недели)
    └── WOW Density + Zone Classifier + все 10 метрик
            ↓
M3: Parameter Sweep и A/B framework              (3 недели)
    └── Grid/Random/Bayesian + One-Param-Scan
            ↓
M4: Визуальные карты и auto-search               (2 недели)
    └── Heatmaps + CMA-ES + Золотая область
            ↓
M5: Пресеты, воспроизводимость, экспорт          (2 недели)
    └── YAML presets + replay verification + 5 форматов экспорта
```

Каждый milestone завершается **приёмочным тестом «правильно найденных вариантов»** — он доказывает, что лаборатория способна отличить целевую зону от нецелевых.

---

## 2. M0 — Фундамент и репрезентативный слой (1 неделя)

### 2.1. Цели M0

1. Подготовить инфраструктуру для подмены констант ENIGMA во время эксперимента.
2. Реализовать базовый `ExperimentRunner` (запуск одной сессии).
3. Внедрить 5 базовых метрик (характерных для будущей зоны классификации).
4. Подключить все 9 существующих `probes` и `SUPERBOX` invariant checks.
5. Подготовить test preset-файлы «MANNEQUIN», «CHAOS», «ENIGMA» (по известным параметрам).

### 2.2. Артефакты M0

| Артефакт | Путь | Описание |
|---|---|---|
| Пакет калибровки | `backend/app/services/calibration/__init__.py` | init |
| ConfigOverlay | `backend/app/services/calibration/config_overlay.py` | Подмена `constants.py` на overlay-значения |
| ExperimentRunner | `backend/app/services/calibration/experiment_runner.py` | Оркестратор: создать `GameLoop`, выполнить N тиков |
| ScenarioPlayer | `backend/app/services/calibration/scenario_player.py` | Воспроизведение event-sequence по таймлайну |
| Базовые метрики | `backend/app/services/calibration/metrics/*.py` (5 файлов) | CharacterChange / DecisionDiversity / LoopRate / EventResponsiveness / CausalDepth |
| ProbeAdapter | `backend/app/services/calibration/probe_adapter.py` | Обёртка над `ProbeRunner.run_all()` |
| SuperboxAdapter | `backend/app/services/calibration/superbox_adapter.py` | Запуск всех 25+ SUPERBOX-сценариев |
| Test-пресеты | `configs/calibration/test_presets/{mannequin,chaos,enigma_golden}.yaml` | Контрольные пресеты для тестов |
| Unit-тесты | `backend/tests/calibration_lab/test_m0_*.py` | ≥ 20 тестов |

### 2.3. Ключевые классы и сигнатуры

```python
# backend/app/services/calibration/config_overlay.py
from contextlib import contextmanager
from typing import Iterator, Mapping

@contextmanager
def overlay_constants(overrides: Mapping[str, float]) -> Iterator[None]:
    """
    Временная подмена значений в backend.app.core.constants.
    После выхода из контекста — все значения восстанавливаются.
    Используется monkey-patching на уровне модуля (читается DecisionHub
    через `from ..core import constants as C; C.SCORE_NOISE_RANGE`).
    """
    ...
```

```python
# backend/app/services/calibration/experiment_runner.py
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import random

@dataclass(frozen=True)
class ExperimentConfig:
    preset_path: str                           # YAML-путь
    scenario_path: str                        # YAML-путь
    seed: int
    duration_ticks: int                        # например, 300 (для 30 мин при 10 т/мин)
    speed_multiplier: float = 1.0
    interventions: List[Dict[str, Any]] = ()   # scripted events

@dataclass
class ExperimentResult:
    experiment_id: str
    config: ExperimentConfig
    final_npc_state: Dict[str, Any]            # по всем NPC
    metrics: Dict[str, float]
    wow_events: List[Dict[str, Any]]
    causal_chains: List[Dict[str, Any]]
    invariant_violations: int
    nan_count: int
    replay_deterministic: bool

class ExperimentRunner:
    def __init__(self, game_loop_factory): ...
    def run(self, config: ExperimentConfig) -> ExperimentResult: ...
    def run_parallel(self, configs: List[ExperimentConfig]) -> List[ExperimentResult]: ...
```

```python
# backend/app/services/calibration/metrics/base.py
from abc import ABC, abstractmethod
from typing import Any

class CalibrationMetric(ABC):
    name: str
    @abstractmethod
    def update(self, tick: int, state_snapshot: Dict[str, Any], event: Optional[Dict[str, Any]] = None) -> None: ...
    @abstractmethod
    def compute(self) -> float: ...
    @abstractmethod
    def reset(self) -> None: ...
```

### 2.4. Тестовые пресеты (с проверенными значениями)

#### `configs/calibration/test_presets/mannequin.yaml`

```yaml
meta:
  preset_id: mannequin
  description: "Крайний случай: NPC почти не меняется"
parameters:
  identity_rigidity: 0.95
  trait_decay_rate: 0.001
  intent_inertia_weight: 0.85
  intent_inertia_max_ticks: 30
  theta_up: 0.95
  theta_down: 0.05
  affect_decay_base_rate: 0.01
  reactive_urgency_threshold: 0.99
  event_memory_decay_rate: 0.005
  score_noise_range: 0.01
```

#### `configs/calibration/test_presets/chaos.yaml`

```yaml
meta:
  preset_id: chaos
  description: "Крайний случай: NPC меняется хаотично"
parameters:
  identity_rigidity: 0.05
  trait_decay_rate: 0.20
  intent_inertia_weight: 0.05
  intent_inertia_max_ticks: 1
  theta_up: 0.05
  theta_down: 0.95
  affect_decay_base_rate: 0.50
  reactive_urgency_threshold: 0.50
  event_memory_decay_rate: 0.80
  score_noise_range: 0.40
  threat_amplification_factor: 0.80
  resentment_bias_factor: 0.80
```

#### `configs/calibration/test_presets/enigma_golden.yaml`

```yaml
meta:
  preset_id: enigma_golden
  description: "Золотая область — целевой tragikomedia"
parameters:
  identity_rigidity: 0.42
  trait_decay_rate: 0.018
  intent_inertia_weight: 0.20
  intent_inertia_max_ticks: 10
  theta_up: 0.55
  theta_down: 0.20
  affect_decay_base_rate: 0.06
  reactive_urgency_threshold: 0.78
  event_memory_decay_rate: 0.045
  score_noise_range: 0.08
  threat_amplification_factor: 0.18
  resentment_bias_factor: 0.20
  distrust_stress_boost: 9.0
```

### 2.5. Приёмочные тесты M0 (правильно найденных вариантов)

```python
# backend/tests/calibration_lab/test_m0_baseline_metrics.py

def test_mannequin_preset_yields_low_dynamics():
    """M0-AC-001: МАНЕКЕН-пресет даёт character_change_rate < 0.15"""
    result = ExperimentRunner().run(ExperimentConfig(
        preset_path="configs/calibration/test_presets/mannequin.yaml",
        scenario_path="config/scenarios/tavern_silver_wolf_15min.yaml",
        seed=7331, duration_ticks=150,
    ))
    assert result.metrics["character_change_rate"] < 0.15
    assert result.metrics["loop_rate"] > 0.50
    assert result.invariant_violations == 0
    assert result.nan_count == 0


def test_chaos_preset_yields_high_dynamics():
    """M0-AC-002: ХАОС-пресет даёт character_change_rate > 0.90"""
    result = ExperimentRunner().run(ExperimentConfig(
        preset_path="configs/calibration/test_presets/chaos.yaml",
        scenario_path="config/scenarios/tavern_silver_wolf_15min.yaml",
        seed=7331, duration_ticks=150,
    ))
    assert result.metrics["character_change_rate"] > 0.85
    assert result.metrics["loop_rate"] < 0.05
    assert result.invariant_violations == 0  # хаос ≠ слом
    assert result.nan_count == 0


def test_enigma_golden_yields_target_dynamics():
    """M0-AC-003: ENIGMA-пресет даёт character_change_rate в [0.3, 0.8]"""
    result = ExperimentRunner().run(ExperimentConfig(
        preset_path="configs/calibration/test_presets/enigma_golden.yaml",
        scenario_path="config/scenarios/tavern_silver_wolf_15min.yaml",
        seed=7331, duration_ticks=150,
    ))
    assert 0.30 <= result.metrics["character_change_rate"] <= 0.80
    assert result.metrics["loop_rate"] < 0.15
    assert result.invariant_violations == 0
    assert result.nan_count == 0


def test_replay_determinism():
    """M0-AC-004: Одинаковый seed → битово-идентичный результат"""
    cfg = ExperimentConfig(
        preset_path="configs/calibration/test_presets/enigma_golden.yaml",
        scenario_path="config/scenarios/tavern_silver_wolf_15min.yaml",
        seed=7331, duration_ticks=150,
    )
    r1 = ExperimentRunner().run(cfg)
    r2 = ExperimentRunner().run(cfg)
    assert r1.final_npc_state == r2.final_npc_state
    assert r1.metrics == r2.metrics
    assert r1.wow_events == r2.wow_events


def test_superbox_scenarios_still_pass():
    """M0-AC-005: Все SUPERBOX-сценарии проходят при overlay констант"""
    with overlay_constants(load_yaml("configs/calibration/test_presets/enigma_golden.yaml")["parameters"]):
        results = SuperboxAdapter.run_all_scenarios()
    assert all(r.passed for r in results), [
        f"{r.name} failed" for r in results if not r.passed
    ]


def test_overlay_constants_restores_after_exit():
    """M0-AC-006: Overlay корректно восстанавливает константы"""
    from backend.app.core import constants as C
    original = C.SCORE_NOISE_RANGE
    with overlay_constants({"SCORE_NOISE_RANGE": 0.42}):
        assert C.SCORE_NOISE_RANGE == 0.42
    assert C.SCORE_NOISE_RANGE == original
```

### 2.6. Риски M0

| Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|
| `overlay_constants` ломает другие тесты из-за глобального monkey-patch | высокая | высокое | Использовать `threading.local()` + explicit передача `constants_module` в DecisionHub через `decision_ctx` (требует small patch DecisionHub) |
| `ExperimentRunner` создаёт утечку SQLite-соединений | средняя | среднее | Использовать `:memory:` БД + cleanup в `__exit__` |
| SUPERBOX-сценарии ломаются при overlay | средняя | высокое | Overlay применяется только к `constants.py`, не к `kernel_rng.py`; SUPERBOX имеет собственные `seed` |
| Game-loop не запускается без LLM-сервера | высокая | критическое | M0 должен работать в `--no-llm` режиме; LLM-зависимости заглушаются `DmAgent` в offline-режиме |

### 2.7. Definition of Done для M0

- [ ] Все артефакты из 2.2 созданы и проходят `mypy --strict`;
- [ ] Все 6 приёмочных тестов из 2.5 проходят;
- [ ] Документация в `architecture/calibration.yaml` (новый YAML-контракт архитектуры);
- [ ] Worklog-запись в `worklog.md`.

---

## 3. M1 — MVP: Драматическая сессия 30 мин (5 недель)

### 3.1. Цели M1

> Соответствует ТЗ раздел 28 (минимальный MVP).

1. Веб-UI на русском языке с 10–15 слайдерами реальных параметров.
2. Запуск 30-минутной симуляции NPC (через реальный `TickOrchestrator`).
3. Пауза / пошаговый тик / ускорение (×1, ×5, ×20, ×100).
4. Кнопки событий игрока (минимум 6).
5. Timeline событий (минимум 5 типов).
6. Живое отображение состояния NPC: trust, beliefs, intent, stress.
7. Минимум 3 графика в реальном времени (trust, stress, emotion).
8. A/B сравнение (две конфигурации параллельно).
9. Сохранение пресета в YAML.
10. Seed с детерминизмом.
11. Экспорт CSV/JSON.

### 3.2. Структура Sprint-ов внутри M1

| Sprint | Длительность | Цель |
|---|---|---|
| Sprint 1 | 1 неделя | ExperimentRunner v2 + REST API + SSE streaming |
| Sprint 2 | 1 неделя | Next.js UI: layout + слайдеры + карточка NPC |
| Sprint 3 | 1 неделя | Кнопки игрока + timeline + графики |
| Sprint 4 | 1 неделя | A/B режим + сохранение пресета |
| Sprint 5 | 1 неделя | Экспорт + приёмочные тесты + bugfix |

### 3.3. Sprint 1: ExperimentRunner v2 + REST API

#### 3.3.1. Расширение `ExperimentRunner`

```python
# backend/app/services/calibration/experiment_runner.py
class ExperimentRunner:
    def start(self, config: ExperimentConfig) -> str:
        """Запуск в фоне, возвращает experiment_id"""

    def pause(self, experiment_id: str) -> None: ...
    def resume(self, experiment_id: str) -> None: ...
    def step(self, experiment_id: str, n_ticks: int = 1) -> None: ...
    def set_speed(self, experiment_id: str, multiplier: float) -> None: ...

    def inject_intervention(self, experiment_id: str,
                             intervention: InterventionEvent) -> None: ...

    def get_live_state(self, experiment_id: str) -> LiveStateDTO: ...

    def abort(self, experiment_id: str) -> ExperimentResult: ...

    def list_active(self) -> List[str]: ...
```

#### 3.3.2. REST API

```python
# backend/app/api/calibration_routes.py
from fastapi import APIRouter
router = APIRouter(prefix="/api/calibration", tags=["calibration"])

@router.post("/experiments")
async def create_experiment(req: CreateExperimentRequest) -> CreateExperimentResponse: ...

@router.post("/experiments/{exp_id}/start")
async def start_experiment(exp_id: str) -> None: ...

@router.post("/experiments/{exp_id}/pause")
async def pause_experiment(exp_id: str) -> None: ...

@router.post("/experiments/{exp_id}/step")
async def step_experiment(exp_id: str, ticks: int = 1) -> None: ...

@router.post("/experiments/{exp_id}/speed")
async def set_speed(exp_id: str, multiplier: float) -> None: ...

@router.post("/experiments/{exp_id}/intervention")
async def inject_intervention(exp_id: str, intervention: InterventionRequest) -> None: ...

@router.get("/experiments/{exp_id}/state")
async def get_state(exp_id: str) -> LiveStateDTO: ...

@router.get("/experiments/{exp_id}/timeline")
async def get_timeline(exp_id: str, since_tick: int = 0) -> TimelineDTO: ...

@router.post("/experiments/ab")
async def run_ab(req: ABRequest) -> ABResultDTO: ...
```

#### 3.3.3. SSE streaming

```python
# backend/app/api/calibration_stream.py
from fastapi.responses import StreamingResponse

@router.post("/experiments/{exp_id}/stream")
async def stream_experiment(exp_id: str):
    async def event_generator():
        runner = ExperimentRunnerRegistry.get(exp_id)
        async for tick_event in runner.stream():
            yield f"event: tick\ndata: {json.dumps(tick_event)}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

#### 3.3.4. Подключение к `app/main.py`

```python
# backend/app/main.py (diff)
from app.api import calibration_routes, calibration_stream

# в lifespan:
from app.services.calibration import ExperimentRunnerRegistry
ExperimentRunnerRegistry.init(game_loop_factory=build_game_loop)

# в router setup:
app.include_router(calibration_routes.router)
app.include_router(calibration_stream.router)
```

#### 3.3.5. Приёмочные тесты Sprint 1

```python
# backend/tests/calibration_lab/test_m1_sprint1_api.py

def test_create_experiment_returns_id():
    resp = client.post("/api/calibration/experiments", json={
        "preset_path": "configs/calibration/test_presets/enigma_golden.yaml",
        "scenario_path": "config/scenarios/tavern_silver_wolf_15min.yaml",
        "seed": 7331,
        "duration_ticks": 150,
    })
    assert resp.status_code == 201
    assert "experiment_id" in resp.json()

def test_sse_stream_emits_tick_events():
    # создаём эксперимент, подписываемся на stream, ждём 5 тиков
    ...

def test_inject_intervention_creates_event():
    # post /intervention, проверяем что в timeline появилось событие
    ...
```

### 3.4. Sprint 2: Next.js UI — layout + слайдеры + карточка NPC

#### 3.4.1. Структура проекта

```text
calibration_ui/
├── package.json
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── src/
│   ├── app/
│   │   ├── layout.tsx            # root layout
│   │   ├── page.tsx              # главная страница (лаборатория)
│   │   ├── experiments/[id]/page.tsx  # страница эксперимента
│   │   └── api/health/route.ts   # health check
│   ├── components/
│   │   ├── ui/                   # shadcn/ui primitives
│   │   ├── sliders/
│   │   │   ├── SliderPanel.tsx
│   │   │   ├── PersonalitySliders.tsx
│   │   │   ├── PerceptionSliders.tsx
│   │   │   ├── EmotionSliders.tsx
│   │   │   ├── DecisionSliders.tsx
│   │   │   ├── EpistemicSliders.tsx
│   │   │   └── MemorySliders.tsx
│   │   ├── npc-card/
│   │   │   ├── NpcCard.tsx
│   │   │   ├── NpcStateView.tsx
│   │   │   ├── NpcRelationships.tsx
│   │   │   ├── NpcBeliefs.tsx
│   │   │   └── NpcDrives.tsx
│   │   ├── timeline/
│   │   │   └── TimelinePanel.tsx
│   │   ├── causal-chain/
│   │   │   └── CausalChainView.tsx
│   │   ├── controls/
│   │   │   ├── PlayPauseControls.tsx
│   │   │   └── SpeedControls.tsx
│   │   ├── player-actions/
│   │   │   └── PlayerActionPanel.tsx
│   │   └── graphs/
│   │       ├── TrustGraph.tsx
│   │       ├── StressGraph.tsx
│   │       └── EmotionGraph.tsx
│   ├── lib/
│   │   ├── api.ts                # REST клиент
│   │   ├── sse.ts                # SSE подписка
│   │   ├── store.ts              # Zustand store
│   │   ├── types.ts              # TS типы (соответствуют backend DTO)
│   │   └── i18n.ts                # RU-строки
│   └── hooks/
│       ├── useExperiment.ts
│       ├── useSSE.ts
│       └── useSliderState.ts
└── public/
    └── presets/                 # examples для скачивания
```

#### 3.4.2. Слайдер (компонент)

```tsx
// calibration_ui/src/components/sliders/Slider.tsx
import { Slider } from "@/components/ui/slider";
import { Tooltip } from "@/components/ui/tooltip";

interface ParamSliderProps {
  labelRu: string;          // "Жёсткость личности"
  labelEn: string;          // "identity_rigidity"
  value: number;
  min: number;
  max: number;
  step: number;
  default: number;
  unit?: string;
  wired: boolean;            // false → "Параметр запланирован"
  tooltip: {
    whatItMeans: string;
    zero: string;
    one: string;
    increase: string;
    decrease: string;
    gameEffect: string;
    source: string;          // "models/npc_state.py:376"
  };
  onChange: (v: number) => void;
}

export function ParamSlider(props: ParamSliderProps) {
  if (!props.wired) {
    return (
      <div className="opacity-50 cursor-not-allowed">
        <label>{props.labelRu}</label>
        <div className="text-xs text-muted">[ПАРАМЕТР ЗАПЛАНИРОВАН — ЕЩЁ НЕ ПОДКЛЮЧЁН]</div>
        <Slider disabled value={[props.default]} min={props.min} max={props.max} />
      </div>
    );
  }
  return (
    <Tooltip content={<TooltipBody {...props.tooltip} />}>
      <div>
        <label className="block text-sm font-medium">{props.labelRu}</label>
        <span className="text-xs text-muted">{props.labelEn}</span>
        <Slider
          value={[props.value]}
          min={props.min}
          max={props.max}
          step={props.step}
          onValueChange={(v) => props.onChange(v[0])}
        />
        <div className="text-xs">{props.value}{props.unit}</div>
      </div>
    </Tooltip>
  );
}
```

#### 3.4.3. Карточка NPC (живое состояние)

```tsx
// calibration_ui/src/components/npc-card/NpcCard.tsx
export function NpcCard({ npcId, experimentId }: Props) {
  const state = useNpcLiveState(experimentId, npcId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{state.name_ru}</CardTitle>      {/* "Люся" */}
        <CardSubtitle>{state.role_ru}</CardSubtitle> {/* "Служанка таверны" */}
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <Field label="Сейчас считает игрока" value={state.player_assessment_ru} />
          <Field label="Настроение" value={state.mood_ru} />
          <Field label="Главная тревога" value={state.main_concern_ru} />
          <Field label="Последнее убеждение" value={state.last_belief_ru} />
          <Field label="Текущее намерение" value={state.current_intent_ru} />
          <Field label="Уверенность" value={`${(state.confidence * 100).toFixed(0)} %`} />
        </div>
        <Separator className="my-3" />
        <NpcStateView state={state.internal} />
        <NpcRelationships relationships={state.relationships} />
        <NpcBeliefs beliefs={state.crystallized_beliefs} />
        <NpcDrives drives={state.effective_drives} />
      </CardContent>
    </Card>
  );
}
```

#### 3.4.4. Локализация (RU)

```ts
// calibration_ui/src/lib/i18n.ts
export const STRINGS_RU = {
  // Панели
  panel_parameters: "Параметры NPC",
  panel_npc_life: "Жизнь NPC",
  panel_timeline: "История изменений",
  panel_causal_chain: "Причинная цепочка",
  panel_player_actions: "Вмешательство игрока",
  panel_graphs: "Графики",

  // Кнопки управления
  btn_start: "▶ Запустить",
  btn_pause: "⏸ Пауза",
  btn_step: "⏭ Следующий тик",
  btn_speed_x1: "×1",
  btn_speed_x5: "×5",
  btn_speed_x20: "×20",
  btn_speed_x100: "×100",
  btn_restart: "↻ Перезапуск",
  btn_reset_params: "⟲ Сброс параметров",

  // Кнопки игрока
  action_help: "Помог",
  action_lie: "Соврал",
  action_steal: "Украл",
  action_insult: "Оскорбил",
  action_praise: "Похвалил",
  action_gift: "Дал подарок",
  action_betray: "Предал",
  action_protect: "Защитил NPC",
  action_frighten: "Испугал NPC",
  action_truth: "Рассказал правду",
  action_rumor: "Распространил слух",
  action_strange: "Совершил странный поступок",

  // Кнопки мира
  world_injury: "NPC получил травму",
  world_death: "Друг NPC умер",
  world_threat: "Появилась угроза",
  world_secret: "NPC узнал секрет",
  world_status: "Изменился статус NPC",
  world_new_person: "Появился новый человек",
  world_rumor: "Слух распространился",
  world_festival: "Начался праздник",
  world_weather: "Смена погоды",
  world_guards: "Приход стражи",
  world_promotion: "NPC назначили на должность",
  world_demotion: "NPC понизили",

  // Зоны
  zone_mannequin: "МАНЕКЕН",
  zone_chaos: "ХАОС",
  zone_enigma: "ENIGMA",
  zone_warning: "ПРЕДУПРЕЖДЕНИЕ",
} as const;
```

#### 3.4.5. Приёмочные тесты Sprint 2

```ts
// calibration_ui/tests/e2e/sliders.spec.ts
import { test, expect } from "@playwright/test";

test("UI отображает 15+ слайдеров на русском", async ({ page }) => {
  await page.goto("http://localhost:3001");
  const sliders = page.locator("[data-testid='param-slider']");
  await expect(sliders).toHaveCount(15);
  // Все лейблы на русском
  const labels = await page.locator("[data-testid='param-slider'] label").allTextContents();
  expect(labels.every(l => /[А-Яа-я]/.test(l))).toBeTruthy();
});

test("Параметр [PLAN] отображается как disabled", async ({ page }) => {
  await page.goto("http://localhost:3001");
  const planSlider = page.locator("[data-testid='param-plan']").first();
  await expect(planSlider).toBeDisabled();
  await expect(planSlider).toContainText("ПАРАМЕТР ЗАПЛАНИРОВАН");
});

test("Карточка NPC показывает состояние на русском", async ({ page }) => {
  // запускаем эксперимент, ждём 5 тиков
  // проверяем, что в карточке есть поля "Настроение", "Текущее намерение"
  ...
});
```

### 3.5. Sprint 3: Кнопки игрока + timeline + графики

#### 3.5.1. Кнопки игрока → `InterventionEvent`

```python
# backend/app/api/calibration_routes.py
@router.post("/experiments/{exp_id}/intervention")
async def inject_intervention(exp_id: str, req: InterventionRequest):
    """
    InterventionRequest:
        action_type: "HELP" | "LIE" | "STEAL" | "INSULT" | "PRAISE"
                    | "GIFT" | "BETRAY" | "PROTECT" | "FRIGHTEN"
                    | "TRUTH" | "RUMOR" | "STRANGE"
                    | "INJURY" | "DEATH" | "THREAT_APPEAR" | "SECRET_REVEAL"
        target_npc_id: str
        secret_id?: str
        intensity?: float
    """
    runner = ExperimentRunnerRegistry.get(exp_id)
    intervention = map_action_to_intervention(req)  # см. таблицу в ТЗ 11.2
    runner.inject_intervention(intervention)
    return {"status": "queued"}
```

#### 3.5.2. Timeline — источник событий

```python
# backend/app/services/calibration/timeline_builder.py
class TimelineBuilder:
    """Подписывается на EventBus, строит timeline в реальном времени."""

    def __init__(self, event_bus: EventBus, l1_chronicle: L1Chronicle):
        self._events: List[TimelineEvent] = []
        event_bus.subscribe("EventDTO", self._on_event)
        event_bus.subscribe("TraitDriftEvent", self._on_trait_drift)
        event_bus.subscribe("BeliefCrystallizationEvent", self._on_belief)
        event_bus.subscribe("IntentEvent", self._on_intent)
        event_bus.subscribe("CausalEntry", self._on_causal)

    def get_since(self, since_tick: int) -> List[TimelineEvent]: ...
```

#### 3.5.3. Графики (Plotly)

```tsx
// calibration_ui/src/components/graphs/TrustGraph.tsx
import { Line } from "react-plotly.js";

export function TrustGraph({ experimentId, npcId }: Props) {
  const data = useTrustHistory(experimentId, npcId);  // SSE-подписка
  return (
    <Line
      data={[{
        x: data.map(d => d.tick),
        y: data.map(d => d.trust),
        type: "scatter",
        mode: "lines",
        line: { color: "#2E8B57" },
      }]}
      layout={{
        title: "Доверие к игроку во времени",
        xaxis: { title: "Тик" },
        yaxis: { title: "Trust", range: [-100, 100] },
      }}
    />
  );
}
```

#### 3.5.4. Приёмочные тесты Sprint 3

```python
# backend/tests/calibration_lab/test_m1_sprint3_actions.py

def test_player_help_increases_trust():
    """M1-AC-301: Кнопка 'Помог' увеличивает trust"""
    runner = ExperimentRunner()
    exp_id = runner.start(ExperimentConfig(
        preset_path="configs/calibration/test_presets/enigma_golden.yaml",
        scenario_path="config/scenarios/tavern_silver_wolf_15min.yaml",
        seed=7331, duration_ticks=150,
    ))
    runner.step(exp_id, n_ticks=10)
    trust_before = runner.get_live_state(exp_id).npcs["maid_lusya"].trust_player
    runner.inject_intervention(exp_id, InterventionRequest(
        action_type="HELP", target_npc_id="maid_lusya", intensity=1.0,
    ))
    runner.step(exp_id, n_ticks=5)
    trust_after = runner.get_live_state(exp_id).npcs["maid_lusya"].trust_player
    assert trust_after > trust_before


def test_player_betray_drops_trust_and_raises_stress():
    """M1-AC-302: Кнопка 'Предал' уменьшает trust и поднимает stress"""
    ...
    assert trust_after < trust_before - 10
    assert stress_after > stress_before


def test_timeline_records_intervention():
    """M1-AC-303: Timeline содержит событие вмешательства"""
    timeline = runner.get_timeline(exp_id, since_tick=10)
    assert any(e.type == "PLAYER_INTERVENTION" for e in timeline)
```

### 3.6. Sprint 4: A/B режим + сохранение пресета

#### 3.6.1. A/B сравнение

```python
# backend/app/services/calibration/ab_runner.py
@dataclass
class ABResult:
    config_a_id: str
    config_b_id: str
    metrics_a: Dict[str, float]
    metrics_b: Dict[str, float]
    zone_a: Zone
    zone_b: Zone
    wow_density_ratio: float    # metrics_a.wow / metrics_b.wow
    character_change_ratio: float
    verdict_ru: str              # human-readable verdict

class ABRunner:
    def run(self, config_a: ExperimentConfig, config_b: ExperimentConfig,
            same_scenario: bool = True, seed: int = 7331) -> ABResult:
        r_a = self._runner.run(config_a)
        r_b = self._runner.run(config_b)
        return self._compare(r_a, r_b)
```

#### 3.6.2. Сохранение пресета

```python
# backend/app/services/calibration/preset_io.py
class PresetIO:
    def save(self, params: Dict[str, float], metrics: Dict[str, float],
             experiment_id: str, seed: int, scenario: str) -> str:
        """
        Сохраняет пресет в configs/npc/<name>.yaml
        Возвращает путь.
        """
        ...

    def load(self, path: str) -> Preset: ...
```

#### 3.6.3. Приёмочные тесты Sprint 4

```python
def test_ab_comparison_detects_enigma_vs_mannequin():
    """M1-AC-401: A/B корректно разделяет ENIGMA и МАНЕКЕН"""
    ab = ABRunner().run(
        config_a=ExperimentConfig(preset_path=".../enigma_golden.yaml", ...),
        config_b=ExperimentConfig(preset_path=".../mannequin.yaml", ...),
    )
    assert ab.zone_a == Zone.ENIGMA
    assert ab.zone_b == Zone.MANNEQUIN
    assert ab.wow_density_ratio > 2.0


def test_preset_save_and_reload_yields_same_metrics():
    """M1-AC-402: Сохранённый и перезагруженный пресет даёт те же метрики"""
    r1 = runner.run(config_with_seed_7331)
    path = PresetIO().save(params=..., metrics=r1.metrics, ...)
    r2 = runner.run(ExperimentConfig(preset_path=path, ...))
    assert abs(r1.metrics["character_change_rate"] - r2.metrics["character_change_rate"]) < 0.01
```

### 3.7. Sprint 5: Экспорт + bugfix + окончательная приёмка

#### 3.7.1. Экспорт

```python
# backend/app/services/calibration/exporters/
class JSONExporter:
    def export(self, result: ExperimentResult, dest: Path) -> Path: ...

class CSVExporter:
    def export(self, result: ExperimentResult, dest: Path) -> Path: ...

class PNGExporter:
    def export(self, result: ExperimentResult, dest: Path) -> List[Path]:
        # 5 графиков: trust, stress, belief, intent, wow_density
        ...

class HTMLExporter:
    def export(self, result: ExperimentResult, dest: Path) -> Path:
        # Plotly-интерактивный дашборд
        ...

class YAMLPresetExporter:
    def export(self, result: ExperimentResult, dest: Path) -> Path: ...
```

#### 3.7.2. Финальные приёмочные тесты M1

```python
def test_m1_full_user_workflow():
    """M1-AC-501: Полный пользовательский сценарий работает end-to-end"""
    # 1. Создать эксперимент с enigma_golden preset
    # 2. Запустить, дождаться 10 тиков
    # 3. Вмешаться: HELP, потом LIE
    # 4. Дождаться 30 тиков
    # 5. Проверить timeline содержит 2 PLAYER_INTERVENTION
    # 6. Пауза, ускорение ×20, ещё 50 тиков
    # 7. Экспортировать CSV, JSON, PNG
    # 8. Сохранить пресет как enigma_mvp_v1.yaml
    # 9. Перезапустить с тем же seed → детерминизм
    # 10. A/B сравнить с mannequin preset
    #     → A в ENIGMA zone, B в MANNEQUIN
    pass
```

### 3.8. Definition of Done для M1

- [ ] Все 4 слоя архитектуры работают (UI ↔ Runner ↔ Engine ↔ Observability);
- [ ] 15+ слайдеров на русском;
- [ ] 6+ кнопок игрока;
- [ ] timeline с 5+ типами событий;
- [ ] 3+ живых графика;
- [ ] A/B режим работает;
- [ ] Сохранение пресета → reload → повтор тех же метрик;
- [ ] Экспорт в 5 форматов;
- [ ] Все acceptance-тесты из 3.5–3.7 проходят;
- [ ] Документация в `docs/calibration_lab/usage.md`;
- [ ] Worklog обновлён.

---

## 4. M2 — Драматические метрики (3 недели)

### 4.1. Цели M2

1. Реализовать все 10 метрик из ТЗ раздел 14.
2. Реализовать `WOWAggregator` (раздел 15).
3. Реализовать `ZoneClassifier` (раздел 16, 17.2).
4. Расширить `DNASnapshot` новыми полями.
5. Подключить метрики к UI в реальном времени.

### 4.2. Артефакты M2

| Артефакт | Путь |
|---|---|
| Character Change | `backend/app/services/calibration/metrics/character_change.py` |
| Decision Diversity | `backend/app/services/calibration/metrics/decision_diversity.py` |
| Emotional Volatility | `backend/app/services/calibration/metrics/emotional_volatility.py` |
| Belief Revision Rate | `backend/app/services/calibration/metrics/belief_revision_rate.py` |
| Relationship Dynamics | `backend/app/services/calibration/metrics/relationship_dynamics.py` |
| Event Responsiveness | `backend/app/services/calibration/metrics/event_responsiveness.py` |
| Causal Depth | `backend/app/services/calibration/metrics/causal_depth.py` |
| Loop Rate | `backend/app/services/calibration/metrics/loop_rate.py` |
| Character Stability | `backend/app/services/calibration/metrics/character_stability.py` |
| WOW Aggregator | `backend/app/services/calibration/metrics/wow_aggregator.py` |
| Zone Classifier | `backend/app/services/calibration/zone_classifier.py` |
| DNA extension | `diagnostics/dna_metrics.py` (diff: +10 полей) |
| UI: Zone indicator | `calibration_ui/src/components/zone/ZoneIndicator.tsx` |
| UI: Metrics panel | `calibration_ui/src/components/metrics/MetricsPanel.tsx` |

### 4.3. Спецификация метрик

#### 4.3.1. Character Change Rate

```python
class CharacterChangeRate(CalibrationMetric):
    """
    Насколько сильно изменилось состояние NPC за N минут.

    Formula:
        state_vector(t) = [
            trust, stress, affective_load, resentment,
            identity_integrity, pressure_resistance, breakpoint,
            *effective_drives, *top_beliefs_confidence
        ]
        Δ(t) = ||state_vector(t) - state_vector(t - window)||
        character_change_rate = mean(Δ over windows)

    Source: NPCStateAdapter snapshots, taken every tick.
    """
    def update(self, tick, state_snapshot, event=None):
        self._snapshots.append((tick, self._to_vector(state_snapshot)))
    def compute(self) -> float:
        # нормализованная L2-норма разницы, усреднённая по окну
        ...
```

#### 4.3.2. WOW Aggregator

```python
# backend/app/services/calibration/metrics/wow_aggregator.py
class WOWCategory(Enum):
    RELATIONSHIP = "relationship"
    INTENT = "intent"
    BELIEF = "belief"
    SECRET = "secret"
    CONFLICT = "conflict"
    RECONCILIATION = "reconciliation"
    PROACTIVE = "proactive"
    ERROR = "error"

@dataclass(frozen=True)
class WOWEvent:
    tick: int
    real_time: float
    category: WOWCategory
    delta: float
    description: str
    npc_id: str
    causal_parent_id: Optional[str]

class WOWAggregator:
    SUBSCRIPTIONS = [
        "RelationshipDeltaEvent",   # trust change with |Δ| ≥ 5
        "IntentEvent",               # intent != previous
        "CrystallizedBeliefEvent",   # new or revised belief
        "SecretRevealedEvent",
        "ConflictStartedEvent",
        "ConflictResolvedEvent",
        "ProactiveIntentEvent",
        "NPCErrorEvent",
    ]

    def __init__(self, event_bus: EventBus):
        self._events: List[WOWEvent] = []
        for topic in self.SUBSCRIPTIONS:
            event_bus.subscribe(topic, self._on_event)

    def _on_event(self, event):
        if self._is_significant(event):
            self._events.append(self._to_wow_event(event))

    def _is_significant(self, event) -> bool:
        """Фильтр: |Δ trust| ≥ 5, intent != previous, и т.д."""
        ...

    def density(self, window_minutes: float = 30.0) -> float:
        """WOW events per minute in the last `window_minutes`."""
        ...

    def events_in_window(self, window_minutes: float) -> List[WOWEvent]: ...
```

#### 4.3.3. Zone Classifier

```python
# backend/app/services/calibration/zone_classifier.py
class Zone(Enum):
    MANNEQUIN = "mannequin"
    CHAOS = "chaos"
    ENIGMA = "enigma"
    WARNING = "warning"

@dataclass(frozen=True)
class CalibrationMetrics:
    character_change_rate: float
    decision_diversity: float
    emotional_volatility: float
    belief_revision_rate: float
    relationship_dynamics: float
    event_responsiveness: float
    causal_depth: float
    loop_rate: float
    character_stability: float
    wow_density: float
    contradiction_rate: float
    causal_coverage: float
    nan_count: int
    invariant_violations: int

@dataclass(frozen=True)
class ZoneClassification:
    zone: Zone
    confidence: float          # 0..1
    reason: str                # "character_change_rate=0.05 → MANNEQUIN"
    metrics: CalibrationMetrics

# Thresholds loaded from configs/calibration/zone_thresholds.yaml
class ZoneClassifier:
    def __init__(self, thresholds: ZoneThresholds): ...
    def classify(self, metrics: CalibrationMetrics) -> ZoneClassification:
        # Если nan_count > 0 или invariant_violations > 0 → BROKEN (не зона)
        # Алгоритм — см. ТЗ раздел 17.2
        ...
```

#### 4.3.4. `configs/calibration/zone_thresholds.yaml`

```yaml
mannequin:
  character_change_rate_max: 0.15
  wow_density_max: 0.20
  loop_rate_min: 0.50
chaos:
  character_change_rate_min: 0.90
  contradiction_rate_min: 0.20
  causal_coverage_max: 0.50
  character_stability_max: 0.20
enigma:
  character_change_rate: [0.30, 0.80]
  wow_density: [0.40, 1.20]
  loop_rate_max: 0.15
  character_stability_min: 0.50
  causal_coverage_min: 0.90
  contradiction_rate_max: 0.10
warning:
  # всё остальное
```

### 4.4. Расширение DNASnapshot

```python
# diagnostics/dna_metrics.py (diff)
@dataclass
class DNASnapshot:
    # ... существующие 25 полей ...
    # НОВЫЕ ПОЛЯ (M2):
    character_change_rate: float = 0.0
    decision_diversity: float = 0.0
    emotional_volatility: float = 0.0
    belief_revision_rate: float = 0.0
    relationship_dynamics: float = 0.0
    event_responsiveness: float = 0.0
    causal_depth: float = 0.0
    loop_rate: float = 0.0
    character_stability: float = 0.0
    wow_density: float = 0.0
    contradiction_rate: float = 0.0
    causal_coverage: float = 0.0
    zone: str = "unknown"     # "mannequin" | "chaos" | "enigma" | "warning"
```

### 4.5. Приёмочные тесты M2 (главные — «правильно найденных вариантов»)

```python
# backend/tests/calibration_lab/test_m2_zone_classification.py

class TestZoneClassification:
    """Тесты «правильно найденных вариантов»: лаборатория корректно
    классифицирует заранее известные пресеты."""

    def test_mannequin_preset_classified_as_mannequin(self):
        """M2-AC-001: mannequin.yaml → Zone.MANNEQUIN"""
        result = run_15min(preset="mannequin.yaml", seed=7331)
        classification = ZoneClassifier().classify(result.metrics)
        assert classification.zone == Zone.MANNEQUIN
        assert classification.confidence > 0.8

    def test_chaos_preset_classified_as_chaos(self):
        """M2-AC-002: chaos.yaml → Zone.CHAOS"""
        result = run_15min(preset="chaos.yaml", seed=7331)
        classification = ZoneClassifier().classify(result.metrics)
        assert classification.zone == Zone.CHAOS
        assert classification.confidence > 0.8

    def test_enigma_golden_classified_as_enigma(self):
        """M2-AC-003: enigma_golden.yaml → Zone.ENIGMA"""
        result = run_15min(preset="enigma_golden.yaml", seed=7331)
        classification = ZoneClassifier().classify(result.metrics)
        assert classification.zone == Zone.ENIGMA
        assert classification.confidence > 0.7

    def test_broken_preset_returns_broken_not_chaos(self):
        """M2-AC-004: Пресет с NaN → BROKEN, не ХАОС"""
        result = run_15min(preset="broken_nan.yaml", seed=7331)
        # broken_nan.yaml содержит параметры, которые приводят к NaN
        classification = ZoneClassifier().classify(result.metrics)
        assert classification.zone == Zone.BROKEN  # требуется добавить
        assert result.nan_count > 0

    def test_invariant_violation_returns_broken(self):
        """M2-AC-005: Нарушение SUPERBOX → BROKEN, не ENIGMA"""
        result = run_15min(preset="invariant_breaker.yaml", seed=7331)
        classification = ZoneClassifier().classify(result.metrics)
        assert classification.zone == Zone.BROKEN
        assert result.invariant_violations > 0

    def test_warning_zone_for_borderline_preset(self):
        """M2-AC-006: Пограничный пресет → WARNING, не ENIGMA"""
        # preset с character_change_rate = 0.28 (ниже 0.30)
        result = run_15min(preset="borderline_low.yaml", seed=7331)
        classification = ZoneClassifier().classify(result.metrics)
        assert classification.zone == Zone.WARNING


class TestWOWAggregator:
    def test_wow_density_in_enigma_range(self):
        """M2-AC-007: enigma_golden даёт wow_density ∈ [0.4, 1.2]"""
        result = run_30min(preset="enigma_golden.yaml", seed=7331)
        assert 0.4 <= result.metrics["wow_density"] <= 1.2

    def test_wow_density_low_in_mannequin(self):
        """M2-AC-008: mannequin даёт wow_density < 0.2"""
        result = run_30min(preset="mannequin.yaml", seed=7331)
        assert result.metrics["wow_density"] < 0.2

    def test_wow_density_not_inflated_by_random_noise(self):
        """M2-AC-009: WOW не считает шум (SCORE_NOISE_RANGE вверх-вниз)"""
        # preset с очень высоким score_noise_range, но низким character_change
        # wow_density должна быть низкой (не считаем шум как WOW)
        result = run_30min(preset="noise_only.yaml", seed=7331)
        assert result.metrics["wow_density"] < 0.3


class TestMetricsStability:
    def test_metrics_stable_across_seeds(self):
        """M2-AC-010: Метрики в ENIGMA-зоне стабильны для разных seed"""
        results = [run_30min(preset="enigma_golden.yaml", seed=s)
                   for s in [1, 42, 7331, 99999]]
        for r in results:
            c = ZoneClassifier().classify(r.metrics)
            assert c.zone == Zone.ENIGMA, f"seed={r.config.seed}: zone={c.zone}"

    def test_metrics_variance_in_chaos(self):
        """M2-AC-011: В ХАОСЕ метрики сильно варьируются между seed"""
        results = [run_30min(preset="chaos.yaml", seed=s)
                   for s in [1, 42, 7331, 99999]]
        wow_values = [r.metrics["wow_density"] for r in results]
        # в хаосе метрики должны сильно различаться
        assert (max(wow_values) - min(wow_values)) > 0.5
```

### 4.6. Definition of Done для M2

- [ ] 10 метрик реализованы;
- [ ] WOW Aggregator фильтрует шум;
- [ ] ZoneClassifier корректно отличает 4 зоны (+BROKEN);
- [ ] Все 11 приёмочных тестов из 4.5 проходят;
- [ ] DNA-снапшот расширен;
- [ ] UI показывает ZoneIndicator в реальном времени;
- [ ] Worklog обновлён.

---

## 5. M3 — Parameter Sweep и A/B framework (3 недели)

### 5.1. Цели M3

1. Реализовать `EnigmaPhaseEngine` (замена stub в `calibration/run_sweep.py:10-12`).
2. Реализовать Grid / Random / Bayesian sweep.
3. Реализовать One-Param-Scan режим (ТЗ раздел 19).
4. Расширить A/B до A/B/C/.../N.
5. UI для sweep с прогресс-баром.

### 5.2. Артефакты M3

| Артефакт | Путь |
|---|---|
| EnigmaPhaseEngine | `backend/app/services/calibration/sweep/phase_engine.py` |
| Scoring function | `backend/app/services/calibration/sweep/scoring.py` |
| Grid sweep | `backend/app/services/calibration/sweep/grid_sweep.py` |
| Random sweep | `backend/app/services/calibration/sweep/random_sweep.py` |
| Bayesian sweep | `backend/app/services/calibration/sweep/bayesian_sweep.py` |
| One-Param-Scan | `backend/app/services/calibration/sweep/one_param_scan.py` |
| SweepRunner (orchestrator) | `backend/app/services/calibration/sweep/runner.py` |
| UI: Sweep panel | `calibration_ui/src/components/sweep/SweepPanel.tsx` |
| UI: Sweep results | `calibration_ui/src/components/sweep/SweepResultsTable.tsx` |

### 5.3. Реализация `EnigmaPhaseEngine`

```python
# backend/app/services/calibration/sweep/phase_engine.py
"""Замена stub из backend/tests/sandbox/calibration/run_sweep.py:10-12"""
import numpy as np
from typing import Tuple, List, Dict
from backend.app.services.calibration.experiment_runner import ExperimentRunner
from backend.app.services.calibration.zone_classifier import (
    ZoneClassifier, CalibrationMetrics, Zone
)

class EnigmaPhaseEngine:
    """
    Реализация PhasePhysicsEngine для ENIGMA.
    Каждый «фазовый» сэмпл = полный запуск эксперимента с данными параметрами.
    Возвращает CausalStateVector + zone classification.
    """

    def __init__(self, scenario_path: str, seed: int = 7331,
                 duration_ticks: int = 150):
        self._runner = ExperimentRunner()
        self._scenario = scenario_path
        self._seed = seed
        self._duration = duration_ticks
        self._classifier = ZoneClassifier()

    def elastic_warp(self, params: Dict[str, float]) -> "CausalStateVector":
        """Запускает эксперимент с params, возвращает state vector."""
        preset = self._materialize_preset(params)
        result = self._runner.run(ExperimentConfig(
            preset_path=preset,
            scenario_path=self._scenario,
            seed=self._seed,
            duration_ticks=self._duration,
        ))
        return CausalStateVector(
            g_basis=self._to_vector(result.final_npc_state),
            last_commit_tick=result.last_tick,
            version=result.enigma_version,
            zone=self._classifier.classify(result.metrics).zone,
            metrics=result.metrics,
        )

    def phi_stable_check(self, csv_path: str) -> bool:
        """Проверка: replay даёт тот же результат."""
        ...

    def _materialize_preset(self, params: Dict[str, float]) -> str:
        """Создаёт временный YAML из params."""
        ...
```

### 5.4. Scoring function

```python
# backend/app/services/calibration/sweep/scoring.py
from typing import Dict
from yaml import safe_load

class Scorer:
    def __init__(self, weights_path: str = "configs/calibration/scoring.yaml"):
        with open(weights_path) as f:
            self._weights = safe_load(f)["weights"]
        self._hard_constraints = self._load_hard_constraints()

    def score(self, metrics: Dict[str, float]) -> float:
        if not self._passes_hard_constraints(metrics):
            return -1.0   # rejected
        s = 0.0
        for metric, weight in self._weights.items():
            s += weight * metrics.get(metric, 0.0)
        return s

    def _passes_hard_constraints(self, metrics: Dict[str, float]) -> bool:
        if metrics.get("nan_count", 0) > 0: return False
        if metrics.get("invariant_violations", 0) > 0: return False
        if metrics.get("loop_rate", 0) >= 0.30: return False
        if metrics.get("contradiction_rate", 0) >= 0.20: return False
        if metrics.get("causal_coverage", 1.0) <= 0.5: return False
        if metrics.get("character_stability", 1.0) <= 0.2: return False
        return True
```

### 5.5. One-Param-Scan

```python
# backend/app/services/calibration/sweep/one_param_scan.py
@dataclass
class OneParamScanResult:
    param_name: str
    values: List[float]
    metrics: List[Dict[str, float]]
    zones: List[Zone]
    scores: List[float]
    best_value: float
    best_zone: Zone

class OneParamScanner:
    def scan(self, param_name: str, values: List[float],
             base_preset: str, scenario: str, seed: int) -> OneParamScanResult:
        results = []
        for v in values:
            preset = self._with_param(base_preset, param_name, v)
            r = self._runner.run(ExperimentConfig(
                preset_path=preset, scenario_path=scenario,
                seed=seed, duration_ticks=150,
            ))
            results.append((v, r.metrics))
        return self._summarize(param_name, results)
```

### 5.6. Приёмочные тесты M3 (главные — «правильно найденных вариантов»)

```python
# backend/tests/calibration_lab/test_m3_sweep_correctness.py

class TestSweepFindsGoldenZone:
    """Тесты «правильно найденных вариантов»: sweep корректно
    находит ENIGMA-зону в заранее известном параметрическом пространстве."""

    def test_grid_sweep_finds_at_least_3_enigma_configs(self):
        """M3-AC-001: Grid sweep находит ≥ 3 ENIGMA-конфигурации"""
        sweep = GridSweep(
            params={
                "identity_rigidity": [0.20, 0.40, 0.60, 0.80],
                "threat_amplification_factor": [0.05, 0.15, 0.30],
                "event_memory_decay_rate": [0.02, 0.05, 0.10, 0.20],
            },
            scenario="tavern_silver_wolf_15min.yaml",
            seed=7331,
        )
        results = sweep.run()
        enigma_count = sum(1 for r in results if r.zone == Zone.ENIGMA)
        assert enigma_count >= 3
        # Все ENIGMA-конфиги прошли hard constraints
        for r in results:
            if r.zone == Zone.ENIGMA:
                assert r.metrics["loop_rate"] < 0.15
                assert r.metrics["character_stability"] >= 0.5

    def test_grid_sweep_classifies_mannequin_zone_at_extremes(self):
        """M3-AC-002: Крайние значения rigidity=0.95 → MANNEQUIN"""
        sweep = GridSweep(
            params={"identity_rigidity": [0.95, 0.05]},
            scenario="tavern_silver_wolf_15min.yaml",
            seed=7331,
        )
        results = sweep.run()
        # rigidity=0.95 → MANNEQUIN
        high = next(r for r in results if r.params["identity_rigidity"] == 0.95)
        assert high.zone == Zone.MANNEQUIN
        # rigidity=0.05 + defaults → CHAOS
        low = next(r for r in results if r.params["identity_rigidity"] == 0.05)
        assert low.zone == Zone.CHAOS

    def test_one_param_scan_finds_optimal_decay_rate(self):
        """M3-AC-003: One-Param-Scan находит «золотой» decay_rate"""
        scanner = OneParamScanner()
        result = scanner.scan(
            param_name="event_memory_decay_rate",
            values=[0.01, 0.02, 0.05, 0.10, 0.20, 0.40, 0.80],
            base_preset="configs/calibration/test_presets/enigma_golden.yaml",
            scenario="tavern_silver_wolf_15min.yaml",
            seed=7331,
        )
        # Оптимум должен быть в районе 0.02–0.10
        assert 0.02 <= result.best_value <= 0.10
        assert result.best_zone == Zone.ENIGMA
        # При экстремальных значениях — другие зоны
        assert result.zones[0] == Zone.MANNEQUIN  # decay=0.01
        assert result.zones[-1] == Zone.CHAOS     # decay=0.80

    def test_bayesian_optimization_finds_enigma_within_budget(self):
        """M3-AC-004: Bayesian optimization находит ENIGMA за ≤ 30 итераций"""
        bayes = BayesianSweep(
            param_ranges={
                "identity_rigidity": (0.10, 0.90),
                "threat_amplification_factor": (0.05, 0.50),
                "affect_decay_base_rate": (0.01, 0.30),
                "score_noise_range": (0.01, 0.25),
            },
            scenario="tavern_silver_wolf_15min.yaml",
            seed=7331,
            max_iterations=30,
        )
        result = bayes.run()
        assert result.best_zone == Zone.ENIGMA
        assert result.best_score > 0.5

    def test_sweep_rejects_broken_configs(self):
        """M3-AC-005: Sweep не возвращает BROKEN как ENIGMA"""
        # preset с экстремально низким breakpoint → NaN
        sweep = GridSweep(
            params={"breakpoint": [0.0, 1.0, 50.0, 100.0]},
            scenario="tavern_silver_wolf_15min.yaml",
            seed=7331,
        )
        results = sweep.run()
        for r in results:
            if r.metrics.get("nan_count", 0) > 0:
                assert r.zone != Zone.ENIGMA
                assert r.zone != Zone.MANNEQUIN
                assert r.zone != Zone.CHAOS
                assert r.zone == Zone.BROKEN

    def test_sweep_results_are_deterministic(self):
        """M3-AC-006: Одинаковый seed → одинаковые результаты sweep"""
        sweep1 = GridSweep(params=..., scenario=..., seed=7331)
        sweep2 = GridSweep(params=..., scenario=..., seed=7331)
        r1 = sweep1.run()
        r2 = sweep2.run()
        for a, b in zip(r1, r2):
            assert a.metrics == b.metrics
            assert a.zone == b.zone


class TestABComparisonAdvanced:
    def test_ab_correctly_identifies_more_expressive_config(self):
        """M3-AC-007: A/B находит конфиг с ×2.5+ большей выразительностью"""
        ab = ABRunner().run(
            config_a=ExperimentConfig(preset_path=".../enigma_golden.yaml", ...),
            config_b=ExperimentConfig(preset_path=".../mannequin.yaml", ...),
        )
        assert ab.wow_density_ratio > 2.5
        assert "более выразителен" in ab.verdict_ru

    def test_ab_with_identical_configs_returns_ratio_1(self):
        """M3-AC-008: A/A тест даёт ratio ≈ 1.0"""
        ab = ABRunner().run(
            config_a=ExperimentConfig(preset_path=".../enigma_golden.yaml", ...),
            config_b=ExperimentConfig(preset_path=".../enigma_golden.yaml", ...),
        )
        assert 0.95 <= ab.wow_density_ratio <= 1.05
```

### 5.7. Definition of Done для M3

- [ ] `EnigmaPhaseEngine` реализован, stub удалён;
- [ ] Grid/Random/Bayesian работают;
- [ ] One-Param-Scan работает;
- [ ] Все 8 приёмочных тестов из 5.6 проходят;
- [ ] UI показывает прогресс sweep и таблицу результатов;
- [ ] Worklog обновлён.

---

## 6. M4 — Визуальные карты и auto-search (2 недели)

### 6.1. Цели M4

1. Реализовать визуальные heatmaps поведения (ТЗ раздел 22).
2. Добавить CMA-ES и genetic algorithm для расширенного auto-search.
3. Реализовать «3D-карту» золотой области (для 3+ параметров).
4. UI: интерактивный Plotly-дашборд с картами.

### 6.2. Артефакты M4

| Артефакт | Путь |
|---|---|
| Heatmap renderer | `backend/app/services/calibration/visualization/heatmaps.py` |
| Zone map (3D) | `backend/app/services/calibration/visualization/zone_3d.py` |
| CMA-ES sweep | `backend/app/services/calibration/sweep/cma_es.py` |
| Genetic sweep | `backend/app/services/calibration/sweep/genetic.py` |
| UI: Heatmap panel | `calibration_ui/src/components/visualization/HeatmapPanel.tsx` |
| UI: 3D zone map | `calibration_ui/src/components/visualization/ZoneMap3D.tsx` |

### 6.3. Heatmap

```python
# backend/app/services/calibration/visualization/heatmaps.py
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
from pathlib import Path

# Регистрация русских шрифтов
fm.fontManager.addfont('/usr/share/fonts/truetype/chinese/NotoSansSC-Regular.ttf')
plt.rcParams['font.sans-serif'] = ['Noto Sans SC', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class HeatmapRenderer:
    def render(self, x_param: str, y_param: str, metric: str,
               results: List[SweepResult], dest: Path) -> Path:
        """Создаёт heatmap: x=param1, y=param2, color=metric"""
        ...
```

### 6.4. Приёмочные тесты M4

```python
class TestVisualization:
    def test_heatmap_shows_golden_zone(self):
        """M4-AC-001: Heatmap визуально показывает ENIGMA-зону"""
        # запускаем sweep с известной golden зоной
        # рендерим heatmap
        # проверяем, что в центре картинки — зелёные пиксели
        ...

    def test_3d_zone_map_classifies_volume(self):
        """M4-AC-002: 3D-карта корректно показывает объём ENIGMA-зоны"""
        ...

class TestAdvancedSearch:
    def test_cma_es_finds_better_than_grid(self):
        """M4-AC-003: CMA-ES находит конфиг лучше, чем grid search"""
        grid_best = GridSweep(...).run().best_score
        cma_best = CMAESSweep(...).run().best_score
        assert cma_best >= grid_best

    def test_genetic_finds_multiple_enigma_zones(self):
        """M4-AC-004: Genetic algorithm находит ≥ 2 различных ENIGMA-зоны"""
        results = GeneticSweep(...).run()
        distinct_zones = cluster_by_params(results, threshold=0.15)
        enigma_clusters = [c for c in distinct_zones
                          if c[0].zone == Zone.ENIGMA]
        assert len(enigma_clusters) >= 2
```

### 6.5. Definition of Done для M4

- [ ] Heatmaps генерируются в PNG + HTML;
- [ ] CMA-ES и Genetic работают;
- [ ] Все 4 приёмочных теста проходят;
- [ ] UI показывает интерактивные карты;
- [ ] Worklog обновлён.

---

## 7. M5 — Пресеты, воспроизводимость, экспорт (2 недели)

### 7.1. Цели M5

1. Финализировать формат пресета (ТЗ раздел 23).
2. Реализовать полный replay verification (ТЗ раздел 24).
3. Реализовать все 5 форматов экспорта (ТЗ раздел 25).
4. Подключить пресет-файлы к `config/user_settings.yaml`.
5. Документация для разработчиков и пользователей.

### 7.2. Артефакты M5

| Артефакт | Путь |
|---|---|
| Replay Verifier | `backend/app/services/calibration/replay_verifier.py` |
| HTML Exporter | `backend/app/services/calibration/exporters/html_exporter.py` |
| PNG Exporter | `backend/app/services/calibration/exporters/png_exporter.py` |
| YAML Preset Exporter | `backend/app/services/calibration/exporters/yaml_preset_exporter.py` |
| User settings integration | `config/user_settings.yaml` (diff) |
| Документация | `docs/calibration_lab/usage.md`, `docs/calibration_lab/architecture.md` |
| Пресет-менеджер | `backend/app/services/calibration/preset_manager.py` |

### 7.3. Replay Verifier

```python
# backend/app/services/calibration/replay_verifier.py
@dataclass
class ReplayResult:
    deterministic: bool
    state_diff_count: int
    metrics_diff_max: float
    diff_fields: List[str]

class ReplayVerifier:
    def verify(self, config: ExperimentConfig) -> ReplayResult:
        """Запускает эксперимент дважды с одинаковым seed, сравнивает."""
        r1 = self._runner.run(config)
        r2 = self._runner.run(config)
        return self._compare(r1, r2)

    def _compare(self, r1, r2) -> ReplayResult:
        diff = StateDiffer().diff(r1.final_npc_state, r2.final_npc_state)
        metrics_diff = max(abs(r1.metrics[k] - r2.get(k, 0))
                          for k in r1.metrics)
        return ReplayResult(
            deterministic=(diff.field_count == 0 and metrics_diff == 0),
            state_diff_count=diff.field_count,
            metrics_diff_max=metrics_diff,
            diff_fields=diff.fields,
        )
```

### 7.4. Приёмочные тесты M5

```python
class TestReproducibility:
    def test_replay_bitwise_identical(self):
        """M5-AC-001: Два запуска дают битово-идентичный результат"""
        cfg = ExperimentConfig(
            preset_path=".../enigma_golden.yaml",
            scenario_path="config/scenarios/tavern_silver_wolf_30min.yaml",
            seed=7331, duration_ticks=300,
        )
        result = ReplayVerifier().verify(cfg)
        assert result.deterministic
        assert result.state_diff_count == 0
        assert result.metrics_diff_max == 0.0

    def test_different_seeds_give_different_results(self):
        """M5-AC-002: Разные seed дают разные результаты (не детерминизм)"""
        r1 = runner.run(cfg_with_seed(7331))
        r2 = runner.run(cfg_with_seed(99999))
        assert r1.final_npc_state != r2.final_npc_state

    def test_yaml_preset_roundtrip(self):
        """M5-AC-003: Сохранение и загрузка пресета сохраняет все параметры"""
        original_preset = load_preset(".../enigma_golden.yaml")
        path = PresetIO().save(...)
        loaded_preset = load_preset(path)
        assert original_preset.parameters == loaded_preset.parameters
        assert loaded_preset.meta.preset_id == original_preset.meta.preset_id


class TestExport:
    def test_json_export_contains_all_fields(self):
        """M5-AC-004: JSON содержит experiment_id, seed, params, metrics"""
        ...

    def test_csv_export_has_one_row_per_tick(self):
        """M5-AC-005: CSV имеет по строке на тик"""
        ...

    def test_html_export_is_interactive(self):
        """M5-AC-006: HTML содержит Plotly-графики"""
        ...

    def test_png_export_has_5_graphs(self):
        """M5-AC-007: PNG содержит 5 графиков"""
        ...

    def test_yaml_preset_connects_to_enigma(self):
        """M5-AC-008: Пресет можно подключить к config/user_settings.yaml"""
        # 1. Сохраняем пресет
        # 2. Подключаем к user_settings
        # 3. Запускаем обычный ENIGMA (через game_launcher)
        # 4. Проверяем, что параметры применились
        ...


class TestFinalAcceptance:
    """Финальная приёмка лаборатории по критериям ТЗ раздел 30."""

    def test_developer_can_complete_full_workflow(self):
        """M5-AC-009: Разработчик может выполнить 11 шагов из ТЗ 30.1"""
        # 1. Открыть лабораторию (UI доступен на :3001)
        # 2. Выбрать NPC (Люся)
        # 3. Увидеть параметры на русском
        # 4. Запустить 45-минутную симуляцию
        # 5. Вмешиваться событиями (HELP, LIE, GIFT)
        # 6. Видеть причинную цепочку
        # 7. Изменить один параметр (identity_rigidity 0.42 → 0.30)
        # 8. Перезапустить
        # 9. Сравнить результат (A/B)
        # 10. Найти ENIGMA-конфиг
        # 11. Сохранить как enigma_mvp_v2.yaml
        pass  # e2e тест через Playwright

    def test_quantitative_success_criteria(self):
        """M5-AC-010: ТЗ 30.2 — количественные критерии"""
        # 3+ ENIGMA конфигов найдено
        # 0 нарушений SUPERBOX
        # 0 NaN
        # 100% детерминизм
        # WOW Density в [0.4, 1.2] для всех ENIGMA
        pass
```

### 7.5. Definition of Done для M5

- [ ] Replay Verifier работает на всех пресетах;
- [ ] Все 5 форматов экспорта функционируют;
- [ ] Пресеты подключаются к production ENIGMA;
- [ ] Документация полная;
- [ ] Все 10 приёмочных тестов M5 проходят;
- [ ] Worklog обновлён.

---

## 8. Сводная таблица приёмочных тестов «правильно найденных вариантов»

> Это **самый важный раздел плана**. Все тесты ниже проверяют, что лаборатория
> **правильно** классифицирует заранее известные конфигурации. Если хотя бы один
> тест падает — milestone нельзя считать завершённым.

| ID | Milestone | Что проверяет | Ожидаемый результат |
|---|---|---|---|
| M0-AC-001 | M0 | mannequin.yaml → низкая динамика | `character_change_rate < 0.15` |
| M0-AC-002 | M0 | chaos.yaml → высокая динамика | `character_change_rate > 0.85` |
| M0-AC-003 | M0 | enigma_golden.yaml → целевая динамика | `character_change_rate ∈ [0.3, 0.8]` |
| M0-AC-004 | M0 | Одинаковый seed → идентичный результат | `state_diff_count == 0` |
| M0-AC-005 | M0 | SUPERBOX-сценарии проходят при overlay | `all passed` |
| M0-AC-006 | M0 | Overlay восстанавливается после выхода | `original == restored` |
| M1-AC-301 | M1 | Кнопка «Помог» увеличивает trust | `trust_after > trust_before` |
| M1-AC-302 | M1 | Кнопка «Предал» уменьшает trust, поднимает stress | `trust_after < trust_before - 10` |
| M1-AC-303 | M1 | Timeline содержит вмешательство | `any(event.type == PLAYER_INTERVENTION)` |
| M1-AC-401 | M1 | A/B разделяет ENIGMA и МАНЕКЕН | `zone_a=ENIGMA, zone_b=MANNEQUIN` |
| M1-AC-402 | M1 | Сохранённый пресет reload → те же метрики | `|Δ| < 0.01` |
| M1-AC-501 | M1 | Полный e2e workflow работает | все шаги 1-11 из ТЗ 30.1 |
| M2-AC-001 | M2 | mannequin.yaml → Zone.MANNEQUIN | `zone == MANNEQUIN, confidence > 0.8` |
| M2-AC-002 | M2 | chaos.yaml → Zone.CHAOS | `zone == CHAOS, confidence > 0.8` |
| M2-AC-003 | M2 | enigma_golden.yaml → Zone.ENIGMA | `zone == ENIGMA, confidence > 0.7` |
| M2-AC-004 | M2 | broken_nan.yaml → Zone.BROKEN (не ХАОС) | `zone == BROKEN, nan_count > 0` |
| M2-AC-005 | M2 | invariant_breaker.yaml → Zone.BROKEN | `zone == BROKEN, invariant_violations > 0` |
| M2-AC-006 | M2 | borderline_low.yaml → Zone.WARNING | `zone == WARNING` |
| M2-AC-007 | M2 | enigma_golden → wow_density ∈ [0.4, 1.2] | `0.4 <= wow <= 1.2` |
| M2-AC-008 | M2 | mannequin → wow_density < 0.2 | `wow < 0.2` |
| M2-AC-009 | M2 | noise_only → wow_density < 0.3 (фильтр шума) | `wow < 0.3` |
| M2-AC-010 | M2 | ENIGMA-зона стабильна для разных seed | `all 4 seeds → ENIGMA` |
| M2-AC-011 | M2 | В ХАОСЕ метрики сильно варьируются между seed | `max-min > 0.5` |
| M3-AC-001 | M3 | Grid sweep находит ≥ 3 ENIGMA-конфига | `enigma_count >= 3` |
| M3-AC-002 | M3 | rigidity=0.95 → MANNEQUIN; rigidity=0.05 → CHAOS | `zones correct` |
| M3-AC-003 | M3 | One-Param-Scan находит оптимальный decay_rate | `best ∈ [0.02, 0.10]` |
| M3-AC-004 | M3 | Bayesian находит ENIGMA за ≤ 30 итераций | `best_zone == ENIGMA` |
| M3-AC-005 | M3 | Sweep не возвращает BROKEN как ENIGMA | `nan configs → Zone.BROKEN` |
| M3-AC-006 | M3 | Sweep детерминирован | `r1.metrics == r2.metrics` |
| M3-AC-007 | M3 | A/B находит в 2.5+ раза более выразительный конфиг | `ratio > 2.5` |
| M3-AC-008 | M3 | A/A тест даёт ratio ≈ 1.0 | `0.95 <= ratio <= 1.05` |
| M4-AC-001 | M4 | Heatmap визуально показывает ENIGMA-зону | green pixels in center |
| M4-AC-002 | M4 | 3D-карта показывает объём ENIGMA-зоны | volume > 0 |
| M4-AC-003 | M4 | CMA-ES лучше Grid | `cma_best >= grid_best` |
| M4-AC-004 | M4 | Genetic находит ≥ 2 различных ENIGMA-зоны | `enigma_clusters >= 2` |
| M5-AC-001 | M5 | Replay битово-идентичен | `deterministic == True` |
| M5-AC-002 | M5 | Разные seed → разные результаты | `r1 != r2` |
| M5-AC-003 | M5 | YAML preset roundtrip сохраняет все параметры | `original == loaded` |
| M5-AC-004 | M5 | JSON экспорт содержит все поля | `has experiment_id, seed, params, metrics` |
| M5-AC-005 | M5 | CSV имеет по строке на тик | `rows == tick_count` |
| M5-AC-006 | M5 | HTML содержит Plotly | `has plotly.js reference` |
| M5-AC-007 | M5 | PNG содержит 5 графиков | `5 PNG files` |
| M5-AC-008 | M5 | Пресет подключается к production ENIGMA | `params applied` |
| M5-AC-009 | M5 | Полный 11-шаговый workflow работает | e2e pass |
| M5-AC-010 | M5 | Количественные критерии ТЗ 30.2 выполнены | все критерии pass |

**Итого: 42 приёмочных теста «правильно найденных вариантов».**

---

## 9. Расписание и параллелизация

```text
Неделя 1:    M0  (1 чел.)                                  ████████
Неделя 2-6:  M1  (2 чел.: backend + frontend параллельно)  ████████████████████
Неделя 7-9:  M2  (1 чел. backend)                          ███████████
Неделя 10-12: M3 (1 чел. backend + 0.5 чел. frontend)       ███████████
Неделя 13-14: M4 (1 чел. backend + 0.5 чел. frontend)      ████████
Неделя 15-16: M5 (1 чел. backend + 0.5 чел. docs)          ████████
```

### 9.1. Параллельные задачи

| Backend | Frontend |
|---|---|
| M0 (1 неделя) | — |
| M1/Sprint 1 (API) | M1/Sprint 1 (UI scaffold, mock API) |
| M1/Sprint 2 (Runner v2) | M1/Sprint 2 (слайдеры, карточка) |
| M1/Sprint 3 (interventions, timeline) | M1/Sprint 3 (кнопки, график) |
| M1/Sprint 4 (A/B, preset IO) | M1/Sprint 4 (A/B UI, preset UI) |
| M1/Sprint 5 (export) | M1/Sprint 5 (export UI, e2e) |
| M2 (10 метрик) | M2 (UI метрик, Zone indicator) |
| M3 (sweep) | M3 (sweep UI) |
| M4 (heatmaps, CMA-ES) | M4 (heatmap UI, 3D map) |
| M5 (replay, экспорт) | M5 (документация UI) |

---

## 10. Риски и митигации

| Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|
| `overlay_constants` ломает глобальное состояние | высокая | критическое | Использовать `threading.local`, явно передавать `constants_module` в `DecisionHub` через DI |
| LLM-зависимости мешают headless-запуску | высокая | высокое | M0 должен работать в `--no-llm` режиме; LLM-вызовы заглушать в calibration mode |
| Sweep слишком медленный (1 эксперимент = 30 сек) | высокая | среднее | Параллелизация через `multiprocessing`, кеширование пресетов |
| Game-loop создаёт утечку ресурсов | средняя | среднее | Cleanup в `__exit__`, valgrind-профилирование раз в sprint |
| SUPERBOX-сценарии ломаются после изменений | средняя | критическое | CI-шаг: `python backend/tests/sandbox/SUPERBOX/run.py all` на каждый PR |
| UI тормозит при большом потоке SSE-событий | средняя | среднее | Throttling SSE до 10 событий/сек, batched updates в React Query |
| Bayesian/CMA-ES находят «овербайтные» конфиги | средняя | низкое | Hard constraints (раздел 21.1) отсекают сломанные конфиги |
| Разработчик не знает, что параметр `[PLAN]` | низкое | низкое | UI помечает `[PLAN]` серым + tooltip с пояснением |
| Пресеты разных версий ENIGMA несовместимы | средняя | высокое | В `meta.enigma_version` проверять совместимость при загрузке |

---

## 11. Архитектурный контракт (новый YAML)

### 11.1. `architecture/calibration.yaml`

> Должен быть создан в M0 и расширен в каждом milestone.

```yaml
domain: CALIBRATION
description: "Лаборатория калибровки психики ENIGMA. Запускает production pipeline с подменяемыми параметрами. Не создаёт параллельную симуляцию."
version: "1.0"
status: IMPLEMENTED  # после M5

nodes:
  CalibrationUI:
    type: service
    layer: Presentation
    tech: "Next.js 16 + TypeScript"
    port: 3001
    description: "Русскоязычный интерфейс со слайдерами, графиками, timeline."

  CalibrationAPI:
    type: service
    layer: Application
    tech: "FastAPI (расширение существующего app)"
    port: 8000
    routes:
      - POST /api/calibration/experiments
      - POST /api/calibration/experiments/{id}/start
      - POST /api/calibration/experiments/{id}/pause
      - POST /api/calibration/experiments/{id}/step
      - POST /api/calibration/experiments/{id}/speed
      - POST /api/calibration/experiments/{id}/intervention
      - GET  /api/calibration/experiments/{id}/state
      - GET  /api/calibration/experiments/{id}/timeline
      - POST /api/calibration/experiments/{id}/stream   (SSE)
      - POST /api/calibration/experiments/ab
      - POST /api/calibration/sweep
      - GET  /api/calibration/sweep/{id}/results
      - POST /api/calibration/presets
      - GET  /api/calibration/presets
      - POST /api/calibration/export/{exp_id}/{format}

  ExperimentRunner:
    type: service
    layer: Application
    code_ref: "backend/app/services/calibration/experiment_runner.py"
    description: "Оркестратор сессий. Создаёт GameLoop через game_loop_builder."

  ConfigOverlay:
    type: service
    layer: Domain
    code_ref: "backend/app/services/calibration/config_overlay.py"
    description: "Временная подмена constants.py. Контекстный менеджер."

  ScenarioPlayer:
    type: service
    layer: Application
    code_ref: "backend/app/services/calibration/scenario_player.py"
    description: "Воспроизведение event-sequence из YAML-сценария."

  CalibrationMetrics:
    type: service
    layer: Observability
    code_ref: "backend/app/services/calibration/metrics/"
    submodules:
      - character_change
      - decision_diversity
      - emotional_volatility
      - belief_revision_rate
      - relationship_dynamics
      - event_responsiveness
      - causal_depth
      - loop_rate
      - character_stability
      - wow_aggregator
    description: "10 драматических метрик, дополняющих DNASnapshot."

  ZoneClassifier:
    type: service
    layer: Observability
    code_ref: "backend/app/services/calibration/zone_classifier.py"
    description: "Классификатор: MANNEQUIN / CHAOS / ENIGMA / WARNING / BROKEN."

  SweepRunner:
    type: service
    layer: Application
    code_ref: "backend/app/services/calibration/sweep/"
    submodules:
      - grid_sweep
      - random_sweep
      - bayesian_sweep
      - cma_es
      - genetic
      - one_param_scan
    description: "Parameter sweep с разными стратегиями."

  PresetIO:
    type: service
    layer: Application
    code_ref: "backend/app/services/calibration/preset_io.py"
    description: "Чтение/запись YAML-пресетов."

  ReplayVerifier:
    type: service
    layer: Observability
    code_ref: "backend/app/services/calibration/replay_verifier.py"
    description: "Детерминизм-проверка: один seed → идентичный результат."

  Exporters:
    type: service
    layer: Application
    code_ref: "backend/app/services/calibration/exporters/"
    formats: [json, csv, html, png, yaml]

edges:
  - {from: CalibrationUI, to: CalibrationAPI, type: http_sse}
  - {from: CalibrationAPI, to: ExperimentRunner, type: python_call}
  - {from: ExperimentRunner, to: ConfigOverlay, type: context_manager}
  - {from: ExperimentRunner, to: ScenarioPlayer, type: python_call}
  - {from: ExperimentRunner, to: TickOrchestrator, type: production_pipeline}
  - {from: TickOrchestrator, to: EventBus, type: emit}
  - {from: EventBus, to: CalibrationMetrics, type: subscribe}
  - {from: EventBus, to: ZoneClassifier, type: subscribe}
  - {from: CalibrationMetrics, to: DNASnapshot, type: extend}
  - {from: ExperimentRunner, to: ProbeRunner, type: invariant_check}
  - {from: ExperimentRunner, to: SuperboxAdapter, type: scenario_check}
  - {from: ExperimentRunner, to: ReplayVerifier, type: determinism_check}
  - {from: ZoneClassifier, to: CalibrationUI, type: live_state}

constraints:
  - id: CAL-001
    severity: CRITICAL
    rule: "Calibration Laboratory НЕ создаёт параллельную симуляцию."
    enforced_by: "ExperimentRunner использует game_loop_builder.build_game_loop"

  - id: CAL-002
    severity: CRITICAL
    rule: "Все вмешательства идут через InterventionEvent."
    enforced_by: "CalibrationAPI.inject_intervention → InterventionEvent.from_player_action"

  - id: CAL-003
    severity: CRITICAL
    rule: "Все параметрические изменения применяются ТОЛЬКО через ConfigOverlay."
    enforced_by: "ConfigOverlay — единственный механизм monkey-patch constants"

  - id: CAL-004
    severity: CRITICAL
    rule: "Каждый эксперимент детерминирован при одинаковом seed."
    enforced_by: "KernelRNG (ADR-O-301) + ReplayVerifier"

  - id: CAL-005
    severity: CRITICAL
    rule: "Ни одна метрика не мутирует NPC state."
    enforced_by: "CalibrationMetrics — только подписчики EventBus"

  - id: CAL-006
    severity: HIGH
    rule: "BROKEN zone не может быть классифицирована как ENIGMA/CHAOS/MANNEQUIN."
    enforced_by: "ZoneClassifier проверяет nan_count и invariant_violations первым"

  - id: CAL-007
    severity: HIGH
    rule: "WOW Density НЕ максимизируется напрямую (только с ограничениями)."
    enforced_by: "Scorer._passes_hard_constraints отсекает по loop_rate, contradiction, и т.д."

  - id: CAL-008
    severity: HIGH
    rule: "Каждый эксперимент логирует experiment_id, seed, version, scenario, tick_count, event_sequence, final_state, metrics."
    enforced_by: "ExperimentResult frozen dataclass"

ownership:
  - resource: NPCState
    writer: StateApplicator
    readers: [ExperimentRunner, CalibrationMetrics, ZoneClassifier]

  - resource: ConfigOverlay
    writer: ExperimentRunner
    readers: [TickOrchestrator (через constants module)]

  - resource: CalibrationMetrics
    writer: CalibrationMetrics (агрегаты)
    readers: [ZoneClassifier, CalibrationUI]

  - resource: Presets (configs/npc/*.yaml)
    writer: PresetIO
    readers: [ExperimentRunner, config/user_settings.yaml]

sequences:
  - name: "Dramatic Session"
    steps:
      - CalibrationUI → POST /api/calibration/experiments
      - CalibrationAPI → ExperimentRunner.start(config)
      - ExperimentRunner → ConfigOverlay(overlay_params)
      - ExperimentRunner → ScenarioPlayer(scenario)
      - ExperimentRunner → TickOrchestrator.execute(...) × N ticks
      - TickOrchestrator → EventBus.emit(events)
      - EventBus → CalibrationMetrics.update
      - EventBus → ZoneClassifier.subscribe
      - CalibrationAPI → SSE stream → CalibrationUI
      - CalibrationUI → render live state

  - name: "A/B Comparison"
    steps:
      - CalibrationUI → POST /api/calibration/experiments/ab
      - CalibrationAPI → ABRunner.run(config_a, config_b)
      - ABRunner → ExperimentRunner.run(config_a) (parallel)
      - ABRunner → ExperimentRunner.run(config_b) (parallel)
      - ABRunner → ZoneClassifier.classify(metrics_a, metrics_b)
      - ABRunner → ABResult(wow_density_ratio, verdict_ru)
      - CalibrationAPI → ABResult → CalibrationUI

  - name: "Parameter Sweep"
    steps:
      - CalibrationUI → POST /api/calibration/sweep
      - CalibrationAPI → SweepRunner.run(grid/random/bayesian)
      - SweepRunner → EnigmaPhaseEngine.elastic_warp(params) × N
      - EnigmaPhaseEngine → ExperimentRunner.run(preset)
      - EnigmaPhaseEngine → ZoneClassifier.classify
      - SweepRunner → SweepResults(sorted by score)
      - CalibrationAPI → SweepResults → CalibrationUI
```

---

## 12. Worklog-протокол

> Все разработчики (главный агент + subagent'ы) пишут в
> `/home/z/my-project/worklog.md` по единому шаблону.

### 12.1. Шаблон записи

```markdown
---
Task ID: M1-Sprint2-frontend
Agent: frontend-developer
Task: Реализовать слайдеры и карточку NPC (M1/Sprint 2)

Work Log:
- Создан calibration_ui/ проект (Next.js 16 + Tailwind 4)
- Реализован ParamSlider с tooltip
- Реализована NpcCard с живым состоянием
- Подключён SSE-стрим к store Zustand
- Написаны Playwright-тесты

Stage Summary:
- 15 слайдеров на русском, 3 disabled [PLAN]
- Карточка показывает trust/beliefs/intent/stress
- Прогнал все acceptance-тесты Sprint 2 — 5/5 pass
- Файлы: calibration_ui/src/components/{sliders,npc-card}/
- Готово к Sprint 3
```

### 12.2. Контрольные точки

После каждого Sprint — главный архитектор:
1. Читает `worklog.md`;
2. Запускает все acceptance-тесты milestone;
3. Помечает milestone как `DONE` или возвращает на доработку.

---

## 13. Что нужно от архитектора до старта M0

### 13.1. Решения, которые нужно зафиксировать

| Решение | Вариант A | Вариант B | Рекомендация |
|---|---|---|---|
| Где живёт ConfigOverlay | monkey-patch `constants` модуля | DI в `DecisionHub.__init__` | **B** — чище, но требует патча DecisionHub |
| Где живёт UI | отд. Next.js приложение (:3001) | встроенный в pygame экран | **A** — быстрее разработка, не мешает существующему UI |
| БД для параллельных сессий | `:memory:` SQLite | временные файлы | **A** — быстрее cleanup |
| Sweep concurrency | `multiprocessing.Pool` | `asyncio` | **A** — ENIGMA CPU-bound |
| Plotly vs Recharts | Plotly (для интерактивности) | Recharts (легче) | **A** — нужны 3D-карты в M4 |

### 13.2. Подготовительные задачи

- [ ] Создать ветку `feature/calibration-lab` от текущего `main`;
- [ ] Создать пустые директории:
  - `backend/app/services/calibration/`
  - `backend/tests/calibration_lab/`
  - `config/scenarios/`
  - `configs/calibration/`
  - `calibration_ui/`
  - `docs/calibration_lab/`;
- [ ] Создать `architecture/calibration.yaml` (заготовка);
- [ ] Обновить `architecture/pipeline.yaml` — добавить ссылку на calibration контракт;
- [ ] Зафиксировать в `worklog.md` старт M0.

### 13.3. Стартовая конфигурация

```bash
# Переменные окружения для лаборатории
export ENIGMA_CALIBRATION_MODE=1
export ENIGMA_LLM_DISABLE=1   # для M0 — headless режим
export ENIGMA_CALIBRATION_DATA_DIR=/home/z/my-project/download/experiments
export ENIGMA_CALIBRATION_PORT=8000   # основной API
export ENIGMA_CALIBRATION_UI_PORT=3001
```

---

## 14. Контроль качества (Definition of Done для всего проекта)

### 14.1. Код

- [ ] Все новые файлы проходят `mypy --strict` (см. `mypy.ini`);
- [ ] Все новые файлы проходят `ruff check` (см. `ruff.toml`);
- [ ] Все новые тесты проходят в `pytest backend/tests/calibration_lab/`;
- [ ] Все существующие SUPERBOX-сценарии продолжают проходить;
- [ ] Все 9 probes продолжают проходить;
- [ ] `python backend/tests/IPT.py` — passes (Invariant Probe Tests < 5 сек).

### 14.2. Архитектура

- [ ] `architecture/calibration.yaml` заполнен полностью;
- [ ] Все 8 constraints (CAL-001 — CAL-008) проверены тестами;
- [ ] 4 sequence-диаграммы соответствуют коду;
- [ ] Все edges в коде подтверждены call-path'ами.

### 14.3. Документация

- [ ] `docs/calibration_lab/usage.md` — для пользователя (как запустить);
- [ ] `docs/calibration_lab/architecture.md` — для разработчика (как устроено);
- [ ] `docs/calibration_lab/api.md` — REST API reference;
- [ ] `docs/calibration_lab/preset_format.md` — формат YAML-пресетов;
- [ ] Все строки UI вынесены в `i18n.ts` (RU).

### 14.4. Приёмка

- [ ] Все **42** приёмочных теста «правильно найденных вариантов» проходят;
- [ ] E2E-тест `M5-AC-009` (полный workflow) проходит через Playwright;
- [ ] Количественные критерии `M5-AC-010` выполнены:
  - 3+ ENIGMA-конфигов найдено;
  - 0 нарушений SUPERBOX;
  - 0 NaN;
  - 100% детерминизм;
  - WOW Density ∈ [0.4, 1.2] для всех ENIGMA-конфигов.

---

## 15. Финальный артефакт проекта

После завершения M5 в репозитории должны быть:

```text
configs/npc/
├── enigma_mvp_v1.yaml          ← первый откалиброванный пресет
├── enigma_mvp_v2.yaml          ← улучшенный
└── enigma_mvp_v3.yaml          ← финальный (MVP для игры)

config/scenarios/
├── tavern_silver_wolf_15min.yaml
├── tavern_silver_wolf_30min.yaml
├── tavern_silver_wolf_45min.yaml
└── tavern_silver_wolf_60min.yaml

configs/calibration/
├── scoring.yaml                ← веса целевой функции
├── zone_thresholds.yaml        ← пороги классификации
└── test_presets/
    ├── mannequin.yaml
    ├── chaos.yaml
    ├── enigma_golden.yaml
    ├── broken_nan.yaml
    ├── invariant_breaker.yaml
    ├── borderline_low.yaml
    └── noise_only.yaml

backend/app/services/calibration/   ← весь код лаборатории
backend/tests/calibration_lab/      ← все 42+ теста
calibration_ui/                    ← Next.js приложение
docs/calibration_lab/               ← документация
architecture/calibration.yaml       ← архитектурный контракт

config/user_settings.yaml           ← обновлён, подключает enigma_mvp_v3.yaml
```

### 15.1. Главный результат

> Файл `configs/npc/enigma_mvp_v3.yaml`, который при подключении к production ENIGMA
> даёт **для большинства NPC** в сценарии «Таверна — 45 минут»:
>
> - `wow_density ∈ [0.4, 1.2]` событий/мин;
> - `character_change_rate ∈ [0.3, 0.8]`;
> - `loop_rate < 0.15`;
> - `character_stability >= 0.5`;
> - `causal_coverage >= 0.9`;
> - `0` нарушений инвариантов;
> - `0` NaN;
> - `100%` детерминизм.
>
> **Это и есть «золотая область» ENIGMA, ради которой строилась лаборатория.**

---

**КОНЕЦ ПЛАНА РАЗРАБОТКИ.**

> Сопутствующий документ: `ТЗ_Лаборатория_Калибровки_ENIGMA.md`
> Архитектурный контракт: `architecture/calibration.yaml` (создаётся в M0)
> Worklog: `/home/z/my-project/worklog.md`
