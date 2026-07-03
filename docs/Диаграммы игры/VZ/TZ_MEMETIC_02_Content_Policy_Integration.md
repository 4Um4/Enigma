# ТЗ: ИНТЕГРАЦИЯ CONTENT POLICY С MEMETIC DOMAIN (Content Policy Integration)

> **Проект:** ENIGMA / The Fool
> **Версия ТЗ:** 1.0
> **Статус:** PROPOSED
> **Дата:** 2026-07-03
> **Зависимости:** 
> - `TZ_CONTENT_POLICY_FUNDAMENT.md` (обязательно)
> - `TZ_MEMETIC_01_Domain_Spec.md` (обязательно)
> **Связанные документы:** `architecture/verbalization.yaml`, `architecture/identity.yaml`
> **Критичность:** P1 — связующий слой между фундаментом и доменом
> **Архитектурный принцип:** ADR-O-MEMETIC-002 (вводится этим ТЗ)

---

## 0. НАЗНАЧЕНИЕ И СКОУП

### 0.1. Цель

Это ТЗ описывает **как именно** домен MEMETIC_TRANSMISSION (TZ-MEMETIC-01) подключается к Content Policy (TZ_CONTENT_POLICY_FUNDAMENT). Это «клей» между двумя системами.

Без этого ТЗ:
- `ContentPolicy` работает, но `ContentProfile` всегда = глобальной политике (per-NPC различий нет).
- `ResponseValidator` фильтрует по словарям `insults_ru.json`, не по `category_tags` Expressions.
- `DMContractBuilder` использует голый `voice_profile` (free-form текст), не `SpeakerVocabulary`.
- Графиня всё ещё может случайно обложиться матом, потому что LLM не знает, какие конкретные выражения ей свойственны.

С этим ТЗ:
- `ContentProfile.from_npc_state()` вычисляет per-NPC профиль из **adopted expressions**.
- `ResponseValidator` фильтрует по `category_tags` конкретных Expressions, которые NPC **знает и может использовать**.
- `DMContractBuilder` получает `SpeakerVocabulary` — какие конкретные слова NPC выбирает для каких Concept-ов.
- Графиня получает в промпт **только литературные expressions** для Concept «стражник» — «стражник», «караульный», но не «железник» и не «синяя спина».

### 0.2. Что меняется по сравнению с фундаментом

| Компонент | В TZ_CONTENT_POLICY_FUNDAMENT | В TZ-MEMETIC-02 (этот документ) |
|---|---|---|
| `ContentProfile` | `from_global_policy()` — все NPC одинаковы | `from_npc_state()` — per-NPC, из adopted expressions |
| `ResponseValidator` | Фильтр по словарям (`insults_ru.json` + 3 новых) | Фильтр по `category_tags` Expressions + fallback на словари |
| `DMContractBuilder` | Policy-блок с общими правилами | Policy-блок + **SpeakerVocabulary** с конкретными словами |
| `DMContractBuilder` voice_constraints | `{"STYLE": voice_profile}` | `{"STYLE": voice_profile, "VOCABULARY": preferred_expressions, "FORBIDDEN": blocked_expressions}` |
| `ResponseRephraser` | Переформулирование при любом нарушении | Переформулирование **только если violation конкретного expression** |
| UI settings | Один тумблер + 4 слайдера | Без изменений (UI не меняется) |

### 0.3. Принцип обратной совместимости

Это ТЗ **не ломает** TZ_CONTENT_POLICY_FUNDAMENT. Конкретно:

- `ContentProfile.from_global_policy()` **остаётся** и работает (для NPC без memetic state — например, для minor NPC или при отключённой memetic-системе).
- `ContentPolicy` (глобальный потолок) **не меняется** — те же 4 оси, те же 3 уровня.
- UI настроек **не меняется** — игрок по-прежнему видит один тумблер + 4 слайдера.
- Persistence `user_settings.yaml` **не меняется**.

Меняется только **внутренняя логика** формирования `ContentProfile` и **источник данных** для `ResponseValidator` и `DMContractBuilder`.

### 0.4. Условие активации

Memetic-интеграция **активируется по флагу**:

```python
# backend/app/core/config.py — РАСШИРЕНИЕ

class Settings(BaseSettings):
    # ...
    
    # НОВОЕ — флаг активации memetic-интеграции
    memetic_integration_enabled: bool = False
    """Если True — ContentProfile вычисляется из npc_state.
    Если False — используется from_global_policy() (fundament режим).
    
    Позволяет включать memetic-систему постепенно, после тестирования.
    По умолчанию False — fundament работает как описано в TZ_CONTENT_POLICY_FUNDAMENT.
    """
```

Когда `memetic_integration_enabled=False`, вся система ведёт себя **точно как в TZ_CONTENT_POLICY_FUNDAMENT**. Это позволяет:
- Реализовать фундамент первым (7-10 дней).
- Реализовать memetic-домен (5-6 недель).
- Включить интеграцию одним флагом, когда обе системы готовы и протестированы.

---

## 1. МНОГОСЛОЙНАЯ МОДЕЛЬ CONTENT PROFILE

### 1.1. Три уровня ContentProfile

В этом ТЗ `ContentProfile` становится **многослойным**:

```
L0: Глобальная политика (ContentPolicy из user_settings.yaml)
    ↓
L1: Voice Archetype defaults (из config/canon/voice_archetypes/)
    ↓
L2: NPC adopted expressions (из state.db, npc_adoptions table)
    ↓
L3: Effective ContentProfile (computed per-NPC, per-tick)
```

**L0** — потолок игрока. Никогда не превышается.
**L1** — что свойственно архетипу NPC (noble = без мата, thief = лёгкий мат).
**L2** — что NPC реально усвоил через memetic transmission.
**L3** — итоговый профиль, который уходит в `DMContractBuilder` и `ResponseValidator`.

### 1.2. Формула Effective ContentProfile

```python
# backend/app/services/memetic/effective_content_profile.py — НОВЫЙ ФАЙЛ

from dataclasses import dataclass
from typing import Optional


class EffectiveContentProfileComputer:
    """Вычисляет per-NPC ContentProfile из трёх уровней.
    
    L0 (global policy) → потолок
    L1 (archetype) → базовые наклонности
    L2 (adopted) → что реально усвоено
    
    L3 = min(L0, max(L1, L2_effective))
    
    Где L2_effective = уровень, на котором NPC реально использует
    усвоенные expressions данной оси.
    """
    
    def compute(
        self,
        global_policy: ContentPolicy,           # L0
        voice_archetype: VoiceArchetype,         # L1
        npc_adoptions: list[Adoption],           # L2
        npc_psyche: PsycheSnapshot,              # для stress gate
        current_tick: int,
    ) -> ContentProfile:
        """Возвращает ContentProfile для конкретного NPC в текущий момент."""
        
        # L0: потолок (из глобальной политики)
        ceiling = {
            "profanity": int(global_policy.profanity_level),
            "sexual_content": int(global_policy.sexual_content_level),
            "violence": int(global_policy.violence_level),
            "taboo_practices": int(global_policy.taboo_practices_level),
        }
        
        # L1: archetype defaults
        archetype_level = self._archetype_axis_levels(voice_archetype)
        # noble: profanity=0, sexual=0, violence=1, taboo=0
        # thief: profanity=1, sexual=1, violence=2, taboo=0
        # ...
        
        # L2: adopted expressions
        adopted_level = self._adopted_axis_levels(npc_adoptions, current_tick)
        # Если NPC усвоил 5 profanity:heavy expressions → profanity=2
        # Если NPC усвоил 2 sexual:explicit expressions → sexual=2
        
        # L3: effective = min(ceiling, max(archetype, adopted))
        # Это значит:
        # - NPC не может превысить потолок игрока
        # - NPC не может быть "ниже" своего архетипа (noble не начинает материться)
        # - NPC может быть "выше" архетипа, если усвоил новые expressions
        #   (вор научил крестьянина мату)
        
        effective = {}
        for axis in ["profanity", "sexual_content", "violence", "taboo_practices"]:
            effective[axis] = min(
                ceiling[axis],
                max(archetype_level[axis], adopted_level[axis]),
            )
        
        # Stress gate: при высоком stress можно +1 (но не выше ceiling)
        if npc_psyche.stress > npc_psyche.breakpoint * 0.8:
            for axis in effective:
                effective[axis] = min(ceiling[axis], effective[axis] + 1)
        
        # Собираем adopted words для DMContractBuilder
        adopted_profanity = self._collect_adopted_words(
            npc_adoptions, "profanity", ceiling["profanity"]
        )
        adopted_sexual = self._collect_adopted_words(
            npc_adoptions, "sexual", ceiling["sexual_content"]
        )
        
        return ContentProfile(
            profanity_level=effective["profanity"],
            sexual_content_level=effective["sexual_content"],
            violence_level=effective["violence"],
            taboo_practices_level=effective["taboo_practices"],
            adopted_profanity_words=adopted_profanity,
            adopted_sexual_words=adopted_sexual,
        )
    
    def _archetype_axis_levels(
        self, archetype: VoiceArchetype,
    ) -> dict[str, int]:
        """Возвращает дефолтные уровни осей для архетипа.
        
        Читается из voice_archetypes/<id>.yaml, поле content_defaults.
        """
        # Из YAML:
        # noble.yaml: content_defaults: {profanity: 0, sexual: 0, violence: 1, taboo: 0}
        # thief.yaml: content_defaults: {profanity: 2, sexual: 1, violence: 2, taboo: 0}
        # maid.yaml:  content_defaults: {profanity: 0, sexual: 1, violence: 1, taboo: 0}
        # ...
        return {
            "profanity": archetype.content_defaults.get("profanity", 0),
            "sexual_content": archetype.content_defaults.get("sexual", 0),
            "violence": archetype.content_defaults.get("violence", 1),
            "taboo_practices": archetype.content_defaults.get("taboo", 0),
        }
    
    def _adopted_axis_levels(
        self, adoptions: list[Adoption], current_tick: int,
    ) -> dict[str, int]:
        """Вычисляет уровень оси из adopted expressions.
        
        Логика:
        - 0 adopted expressions уровня N → уровень 0
        - 1-2 adopted уровня 1 → уровень 1
        - 3+ adopted уровня 1, или 1+ уровня 2 → уровень 2
        
        Учитывает recency: если последнее использование было давно —
        уровень может снижаться (word fading from active vocabulary).
        """
        # ... реализация ...
```

