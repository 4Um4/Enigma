# Архитектурный рефакторинг: Salience Engine и динамический контекст

Данное руководство описывает внедрение **Salience Engine (Движка Важности)** — промежуточного слоя между физическим состоянием сцены (`SceneState`) и LLM. 

Главный принцип новой архитектуры: **LLM не принимает решения о том, что важно. LLM только "видит" то, что Python-движок подсветил как важное в данный момент времени.**

---

## Фаза 1: Рефакторинг Activity (Производная, а не состояние)

**Суть:** Избавляемся от ручного сброса `activity` через костыльные `if`. Активность больше не хранится как независимая переменная, она вычисляется "на лету" на основе `Intent` (намерения).

**Файл:** `backend/app/models/npc_state.py` (или аналогичный класс состояния)

```python
from enum import Enum

class ActivityTag(Enum):
    CLEANING = "CLEANING"
    SERVING = "SERVING"
    FIGHTING = "FIGHTING"
    FLEEING = "FLEEING"
    IDLE = "IDLE"

class NPCState:
    def __init__(self, default_role_activity=ActivityTag.CLEANING):
        self.intent = Intent.IDLE
        self.default_role_activity = default_role_activity
        # self.activity = ...  <-- УДАЛИТЬ ЭТО ПОЛЕ

    @property
    def current_activity_tag(self) -> str:
        """
        Activity вычисляется динамически. Нет риска рассинхрона состояний.
        """
        if self.intent == Intent.COMBAT:
            return ActivityTag.FIGHTING.value
        elif self.intent == Intent.FLEE:
            return ActivityTag.FLEEING.value
        elif self.intent == Intent.IDLE:
            return self.default_role_activity.value
            
        return ActivityTag.IDLE.value
```
*В промпт теперь уходит только тег (например, `[ACTIVITY: CLEANING]`), а не готовая фраза "протирает стаканы". LLM сама решает, как это литературно обыграть.*

---

## Фаза 2: Проектирование Salience Engine (Слой внимания)

**Суть:** Создаем движок, который оценивает каждый объект в сцене и выдает ему "вес важности" (Salience Score). В LLM пойдут только объекты с наивысшим скором.

**Новый файл:** `backend/app/services/scene/salience_engine.py`

```python
class SalienceEngine:
    def __init__(self):
        # Настроечные веса для тюнинга фокуса
        self.weights = {
            "proximity": 1.0,
            "interaction": 2.0,
            "intent_match": 1.5,
            "stress_multiplier": 1.5
        }

    def calculate_salience(self, obj, npc_state, scene_state) -> float:
        score = 0.0
        
        # 1. Близость (Proximity)
        if obj.distance_to(npc_state.position) < 2.0:
            score += self.weights["proximity"]
            
        # 2. Прямое взаимодействие (Interaction)
        if obj.id == npc_state.target_object_id:
            score += self.weights["interaction"]
            
        # 3. Релевантность намерению (Intent Match)
        if npc_state.intent == Intent.COMBAT and getattr(obj, 'is_weapon', False):
            score += self.weights["intent_match"]
        elif npc_state.intent == Intent.FLEE and getattr(obj, 'is_exit', False):
            score += self.weights["intent_match"]
            
        # 4. Туннельное зрение при стрессе (Stress Tunneling)
        if npc_state.stress > 50.0:
            # При панике мозг игнорирует стаканы и видит только угрозу/выход
            if not (getattr(obj, 'is_threat', False) or getattr(obj, 'is_exit', False)):
                score *= 0.1  # Пенализируем фоновый мусор
            else:
                score *= self.weights["stress_multiplier"]
                
        return score

    def get_focused_objects(self, scene_state, npc_state, top_n=3) -> list:
        scored_objects = []
        
        for obj in scene_state.objects.values():
            # Перцепционный фильтр: игнорируем надетые вещи и инвентарь
            if getattr(obj, 'state', '') in ['equipped', 'in_inventory']:
                continue
                
            score = self.calculate_salience(obj, npc_state, scene_state)
            if score > 0.2: # Отсекаем абсолютно нерелевантный фон
                scored_objects.append((score, obj))
                
        # Сортируем по убыванию важности
        scored_objects.sort(key=lambda x: x[0], reverse=True)
        
        # Возвращаем только Top-N самых важных объектов
        return [obj for score, obj in scored_objects[:top_n]]
```

---

## Фаза 3: Интеграция в DM Scene Builder

**Суть:** Заменяем слепую выгрузку всех объектов на вызов `SalienceEngine`.

**Файл:** `backend/app/services/action/dm_scene_builder.py`

```python
from backend.app.services.scene.salience_engine import SalienceEngine

class DMSceneBuilder:
    def __init__(self):
        self.salience_engine = SalienceEngine()

    def build_scene_context(self, scene_state, active_npc_state):
        # Получаем только те объекты, которые ВАЖНЫ прямо сейчас
        focused_objects = self.salience_engine.get_focused_objects(
            scene_state=scene_state, 
            npc_state=active_npc_state, 
            top_n=3 # Жесткий лимит для экономии контекста и фокуса LLM
        )
        
        # Формируем блок для промпта
        focus_block = " ".join([f"[{obj.name}]" for obj in focused_objects])
        return f"[FOCUS_OBJECTS: {focus_block}]"
```

---

## Фаза 4: Обновление системного промпта (Возврат контроля)

**Суть:** Мы забираем у LLM право решать, что важно, и приказываем ей строить нарратив строго вокруг того, что подсветил `SalienceEngine`.

**Файл:** `backend/app/agents/dm_agent.py` (Системный промпт)

**Новый промпт:**
> "Ты — DM. Твоя задача — описать текущую сцену и действия NPC.
> В блоке `[FOCUS_OBJECTS]` Python-движок передал тебе объекты, на которых **сейчас сфокусировано внимание** (определено физикой, стрессом и намерениями). 
> **Твоя директива:** Строй повествование строго вокруг этих объектов. Не придумывай взаимодействие с другими предметами.
> Текущее состояние NPC передано тегом `[ACTIVITY]`. Отыграй это состояние литературно, опираясь на фокусные объекты."

---

## Итог архитектуры
1. **Нет рассинхрона:** `Activity` всегда соответствует `Intent`.
2. **Нет мусора:** Инвентарь отсекается на уровне перцепции.
3. **Абсолютный контроль:** Python-движок через математику (веса) решает, что видит NPC. LLM работает как "рендерер" (видеокарта), просто отрисовывая текстом то, что ей передал процессор (`SalienceEngine`).