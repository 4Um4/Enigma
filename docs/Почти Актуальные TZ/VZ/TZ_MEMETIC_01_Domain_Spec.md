# ТЗ: ДОМЕН MEMETIC TRANSMISSION (Memetic Transmission Domain Spec)

> **Проект:** ENIGMA / The Fool
> **Версия ТЗ:** 1.0
> **Статус:** PROPOSED
> **Дата:** 2026-07-03
> **Зависимости:** `TZ_CONTENT_POLICY_FUNDAMENT.md` (обязательно к реализации первым)
> **Связанные документы:** `architecture/identity.yaml`, `architecture/memory.yaml`, `architecture/verbalization.yaml`, будущий `TZ-MEMETIC-02/03`
> **Критичность:** P0 — фундаментальная онтология
> **Архитектурный принцип:** ADR-O-MEMETIC-001 (вводится этим ТЗ)

---

## 0. НАЗНАЧЕНИЕ И СКОУП

### 0.1. Цель

Ввести в ENIGMA **единый механизм культурной трансляции**, в котором единицей эволюции является не слово, а **мем** — культурная единица любого типа (слово, имя, прозвище, ритуал, жест, название монеты, поговорка и т.д.).

Это ТЗ описывает:
- Онтологию домена (Concept / Expression / Adoption / Norm / Extinction)
- Иерархию типов (Core Types / Domain Types / Tags)
- Persistence по трёхслойной модели Canon/History/State (введённой ADR-O-MEMETIC-000)
- Интеграцию с существующим доменом IDENTITY (L0/L1/L1.5/L2.5/L3)
- Cultural Pressure Accumulator (per event × community)
- Memetic Burst pipeline (детерминированный триггер → LLM-генерация → валидация → реестр)
- Конкуренцию мутаций (adoption dynamics)
- Player-created memes с adoption backpressure
- Аналитический drift для перемотки времени

### 0.2. Что входит в scope

| Входит | Не входит |
|---|---|
| Concept Registry (канон) | Реализация UI редактора концептов |
| Expression Registry (канон) | Per-NPC adoption UI |
| MemeticTransmissionEvent (история) | Сложные визуализации культурных графов |
| Speaker Vocabulary (состояние) | Voice Archetype editor |
| Cultural Pressure Accumulator | Memetic Burst UI preview |
| Memetic Burst pipeline (LLM + validator) | Player feedback UI на bursts |
| Конкуренция мутаций (Bass diffusion) | Cross-campaign memetic migration |
| Player-created memes | |
| Extinction engine | |
| Аналитический drift для time-skip | |

### 0.3. Теоретическая база

Архитектура опирается на три устоявшиеся исследовательские традиции:

1. **Memetics** (Dawkins 1976 «Selfish Gene», Blackmore 1999 «The Meme Machine»): культурные единицы аналогичны генам — реплицируются, мутируют, подвергаются отбору.
2. **Epidemiology of Representations** (Sperber 1996): мемы распространяются как инфекции, с носителями, контагиозностью и порогами устойчивости.
3. **Dual Inheritance Theory** (Boyd & Richerson 1985 «Culture and Evolutionary Process»): культурная эволюция подчиняется формальным правилам, допускает аналитическую аппроксимацию.

Дополнительно используются:
- **Speech Accommodation Theory** (Giles 1973): носители сдвигаются к собеседнику при симпатии, отдаляются при антипатии.
- **Lexical Diffusion** (Wang 1969, Labov 2001): слова усваиваются по одному, не пачкой; критический период 2-7 лет, подростковый пик 12-15.
- **Bass Diffusion Model** (Bass 1969): аналитическая модель распространения инноваций.
- **Axelrod Model of Cultural Dissemination** (Axelrod 1997): сетевая модель культурной гомогенизации.

### 0.4. Принцип «LLM — голос, а не источник истины»

Это расширение фундаментального принципа ENIGMA из `README.md:83`. В memetic-домене:

- **LLM не создаёт законы культуры.** Она лишь предлагает языковые формы для мемов, которые детерминированная система решила породить.
- **LLM не решает, что приживётся.** Adoption определяется симуляцией: кто кому рассказывает, с каким весом, при каких отношениях.
- **LLM не валидирует.** Валидатор детерминирован (морфология, канон-консистентность, density cap). LLM — только эксперт по стилистике эпохи, и то опционально.

---

## 1. ОНТОЛОГИЯ ДОМЕНА

### 1.1. Жизненный цикл мема

```
CONCEPT  →  EXPRESSION  →  SPREAD  →  CRYSTALLIZATION  →  EXTINCTION
(sense)     (form)          (adoption)  (norm)              (disuse)
   ↑                                                          │
   └────────────────── (revival via memetic burst) ────────────┘
```

**Пять состояний**, каждое живёт своей жизнью:

| Состояние | Уровень | Что это | Где хранится |
|---|---|---|---|
| CONCEPT | Canon | Инвариант смысла. «Стражник» как роль. Не зависит от слова. | `config/canon/concepts/*.yaml` |
| EXPRESSION | Canon | Форма. «Стражник», «железник», «синяя спина». | `config/canon/concepts/*.yaml` (внутри Concept) |
| SPREAD | State | Кто знает/использует. Per-NPC adoption table. | `saves/<campaign>/state.db` |
| CRYSTALLIZATION | State | Community-level: «в деревне X норма — железник». | `saves/<campaign>/state.db` |
| EXTINCTION | History | Expression, который nobody не использовал N тиков. | `saves/<campaign>/history.db` |

### 1.2. Concept

Concept — это **инвариант смысла**. Он рождается, когда появляется новый культурный объект. У него есть referent (что он обозначает), но нет конкретной формы — форма живёт в Expression.

```python
# backend/app/domain/memetic/concept.py — НОВЫЙ ФАЙЛ

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class Concept:
    """Культурный объект. Инвариант смысла.
    
    Примеры:
      - concept_id="guard_role", referent="Стражник как социальная роль"
      - concept_id="holiday_orm_slaying", referent="Праздник в честь победы Орма над драконом"
      - concept_id="steel_material", referent="Сталь как материал"
      - concept_id="personal_name_orm", referent="Личное имя Орм"
    
    Один Concept может иметь много Expressions (синонимия).
    Один Expression может указывать на несколько Concept (полисемия).
    """
    concept_id: str                    # стабильно во веки веков
    referent: str                       # что обозначает
    core_type: CoreType                 # из закрытого списка (см. §2.1)
    domain_types: Tuple[str, ...]       # из расширяемого списка (см. §2.2)
    domain: str                         # "law_enforcement" / "currency" / "deity" / ...
    
    # Происхождение
    created_tick: int                   # когда впервые появился в мире
    origin_npc_id: Optional[str] = None # кто впервые выразил (None = авторский канон)
    origin_event_id: Optional[str] = None  # какое событие породило (для bursts)
    
    # Метаданные
    description: str = ""               # человекочитаемое описание для авторов
    version: str = "1.0"                # для миграций
    
    # Aliases — Expressions, встроенные в Concept
    # (см. §1.3 — Expression всегда часть Concept)
    aliases: Tuple["Expression", ...] = ()
```

### 1.3. Expression (как Alias внутри Concept)

Expression — это **форма**. Согласно принципу из обсуждения, Expression **не существует сам по себе** — он всегда выражает какой-то Concept. Поэтому Expression хранится **внутри** Concept как `alias`.

```python
# backend/app/domain/memetic/expression.py — НОВЫЙ ФАЙЛ

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple, Optional


@dataclass(frozen=True)
class Expression:
    """Форма выражения Concept. Всегда часть какого-то Concept.
    
    Примеры:
      - form="стражник", register="formal", culture="capital"
      - form="железник", register="slang", culture="thieves"
      - form="синяя спина", register="epithet", culture="north"
    
    Один Concept → много Expressions (синонимия).
    """
    text: str                            # "железник" — конкретная форма
    register: str                        # "formal" / "slang" / "archaic" / "childish" / "sacred" / "epithet"
    culture: str                         # к какой культуре принадлежит ("capital" / "thieves" / "north")
    probability: float = 0.5             # начальная вероятность выбора в этой культуре (0..1)
    
    # Категории для ContentPolicy фильтрации
    category_tags: Tuple[str, ...] = ()  # ["profanity:mild", "vulgar", "criminal"]
    
    # Происхождение
    creator_npc_id: Optional[str] = None  # кто впервые произнёс (None = авторский)
    created_tick: int = 0
    
    # Жизненный цикл
    is_extinct: bool = False             # помечен как вышедший из употребления
    extinct_tick: Optional[int] = None
    is_revived: bool = False             # был extinct, потом снова появился
```

**Пример полного Concept с aliases:**

```yaml
# config/canon/concepts/guard_role.yaml
concept_id: guard_role
referent: "Стражник как социальная роль — охранник порядка в городе"
core_type: ROLE
domain_types:
  - LAW_ENFORCEMENT
domain: law_enforcement
created_tick: 0
description: "Базовая роль городской стражи. Существует с начала кампании."
version: "1.0"

aliases:
  - text: "стражник"
    register: formal
    culture: capital
    probability: 0.95
    category_tags: [official]
    created_tick: 0
    
  - text: "страж"
    register: formal
    culture: capital
    probability: 0.3
    category_tags: [official, poetic]
    created_tick: 0
    
  - text: "железник"
    register: slang
    culture: thieves
    probability: 0.8
    category_tags: [vulgar:mild, criminal]
    creator_npc_id: thief_shadow
    created_tick: 1247
    
  - text: "синяя спина"
    register: epithet
    culture: north
    probability: 0.4
    category_tags: [informal, regional]
    creator_npc_id: blacksmith_orm
    created_tick: 2103
    
  - text: "караульный"
    register: formal
    culture: military
    probability: 0.7
    category_tags: [official, military]
    created_tick: 0
```

### 1.4. Adoption (per-NPC, State)