### 1.3. Расширение VoiceArchetype

В `TZ-MEMETIC-01` `VoiceArchetype` уже определён. Здесь добавляем поле `content_defaults`:

```yaml
# config/canon/voice_archetypes/noble.yaml — РАСШИРЕНИЕ

archetype_id: noble
# ... (существующие поля из TZ-MEMETIC-01) ...

# НОВОЕ — дефолтные уровни контента для архетипа
content_defaults:
  profanity: 0          # благородный не матерится
  sexual: 0             # и не обсуждает секс открыто
  violence: 1           # но может описать насилие сдержанно
  taboo: 0              # табу-практики абсолютно исключены
```

```yaml
# config/canon/voice_archetypes/thief.yaml

content_defaults:
  profanity: 2          # матерится свободно
  sexual: 1             # намёки и грубоватые шутки
  violence: 2           # описывает насилие детально
  taboo: 0              # но каннибализм — за гранью
```

```yaml
# config/canon/voice_archetypes/maid.yaml

content_defaults:
  profanity: 0          # не матерится (но может усвоить через memetic)
  sexual: 1             # знает про секс из опыта (Люся)
  violence: 1           # видела насилие, описывает сдержанно
  taboo: 0
```

### 1.4. `ContentProfile.from_npc_state()` — новая фабрика

```python
# backend/app/services/verbalization/verbalization_context.py — РАСШИРЕНИЕ

@dataclass(frozen=True)
class ContentProfile:
    """Профиль разрешённого контента для вербализации конкретного NPC.
    
    В TZ_CONTENT_POLICY_FUNDAMENT: всегда = глобальной политике.
    В TZ-MEMETIC-02: per-NPC, вычисляется из archetype + adopted expressions.
    """
    profanity_level: int = 0
    sexual_content_level: int = 0
    violence_level: int = 0
    taboo_practices_level: int = 0
    
    adopted_profanity_words: tuple[str, ...] = ()
    adopted_sexual_words: tuple[str, ...] = ()
    
    # НОВОЕ — источник профиля (для аудита)
    source: str = "global"  # "global" / "archetype" / "memetic"
    
    def __post_init__(self) -> None:
        # ... (существующая валидация) ...
        pass
    
    @classmethod
    def from_global_policy(cls, policy: ContentPolicy) -> "ContentProfile":
        """Fundament режим — все NPC одинаковы."""
        return cls(
            profanity_level=int(policy.profanity_level),
            sexual_content_level=int(policy.sexual_content_level),
            violence_level=int(policy.violence_level),
            taboo_practices_level=int(policy.taboo_practices_level),
            source="global",
        )
    
    @classmethod
    def from_npc_state(
        cls,
        npc_id: str,
        global_policy: ContentPolicy,
        voice_archetype: VoiceArchetype,
        npc_adoptions: list[Adoption],
        npc_psyche: PsycheSnapshot,
        current_tick: int,
    ) -> "ContentProfile":
        """Memetic режим — per-NPC, из archetype + adopted.
        
        Вызывается ТОЛЬКО когда settings.memetic_integration_enabled = True.
        """
        computer = EffectiveContentProfileComputer()
        return computer.compute(
            global_policy=global_policy,
            voice_archetype=voice_archetype,
            npc_adoptions=npc_adoptions,
            npc_psyche=npc_psyche,
            current_tick=current_tick,
        )
```

### 1.5. Ленивое вычисление в `DMAgent`

```python
# backend/app/agents/dm_agent.py — РАСШИРЕНИЕ

def _build_contract(self, context: DMContext) -> str:
    settings = Settings()
    content_policy = settings.content_policy
    
    # НОВОЕ: выбор фабрики ContentProfile
    if settings.memetic_integration_enabled:
        # Memetic режим: per-NPC профиль
        voice_archetype = self._load_voice_archetype(context.npc_id)
        npc_adoptions = self._load_adoptions(context.npc_id)
        npc_psyche = self._load_psyche_snapshot(context.npc_id)
        
        content_profile = ContentProfile.from_npc_state(
            npc_id=context.npc_id,
            global_policy=content_policy,
            voice_archetype=voice_archetype,
            npc_adoptions=npc_adoptions,
            npc_psyche=npc_psyche,
            current_tick=context.current_tick,
        )
    else:
        # Fundament режим: глобальная политика
        content_profile = ContentProfile.from_global_policy(content_policy)
    
    builder = DMContractBuilder(
        hardcore_mode=getattr(settings, "hardcore_mode", False),  # DEPRECATED
        max_sentences=3,
        content_profile=content_profile,
    )
    
    # ... остальная логика ...
```

---

## 2. SPEAKER VOCABULARY В DMCONTRACTBUILDER

### 2.1. Что меняется в voice_constraints

В `TZ_CONTENT_POLICY_FUNDAMENT` `DMContractBuilder` строит `voice_constraints` из голого `voice_profile`:

```python
# Существующее (из scene_outcome_builder.py:872-883)
def _build_voice_constraints(self, npc_id, context, profile):
    if profile and profile.voice_profile:
        return {"STYLE": profile.voice_profile}
    return {}
```

В TZ-MEMETIC-02 `voice_constraints` становится **богаче**:

```python
# backend/app/services/verbalization/scene_outcome_builder.py — РАСШИРЕНИЕ

def _build_voice_constraints(
    self, npc_id: str, context: VerbalizationContext, profile: NPCProfileL0,
) -> dict:
    """Строит voice_constraints для DM-промпта.
    
    В fundament режиме: только STYLE.
    В memetic режиме: STYLE + VOCABULARY + FORBIDDEN.
    """
    constraints = {}
    
    # 1. STYLE — всегда (из voice_profile)
    if profile and profile.voice_profile:
        constraints["STYLE"] = profile.voice_profile
    
    # 2. VOCABULARY — только в memetic режиме
    settings = Settings()
    if settings.memetic_integration_enabled:
        speaker_vocab = self._load_speaker_vocabulary(npc_id, context)
        if speaker_vocab:
            constraints["VOCABULARY"] = self._format_vocabulary_block(speaker_vocab)
        
        # 3. FORBIDDEN — expressions, заблокированные ContentPolicy
        forbidden = self._compute_forbidden_expressions(npc_id, context)
        if forbidden:
            constraints["FORBIDDEN"] = forbidden
    
    return constraints


def _format_vocabulary_block(
    self, vocab_bundle: SpeakerVocabularyBundle,
) -> str:
    """Форматирует SpeakerVocabulary в текстовый блок для LLM.
    
    Пример:
    
    VOCABULARY (предпочтительные выражения NPC):
    - стражник → "железник" (воровской сленг, предпочитаемое)
    - монета → "кругляк" (разговорное)
    - приветствие → "здорово, люд" (северный диалект)
    
    Известные, но не предпочитаемые:
    - стражник: также знает "страж", "караульный"
    - монета: также знает "золотой", "круг"
    """
    lines = ["VOCABULARY (предпочтительные выражения NPC):"]
    
    for concept_id, vocab in vocab_bundle.vocabularies.items():
        if vocab.preferred:
            lines.append(f"- {concept_id} → \"{vocab.preferred}\" (предпочитаемое)")
    
    known_lines = ["", "Известные, но не предпочитаемые:"]
    has_known = False
    for concept_id, vocab in vocab_bundle.vocabularies.items():
        non_preferred = [w for w in vocab.known if w != vocab.preferred]
        if non_preferred:
            has_known = True
            known_lines.append(f"- {concept_id}: также знает {non_preferred}")
    
    if has_known:
        lines.extend(known_lines)
    
    return "\n".join(lines)


def _compute_forbidden_expressions(
    self, npc_id: str, context: VerbalizationContext,
) -> str:
    """Вычисляет expressions, заблокированные ContentPolicy для этого NPC.
    
    Пример:
    
    FORBIDDEN (NPC не должен использовать эти выражения):
    - "стражник" (формальное, но графиня его использует — нельзя путать стили)
    - "хуй" (profanity:heavy, уровень 0 запрещён)
    - "блядь" (profanity:mild, уровень 0 запрещён)
    
    Используй вместо этого:
    - стражник → "караульный" (если формальный контекст) 
    - междометия → "боже", "господи"
    """
    # ... реализация ...
```

