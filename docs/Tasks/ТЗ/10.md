## ТЗ-14: Cross-location Navigation — NPC переходят между локациями

**Статус:** ❌ СЛОМАН | **Критичность:** HIGH | **Волна:** 4 (зависит от ТЗ-02, ТЗ-06)

---

### Суть проблемы одной строкой

NPC не могут покинуть свою локацию. Нет intent'а TRANSIT, нет маршрутизации через boundary, нет schedule-driven переходов. Стражник стоит в таверне вечно.

---

### Почему NPC застревают

```
1. DecisionHub не формирует intent "перейти в другую локацию"
   → нет INTENT.TRANSIT в Enum

2. Даже если бы сформировал — MovementEngine не умеет
   → нет обработки CrossLocationPath (это ТЗ-02)

3. Расписание NPC говорит "sleeping → barracks"
   → но никто не проверяет schedule на смену локации

4. Арhetипы maid и thief не имеют activity_map
   → планировщик не знает, где они должны быть

5. Нет SemanticIndex для поиска локаций по смыслу
   → NPC не может сказать "идти в кузницу" (это ТЗ-02 шаг 4)
```

---

### Пошаговый план исправления

#### Шаг 1: Добавить INTENT.TRANSIT

**Файл:** `backend/app/models/npc_state.py` — найти Intent enum

```python
# СЕЙЧАС:
class Intent(str, Enum):
    IDLE = "IDLE"
    TALK = "TALK"
    ATTACK = "ATTACK"
    FLEE = "FLEE"
    GUARD = "GUARD"
    TRADE = "TRADE"
    # ... другие intents ...
    # TRANSIT отсутствует

# ИСПРАВИТЬ: добавить
class Intent(str, Enum):
    IDLE = "IDLE"
    TALK = "TALK"
    ATTACK = "ATTACK"
    FLEE = "FLEE"
    GUARD = "GUARD"
    TRADE = "TRADE"
    SEEK_FOOD = "SEEK_FOOD"
    SEEK_SHELTER = "SEEK_SHELTER"
    SEEK_HELP = "SEEK_HELP"
    SOCIALIZE = "SOCIALIZE"
    CRAFT = "CRAFT"
    GOSSIP = "GOSSIP"
    CALL_FOR_HELP = "CALL_FOR_HELP"
    SPREAD_RUMOR = "SPREAD_RUMOR"
    AMBUSH = "AMBUSH"
    BLOCK_PATH = "BLOCK_PATH"
    TRANSIT = "TRANSIT"  # ← НОВОЕ: переход в другую локацию
```

---

#### Шаг 2: Расширить IntentProfile для указания цели перехода

**Файл:** `backend/app/models/intent_profile.py` (или где определён IntentProfile)

```python
@dataclass
class IntentProfile:
    """Профиль намерения NPC с опциональной целью перехода"""
    intent: Intent
    score: float
    reason: str = ""
    
    # НОВОЕ: цель перехода (только для TRANSIT)
    target_location_id: Optional[str] = None
    target_node_id: Optional[str] = None     # конкретный узел в целевой локации
    transit_reason: Optional[str] = None       # "schedule" / "need" / "social" / "flee"
```

---

#### Шаг 3: DecisionHub формирует TRANSIT intent

**Файл:** `backend/app/services/npc/decision_hub.py`