Adoption — это **знание конкретным NPC конкретного Expression**. Это состояние, не канон.

```python
# backend/app/domain/memetic/adoption.py — НОВЫЙ ФАЙЛ

@dataclass
class Adoption:
    """NPC знает Expression. State-level (mutable).
    
    Хранится в saves/<campaign>/state.db, table: npc_adoptions.
    """
    npc_id: str
    concept_id: str
    expression_text: str         # ссылка на alias в Concept
    
    # Уровень владения
    is_preferred: bool = False   # какое выражение NPC выбирает по умолчанию
    confidence: float = 0.0      # 0..1, насколько уверено использование
    usage_count: int = 0         # сколько раз использовал в речи
    
    # Источник усвоения
    adopted_tick: int = 0        # когда впервые усвоено
    adopted_from_npc_id: Optional[str] = None  # от кого усвоено
    adopted_via: str = "dialogue"  # "dialogue" / "eavesdrop" / "childhood" / "burst"
    
    # Устойчивость к забыванию
    last_used_tick: int = 0      # для decay-расчёта
    reinforcement_count: int = 0  # сколько раз подтверждалось использованием
```

**Speaker Vocabulary** — это агрегация всех Adoptions одного NPC по одному Concept:

```python
@dataclass
class SpeakerVocabulary:
    """Что NPC знает о Concept и что предпочитает говорить."""
    npc_id: str
    concept_id: str
    
    preferred: Optional[str] = None    # text выражения, которое NPC выбирает по умолчанию
    known: list[str] = field(default_factory=list)  # все известные texts
    
    @classmethod
    def from_adoptions(cls, npc_id: str, concept_id: str, 
                       adoptions: list[Adoption]) -> "SpeakerVocabulary":
        preferred = next((a.expression_text for a in adoptions if a.is_preferred), None)
        known = [a.expression_text for a in adoptions]
        return cls(npc_id=npc_id, concept_id=concept_id, preferred=preferred, known=known)
```

### 1.5. CulturalNorm (community-level, State)

CulturalNorm — это **доминирующее выражение в общности**. Когда 80% NPC в деревне говорят «железник», это норма.

```python
@dataclass
class CulturalNorm:
    """В общности C для Concept X доминирует Expression Y.
    
    Вычисляется периодически из adoptions всех NPC в community.
    """
    community_id: str            # "capital" / "thieves_guild" / "north_village"
    concept_id: str
    dominant_expression: str     # text
    dominance_share: float       # 0..1, какая доля NPC использует
    
    # Метаданные
    last_computed_tick: int = 0
    history: list[tuple[int, str, float]] = field(default_factory=list)
    # [(tick, expression_text, share), ...] — для tracking дрейфа
```

### 1.6. Extinction

Expression помечается `is_extinct=True`, когда:
- `last_used_tick` был более N тиков назад (N настраивается, дефолт 2000 = ~33 игровых дня)
- И `usage_count` < 5 за всю историю
- И не является `preferred` ни у одного живого NPC

Extinct expressions **не удаляются из Canon** — они остаются в `Concept.aliases`, но помечаются `is_extinct=True`. LLM получает в `voice_profile` только активные expressions, extinct помечаются как «устаревшие, использовать только если NPC намеренно цитирует старину».

Extinct expressions могут **возрождаться** через memetic burst (если культурное событие триггерит interest к старине) — тогда `is_revived=True`, `is_extinct=False`.

---

## 2. ИЕРАРЧИЯ ТИПОВ

### 2.1. Core Types (закрытый список)

16 архитектурных категорий. Никогда не меняются (кроме ADR-level решений).

```python
# backend/app/domain/memetic/core_types.py — НОВЫЙ ФАЙЛ

from enum import Enum


class CoreType(str, Enum):
    """16 фундаментальных категорий культурных объектов.
    
    Закрытый список. Расширение — только через ADR.
    Каждый CoreType определяет базовые операции (can_spread, can_be_used_in_speech, 
    can_be_inherited_by_children, etc.).
    """
    
    PERSON = "PERSON"                    # конкретная личность (Орм, Тень)
    PLACE = "PLACE"                      # локация (таверна, столица)
    OBJECT = "OBJECT"                    # физический объект (меч, монета)
    ACTION = "ACTION"                    # действие (бить, красть, молиться)
    ROLE = "ROLE"                        # социальная роль (стражник, кузнец)
    ORGANIZATION = "ORGANIZATION"        # группа (гильдия воров, церковь)
    LANGUAGE = "LANGUAGE"                # язык/диалект (древний, торговый)
    RITUAL = "RITUAL"                    # ритуал (похороны, свадьба)
    BELIEF = "BELIEF"                    # верование (боги, приметы)
    EVENT = "EVENT"                      # событие (битва, коронация)
    LAW = "LAW"                          # закон/норма (запрет, обычай)
    SYMBOL = "SYMBOL"                    # символ (герб, знак, татуировка)
    RESOURCE = "RESOURCE"                # ресурс (железо, золото, лён)
    BIOLOGY = "BIOLOGY"                  # биологическое (болезнь, растение, животное)
    TIME = "TIME"                        # временная единица (час, неделя, праздник)
    SOCIAL = "SOCIAL"                    # социальная практика (приветствие, обращение)
```

### 2.2. Domain Types (расширяемые, с обязательным parent)

Domain Types — конкретные подтипы. Каждый **обязан** указать один или несколько `parent` из CoreType (или из другого Domain Type). Множественное наследование допустимо.

```python
# backend/app/domain/memetic/domain_types.py — НОВЫЙ ФАЙЛ

# Реестр Domain Types. Не enum, а словарь, потому что расширяемый.
# Автор кампании может добавлять свои Domain Types в config/canon/domain_types.yaml.

DOMAIN_TYPES_REGISTRY: dict[str, "DomainType"] = {}


@dataclass(frozen=True)
class DomainType:
    """Расширяемый подтип. Обязан иметь parent (один или несколько)."""
    type_id: str                          # "FOOD_RECIPE"
    parent_ids: tuple[str, ...]           # ("OBJECT",) или ("RITUAL", "SOCIAL")
    description: str = ""


def register_domain_type(type_id: str, parent_ids: tuple[str, ...], 
                         description: str = "") -> None:
    """Регистрирует новый Domain Type. 
    Parent должен быть CoreType или уже зарегистрированным Domain Type."""
    for parent in parent_ids:
        if parent not in DOMAIN_TYPES_REGISTRY and parent not in CoreType.__members__:
            raise ValueError(f"Unknown parent: {parent}")
    DOMAIN_TYPES_REGISTRY[type_id] = DomainType(
        type_id=type_id, parent_ids=parent_ids, description=description
    )


# Стандартные Domain Types (регистрируются при старте)
def _register_standard_domain_types() -> None:
    register_domain_type("FOOD_RECIPE", ("OBJECT",), 
                         "Кулинарный рецепт как передаваемое знание")
    register_domain_type("DEITY_NAME", ("PERSON", "BELIEF"), 
                         "Имя божества")
    register_domain_type("DISEASE_NAME", ("BIOLOGY",), 
                         "Название болезни")
    register_domain_type("GREETING", ("SOCIAL",), 
                         "Формула приветствия")
    register_domain_type("OATH", ("RITUAL", "SOCIAL"), 
                         "Клятва как ритуальное действие")
    register_domain_type("TATTOO_PATTERN", ("SYMBOL", "OBJECT"), 
                         "Узор татуировки")
    register_domain_type("PROFESSION_NAME", ("ROLE",), 
                         "Название профессии")
    register_domain_type("CURRENCY_NAME", ("OBJECT", "RESOURCE"), 
                         "Название денежной единицы")
    register_domain_type("KINSHIP_TERM", ("SOCIAL",), 
                         "Термин родства")
    register_domain_type("UNIT_OF_TIME", ("TIME",), 
                         "Единица измерения времени")
    register_domain_type("HOLIDAY", ("EVENT", "RITUAL"), 
                         "Праздник как регулярное событие")
    register_domain_type("EPITHET", ("SYMBOL", "SOCIAL"), 
                         "Прозвище/эпитет")
    register_domain_type("PROVERB", ("LANGUAGE", "BELIEF"), 
                         "Поговорка как культурная единица")
    register_domain_type("TABOO_PRACTICE", ("RITUAL", "SOCIAL"), 
                         "Табуированная социальная практика (каннибализм и т.д.)")
    register_domain_type("SUPERSTITION", ("BELIEF",), 
                         "Суеверие")
    register_domain_type("EPONYM", ("PERSON", "OBJECT"), 
                         "Имя, ставшее нарицательным (ормовская сталь)")
```

**Пример:**
```yaml
# config/canon/domain_types.yaml — автор может расширять
- type_id: CURSED_RECIPE
  parent_ids: [FOOD_RECIPE, BELIEF]
  description: "Рецепт, связанный с проклятием или тёмной магией"
```

Через `parent_ids` система знает: `CURSED_RECIPE → FOOD_RECIPE → OBJECT` (значит, можно готовить, передавать, забыть, назвать) **и** `CURSED_RECIPE → BELIEF` (значит, может быть табуирован, связан с ритуалом).

### 2.3. Tags (полностью открытые)

Tags — не типы. Это **свойства** выражений, не концептов. Используются для:
- Фильтрации в ContentPolicy (см. `TZ_CONTENT_POLICY_FUNDAMENT.md` §2.1)
- Поиска в реестре
- Пометки для будущего UI

```python
# Tags — это просто строки. Любые.
# Примеры category_tags в Expression:
["vulgar:mild", "criminal", "obsolete:rising"]
["sacred", "religious", "ancient"]
["noble", "formal", "capital"]
["childish", "regional", "deprecated"]
```

**Правило**: tags никогда не влияют на онтологию. Они влияют только на фильтрацию и отображение. Если автор удаляет все tags с expression — система продолжает работать, просто теряются фильтры.

---

## 3. PERSISTENCE