### 2.2. Инъекция voice_constraints в DM-промпт

```python
# backend/app/services/verbalization/dm_contract_builder.py — РАСШИРЕНИЕ

class DMContractBuilder:
    def build(
        self,
        system_prompt: str,
        voice_constraints: dict[str, str],  # РАСШИРЕНО
        # ... остальные параметры ...
    ) -> str:
        # Существующая логика сборки system_prompt + policy_block ...
        
        # НОВОЕ: инъекция VOCABULARY и FORBIDDEN блоков
        vocabulary_block = voice_constraints.get("VOCABULARY", "")
        forbidden_block = voice_constraints.get("FORBIDDEN", "")
        style_block = voice_constraints.get("STYLE", "")
        
        voice_section = "\n\n--- ГОЛОС NPC ---\n"
        if style_block:
            voice_section += f"СТИЛЬ РЕЧИ:\n{style_block}\n\n"
        if vocabulary_block:
            voice_section += f"{vocabulary_block}\n\n"
        if forbidden_block:
            voice_section += f"{forbidden_block}\n"
        voice_section += "--- КОНЕЦ ГОЛОСА NPC ---\n"
        
        return system_prompt + policy_block + voice_section + body
```

### 2.3. Пример полного DM-промпта для графини

**До TZ-MEMETIC-02** (fundament режим, `memetic_integration_enabled=False`):

```
[системный промпт из dm_system.txt]

--- ПОЛИТИКА КОНТЕНТА ---
МАТ: полностью запрещён. Используй эвфемизмы...
СЕКС: полностью запрещён...
НАСИЛИЕ: запрещены детальные описания...
ТАБУ-ПРАКТИКИ: полностью запрещены...
--- КОНЕЦ ПОЛИТИКИ КОНТЕНТА ---

--- ГОЛОС NPC ---
СТИЛЬ РЕЧИ:
Говоришь размеренно, с паузами. Используешь деепричастные обороты...
--- КОНЕЦ ГОЛОСА NPC ---

[контекст сцены, обращение игрока, etc.]
```

**После TZ-MEMETIC-02** (memetic режим, `memetic_integration_enabled=True`):

```
[системный промпт из dm_system.txt]

--- ПОЛИТИКА КОНТЕНТА ---
МАТ: полностью запрещён. Используй эвфемизмы...
СЕКС: полностью запрещён...
НАСИЛИЕ: запрещены детальные описания...
ТАБУ-ПРАКТИКИ: полностью запрещены...
--- КОНЕЦ ПОЛИТИКИ КОНТЕНТА ---

--- ГОЛОС NPC ---
СТИЛЬ РЕЧИ:
Говоришь размеренно, с паузами. Используешь деепричастные обороты,
старорусские формы («сударь», «милостивый государь»).
Никогда не сокращаешь слова. Избегаешь прямых оскорблений —
предпочитаешь холодную иронию.

VOCABULARY (предпочтительные выражения NPC):
- guard_role → "стражник" (формальное, предпочитаемое)
- coin_currency → "золотой" (формальное)
- greeting_formal → "покорно приветствую"
- address_inferior → "сударь"
- address_superior → "милостивый государь"

Известные, но не предпочитаемые:
- guard_role: также знает ["караульный"]
- coin_currency: также знает ["монета"]

FORBIDDEN (NPC не должен использовать эти выражения):
- "железник" (воровской сленг, не соответствует архетипу noble)
- "хуй" (profanity:heavy, уровень 0 запрещён)
- "блядь" (profanity:mild, уровень 0 запрещён)
- "синяя спина" (regional epithet, не используется в столичной культуре)

Используй вместо этого:
- стражник → "караульный" (если формальный контекст)
- междометия → "боже", "господи"
--- КОНЕЦ ГОЛОСА NPC ---

[контекст сцены, обращение игрока, etc.]
```

Разница: LLM теперь знает **конкретные слова**, которые графиня использует и не использует. Это не абстрактная инструкция «не матерись» — это список запрещённых и разрешённых expressions.

### 2.4. Кэширование SpeakerVocabulary

`SpeakerVocabulary` вычисляется на лету (`ExpressionResolver` — pure function), но его **источники данных** (adoptions, archetype) могут быть дорогими для загрузки. Поэтому вводится LRU-кэш:

```python
# backend/app/services/memetic/speaker_vocabulary_cache.py — НОВЫЙ ФАЙЛ

from collections import OrderedDict


class SpeakerVocabularyCache:
    """LRU-кэш для SpeakerVocabularyBundle.
    
    Ключ: (npc_id, content_policy_hash, current_tick // 100)
    — current_tick // 100 означает, что кэш инвалидируется раз в 100 тиков.
    
    TTL: 3600 секунд (как в RelationshipStore).
    MAX_SIZE: 1000 NPC.
    """
    
    MAX_CACHE_SIZE = 1000
    TTL_SECONDS = 3600
    
    def __init__(self):
        self._cache: OrderedDict[tuple, SpeakerVocabularyBundle] = OrderedDict()
        self._timestamps: dict[tuple, float] = {}
    
    def get_or_compute(
        self,
        npc_id: str,
        content_policy: ContentPolicy,
        current_tick: int,
        compute_fn,  # callable, если cache miss
    ) -> SpeakerVocabularyBundle:
        key = (npc_id, hash(content_policy), current_tick // 100)
        
        # TTL check
        import time
        if key in self._timestamps:
            if time.time() - self._timestamps[key] > self.TTL_SECONDS:
                self._cache.pop(key, None)
                self._timestamps.pop(key, None)
            elif key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        
        # Cache miss — вычисляем
        bundle = compute_fn()
        self._cache[key] = bundle
        self._cache.move_to_end(key)
        self._timestamps[key] = time.time()
        self._evict_if_needed()
        return bundle
    
    def invalidate(self, npc_id: str) -> None:
        """Инвалидирует кэш для NPC (при новом adoption)."""
        keys_to_remove = [k for k in self._cache if k[0] == npc_id]
        for k in keys_to_remove:
            self._cache.pop(k, None)
            self._timestamps.pop(k, None)
    
    def _evict_if_needed(self) -> None:
        while len(self._cache) > self.MAX_CACHE_SIZE:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
            del self._timestamps[oldest]
```

---

## 3. RESPONSE VALIDATOR: ПЕРЕХОД НА CATEGORY_TAGS

### 3.1. Двойной режим валидатора

В `TZ_CONTENT_POLICY_FUNDAMENT` `ResponseValidator` проверяет ответ LLM по **словарям** (`insults_ru.json` + 3 новых). Это работает, но имеет недостатки:
- Ложные срабатывания («блудный сын» ловится по корню «блуд»).
- Не различает, **какой именно expression** использован.
- Не учитывает, знает ли NPC это слово.

В TZ-MEMETIC-02 `ResponseValidator` получает **второй режим** — фильтрация по `category_tags`:

