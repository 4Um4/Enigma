## ТЗ-01: DecisionHub — подключение через API

**Статус:** ⚠️ РАБОТАЕТ | **Критичность:** MEDIUM (архитектурный долг) | **Волна:** 3 (зависит от ТЗ-10)

---

### Суть проблемы одной строкой

DecisionHub принимает решения, но видит **только** сырые данные NPCState. Всё, что вычисляют другие подсистемы — интерпретации, экономические потребности, травмы, воспоминания — **невидимо** для него. NPC решает вслепую.

---

### Что видит DecisionHub сейчас vs что должен

```
ВХОД DecisionHub СЕЙЧАС:              ВХОД DecisionHub ДОЛЖЕН:
┌──────────────────────┐              ┌──────────────────────┐
│ npc_state.drives      │              │ npc_state.drives      │
│ npc_state.emotion     │              │ npc_state.emotion     │
│ npc_state.position    │              │ npc_state.position    │
│ current_event         │              │ current_event         │
└──────────────────────┘              │ score_modifiers ←── InterpretationEngine
                                      │ economic_drives  ←── NeedEngine
  НЕТ:                                │ affective_imprints←── affect.py
  • InterpretationEngine              │ recent_narrative  ←── narrative_cache
  • NeedEngine                        │ avatar_emotion    ←── PlayerAvatar
  • AffectiveImprint                  └──────────────────────┘
  • narrative_cache
  • Avatar emotion
```

---

### Пошаговый план исправления

#### Шаг 1: Расширить NpcTickInput

**Файл:** `backend/app/models/npc_state.py` (или `game_loop/tick_context.py` — найти класс NpcTickInput / TickInput)

```python
from typing import Optional, Dict, List
from app.models.affect import AffectiveImprint
from app.services.economy.need_engine import NeedDrive
from app.domain.events import EventMemory

@dataclass
class NpcTickInput:
    """Расширенный контекст для DecisionHub"""
    
    # Существующие поля:
    npc_id: str
    drives: Dict[str, float]
    emotion: str
    position: Tuple[int, int]
    current_event: Optional[dict] = None
    social_modifiers: Optional[Dict[str, float]] = None
    
    # НОВЫЕ ПОЛЯ (все Optional — обратная совместимость):
    
    score_modifiers: Optional[Dict[str, float]] = None
    """Модификаторы скоров от InterpretationEngine.
    Пример: {"flee": 0.15, "attack": -0.2}
    """
    
    economic_drives: Optional[List[NeedDrive]] = None
    """Экономические потребности от NeedEngine.
    Пример: [NeedDrive(drive_type=FOOD, strength=0.7)]
    """
    
    affective_imprints: Optional[List[AffectiveImprint]] = None
    """Аффективные отпечатки (травмы) из affect.py.
    Пример: [AffectiveImprint(trigger="combat", fear=0.8)]
    """
    
    recent_narrative: Optional[List[EventMemory]] = None
    """Недавние воспоминания из narrative_cache.
    Пример: [EventMemory(subject="guard_Borko", action="attacked")]
    """
    
    avatar_emotional_state: Optional[Dict[str, float]] = None
    """Эмоциональное состояние аватара игрока.
    Пример: {"stress": 0.6, "fear": 0.4}
    """
```

---

#### Шаг 2: Подключить InterpretationEngine.score_modifiers

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py`

```python
# ПОСЛЕ вызова interpretation_engine.compute():

interpretation_result = self.interpretation_engine.compute(
    npc_state=npc_state,
    event=current_event,
)

