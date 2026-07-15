# ТЗ: ФУНДАМЕНТ СИСТЕМЫ УПРАВЛЕНИЯ КОНТЕНТОМ (Content Policy Fundament)

> **Проект:** ENIGMA / The Fool
> **Версия ТЗ:** 1.0
> **Статус:** PROPOSED — готов к реализации
> **Дата:** 2026-07-03
> **Зависимости:** нет (документ самодостаточный)
> **Связанные документы:** `TZ_ustanovochnik_ENIGMA_Dopolnenie_A.docx` §А.6; будущие `TZ-MEMETIC-01/02/03`
> **Критичность:** P1 — обязательный фундамент для релиза 1.0
> **Архитектурный принцип:** ADR-O-MEMETIC-000 (вводится этим ТЗ)

---

## 0. НАЗНАЧЕНИЕ И СКОУП

### 0.1. Цель

Ввести в игру **единый механизм управления 18+ контентом**, который:

1. Игрок может переключать одним кликом в настройках.
2. Является **глобальным потолком** для всех будущих контентных систем (мат, секс, насилие, табу-практики).
3. Не зависит от выполнения остальных ТЗ меметической системы — может быть реализован и работать **уже сейчас**, на текущем `voice_profile` NPC.
4. Готов к бесшовной интеграции с будущим `MEMETIC_TRANSMISSION` доменом без переписывания.

Этот документ описывает **минимальный самодостаточный фундамент**: данные, persistence, UI, точки интеграции с существующим кодом, тесты принятия.

### 0.2. Что входит в scope этого ТЗ

| Входит | Не входит |
|---|---|
| Структура `ContentPolicy` (глобальная) | Per-NPC профили цензуры (отдельное ТЗ) |
| Расширение stub `ContentProfile` до рабочего состояния | Memetic Transmission engine (отдельное ТЗ) |
| Persistence в `user_settings.yaml` | LLM-генерация новых мемов |
| UI: вкладка «Контент» в settings screen | Конкуренция мутаций, adoption dynamics |
| Интеграция с `DMContractBuilder` | Cultural Pressure Accumulator |
| Пост-фильтр в `ResponseValidator` | Per-NPC linguistic integrity |
| Миграция с `hardcore_mode` на новую модель | System-generated Concept/Expression |
| B-plan: LLM переформулирование | Burst pipeline |

### 0.3. Почему это вводится первым

Текущее состояние (по расследованию кодовой базы V.0.5.3.3.3):

- Глобальный флаг `hardcore_mode: bool = True` в `config.py:69` — влияет **только** на инъекцию `author_notes` в DM-промпт.
- Stub `ContentProfile` в `verbalization_context.py:21-31` — определён, **никем не читается**.
- `DM_SYSTEM_PROMPT_HARDCORE` в `dm_contract_builder.py:39-44` — определён, **не используется** (перекрыт внешним `dm_system.txt`).
- `insults_ru.json` (~200 матерных корней) — используется **только one-way** для детекции оскорблений игрока.
- Кнопка `MenuAction.SETTINGS` — заглушка `pass`.
- В ТЗ установочника (Дополнение А §А.6.1) — 4 вкладки настроек, **цензуры нет вообще**.

Это значит, что **сегодня невозможно** дать игроку выбор «играть с матом или без». NPC матерятся или не матерятся в зависимости от того, что LLM решит на основе `voice_profile`, без какой-либо enforcement. Этот ТЗ закрывает базовую потребность.

---

## 1. АРХИТЕКТУРНЫЕ ПРИНЦИПЫ

### 1.1. Принцип потолка, а не предписания

`ContentPolicy` — это **верхняя граница разрешённого контента**, установленная игроком. Она не заставляет NPC материться, если `policy.level=2`; она лишь **разрешает** им это делать, если это свойственно персонажу. Это различие критично: когда в будущем появится per-NPC `profanity_level` (через memetic adoption),effective_profanity будет вычисляться как:

```
effective_profanity(npc, moment) = min(
    global_policy.profanity_level,      # потолок игрока
    npc.linguistic_state.profanity,     # что свойственно NPC сейчас
    situation_gate(npc.stress, npc.relationship_with_player)
)
```

В рамках текущего ТЗ `npc.linguistic_state.profanity` принимается равным `global_policy.profanity_level` (то есть потолок = факту), потому что per-NPC система ещё не построена. Когда memetic-домен будет готов, формула просто начнёт учитывать второй аргумент — без изменения интерфейса `ContentPolicy`.

### 1.2. Принцип одного тумблера для игрока, трёх осей для системы

Игрок видит один переключатель с тремя положениями: **«Выключено» / «Умеренно» / «Без ограничений»**. Это сделано осознанно — средний игрок не должен разбираться в типах контента. Под капотом этот тумблер отображается на **четырёх независимые оси**:

| Ось | Что контролирует |
|---|---|
| `profanity_level` | Мат, ругань, грубая лексика |
| `sexual_content_level` | Сексуальные сцены, эротика, намёки |
| `violence_level` | Жестокость, детальность описания травм |
| `taboo_practices_level` | Каннибализм, некрофилия, инцест, сатанизм (для будущих кампаний) |

Каждая ось — int 0..2. Каннибализм отделён от насилия, потому что экспозиция к мату и экспозиция к каннибализму — это разные потоки культурной трансляции, и в будущей memetic-системе они будут кристаллизоваться независимо.

### 1.3. Принцип детерминированной фильтрации, LLM — только переформулирование

Решение «этот ответ LLM нарушает ContentPolicy» принимается **детерминированно**, через словарь `insults_ru.json` (расширенный до sexual/violence/taboo корней) и простую лемматизацию через `pymorphy3`. LLM не участвует в решении «можно/нельзя» — это сделало бы систему недетерминированной и дорогостоящей.

LLM вызывается **только** в fallback-режиме (B-plan): когда валидатор обнаружил нарушение и `npc.tier == "major"`, LLM получает узкий контракт «переформулируй ту же мысль мягче». Для minor NPC fallback — silent replacement на заранее написанную фразу. Это удерживает latency в приемлемых рамках.

### 1.4. Принцип подготовленности к Memetic Transmission

Все структуры данных, вводимые этим ТЗ, спроектированы так, чтобы будущий `MEMETIC_TRANSMISSION` домен подключался **без schema migration**. Конкретно:

- `ContentProfile` уже имеет 4 оси, под которые в будущем лягут `category_tags` выражений.
- `NPCProfileL0` получает stub-поле `voice_archetype_id` (пока не используется, но резервирует место).
- `PsycheBase` получает stub-поле `linguistic_integrity: float` (пока всегда 1.0, но резервирует место).
- Persistence-слой `user_settings.yaml` спроектирован под трёхслойную онтологию Canon/History/State (см. §4).

---

## 2. МОДЕЛЬ ДАННЫХ

### 2.1. Глобальная политика контента (`ContentPolicy`)

