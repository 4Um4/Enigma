# The Fool (ENIGMA Engine)

Локальная narrative-RPG, где:
- Python считает причинность и состояние мира.
- LLM озвучивает уже вычисленный результат.
- NPC живут в time-driven симуляции, а не в скриптах.

Актуальная версия в этой ветке: `V.0.5.3.0.6_ПЕСОЧНИЦЫ_3`.

## Что такое The Fool

**The Fool** в ENIGMA — это цифровой DM с принципом:
- `LLM = Voice`
- `Python = Logic`

Это значит:
- реплика NPC не является источником истины;
- источник истины — runtime state + causality pipeline;
- бой, социальное давление, память и движение замкнуты в общий цикл.

## Что зафиксировано в V.0.5.3.0.6

### 1) LifeEngine de-godification (ADR-051)

- `LifeEngine` перестал напрямую двигать NPC через `MovementEngine`.
- `LifeEngine` теперь лоббирует: генерирует `MovementIntent`, а исполняет их `TickOrchestrator`.
- Расписание подавляется когнитивной угрозой (`perceptual_kernel.threat_gradient > 0.4`), чтобы NPC не «ломали» свежую причинность.

### 2) Единая пространственная истина (ADR-048)

- Убраны legacy-ветки чтения игрока из `player_spatial`.
- Игрок читается как `npc_id="player"` из `scene_state["npc_positions"]`.
- Снижен риск spatial divergence между Decision/Perception/Snapshot.

### 3) Замыкание Pressure -> Decision

- `pressure_translator` синхронизирован с актуальной геометрией `DecisionContext`:
  - `compliance_bias`
  - `initiative_suppression`
- `DecisionHub` теперь учитывает не только fear, но и `perceptual_kernel.threat_gradient`.

### 4) Каузальная обсерватория (ADR-050)

Добавлены отдельные sandbox-направления:
- `tests/sandbox/phenomenology/`
- `tests/sandbox/system/`
- `tests/sandbox/stress/`

Они проверяют не «наличие строк», а законы:
- эпистемическое расхождение наблюдателей;
- деградацию/восстановление воли под давлением;
- замыкание контура «возмущение -> давление -> решение».

## Будущее из docs/Tasks (направление проекта)

### 1) Variable Causal Density

Мир делится по плотности причинности:
- **LOD2 Myth Layer**: дальний мир аналитически проецируется.
- **LOD1 Observed Macro**: перемещения по узлам графа через intent/traversal.
- **LOD0 Observed Micro**: локальная непрерывная локомоция (`LocalSteeringIntent`).

### 2) Главный блокер следующего шага

Реализовать `LocalSteeringIntent`, чтобы микро-сближение не пыталось проходить через макро-граф.

### 3) Наблюдаемость как обязательство

Каждое архитектурное изменение доменов (fear/trust/will/intent) фиксируется через:
- ADR pre-flight;
- Impact audit в `docs/audits`;
- sandbox-регрессию в профильной папке (`micro`, `system`, `stress`, `phenomenology`).

## Архитектура (коротко)

```text
Pygame Frontend
  -> FastAPI
  -> GameLoop
  -> TickOrchestrator (Phase 0..10)
  -> EventBus + Memory + Decision + Spatial + CFRM
  -> WorldSnapshotDTO
  -> Frontend Presentation
```

Ключевые фазы:
- `0`: Life simulation
- `0.5`: time-driven decay handlers
- `1-7`: input -> event -> memory -> decision -> secondary events
- `8`: layered reduction
- `9`: CFRM + snapshot integration
- `10`: atomic persistence

## Запуск

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
pip install pygame
python game_launcher.py
```

Backend only:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Тесты

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests -v --tb=short
```

Sandbox smoke:

```powershell
..\.venv\Scripts\python.exe -m pytest tests\sandbox -q
```

## Документы, которые задают курс

- `docs/Tasks/ADR (Architecture Decision Records).md`
- `docs/Tasks/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md`
- `docs/Tasks/ТЕХЗАДАНИЕ ПРЕЕМНИКУ ДВИЖЕНИЯ.md`
- `docs/Tasks/MUTATIONS.md`
- `docs/Tasks/DTO Registry (Реестр контрактов).md`
- `docs/audits/ADR-048_IMPACT.md`
- `docs/audits/ADR-049_IMPACT.md`
- `docs/audits/ADR-050_IMPACT.md`
- `docs/audits/ADR-051_IMPACT.md`