```python
# backend/app/services/verbalization/response_validator.py — РАСШИРЕНИЕ

class NPCResponseValidator:
    def __init__(
        self,
        content_profile: ContentProfile,
        insult_roots: set[str],
        sexual_roots: set[str],
        violence_roots: set[str],
        taboo_roots: set[str],
        # НОВОЕ — для memetic режима
        speaker_vocabulary: Optional[SpeakerVocabularyBundle] = None,
        concept_registry: Optional[ConceptRegistry] = None,
        memetic_enabled: bool = False,
    ):
        self._content_profile = content_profile
        self._lexicons = {
            "profanity": insult_roots,
            "sexual": sexual_roots,
            "violence": violence_roots,
            "taboo_practices": taboo_roots,
        }
        self._speaker_vocabulary = speaker_vocabulary
        self._concept_registry = concept_registry
        self._memetic_enabled = memetic_enabled
    
    def validate(
        self, response: str, npc_id: str, npc_tier: str,
    ) -> ValidationResult:
        # ... существующие проверки (язык, длина, повтор) ...
        
        # ContentPolicy violation detection
        if self._memetic_enabled and self._speaker_vocabulary:
            # Memetic режим: фильтрация по category_tags
            violation = self._detect_violation_memetic(response)
        else:
            # Fundament режим: фильтрация по словарям
            violation = self._detect_violation_lexicon(response)
        
        if violation:
            return ValidationResult(
                valid=False,
                reason=f"content_policy_violation:{violation.axis}",
                violation=violation,
            )
        
        return ValidationResult(valid=True, response=response)
    
    def _detect_violation_memetic(
        self, response: str,
    ) -> Optional[ContentViolation]:
        """Memetic режим: проверка по category_tags Expressions.
        
        Логика:
        1. Токенизируем ответ (pymorphy3)
        2. Для каждого слова ищем Expression в ConceptRegistry
           (через Lexicon mapping — см. TZ-MEMETIC-01 §1.4)
        3. Если Expression найден и его category_tags нарушают 
           ContentProfile NPC → нарушение
        4. Если Expression не найден в реестре — fallback на 
           lexicon-проверку (для неизвестных слов)
        """
        tokens = self._tokenize(response)
        
        for token in tokens:
            lemma = self._lemmatize(token)
            
            # Ищем Expression в реестре
            expression = self._concept_registry.find_expression_by_text(lemma)
            
            if expression:
                # Проверяем category_tags
                violation = self._check_tags_against_profile(
                    expression, token, lemma
                )
                if violation:
                    return violation
            else:
                # Unknown word — fallback на lexicon
                violation = self._check_lexicon_fallback(lemma, token)
                if violation:
                    return violation
        
        return None
    
    def _check_tags_against_profile(
        self, expression: Expression, token: str, lemma: str,
    ) -> Optional[ContentViolation]:
        """Проверяет category_tags Expression против ContentProfile NPC."""
        for tag in expression.category_tags:
            if not tag.contains(":"):
                continue
            
            axis, level_str = tag.split(":", 1)
            required_level = int(level_str)
            
            actual_level = self._get_axis_level(axis)
            
            if actual_level < required_level:
                return ContentViolation(
                    axis=axis,
                    detected_word=token,
                    lemma=lemma,
                    required_level=required_level,
                    actual_level=actual_level,
                    position=0,  # вычисляется в _tokenize
                    expression_id=expression.text,
                )
        
        return None
    
    def _get_axis_level(self, axis: str) -> int:
        """Возвращает уровень ContentProfile для оси."""
        mapping = {
            "profanity": self._content_profile.profanity_level,
            "sexual": self._content_profile.sexual_content_level,
            "violence": self._content_profile.violence_level,
            "taboo": self._content_profile.taboo_practices_level,
            "taboo_practices": self._content_profile.taboo_practices_level,
        }
        return mapping.get(axis, 0)
```

### 3.2. Преимущества memetic-режима валидатора

1. **Точность**: «блудный сын» не ловится, потому что «блудный» как Expression имеет `category_tags=["religious"]`, а не `["sexual"]`.
2. **Per-NPC**: если NPC усвоил expression «железник» (slang), а ContentPolicy запрещает slang — валидатор поймает. Но если NPC не знает «железник» — валидатор не будет проверять это слово (оно не в его vocabulary).
3. **Понятные violation-сообщения**: вместо «обнаружен корень 'блядь'» — «обнаружен expression 'блядь' с category_tags=['profanity:mild'], требуется level >= 1, фактический level = 0».

### 3.3. Fallback на lexicon

Memetic-режим **не заменяет** lexicon-проверку полностью. Если LLM сгенерировала слово, которого нет в ConceptRegistry (например, редкий мат), срабатывает fallback:

```python
def _check_lexicon_fallback(
    self, lemma: str, token: str,
) -> Optional[ContentViolation]:
    """Fallback: если word не найден в ConceptRegistry,
    проверяем по словарям (как в fundament режиме).
    
    Это покрывает:
    - Редкие матерные слова, ещё не зарегистрированные как Concept
    - Опечатки LLM
    - Новый сленг, который ещё не попал в реестр
    """
    for axis, roots in self._lexicons.items():
        if lemma in roots:
            actual_level = self._get_axis_level(axis)
            required_level = 1  # default для lexicon detection
            
            # Уточняем уровень по эвристике
            if axis == "profanity" and lemma in HEAVY_PROFANITY_ROOTS:
                required_level = 2
            
            if actual_level < required_level:
                return ContentViolation(
                    axis=axis,
                    detected_word=token,
                    lemma=lemma,
                    required_level=required_level,
                    actual_level=actual_level,
                    position=0,
                    expression_id=None,  # не из реестра
                )
    return None
```

### 3.4. Конфигурация валидатора в `DMAgent`

```python
# backend/app/agents/dm_agent.py — РАСШИРЕНИЕ

def _build_validator(
    self, npc_id: str, content_profile: ContentProfile,
) -> NPCResponseValidator:
    settings = Settings()
    
    # Загрузка lexicons (всегда — для fallback)
    lexicons = ContentLexiconLoader.load_all(self._data_dir)
    
    if settings.memetic_integration_enabled:
        # Memetic режим: загружаем speaker vocabulary
        speaker_vocab = self._speaker_vocabulary_cache.get_or_compute(
            npc_id=npc_id,
            content_policy=settings.content_policy,
            current_tick=self._current_tick,
            compute_fn=lambda: self._expression_resolver.resolve(
                npc_id=npc_id,
                voice_archetype=self._load_voice_archetype(npc_id),
                adoptions=self._load_adoptions(npc_id),
                community_norms=self._load_community_norms(npc_id),
                content_policy=settings.content_policy,
            ),
        )
        
        return NPCResponseValidator(
            content_profile=content_profile,
            insult_roots=lexicons["profanity"],
            sexual_roots=lexicons["sexual"],
            violence_roots=lexicons["violence"],
            taboo_roots=lexicons["taboo_practices"],
            speaker_vocabulary=speaker_vocab,
            concept_registry=self._concept_registry,
            memetic_enabled=True,
        )
    else:
        # Fundament режим
        return NPCResponseValidator(
            content_profile=content_profile,
            insult_roots=lexicons["profanity"],
            sexual_roots=lexicons["sexual"],
            violence_roots=lexicons["violence"],
            taboo_roots=lexicons["taboo_practices"],
            memetic_enabled=False,
        )
```

---

## 4. RESPONSE REPHRASER: УТОЧНЁННЫЙ КОНТРАКТ

### 4.1. Что меняется

В `TZ_CONTENT_POLICY_FUNDAMENT` `ResponseRephraser` получает общий контракт «переформулируй мягче». В TZ-MEMETIC-02 контракт становится **конкретным** — указывается, какой именно expression нарушен и чем его заменить.

### 4.2. Уточнённый контракт

