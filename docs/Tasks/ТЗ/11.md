## ТЗ-04: Belief Layer (v12.0) — реализация PatternDetector

**Статус:** ⚠️ ЧАСТИЧНО | **Критичность:** MEDIUM | **Волна:** 4 (зависит от ТЗ-01)

---

### Суть проблемы одной строкой

Убеждения NPC меняются, но **нет механизма распознавания паттернов** — NPC не может понять «этот торговец всегда обманывает». Плюс два writer'а пишут в одни убеждения без координации, а drift-события личности теряются, не доходя до хроники.

---

### Три проблемы в одном слое

```
Проблема 1: Dual-writer в BeliefState
  BeliefTransitionEngine (R7) пишет в фазе 5
  BeliefAggregator (R8) пишет в фазе 8
  → last-write-wins, молчаливая перезапись

Проблема 2: PatternDetector = PROPOSED
  NPC видит 5 раз, как торговец обманывает
  Но не может кристаллизовать убеждение "торговец — обманщик"
  → каждый раз реагирует как впервые

Проблема 3: L1 drift events не попадают в L1Chronicle
  compute_continuous_drift() возвращает TraitDriftEvent
  Но L1EventStream.append() никогда не вызывается
  → L3 projection всегда = L0, личность никогда не меняется
```

---

### Пошаговый план исправления

#### Шаг 1: Решить dual-writer проблему в BeliefState

**Файл:** `backend/app/models/npc/beliefs.py`

```python
# СЕЙЧАС (сломано):
class BeliefState:
    """
    ⚠️ ДВА независимых writer'а:
    R7: BeliefTransitionEngine
    R8: CoherenceBeliefAggregator
    last-write-wins — conscious compromise
    """
    
    def update(self, belief_id: str, data: dict):
        self.beliefs[belief_id] = data  # ← перезапись!
```

**Как чинить — merge-стратегия:**

```python
@dataclass
class BeliefEntry:
    """Одно убеждение с историей записи"""
    belief_id: str
    confidence: float          # 0..1
    evidence: List[str]        # список свидетельств
    last_writer: str           # "R7" или "R8"
    last_updated_tick: int
    
    # НОВОЕ: merge metadata
    r7_confidence: Optional[float] = None
    r8_confidence: Optional[float] = None
    r7_evidence: List[str] = field(default_factory=list)
    r8_evidence: List[str] = field(default_factory=list)

class BeliefState:
    """Состояние убеждений NPC с merge-стратегией"""
    
    def update(
        self,
        belief_id: str,
        confidence: float,
        evidence: List[str],
        writer: str,  # "R7" или "R8"
        tick: int,
    ):
        existing = self.beliefs.get(belief_id)
        
        if existing is None:
            # Новое убеждение — просто записать
            self.beliefs[belief_id] = BeliefEntry(
                belief_id=belief_id,
                confidence=confidence,
                evidence=evidence,
                last_writer=writer,
                last_updated_tick=tick,
                r7_confidence=confidence if writer == "R7" else None,
                r8_confidence=confidence if writer == "R8" else None,
                r7_evidence=evidence if writer == "R7" else [],
                r8_evidence=evidence if writer == "R8" else [],
            )
        else:
            # СУЩЕСТВУЮЩЕЕ убеждение — MERGE вместо перезаписи
            self._merge_belief(existing, confidence, evidence, writer, tick)
    
    def _merge_belief(
        self,
        existing: BeliefEntry,
        new_confidence: float,
        new_evidence: List[str],
        writer: str,
        tick: int,
    ):
        """Merge двух writer'ов: взвешенное среднее confidence, union evidence"""
        
        # Сохранить данные writer'а
        if writer == "R7":
            existing.r7_confidence = new_confidence
            existing.r7_evidence = new_evidence
        else:
            existing.r8_confidence = new_confidence
            existing.r8_evidence = new_evidence
        
        # MERGE confidence: взвешенное среднее
        # R7 (непосредственный опыт) весит больше, чем R8 (когерентность)
        if existing.r7_confidence is not None and existing.r8_confidence is not None:
            existing.confidence = (
                existing.r7_confidence * 0.6 +  # опыт важнее
                existing.r8_confidence * 0.4     # когерентность корректирует
            )
        elif existing.r7_confidence is not None:
            existing.confidence = existing.r7_confidence
        else:
            existing.confidence = existing.r8_confidence
        
        # MERGE evidence: union без дубликатов
        all_evidence = list(set(existing.r7_evidence + existing.r8_evidence))
        existing.evidence = all_evidence
        
        existing.last_writer = writer
        existing.last_updated_tick = tick
```