```python
# backend/app/core/content_policy.py — НОВЫЙ ФАЙЛ

from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
from typing import Literal


class ContentLevel(IntEnum):
    """Уровень разрешённого контента по одной оси."""
    OFF = 0          # Полный запрет
    MODERATE = 1     # Лёгкие формы, намёки, эвфемизмы
    EXPLICIT = 2     # Полный контент без ограничений


@dataclass(frozen=True)
class ContentPolicy:
    """Глобальная политика контента. Один экземпляр на игру.
    
    Загружается из user_settings.yaml при старте сессии.
    Неизменна в течение тика — изменение требует restart сессии 
    или явного reload через Settings screen.
    """
    profanity_level: ContentLevel = ContentLevel.OFF
    sexual_content_level: ContentLevel = ContentLevel.OFF
    violence_level: ContentLevel = ContentLevel.MODERATE
    taboo_practices_level: ContentLevel = ContentLevel.OFF
    
    # Пресеты для UI тумблера
    @classmethod
    def preset_off(cls) -> "ContentPolicy":
        """Выключено — для чувствительной аудитории."""
        return cls(
            profanity_level=ContentLevel.OFF,
            sexual_content_level=ContentLevel.OFF,
            violence_level=ContentLevel.OFF,
            taboo_practices_level=ContentLevel.OFF,
        )
    
    @classmethod
    def preset_moderate(cls) -> "ContentPolicy":
        """Умеренно — лёгкая ругань, намёки, физиологичное насилие."""
        return cls(
            profanity_level=ContentLevel.MODERATE,
            sexual_content_level=ContentLevel.MODERATE,
            violence_level=ContentLevel.MODERATE,
            taboo_practices_level=ContentLevel.OFF,
        )
    
    @classmethod
    def preset_explicit(cls) -> "ContentPolicy":
        """Без ограничений — полный 18+ контент."""
        return cls(
            profanity_level=ContentLevel.EXPLICIT,
            sexual_content_level=ContentLevel.EXPLICIT,
            violence_level=ContentLevel.EXPLICIT,
            taboo_practices_level=ContentLevel.EXPLICIT,
        )
    
    # Deprecated alias — для обратной совместимости
    @property
    def hardcore_mode(self) -> bool:
        """ADR-O-MEMETIC-000 §6: deprecated alias.
        
        True, если хотя бы одна ось = EXPLICIT.
        Используется только в dm_agent.py:124 до полного перехода.
        """
        return any(
            level == ContentLevel.EXPLICIT 
            for level in [
                self.profanity_level,
                self.sexual_content_level,
                self.violence_level,
                self.taboo_practices_level,
            ]
        )
```

### 2.2. Per-NPC профиль контента (расширение stub)

Существующий `ContentProfile` в `verbalization_context.py:21-31` **расширяется** до рабочего состояния. В рамках этого ТЗ он используется **только как pass-through** для глобальной политики — но структура готова к будущему per-NPC заполнению через memetic adoption.

```python
# backend/app/services/verbalization/verbalization_context.py — РАСШИРЕНИЕ

@dataclass(frozen=True)
class ContentProfile:
    """Профиль разрешённого контента для вербализации конкретного NPC.
    
    В текущем ТЗ (fundament): все поля = глобальной политике.
    В будущем (memetic): per-NPC значения, вычисленные из 
    adopted expressions и linguistic integrity.
    """
    profanity_level: int = 0      # 0..2, см ContentLevel
    sexual_content_level: int = 0
    violence_level: int = 0
    taboo_practices_level: int = 0
    
    # Резерв для memetic-системы (пока всегда None)
    adopted_profanity_words: tuple[str, ...] = ()  # ID кристаллизованных мата
    adopted_sexual_words: tuple[str, ...] = ()
    
    def __post_init__(self) -> None:
        for field_name in ("profanity_level", "sexual_content_level", 
                           "violence_level", "taboo_practices_level"):
            val = getattr(self, field_name)
            if not (0 <= val <= 2):
                raise ValueError(
                    f"{field_name} должен быть 0-2, получено: {val}"
                )
    
    @classmethod
    def from_global_policy(cls, policy: "ContentPolicy") -> "ContentProfile":
        """Фабрика: создаёт профиль из глобальной политики.
        
        Это единственный способ создания ContentProfile в рамках fundament ТЗ.
        Memetic ТЗ добавит фабрику from_npc_state().
        """
        return cls(
            profanity_level=int(policy.profanity_level),
            sexual_content_level=int(policy.sexual_content_level),
            violence_level=int(policy.violence_level),
            taboo_practices_level=int(policy.taboo_practices_level),
        )
```

### 2.3. Stub-поля для будущей memetic-интеграции

В `NPCProfileL0` и `PsycheBase` добавляются **stub-поля**, которые сейчас всегда равны значениям по умолчанию, но резервируют схему:

```python
# backend/app/models/npc_profile.py — РАСШИРЕНИЕ

@dataclass(frozen=True)
class NPCProfileL0:
    id: str
    name: str
    tier: str
    drives_base: Dict[str, float]
    psyche_base: PsycheBase
    voice_profile: str
    backstory: str = ""
    author_notes: str = ""
    inventory_rules: Optional[InventoryProfile] = None
    gender: str = "male"
    archetype: str = "commoner"
    
    # НОВЫЕ STUB-ПОЛЯ (TZ-CONTENT-POLICY-FUNDAMENT)
    voice_archetype_id: Optional[str] = None  
    """ID архетипа голоса в config/canon/voice_archetypes/*.yaml.
    Пока не используется (None = default). Memetic ТЗ заполнит."""
```

```python
# backend/app/domain/vital_state.py или эквивалент — PsycheBase

@dataclass(frozen=True)
class PsycheBase:
    willpower: int          # 0..100, существует
    breakpoint: int         # 0..100, существует
    loyalty_true: float     # -1..1, существует
    
    # НОВОЕ STUB-ПОЛЕ
    linguistic_integrity: float = 1.0
    """Сопротивление языковому дрейфу. 0..1.
    В рамках fundament ТЗ всегда 1.0 (нет дрейфа).
    Memetic ТЗ будет вычислять по формуле:
    willpower * class_factor * age_factor * identity_attachment.
    """
```

Эти поля не ломают существующих NPC-конфигов, потому что имеют defaults. Любой существующий `lusya.json` будет загружен без ошибок.

---

## 3. PERSISTENCE

### 3.1. Трёхслойная онтология данных (вводится как ADR)

Это ТЗ вводит **архитектурное правило**, которое переживёт смену технологий хранения:

| Слой | Характеристики | Технология | Примеры |
|---|---|---|---|
| **Canon** | Редко меняется. Автор пишет. Версионный. Не зависит от сохранений. | JSON/YAML + git | `ConceptRegistry`, `ExpressionRegistry`, `VoiceArchetypes`, `ContentPolicyDefaults` |
| **History** | Никогда не переписывается. Только append. | SQLite | `L1Chronicle`, `MemeticTransmissionEvent`, `SocialEvents`, `Crimes` |
| **State** | Меняется постоянно. Snapshot текущего мира. | SQLite | `NPCState`, `RelationshipStore`, `PlayerBeliefModel`, `ContentPolicy` (runtime) |

**В рамках этого ТЗ** вводится только **Canon** и **State** части для Content Policy:

```
config/
    canon/
        content_policy_defaults.yaml   # Canon: дефолтные пресеты
    user_settings.yaml                  # State: настройки игрока (per-save)
```

`History` (SQLite) будет задействован в `TZ-MEMETIC-01`.

### 3.2. Файл `config/canon/content_policy_defaults.yaml` (Canon)

```yaml
# Canon: настройки контента по умолчанию для новых сохранений
# Редактируется автором. Версионный. Не зависит от сохранений.

version: "1.0"
schema: content_policy_defaults

# Пресеты для UI тумблера (см. §5.2)
presets:
  off:
    label: "Выключено"
    description: "Никакого мата, секса, детального насилия. Подходит для чувствительной аудитории."
    profanity_level: 0
    sexual_content_level: 0
    violence_level: 0
    taboo_practices_level: 0
  
  moderate:
    label: "Умеренно"
    description: "Лёгкая ругань, намёки на секс, физиологичное насилие без садизма."
    profanity_level: 1
    sexual_content_level: 1
    violence_level: 1
    taboo_practices_level: 0
  
  explicit:
    label: "Без ограничений"
    description: "Полный 18+ контент: мат, explicit-секс, детальная жестокость, табу-практики."
    profanity_level: 2
    sexual_content_level: 2
    violence_level: 2
    taboo_practices_level: 2

# Дефолтный пресет для новых сохранений
default_preset: explicit

# Что считать нарушением (для ResponseValidator)
# Расширение insults_ru.json до 4 категорий
violation_lexicons:
  profanity:
    source_file: "data/insults_ru.json"      # уже существует
    root_field: "roots"
  sexual:
    source_file: "data/sexual_lexicon_ru.json"  # НОВЫЙ ФАЙЛ
    root_field: "roots"
  violence:
    source_file: "data/violence_lexicon_ru.json"  # НОВЫЙ ФАЙЛ
    root_field: "roots"
  taboo_practices:
    source_file: "data/taboo_lexicon_ru.json"  # НОВЫЙ ФАЙЛ
    root_field: "roots"

# Fallback-фразы для silent replacement (когда LLM fallback не вызывается или падает)
fallback_phrases:
  profanity:
    - "{npc_name} молча смотрит в сторону."
    - "{npc_name} сжимает губы."
    - "{npc_name} не считает нужным отвечать."
  sexual:
    - "{npc_name} отворачивается."
    - "{npc_name} меняет тему."
  violence:
    - "{npc_name} бледнеет."
    - "{npc_name} отступает на шаг."
  taboo_practices:
    - "{npc_name} крестится."
    - "{npc_name} отказывается это обсуждать."
```

### 3.3. Файл `config/user_settings.yaml` (State) — секция `content`

Расширяет структуру, описанную в `TZ_ustanovochnik_ENIGMA_Dopolnenie_A.docx` §А.6.6. Добавляется 6-я секция:

```yaml
# config/user_settings.yaml
graphics:
  # ... (существующее)
ai_model:
  # ...
performance:
  # ...
audio:
  # ...
interface:
  language: "ru"
controls:
  keybindings: {}
  
# НОВАЯ СЕКЦИЯ
content:
  # Пресет (одно из: off / moderate / explicit)
  # Если указан пресет, individual levels игнорируются при загрузке
  # Если preset = null, используются individual levels
  preset: "explicit"
  
  # Individual levels (0..2) — используются если preset = null
  # или если игрок раскрыл "Детальные настройки" и поменял что-то
  individual:
    profanity_level: 2
    sexual_content_level: 2
    violence_level: 2
    taboo_practices_level: 2
  
  # Метаданные
  last_changed_tick: 0       # когда игрок последний раз менял (для аудита)
  last_changed_reason: "user_action"  # user_action / migration / default
```

**Правило консистентности**: если игрок выбирает пресет, `individual` обновляется из пресета. Если игрок меняет individual level — `preset` сбрасывается в `null`. Это исключает рассинхрон.

### 3.4. Миграция с `hardcore_mode`

Существующее поле `hardcore_mode: bool = True` в `backend/app/core/config.py:69` объявляется **deprecated**. Миграция:

```python
# backend/app/core/config.py — ИЗМЕНЕНИЕ

class Settings(BaseSettings):
    # ... существующее ...
    
    # DEPRECATED — заменено на ContentPolicy
    # Оставлено только для обратной совместимости со старыми сохранениями
    hardcore_mode: bool = True
    
    # НОВОЕ — путь к user_settings.yaml
    user_settings_path: Path = BASE_DIR / "config" / "user_settings.yaml"
```

```python
# backend/app/core/content_policy.py — ДОБАВИТЬ функцию

def load_content_policy(settings: Settings) -> ContentPolicy:
    """Загружает ContentPolicy из user_settings.yaml.
    
    Логика миграции:
    1. Если секция content существует — использует её.
    2. Если секции нет, но hardcore_mode=True — preset=explicit.
    3. Если секции нет и hardcore_mode=False — preset=off.
    4. Создаёт файл с дефолтным пресетом, если его нет.
    """
    path = settings.user_settings_path
    
    if not path.exists():
        # Миграция со старых версий
        if getattr(settings, "hardcore_mode", True):
            policy = ContentPolicy.preset_explicit()
        else:
            policy = ContentPolicy.preset_off()
        _save_content_section(path, policy, reason="migration")
        return policy
    
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    content_section = data.get("content")
    
    if content_section is None:
        # Файл есть, но секции content нет — миграция
        if getattr(settings, "hardcore_mode", True):
            policy = ContentPolicy.preset_explicit()
        else:
            policy = ContentPolicy.preset_off()
        data["content"] = _content_to_dict(policy, reason="migration")
        path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        return policy
    
    return _content_from_dict(content_section)
```

### 3.5. Runtime access

`ContentPolicy` — singleton на сессию. Доступ через `Settings`:

```python
# backend/app/core/config.py — ИЗМЕНЕНИЕ

class Settings(BaseSettings):
    # ...
    
    # Кэшированная политика (загружается при первом обращении)
    _content_policy_cache: Optional[ContentPolicy] = None
    
    @property
    def content_policy(self) -> ContentPolicy:
        if self._content_policy_cache is None:
            self._content_policy_cache = load_content_policy(self)
        return self._content_policy_cache
    
    def reload_content_policy(self) -> ContentPolicy:
        """Принудительный reload. Вызывается из settings screen 
        после изменения игроком."""
        self._content_policy_cache = load_content_policy(self)
        return self._content_policy_cache
```