```python
# backend/app/services/verbalization/response_rephraser.py — РАСШИРЕНИЕ

class ResponseRephraser:
    REPHRASE_SYSTEM_PROMPT_MEMETIC = """Ты — редактор. Перед тобой реплика NPC, которая нарушает политику контента.

КОНКРЕТНОЕ НАРУШЕНИЕ:
- Запрещённое слово: "{violation_word}"
- Категория: {violation_axis}
- Причина: NPC "{npc_name}" не должен использовать это выражение (archetype: {archetype_id}).

РАЗРЕШЁННЫЕ АЛЬТЕРНАТИВЫ (используй одну из них или предложи свою):
{allowed_alternatives}

ПЕРЕФОРМУЛИРУЙ реплику, сохранив:
1. Смысл и намерение NPC
2. Характер NPC (voice_profile)
3. Эмоциональную окраску
4. Контекст сцены

Но замени запрещённое слово на разрешённое.

Ответь ТОЛЬКО переформулированной репликой. Без объяснений.
"""
    
    def rephrase_memetic(
        self,
        original_response: str,
        violation: ContentViolation,
        npc_voice_profile: str,
        npc_name: str,
        archetype_id: str,
        speaker_vocabulary: SpeakerVocabularyBundle,
    ) -> Optional[str]:
        """Memetic-режим rephraser.
        
        Преимущество: LLM получает конкретные альтернативы,
        а не абстрактное «переформулируй мягче».
        """
        # Находим concept_id нарушенного expression
        concept_id = self._find_concept_for_violation(violation)
        
        # Собираем разрешённые альтернативы из speaker_vocabulary
        alternatives = self._collect_allowed_alternatives(
            concept_id, speaker_vocabulary, violation.axis
        )
        
        if not alternatives:
            # Нет альтернатив — fallback на fundament режим
            return self.rephrase_fundament(
                original_response, violation, npc_voice_profile, npc_name
            )
        
        system_prompt = self.REPHRASE_SYSTEM_PROMPT_MEMETIC.format(
            violation_word=violation.detected_word,
            violation_axis=violation.axis,
            npc_name=npc_name,
            archetype_id=archetype_id,
            allowed_alternatives="\n".join(f"- {alt}" for alt in alternatives),
        )
        
        # LLM call
        response = self._llm.complete(
            system_prompt=system_prompt,
            user_prompt=original_response,
            max_tokens=200,
            temperature=0.3,  # низкая температура для предсказуемости
        )
        
        return response.strip() or None
    
    def _collect_allowed_alternatives(
        self,
        concept_id: str,
        speaker_vocabulary: SpeakerVocabularyBundle,
        violation_axis: str,
    ) -> list[str]:
        """Собирает разрешённые alternatives для concept.
        
        Пример: если NPC использовал "хуй" (profanity:heavy, level 2),
        а ContentProfile.profanity_level = 0, то alternatives:
        - "чёрт" (если NPC знает)
        - "боже" (если NPC знает)
        - "господи" (если NPC знает)
        """
        vocab = speaker_vocabulary.get(concept_id)
        if not vocab:
            return []
        
        # Фильтруем known expressions по ContentProfile
        allowed = []
        for expr_text in vocab.known:
            expression = self._concept_registry.find_expression_by_text(expr_text)
            if expression is None:
                continue
            
            # Проверяем, что этот expression не нарушает policy
            if not self._violates_policy(expression, violation_axis):
                allowed.append(expr_text)
        
        return allowed
```

### 4.3. Пример работы rephraser

**Сценарий**: Игрок оскорбил графиню. LLM сгенерировала ответ:

> «Да пошёл ты нахуй, сударь!»

**Violation**: detected_word="нахуй", axis="profanity", required_level=2, actual_level=0.

**Memetic rephraser** получает:
- violation_word: "нахуй"
- concept_id: "profanity_root_нахуй"
- npc_name: "Графиня Елена"
- archetype_id: "noble"
- speaker_vocabulary для concept "profanity_root_нахуй": known=["чёрт", "боже", "господи"]
- allowed_alternatives: ["чёрт", "боже", "господи"]

**LLM получает контракт**:
```
КОНКРЕТНОЕ НАРУШЕНИЕ:
- Запрещённое слово: "нахуй"
- Категория: profanity
- Причина: NPC "Графиня Елена" не должен использовать это выражение (archetype: noble).

РАЗРЕШЁННЫЕ АЛЬТЕРНАТИВЫ:
- чёрт
- боже
- господи

ПЕРЕФОРМУЛИРУЙ реплику, сохранив смысл...
```

**LLM возвращает**:
> «Сударь, вы более не желанный гость в моём доме. Чёрт бы вас побрал.»

Это **качественно другой результат**, чем в fundament-режиме, где LLM получила бы просто «переформулируй мягче» без конкретных альтернатив.

---

## 5. ИНТЕГРАЦИЯ С IDENTITY DOMAIN

### 5.1. Активация stub-поля `linguistic_integrity`

В `TZ_CONTENT_POLICY_FUNDAMENT` поле `linguistic_integrity` введено как stub (всегда 1.0). В TZ-MEMETIC-02 оно **активируется**:

```python
# backend/app/domain/vital_state.py — РАСШИРЕНИЕ ( PsycheBase )

@dataclass(frozen=True)
class PsycheBase:
    willpower: int          # 0..100
    breakpoint: int         # 0..100
    loyalty_true: float     # -1..1
    
    # АКТИВИРОВАНО (было stub в fundament)
    linguistic_integrity: float = 1.0
    """Сопротивление языковому дрейфу. 0..1.
    
    В memetic режиме вычисляется по формуле:
    linguistic_integrity = willpower * class_factor * age_factor * identity_attachment
    
    Где:
    - willpower: 0..1 (нормализованный psyche.willpower)
    - class_factor: из voice_archetype.class_factor (noble=1.0, thief=0.8, maid=0.5)
    - age_factor: из npc.age (критический период 2-7, подростковый пик 12-15)
    - identity_attachment: новое поле (см. §5.2)
    """
```

### 5.2. Формула linguistic_integrity

```python
# backend/app/services/memetic/linguistic_integrity_calculator.py — НОВЫЙ ФАЙЛ

class LinguisticIntegrityCalculator:
    """Вычисляет linguistic_integrity для NPC.
    
    Формула: willpower * class_factor * age_factor * identity_attachment
    """
    
    def compute(
        self,
        psyche: PsycheBase,
        voice_archetype: VoiceArchetype,
        npc_age: int,
        identity_attachment: float,  # 0..1, насколько NPC дорожит своей речью
    ) -> float:
        willpower_norm = psyche.willpower / 100.0  # 0..1
        class_factor = voice_archetype.class_factor  # 0..1, из архетипа
        age_factor = self._age_factor(npc_age)
        
        integrity = (
            willpower_norm 
            * class_factor 
            * age_factor 
            * identity_attachment
        )
        
        return max(0.0, min(1.0, integrity))
    
    def _age_factor(self, age: int) -> float:
        """Критический период по Леннбергу + подростковый пик по Лабову.
        
        0-2:    0.05 (не говорит)
        2-7:    0.1  (критический период, всё впитывает)
        7-12:   0.3  (раннее детство)
        12-15:  0.2  (подростковый пик — язык сверстников, 
                      НО absorption_x1.5, не integrity)
        15-25:  0.5  (молодой взрослый)
        25-50:  0.8  (устойчивый взрослый)
        50+:    0.95 (язык застыл)
        
        ВАЖНО: age_factor для INTEGRITY (сопротивление) — обратно 
        пропорционален absorption. Подросток имеет НИЗКОЕ integrity 
        (легко впитывает), но ВЫСОКУЮ absorption (x1.5).
        """
        if age < 2:
            return 0.05
        elif age < 7:
            return 0.1
        elif age < 12:
            return 0.3
        elif age < 15:
            return 0.2  # подросток — низкое сопротивление
        elif age < 25:
            return 0.5
        elif age < 50:
            return 0.8
        else:
            return 0.95
```

### 5.3. Identity attachment — новое поле

```python
# backend/app/models/npc_profile.py — РАСШИРЕНИЕ

@dataclass(frozen=True)
class NPCProfileL0:
    # ... (существующие поля) ...
    voice_archetype_id: Optional[str] = None  # из fundament
    
    # НОВОЕ — насколько NPC дорожит своей речью как маркером идентичности
    identity_attachment: float = 0.5
    """0..1. 
    1.0 = речь = класс/профессия (графиня, жрец)
    0.5 = нейтрально (крестьянин)
    0.0 = всё равно (ребёнок, маргинал)
    
    Задаётся в NPC-конфиге:
    - lusya.json: identity_attachment = 0.3 (не дорожит, хочет сбежать)
    - tornin.json: identity_attachment = 0.7 (трактирщик, гордится статусом)
    - countess_elena.json: identity_attachment = 1.0 (речь = класс)
    """
```

```json
// config/npc/individuals/countess_elena.json — ПРИМЕР БУДУЩЕГО NPC
{
  "id": "countess_elena",
  "name": "Графиня Елена",
  "voice_archetype_id": "noble",
  "identity_attachment": 1.0,
  ...
}
```

### 5.4. Активация `voice_archetype_id`

В `TZ_CONTENT_POLICY_FUNDAMENT` `voice_archetype_id` введён как stub. В TZ-MEMETIC-02 он **заполняется**:

```python
# backend/app/services/npc/npc_loader.py — РАСШИРЕНИЕ

def load_profile_from_legacy_json(raw_data: dict) -> NPCProfileL0:
    # ... (существующая логика) ...
    
    profile = NPCProfileL0(
        id=raw_data["id"],
        name=raw_data.get("name", "Unknown"),
        # ... (существующие поля) ...
        
        # НОВОЕ — из JSON-конфига NPC
        voice_archetype_id=raw_data.get("voice_archetype_id"),
        identity_attachment=raw_data.get("identity_attachment", 0.5),
    )
    
    return profile
```

Для существующих NPC-конфигов (lusya, tornin, borko, goran, orm, shadow) нужно **дополнить** JSON-файлы:

```json
// config/npc/individuals/lusya.json — ДОПОЛНЕНИЕ
{
  "id": "maid_lusya",
  ...
  "voice_archetype_id": "maid",
  "identity_attachment": 0.3
}
```