```python
class DecisionHub:
    
    def compute(self, tick_input: NpcTickInput) -> DecisionResult:
        scores = self._compute_base_scores(tick_input)
        
        # ... применение modifiers (ТЗ-01) ...
        
        # НОВОЕ: проверить, нужно ли менять локацию
        transit_profile = self._evaluate_transit_need(tick_input)
        if transit_profile and transit_profile.score > self.TRANSIT_THRESHOLD:
            scores[Intent.TRANSIT] = transit_profile.score
            self._pending_transit = transit_profile  # сохранить для результата
        
        selected_intent = max(scores, key=scores.get)
        
        result = DecisionResult(
            selected_intent=selected_intent,
            scores=scores,
        )
        
        # Если выбран TRANSIT — прикрепить профиль
        if selected_intent == Intent.TRANSIT and self._pending_transit:
            result.transit_profile = self._pending_transit
        
        return result

    def _evaluate_transit_need(self, tick_input: NpcTickInput) -> Optional[IntentProfile]:
        """Определить, нужно ли NPC переходить в другую локацию"""
        
        transit_candidates = []
        
        # 1. SCHEDULE-DRIVEN: расписание требует другую локацию
        if tick_input.schedule and tick_input.current_activity:
            required_location = self._get_activity_location(
                tick_input.schedule, tick_input.current_activity
            )
            if required_location and required_location != tick_input.current_location:
                transit_candidates.append(IntentProfile(
                    intent=Intent.TRANSIT,
                    score=0.7,  # высокий приоритет — рутина
                    target_location_id=required_location,
                    transit_reason="schedule",
                ))
        
        # 2. NEED-DRIVEN: экономическая потребность требует другую локацию
        if tick_input.economic_drives:
            for drive in tick_input.economic_drives:
                if drive.strength > 0.6:
                    target = self.semantic_index.find_location_for_need(drive.drive_type)
                    if target and target != tick_input.current_location:
                        transit_candidates.append(IntentProfile(
                            intent=Intent.TRANSIT,
                            score=0.3 + drive.strength * 0.4,  # 0.54..0.7
                            target_location_id=target,
                            transit_reason="need",
                        ))
        
        # 3. FLEE-DRIVEN: бегство в безопасную локацию
        if tick_input.score_modifiers and tick_input.score_modifiers.get("flee", 0) > 0.5:
            safe_location = self.semantic_index.find_location("shelter")
            if safe_location and safe_location != tick_input.current_location:
                transit_candidates.append(IntentProfile(
                    intent=Intent.TRANSIT,
                    score=0.8,  # высокий — спасение жизни
                    target_location_id=safe_location,
                    transit_reason="flee",
                ))
        
        # Вернуть лучший кандидат
        if transit_candidates:
            return max(transit_candidates, key=lambda p: p.score)
        return None

    def _get_activity_location(self, schedule: dict, activity: str) -> Optional[str]:
        """Найти локацию для данной активности из activity_map"""
        activity_map = schedule.get("activity_map", {})
        activity_data = activity_map.get(activity, {})
        return activity_data.get("location")
```

---

#### Шаг 4: Обработать TRANSIT в npc_tick_pipeline

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py`

```python
# ПОСЛЕ DecisionHub.compute():

decision = self.decision_hub.compute(tick_input)

if decision.selected_intent == Intent.TRANSIT and decision.transit_profile:
    # Выполнить переход через MovementEngine
    transit = decision.transit_profile
    
    movement_result = await self.movement_engine.move_entity(
        npc_id=npc_state.npc_id,
        target_node_id=transit.target_node_id or "entry",  # default entry point
        boundary_map=ctx.boundary_map,
        allow_cross_location=True,
    )
    
    if movement_result.success and movement_result.location_changed:
        # Успешный переход
        npc_state.location_id = movement_result.new_location
        npc_state.position = movement_result.new_position
        
        # Сгенерировать нарративное событие
        await self.event_bus.publish(SceneEvent(
            event_type="NPC_TRANSIT",
            npc_id=npc_state.npc_id,
            data={
                "from": movement_result.old_location,
                "to": movement_result.new_location,
                "reason": transit.transit_reason,
                "activity": tick_input.current_activity,
            },
        ))
    else:
        # Переход не удался — fallback на IDLE
        npc_state.current_intent = Intent.IDLE
```

---

#### Шаг 5: Добавить activity_map для maid и thief

**Файл:** `config/npc/archetypes/maid.json`

```json
{
  "archetype": "maid",
  "routine": {
    "schedule": {
      "06:00-10:00": "cleaning",
      "10:00-14:00": "serving_tables",
      "14:00-16:00": "resting",
      "16:00-22:00": "serving_tables",
      "22:00-06:00": "sleeping"
    },
    "activity_map": {
      "cleaning": {
        "location": "tavern_silver_wolf",
        "position": "back_room",
        "display": "убирает в подсобке"
      },
      "serving_tables": {
        "location": "tavern_silver_wolf",
        "position": "bar_area",
        "display": "обслуживает за стойкой"
      },
      "resting": {
        "location": "tavern_silver_wolf",
        "position": "staff_room",
        "display": "отдыхает в комнате прислуги"
      },
      "sleeping": {
        "location": "tavern_silver_wolf",
        "position": "staff_quarters",
        "display": "спит в спальне прислуги"
      }
    }
  }
}
```

**Файл:** `config/npc/archetypes/thief.json`

```json
{
  "archetype": "thief",
  "routine": {
    "schedule": {
      "06:00-12:00": "sleeping",
      "12:00-14:00": "planning",
      "14:00-20:00": "active",
      "20:00-02:00": "prowling",
      "02:00-06:00": "returning"
    },
    "activity_map": {
      "sleeping": {
        "location": "thief_hideout",
        "position": "bed",
        "display": "спит в убежище"
      },
      "planning": {
        "location": "thief_hideout",
        "position": "table",
        "display": "планирует дело"
      },
      "active": {
        "location": "market_square",
        "position": "crowd",
        "display": "ошивается на рынке"
      },
      "prowling": {
        "location": "city_streets",
        "position": "alley",
        "display": "бродит по переулкам"
      },
      "returning": {
        "location": "thief_hideout",
        "position": "entrance",
        "display": "возвращается в убежище"
      }
    }
  }
}
```

**Ключевое:** thief — первый NPC, который **реально переходит между локациями** (hideout → market → streets → hideout). Это тест-кейс для всего кросс-локационного механизма.

---

#### Шаг 6: Генерировать SpatialEvent.CROSS_LOCATION_TRANSITION

**Файл:** `backend/app/services/spatial/spatial_events.py` — добавить:

```python
@dataclass
class CrossLocationTransitionEvent:
    """Событие: NPC перешёл в другую локацию"""
    event_type: str = "CROSS_LOCATION_TRANSITION"
    npc_id: str = ""
    from_location: str = ""
    to_location: str = ""
    from_node: str = ""
    to_node: str = ""
    reason: str = ""          # schedule / need / flee / social
    activity: str = ""        # что NPC будет делать
    travel_time: int = 1      # сколько тиков занял переход
