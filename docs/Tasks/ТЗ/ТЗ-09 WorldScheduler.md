## ТЗ-09: WorldScheduler — активация

**Статус:** ❌ МЁРТВЫЙ | **Критичность:** HIGH | **Волна:** 3 (зависит от ТЗ-07, ТЗ-10)

---

### Суть проблемы одной строкой

Мир изменяется **только** когда игрок нажимает кнопку. Между ходами — статика: NPC стоят, экономика замёрзла, время не идёт. WorldScheduler возвращает заглушку.

---

### Что происходит сейчас

**Файл:** `backend/app/services/world_scheduler.py` строки 33-43

```python
# СЕЙЧАС (мёртвый):
def maybe_tick(self, ...) -> dict:
    result = {
        "world_events": [],
        "simulation_log": "disabled_pending_phase6"
    }
    return result  # ← заглушка, мир не тикает
```

**Следствия:**

| Что не работает | Почему |
|----------------|--------|
| NPC не действуют между ходами | proactive decisions не генерируются |
| Экономика стагнирует | цены, спрос, предложение не меняются |
| Время стоит | часы не идут, дни не сменяются |
| Потребности не растут | NPC не голодает, не устаёт |
| Мир «реактивный» | всё происходит только в ответ на игрока |

---

### Как должен работать живой мир

```
Ход игрока: "Иду на рынок"
    ↓
Фаза 1: обработать ввод
Фаза 2: мир тикает (NPC действуют, время идёт)
Фаза 3-6: решения, применение
    ↓
Результат: игрок видит ИЗМЕНИВШИЙСЯ мир
    - Торговец уже пересчитал цены
    - Стражник сменился на посту
    - Прошёл 1 час игрового времени
    - В таверне появился новый посетитель
```

---

### Пошаговый план исправления

#### Шаг 1: Убрать заглушку, реализовать реальную логику

**Файл:** `backend/app/services/world_scheduler.py`

```python
class WorldScheduler:
    """Планировщик мировых тиков — автономная жизнь мира"""
    
    def __init__(
        self,
        world_tick_engine: WorldTickEngine,
        temporal_engine: TemporalEngine,
        state_applicator: StateApplicator,
        event_bus: EventBus,
    ):
        self.world_tick_engine = world_tick_engine
        self.temporal_engine = temporal_engine
        self.state_applicator = state_applicator
        self.event_bus = event_bus
        self._last_world_tick: int = 0
    
    async def maybe_tick(
        self,
        ctx: TickContext,
        force: bool = False,
    ) -> WorldSchedulerResult:
        """
        Выполнить мировой тик, если условия выполнены.
        
        Условия (любое из):
          - прошёл WORLD_TICK_INTERVAL_TICKS с последнего мирового тика
          - игрок бездействует > WORLD_TICK_IDLE_THRESHOLD секунд
          - force=True (принудительный тик)
        """
        should_tick, reason = self._should_tick(ctx, force)
        if not should_tick:
            return WorldSchedulerResult(ticked=False, events=[], log="skipped")
        
        # Продвинуть время
        temporal_ctx = self.temporal_engine.advance_tick()
        
        # Вычислить проактивные решения NPC
        tick_result = await self.world_tick_engine.compute_proactive_decisions(
            location_id=ctx.location_id,
            npcs=ctx.active_npcs,
            temporal_context=temporal_ctx,
            economy_state=ctx.economy_state,
        )
        
        # Применить решения через StateApplicator
        if tick_result.deltas:
            self.state_applicator.apply_all(tick_result.deltas)
        
        # Проверить смену дня
        if temporal_ctx.is_new_day:
            await self._process_new_day(ctx, temporal_ctx)
        
        # Обновить экономику
        economy_events = await self._tick_economy(ctx, temporal_ctx)
        
        # Сгенерировать события для DM-нарратива
        all_events = tick_result.events + economy_events
        
        self._last_world_tick = ctx.current_tick
        
        return WorldSchedulerResult(
            ticked=True,
            events=all_events,
            log=f"world_tick: {reason}, {len(all_events)} events",
            temporal_context=temporal_ctx,
        )
    
    def _should_tick(self, ctx: TickContext, force: bool) -> Tuple[bool, str]:
        """Определить, нужен ли мировой тик"""
        if force:
            return True, "forced"
        
        ticks_since_last = ctx.current_tick - self._last_world_tick
        if ticks_since_last >= self.WORLD_TICK_INTERVAL_TICKS:
            return True, f"interval ({ticks_since_last} ticks)"
        
        idle_seconds = ctx.player_idle_seconds or 0
        if idle_seconds >= self.WORLD_TICK_IDLE_THRESHOLD:
            return True, f"player_idle ({idle_seconds}s)"
        
        return False, "not_needed"
```