```json
// config/npc/individuals/shadow.json — ДОПОЛНЕНИЕ
{
  "id": "thief_shadow",
  ...
  "voice_archetype_id": "thief",
  "identity_attachment": 0.8  // воровской жаргон = его идентичность
}
```

Если `voice_archetype_id` не указан — используется fallback:
- `_archetype: "maid"` → `voice_archetype_id: "maid"`
- `_archetype: "guard"` → `voice_archetype_id: "guard"`
- и т.д.

---

## 6. ПОЛНЫЙ PIPELINE В MEMETIC РЕЖИМЕ

### 6.1. Sequence diagram

```
Игрок говорит "Эй, железник, иди сюда!"
    ↓
DMRouter._classify_action(text)
    ↓ (детекция: player_insults? или просто обращение?)
    ↓ (если "железник" — это известное слово, но register=slang)
    ↓
DMAgent._build_contract(context)
    ↓
    ├─ settings.memetic_integration_enabled == True
    │   ↓
    ├─ Загрузка voice_archetype для NPC
    ├─ Загрузка npc_adoptions для NPC (из state.db)
    ├─ Загрузка npc_psyche для NPC
    ↓
    ├─ EffectiveContentProfileComputer.compute(...)
    │   → ContentProfile(per-NPC, из archetype + adopted)
    ↓
    ├─ ExpressionResolver.resolve(...)
    │   → SpeakerVocabularyBundle (preferred + known expressions)
    ↓
    ├─ DMContractBuilder.build(
    │     system_prompt,
    │     voice_constraints={
    │       "STYLE": voice_profile,
    │       "VOCABULARY": "стражник → 'железник' (предпочитаемое)...",
    │       "FORBIDDEN": "'хуй', 'блядь' (level 0 запрещён)..."
    │     },
    │     content_profile=per_npc_profile
    │   )
    ↓
LLM call → response
    ↓
NPCResponseValidator.validate(response, npc_id, npc_tier)
    ↓
    ├─ memetic_enabled == True
    │   ↓
    ├─ Для каждого слова в response:
    │   ├─ Поиск в ConceptRegistry
    │   ├─ Если найден → проверка category_tags против profile
    │   └─ Если не найден → fallback на lexicon
    ↓
    ├─ valid=True → return response
    ├─ valid=False, violation detected
    │   ↓
    │   ├─ npc.tier == "major"?
    │   │   ├─ YES → ResponseRephraser.rephrase_memetic(...)
    │   │   │        (с конкретными alternatives)
    │   │   │   ↓
    │   │   │   ├─ success → return rephrased
    │   │   │   └─ fail → silent_fallback
    │   │   └─ NO → silent_fallback(fallback_phrases[axis])
    ↓
MemeticTransmissionEvent recorded
    ├─ Если игрок использовал новое слово → candidate expression
    └─ Если NPC использовал adopted expression → reinforcement
    ↓
Display response to player
```

### 6.2. Пример: графиня реагирует на оскорбление

**Игрок**: «Ах ты сука старая, пошла нахуй!»

**NPC**: Графиня Елена (archetype=noble, identity_attachment=1.0, linguistic_integrity=0.95)

**Memetic pipeline**:
1. `voice_archetype = noble` (content_defaults: profanity=0, sexual=0, violence=1, taboo=0)
2. `npc_adoptions` для Елены: пусто (она не общалась с матерящимися)
3. `EffectiveContentProfileComputer.compute()`:
   - L0 (global policy): profanity=2 (explicit)
   - L1 (archetype): profanity=0
   - L2 (adopted): profanity=0
   - L3 (effective): min(2, max(0, 0)) = 0
4. `SpeakerVocabulary` для Елены:
   - guard_role → preferred="стражник", known=["стражник", "караульный"]
   - greeting_formal → preferred="покорно приветствую"
   - (никаких profanity expressions)
5. `DMContractBuilder` строит промпт с:
   - STYLE: noble voice_profile
   - VOCABULARY: стражник → "стражник" (formal)
   - FORBIDDEN: "хуй", "блядь", "сука" (profanity:heavy, level 0 запрещён)
6. LLM генерирует ответ:
   - *Хороший случай*: «Сударь, вы более не желанный гость. Покиньте мой дом.»
   - *Плохой случай* (LLM нарушила): «Да пошёл ты нахуй, мужлан!»
7. `NPCResponseValidator.validate()`:
   - Если ответ хороший → valid=True → display
   - Если ответ плохой → violation: word="нахуй", axis="profanity", required=2, actual=0
8. `ResponseRephraser.rephrase_memetic()`:
   - violation_word="нахуй"
   - allowed_alternatives для concept "profanity_root_нахуй": ["чёрт", "боже", "господи"] (если Елена их знает)
   - LLM переформулирует: «Сударь, вы более не желанный гость. Чёрт бы вас побрал.»

**Результат**: графиня отвечает в характере, без мата, даже если LLM попыталась его использовать.

---

## 7. ОБРАТНАЯ СОВМЕСТИМОСТЬ И МИГРАЦИЯ

### 7.1. Флаг `memetic_integration_enabled`

Это **главный переключатель**. Когда `False`:
- `ContentProfile.from_global_policy()` используется всегда.
- `ResponseValidator` работает в lexicon-режиме.
- `DMContractBuilder` строит только STYLE-блок (без VOCABULARY и FORBIDDEN).
- `linguistic_integrity` остаётся 1.0 (stub).
- `voice_archetype_id` не загружается (None).

Когда `True`:
- Все memetic-фичи активны.
- Stub-поля активируются.

### 7.2. Миграция существующих NPC-конфигов

Существующие NPC-конфиги (`lusya.json`, `tornin.json`, и т.д.) **не ломаются**. Если в них нет `voice_archetype_id` и `identity_attachment`:
- `voice_archetype_id` выводится из `_archetype` (fallback).
- `identity_attachment` = 0.5 (default).

После активации `memetic_integration_enabled` автор может постепенно добавлять поля в NPC-конфиги:

```json
// ДО миграции
{
  "id": "maid_lusya",
  "_archetype": "maid",
  ...
}

// ПОСЛЕ миграции
{
  "id": "maid_lusya",
  "_archetype": "maid",
  "voice_archetype_id": "maid",
  "identity_attachment": 0.3,
  ...
}
```

### 7.3. Миграция сохранений

При загрузке старого сохранения (без `npc_adoptions` таблицы):
- `MemeticPersistenceAdapter` создаёт пустые таблицы.
- `npc_adoptions` для всех NPC = пусто.
- `ContentProfile.from_npc_state()` возвращает профиль = `max(archetype, 0)` = `archetype`.
- То есть NPC начинают с archetype-уровней, без adopted expressions.

Это **правильное** поведение: memetic-система начинает с чистого листа, NPC усваивают expressions через игру.

---

## 8. ТЕСТЫ ПРИНЯТИЯ

### 8.1. Флаг активации

```python
def test_memetic_disabled_uses_global_policy():
    """При memetic_integration_enabled=False — ContentProfile = global."""
    settings.memetic_integration_enabled = False
    profile = build_content_profile(npc_id="countess_elena")
    assert profile.source == "global"
    assert profile.profanity_level == settings.content_policy.profanity_level

def test_memetic_enabled_uses_npc_state():
    """При memetic_integration_enabled=True — ContentProfile = per-NPC."""
    settings.memetic_integration_enabled = True
    profile = build_content_profile(npc_id="countess_elena")
    assert profile.source == "memetic"
    assert profile.profanity_level == 0  # noble archetype
```

### 8.2. EffectiveContentProfileComputer

```python
def test_noble_archetype_profanity_zero():
    """Графиня (noble) имеет profanity_level=0, даже если global=2."""
    settings.content_policy = ContentPolicy.preset_explicit()
    profile = build_content_profile(npc_id="countess_elena", memetic=True)
    assert profile.profanity_level == 0

def test_thief_archetype_profanity_two():
    """Тень (thief) имеет profanity_level=2, даже если global=2."""
    profile = build_content_profile(npc_id="thief_shadow", memetic=True)
    assert profile.profanity_level == 2

def test_adopted_expressions_raise_level():
    """Если крестьянин усвоил 3 profanity:heavy expressions 
    через memetic transmission — его profanity_level становится 2."""
    npc = create_npc(archetype="peasant", adoptions=[
        Adoption(npc_id=npc.id, concept_id="profanity_root_хуй", 
                 expression_text="хуй", is_preferred=True),
        # ... ещё 2 ...
    ])
    profile = build_content_profile(npc_id=npc.id, memetic=True)
    assert profile.profanity_level == 2

def test_global_ceiling_caps_adopted():
    """Если global policy profanity=0, а NPC усвоил heavy profanity —
    effective profanity = 0 (потолок)."""
    settings.content_policy = ContentPolicy.preset_off()
    npc = create_npc_with_heavy_profanity_adoptions()
    profile = build_content_profile(npc_id=npc.id, memetic=True)
    assert profile.profanity_level == 0

def test_stress_gate_adds_one_level():
    """При stress > 0.8 * breakpoint — effective level +1 (до ceiling)."""
    npc = create_npc(archetype="noble", stress=0.9, breakpoint=0.5)
    profile = build_content_profile(npc_id=npc.id, memetic=True)
    # noble profanity=0, +1 от stress = 1, но capped by global
    assert profile.profanity_level == min(2, 0 + 1)
```