### 3.1. Трёхслойная онтология (напоминание)

Согласно ADR-O-MEMETIC-000 (введённому `TZ_CONTENT_POLICY_FUNDAMENT.md`):

| Слой | Технология | Что хранит |
|---|---|---|
| **Canon** | JSON/YAML + git | Concept Registry, Expression Registry, Domain Types Registry, Cultural Defaults |
| **History** | SQLite, append-only | MemeticTransmissionEvent, MemeticBurstLog, ExtinctionLog |
| **State** | SQLite, mutable | NPCAdoption, CulturalNorm, CulturalPressureAccumulator |

### 3.2. Структура каталогов

```
config/
    canon/
        concepts/                          # Canon: все Concept-ы
            guard_role.yaml
            blacksmith_role.yaml
            coin_currency.yaml
            holiday_orm_slaying.yaml
            personal_name_orm.yaml
            ...
        domain_types.yaml                  # Canon: реестр Domain Types
        voice_archetypes/                  # Canon: архетипы голоса
            noble.yaml
            thief.yaml
            maid.yaml
            merchant.yaml
            blacksmith.yaml
            guard.yaml
        content_policy_defaults.yaml       # Canon: из fundament ТЗ
    
    user_settings.yaml                     # State: настройки игрока

saves/<campaign_id>/
    state.db                               # State: NPCAdoption, CulturalNorm, ...
    history.db                             # History: MemeticTransmissionEvent, ...

backend/data/
    insults_ru.json                        # Canon: лексикон profanity
    sexual_lexicon_ru.json                 # Canon: лексикон sexual
    violence_lexicon_ru.json               # Canon: лексикон violence
    taboo_lexicon_ru.json                  # Canon: лексикон taboo
```

### 3.3. Canon: `config/canon/concepts/<concept_id>.yaml`

Один файл = один Concept. Это позволяет git-у красиво отслеживать изменения и автору редактировать точечно.

```yaml
# config/canon/concepts/holiday_orm_slaying.yaml
# Concept, созданный memetic burst-ом (см. §6)

concept_id: holiday_orm_slaying
referent: "Праздник в честь победы кузнеца Орма над драконом, спасшей столицу"
core_type: EVENT
domain_types:
  - HOLIDAY
domain: heroic_legend
created_tick: 8472                          # когда Орм спас столицу
origin_npc_id: null                         # не один NPC, а событие
origin_event_id: orm_slew_dragon_8472       # ссылка на событие в L1Chronicle
description: |
  Ежегодный праздник, посвящённый подвигу Орма.
  Отмечается в день битвы. Включает:
  - торжественную процессию
  - раздачу железных украшений
  - пересказ подвига
version: "1.0"

aliases:
  - text: "Ормов день"
    register: formal
    culture: capital
    probability: 0.95
    category_tags: [noble, heroic]
    creator_npc_id: null                    # создан LLM в burst
    created_tick: 8520                      # через 48 тиков после события
    
  - text: "День Спасения"
    register: formal
    culture: capital_clergy
    probability: 0.6
    category_tags: [religious, formal]
    creator_npc_id: high_priest_melchior
    created_tick: 8601
    
  - text: "День Железной Победы"
    register: formal
    culture: blacksmith_guild
    probability: 0.5
    category_tags: [professional, heroic]
    creator_npc_id: blacksmith_guild_master
    created_tick: 8590
    
  - text: "Ормов праздник"
    register: colloquial
    culture: north_village
    probability: 0.7
    category_tags: [informal, regional]
    creator_npc_id: villager_petr
    created_tick: 9100
    
  - text: "День Орма"
    register: colloquial
    culture: common
    probability: 0.4
    category_tags: [informal]
    creator_npc_id: maid_lusya
    created_tick: 8700
```

### 3.4. History: таблица `memetic_transmission_events`

```sql
-- saves/<campaign>/history.db

CREATE TABLE memetic_transmission_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tick INTEGER NOT NULL,
    
    -- Кто кому передал
    source_npc_id TEXT NOT NULL,
    target_npc_id TEXT NOT NULL,
    
    -- Что передал
    concept_id TEXT NOT NULL,
    expression_text TEXT NOT NULL,
    
    -- Контекст передачи
    context TEXT NOT NULL,           -- 'dialogue' / 'eavesdrop' / 'childhood' / 'burst' / 'teaching'
    interaction_type TEXT,           -- 'greeting' / 'insult' / 'storytelling' / 'prayer' / ...
    
    -- Вес передачи (для adoption dynamics)
    transmission_weight REAL NOT NULL,  -- 0..1, см. §4.3
    
    -- Состояние в момент передачи
    source_stress REAL,
    target_stress REAL,
    relationship_trust REAL,
    relationship_respect REAL,
    
    -- Связь с burst (если применимо)
    burst_event_id TEXT,             -- ссылка на memetic_burst_log.event_id
    
    -- Timestamps
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_mte_target ON memetic_transmission_events(target_npc_id, concept_id);
CREATE INDEX idx_mte_tick ON memetic_transmission_events(tick);
CREATE INDEX idx_mte_burst ON memetic_transmission_events(burst_event_id);
```

**Append-only**. Никогда не UPDATE, никогда не DELETE (кроме explicit GC по ADR, который ещё не написан).

### 3.5. State: таблица `npc_adoptions`

```sql
-- saves/<campaign>/state.db

CREATE TABLE npc_adoptions (
    npc_id TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    expression_text TEXT NOT NULL,
    
    is_preferred BOOLEAN NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0.0,
    usage_count INTEGER NOT NULL DEFAULT 0,
    
    adopted_tick INTEGER NOT NULL,
    adopted_from_npc_id TEXT,
    adopted_via TEXT NOT NULL DEFAULT 'dialogue',
    
    last_used_tick INTEGER NOT NULL DEFAULT 0,
    reinforcement_count INTEGER NOT NULL DEFAULT 0,
    
    PRIMARY KEY (npc_id, concept_id, expression_text)
);

CREATE INDEX idx_adoptions_npc_concept ON npc_adoptions(npc_id, concept_id);
CREATE INDEX idx_adoptions_preferred ON npc_adoptions(npc_id, is_preferred);
```

**Mutable**. UPDATE при каждом использовании expression NPC. DELETE только при extinction.

### 3.6. State: таблица `cultural_norms`

```sql
-- saves/<campaign>/state.db

CREATE TABLE cultural_norms (
    community_id TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    
    dominant_expression TEXT NOT NULL,
    dominance_share REAL NOT NULL,
    
    last_computed_tick INTEGER NOT NULL,
    
    -- История дрейфа (последние 10 измерений)
    history_json TEXT NOT NULL DEFAULT '[]',
    
    PRIMARY KEY (community_id, concept_id)
);
```

### 3.7. State: таблица `cultural_pressure_accumulators`

```sql
-- saves/<campaign>/state.db

CREATE TABLE cultural_pressure_accumulators (
    event_id TEXT NOT NULL,           -- ссылка на L1Chronicle event
    community_id TEXT NOT NULL,
    
    notoriety REAL NOT NULL DEFAULT 0.0,        -- 0..1
    retelling_count INTEGER NOT NULL DEFAULT 0,
    last_retell_tick INTEGER NOT NULL,
    emotional_weight REAL NOT NULL DEFAULT 0.0,
    faction_alignment REAL NOT NULL DEFAULT 0.0,  -- -1..1
    
    pressure_score REAL NOT NULL DEFAULT 0.0,
    
    last_burst_tick INTEGER,          -- когда последний раз триггерил burst
    burst_count INTEGER NOT NULL DEFAULT 0,
    
    PRIMARY KEY (event_id, community_id)
);
```

### 3.8. History: таблица `memetic_burst_log`

```sql
-- saves/<campaign>/history.db

CREATE TABLE memetic_burst_log (
    burst_id TEXT PRIMARY KEY,        -- UUID
    event_id TEXT NOT NULL,           -- что триггернуло
    community_id TEXT NOT NULL,
    
    trigger_tick INTEGER NOT NULL,
    pressure_score REAL NOT NULL,
    
    -- Что LLM предложила
    proposed_artifacts_json TEXT NOT NULL,  -- список предложенных Concept/Expression
    
    -- Что прошло валидацию
    validated_artifacts_json TEXT NOT NULL,
    
    -- Что было принято в Canon
    accepted_concept_ids_json TEXT NOT NULL,   -- созданные Concept
    accepted_expression_refs_json TEXT NOT NULL, -- (concept_id, expression_text) tuples
    
    -- Статус
    status TEXT NOT NULL,             -- 'completed' / 'partial' / 'rejected'
    rejection_reasons_json TEXT,
    
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## 4. ИНТЕГРАЦИЯ С ДОМЕНОМ IDENTITY

### 4.1. Параллельная 5-уровневая модель

Существующий домен IDENTITY (см. `architecture/identity.yaml`) построен по схеме:
```
L0 (Архетип) → L1 (Хроника) → L1.5 (Статистика) → L2.5 (Кристаллизация) → L3 (Проекция)
```

Memetic-домен **повторяет ту же структуру**, но для языка/культуры вместо характера:

| Уровень | IDENTITY (характер) | MEMETIC (язык/культура) |
|---|---|---|
| **L0** | `NPCProfileL0` — архетип, drives | `VoiceArchetype` — родной язык, register, culture |
| **L1** | `L1Chronicle` — события жизни | `MemeticTransmissionEvent` — контакты с мемами |
| **L1.5** | `PatternDetector` — статистика | `MemeticAdoptionDetector` — статистика экспозиции |
| **L2.5** | `BeliefCrystallizationEngine` → `CrystallizedBelief` | `LexiconCrystallizationEngine` → `Adoption` (individual) + `CulturalNorm` (community) |
| **L3** | `DriveResolver` → `EffectiveDrives` | `ExpressionResolver` → `SpeakerVocabulary` |

### 4.2. L0: VoiceArchetype

```python
# backend/app/domain/memetic/voice_archetype.py — НОВЫЙ ФАЙЛ