---

#### Шаг 2: Реализовать PatternDetector (минимальная версия)

**Новый файл:** `backend/app/services/npc/pattern_detector.py`

```python
from dataclasses import dataclass
from typing import List, Optional, Dict
from app.models.npc.beliefs import BeliefState, BeliefEntry

@dataclass
class DetectedPattern:
    """Распознанный поведенческий паттерн"""
    subject: str           # кто: "merchant_goran"
    action_type: str       # что: "overcharges" / "lies" / "helps"
    observation_count: int # сколько раз наблюдалось
    confidence: float      # 0..1, зависит от count
    first_seen_tick: int
    last_seen_tick: int

class PatternDetector:
    """Распознавание поведенческих паттернов из narrative_cache"""
    
    # Минимум наблюдений для распознавания паттерна
    MIN_OBSERVATIONS: int = 3
    
    # Типы паттернов и их маппинг на убеждения
    PATTERN_TO_BELIEF = {
        "overcharges": {
            "belief_id": "subject_is_greedy",
            "confidence_per_obs": 0.15,
            "max_confidence": 0.8,
        },
        "lies": {
            "belief_id": "subject_is_dishonest",
            "confidence_per_obs": 0.2,
            "max_confidence": 0.9,
        },
        "helps": {
            "belief_id": "subject_is_helpful",
            "confidence_per_obs": 0.1,
            "max_confidence": 0.7,
        },
        "attacks": {
            "belief_id": "subject_is_dangerous",
            "confidence_per_obs": 0.25,
            "max_confidence": 0.95,
        },
        "steals": {
            "belief_id": "subject_is_thief",
            "confidence_per_obs": 0.3,
            "max_confidence": 0.95,
        },
        "shares_food": {
            "belief_id": "subject_is_generous",
            "confidence_per_obs": 0.1,
            "max_confidence": 0.7,
        },
    }
    
    def detect_patterns(
        self,
        narrative_cache: List[dict],
        current_tick: int,
    ) -> List[DetectedPattern]:
        """
        Сканировать narrative_cache на повторяющиеся паттерны.
        Возвращает список распознанных паттернов.
        """
        # Сгруппировать наблюдения по (subject, action_type)
        observation_map: Dict[tuple, List[dict]] = {}
        
        for memory in narrative_cache:
            subject = memory.get("subject", "")
            action = memory.get("action", "")
            
            # Нормализовать action к типу паттерна
            action_type = self._classify_action(action)
            if not action_type:
                continue
            
            key = (subject, action_type)
            if key not in observation_map:
                observation_map[key] = []
            observation_map[key].append(memory)
        
        # Найти паттерны с достаточным количеством наблюдений
        patterns = []
        for (subject, action_type), observations in observation_map.items():
            if len(observations) >= self.MIN_OBSERVATIONS:
                confidence = self._compute_confidence(action_type, len(observations))
                patterns.append(DetectedPattern(
                    subject=subject,
                    action_type=action_type,
                    observation_count=len(observations),
                    confidence=confidence,
                    first_seen_tick=observations[0].get("tick", 0),
                    last_seen_tick=observations[-1].get("tick", current_tick),
                ))
        
        return patterns
    
    def patterns_to_belief_updates(
        self,
        patterns: List[DetectedPattern],
    ) -> List[dict]:
        """Преобразовать паттерны в предложения обновления убеждений"""
        updates = []
        
        for pattern in patterns:
            mapping = self.PATTERN_TO_BELIEF.get(pattern.action_type)
            if not mapping:
                continue
            
            belief_id = f"{pattern.subject}:{mapping['belief_id']}"
            
            updates.append({
                "belief_id": belief_id,
                "confidence": pattern.confidence,
                "evidence": [
                    f"observed_{pattern.action_type}_x{pattern.observation_count}"
                ],
                "source": "pattern_detector",
                "subject": pattern.subject,
            })
        
        return updates
    
    def _classify_action(self, action: str) -> Optional[str]:
        """Классифицировать действие в тип паттерна"""
        classification = {
            # Жадность
            "overcharge": "overcharges",
            "refuse_discount": "overcharges",
            "hoard": "overcharges",
            # Обман
            "lie": "lies",
            "deceive": "lies",
            "break_promise": "lies",
            # Помощь
            "help": "helps",
            "heal": "helps",
            "share": "helps",
            # Насилие
            "attack": "attacks",
            "threaten": "attacks",
            "intimidate": "attacks",
            # Воровство
            "steal": "steals",
            "pickpocket": "steals",
            # Щедрость
            "share_food": "shares_food",
            "give_gift": "shares_food",
            "offer_free": "shares_food",
        }
        return classification.get(action.lower())
    
    def _compute_confidence(self, action_type: str, count: int) -> float:
        """Вычислить confidence на основе количества наблюдений"""
        mapping = self.PATTERN_TO_BELIEF.get(action_type, {})
        per_obs = mapping.get("confidence_per_obs", 0.1)
        max_conf = mapping.get("max_confidence", 0.8)
        return min(max_conf, per_obs * count)
```