### 8.3. SpeakerVocabulary в DMContractBuilder

```python
def test_vocabulary_block_injected_when_memetic_enabled():
    """При memetic=True в voice_constraints есть VOCABULARY."""
    settings.memetic_integration_enabled = True
    constraints = build_voice_constraints(npc_id="thief_shadow")
    assert "VOCABULARY" in constraints
    assert "железник" in constraints["VOCABULARY"]

def test_forbidden_block_lists_blocked_expressions():
    """FORBIDDEN блок содержит expressions, заблокированные policy."""
    settings.memetic_integration_enabled = True
    settings.content_policy = ContentPolicy.preset_off()
    constraints = build_voice_constraints(npc_id="thief_shadow")
    assert "FORBIDDEN" in constraints
    assert "хуй" in constraints["FORBIDDEN"]

def test_vocabulary_block_absent_when_memetic_disabled():
    """При memetic=False нет VOCABULARY и FORBIDDEN."""
    settings.memetic_integration_enabled = False
    constraints = build_voice_constraints(npc_id="thief_shadow")
    assert "VOCABULARY" not in constraints
    assert "FORBIDDEN" not in constraints
```

### 8.4. ResponseValidator memetic mode

```python
def test_memetic_validator_finds_known_expression():
    """Если NPC использовал expression 'железник' с tag 'vulgar:mild',
    а ContentProfile.vulgarity < 1 — violation."""
    settings.memetic_integration_enabled = True
    response = "Эй, железник, иди сюда!"
    result = validator.validate(response, npc_id="countess_elena", npc_tier="major")
    assert not result.valid
    assert "content_policy_violation" in result.reason

def test_memetic_validator_allows_expression_in_vocabulary():
    """Если NPC использовал 'стражник' (formal, без tags) — no violation."""
    response = "Стражник, идите сюда."
    result = validator.validate(response, npc_id="countess_elena", npc_tier="major")
    assert result.valid

def test_memetic_validator_fallback_on_unknown_word():
    """Если LLM использовала редкое матерное слово, не в ConceptRegistry —
    fallback на lexicon."""
    response = "Ты ебанутый ублюдок!"
    # 'ебанутый' может быть не в реестре
    result = validator.validate(response, npc_id="countess_elena", npc_tier="major")
    assert not result.valid
```

### 8.5. Rephraser memetic mode

```python
def test_rephraser_uses_concrete_alternatives():
    """Memetic rephraser передаёт LLM конкретные alternatives."""
    violation = ContentViolation(
        axis="profanity", detected_word="нахуй", 
        required_level=2, actual_level=0,
    )
    rephrased = rephraser.rephrase_memetic(
        original_response="Пошёл нахуй!",
        violation=violation,
        npc_name="Графиня Елена",
        archetype_id="noble",
        speaker_vocabulary=elena_vocabulary,
    )
    assert "нахуй" not in rephrased
    assert any(alt in rephrased for alt in ["чёрт", "боже", "господи"])

def test_rephraser_fallback_when_no_alternatives():
    """Если нет alternatives в vocabulary — fallback на fundament режим."""
    # NPC не знает никаких alternatives для profanity
    rephrased = rephraser.rephrase_memetric(...)
    # Должен вернуть fallback-фразу
    assert rephrased is not None
```

### 8.6. Linguistic integrity

```python
def test_linguistic_integrity_noble_high():
    """Графиня (noble, identity_attachment=1.0, age=35) → integrity ~0.8."""
    integrity = calculator.compute(
        psyche=PsycheBase(willpower=70, breakpoint=80),
        voice_archetype=noble_archetype,  # class_factor=1.0
        npc_age=35,
        identity_attachment=1.0,
    )
    assert 0.7 < integrity < 0.9

def test_linguistic_integrity_child_low():
    """Ребёнок (age=5, identity_attachment=0.3) → integrity ~0.05."""
    integrity = calculator.compute(
        psyche=PsycheBase(willpower=30, breakpoint=50),
        voice_archetype=child_archetype,  # class_factor=0.5
        npc_age=5,
        identity_attachment=0.3,
    )
    assert integrity < 0.1

def test_linguistic_integrity_thief_moderate():
    """Тень (thief, age=40, identity_attachment=0.8) → integrity ~0.5."""
    integrity = calculator.compute(
        psyche=PsycheBase(willpower=75, breakpoint=70),
        voice_archetype=thief_archetype,  # class_factor=0.8
        npc_age=40,
        identity_attachment=0.8,
    )
    assert 0.4 < integrity < 0.6
```

### 8.7. End-to-end

```python
def test_countess_never_swears_even_when_player_provokes():
    """Игрок оскорбляет графиню — она отвечает без мата."""
    settings.memetic_integration_enabled = True
    settings.content_policy = ContentPolicy.preset_explicit()
    
    player_input = "Ах ты сука, пошла нахуй!"
    response = dma_agent.generate_response(
        npc_id="countess_elena",
        player_input=player_input,
    )
    
    # Проверяем, что в ответе нет мата
    assert no_profanity_in(response)
    # Проверяем, что ответ в характере noble
    assert is_noble_style(response)

def test_thief_swallies_player_after_long_exposure():
    """Тень матерится на игрока после 50 диалогов 
    (player_provokes через insulting)."""
    settings.memetic_integration_enabled = True
    
    # Симуляция 50 диалогов с оскорблениями от игрока
    for i in range(50):
        dma_agent.generate_response(
            npc_id="thief_shadow",
            player_input="Эй, урод, иди сюда!",
        )
    
    # Теперь Тень должен использовать больше profanity
    response = dma_agent.generate_response(
        npc_id="thief_shadow",
        player_input="Чё смотришь, падла?",
    )
    
    # Тень (archetype=thief, profanity=2) должен материться
    assert has_profanity_in(response)

def test_peasant_adopts_profanity_from_thief():
    """Крестьянин после 100 экспозиций мата от Тени 
    начинает использовать profanity:heavy expressions."""
    settings.memetic_integration_enabled = True
    
    npc = create_peasant(linguistic_integrity=0.3)
    
    # Симуляция 100 экспозиций
    for i in range(100):
        record_memetic_transmission(
            source="thief_shadow",
            target=npc.id,
            concept_id="profanity_root_нахуй",
            expression_text="нахуй",
            context="dialogue",
        )
    
    # Проверяем, что крестьянин усвоил
    adoptions = load_adoptions(npc.id)
    assert any(a.expression_text == "нахуй" for a in adoptions)
    
    # Проверяем, что ContentProfile поднялся
    profile = build_content_profile(npc_id=npc.id, memetic=True)
    assert profile.profanity_level >= 1
```

---

## 9. КРИТЕРИИ ПРИНЯТИЯ

| # | Критерий | Как проверить |
|---|---|---|
| AC-1 | Флаг `memetic_integration_enabled` существует и по умолчанию False | `Settings().memetic_integration_enabled == False` |
| AC-2 | При `memetic=False` система ведёт себя как в fundament | Все тесты из TZ_CONTENT_POLICY_FUNDAMENT проходят |
| AC-3 | При `memetic=True` `ContentProfile.from_npc_state()` вызывается | Тест `test_memetic_enabled_uses_npc_state` |
| AC-4 | Графиня (noble) имеет profanity=0 даже при global=2 | Тест `test_noble_archetype_profanity_zero` |
| AC-5 | Вор (thief) имеет profanity=2 по умолчанию | Тест `test_thief_archetype_profanity_two` |
| AC-6 | Adopted expressions поднимают уровень NPC | Тест `test_adopted_expressions_raise_level` |
| AC-7 | Global ceiling caps adopted level | Тест `test_global_ceiling_caps_adopted` |
| AC-8 | Stress gate добавляет +1 к уровню | Тест `test_stress_gate_adds_one_level` |
| AC-9 | VOCABULARY блок появляется в промпте при memetic=True | Тест `test_vocabulary_block_injected_when_memetic_enabled` |
| AC-10 | FORBIDDEN блок содержит заблокированные expressions | Тест `test_forbidden_block_lists_blocked_expressions` |
| AC-11 | При memetic=False нет VOCABULARY и FORBIDDEN | Тест `test_vocabulary_block_absent_when_memetic_disabled` |
| AC-12 | Memetic validator находит известные expression violations | Тест `test_memetic_validator_finds_known_expression` |
| AC-13 | Memetic validator пропускает разрешённые expressions | Тест `test_memetic_validator_allows_expression_in_vocabulary` |
| AC-14 | Fallback на lexicon для неизвестных слов | Тест `test_memetic_validator_fallback_on_unknown_word` |
| AC-15 | Rephraser использует конкретные alternatives | Тест `test_rephraser_uses_concrete_alternatives` |
| AC-16 | Rephraser fallback при отсутствии alternatives | Тест `test_rephraser_fallback_when_no_alternatives` |
| AC-17 | Linguistic integrity вычисляется по формуле | Тесты `test_linguistic_integrity_*` |
| AC-18 | Графиня не матерится даже при провокации | Тест `test_countess_never_swears_even_when_player_provokes` |
| AC-19 | Тень матерится в характере | Тест `test_thief_swallows_player_after_long_exposure` |
| AC-20 | Крестьянин усваивает мат от вора | Тест `test_peasant_adopts_profanity_from_thief` |