@dataclass(frozen=True)
class VoiceArchetype:
    """Родной язык NPC. Canon-level.
    
    Загружается из config/canon/voice_archetypes/<archetype>.yaml.
    Один архетип на много NPC (noble, thief, maid, ...).
    """
    archetype_id: str                # "noble" / "thief" / "maid" / ...
    culture: str                     # к какой культуре принадлежит по умолчанию
    register: str                    # "formal" / "slang" / "rustic" / ...
    
    # Базовые характеристики речи
    sentence_length: str             # "short" / "medium" / "long"
    vocabulary_richness: float       # 0..1
    metaphor_density: float          # 0..1
    
    # Сопротивление дрейфу
    default_linguistic_integrity: float  # 0..1, базовое сопротивление
    class_factor: float = 1.0        # множитель для целевых классов
    
    # Свободное описание (для LLM)
    voice_profile: str               # "Говоришь тихо, короткими фразами..."
    
    # Канонические Expressions по умолчанию
    # (какие Concepts этот архетип использует по умолчанию, и какие expressions предпочитает)
    default_expressions: dict[str, str] = field(default_factory=dict)
    # {"guard_role": "стражник", "coin_currency": "золотой", ...}
```

```yaml
# config/canon/voice_archetypes/noble.yaml
archetype_id: noble
culture: capital
register: formal
sentence_length: long
vocabulary_richness: 0.9
metaphor_density: 0.6
default_linguistic_integrity: 0.95
class_factor: 1.0

voice_profile: |
  Говоришь размеренно, с паузами. Используешь деепричастные обороты,
  старорусские формы («сударь», «милостивый государь»). 
  Никогда не сокращаешь слова. Избегаешь прямых оскорблений — 
  предпочитаешь холодную иронию.

default_expressions:
  guard_role: "стражник"
  coin_currency: "золотой"
  greeting_formal: "покорно приветствую"
  address_inferior: "сударь"
  address_superior: "милостивый государь"
```

### 4.3. L1: MemeticTransmissionEvent

Расширение существующего `TraitDriftEvent`. Не отдельная сущность — новый `event_type` в `L1Chronicle`.

```python
# backend/app/domain/memetic/transmission_event.py — НОВЫЙ ФАЙЛ

@dataclass(frozen=True)
class MemeticTransmissionEvent:
    """Запись о передаче мема от source к target.
    
    Append-only. Хранится в history.db (memetic_transmission_events table).
    """
    event_id: int                    # auto-increment
    tick: int
    
    source_npc_id: str
    target_npc_id: str
    
    concept_id: str
    expression_text: str
    
    context: str                     # 'dialogue' / 'eavesdrop' / 'childhood' / 'burst' / 'teaching'
    interaction_type: str            # 'greeting' / 'insult' / 'storytelling' / ...
    
    # Вычисляется в момент передачи (см. §4.4)
    transmission_weight: float       # 0..1
    
    # Контекст состояния
    source_stress: float
    target_stress: float
    relationship_trust: float
    relationship_respect: float
    
    # Связь с burst (если передача произошла из-за burst-волны)
    burst_event_id: Optional[str] = None
```

### 4.4. Transmission weight — формула

Вес передачи = насколько сильно экспозиция повлияет на adoption. Базируется на Speech Accommodation Theory (Giles 1973).

```python
# backend/app/services/memetic/transmission_calculator.py — НОВЫЙ ФАЙЛ

class TransmissionCalculator:
    """Вычисляет transmission_weight для MemeticTransmissionEvent."""
    
    def calculate(
        self,
        source_npc_id: str,
        target_npc_id: str,
        context: str,
        relationship: RelationshipSnapshot,
        target_psyche: PsycheSnapshot,
        expression: Expression,
    ) -> float:
        """Возвращает 0..1."""
        
        # Базовый вес по контексту
        base = self._context_base_weight(context)
        # dialogue: 0.5, eavesdrop: 0.2, childhood: 0.9, burst: 0.7, teaching: 0.8
        
        # Speech Accommodation: если target уважает source — вес выше
        accommodation = 1.0 + relationship.respect * 0.5 + relationship.attraction * 0.3
        if relationship.trust < 0:
            # антипатия тормозит (но не обнуляет — можно перенять и у врага)
            accommodation *= max(0.1, 1.0 - abs(relationship.trust) * 0.5)
        
        # Психологическое состояние target
        stress_factor = 1.0 + target_psyche.stress * 0.5  # в стрессе впитывает быстрее
        
        # Сопротивление дрейфу (1 - linguistic_integrity)
        resistance = self._compute_resistance(target_psyche, expression)
        
        # Регистр: если expression register=slang, а target archetype=noble,
        # сопротивление выше
        register_factor = self._register_compatibility(
            target_psyche.voice_archetype.register,
            expression.register,
        )
        
        weight = base * accommodation * stress_factor * register_factor * (1.0 - resistance)
        return max(0.0, min(1.0, weight))
    
    def _compute_resistance(self, psyche: PsycheSnapshot, expression: Expression) -> float:
        """Сопротивление дрейфу. 0 = нет сопротивления, 1 = невозможно перенять."""
        # Формула из TZ_CONTENT_POLICY_FUNDAMENT.md §1.4
        # linguistic_integrity = willpower * class_factor * age_factor * identity_attachment
        # Возвращаем linguistic_integrity, но с modifier для типа expression
        base_integrity = psyche.linguistic_integrity  # 0..1
        
        # Междометия легче усваиваются (на 30%)
        if expression.register == "interjection":
            base_integrity *= 0.7
        # Прямые оскорбления труднее (на 50%)
        elif "profanity:heavy" in expression.category_tags:
            base_integrity = min(1.0, base_integrity * 1.5)
        
        return base_integrity
```

### 4.5. L1.5: MemeticAdoptionDetector

Аналог `PatternDetector`. Агрегует `MemeticTransmissionEvent` по `(target_npc_id, concept_id, expression_text)`:

```python
# backend/app/services/memetic/adoption_detector.py — НОВЫЙ ФАЙЛ

@dataclass(frozen=True)
class ExposureStats:
    """Статистика экспозиции NPC к конкретному Expression."""
    npc_id: str
    concept_id: str
    expression_text: str
    
    total_exposure_count: int           # сколько раз слышал
    total_weight: float                  # сумма всех transmission_weights
    avg_weight: float
    last_exposure_tick: int
    
    # Источники (топ-3)
    top_sources: list[tuple[str, float]]  # [(npc_id, total_weight), ...]
    
    # Контексты
    context_breakdown: dict[str, int]   # {"dialogue": 5, "eavesdrop": 2, ...}


class MemeticAdoptionDetector:
    """Агрегует MemeticTransmissionEvent в ExposureStats."""
    
    def compute_stats(
        self, npc_id: str, concept_id: str, expression_text: str,
        events: list[MemeticTransmissionEvent],
    ) -> ExposureStats:
        ...
```

### 4.6. L2.5: LexiconCrystallizationEngine (двухуровневая)

**Это ключевой сервис домена.** Он разделён на individual и community.

```python
# backend/app/services/memetic/lexicon_crystallization_engine.py — НОВЫЙ ФАЙЛ

class IndividualLexiconCrystallizer:
    """L2.5-individual: кристаллизует ExposureStats в Adoption.
    
    Аналог BeliefCrystallizationEngine, но для лексики.
    Использует ту же асимметрию (x6 trauma-множитель) — 
    если экспозиция произошла в травматическом контексте, 
    кристаллизация ускорена.
    """
    
    # Пороги кристаллизации по типу выражения
    CRYSTALLIZATION_THRESHOLDS = {
        "interjection": 0.3,      # "блядь" как междометие — легко
        "particle": 0.5,           # "нахуй" как усилитель
        "slang": 0.6,              # "железник" вместо "стражник"
        "epithet": 0.7,            # "синяя спина"
        "direct_insult": 0.8,      # "хуй" как обращение — графиня никогда
        "sexual_explicit": 1.0,    # только если NPC сам начал говорить об этом
        "taboo_practice": 1.5,     # почти невозможно без explicit cultural pressure
    }
    
    def try_crystallize(
        self, npc_id: str, expression: Expression, stats: ExposureStats,
        psyche: PsycheSnapshot,
    ) -> Optional[Adoption]:
        """Если совокупный вес превышает порог — создаёт Adoption."""
        
        threshold = self.CRYSTALLIZATION_THRESHOLDS.get(
            self._classify_expression(expression), 0.6
        )
        
        # Trauma multiplier (как в BeliefCrystallizationEngine)
        trauma_multiplier = 1.0
        if stats.has_traumatic_context:
            trauma_multiplier = 6.0
        
        effective_weight = stats.total_weight * trauma_multiplier
        
        if effective_weight < threshold:
            return None
        
        # Кристаллизация!
        return Adoption(
            npc_id=npc_id,
            concept_id=expression.concept_id,
            expression_text=expression.text,
            is_preferred=self._should_be_preferred(npc_id, expression, stats),
            confidence=min(1.0, effective_weight / (threshold * 2)),
            usage_count=0,
            adopted_tick=stats.last_exposure_tick,
            adopted_from_npc_id=stats.top_sources[0][0] if stats.top_sources else None,
            adopted_via="crystallization",
            last_used_tick=0,
            reinforcement_count=0,
        )
```

```python
# backend/app/services/memetic/community_norm_engine.py — НОВЫЙ ФАЙЛ