---

#### Шаг 3: Подключить PatternDetector к npc_tick_pipeline

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py`

```python
# ПОСЛЕ обновления narrative_cache, ДО DecisionHub:

# 1. Запустить PatternDetector
patterns = self.pattern_detector.detect_patterns(
    narrative_cache=npc_state.narrative_cache,
    current_tick=ctx.current_tick,
)

# 2. Преобразовать паттерны в обновления убеждений
if patterns:
    belief_updates = self.pattern_detector.patterns_to_belief_updates(patterns)
    
    for update in belief_updates:
        npc_state.beliefs.update(
            belief_id=update["belief_id"],
            confidence=update["confidence"],
            evidence=update["evidence"],
            writer="R9",  # PatternDetector = новый writer R9
            tick=ctx.current_tick,
        )
        
        # Логировать распознанный паттерн
        logger.info(
            f"Pattern detected: {update['belief_id']} "
            f"conf={update['confidence']:.2f} "
            f"evidence={update['evidence']}"
        )
```

---

#### Шаг 4: Подключить L1 drift events к L1Chronicle

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py`

```python
# СЕЙЧАС (сломано):
drift_events = self.break_progress_engine.compute_continuous_drift(npc_state)
# drift_events → List[TraitDriftEvent]
# Но L1EventStream.append() НИКОГДА не вызывается
# → drift не влияет на L3 projection

# ИСПРАВИТЬ: записать drift events в L1Chronicle
drift_events = self.break_progress_engine.compute_continuous_drift(npc_state)

if drift_events:
    for event in drift_events:
        self.l1_chronicle.append(
            npc_id=npc_state.npc_id,
            event_type="trait_drift",
            data={
                "trait": event.trait_name,
                "delta": event.delta,
                "source": event.source,
                "tick": ctx.current_tick,
            },
        )
```

---

#### Шаг 5: DriveResolver читает из L1Chronicle

**Файл:** `backend/app/services/npc/drive_resolver.py`