---

#### Шаг 2: Добавить настройки WorldScheduler

**Файл:** `backend/app/core/config.py` или `settings_world.py`

```python
# Настройки мирового тика
WORLD_TICK_INTERVAL_TICKS: int = 5      # каждые 5 игровых тиков
WORLD_TICK_IDLE_THRESHOLD: int = 30     # через 30 сек бездействия игрока
WORLD_TICK_MIN_INTERVAL_SECONDS: int = 10  # минимальный реальный интервал

# Настройки нового дня
NEW_DAY_NEEDS_RESET: bool = True        # сбрасывать потребности при смене дня
NEW_DAY_ECONOMY_RESET: bool = True      # сбрасывать экономические трекеры
NEW_DAY_NPC_ROUTINE: bool = True        # обновлять рутины NPC
```

---

#### Шаг 3: Реализовать обработку смены дня

**Файл:** `backend/app/services/world_scheduler.py`

```python
async def _process_new_day(self, ctx: TickContext, temporal: TemporalContext):
    """Каскадные эффекты при смене игрового дня"""
    events = []
    
    # 1. Потребности NPC: голод растёт, усталость накапливается
    if self.NEW_DAY_NEEDS_RESET:
        for npc in ctx.active_npcs:
            # Голод увеличивается каждый день
            npc.needs.food = min(1.0, npc.needs.food + 0.2)
            npc.needs.shelter = min(1.0, npc.needs.shelter + 0.1)
            # Усталость сбрасывается (NPC спал)
            npc.body_state.fatigue = max(0, npc.body_state.fatigue - 0.3)
            
            events.append(SceneEvent(
                type="NEW_DAY_NEEDS_UPDATE",
                npc_id=npc.npc_id,
                data={"food": npc.needs.food, "fatigue": npc.body_state.fatigue},
            ))
    
    # 2. Экономика: сбросить дневные трекеры
    if self.NEW_DAY_ECONOMY_RESET:
        await self._reset_daily_economy(ctx)
        events.append(SceneEvent(
            type="NEW_DAY_ECONOMY_RESET",
            data={"day": temporal.game_day},
        ))
    
    # 3. Рутины NPC: переключить на дневное расписание
    if self.NEW_DAY_NPC_ROUTINE:
        for npc in ctx.active_npcs:
            new_activity = self._get_routine_for_hour(
                npc, temporal.game_hour
            )
            if new_activity:
                npc.current_activity = new_activity
                events.append(SceneEvent(
                    type="ROUTINE_CHANGE",
                    npc_id=npc.npc_id,
                    data={"activity": new_activity, "hour": temporal.game_hour},
                ))
    
    return events

def _get_routine_for_hour(self, npc: NPCState, hour: int) -> Optional[str]:
    """Определить активность NPC по расписанию и часу"""
    schedule = npc.schedule  # из архетипа
    if not schedule:
        return None
    
    for time_slot, activity in schedule.items():
        # time_slot = "06:00-12:00", activity = "working"
        start_h, end_h = self._parse_time_slot(time_slot)
        if start_h <= hour < end_h:
            return activity
    
    return "idle"
```

---

#### Шаг 4: Экономический подтик

**Файл:** `backend/app/services/world_scheduler.py`

```python
async def _tick_economy(
    self,
    ctx: TickContext,
    temporal: TemporalContext,
) -> List[SceneEvent]:
    """Обновить экономическое состояние мира"""
    events = []
    
    # 1. Обновить рыночную фазу (BOOM/STABLE/RECESSION/CRASH)
    market = self.economy_tracker.get_market_state()
    if temporal.is_new_day:
        new_phase = market.evaluate_phase_change()
        if new_phase != market.current_phase:
            market.current_phase = new_phase
            events.append(SceneEvent(
                type="MARKET_PHASE_CHANGE",
                data={
                    "old_phase": market.current_phase,
                    "new_phase": new_phase,
                    "reason": market.phase_change_reason,
                },
            ))
    
    # 2. Обновить цены товаров
    self.economy_tracker.tick_prices(temporal)
    
    # 3. Обновить спрос/предложение
    self.economy_tracker.tick_supply_demand(temporal)
    
    # 4. NPC-торговцы: обновить инвентарь
    for npc in ctx.active_npcs:
        if npc.role == "merchant":
            self.economy_tracker.restock_merchant(npc, temporal)
    
    return events
```

---

#### Шаг 5: Подключить WorldScheduler к GameLoop

**Файл:** `backend/app/services/game_loop/__init__.py` или `tick_orchestrator.py`