class CommunityNormEngine:
    """L2.5-community: вычисляет CulturalNorm из adoptions всех NPC в community.
    
    Запускается периодически (раз в N тиков), не на каждый тик.
    """
    
    COMPUTE_INTERVAL_TICKS = 100  # раз в 100 тиков
    
    def compute_norm(
        self, community_id: str, concept_id: str,
        all_adoptions: list[Adoption],
        community_members: list[str],  # npc_ids
    ) -> CulturalNorm:
        """Считает долю каждого expression среди preferred в community."""
        
        # Фильтруем adoptions по community_members
        relevant = [a for a in all_adoptions 
                    if a.npc_id in community_members 
                    and a.concept_id == concept_id
                    and a.is_preferred]
        
        if not relevant:
            # Нет preferred — берём любое known
            relevant = [a for a in all_adoptions 
                        if a.npc_id in community_members 
                        and a.concept_id == concept_id]
        
        if not relevant:
            return None  # норма не определена
        
        # Считаем доли
        counts: dict[str, int] = {}
        for a in relevant:
            counts[a.expression_text] = counts.get(a.expression_text, 0) + 1
        
        total = sum(counts.values())
        dominant = max(counts.items(), key=lambda x: x[1])
        
        return CulturalNorm(
            community_id=community_id,
            concept_id=concept_id,
            dominant_expression=dominant[0],
            dominance_share=dominant[1] / total,
            last_computed_tick=current_tick,
            history=[],  # обновится в persistence layer
        )
```

### 4.7. L3: ExpressionResolver

Финальный шаг — собрать **актуальный lexicon NPC** на лету. Это pure function, как `DriveResolver`.

```python
# backend/app/services/memetic/expression_resolver.py — НОВЫЙ ФАЙЛ

class ExpressionResolver:
    """L3: собирает SpeakerVocabulary для NPC на лету.
    
    Pure function: VoiceArchetype (L0) + Adoptions (L2.5-ind) + CulturalNorms (L2.5-comm)
    → SpeakerVocabulary (L3).
    """
    
    def resolve(
        self,
        npc_id: str,
        voice_archetype: VoiceArchetype,
        adoptions: list[Adoption],
        community_norms: list[CulturalNorm],
        content_policy: ContentPolicy,  # из fundament ТЗ
    ) -> SpeakerVocabularyBundle:
        """Возвращает все Concept-ы, которые NPC может выразить сейчас,
        с учётом ContentPolicy (потолок)."""
        
        bundle = SpeakerVocabularyBundle(npc_id=npc_id)
        
        # Для каждого Concept, который NPC знает
        all_concept_ids = set(a.concept_id for a in adoptions)
        # + concept_ids из voice_archetype.default_expressions
        
        for concept_id in all_concept_ids:
            # Собираем все adoptions по этому concept
            concept_adoptions = [a for a in adoptions if a.concept_id == concept_id]
            
            # + дефолт из archetype (если NPC ещё ничего не перенял)
            if not concept_adoptions and concept_id in voice_archetype.default_expressions:
                default_text = voice_archetype.default_expressions[concept_id]
                # Создаём виртуальную adoption
                concept_adoptions = [Adoption(
                    npc_id=npc_id, concept_id=concept_id,
                    expression_text=default_text,
                    is_preferred=True, confidence=1.0,
                    adopted_via="archetype_default",
                )]
            
            # Фильтруем по ContentPolicy
            filtered = []
            for a in concept_adoptions:
                expression = self._lookup_expression(concept_id, a.expression_text)
                if expression is None:
                    continue
                
                # Проверяем category_tags против content_policy
                if self._is_blocked_by_policy(expression, content_policy):
                    continue
                
                filtered.append((a, expression))
            
            if not filtered:
                continue
            
            # Выбираем preferred
            preferred = next((a for a, e in filtered if a.is_preferred), None)
            if preferred is None:
                # Берём с наибольшей confidence
                preferred = max(filtered, key=lambda x: x[0].confidence)[0]
            
            vocabulary = SpeakerVocabulary(
                npc_id=npc_id,
                concept_id=concept_id,
                preferred=preferred.expression_text,
                known=[a.expression_text for a, e in filtered],
            )
            bundle.add(concept_id, vocabulary)
        
        return bundle
    
    def _is_blocked_by_policy(
        self, expression: Expression, policy: ContentPolicy,
    ) -> bool:
        """Проверяет, заблокирован ли expression политикой контента."""
        for tag in expression.category_tags:
            if tag.startswith("profanity:"):
                level_required = int(tag.split(":")[1])  # 1 или 2
                if policy.profanity_level < level_required:
                    return True
            elif tag.startswith("sexual:"):
                level_required = int(tag.split(":")[1])
                if policy.sexual_content_level < level_required:
                    return True
            elif tag.startswith("violence:"):
                level_required = int(tag.split(":")[1])
                if policy.violence_level < level_required:
                    return True
            elif tag.startswith("taboo:"):
                level_required = int(tag.split(":")[1])
                if policy.taboo_practices_level < level_required:
                    return True
        return False
```

---

## 5. CULTURAL PRESSURE ACCUMULATOR

### 5.1. Принцип per-(event × community)

Каждое крупное событие в мире (спасение столицы, убийство короля, эпидемия) аккумулирует **культурное давление** — отдельно в каждой общности. Один и тот же Орм в столице → герой, в северной деревне, которую он случайно сжёг → проклятие.

### 5.2. Источники давления

Давление растёт от **пересказов**. Каждый раз, когда NPC в community рассказывает другому NPC о событии (через storytelling context в dialogue) — давление растёт.

```python
# backend/app/services/memetic/cultural_pressure_engine.py — НОВЫЙ ФАЙЛ

class CulturalPressureEngine:
    """Накапливает и затухает cultural pressure per-(event, community)."""
    
    DECAY_RATE = 0.001  # за тик, если нет новых пересказов
    
    def register_retelling(
        self, event_id: str, community_id: str,
        reteller_npc_id: str, listener_npc_id: str,
        emotional_intensity: float, tick: int,
    ) -> None:
        """NPC рассказал другому NPC о событии. Увеличивает pressure."""
        
        acc = self._load_or_create(event_id, community_id)
        
        # Notoriety: если listener ещё не знал — увеличиваем
        # (упрощённая модель: notoriety = max(notoriety, listener_knows))
        acc.notoriety = min(1.0, acc.notoriety + 0.05)
        
        # Retelling count
        acc.retelling_count += 1
        acc.last_retell_tick = tick
        
        # Emotional weight — берём максимум, не сумму
        # (одно очень эмоциональное пересказывание важнее десяти блёклых)
        acc.emotional_weight = max(acc.emotional_weight, emotional_intensity)
        
        # Faction alignment — определяется по community
        # (например, через community.alignment_to_event[event_id])
        # ... реализация ...
        
        # Пересчёт pressure_score
        acc.pressure_score = self._compute_pressure(acc)
        
        self._save(acc)
    
    def _compute_pressure(self, acc: CulturalPressureAccumulator) -> float:
        """Формула давления. 0..1."""
        # notoriety: 0..1
        # retelling_factor: log-scaled, насыщается
        retelling_factor = min(1.0, math.log(1 + acc.retelling_count) / math.log(50))
        # recency: 1.0 если только что, 0.0 если 10000 тиков назад
        ticks_since = current_tick - acc.last_retell_tick
        recency = math.exp(-ticks_since / 5000)  # экспоненциальное затухание
        # emotional weight: 0..1
        # alignment: |alignment| — важна интенсивность, не знак
        alignment_intensity = abs(acc.faction_alignment)
        
        # Взвешенная сумма
        score = (
            0.30 * acc.notoriety +
            0.25 * retelling_factor +
            0.20 * recency +
            0.15 * acc.emotional_weight +
            0.10 * alignment_intensity
        )
        return min(1.0, score)
    
    def decay_all(self, tick: int) -> None:
        """Периодический decay. Раз в 100 тиков."""
        # Уменьшает recency для всех аккумуляторов
        # Если pressure < 0.05 и last_retell_tick очень старый — можно удалить
        ...
```

### 5.3. Trigger conditions для Memetic Burst

```python
class MemeticBurstTrigger:
    """Решает, когда культурное давление достаточно для burst."""
    
    THRESHOLD = 0.75           # минимальный pressure_score
    COOLDOWN_TICKS = 500       # не чаще раза в 500 тиков на одно событие
    MIN_EMOTIONAL_WEIGHT = 0.4 # событие должно быть эмоционально насыщенным
    
    def should_trigger_burst(
        self, acc: CulturalPressureAccumulator, current_tick: int,
    ) -> bool:
        if acc.pressure_score < self.THRESHOLD:
            return False
        if acc.emotional_weight < self.MIN_EMOTIONAL_WEIGHT:
            return False
        if acc.last_burst_tick and current_tick - acc.last_burst_tick < self.COOLDOWN_TICKS:
            return False
        return True
```

---

## 6. MEMETIC BURST PIPELINE

### 6.1. Полный pipeline

```
1. CulturalPressureEngine регистрирует retelling
   ↓
2. MemeticBurstTrigger.should_trigger_burst(acc) = True
   ↓
3. MemeticBurstOrchestrator.start_burst(event, community)
   ↓
   ┌─────────────────────────────────────────────────┐
   │ 3a. Готовит контекст для LLM:                    │
   │     - событие (факты из L1Chronicle)             │
   │     - community (характеристики)                 │
   │     - alignment (позитив/негатив)                │
   │     - existing concepts (чтобы не дублировать)   │
   └─────────────────────────────────────────────────┘
   ↓
4. LLM call: "Предложи 10 культурных артефактов"
   (один вызов, узкий контракт)
   ↓
5. Validator: проверяет каждый артефакт
   ├── morphological (pymorphy3) — детерминированно
   ├── canonical (concept_id collision) — детерминированно
   ├── density cap (max N per type per event) — детерминированно
   └── epoch/style (LLM-judge, опционально) — не "можно/нельзя", 
       а "насколько естественно для эпохи"
   ↓
6. Принятые артефакты → ConceptRegistry (Canon, если автор одобрил) 
   или → TemporaryConceptStore (State, если auto-accept)
   ↓
7. Burst-волна: первые пересказы
   - creator_npc_id = наиболее уважаемый NPC в community
   - initial adoption с weight=0.7 (выше обычного)
   ↓