---

## 4. ИНТЕГРАЦИЯ С СУЩЕСТВУЮЩИМ КОДОМ

### 4.1. `DMContractBuilder` — параметризация системного промпта

**Проблема**: `DM_SYSTEM_PROMPT_HARDCORE` в `dm_contract_builder.py:39-44` определён, но перекрыт внешним `dm_system.txt`. Это противоречие исправляется.

**Решение**: `DMContractBuilder` получает `ContentProfile` в конструктор и инжектит **policy-блок** в системный промпт **поверх** того, что загружено из файла.

```python
# backend/app/services/verbalization/dm_contract_builder.py — ИЗМЕНЕНИЕ

# DEPRECATED — оставлено для reference, но не используется
DM_SYSTEM_PROMPT_HARDCORE = (
    DM_SYSTEM_PROMPT
    + "\n\nТОН/РЕЖИМ: HARDCORE.\n"
    "Разрешены: мрачные сцены, жестокость, кровь, смерть, грубость, мат.\n"
    "Не морализируй, не сглаживай и не 'перевоспитывай' игрока."
)

# НОВОЕ — параметризованная инъекция
def _build_content_policy_block(profile: ContentProfile) -> str:
    """Строит блок ContentPolicy для системного промпта.
    
    Формат: явные per-axis инструкции, чтобы LLM понимала границы.
    """
    lines = ["\n\n--- ПОЛИТИКА КОНТЕНТА ---"]
    
    # Profanity
    if profile.profanity_level == 0:
        lines.append("МАТ: полностью запрещён. Используй эвфемизмы ('чёрт', 'твою мать'). "
                     "Даже если игрок оскорбляет NPC, NPC отвечает литературно.")
    elif profile.profanity_level == 1:
        lines.append("МАТ: лёгкая ругань допустима ('чёрт', 'блядь' как междометие, 'твою мать'). "
                     "Тяжёлый мат (хуй, пизда, ебанутый) — запрещён.")
    else:
        lines.append("МАТ: разрешён в полной мере, в соответствии с характером NPC.")
    
    # Sexual content
    if profile.sexual_content_level == 0:
        lines.append("СЕКС: полностью запрещён. Сцены интима — fade-to-black, "
                     "упоминания только через 'они были вместе'.")
    elif profile.sexual_content_level == 1:
        lines.append("СЕКС: намёки и полутона допустимы. Explicit-описания запрещены. "
                     "Можно описать поцелуй, нельзя — акт.")
    else:
        lines.append("СЕКС: разрешён explicit, в соответствии с характером NPC и ситуацией.")
    
    # Violence
    if profile.violence_level == 0:
        lines.append("НАСИЛИЕ: запрещены детальные описания. 'Он упал и не встал' вместо "
                     "'Кровь хлынула из рассечённой артерии'.")
    elif profile.violence_level == 1:
        lines.append("НАСИЛИЕ: физиологичные описания допустимы, но без садизма и смакования.")
    else:
        lines.append("НАСИЛИЕ: разрешены детальные описания, включая жестокость.")
    
    # Taboo practices
    if profile.taboo_practices_level == 0:
        lines.append("ТАБУ-ПРАКТИКИ (каннибализм, некрофилия, инцест, сатанизм): "
                     "полностью запрещены. NPC отказываются обсуждать, молчат, крестятся.")
    elif profile.taboo_practices_level == 1:
        lines.append("ТАБУ-ПРАКТИКИ: можно упоминать как слухи или преступления, "
                     "без описания от первого лица.")
    else:
        lines.append("ТАБУ-ПРАКТИКИ: разрешены в полном объёме, в соответствии с сеттингом.")
    
    lines.append("--- КОНЕЦ ПОЛИТИКИ КОНТЕНТА ---\n")
    return "\n".join(lines)


class DMContractBuilder:
    def __init__(
        self,
        hardcore_mode: bool = False,  # DEPRECATED — оставлен для совместимости
        max_sentences: int = 3,
        content_profile: Optional[ContentProfile] = None,  # НОВОЕ
    ):
        self._hardcore = hardcore_mode
        self._max_sentences = max_sentences
        self._content_profile = content_profile or ContentProfile()
    
    def build(
        self, 
        system_prompt: str,
        # ... остальные параметры ...
    ) -> str:
        # Существующая логика сборки...
        
        # НОВОЕ: инъекция policy-блока
        policy_block = _build_content_policy_block(self._content_profile)
        system = system_prompt + policy_block
        
        # DEPRECATED PATH: если content_profile не передан, 
        # используем старую логику hardcore_mode (для обратной совместимости)
        if not self._content_profile or self._content_profile == ContentProfile():
            if self._hardcore:
                system = system_prompt + "\n\n" + DM_SYSTEM_PROMPT_HARDCORE.split("\n\n", 1)[1]
        
        return system + body
```

### 4.2. `DMAgent` — передача ContentProfile в builder

```python
# backend/app/agents/dm_agent.py — ИЗМЕНЕНИЕ (строки 120-130)

def _build_contract(self, context: DMContext) -> str:
    settings = Settings()
    
    # НОВОЕ: загрузка ContentPolicy и создание ContentProfile
    content_policy = settings.content_policy
    content_profile = ContentProfile.from_global_policy(content_policy)
    
    builder = DMContractBuilder(
        hardcore_mode=getattr(settings, "hardcore_mode", False),  # DEPRECATED
        max_sentences=3,
        content_profile=content_profile,  # НОВОЕ
    )
    
    # ... существующая логика ...
    
    # Инъекция author_notes теперь зависит от content_profile, 
    # не от hardcore_mode (см. строку 370)
    if _author and content_policy.hardcore_mode:  # alias property
        _line += f"\n  Режиссёрская: {_author}"
```

### 4.3. `ResponseValidator` — пост-фильтр нарушений

```python
# backend/app/services/verbalization/response_validator.py — РАСШИРЕНИЕ

class NPCResponseValidator:
    def __init__(
        self,
        # ... существующие параметры ...
        content_profile: ContentProfile,
        insult_roots: set[str],          # из insults_ru.json
        sexual_roots: set[str],           # из sexual_lexicon_ru.json
        violence_roots: set[str],         # из violence_lexicon_ru.json
        taboo_roots: set[str],            # из taboo_lexicon_ru.json
    ):
        # ...
        self._content_profile = content_profile
        self._lexicons = {
            "profanity": insult_roots,
            "sexual": sexual_roots,
            "violence": violence_roots,
            "taboo_practices": taboo_roots,
        }
    
    def validate(self, response: str, npc_id: str, npc_tier: str) -> ValidationResult:
        # ... существующие проверки (язык, длина, повтор) ...
        
        # НОВАЯ ПРОВЕРКА: ContentPolicy violation
        violation = self._detect_content_violation(response)
        if violation:
            return ValidationResult(
                valid=False,
                reason=f"content_policy_violation:{violation.axis}",
                violation=violation,
            )
        
        return ValidationResult(valid=True, response=response)
    
    def _detect_content_violation(self, text: str) -> Optional[ContentViolation]:
        """Детерминированная проверка через лемматизацию pymorphy3.
        
        Для каждого слова в ответе:
        1. Лемматизация через pymorphy3
        2. Поиск леммы в lexicons[axis]
        3. Если найдено и content_profile.{axis}_level < required_level → нарушение
        """
        # Реализация аналогична dm_router._classify_action (строки 224-287)
        # Использует ту же логику защиты от залипания, отрицаний, междометий
        # ...
```