```python
# СЕЙЧАС: L3 projection = L0 (потому что L1Chronicle пуст)
# ИСПРАВИТЬ: DriveResolver должен применять drift events из Chronicle

class DriveResolver:
    
    def resolve(self, npc_state: NPCState) -> Dict[str, float]:
        """Вычислить L3 projection из L0 + L1 drift events"""
        
        l0 = npc_state.drives_base  # статический архетип
        l3 = dict(l0)               # начать с L0
        
        # Прочитать все drift events из L1Chronicle
        chronicle = self.l1_chronicle.get_events(npc_state.npc_id)
        
        for event in chronicle:
            trait = event.data.get("trait")
            delta = event.data.get("delta", 0)
            
            if trait in l3:
                l3[trait] += delta
                # Ограничить диапазон [0, 1]
                l3[trait] = max(0.0, min(1.0, l3[trait]))
        
        return l3
```

---

### Как проверить

```python
# Тест: PatternDetector распознаёт повторяющееся поведение
def test_pattern_detection():
    npc = create_test_npc()
    
    # NPC видел, как торговец обманул 4 раза
    narrative = [
        {"subject": "merchant_goran", "action": "overcharge", "tick": 10},
        {"subject": "merchant_goran", "action": "lie", "tick": 15},
        {"subject": "merchant_goran", "action": "overcharge", "tick": 20},
        {"subject": "merchant_goran", "action": "overcharge", "tick": 25},
        {"subject": "merchant_goran", "action": "lie", "tick": 30},
    ]
    npc.narrative_cache = narrative
    
    detector = PatternDetector()
    patterns = detector.detect_patterns(narrative, current_tick=30)
    
    # Должен распознать 2 паттерна: overcharges (3x) и lies (2x)
    assert len(patterns) == 1  # только overcharges достиг MIN_OBSERVATIONS=3
    
    overcharge_pattern = patterns[0]
    assert overcharge_pattern.subject == "merchant_goran"
    assert overcharge_pattern.action_type == "overcharges"
    assert overcharge_pattern.observation_count == 3

# Тест: L1 drift events влияют на L3 projection
def test_l1_drift_changes_l3():
    npc = create_test_npc(drives_base={"fear": 0.2, "control": 0.7})
    
    # Записать drift event: страх вырос на 0.3
    l1_chronicle.append(npc.npc_id, "trait_drift", {
        "trait": "fear", "delta": 0.3, "source": "combat_trauma"
    })
    
    resolver = DriveResolver(l1_chronicle=l1_chronicle)
    l3 = resolver.resolve(npc)
    
    # L3 должен отличаться от L0
    assert l3["fear"] == 0.5   # 0.2 + 0.3
    assert l3["control"] == 0.7 # не изменился

# Тест: merge-стратегия убеждений
def test_belief_merge():
    beliefs = BeliefState()
    
    # R7 пишет: confidence=0.6
    beliefs.update("goran:honest", 0.6, ["traded_fairly"], writer="R7", tick=10)
    
    # R8 пишет: confidence=0.3 (когерентность с другими убеждениями)
    beliefs.update("goran:honest", 0.3, ["inconsistent_with_greed"], writer="R8", tick=10)
    
    # Merged: 0.6 * 0.6 + 0.3 * 0.4 = 0.48
    assert beliefs.beliefs["goran:honest"].confidence == pytest.approx(0.48, abs=0.01)
    # Evidence: union обоих writer'ов
    assert len(beliefs.beliefs["goran:honest"].evidence) == 2
```

---

### Порядок исправления

| # | Шаг | Время |
|---|-----|-------|
| 1 | BeliefEntry + merge-стратегия в BeliefState | 45 мин |
| 2 | PatternDetector реализация | 1 час |
| 3 | Подключить PatternDetector к pipeline | 20 мин |
| 4 | L1 drift → L1Chronicle | 20 мин |
| 5 | DriveResolver читает L1Chronicle | 30 мин |
| 6 | Тесты | 30 мин |

**Итого:** ~3 часа

**Предпосылки:** ТЗ-01 (DecisionHub API) — убеждения должны влиять на решения

---

Давать следующее? Это **ТЗ-05: SocialPropagation — NPC→NPC** (социальные модификаторы между NPC).