8. Дальше — обычная memetic transmission dynamics
   (конкуренция мутаций, adoption, crystallization, extinction)
```

### 6.2. LLM-контракт для burst

```python
# backend/app/services/memetic/burst_llm_contract.py — НОВЫЙ ФАЙЛ

MEMETIC_BURST_SYSTEM_PROMPT = """Ты — культуролог. Перед тобой историческое событие и общность, в которой это событие вызвало культурный резонанс.

Твоя задача: предложить 10 культурных артефактов, которые могли бы возникнуть в этой общности в результате данного события.

КАТЕГОРИИ АРТЕФАКТОВ (выбери разнообразные):
- имя (личное, ставшее популярным)
- прозвище (эпитет героя)
- название праздника
- название материала / предмета (eponym)
- идиома / поговорка
- ругательство (используя имя героя)
- благословение / проклятие
- название улицы / места
- детская считалка
- песня (только название)
- тост
- клятва

ФОРМАТ ОТВЕТА — JSON:
{
  "artifacts": [
    {
      "category": "holiday",
      "form": "Ормов день",
      "concept_referent": "Праздник в честь победы Орма над драконом",
      "concept_core_type": "EVENT",
      "concept_domain_types": ["HOLIDAY"],
      "register": "formal",
      "culture": "capital",
      "category_tags": ["heroic", "noble"],
      "rationale": "Ежегодный праздник в день битвы."
    },
    ...
  ]
}

ПРАВИЛА:
- Формы должны быть на русском языке, стилистически соответствовать эпохе.
- Не дублировать существующие в мире выражения (список ниже).
- Учитывай alignment: если событие для общности негативное, артефакты должны отражать это.
- Если событие для общности позитивное — celebratory tone.
- 10 артефактов, не больше, не меньше.
- Без объяснений, только JSON.
"""


class BurstLLMContractor:
    def build_user_prompt(
        self, event: ChronicleEvent, community: CommunitySnapshot,
        existing_concepts: list[Concept],
    ) -> str:
        return f"""СОБЫТИЕ:
{event.summary}
Эмоциональный вес: {event.emotional_weight}
Давность: {event.tick} тик назад

ОБЩНОСТЬ: {community.name}
Культура: {community.culture}
Alignment к событию: {community.alignment_to_event} (-1..1)

СУЩЕСТВУЮЩИЕ КОНЦЕПТЫ (не дублировать):
{self._format_existing(existing_concepts)}

Предложи 10 артефактов."""
```

### 6.3. Validator

```python
# backend/app/services/memetic/burst_validator.py — НОВЫЙ ФАЙЛ

class BurstArtifactValidator:
    """Четырёхуровневая валидация предложенных артефактов."""
    
    DENSITY_CAPS = {
        # Не более N артефактов одного type на одно событие
        "holiday": 1,
        "personal_name": 2,
        "epithet": 3,
        "idiom": 3,
        "street_name": 2,
        # ... и т.д.
    }
    
    def validate(
        self, artifacts: list[ProposedArtifact], event_id: str,
        existing_concepts: list[Concept],
    ) -> tuple[list[ValidatedArtifact], list[RejectionReason]]:
        accepted = []
        rejections = []
        
        # Подсчёт density для этого burst-а
        density_counter: dict[str, int] = {}
        
        for artifact in artifacts:
            reasons = []
            
            # 1. Морфология (детерминированно)
            if not self._check_morphology(artifact.form):
                reasons.append(RejectionReason(
                    artifact=artifact, level="morphology",
                    reason=f"Форма '{artifact.form}' не является валидным русским словом"
                ))
            
            # 2. Канон-консистентность (детерминированно)
            if self._conflicts_with_existing(artifact, existing_concepts):
                reasons.append(RejectionReason(
                    artifact=artifact, level="canonical",
                    reason=f"Конфликтует с существующим concept"
                ))
            
            # 3. Density cap (детерминированно)
            cap = self.DENSITY_CAPS.get(artifact.category, 5)
            if density_counter.get(artifact.category, 0) >= cap:
                reasons.append(RejectionReason(
                    artifact=artifact, level="density",
                    reason=f"Превышен cap {cap} для категории {artifact.category}"
                ))
            
            # 4. Epoch/style (LLM-judge, опционально)
            if self._llm_judge_enabled:
                score = self._llm_judge_epoch_style(artifact)
                if score < 0.5:
                    reasons.append(RejectionReason(
                        artifact=artifact, level="epoch_style",
                        reason=f"LLM-juge: не соответствует эпохе (score={score:.2f})"
                    ))
            
            if reasons:
                rejections.extend(reasons)
            else:
                density_counter[artifact.category] = density_counter.get(artifact.category, 0) + 1
                accepted.append(ValidatedArtifact(
                    artifact=artifact,
                    concept_id=self._generate_concept_id(artifact),
                ))
        
        return accepted, rejections
```

### 6.4. Конкуренция мутаций

Когда валидатор принял несколько Expressions для одного Concept (например, «Ормов день», «День Спасения», «День Железной Победы» — все для `holiday_orm_slaying`), они **конкурируют** за adoption. Нет «правильного» ответа — выживает то, что NPC реально используют.

Начальные условия:
- Каждое Expression получает initial adoption от своего `creator_npc_id` с weight=0.7.
- Дальше — обычная memetic transmission dynamics.

Через 1000 тиков система сама покажет, кто победил в community `capital`: «Ормов день» с долей 0.6, «День Спасения» с 0.3, «День Железной Победы» с 0.1. Через 5000 тиков — возможно, один из них extinct, другой стал нормой.

---

## 7. PLAYER-CREATED MEMES

### 7.1. Равенство с NPC

Игрок может создавать новые Concept и Expression наравне с NPC. Не через UI (это отдельная фича), а через обычные реплики в диалоге.

### 7.2. Detection

Когда игрок пишет реплику, `IntentCompressor` (или новый `PlayerExpressionDetector`) пытается найти в тексте:
- Неизвестные слова (не в lexicons, не в concept registry)
- Необычные использования известных слов (метафоры)

Если найдено — создаётся **candidate expression** для существующего или нового Concept.

### 7.3. Adoption backpressure

Player-created expressions получают **начальный transmission_weight = 0.1** (а не 0.5-0.7, как от уважаемого NPC). Это значит:

- Одно произнесение слова игроком почти ничего не меняет.
- Чтобы слово прижилось, игрок должен:
  - Произнести его несколько раз одному NPC (5-10 раз, в зависимости от resistance)
  - Или произнести в эмоционально насыщенном контексте (травма-множитель x6)
  - Или убедить уважаемого NPC повторить его (тогда NPC станет `source_npc_id` с нормальным weight)

### 7.4. Spam dampener

```python
class PlayerExpressionLimiter:
    """Не более 1 нового Expression от игрока на NPC за тик."""
    
    def should_record(
        self, player_id: str, target_npc_id: str, tick: int,
    ) -> bool:
        key = (player_id, target_npc_id, tick)
        if key in self._recent:
            return False
        self._recent.add(key)
        # Очистка старых ключей — раз в 100 тиков
        ...
        return True
```

### 7.5. Morphology gate

Player-created expressions проходят тот же morphology check, что и burst-артефакты. «Жлзник» от игрока отбрасывается.

### 7.6. Canon consistency

Новый Concept от игрока не может иметь `core_type`, конфликтующий с миром. Если игрок придумывает «драконью сталь» — Concept создаётся, потому что `steel_material` существует. Если игрок придумывает «звёздный крейсер» — Concept создаётся, но с `core_type=OBJECT` и пометкой `anachronistic: true`, что LLM-judge отбросит на валидации.

---

## 8. АНАЛИТИЧЕСКИЙ DRIFT ДЛЯ ПЕРЕМОТКИ ВРЕМЕНИ

### 8.1. Проблема

При перемотке времени (например, эпилог через 50 лет, или между кампаниями) нельзя пошагово симулировать 50 лет тиков. Согласно ADR-047 «No Retro-simulation», нужно аналитически вычислять `reconcile_state(elapsed_seconds)`.

### 8.2. Bass Diffusion Model

Для каждого Expression в каждой community применяется Bass Diffusion:

```
P(t) = adoption_share(t) = (1 - exp(-(p+q)*t)) / (1 + (q/p)*exp(-(p+q)*t))
```

Где:
- `p` = coefficient of innovation (внешнее влияние, например, через burst-волны)
- `q` = coefficient of imitation (внутреннее влияние, через NPC-to-NPC transmission)
- `t` = elapsed ticks

Коэффициенты берутся из текущего состояния:
- `p` = initial_adoption_share (от burst или player seed)
- `q` = avg_transmission_rate × community_density

### 8.3. Реализация

```python
# backend/app/services/memetic/analytical_drift.py — НОВЫЙ ФАЙЛ

class AnalyticalDriftEngine:
    """Аналитический расчёт linguistic drift за прошедшее время.
    
    Используется в SceneInit при загрузке сохранения с большим elapsed_time,
    или в Epilogue engine, или в cross-campaign migration.
    """
    
    def reconcile(
        self, community_id: str, elapsed_ticks: int,
        current_state: CommunityMemeticState,
    ) -> CommunityMemeticState:
        """Применяет Bass diffusion ко всем competing expressions."""
        
        for concept_id, expressions in current_state.competing_expressions.items():
            # Группируем по concept_id
            total_share = sum(e.share for e in expressions)
            if total_share < 0.01:
                continue  # ничего не прижилось, пропускаем
            
            # Для каждого expression применяем Bass
            for expr in expressions:
                p = expr.innovation_coefficient  # малая, если не было burst
                q = expr.imitation_coefficient    # зависит от community
                
                # Финальная доля
                final_share = self._bass_diffusion(
                    p, q, elapsed_ticks, initial_share=expr.share
                )
                
                expr.share = final_share
            
            # Нормализуем shares (чтобы сумма = 1.0)
            total = sum(e.share for e in expressions)
            for e in expressions:
                e.share /= total if total > 0 else 1
            
            # Помечаем extinct тех, у кого share < 0.05
            for e in expressions:
                if e.share < 0.05:
                    e.is_extinct = True
        
        return current_state
    
    def _bass_diffusion(
        self, p: float, q: float, t: int, initial_share: float,
    ) -> float:
        """Bass model. Возвращает финальную долю."""
        # Стандартная формула
        denom = 1 + (q / p) * math.exp(-(p + q) * t)
        bass_share = (1 - math.exp(-(p + q) * t)) / denom
        # Комбинируем с initial_share
        return max(initial_share, bass_share)