```python
# backend/app/services/verbalization/response_validator.py — ДОПОЛНЕНИЕ

@dataclass(frozen=True)
class ContentViolation:
    """Результат детекции нарушения ContentPolicy."""
    axis: str           # "profanity" / "sexual" / "violence" / "taboo_practices"
    detected_word: str  # что найдено
    lemma: str          # нормальная форма
    required_level: int # какой уровень нужен (1 или 2)
    actual_level: int   # какой уровень разрешён (из profile)
    position: int       # смещение в тексте
```

### 4.4. B-plan: LLM переформулирование

Когда валидатор обнаружил нарушение и `npc.tier == "major"`, вызывается LLM для переформулирования. Это **второй** LLM-вызов в худшем случае — но он происходит редко (только когда LLM нарушила policy), и только для major NPC (которых в сцене обычно 1-2).

```python
# backend/app/services/verbalization/response_rephraser.py — НОВЫЙ ФАЙЛ

class ResponseRephraser:
    """Переформулирование ответа LLM при нарушении ContentPolicy.
    
    Вызывается из DMAgent после validate(), если:
    - violation detected
    - npc.tier == "major"
    - retry_count < 1 (только одна попытка)
    """
    
    REPHRASE_SYSTEM_PROMPT = (
        "Ты — редактор. Перед тобой реплика NPC, которая нарушает политику контента. "
        "Переформулируй её, сохранив:\n"
        "1. Смысл и намерение NPC\n"
        "2. Характер NPC (voice_profile)\n"
        "3. Эмоциональную окраску\n"
        "Но убери:\n"
        "- {violation_description}\n"
        "Ответь ТОЛЬКО переформулированной репликой. Без объяснений."
    )
    
    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider
    
    def rephrase(
        self,
        original_response: str,
        violation: ContentViolation,
        npc_voice_profile: str,
        npc_name: str,
    ) -> Optional[str]:
        """Возвращает переформулированную реплику или None при неудаче."""
        # ... реализация ...
```

Для `npc.tier != "major"` — silent fallback на `fallback_phrases` из `content_policy_defaults.yaml`.

### 4.5. Полный pipeline валидации

```
LLM генерирует response
       ↓
ResponseValidator.validate(response, npc_id, npc_tier)
       ↓
   ┌───────────────────────────────────┐
   │ valid=True?                       │
   └──┬────────────────────────────────┘
      │
   да │ нет → violation detected
      ↓     │
   return   ↓
            npc.tier == "major"?
                │
            да  │  нет
                ↓   ↓
                │   silent_fallback(fallback_phrases[axis])
                ↓   return fallback_response
            ResponseRephraser.rephrase(...)
                │
            success?
                │
            да  │  нет
                ↓   ↓
                return rephrased   silent_fallback
```

---

## 5. UI: ВКЛАДКА «КОНТЕНТ» В SETTINGS SCREEN

### 5.1. Контекст

В `TZ_ustanovochnik_ENIGMA_Dopolnenie_A.docx` §А.6.1 описаны 4 вкладки экрана настроек: Графика, AI-модель, Производительность, Управление и звук. Экран настроек не реализован (заглушка `pass` в `game_launcher.py:212-214`).

Это ТЗ вводит **5-ю вкладку** — «Контент». Она может быть реализована **до** реализации остальных 4-х, потому что логически независима. Если экран настроек ещё не построен — вкладка «Контент» становится первой частью этого экрана, к которой потом добавятся остальные.

### 5.2. Структура вкладки

```
┌─ НАСТРОЙКИ ──────────────────────────────────────────────────────┐
│                                                                  │
│  [Графика] [AI-модель] [Производительность] [Управление] [КОНТЕНТ]│
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  18+ КОНТЕНТ                                               │  │
│  │                                                            │  │
│  │  Выберите уровень контента в игре:                         │  │
│  │                                                            │  │
│  │   ○ Выключено                                              │  │
│  │     Никакого мата, секса, детального насилия.              │  │
│  │     Подходит для чувствительной аудитории.                 │  │
│  │                                                            │  │
│  │   ○ Умеренно                                               │  │
│  │     Лёгкая ругань, намёки на секс,                         │  │
│  │     физиологичное насилие без садизма.                     │  │
│  │                                                            │  │
│  │   ● Без ограничений                                        │  │
│  │     Полный 18+ контент: мат, explicit-секс,                │  │
│  │     детальная жестокость, табу-практики.                   │  │
│  │                                                            │  │
│  │  ┌─ Детальные настройки ─────────────────────────────┐    │  │
│  │  │                                                    │    │  │
│  │  │  Мат:           [Выкл] [Умеренно] [Без огранич.]   │    │  │
│  │  │  Секс:          [Выкл] [Умеренно] [Без огранич.]   │    │  │
│  │  │  Насилие:       [Выкл] [Умеренно] [Без огранич.]   │    │  │
│  │  │  Табу-практики: [Выкл] [Умеренно] [Без огранич.]   │    │  │
│  │  │                                                    │    │  │
│  │  │  ⚠ Изменение детальных настроек отключит           │    │  │
│  │  │    пресет и будет использовать individual levels.  │    │  │
│  │  └────────────────────────────────────────────────────┘    │  │
│  │                                                            │  │
│  │  [Свернуть детальные настройки ▼]                          │  │
│  │                                                            │  │
│  │  ┌─ ПРЕДУПРЕЖДЕНИЕ ───────────────────────────────────┐    │  │
│  │  │ Изменение настроек контента вступит в силу          │    │  │
│  │  │ с начала следующего игрового тика. Текущие          │    │  │
│  │  │ диалоги в прогрессе будут завершены по старым       │    │  │
│  │  │ правилам.                                           │    │  │
│  │  └────────────────────────────────────────────────────┘    │  │
│  │                                                            │  │
│  │                          [Отмена]  [Применить]             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.3. UX-логика

1. **Один тумблер по умолчанию**: игрок видит 3 radio-кнопки (Выключено / Умеренно / Без ограничений). Это 90% случаев — большинству игроков не нужны детали.

2. **Раскрытие детальных настроек**: ссылка «Детальные настройки ▼» разворачивает 4 слайдера. Когда игрок меняет любой слайдер — radio-кнопки пресетов деактивируются (визуально становятся неактивными), и сохраняется `preset: null` + `individual` values.

3. **Возврат к пресету**: если игрок снова выбирает radio-кнопку пресета — individual values перезаписываются значениями пресета.

4. **Кнопка «Применить»**: изменения не вступают в силу немедленно. Игрок должен нажать «Применить» — тогда:
   - Записывается `last_changed_tick` (текущий тик)
   - `Settings.reload_content_policy()` вызывается
   - Со следующего тика LLM получает новый policy-блок в системном промпте
   - ResponseValidator загружает новые lexicons-уровни

5. **Кнопка «Отмена»**: закрывает экран без сохранения. Изменения в UI сбрасываются.

6. **Предупреждение**: явный текст, что текущие диалоги завершатся по старым правилам. Это сделано потому, что LLM-запрос в полёте нельзя отменить — он использует тот промпт, с которым был отправлен.

### 5.4. Pygame-реализация (структура)

```python
# frontend/settings_screen.py — НОВЫЙ ФАЙЛ (минимальная реализация под вкладку Контент)