# НОВОЕ: передать score_modifiers в NpcTickInput
tick_input = NpcTickInput(
    npc_id=npc_state.npc_id,
    drives=npc_state.drives,
    emotion=npc_state.emotion,
    position=npc_state.position,
    current_event=current_event,
    social_modifiers=interpretation_result.social_modifiers,
    score_modifiers=interpretation_result.score_modifiers,  # ← НОВОЕ
)
```

**Файл:** `backend/app/services/npc/decision_hub.py` — добавить merge:

```python
class DecisionHub:
    
    def compute(self, tick_input: NpcTickInput) -> DecisionResult:
        # Вычислить базовые скоры для каждого intent
        scores = self._compute_base_scores(tick_input)
        
        # НОВОЕ: применить score_modifiers от InterpretationEngine
        if tick_input.score_modifiers:
            for intent_name, modifier in tick_input.score_modifiers.items():
                if intent_name in scores:
                    scores[intent_name] += modifier
                    # Пример: interpretation дала "flee": +0.15
                    # NPC, который интерпретирует угрозу, склоннее бежать
        
        # НОВОЕ: применить social_modifiers (существующая логика, но гарантировать)
        if tick_input.social_modifiers:
            for intent_name, modifier in tick_input.social_modifiers.items():
                if intent_name in scores:
                    scores[intent_name] += modifier
        
        # Выбрать intent с максимальным скором
        selected_intent = max(scores, key=scores.get)
        
        return DecisionResult(
            selected_intent=selected_intent,
            scores=scores,
            confidence=scores[selected_intent],
        )
```

---

#### Шаг 3: Маршрутизировать NeedDrive в DecisionHub

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py`

```python
# ПОСЛЕ compute_economy():

economy_result = self.economy_service.tick(npc_state)

# НОВОЕ: преобразовать NeedDrive в модификаторы намерий
if economy_result.need_drives:
    economic_intent_modifiers = self._need_drives_to_modifiers(
        economy_result.need_drives
    )
    tick_input.economic_drives = economy_result.need_drives
    # Также добавить модификаторы в score_modifiers
    if tick_input.score_modifiers is None:
        tick_input.score_modifiers = {}
    tick_input.score_modifiers.update(economic_intent_modifiers)

def _need_drives_to_modifiers(self, drives: List[NeedDrive]) -> Dict[str, float]:
    """Преобразовать экономические потребности в модификаторы намерий"""
    modifiers = {}
    
    # Маппинг: NeedType → Intent + модификатор
    NEED_TO_INTENT = {
        "FOOD":       ("SEEK_FOOD",    0.3),
        "SHELTER":    ("SEEK_SHELTER",  0.25),
        "INCOME":     ("TRADE",         0.2),
        "SOCIAL":     ("SOCIALIZE",     0.15),
        "SECURITY":   ("GUARD",         0.2),
        "CLEANLINESS":("SEEK_SERVICE",  0.15),
        "TOOLS":      ("CRAFT",         0.2),
        "INFORMATION":("GOSSIP",        0.1),
    }
    
    for drive in drives:
        mapping = NEED_TO_INTENT.get(drive.drive_type)
        if mapping:
            intent_name, base_weight = mapping
            # Модификатор пропорционален силе потребности
            modifiers[intent_name] = base_weight * drive.strength
    
    return modifiers
```

---

#### Шаг 4: Подключить AffectiveImprint к DecisionHub

**Файл:** `backend/app/services/npc/decision_hub.py` — добавить метод:

```python
def _apply_affective_bias(
    self,
    scores: Dict[str, float],
    imprints: List[AffectiveImprint],
    current_context: dict,
) -> Dict[str, float]:
    """
    Аффективные отпечатки смещают скоры намерий.
    NPC с боевой травмой более склонен к бегству при виде оружия.
    """
    for imprint in imprints:
        # Проверить, резонирует ли импринт с текущим контекстом
        resonance = self._check_imprint_resonance(imprint, current_context)
        if resonance <= 0:
            continue
        
        # Страх → усиление defensive/flee intent'ов
        if imprint.fear_signature > 0.3:
            fear_boost = imprint.fear_signature * resonance * 0.3
            scores["FLEE"] = scores.get("FLEE", 0) + fear_boost
            scores["GUARD"] = scores.get("GUARD", 0) + fear_boost * 0.5
            scores["ATTACK"] = scores.get("ATTACK", 0) - fear_boost * 0.3
        
        # Боль → усиление defensive intent'ов
        if imprint.pain_signature > 0.3:
            pain_boost = imprint.pain_signature * resonance * 0.2
            scores["FLEE"] = scores.get("FLEE", 0) + pain_boost
            scores["SEEK_HELP"] = scores.get("SEEK_HELP", 0) + pain_boost * 0.5
        
        # Унижение → усиление avoid/submit intent'ов
        if imprint.humiliation_signature > 0.3:
            hum_boost = imprint.humiliation_signature * resonance * 0.2
            scores["AVOID"] = scores.get("AVOID", 0) + hum_boost
            scores["SUBMIT"] = scores.get("SUBMIT", 0) + hum_boost * 0.5
            scores["RETALIATE"] = scores.get("RETALIATE", 0) + hum_boost * 0.3
    
    return scores

def _check_imprint_resonance(
    self,
    imprint: AffectiveImprint,
    current_context: dict,
) -> float:
    """Насколько текущий контекст резонирует с импринтом (0..1)"""
    if imprint.trigger in current_context.get("tags", []):
        return imprint.trigger_strength
    if imprint.target in current_context.get("actors", []):
        return imprint.trigger_strength * 0.7
    return 0.0
```