```

### 8.4. Honesty contract

Аналитический drift **не претендует на правду каждого слова** — он претендует на **правдоподобие распределения**. Если игрок после time-skip видит, что «Ормов день» стал доминирующим, а «День Спасения» вымер — это правдоподобный исход конкуренции мутаций. Но это **не значит**, что именно так всё и было — это аналитическая аппроксимация.

Это явно фиксируется в `MemeticBurstLog`: если состояние было получено через analytical drift, в логе пишется `reconciliation_source: analytical_bass_v1`.

---

## 9. СВЯЗЬ С СУЩЕСТВУЮЩИМ `insults_ru.json`

### 9.1. Двойная роль

`backend/data/insults_ru.json` сейчас используется **только one-way** — для детекции оскорблений игрока в `dm_router.py`. В memetic-системе он получает вторую роль: **словарь корней для profanity category_tags**.

### 9.2. Миграция

Не нужно переписывать `insults_ru.json`. Каждое слово в нём автоматически становится **Expression** для специального Concept `profanity_root_<word>` с `core_type=LANGUAGE`, `domain_type=OATH` (или `EPITHET`), `category_tags=["profanity:heavy"]`.

Это делается лениво: при первом упоминании слова в `MemeticTransmissionEvent` система проверяет, есть ли уже Concept для него. Если нет — создаёт через `ProfanityConceptFactory`.

```python
# backend/app/services/memetic/profanity_concept_factory.py — НОВЫЙ ФАЙЛ

class ProfanityConceptFactory:
    """Создаёт Concept + Expression для матерного слова из insults_ru.json."""
    
    def get_or_create(self, word: str) -> tuple[str, str]:
        """Возвращает (concept_id, expression_text)."""
        concept_id = f"profanity_root_{word}"
        # Проверяем, есть ли уже в реестре
        if self._registry.has(concept_id):
            return concept_id, word
        
        # Создаём
        concept = Concept(
            concept_id=concept_id,
            referent=f"Матерное слово: {word}",
            core_type=CoreType.LANGUAGE,
            domain_types=("OATH",),  # или EPITHET, в зависимости от контекста
            domain="profanity",
            created_tick=0,
            origin_npc_id=None,
            description=f"Auto-generated from insults_ru.json",
        )
        expression = Expression(
            text=word,
            register="profane",
            culture="common",
            probability=0.0,  # не используется как default
            category_tags=("profanity:heavy", "vulgar"),
            creator_npc_id=None,
            created_tick=0,
        )
        concept = replace(concept, aliases=(expression,))
        self._registry.register(concept)
        return concept_id, word
```

---

## 10. ТЕСТЫ ПРИНЯТИЯ

### 10.1. Онтология

```python
def test_concept_can_have_multiple_expressions():
    """Concept 'guard_role' имеет 5 expressions."""

def test_expression_always_belongs_to_concept():
    """Expression не может существовать без Concept."""

def test_core_type_closed_list():
    """CoreType enum содержит ровно 16 значений."""

def test_domain_type_requires_parent():
    """DomainType без parent_ids → ValueError."""

def test_multiple_inheritance_works():
    """TABOO_PRACTICE имеет parents (RITUAL, SOCIAL) — оба валидны."""

def test_tags_do_not_affect_ontology():
    """Удаление всех tags с expression не ломает систему."""
```

### 10.2. Persistence

```python
def test_canon_files_are_yaml():
    """config/canon/concepts/*.yaml — валидный YAML."""

def test_history_db_append_only():
    """MemeticTransmissionEvent нельзя UPDATE."""

def test_state_db_mutable():
    """npc_adoptions можно UPDATE."""

def test_migration_from_old_save_creates_canon():
    """При загрузке старого сохранения без memetic-данных 
    создаётся пустой Canon с дефолтными Concept-ами."""
```

### 10.3. Transmission

```python
def test_transmission_weight_respects_respect():
    """Если target уважает source — weight выше."""

def test_transmission_weight_zero_when_resistance_max():
    """linguistic_integrity=1.0 → weight=0."""

def test_interjection_easier_to_adopt_than_direct_insult():
    """Междометие кристаллизуется при weight=0.3, 
    direct_insult — при weight=0.8."""

def test_trauma_multiplier_x6():
    """ExposureStats с traumatic_context кристаллизуется в 6 раз быстрее."""
```

### 10.4. Crystallization

```python
def test_individual_crystallization_creates_adoption():
    """После достаточной экспозиции создаётся Adoption в state.db."""

def test_community_norm_computed_periodically():
    """CulturalNorm пересчитывается раз в 100 тиков."""

def test_preferred_expression_updated_on_higher_confidence():
    """Если NPC перенял новое expression с confidence > 0.8, 
    оно становится preferred."""
```

### 10.5. Cultural Pressure

```python
def test_pressure_per_event_per_community():
    """Один event в двух communities — два разных accumulator."""

def test_pressure_decay_over_time():
    """Без новых retelling, pressure падает."""

def test_burst_trigger_respects_cooldown():
    """После burst-а следующий не раньше 500 тиков."""
```

### 10.6. Burst

```python
def test_burst_validates_morphology():
    """«Жлзник» отбрасывается на morphology check."""

def test_burst_validates_canonical_conflict():
    """Нельзя создать concept_id, уже существующий."""

def test_burst_density_cap_blocks_excess_holidays():
    """Второй 'holiday' для одного event — rejected."""

def test_burst_competition_3_expressions_for_one_concept():
    """3 выражения для 'holiday_orm_slaying' — все приняты, 
    дальше конкурируют через adoption."""

def test_burst_llm_contract_returns_json():
    """LLM возвращает валидный JSON с 10 артефактами."""
```

### 10.7. Player memes

```python
def test_player_expression_initial_weight_0_1():
    """Player-created expression получает weight=0.1, не 0.7."""

def test_player_spam_dampener_blocks_duplicates():
    """Второе новое слово от игрока тому же NPC в том же тике — 
    не записывается."""

def test_player_morphology_gate_rejects_garbage():
    """'Жлзник' от игрока не создаёт Concept."""
```

### 10.8. Analytical drift

```python
def test_bass_diffusion_monotonic():
    """P(t) монотонно возрастает по t."""

def test_analytical_drift_marks_low_share_extinct():
    """Expression с share < 0.05 после drift → is_extinct=True."""

def test_reconciliation_logged():
    """В memetic_burst_log пишется reconciliation_source."""
```

### 10.9. End-to-end scenarios

```python
def test_thief_word_spreads_to_lusya_over_500_ticks():
    """Тень говорит 'железник' 100 раз за 500 тиков.
    Люся (linguistic_integrity=0.35) усваивает через ~30 экспозиций."""

def test_noble_never_adopts_heavy_profanity():
    """Графиня с integrity=0.95 не усваивает 'ебанутый' 
    даже после 1000 экспозиций."""

def test_orm_slaying_creates_holiday_after_500_ticks():
    """Орм спасает столицу → через ~500 тиков и 50 retelling 
    срабатывает burst → создаётся Concept holiday_orm_slaying."""

def test_after_50_year_timeskip_one_expression_dominates():
    """После analytical drift один из 3 конкурирующих expressions 
    имеет share > 0.7, остальные extinct."""

def test_player_creates_word_npc_repeats_it_word_spreads():
    """Игрок придумывает 'свинорез' → NPC повторяет (вес 0.5) → 
    другие NPC начинают использовать → через 1000 тиков 
    'свинорез' — норма в community."""
