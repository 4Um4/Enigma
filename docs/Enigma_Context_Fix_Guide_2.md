# Архитектурный рефакторинг: Гибридный подход (Контекст + Salience Engine)

Данное руководство описывает внедрение гибридного решения для устранения "зацикливания" LLM. Мы объединяем быстрые прагматичные фиксы (очистка мусора) с фундаментальной архитектурой (Salience Engine и Режимы Сцены).

Главный принцип: **LLM получает не описание того, что она должна сказать, а физические ограничения и фокус внимания, зависящий от текущего режима игры.**

---

## Шаг 1: Трансформация Activity (От текста к ограничениям)

**Суть:** Мы не удаляем `activity` полностью (чтобы не потерять "инерцию мира"), но и не передаем ее как текст ("протирает стаканы") или жесткий тег. Мы переводим активность в **физические ограничения и контекст роли**.

**Файл:** `backend/app/models/npc_state.py`

```python
class NPCState:
    def __init__(self, role_context="BARTENDER"):
        self.intent = Intent.IDLE
        self.role_context = role_context
        self.hands_occupied = False  # Флаг физического ограничения
        
    def update_state_from_intent(self):
        """
        Состояние рук и занятости вычисляется из намерения и стресса.
        """
        if self.intent in [Intent.COMBAT, Intent.FLEE] or self.stress > 30.0:
            self.hands_occupied = False # Бросает все дела при опасности
        elif self.intent == Intent.IDLE:
            self.hands_occupied = True  # В спокойном состоянии занят рутиной
```
*В промпт уходит:* `[ROLE: BARTENDER] [HANDS_OCCUPIED: TRUE]`. 
*Результат:* LLM понимает, что NPC занят делом бармена, но сама решает, протирает ли он стакан, наливает эль или опирается на стойку. Зацикливание исчезает, инерция мира остается.

---

## Шаг 2: Внедрение режимов сцены (Scene Modes)

**Суть:** Жесткий лимит `top_n=3` ломает игру, когда игрок хочет осмотреться. Контекст должен динамически расширяться или сужаться в зависимости от того, что делает игрок.

**Новый файл:** `backend/app/models/scene_mode.py`

```python
from enum import Enum

class SceneMode(Enum):
    EXPLORATION = "EXPLORATION" # Игрок осматривается (полный контекст)
    INTERACTION = "INTERACTION" # Диалог/взаимодействие (отфильтрованный контекст)
    COMBAT = "COMBAT"           # Бой/Угроза (агрессивный фильтр, только угрозы/выходы)

def determine_scene_mode(player_intent, global_stress) -> SceneMode:
    if global_stress > 50.0 or player_intent == "ATTACK":
        return SceneMode.COMBAT
    elif player_intent in ["EXAMINE", "LOOK_AROUND"]:
        return SceneMode.EXPLORATION
    return SceneMode.INTERACTION
```

---

## Шаг 3: Базовый Salience Engine (Слой внимания)

**Суть:** Внедряем слой оценки важности объектов. Он универсален (может считать фокус как для игрока, так и для NPC) и зависит от `SceneMode`.

**Файл:** `backend/app/services/scene/salience_engine.py`

```python
from backend.app.models.scene_mode import SceneMode

class SalienceEngine:
    def calculate_salience(self, obj, observer_state) -> float:
        # Базовая эвристика без оверинжиниринга
        score = 1.0
        
        # Близость к наблюдателю
        if obj.distance_to(observer_state.position) < 2.0:
            score += 1.0
            
        # Является ли объект угрозой или выходом (важно при стрессе)
        if getattr(obj, 'is_threat', False) or getattr(obj, 'is_exit', False):
            score += 2.0 * (observer_state.stress / 100.0)
            
        return score

    def get_focused_objects(self, scene_state, observer_state, scene_mode: SceneMode) -> list:
        scored_objects = []
        
        for obj in scene_state.objects.values():
            # 1. Быстрый фикс: отсекаем инвентарь и надетые вещи (микромусор)
            if getattr(obj, 'state', '') in ['equipped', 'in_inventory']:
                continue
                
            score = self.calculate_salience(obj, observer_state)
            scored_objects.append((score, obj))
            
        scored_objects.sort(key=lambda x: x[0], reverse=True)
        
        # 2. Динамический лимит на основе SceneMode
        if scene_mode == SceneMode.EXPLORATION:
            top_n = 10  # Даем максимум деталей для осмотра
        elif scene_mode == SceneMode.COMBAT:
            top_n = 2   # Туннельное зрение: только самое важное
        else:
            top_n = 4   # Стандартное взаимодействие
            
        return [obj for score, obj in scored_objects[:top_n]]
```

---

## Шаг 4: Интеграция и обновление промпта DM

**Суть:** DM Scene Builder теперь использует `SceneMode` и `SalienceEngine`, а промпт объясняет LLM текущие ограничения.

**Файл:** `backend/app/services/action/dm_scene_builder.py`

```python
def build_scene_context(self, scene_state, player_state, player_intent):
    scene_mode = determine_scene_mode(player_intent, scene_state.global_stress)
    
    # Salience считается относительно игрока (DM описывает то, что видит игрок)
    focused_objects = self.salience_engine.get_focused_objects(
        scene_state, player_state, scene_mode
    )
    
    focus_block = ", ".join([obj.name for obj in focused_objects])
    return f"[SCENE_MODE: {scene_mode.value}]\n[VISIBLE_FOCUS: {focus_block}]"
```

**Файл:** `backend/app/agents/dm_agent.py` (Системный промпт)

**Новый промпт:**
> "Ты — DM. Твоя задача — описывать мир.
> 
> **Контекст сцены:**
> Режим сцены: `[SCENE_MODE]`. 
> - Если EXPLORATION: опиши окружение подробно.
> - Если INTERACTION: сфокусируйся на диалоге и собеседнике.
> - Если COMBAT: пиши коротко, динамично, описывай только угрозы.
> 
> **Внимание:** В блоке `[VISIBLE_FOCUS]` перечислены объекты, которые сейчас в фокусе внимания. Строй сцену вокруг них.
> 
> **Состояние NPC:** Учитывай теги `[ROLE]` и `[HANDS_OCCUPIED]`. Если руки заняты, NPC не может совершать сложные жесты, но ты сам решаешь, чем именно он занят в рамках своей роли."

---

## Итог гибридного подхода
1. **Мгновенный эффект:** Мусор (инвентарь) отфильтрован, текстовая `activity` больше не сводит LLM с ума.
2. **Долгосрочный фундамент:** Внедрен `SalienceEngine`. Центр принятия решений о том, "что важно", навсегда перенесен из LLM в Python-движок.
3. **Гибкость:** Благодаря `SceneMode`, система не ломает механику осмотра (`EXAMINE`), динамически расширяя или сужая "горлышко" контекста.