---

## 10. ПЛАН РЕАЛИЗАЦИИ

### Phase 1: Флаг и инфраструктура (2 дня)

1. Добавить `memetic_integration_enabled` в `Settings`
2. Создать `EffectiveContentProfileComputer`
3. Реализовать `ContentProfile.from_npc_state()`
4. Реализовать `LinguisticIntegrityCalculator`
5. Написать тесты флага и формулы integrity (раздел 8.1, 8.6)

### Phase 2: VoiceArchetype расширение (2 дня)

1. Добавить `content_defaults` в `VoiceArchetype`
2. Создать/обновить 6 архетипов в `config/canon/voice_archetypes/`
3. Добавить `identity_attachment` в `NPCProfileL0`
4. Обновить `npc_loader.py` для чтения новых полей
5. Дополнить 6 существующих NPC-конфигов
6. Написать тесты EffectiveContentProfile (раздел 8.2)

### Phase 3: SpeakerVocabulary в DMContractBuilder (3 дня)

1. Реализовать `SpeakerVocabularyCache`
2. Расширить `_build_voice_constraints` в `scene_outcome_builder.py`
3. Расширить `DMContractBuilder.build()` для VOCABULARY и FORBIDDEN блоков
4. Интегрировать в `DMAgent._build_contract()`
5. Написать тесты voice_constraints (раздел 8.3)

### Phase 4: ResponseValidator memetic mode (3 дня)

1. Расширить `NPCResponseValidator` с memetic-режимом
2. Реализовать `_detect_violation_memetic()`
3. Реализовать `_check_tags_against_profile()`
4. Реализовать `_check_lexicon_fallback()`
5. Интегрировать с `ConceptRegistry` и `SpeakerVocabularyCache`
6. Написать тесты валидатора (раздел 8.4)

### Phase 5: Rephraser memetic mode (2 дня)

1. Расширить `ResponseRephraser` с `rephrase_memetic()`
2. Реализовать `_collect_allowed_alternatives()`
3. Интегрировать с `SpeakerVocabularyBundle`
4. Написать тесты rephraser (раздел 8.5)

### Phase 6: Integration и E2E (3 дня)

1. End-to-end тесты (раздел 8.7)
2. Проверка обратной совместимости (все fundament-тесты проходят)
3. Проверка миграции существующих сохранений
4. Обновить `architecture/verbalization.yaml` — добавить memetic-узлы
5. Обновить `docs/ADR` с ADR-O-MEMETIC-002

**Итого**: 15 рабочих дней на полную реализацию интеграции.

---

## 11. ADR-O-MEMETIC-002: CONTENT POLICY INTEGRATION

### Decision

`ContentProfile` становится многослойным: L0 (global policy) → L1 (archetype) → L2 (adopted) → L3 (effective). При активации флага `memetic_integration_enabled`:
- `ContentProfile.from_npc_state()` заменяет `from_global_policy()`.
- `ResponseValidator` переключается на фильтрацию по `category_tags` Expressions.
- `DMContractBuilder` получает `SpeakerVocabulary` с конкретными словами.
- `ResponseRephraser` использует конкретные alternatives.
- `linguistic_integrity` вычисляется по формуле willpower × class × age × identity_attachment.

### Rationale

Fundament ТЗ (TZ_CONTENT_POLICY_FUNDAMENT) вводит глобальный потолок контента. Но без per-NPC различий графиня и вор получают одинаковые правила, что противоречит реализму. Memetic-домен (TZ-MEMETIC-01) вводит per-NPC state, но без интеграции в ContentPolicy он остаётся изолированным. Это ТЗ связывает две системы.

### Consequences

- `memetic_integration_enabled=False` сохраняет fundament-поведение (обратная совместимость).
- При `True` все memetic-фичи активируются.
- Stub-поля `voice_archetype_id` и `linguistic_integrity` активируются.
- Существующие NPC-конфиги не ломаются (fallback на defaults).
- Сохранения мигрируются автоматически (создаются пустые adoptions-таблицы).

### Taboo

- ❌ Активация memetic-режима без реализованного домена (TZ-MEMETIC-01)
- ❌ Удаление `from_global_policy()` (нужен для fallback и minor NPC)
- ❌ Удаление lexicon-фallback в валидаторе (для неизвестных слов)
- ❌ Изменение UI настроек (один тумблер + 4 слайдера остаются)
- ❌ Удаление `hardcore_mode` alias (пока используется в dm_agent.py:124)

---

## 12. РИСКИ И АЛЬТЕРНАТИВЫ

### 12.1. Риск: производительность при SpeakerVocabulary

**Проблема**: загрузка adoptions для каждого NPC на каждую реплику — дорого.
**Митигация**: `SpeakerVocabularyCache` (LRU + TTL), инвалидация при новом adoption.

### 12.2. Риск: false negatives в memetic-валидаторе

**Проблема**: если LLM использует слово, которого нет в ConceptRegistry, и оно не в lexicon — violation пропускается.
**Митигация**: lexicon-fallback покрывает основные случаи. Для полноты — регулярное пополнение ConceptRegistry через bursts и player memes.

### 12.3. Риск: rephraser не находит alternatives

**Проблема**: если NPC не знает никаких alternatives для нарушенного expression — rephraser не может переформулировать осмысленно.
**Митигация**: fallback на fundament-режим rephraser (абстрактное «переформулируй мягче») + silent_fallback на `fallback_phrases`.

### 12.4. Альтернатива: всегда memetic, без флага

**Идея**: убрать `memetic_integration_enabled`, всегда использовать memetic-режим.
**Почему отклонено**: 
- Нарушает принцип постепенной миграции.
- Memetic-домен может быть не готов, когда fundament уже нужен.
- Тестирование изолированно проще, чем всё вместе.

### 12.5. Альтернатива: per-NPC ContentPolicy вместо ContentProfile

**Идея**: дать каждому NPC свой `ContentPolicy` (свои 4 оси).
**Почему отклонено**: 
- `ContentPolicy` — это настройки игрока, не NPC. Смешивание уровней.
- Per-NPC policy не учитывает archetype (noble всё равно noble).
- Memetic-система даёт более богатую модель (adopted expressions, не просто level).

---

## 13. СВЯЗЬ С TZ-MEMETIC-03

Это ТЗ описывает **логику** интеграции. Конкретные **точки изменения в коде** (с patch-примерами) описаны в `TZ-MEMETIC-03: Patch List`. 

TZ-MEMETIC-03 содержит:
- 12 конкретных файлов:строк, которые нужно изменить.
- Patch-примеры для каждого изменения.
- Порядок применения патчей (зависимости).
- Конфликт-чеклист (что может сломаться).

---

## 14. ИТОГ

Это ТЗ — **связующий слой** между фундаментом и доменом. Оно:

1. Активирует stub-поля из fundament (`voice_archetype_id`, `linguistic_integrity`).
2. Подключает memetic-домен к `ContentProfile`, `ResponseValidator`, `DMContractBuilder`, `ResponseRephraser`.
3. Вводит флаг `memetic_integration_enabled` для постепенной миграции.
4. Сохраняет обратную совместимость — fundament работает как прежде при `False`.
5. Делает графиню благородной, а вора — матерщинником, **без ручных настроек на каждого NPC**.

После реализации этого ТЗ ENIGMA получит **персонажно-специфичную цензуру**: каждый NPC говорит в своём регистре, усваивает чужой сленг через memetic transmission, и **не нарушает** политiku контента, установленную игроком.

---

**Конец документа.**