```

---

## 11. КРИТЕРИИ ПРИНЯТИЯ

| # | Критерий | Как проверить |
|---|---|---|
| AC-1 | Все 16 CoreTypes определены | `CoreType.__members__` |
| AC-2 | Domain Types регистрируются с parent | `test_domain_type_requires_parent` |
| AC-3 | Concept хранится в YAML, Expression внутри Concept | Чтение `config/canon/concepts/guard_role.yaml` |
| AC-4 | MemeticTransmissionEvent append-only в SQLite | `test_history_db_append_only` |
| AC-5 | Adoption mutable в SQLite | `test_state_db_mutable` |
| AC-6 | Transmission weight учитывает relationship | `test_transmission_weight_respects_respect` |
| AC-7 | Crystallization thresholds зависят от типа expression | `test_interjection_easier_to_adopt_than_direct_insult` |
| AC-8 | CulturalNorm вычисляется per-community | `test_community_norm_computed_periodically` |
| AC-9 | Cultural pressure per-(event, community) | `test_pressure_per_event_per_community` |
| AC-10 | Burst trigger соблюдает threshold + cooldown | `test_burst_trigger_respects_cooldown` |
| AC-11 | Burst validator отбрасывает morphology fail | `test_burst_validates_morphology` |
| AC-12 | Burst создаёт competing expressions | `test_burst_competition_3_expressions_for_one_concept` |
| AC-13 | Player expressions получают weight=0.1 | `test_player_expression_initial_weight_0_1` |
| AC-14 | Spam dampener блокирует дубли | `test_player_spam_dampener_blocks_duplicates` |
| AC-15 | Analytical drift помечает extinct | `test_analytical_drift_marks_low_share_extinct` |
| AC-16 | ExpressionResolver фильтрует по ContentPolicy | Интеграция с TZ_CONTENT_POLICY_FUNDAMENT AC-8 |
| AC-17 | Существующий `insults_ru.json` переиспользуется | `ProfanityConceptFactory` создаёт Concept-ы из roots |
| AC-18 | Графиня не матерится даже при 1000 экспозиций | `test_noble_never_adopts_heavy_profanity` |

---

## 12. ПЛАН РЕАЛИЗАЦИИ

### Phase 1: Онтология и Canon (1 неделя)

1. Создать `backend/app/domain/memetic/` package
2. Реализовать `CoreType`, `DomainType`, `Concept`, `Expression`
3. Создать `config/canon/concepts/` с 20 базовыми Concept-ами (guard_role, blacksmith_role, coin_currency, и т.д.)
4. Создать `config/canon/domain_types.yaml` с 16 стандартными Domain Types
5. Создать `config/canon/voice_archetypes/` с 6 архетипами (noble, thief, maid, merchant, blacksmith, guard)
6. Реализовать `ConceptRegistry` (in-memory cache + lazy load)
7. Написать тесты онтологии (раздел 10.1)

### Phase 2: Persistence (3-4 дня)

1. Создать SQLite-схемы: `memetic_transmission_events`, `npc_adoptions`, `cultural_norms`, `cultural_pressure_accumulators`, `memetic_burst_log`
2. Реализовать `MemeticPersistenceAdapter` (по аналогии с `SqlitePersistenceAdapter`)
3. Реализовать миграцию (создание пустых таблиц при первом запуске)
4. Написать тесты persistence (раздел 10.2)

### Phase 3: Transmission pipeline (1 неделя)

1. Реализовать `MemeticTransmissionEvent` (расширение `TraitDriftEvent`)
2. Реализовать `TransmissionCalculator` (формула из §4.4)
3. Реализовать `MemeticAdoptionDetector` (L1.5)
4. Реализовать `IndividualLexiconCrystallizer` (L2.5-ind)
5. Реализовать `CommunityNormEngine` (L2.5-comm)
6. Реализовать `ExpressionResolver` (L3)
7. Интегрировать в `tick_orchestrator.py` (новая фаза: memetic_transmission)
8. Написать тесты transmission и crystallization (разделы 10.3, 10.4)

### Phase 4: Cultural Pressure и Burst (1 неделя)

1. Реализовать `CulturalPressureEngine`
2. Реализовать `MemeticBurstTrigger`
3. Реализовать `BurstLLMContractor`
4. Реализовать `BurstArtifactValidator` (4 уровня)
5. Реализовать `MemeticBurstOrchestrator`
6. Реализовать конкуренцию мутаций (через существующий adoption pipeline)
7. Написать тесты pressure и burst (разделы 10.5, 10.6)

### Phase 5: Player memes и analytical drift (4-5 дней)

1. Реализовать `PlayerExpressionDetector` (интеграция в `dm_router.py`)
2. Реализовать `PlayerExpressionLimiter` (spam dampener)
3. Реализовать `AnalyticalDriftEngine` (Bass diffusion)
4. Интегрировать в `SceneInit` (при загрузке сохранения с elapsed_time)
5. Написать тесты player memes и analytical drift (разделы 10.7, 10.8)

### Phase 6: Integration и cleanup (3-4 дня)

1. End-to-end тесты (раздел 10.9)
2. Интеграция с `DMContractBuilder` (через `ExpressionResolver` — см. TZ-MEMETIC-02)
3. Интеграция с `ResponseValidator` (через `category_tags` — см. TZ-MEMETIC-02)
4. `ProfanityConceptFactory` — миграция `insults_ru.json` в Concept-ы
5. Обновить `architecture/identity.yaml` — добавить MEMETIC поддомен
6. Обновить `docs/ADR (Architecture Decision Records).md` с ADR-O-MEMETIC-001

**Итого**: 5-6 недель на полную реализацию домена.

---

## 13. ADR-O-MEMETIC-001: MEMETIC TRANSMISSION DOMAIN

### Decision

В ENIGMA вводится домен MEMETIC_TRANSMISSION как расширение домена IDENTITY. Единицей эволюции является **мем** — культурная единица любого типа (слово, имя, ритуал, жест, и т.д.), проходящая через жизненный цикл CONCEPT → EXPRESSION → SPREAD → CRYSTALLIZATION → EXTINCTION.

### Rationale

Текущая модель `TraitDriftEvent` + `BeliefCrystallizationEngine` описывает эволюцию **черт характера**. Однако язык и культура эволюционируют по тем же законам (Dawkins, Sperber, Boyd-Richerson), но требуют другой онтологии:
- Единица — не скалярная черта, а культурный объект с формой и смыслом.
- Кристаллизация двухуровневая: individual adoption + community norm.
- Поддержка времени: аналитический drift для time-skip (Bass diffusion).

### Consequences

- Все культурные единицы хранятся в едином реестре Concept-ов.
- LLM не создаёт законы культуры — она лишь предлагает формы для детерминированно-триггернутых bursts.
- Per-NPC linguistic integrity (введённая TZ_CONTENT_POLICY_FUNDAMENT как stub) активируется и вычисляется.
- Существующий `insults_ru.json` переиспользуется как source для profanity Concept-ов.
- Аналитический drift честно помечается в логах (не претендует на пошаговую правду).

### Taboo

- ❌ LLM как источник истины для создания Concept (LLM — только автор формы)
- ❌ Pошаговая симуляция для time-skip (использовать analytical drift)
- ❌ Хранение Concept в SQLite (Canon должен быть в YAML/JSON)
- ❌ Смешивание individual и community кристаллизации в одной таблице
- ❌ Удаление extinct expressions из Canon (помечать, не удалять)

---

## 14. РИСКИ И АЛЬТЕРНАТИВЫ

### 14.1. Риск: LLM галлюцинирует невалидные Concept-ы в burst

**Проблема**: LLM в burst может предложить «интернет» или «квантовый компьютер» для средневекового сеттинга.
**Митигация**: 4-уровневый валидатор, особенно LLM-judge для epoch/style. Плюс canonical check: если `concept_core_type=OBJECT` и `domain_type=TECHNOLOGY`, но в каноне нет технологий — reject.

### 14.2. Риск: Performance при большом количестве NPC

**Проблема**: 1000 NPC × 100 Concept-ов × 5 Expressions = 500k adoptions. SQL-запросы на каждый тик могут быть медленными.
**Митигация**: 
- `tier=minor` NPC не трекают adoptions — используют только VoiceArchetype defaults.
- LRU-кэш на `SpeakerVocabulary` (как в `RelationshipStore`).
- `CommunityNormEngine` запускается раз в 100 тиков, не на каждый.

### 14.3. Риск: Analytical drift расходится с пошаговой симуляцией

**Проблема**: Если игрок сохраняется, перематывает 50 лет, потом откатывается — состояние может не совпадать.
**Митигация**: Честное логирование `reconciliation_source`. Если игрок хочет «настоящую» симуляцию — должен играть без time-skip.

### 14.4. Альтернатива: LLM генерирует легенды напрямую

**Идея**: вместо memetic burst pipeline просто просить LLM «придумай легенду об Орме».
**Почему отклонено**: 
- Нарушает принцип «LLM — голос, не источник истины».
- Недетерминированно — разные запуски дают разные результаты.
- Не масштабируется — каждый legend = один LLM-вызов, без конкуренции мутаций.
- Не эволюционирует — легенда не меняется со временем.

### 14.5. Альтернатива: Полностью детерминированный burst (без LLM)

**Идея**: burst генерирует выражения по шаблонам (epithet = name + suffix, holiday = «День » + name).
**Почему отклонено**: 
- Скучно — все легенды будут одинаковыми по форме.
- Не использует потенциал LLM для языкового разнообразия.
- Не сможет генерировать идиомы, поговорки, считалки.

LLM в burst — это **правильный** компромисс: детерминированная система решает, **когда** породить мем, LLM предлагает **как**, валидатор проверяет **насколько это валидно**, adoption dynamics решает **что выживет**.

---

## 15. СВЯЗЬ С БУДУЩИМИ ТЗ

Это ТЗ — **доменный спецификация**. Оно описывает, **что** строится. Конкретные точки интеграции с существующим кодом описаны в `TZ-MEMETIC-02` (Content Policy Integration) и `TZ-MEMETIC-03` (Patch List).

**Когда `TZ-MEMETIC-02` будет реализован:**
- `ContentProfile.from_npc_state(npc, global_policy)` начнёт учитывать adopted expressions.
- `ResponseValidator` начнёт фильтровать не по словарям, а по `category_tags` Expressions.
- `DMContractBuilder` начнёт использовать `SpeakerVocabulary` (preferred + known) вместо голого `voice_profile`.

**Когда `TZ-MEMETIC-03` будет реализован:**
- Конкретные 12 точек изменения в существующем коде, с patch-примерами.

---

## 16. ИТОГ

Это ТЗ вводит **домен MEMETIC_TRANSMISSION** — онтологию культурной эволюции, в которой:

1. **Единица** — мем (Concept + Expression), не слово.
2. **Эволюция** — через adoption dynamics, не через скрипты.
3. **LLM** — автор языковых форм, не источник истины.
4. **Масштабирование** — через VoiceArchetype (L0) + community norms (L2.5-comm) + analytical drift.
5. **Дети** — наследуют community norms, а не настройки родителей.
6. **Игрок** — равен NPC в создании мемов, но с adoption backpressure.
7. **Конкуренция** — мутации борются за adoption, выживает то, что используется.
8. **Время** — пошагово для краткосрочного, аналитически для долгосрочного.

После реализации этого ТЗ ENIGMA получит **первую в истории игровую симуляцию культурной эволюции** — где через 200 игровых лет рождается настоящий культурный дрейф, с новыми именами, праздниками, поговорками и ругательствами, которые **никто не прописывал вручную**.

---

**Конец документа.**