```

**Подписчики события:**

```python
# 1. SceneEventEmitter — DM описывает переход
class TransitNarrativeSubscriber:
    async def on_cross_location_transition(self, event):
        descriptions = {
            "schedule": f"{event.npc_id} отправился по делам в {event.to_location}",
            "need": f"{event.npc_id} пошёл в {event.to_location} за припасами",
            "flee": f"{event.npc_id} в спешке бежал в {event.to_location}",
            "social": f"{event.npc_id} вышел, направляясь в {event.to_location}",
        }
        await self.scene_emitter.emit(descriptions.get(event.reason, "..."))

# 2. SocialEngine — обновить social proximity
class TransitSocialSubscriber:
    async def on_cross_location_transition(self, event):
        # NPC покинул локацию — обновить distances
        self.social_engine.remove_from_location(event.npc_id, event.from_location)
        self.social_engine.add_to_location(event.npc_id, event.to_location)

# 3. SceneStateManager — обновить UI
class TransitUISubscriber:
    async def on_cross_location_transition(self, event):
        # Если NPC виден игроку — показать анимацию ухода
        if event.from_location == self.player_location:
            self.ui.show_npc_leaving(event.npc_id, event.to_location)
```

---

#### Шаг 7: Добавить i18n для новых активностей

**Файл:** `frontend/i18n.py` (или где хранятся переводы)

```python
# НОВЫЕ ключи:
"act:cleaning": "убирает",
"act:serving_tables": "обслуживает",
"act:resting": "отдыхает",
"act:planning": "планирует",
"act:active": "ошивается",
"act:prowling": "бродит",
"act:returning": "возвращается",
"act:observing": "наблюдает",
"act:counting_money": "считает деньги",
"act:forging": "куёт",
```

---

### Как проверить

```python
# Тест: вор переходит между локациями по расписанию
async def test_thief_cross_location_transit():
    # 12:00 — вор просыпается, должен идти планировать в hideout
    npc = create_test_npc(
        archetype="thief",
        location="thief_hideout",
        current_activity="sleeping",
    )
    
    # Продвинуть время до 14:00 (active → market)
    temporal = TemporalContext(game_hour=14, ...)
    
    decision = decision_hub.compute(build_tick_input(npc, temporal))
    
    assert decision.selected_intent == Intent.TRANSIT
    assert decision.transit_profile.target_location_id == "market_square"
    assert decision.transit_profile.transit_reason == "schedule"
    
    # Выполнить переход
    result = await movement_engine.move_entity(
        npc_id=npc.npc_id,
        target_node_id="crowd",
        boundary_map=ctx.boundary_map,
        allow_cross_location=True,
    )
    
    assert result.success == True
    assert result.location_changed == True
    assert result.new_location == "market_square"

# Тест: голодный NPC идёт в таверну
async def test_hungry_npc_transit():
    npc = create_test_npc(
        location="barracks",
        needs=Needs(food=0.8),
    )
    
    decision = decision_hub.compute(build_tick_input(npc))
    
    assert decision.selected_intent == Intent.TRANSIT
    assert decision.transit_profile.target_location_id == "tavern_silver_wolf"
    assert decision.transit_profile.transit_reason == "need"
```

---

### Порядок исправления

| # | Шаг | Время |
|---|-----|-------|
| 1 | INTENT.TRANSIT + IntentProfile | 20 мин |
| 2 | _evaluate_transit_need() в DecisionHub | 45 мин |
| 3 | Обработка TRANSIT в npc_tick_pipeline | 30 мин |
| 4 | activity_map для maid и thief | 30 мин |
| 5 | CrossLocationTransitionEvent + подписчики | 45 мин |
| 6 | i18n ключи | 10 мин |
| 7 | Тесты | 30 мин |

**Итого:** ~3.5 часа

**Предпосылки:** ТЗ-02 (SpatialRegistry) + ТЗ-06 (boundary_map) + ТЗ-01 (DecisionHub API)

---

Давать следующее? Это **ТЗ-04: Belief Layer — PatternDetector** (убеждения и распознавание паттернов).