```python
# В основном цикле тика, ПОСЛЕ фазы ввода игрока и ДО фазы NPC:

async def _run_tick(self, ctx: TickContext) -> TickContext:
    # Фаза 1: ввод игрока
    ctx = await self._phase_1_input(ctx)
    
    # Фаза 1.5: МИРОВОЙ ТИК (НОВОЕ)
    world_result = await self.world_scheduler.maybe_tick(ctx)
    if world_result.ticked:
        # Добавить мировые события в контекст
        ctx.world_events = world_result.events
        ctx.temporal_context = world_result.temporal_context
        # DM должен учесть мировые события в нарративе
        ctx.dm_context_events.extend(world_result.events)
    
    # Фаза 2: NPC решения
    ctx = await self._phase_2_npc_decisions(ctx)
    # ... остальные фазы ...
```

---

#### Шаг 6: Передать контекст в WorldTickEngine

**Файл:** `backend/app/services/world/world_tick_engine.py`

```python
# СЕЙЧАС: compute_proactive_decisions() получает абстрактные данные
# ИСПРАВИТЬ: передать реальный контекст

async def compute_proactive_decisions(
    self,
    location_id: str,            # ← реальная локация (не "unknown"!)
    npcs: List[NPCState],        # ← список NPC с состояниями
    temporal_context: TemporalContext,  # ← время суток, день
    economy_state: EconomyState,  # ← рыночные данные
) -> WorldTickResult:
    """Вычислить проактивные действия NPC"""
    decisions = []
    events = []
    
    for npc in npcs:
        # NPC с расписанием — следуют рутине
        if npc.schedule and temporal_context:
            activity = self._resolve_routine(npc, temporal_context)
            if activity != npc.current_activity:
                decisions.append(ProactiveDecision(
                    npc_id=npc.npc_id,
                    action="routine_change",
                    target=activity,
                    reason="schedule",
                ))
        
        # Голодный NPC — идёт искать еду
        if npc.needs.food > 0.7:
            decisions.append(ProactiveDecision(
                npc_id=npc.npc_id,
                action="seek_food",
                target="tavern",  # из SemanticIndex
                reason="hunger",
            ))
        
        # Усталый NPC — идёт спать
        if npc.body_state.fatigue > 0.8:
            decisions.append(ProactiveDecision(
                npc_id=npc.npc_id,
                action="seek_rest",
                target="barracks",
                reason="fatigue",
            ))
    
    return WorldTickResult(decisions=decisions, events=events)
```

---

### Как проверить

```python
# Тест: мир тикает автономно
async def test_world_scheduler_ticks():
    ctx = create_test_context(current_tick=0)
    
    # Тик 1-4: мир не тикает (интервал = 5)
    for i in range(4):
        result = await scheduler.maybe_tick(ctx)
        assert result.ticked == False
    
    # Тик 5: мир тикает
    ctx.current_tick = 5
    result = await scheduler.maybe_tick(ctx)
    assert result.ticked == True
    assert len(result.events) > 0

# Тест: смена дня вызывает каскад
async def test_new_day_cascade():
    ctx = create_test_context(hour=23)
    
    # Продвинуть до полуночи
    temporal = temporal_engine.advance_tick()  # hour=0, is_new_day=True
    assert temporal.is_new_day == True
    
    result = await scheduler._process_new_day(ctx, temporal)
    
    # Потребности обновлены
    for npc in ctx.active_npcs:
        assert npc.needs.food > 0.0  # голод вырос
    
    # Экономика сброшена
    assert economy_tracker.daily_revenue == 0

# Тест: бездействие игрока вызывает мировой тик
async def test_idle_triggers_world_tick():
    ctx = create_test_context(player_idle_seconds=35)
    result = await scheduler.maybe_tick(ctx)
    assert result.ticked == True
```

---

### Порядок исправления

| # | Шаг | Время |
|---|-----|-------|
| 1 | Убрать заглушку, реализовать maybe_tick() | 45 мин |
| 2 | Настройки WORLD_TICK_* | 15 мин |
| 3 | _process_new_day() — каскад при смене дня | 45 мин |
| 4 | _tick_economy() — экономический подтик | 30 мин |
| 5 | Подключить к GameLoop/TickOrchestrator | 20 мин |
| 6 | Передать контекст в WorldTickEngine | 30 мин |
| 7 | Тесты | 30 мин |

**Итого:** ~3.5 часа

**Предпосылки:** ТЗ-07 (world_sim_agent.fix) + ТЗ-10 (аффективный pipeline подключён)

---

Давать следующее? Это **ТЗ-01: DecisionHub — подключение через API** (расширение входного контекста).