**Вызов в compute():**

```python
def compute(self, tick_input: NpcTickInput) -> DecisionResult:
    scores = self._compute_base_scores(tick_input)
    
    # 1. Score modifiers от InterpretationEngine
    if tick_input.score_modifiers:
        for intent, mod in tick_input.score_modifiers.items():
            if intent in scores:
                scores[intent] += mod
    
    # 2. Аффективные импринты (НОВОЕ)
    if tick_input.affective_imprints:
        scores = self._apply_affective_bias(
            scores, tick_input.affective_imprints, tick_input.current_event or {}
        )
    
    # 3. Аватарные эмоции (НОВОЕ)
    if tick_input.avatar_emotional_state:
        scores = self._apply_avatar_perception(
            scores, tick_input.avatar_emotional_state
        )
    
    selected_intent = max(scores, key=scores.get)
    return DecisionResult(selected_intent=selected_intent, scores=scores, ...)
```

---

#### Шаг 5: Подключить narrative_cache

**Файл:** `backend/app/services/npc/decision_hub.py`

```python
def _apply_narrative_bias(
    self,
    scores: Dict[str, float],
    narrative: List[EventMemory],
) -> Dict[str, float]:
    """Недавние воспоминания влияют на решения"""
    
    for memory in narrative[-5:]:  # последние 5 событий
        # Если недавно атакован тем же субъектом — усилить защиту
        if memory.action in ("attacked", "threatened", "insulted"):
            scores["GUARD"] = scores.get("GUARD", 0) + 0.15
            scores["FLEE"] = scores.get("FLEE", 0) + 0.1
            scores["TRUST"] = scores.get("TRUST", 0) - 0.2
        
        # Если недавно помогли — усилить кооперацию
        if memory.action in ("helped", "healed", "traded_fairly"):
            scores["COOPERATE"] = scores.get("COOPERATE", 0) + 0.15
            scores["TRUST"] = scores.get("TRUST", 0) + 0.1
        
        # Если недавно обманули — усилить подозрительность
        if memory.action in ("deceived", "stole", "betrayed"):
            scores["SUSPECT"] = scores.get("SUSPECT", 0) + 0.2
            scores["AVOID"] = scores.get("AVOID", 0) + 0.15
    
    return scores
```

---

#### Шаг 6: Подключить восприятие эмоций аватара

**Файл:** `backend/app/services/npc/decision_hub.py`

```python
def _apply_avatar_perception(
    self,
    scores: Dict[str, float],
    avatar_state: Dict[str, float],
) -> Dict[str, float]:
    """NPC видит эмоции аватара и адаптирует поведение"""
    
    stress = avatar_state.get("stress", 0)
    fear = avatar_state.get("fear", 0)
    willpower = avatar_state.get("willpower", 1)
    
    # Жертва напугана → агрессоры смелеют
    if fear > 0.5:
        scores["INTIMIDATE"] = scores.get("INTIMIDATE", 0) + fear * 0.3
        scores["ATTACK"] = scores.get("ATTACK", 0) + fear * 0.15
    
    # Жертва в стрессе → эксплуататоры активнее
    if stress > 0.6:
        scores["DEMAND"] = scores.get("DEMAND", 0) + stress * 0.2
        scores["MANIPULATE"] = scores.get("MANIPULATE", 0) + stress * 0.15
    
    # Жертва слаба волей → давление усиливается
    if willpower < 0.4:
        scores["PRESSURE"] = scores.get("PRESSURE", 0) + (1 - willpower) * 0.2
    
    # Жертва спокойна и сильна → уважение
    if fear < 0.2 and willpower > 0.7:
        scores["RESPECT"] = scores.get("RESPECT", 0) + 0.15
        scores["COOPERATE"] = scores.get("COOPERATE", 0) + 0.1
    
    return scores
```