class SettingsScreen:
    """Экран настроек. В рамках этого ТЗ — только вкладка Контент.
    Остальные вкладки добавляются позже согласно Дополнению А §А.6.1."""
    
    TABS = ["Графика", "AI-модель", "Производительность", "Управление", "Контент"]
    
    def __init__(self, screen: pygame.Surface):
        self._screen = screen
        self._active_tab = "Контент"  # единственная реализованная
        self._preset: str = "explicit"  # off / moderate / explicit / null
        self._individual = {
            "profanity_level": 2,
            "sexual_content_level": 2,
            "violence_level": 2,
            "taboo_practices_level": 2,
        }
        self._show_advanced = False
        self._dirty = False  # есть несохранённые изменения
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Обработка кликов. Возвращает 'apply' / 'cancel' / None."""
        # ...
    
    def render(self) -> None:
        """Отрисовка вкладки Контент."""
        # ...
    
    def _on_preset_selected(self, preset: str) -> None:
        """Игрок выбрал пресет. Обновляет individual values из пресета."""
        self._preset = preset
        self._individual = self._load_preset_values(preset)
        self._dirty = True
    
    def _on_individual_changed(self, axis: str, level: int) -> None:
        """Игрок изменил individual level. Сбрасывает пресет."""
        self._preset = "null"
        self._individual[axis] = level
        self._dirty = True
    
    def _apply(self) -> None:
        """Запись в user_settings.yaml + reload ContentPolicy."""
        # 1. Чтение текущего user_settings.yaml
        # 2. Обновление секции content
        # 3. Запись обратно
        # 4. Вызов Settings.reload_content_policy()
        # 5. Логирование: last_changed_tick, last_changed_reason
```

### 5.5. Подключение к game_launcher

```python
# game_launcher.py — ИЗМЕНЕНИЕ (строки 212-214)

elif action == MenuAction.SETTINGS:
    from settings_screen import SettingsScreen
    settings_screen = SettingsScreen(self._screen)
    result = settings_screen.run()  # blocking loop
    if result == "apply":
        # ContentPolicy уже перезагружен внутри settings_screen
        # Логирование
        logger.info("[GAME_LAUNCHER] Content policy changed by user")
```

---

## 6. СЛОВАРИ ЛЕКСИКИ

### 6.1. Расширение существующего `insults_ru.json`

Файл `backend/data/insults_ru.json` уже существует и содержит ~200 корней мата. Он **переиспользуется как есть** для оси `profanity`. Никаких изменений в его структуре не требуется — `ResponseValidator` будет читать тот же `roots` field.

### 6.2. Новые файлы лексиконов

Для трёх других осей создаются аналогичные файлы:

```
backend/data/
    insults_ru.json              # СУЩЕСТВУЕТ — profanity
    sexual_lexicon_ru.json       # НОВЫЙ — sexual_content_level
    violence_lexicon_ru.json     # НОВЫЙ — violence_level
    taboo_lexicon_ru.json        # НОВЫЙ — taboo_practices_level
```

**Структура** — идентична `insults_ru.json`:

```json
{
  "_version": "1.0",
  "_type": "content_lexicon",
  "_axis": "sexual",
  "_description": "Корни sexual-лексики. Используется ResponseValidator для детекции нарушений ContentPolicy при sexual_content_level < 2.",
  "roots": [
    "секс",
    "трах",
    "еб",
    "еба",
    "ебл",
    "ебн",
    "блуд",
    "прелюбод",
    "шлюх",
    "курв",
    "проститут",
    "шалав",
    "потаск",
    "распут",
    "грех",
    "блуд"
  ],
  "_notes": [
    "Корни намеренно короткие — лемматизация pymorphy3 нормализует формы.",
    "Слово 'грех' включено, потому что в средневековом сеттинге это маркер sexual-контента в речи духовенства.",
    "Корень 'ебл' ловит 'ебля', 'ебливый', но НЕ 'ебанько' (отдельный корень)."
  ]
}
```

Аналогично для `violence_lexicon_ru.json` (корни: рез, уб, душ, калеч, расчлен, кров, кишк, внутрен, guts-аналоги) и `taboo_lexicon_ru.json` (корни: каннибал, людоед, некро, инцест, кровосм, сатан, бес, демон-поклон).

### 6.3. Загрузка лексиконов

```python
# backend/app/services/verbalization/lexicon_loader.py — НОВЫЙ ФАЙЛ

class ContentLexiconLoader:
    """Загружает 4 лексикона для ResponseValidator.
    
    Кэширует в памяти. Перезагружается при reload_content_policy().
    """
    
    _CACHE: dict[str, set[str]] = {}
    
    @classmethod
    def load_all(cls, data_dir: Path) -> dict[str, set[str]]:
        """Возвращает {'profanity': set, 'sexual': set, ...}."""
        if not cls._CACHE:
            cls._CACHE = {
                "profany": cls._load(data_dir / "insults_ru.json"),
                "sexual": cls._load(data_dir / "sexual_lexicon_ru.json"),
                "violence": cls._load(data_dir / "violence_lexicon_ru.json"),
                "taboo_practices": cls._load(data_dir / "taboo_lexicon_ru.json"),
            }
        return cls._CACHE
    
    @classmethod
    def reload(cls, data_dir: Path) -> dict[str, set[str]]:
        cls._CACHE.clear()
        return cls.load_all(data_dir)
    
    @classmethod
    def _load(cls, path: Path) -> set[str]:
        if not path.exists():
            logger.warning(f"[LEXICON] {path} not found, axis disabled")
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return set(data.get("roots", []))
        except Exception as e:
            logger.error(f"[LEXICON] Failed to load {path}: {e}")
            return set()
```

---

## 7. ТЕСТЫ ПРИНЯТИЯ

### 7.1. Миграция

```python
# backend/tests/test_content_policy_migration.py

def test_old_save_with_hardcore_mode_true_migrates_to_explicit():
    """Старое сохранение с hardcore_mode=True → preset=explicit."""

def test_old_save_with_hardcore_mode_false_migrates_to_off():
    """Старое сохранение с hardcore_mode=False → preset=off."""

def test_new_save_without_content_section_migrates_to_default():
    """Новый user_settings.yaml без секции content → default_preset."""

def test_existing_content_section_not_overwritten_on_migration():
    """Если секция content уже есть — миграция её не трогает."""
```

### 7.2. ContentPolicy

```python
# backend/tests/test_content_policy.py

def test_preset_off_all_axes_zero():
    policy = ContentPolicy.preset_off()
    assert policy.profanity_level == ContentLevel.OFF
    assert policy.sexual_content_level == ContentLevel.OFF
    assert policy.violence_level == ContentLevel.OFF
    assert policy.taboo_practices_level == ContentLevel.OFF

def test_preset_explicit_all_axes_two():
    policy = ContentPolicy.preset_explicit()
    assert policy.profanity_level == ContentLevel.EXPLICIT
    # ...

def test_hardcore_mode_alias_true_when_any_explicit():
    policy = ContentPolicy(profanity_level=ContentLevel.OFF, 
                          sexual_content_level=ContentLevel.EXPLICIT)
    assert policy.hardcore_mode is True

def test_hardcore_mode_alias_false_when_all_below_explicit():
    policy = ContentPolicy.preset_moderate()
    assert policy.hardcore_mode is False
```

### 7.3. DMContractBuilder

```python
# backend/tests/test_dm_contract_builder_content_policy.py

def test_policy_block_injected_into_system_prompt():
    """Policy-блок появляется в системном промпте при build()."""

def test_policy_off_injects_full_profanity_ban():
    builder = DMContractBuilder(content_profile=ContentProfile(
        profanity_level=0, sexual_content_level=0,
        violence_level=0, taboo_practices_level=0
    ))
    result = builder.build(system_prompt="базовый", ...)
    assert "МАТ: полностью запрещён" in result
    assert "СЕКС: полностью запрещён" in result

def test_policy_explicit_injects_permission():
    builder = DMContractBuilder(content_profile=ContentProfile(
        profanity_level=2, sexual_content_level=2,
        violence_level=2, taboo_practices_level=2
    ))
    result = builder.build(system_prompt="базовый", ...)
    assert "МАТ: разрешён" in result
```

### 7.4. ResponseValidator

```python
# backend/tests/test_response_validator_content_policy.py

def test_profanity_detected_when_level_zero():
    """При profanity_level=0 ответ с матом → violation."""

def test_profanity_allowed_when_level_two():
    """При profanity_level=2 ответ с матом → valid."""

def test_morphological_normalization_works():
    """'дурак' и 'дурачком' детектируются как одно нарушение."""

def test_negation_does_not_trigger_violation():
    """'Ты не дурак' — не нарушение."""

def test_interjection_does_not_trigger_violation():
    """'Блядь, я забыл' — не нарушение (если level >= 1)."""
```

### 7.5. UI

```python
# frontend/tests/test_settings_screen.py

def test_selecting_preset_updates_individual_levels():
    """Выбор пресета 'off' → все individual = 0."""

def test_changing_individual_clears_preset():
    """Изменение individual level → preset = null."""

def test_apply_writes_to_user_settings_yaml():
    """Кнопка Apply → файл обновляется."""

def test_cancel_does_not_write():
    """Кнопка Cancel → файл не трогается."""

def test_reload_content_policy_after_apply():
    """После Apply Settings.content_policy возвращает новое значение."""
```

### 7.6. End-to-end scenario

```python
# backend/tests/test_content_policy_e2e.py

def test_player_turns_off_profanity_npc_stops_swearing():
    """Полный цикл:
    1. NPC матерится (level=2)
    2. Игрок ставит profanity_level=0 в настройках
    3. Следующая реплика NPC — без мата (или fallback)
    """

def test_rephraser_called_for_major_npc_on_violation():
    """Major NPC → LLM получает запрос на переформулирование."""

def test_silent_fallback_for_minor_npc_on_violation():
    """Minor NPC → fallback-фраза из content_policy_defaults.yaml."""
```

---

## 8. КРИТЕРИИ ПРИНЯТИЯ (ACCEPTANCE CRITERIA)

| # | Критерий | Как проверить |
|---|---|---|
| AC-1 | В settings screen есть вкладка «Контент» с 3 пресетами | Визуально в игре |
| AC-2 | Раскрытие детальных настроек показывает 4 слайдера | Визуально в игре |
| AC-3 | Изменение пресета обновляет individual levels | Тест `test_selecting_preset_updates_individual_levels` |
| AC-4 | Изменение individual level сбрасывает пресет | Тест `test_changing_individual_clears_preset` |
| AC-5 | Кнопка «Применить» записывает в `user_settings.yaml` | Тест `test_apply_writes_to_user_settings_yaml` |
| AC-6 | Старое сохранение с `hardcore_mode=True` мигрирует в `preset=explicit` | Тест `test_old_save_with_hardcore_mode_true_migrates_to_explicit` |
| AC-7 | Системный промпт DM содержит policy-блок | Тест `test_policy_block_injected_into_system_prompt` |
| AC-8 | При `profanity_level=0` ответ NPC с матом детектируется как violation | Тест `test_profanity_detected_when_level_zero` |
| AC-9 | Для major NPC вызывается `ResponseRephraser` | Тест `test_rephraser_called_for_major_npc_on_violation` |
| AC-10 | Для minor NPC используется silent fallback | Тест `test_silent_fallback_for_minor_npc_on_violation` |
| AC-11 | `hardcore_mode` property работает как alias (не ломает существующий код) | Тест `test_hardcore_mode_alias_*` |
| AC-12 | Все 4 лексикона загружаются без ошибок | Логи при старте |

---

## 9. ПЛАН РЕАЛИЗАЦИИ

### Phase 1: Backend (3-4 дня)

1. Создать `backend/app/core/content_policy.py` (ContentLevel, ContentPolicy)
2. Расширить `ContentProfile` в `verbalization_context.py`
3. Добавить stub-поля в `NPCProfileL0` и `PsycheBase`
4. Реализовать `load_content_policy()` + миграция
5. Расширить `DMContractBuilder` (policy-блок)
6. Обновить `DMAgent._build_contract()` (передача ContentProfile)
7. Реализовать `ContentLexiconLoader`
8. Создать 3 новых файла лексиконов (`sexual`, `violence`, `taboo`)
9. Расширить `ResponseValidator` (детекция violation)
10. Реализовать `ResponseRephraser`
11. Написать backend-тесты (раздел 7.1-7.4)

### Phase 2: Frontend (2-3 дня)

1. Создать `frontend/settings_screen.py` (минимально — только вкладка Контент)
2. Подключить к `game_launcher.py` (вместо заглушки `pass`)
3. Реализовать UI: 3 radio-кнопки + 4 слайдера
4. Реализовать Apply/Cancel логику
5. Написать frontend-тесты (раздел 7.5)

### Phase 3: Integration (1-2 дня)

1. End-to-end тесты (раздел 7.6)
2. Проверка миграции на реальном сохранении
3. Логирование изменений policy (для аудита)
4. Документация: обновить `docs/ADR (Architecture Decision Records).md` с `ADR-O-MEMETIC-000`

### Phase 4: Cleanup (1 день)

1. Удалить `DM_SYSTEM_PROMPT_HARDCORE` (deprecated и не используется)
2. Удалить `config.json.deprecated` (уже deprecated)
3. Обновить `architecture/verbalization.yaml` (расхождение с кодом — см. §1.3 расследования)
4. Обновить README — добавить упоминание ContentPolicy в Build Status

**Итого**: 7-10 рабочих дней на полную реализацию.

---

## 10. ADR-O-MEMETIC-000: ONTOLOGICAL STORAGE PRINCIPLE

Это ТЗ вводит архитектурное правило, которое фиксируется как ADR.

### Decision

Хранение данных в ENIGMA разделяется на три онтологических слоя:

1. **Canon** — исходный код мира. Редактируется человеком. Версионный. Не зависит от сохранений. Технология: JSON/YAML + git.
2. **History** — append-only журнал событий. Никогда не переписывается. Технология: SQLite.
3. **State** — mutable snapshot текущего мира. Свободно изменяется. Технология: SQLite.

### Rationale

Технологии хранения приходят и уходят. Онтологическое разделение переживёт любую смену СУБД или формата файлов. Если через 10 лет JSON будет заменён на бинарный формат, а SQLite — на другую СУБД, архитектура не изменится — изменятся только адаптеры хранения.

### Consequences

- Любая новая фича должна быть классифицирована: Canon / History / State.
- Canon-файлы живут в `config/canon/`. State-файлы — в `config/` (для user settings) или в `saves/<campaign_id>/` (для per-save state). History — в `saves/<campaign_id>/history.db`.
- Смешивание Canon и State в одном файле — архитектурное нарушение.
- Migration scripts могут читать старые форматы, но не должны переписывать History.

### Taboo

- ❌ Перезапись History-записей (кроме случаев explicit garbage collection по ADR).
- ❌ Хранение Canon-данных в SQLite (Canon должен быть человекочитаемым).
- ❌ Хранение mutable State в JSON-файлах (race conditions, no transactions).

---

## 11. СВЯЗЬ С БУДУЩИМИ ТЗ

Это ТЗ — **фундамент**. Оно вводит:

- `ContentPolicy` — глобальный потолок, который будет переиспользован в `TZ-MEMETIC-01` как один из аргументов `ExpressionResolver`.
- `ContentProfile` — per-NPC структура, которая в memetic-системе будет заполняться не из глобальной политики, а из `adopted_expressions` NPC.
- Stub-поля `voice_archetype_id` и `linguistic_integrity` — резервируют схему для memetic-двигателя.
- ADR-O-MEMETIC-000 — онтологический принцип хранения, на который опираются все будущие memetic-структуры.

**Когда `TZ-MEMETIC-01` будет реализован**, изменения в этом ТЗ:
- `ContentProfile.from_global_policy()` остаётся, но добавляется `ContentProfile.from_npc_state(npc, global_policy)` — учитывает adopted expressions.
- `ResponseValidator` начинает фильтровать не по словарям, а по `category_tags` Expressions, которые NPC `adopted`.
- `DMContractBuilder` начинает использовать Speaker Vocabulary (preferred + known expressions) вместо голого `voice_profile`.

То есть **ничто в этом ТЗ не нужно переписывать** — только расширять.

---

## 12. РИСКИ И АЛЬТЕРНАТИВЫ

### 12.1. Риск: LLM-задержки при rephraser

**Проблема**: второй LLM-вызов на каждый violation удваивает latency.
**Митигация**: rephraser только для major NPC (1-2 за сцену). Для minor — silent fallback. Если violation происходит часто — это сигнал, что LLM системно игнорирует policy-блок, и нужно tuning промпта, не rephraser.

### 12.2. Риск: ложные срабатывания валидатора

**Проблема**: «блуд» как корень может поймать «блудный сын» (библейская цитата) при `sexual_content_level=0`.
**Митигация**: lexicons снабжены `_notes` с пояснениями. Автор кампании может добавлять whitelist-исключения в `content_policy_defaults.yaml` (расширение структуры в будущих ТЗ).

### 12.3. Альтернатива: токен-level фильтрация вместо response-level

**Идея**: использовать logit-bias в llama.cpp для запрета генерации матерных токенов.
**Почему отклонено**: 
- Logit-bias работает на token-уровне, не на word-уровне. Один русский мат = 2-5 токенов в Qwen2.5.
- Logit-bias не различает контекст («блядь» как междометие vs оскорбление).
- Logit-bias не масштабируется на 4 оси × 200 корней = 800 запрещённых токенов — деградирует качество генерации.
- LLM должна иметь возможность генерировать мат для NPC с appropriate character — мы фильтруем на response-уровне, не на generation-уровне.

### 12.4. Альтернатива: per-NPC флаг вместо ContentPolicy

**Идея**: вернуться к изначальной идее — `profanity_level` в каждом NPC-конфиге.
**Почему отклонено**: 
- Не решает проблему «игрок хочет включить/выключить 18+ одним кликом».
- Не масштабируется на детей (нельзя настраивать каждому ребёнку).
- Не учитывает языковой дрейф (NPC меняется со временем).
- Per-NPC флаги — это будущая `ContentProfile.from_npc_state()`, но не глобальная политика.

---

## 13. ИТОГ

Это ТЗ вводит **минимальный, самодостаточный, готовый к реализации сейчас** фундамент системы управления контентом. Оно:

1. Решает базовую потребность игрока — переключатель 18+ в настройках.
2. Не зависит от memetic-системы (может быть реализовано и работать уже через неделю).
3. Готовит схему для memetic-системы (stub-поля, ADR, трёхслойная онтология).
4. Исправляет существующие противоречия в коде (`DM_SYSTEM_PROMPT_HARDCORE`, `ContentProfile` stub).
5. Вводит ADR-O-MEMETIC-000 — онтологический принцип хранения, который переживёт технологии.

После реализации этого ТЗ ENIGMA получит **первый реальный рычаг управления контентом** — и игрок сможет выбрать, играть ли ему с полным 18+ или в «цензурированной» версии, без переписывания NPC-конфигов и без ожидания полной memetic-системы.

---

**Конец документа.**