---

### Собрать всё в npc_tick_pipeline

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py`

```python
# Полный конвейер подготовки входа для DecisionHub:

def _build_tick_input(self, npc_state, ctx) -> NpcTickInput:
    """Собрать полный контекст для DecisionHub"""
    
    # 1. Интерпретация
    interpretation = self.interpretation_engine.compute(npc_state, ctx.event)
    
    # 2. Экономика
    economy = self.economy_service.tick(npc_state)
    econ_modifiers = self._need_drives_to_modifiers(economy.need_drives)
    
    # 3. Объединить модификаторы
    combined_modifiers = {}
    if interpretation.score_modifiers:
        combined_modifiers.update(interpretation.score_modifiers)
    combined_modifiers.update(econ_modifiers)
    
    # 4. Собрать NpcTickInput
    return NpcTickInput(
        npc_id=npc_state.npc_id,
        drives=npc_state.drives,
        emotion=npc_state.emotion,
        position=npc_state.position,
        current_event=ctx.event,
        social_modifiers=interpretation.social_modifiers,
        score_modifiers=combined_modifiers,
        economic_drives=economy.need_drives,
        affective_imprints=npc_state.affective_imprints if npc_state.affective_imprints else None,
        recent_narrative=npc_state.narrative_cache[-5:] if npc_state.narrative_cache else None,
        avatar_emotional_state=ctx.avatar_emotional_state,
    )
```

---

### Как проверить

```python
# Тест: DecisionHub учитывает все контексты
def test_decision_hub_full_context():
    # NPC с боевой травмой, голодный, видит испуганного игрока
    npc = create_test_npc()
    npc.affective_imprints = [
        AffectiveImprint(trigger="combat", fear_signature=0.8, trigger_strength=0.9)
    ]
    npc.narrative_cache = [
        EventMemory(subject="player", action="attacked")
    ]
    
    tick_input = NpcTickInput(
        npc_id=npc.npc_id,
        drives=npc.drives,
        emotion=npc.emotion,
        position=npc.position,
        score_modifiers={"flee": 0.15},
        economic_drives=[NeedDrive(drive_type="FOOD", strength=0.7)],
        affective_imprints=npc.affective_imprints,
        recent_narrative=npc.narrative_cache[-5:],
        avatar_emotional_state={"stress": 0.6, "fear": 0.5, "willpower": 0.3},
    )
    
    result = decision_hub.compute(tick_input)
    
    # NPC с боевой травмой + голод + испуганный игрок
    # → должен склоняться к FLEE/SEEK_FOOD, а не ATTACK
    assert result.scores.get("FLEE", 0) > result.scores.get("ATTACK", 0)
    assert result.scores.get("SEEK_FOOD", 0) > 0
```

---

### Порядок исправления

| # | Шаг | Время |
|---|-----|-------|
| 1 | Расширить NpcTickInput | 15 мин |
| 2 | score_modifiers merge в DecisionHub | 20 мин |
| 3 | NeedDrive → intent modifiers | 30 мин |
| 4 | _apply_affective_bias() | 45 мин |
| 5 | _apply_narrative_bias() | 30 мин |
| 6 | _apply_avatar_perception() | 30 мин |
| 7 | Собрать всё в npc_tick_pipeline | 30 мин |
| 8 | Тесты | 30 мин |

**Итого:** ~3.5 часа

**Предпосылки:** ТЗ-10 (аффективный pipeline подключён) — иначе `affective_imprints` всегда пустой

---

Давать следующее? Это **ТЗ-14: Cross-location Navigation** (TRANSIT intent + движение между локациями).