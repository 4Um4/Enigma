# ТЗ: PATCH LIST — ТОЧКИ ИЗМЕНЕНИЯ В КОДЕ (Patch List)

> **Проект:** ENIGMA / The Fool
> **Версия ТЗ:** 1.0
> **Статус:** PROPOSED
> **Дата:** 2026-07-03
> **Зависимости:**
> - `TZ_CONTENT_POLICY_FUNDAMENT.md`
> - `TZ_MEMETIC_01_Domain_Spec.md`
> - `TZ_MEMETIC_02_Content_Policy_Integration.md`
> **Критичность:** P0 — конкретные точки реализации
> **База:** кодовая база V.0.5.3.3.3 (`/home/z/my-project/enigma_v2/Enigma-V.0.5.3.3.3_-_-`)

---

## 0. НАЗНАЧЕНИЕ

Этот документ — **инженерный мост** между архитектурными ТЗ и реальным кодом. Он содержит:

- 12 конкретных точек изменения (file:line) в существующем коде
- 8 новых файлов, которые нужно создать
- Patch-примеры (before/after) для каждой точки
- Порядок применения патчей с учётом зависимостей
- Конфликт-чеклист (что может сломаться)
- Маппинг «патч → раздел ТЗ»

**Это не учебник и не теория.** Это рабочий документ для исполнителя, который садится и пишет код.

### 0.1. Соглашения

- Все пути — относительно корня проекта `Enigma-V.0.5.3.3.3_-_-/`.
- `BEFORE` — существующий код (с точными строками из V.0.5.3.3.3).
- `AFTER` — код после применения патча.
- `+` — добавленная строка.
- `-` — удалённая строка.
- `~` — изменённая строка.
- Номера строк в `BEFORE` актуальны для V.0.5.3.3.3. При мердже с новыми коммитами строки могут сдвинуться — ориентируйся на контекст.

### 0.2. Стратегия применения

```
Phase F (Fundament):  PATCH 01-07  → реализует TZ_CONTENT_POLICY_FUNDAMENT
Phase M (Memetic):    PATCH 08-12  → реализует TZ_MEMETIC_01 + TZ-MEMETIC-02
Phase T (Tests):      все тесты из всех ТЗ
```

Phase F можно реализовать **полностью независимо** от Phase M. После Phase F система уже работает (с глобальной политикой контента). Phase M добавляет memetic-интеграцию, активируемую флагом.

---

## 1. PATCH 01 — `backend/app/core/config.py` — ContentPolicy settings

**ТЗ-ссылка:** TZ_CONTENT_POLICY_FUNDAMENT §2.1, §3.4, §3.5
**Фаза:** F
**Зависимости:** нет
**Файл:** `backend/app/core/config.py`

### BEFORE (строки 1-3, 66-69)

```python
# RTX 3070 Ti (8 GB VRAM) + Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M
# AIDM Backend Configuration
# ...

class Settings(BaseSettings):
    # ...
    
    # ─────────────────────────────────────────────────────────────────
    # Content policy
    # ─────────────────────────────────────────────────────────────────
    hardcore_mode: bool = True
```

### AFTER

```python
# RTX 3070 Ti (8 GB VRAM) + Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M
# AIDM Backend Configuration
# ...
+ # NOTE: 'abliterated' = refusal mechanism removed via orthogonalized
+ # fine-tuning (Arditi et al. 2024). Model does not refuse explicit content.
+ # ContentPolicy (see content_policy.py) is the sole gatekeeper.

class Settings(BaseSettings):
    # ...
    
    # ─────────────────────────────────────────────────────────────────
    # Content policy
    # ─────────────────────────────────────────────────────────────────
+   # DEPRECATED — replaced by ContentPolicy in config/user_settings.yaml
+   # Kept for migration: load_content_policy() reads this if no content section.
    hardcore_mode: bool = True
    
+   # Path to user settings (Canon for content_policy_defaults, State for content)
+   user_settings_path: Path = BASE_DIR.parent / "config" / "user_settings.yaml"
+   
+   # Path to canon content policy defaults
+   content_policy_canon_path: Path = BASE_DIR.parent / "config" / "canon" / "content_policy_defaults.yaml"
+   
+   # Memetic integration flag (TZ-MEMETIC-02 §0.4)
+   # False = fundament mode (all NPC share global policy)
+   # True  = memetic mode (per-NPC ContentProfile from archetype + adopted)
+   memetic_integration_enabled: bool = False
+   
+   # Cached ContentPolicy (loaded lazily, invalidated on reload)
+   _content_policy_cache: Optional["ContentPolicy"] = None
+   
+   @property
+   def content_policy(self) -> "ContentPolicy":
+       """Returns cached ContentPolicy, loading from user_settings.yaml on first access."""
+       if self._content_policy_cache is None:
+           from app.core.content_policy import load_content_policy
+           self._content_policy_cache = load_content_policy(self)
+       return self._content_policy_cache
+   
+   def reload_content_policy(self) -> "ContentPolicy":
+       """Force reload. Called from settings_screen after user changes."""
+       from app.core.content_policy import load_content_policy
+       self._content_policy_cache = load_content_policy(self)
+       return self._content_policy_cache
```

### Конфликт-чеклист
- ⚠️ Если `Settings` — это Pydantic `BaseSettings`, нельзя добавлять `_content_policy_cache` как обычное поле (Pydantic будет требовать значение). Решение: использовать `PrivateAttr` или вынести кэш в модуль-level переменную.
- ⚠️ `BASE_DIR.parent` — проверь, что это корректный путь. Если `config.py` в `backend/app/core/`, то `BASE_DIR.parent.parent.parent` — корень проекта.

---

## 2. PATCH 02 — НОВЫЙ ФАЙЛ `backend/app/core/content_policy.py`

**ТЗ-ссылка:** TZ_CONTENT_POLICY_FUNDAMENT §2.1, §3.4
**Фаза:** F
**Зависимости:** PATCH 01

### Создать файл

Полное содержимое — см. TZ_CONTENT_POLICY_FUNDAMENT §2.1 (`ContentLevel`, `ContentPolicy` с пресетами и `hardcore_mode` alias property) + §3.4 (`load_content_policy` функция с миграцией).

Ключевые элементы:
- `class ContentLevel(IntEnum): OFF=0, MODERATE=1, EXPLICIT=2`
- `@dataclass(frozen=True) class ContentPolicy` с 4 осями и 3 пресетами
- `def load_content_policy(settings) -> ContentPolicy` с миграцией `hardcore_mode → preset`
- `def _save_content_section(path, policy, reason) -> None`
- `def _content_from_dict(data) -> ContentPolicy`
- `def _content_to_dict(policy, reason) -> dict`

### Проверка
```bash
python -c "from app.core.content_policy import ContentPolicy; \
print(ContentPolicy.preset_explicit().hardcore_mode)"
# → True
```

---

## 3. PATCH 03 — `backend/app/services/verbalization/verbalization_context.py` — расширение ContentProfile

**ТЗ-ссылка:** TZ_CONTENT_POLICY_FUNDAMENT §2.2, TZ-MEMETIC-02 §1.4
**Фаза:** F (база) + M (from_npc_state)
**Зависимости:** PATCH 02

### BEFORE (строки 21-31, 73)

```python
@dataclass(frozen=True)
class ContentProfile:
    """Профиль разрешённого контента для вербализации NPC."""
    profanity_level: int = 0
    violence_level: int = 0

    def __post_init__(self) -> None:
        if not (0 <= self.profanity_level <= 2):
            raise ValueError(f"profanity_level должен быть 0-2, получено: {self.profanity_level}")
        if not (0 <= self.violence_level <= 2):
            raise ValueError(f"violence_level должен быть 0-2, получено: {self.violence_level}")

# ... (строка 73) ...
@dataclass
class VerbalizationContext:
    # ...
    content_profile: ContentProfile = field(default_factory=ContentProfile)
```

### AFTER

```python
@dataclass(frozen=True)
class ContentProfile:
    """Профиль разрешённого контента для вербализации конкретного NPC.
    
    Fundament (TZ_CONTENT_POLICY_FUNDAMENT): всегда = глобальной политике.
    Memetic (TZ-MEMETIC-02): per-NPC, из archetype + adopted expressions.
    """
+   profanity_level: int = 0
+   sexual_content_level: int = 0
    violence_level: int = 0
+   taboo_practices_level: int = 0
    
+   # Adopted expressions (для memetic-режима DMContractBuilder)
+   adopted_profanity_words: tuple[str, ...] = ()
+   adopted_sexual_words: tuple[str, ...] = ()
+   
+   # Audit: источник профиля
+   source: str = "global"  # "global" / "archetype" / "memetic"

    def __post_init__(self) -> None:
-       if not (0 <= self.profanity_level <= 2):
-           raise ValueError(f"profanity_level должен быть 0-2, получено: {self.profanity_level}")
-       if not (0 <= self.violence_level <= 2):
-           raise ValueError(f"violence_level должен быть 0-2, получено: {self.violence_level}")
+       for field_name in ("profanity_level", "sexual_content_level", 
+                          "violence_level", "taboo_practices_level"):
+           val = getattr(self, field_name)
+           if not (0 <= val <= 2):
+               raise ValueError(f"{field_name} должен быть 0-2, получено: {val}")
    
+   @classmethod
+   def from_global_policy(cls, policy: "ContentPolicy") -> "ContentProfile":
+       """Фабрика: создаёт профиль из глобальной политики.
+       Единственный способ создания в fundament режиме."""
+       return cls(
+           profanity_level=int(policy.profanity_level),
+           sexual_content_level=int(policy.sexual_content_level),
+           violence_level=int(policy.violence_level),
+           taboo_practices_level=int(policy.taboo_practices_level),
+           source="global",
+       )
+   
+   @classmethod
+   def from_npc_state(
+       cls,
+       npc_id: str,
+       global_policy: "ContentPolicy",
+       voice_archetype: "VoiceArchetype",
+       npc_adoptions: list,
+       npc_psyche: "PsycheSnapshot",
+       current_tick: int,
+   ) -> "ContentProfile":
+       """Фабрика: создаёт per-NPC профиль из archetype + adopted.
+       Только при memetic_integration_enabled=True."""
+       from app.services.memetic.effective_content_profile import (
+           EffectiveContentProfileComputer,
+       )
+       computer = EffectiveContentProfileComputer()
+       return computer.compute(
+           global_policy=global_policy,
+           voice_archetype=voice_archetype,
+           npc_adoptions=npc_adoptions,
+           npc_psyche=npc_psyche,
+           current_tick=current_tick,
+       )

@dataclass
class VerbalizationContext:
    # ...
    content_profile: ContentProfile = field(default_factory=ContentProfile)
```

### Конфликт-чеклист
- ⚠️ Существующий код, который создаёт `ContentProfile()` без аргументов, продолжит работать (defaults).
- ⚠️ Существующий код, который создаёт `ContentProfile(profanity_level=1, violence_level=2)`, продолжит работать (новые поля получают defaults).
- ❌ Если где-то передаётся `ContentProfile(profanity_level=1, violence_level=2)` позиционно — сломается. Проверь grep'ом.

---

## 4. PATCH 04 — `backend/app/services/verbalization/dm_contract_builder.py` — параметризация policy-блока

**ТЗ-ссылка:** TZ_CONTENT_POLICY_FUNDAMENT §4.1, TZ-MEMETIC-02 §2.2
**Фаза:** F (policy-блок) + M (VOCABULARY/FORBIDDEN)
**Зависимости:** PATCH 03

### BEFORE (строки 24-44, 155-187)

```python
DM_SYSTEM_PROMPT = (
    "Ты — Мастер Подземелий D&D 5e. Опиши мир от второго лица.\n"
    "Отвечай ТОЛЬКО по-русски. НЕ ПИШИ по-китайски (中文) — это ЗАПРЕЩЕНО.\n"
    # ...
)

# Усиленный системный промпт для hardcore режима
DM_SYSTEM_PROMPT_HARDCORE = (
    DM_SYSTEM_PROMPT
    + "\n\nТОН/РЕЖИМ: HARDCORE.\n"
    "Разрешены: мрачные сцены, жестокость, кровь, смерть, грубость, мат.\n"
    "Не морализируй, не сглаживай и не 'перевоспитывай' игрока."
)

class DMContractBuilder:
    def __init__(
        self,
        hardcore_mode: bool = False,
        max_sentences: int = 3,
    ):
        self._hardcore = hardcore_mode
        self._max_sentences = max_sentences
    
    def build(
        self, 
        system_prompt: str,
        # ... остальные параметры ...
    ) -> str:
        # ...
        system = DM_SYSTEM_PROMPT_HARDCORE if self._hardcore else DM_SYSTEM_PROMPT
        return system + body
```

### AFTER

```python
DM_SYSTEM_PROMPT = (
    "Ты — Мастер Подземелий D&D 5e. Опиши мир от второго лица.\n"
    "Отвечай ТОЛЬКО по-русски. НЕ ПИШИ по-китайски (中文) — это ЗАПРЕЩЕНО.\n"
    # ...
)

- # Усиленный системный промпт для hardcore режима
- DM_SYSTEM_PROMPT_HARDCORE = (
-     DM_SYSTEM_PROMPT
-     + "\n\nТОН/РЕЖИМ: HARDCORE.\n"
-     "Разрешены: мрачные сцены, жестокость, кровь, смерть, грубость, мат.\n"
-     "Не морализируй, не сглаживай и не 'перевоспитывай' игрока."
- )
+ # DEPRECATED: DM_SYSTEM_PROMPT_HARDCORE удалён.
+ # Политика контента инжектится через _build_content_policy_block(),
+ # который строит per-axis инструкции на основе ContentProfile.
+ # См. TZ_CONTENT_POLICY_FUNDAMENT §4.1.

+ def _build_content_policy_block(profile: "ContentProfile") -> str:
+     """Строит блок ContentPolicy для системного промпта."""
+     lines = ["\n\n--- ПОЛИТИКА КОНТЕНТА ---"]
+     
+     # Profanity
+     if profile.profanity_level == 0:
+         lines.append("МАТ: полностью запрещён. Используй эвфемизмы ('чёрт', 'твою мать'). "
+                      "Даже если игрок оскорбляет NPC, NPC отвечает литературно.")
+     elif profile.profanity_level == 1:
+         lines.append("МАТ: лёгкая ругань допустима ('чёрт', 'блядь' как междометие, 'твою мать'). "
+                      "Тяжёлый мат (хуй, пизда, ебанутый) — запрещён.")
+     else:
+         lines.append("МАТ: разрешён в полной мере, в соответствии с характером NPC.")
+     
+     # Sexual content
+     if profile.sexual_content_level == 0:
+         lines.append("СЕКС: полностью запрещён. Сцены интима — fade-to-black.")
+     elif profile.sexual_content_level == 1:
+         lines.append("СЕКС: намёки и полутона допустимы. Explicit-описания запрещены.")
+     else:
+         lines.append("СЕКС: разрешён explicit, в соответствии с характером NPC.")
+     
+     # Violence
+     if profile.violence_level == 0:
+         lines.append("НАСИЛИЕ: запрещены детальные описания. 'Он упал и не встал' вместо "
+                     "'Кровь хлынула из рассечённой артерии'.")
+     elif profile.violence_level == 1:
+         lines.append("НАСИЛИЕ: физиологичные описания допустимы, но без садизма.")
+     else:
+         lines.append("НАСИЛИЕ: разрешены детальные описания, включая жестокость.")
+     
+     # Taboo practices
+     if profile.taboo_practices_level == 0:
+         lines.append("ТАБУ-ПРАКТИКИ (каннибализм, некрофилия, инцест, сатанизм): "
+                     "полностью запрещены. NPC отказываются обсуждать.")
+     elif profile.taboo_practices_level == 1:
+         lines.append("ТАБУ-ПРАКТИКИ: можно упоминать как слухи, без описания от первого лица.")
+     else:
+         lines.append("ТАБУ-ПРАКТИКИ: разрешены в полном объёме, в соответствии с сеттингом.")
+     
+     lines.append("--- КОНЕЦ ПОЛИТИКИ КОНТЕНТА ---\n")
+     return "\n".join(lines)

class DMContractBuilder:
    def __init__(
        self,
        hardcore_mode: bool = False,  # DEPRECATED
        max_sentences: int = 3,
+       content_profile: Optional["ContentProfile"] = None,
    ):
        self._hardcore = hardcore_mode
        self._max_sentences = max_sentences
+       self._content_profile = content_profile or ContentProfile()
    
    def build(
        self, 
        system_prompt: str,
+       voice_constraints: Optional[dict[str, str]] = None,
        # ... остальные параметры ...
    ) -> str:
        # ...
-       system = DM_SYSTEM_PROMPT_HARDCORE if self._hardcore else DM_SYSTEM_PROMPT
-       return system + body
+       # 1. Базовый системный промпт (из dm_system.txt, передан как system_prompt)
+       system = system_prompt
+       
+       # 2. Инъекция policy-блока
+       policy_block = _build_content_policy_block(self._content_profile)
+       system = system + policy_block
+       
+       # 3. Инъекция voice-блока (VOCABULARY, FORBIDDEN — только в memetic режиме)
+       if voice_constraints:
+           voice_section = "\n\n--- ГОЛОС NPC ---\n"
+           if "STYLE" in voice_constraints:
+               voice_section += f"СТИЛЬ РЕЧИ:\n{voice_constraints['STYLE']}\n\n"
+           if "VOCABULARY" in voice_constraints:
+               voice_section += f"{voice_constraints['VOCABULARY']}\n\n"
+           if "FORBIDDEN" in voice_constraints:
+               voice_section += f"{voice_constraints['FORBIDDEN']}\n"
+           voice_section += "--- КОНЕЦ ГОЛОСА NPC ---\n"
+           system = system + voice_section
+       
+       return system + body
```

### Конфликт-чеклист
- ❌ Удаляется `DM_SYSTEM_PROMPT_HARDCORE`. Если где-то ещё есть импорт — сломается. Проверь: `grep -r "DM_SYSTEM_PROMPT_HARDCORE" backend/`.
- ⚠️ `build()` получает новый параметр `voice_constraints`. Существующие вызовы без него продолжат работать (default None).
- ⚠️ Существующая логика `if self._hardcore: ...` удалена. Если есть тесты на `hardcore_mode` — их нужно обновить (использовать `ContentProfile`).

---

## 5. PATCH 05 — `backend/app/agents/dm_agent.py` — интеграция ContentProfile

**ТЗ-ссылка:** TZ_CONTENT_POLICY_FUNDAMENT §4.2, TZ-MEMETIC-02 §1.5, §6.1
**Фаза:** F (база) + M (memetic ветка)
**Зависимости:** PATCH 02, 03, 04

### BEFORE (строки 120-130, 343-374)

```python
def _build_contract(self, context: DMContext) -> str:
    settings = Settings()
    
    builder = DMContractBuilder(
        hardcore_mode=getattr(settings, "hardcore_mode", False),
        max_sentences=3,
    )
    
    # ... (цикл по NPC, строки 343-374) ...
    for npc_data in context.npcs:
        _voice = npc_data.get("voice_profile", "")
        _author = npc_data.get("author_notes", "")
        _line = f"\n  NPC: {npc_data.get('name', npc_id)}"
        if _voice:
            _line += f"\n  Голос: {_voice}"
        if _author and getattr(settings, "hardcore_mode", False):
            _line += f"\n  Режиссёрская: {_author}"
```

### AFTER

```python
def _build_contract(self, context: DMContext) -> str:
    settings = Settings()
+   content_policy = settings.content_policy
+   
+   # НОВОЕ: выбор фабрики ContentProfile (TZ-MEMETIC-02 §1.5)
+   if settings.memetic_integration_enabled:
+       # Memetic режим: per-NPC профиль
+       # Реализация — см. PATCH 09
+       content_profile = self._build_memetic_content_profile(context)
+   else:
+       # Fundament режим: глобальная политика
+       content_profile = ContentProfile.from_global_policy(content_policy)
    
    builder = DMContractBuilder(
        hardcore_mode=getattr(settings, "hardcore_mode", False),  # DEPRECATED
        max_sentences=3,
+       content_profile=content_profile,
    )
    
    # ... (цикл по NPC) ...
    for npc_data in context.npcs:
        _voice = npc_data.get("voice_profile", "")
        _author = npc_data.get("author_notes", "")
        _line = f"\n  NPC: {npc_data.get('name', npc_id)}"
        if _voice:
            _line += f"\n  Голос: {_voice}"
+       # ИЗМЕНЕНО: используем content_policy.hardcore_mode (alias), не settings.hardcore_mode
-       if _author and getattr(settings, "hardcore_mode", False):
+       if _author and content_policy.hardcore_mode:
            _line += f"\n  Режиссёрская: {_author}"
```

### Дополнительно: метод `_build_memetic_content_profile` (только в Phase M)

```python
+ def _build_memetic_content_profile(
+     self, context: DMContext,
+ ) -> ContentProfile:
+     """Строит per-NPC ContentProfile в memetic режиме.
+     Берёт profile для главного NPC в контексте (первого major)."""
+     # Загрузка VoiceArchetype, adoptions, psyche для NPC
+     # Делегирует в EffectiveContentProfileComputer
+     # ...
+     # Заглушка для Phase F (когда memetic_integration_enabled=False, не вызывается)
+     raise NotImplementedError("Implemented in Phase M")
```

### Конфликт-чеклист
- ⚠️ `Settings()` создаётся каждый раз. Если это дорого — рассмотри кэширование.
- ⚠️ В цикле по NPC сейчас один `content_profile` на всех. В memetic-режиме нужно per-NPC — это требует рефакторинга цикла (Phase M).

---

## 6. PATCH 06 — `backend/app/services/verbalization/response_validator.py` — пост-фильтр

**ТЗ-ссылка:** TZ_CONTENT_POLICY_FUNDAMENT §4.3, TZ-MEMETIC-02 §3
**Фаза:** F (lexicon-режим) + M (memetic-режим)
**Зависимости:** PATCH 03

### BEFORE (строки 49-95)

```python
class NPCResponseValidator:
    def __init__(self, ...):
        # Существующая инициализация без content_profile и lexicons
        ...
    
    def validate(self, response: str, npc_id: str, npc_tier: str) -> ValidationResult:
        # Существующие проверки: пустой ответ, язык, повтор, длина, can_speak, forbidden_actions
        ...
        return ValidationResult(valid=True, response=response)
```

### AFTER

```python
+ @dataclass(frozen=True)
+ class ContentViolation:
+     """Результат детекции нарушения ContentPolicy."""
+     axis: str           # "profanity" / "sexual" / "violence" / "taboo_practices"
+     detected_word: str
+     lemma: str
+     required_level: int
+     actual_level: int
+     position: int
+     expression_id: Optional[str] = None  # None = найдено через lexicon fallback

class NPCResponseValidator:
    def __init__(
        self,
        # ... существующие параметры ...
+       content_profile: "ContentProfile",
+       insult_roots: set[str],
+       sexual_roots: set[str],
+       violence_roots: set[str],
+       taboo_roots: set[str],
+       # Memetic-режим (опционально)
+       speaker_vocabulary: Optional["SpeakerVocabularyBundle"] = None,
+       concept_registry: Optional["ConceptRegistry"] = None,
+       memetic_enabled: bool = False,
    ):
        # ... существующая инициализация ...
+       self._content_profile = content_profile
+       self._lexicons = {
+           "profanity": insult_roots,
+           "sexual": sexual_roots,
+           "violence": violence_roots,
+           "taboo_practices": taboo_roots,
+       }
+       self._speaker_vocabulary = speaker_vocabulary
+       self._concept_registry = concept_registry
+       self._memetic_enabled = memetic_enabled
    
    def validate(self, response: str, npc_id: str, npc_tier: str) -> ValidationResult:
        # ... существующие проверки ...
        
+       # НОВАЯ ПРОВЕРКА: ContentPolicy violation
+       if self._memetic_enabled and self._speaker_vocabulary:
+           violation = self._detect_violation_memetic(response)
+       else:
+           violation = self._detect_violation_lexicon(response)
+       
+       if violation:
+           return ValidationResult(
+               valid=False,
+               reason=f"content_policy_violation:{violation.axis}",
+               violation=violation,
+           )
        
        return ValidationResult(valid=True, response=response)
    
+   def _detect_violation_lexicon(self, response: str) -> Optional[ContentViolation]:
+       """Fundament режим: фильтр по словарям (pymorphy3 лемматизация)."""
+       # Реализация аналогична dm_router._classify_action (строки 224-287)
+       # Защита от залипания, отрицаний, междометий
+       ...
+   
+   def _detect_violation_memetic(self, response: str) -> Optional[ContentViolation]:
+       """Memetic режим: фильтр по category_tags Expressions.
+       Fallback на lexicon для неизвестных слов."""
+       ...
```

### Конфликт-чеклист
- ⚠️ Конструктор меняется — все места создания `NPCResponseValidator` нужно обновить.
- ⚠️ `ValidationResult` нужно расширить полем `violation: Optional[ContentViolation]`.
- ℹ️ Логика лемматизации уже есть в `dm_router.py:224-287` — можно вынести в общий util.

---

## 7. PATCH 07 — НОВЫЕ ФАЙЛЫ лексиконов и lexicon_loader

**ТЗ-ссылка:** TZ_CONTENT_POLICY_FUNDAMENT §6
**Фаза:** F
**Зависимости:** нет

### 7.1. Создать `backend/data/sexual_lexicon_ru.json`

```json
{
  "_version": "1.0",
  "_type": "content_lexicon",
  "_axis": "sexual",
  "_description": "Корни sexual-лексики для ResponseValidator.",
  "roots": [
    "секс", "трах", "еб", "еба", "ебл", "ебн",
    "блуд", "прелюбод", "шлюх", "курв", "проститут",
    "шалав", "потаск", "распут", "грех",
    "постел", "лож", "совокупл", "проникн",
    "ласк", "поцелуй", "обним"
  ],
  "_notes": [
    "Корни намеренно короткие — pymorphy3 нормализует формы.",
    "'грех' включён: в средневековом сеттинге маркер sexual-контента в речи духовенства.",
    "'ласк' и 'поцелуй' включены для level=0 (полный запрет), но могут быть whitelist'нуты."
  ]
}
```

### 7.2. Создать `backend/data/violence_lexicon_ru.json`

```json
{
  "_version": "1.0",
  "_type": "content_lexicon",
  "_axis": "violence",
  "roots": [
    "рез", "уб", "душ", "калеч", "расчлен", "кров", "кишк",
    "внутрен", "мозг", "череп", "кост", "перелом",
    "ран", "бьет", "бью", "бил", "удар", "пин", "топт",
    "палач", "казн", "повеш", "обезглавл", "сожж",
    "пытк", "муч", "страд"
  ],
  "_notes": [
    "'бьет/бью/бил' — разные формы, ловятся через pymorphy3 лемматизацию.",
    "'кров' ловит 'кровь', 'кровавый', 'кровища'.",
    "'мозг' включён для level=0 (описания травм головы)."
  ]
}
```

### 7.3. Создать `backend/data/taboo_lexicon_ru.json`

```json
{
  "_version": "1.0",
  "_type": "content_lexicon",
  "_axis": "taboo_practices",
  "roots": [
    "каннибал", "людоед", "пожир", "съесть человеч",
    "некро", "труп", "мертв", "падаль",
    "инцест", "кровосм", "родственн",
    "сатан", "бес", "демон-поклон", "жертвопринош",
    "прокл", "порча", "сглаз", "ведьм", "колд"
  ],
  "_notes": [
    "'труп' и 'мертв' — контекстно-зависимые. В боевом контексте (level>=1) допустимы, в taboo (level=0) — нет.",
    "Whitelist'нутые формы (библейские, медицинские) — в отдельном файле whitelist_lexicon.json (будущее)."
  ]
}
```

### 7.4. Создать `backend/app/services/verbalization/lexicon_loader.py`

Полное содержимое — см. TZ_CONTENT_POLICY_FUNDAMENT §6.3.

### Проверка
```bash
python -c "
from app.services.verbalization.lexicon_loader import ContentLexiconLoader
from pathlib import Path
lex = ContentLexiconLoader.load_all(Path('backend/data'))
print({k: len(v) for k, v in lex.items()})
"
# → {'profany': ~200, 'sexual': ~20, 'violence': ~30, 'taboo_practices': ~25}
```

---

## 8. PATCH 08 — НОВЫЙ ФАЙЛ `backend/app/services/verbalization/response_rephraser.py`

**ТЗ-ссылка:** TZ_CONTENT_POLICY_FUNDAMENT §4.4, TZ-MEMETIC-02 §4
**Фаза:** F (fundament rephrase) + M (memetic rephrase)
**Зависимости:** PATCH 06

### Создать файл

Два метода:
- `rephrase_fundament(original, violation, voice_profile, npc_name)` — абстрактное «переформулируй мягче».
- `rephrase_memetic(original, violation, voice_profile, npc_name, archetype_id, speaker_vocabulary)` — с конкретными alternatives.

Полное содержимое — см. TZ_CONTENT_POLICY_FUNDAMENT §4.4 и TZ-MEMETIC-02 §4.

---

## 9. PATCH 09 — `frontend/game_launcher.py` + НОВЫЙ `frontend/settings_screen.py`

**ТЗ-ссылка:** TZ_CONTENT_POLICY_FUNDAMENT §5
**Фаза:** F
**Зависимости:** PATCH 02

### 9.1. BEFORE `game_launcher.py` (строки 212-214)

```python
elif action == MenuAction.SETTINGS:
    # TODO: временная заглушка — экран настроек
    pass
```

### 9.1. AFTER

```python
elif action == MenuAction.SETTINGS:
+   from settings_screen import SettingsScreen
+   settings_screen = SettingsScreen(self._screen)
+   result = settings_screen.run()  # blocking loop
+   if result == "apply":
+       # ContentPolicy уже перезагружен внутри settings_screen
+       logger.info("[GAME_LAUNCHER] Content policy changed by user")
```

### 9.2. Создать `frontend/settings_screen.py`

Минимальная реализация — только вкладка «Контент». Остальные вкладки (Графика, AI-модель, Производительность, Управление) — заглушки «Не реализовано».

Полное содержимое — см. TZ_CONTENT_POLICY_FUNDAMENT §5.4.

Ключевые элементы:
- `class SettingsScreen` с `TABS = ["Графика", "AI-модель", "Производительность", "Управление", "Контент"]`
- `_active_tab = "Контент"` (единственная реализованная)
- 3 radio-кнопки (Выключено / Умеренно / Без ограничений)
- Раскрытие «Детальные настройки» с 4 слайдерами
- Кнопки Apply / Cancel
- Запись в `config/user_settings.yaml`
- Вызов `Settings.reload_content_policy()`

### Конфликт-чеклист
- ⚠️ `Settings()` — это backend-класс. Frontend должен ходить через API. Но в текущей архитектуре frontend уже делает HTTP-запросы на backend (см. `api_client.py`), поэтому добавь endpoint `POST /api/settings/content` и дёргай его из settings_screen.

---

## 10. PATCH 10 — НОВЫЕ ФАЙЛЫ конфигов

**ТЗ-ссылка:** TZ_CONTENT_POLICY_FUNDAMENT §3.2, TZ-MEMETIC-01 §3.3, §4.2, TZ-MEMETIC-02 §1.3
**Фаза:** F + M
**Зависимости:** нет

### 10.1. Создать `config/canon/content_policy_defaults.yaml`

Полное содержимое — см. TZ_CONTENT_POLICY_FUNDAMENT §3.2.

### 10.2. Создать `config/user_settings.yaml` (если не существует)

```yaml
# config/user_settings.yaml
# State: настройки игрока (per-save)
# Мигрирует с hardcoded_mode=True при первом запуске.

graphics:
  # ... (из ТЗ Дополнение А §А.6.6, когда будет реализовано)
  placeholder: true

ai_model:
  placeholder: true

performance:
  placeholder: true

audio:
  placeholder: true

interface:
  language: "ru"

controls:
  keybindings: {}

# НОВАЯ СЕКЦИЯ (TZ_CONTENT_POLICY_FUNDAMENT §3.3)
content:
  preset: "explicit"          # off / moderate / explicit / null
  individual:
    profanity_level: 2
    sexual_content_level: 2
    violence_level: 2
    taboo_practices_level: 2
  last_changed_tick: 0
  last_changed_reason: "migration"
```

### 10.3. Создать `config/canon/concepts/` (Phase M)

Начать с 5 базовых Concept-ов (полные YAML — см. TZ-MEMETIC-01 §1.3):

```
config/canon/concepts/
    guard_role.yaml
    blacksmith_role.yaml
    coin_currency.yaml
    tavern_location.yaml
    thieves_guild_org.yaml
```

### 10.4. Создать `config/canon/domain_types.yaml` (Phase M)

Полное содержимое — см. TZ-MEMETIC-01 §2.2 (16 стандартных Domain Types с parent_ids).

### 10.5. Создать `config/canon/voice_archetypes/` (Phase M)

6 архетипов:

```
config/canon/voice_archetypes/
    noble.yaml
    thief.yaml
    maid.yaml
    merchant.yaml
    blacksmith.yaml
    guard.yaml
```

Каждый с полями из TZ-MEMETIC-01 §4.2 + `content_defaults` из TZ-MEMETIC-02 §1.3.

### 10.6. Дополнить NPC-конфиги (Phase M)

Для каждого из 6 NPC добавить 2 поля:

```json
// config/npc/individuals/lusya.json
{
  "id": "maid_lusya",
  ...
+ "voice_archetype_id": "maid",
+ "identity_attachment": 0.3
}
```

| NPC | voice_archetype_id | identity_attachment | Обоснование |
|---|---|---|---|
| maid_lusya | maid | 0.3 | Не дорожит, хочет сбежать |
| tavern_keeper_tornin | merchant | 0.7 | Гордится статусом |
| guard_borko | guard | 0.5 | Нейтрально |
| blacksmith_orm | blacksmith | 0.6 | Гордится ремеслом |
| merchant_goran | merchant | 0.7 | Купеческая гордость |
| thief_shadow | thief | 0.8 | Воровской жарон = идентичность |

---

## 11. PATCH 11 — `backend/app/models/npc_profile.py` + `npc_loader.py` — stub-поля

**ТЗ-ссылка:** TZ_CONTENT_POLICY_FUNDAMENT §2.3, TZ-MEMETIC-02 §5.3
**Фаза:** F (stub) + M (активация)
**Зависимости:** PATCH 03

### 11.1. BEFORE `npc_profile.py` (строки 43-62)

```python
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
```

### 11.1. AFTER

```python
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
+   
+   # STUB (TZ_CONTENT_POLICY_FUNDAMENT §2.3) → ACTIVE (TZ-MEMETIC-02 §5.3)
+   voice_archetype_id: Optional[str] = None
+   """ID архетипа голоса в config/canon/voice_archetypes/*.yaml.
+   None = fallback на _archetype поле."""
+   
+   identity_attachment: float = 0.5
+   """0..1. Насколько NPC дорожит своей речью как маркером идентичности.
+   1.0 = речь = класс (графиня, жрец)
+   0.5 = нейтрально (крестьянин)
+   0.0 = всё равно (ребёнок, маргинал)"""
```

### 11.2. BEFORE `npc_loader.py` (строки 438-450)

```python
profile = NPCProfileL0(
    id=raw_data["id"],
    name=raw_data.get("name", "Unknown"),
    tier=raw_data.get("tier", "minor"),
    gender=raw_data.get("gender", "male"),
    archetype=raw_data.get("_archetype", "commoner"),
    drives_base=drives_base,
    psyche_base=psyche_base,
    voice_profile=raw_data.get("voice_profile", ""),
    backstory=raw_data.get("backstory", raw_data.get("description", "")),
    author_notes=raw_data.get("author_notes", ""),
)
```

### 11.2. AFTER

```python
profile = NPCProfileL0(
    id=raw_data["id"],
    name=raw_data.get("name", "Unknown"),
    tier=raw_data.get("tier", "minor"),
    gender=raw_data.get("gender", "male"),
    archetype=raw_data.get("_archetype", "commoner"),
    drives_base=drives_base,
    psyche_base=psyche_base,
    voice_profile=raw_data.get("voice_profile", ""),
    backstory=raw_data.get("backstory", raw_data.get("description", "")),
    author_notes=raw_data.get("author_notes", ""),
+   voice_archetype_id=raw_data.get("voice_archetype_id"),
+   identity_attachment=raw_data.get("identity_attachment", 0.5),
)
```

### Конфликт-чеклист
- ✅ Существующие NPC-конфиги без новых полей продолжат работать (defaults).
- ⚠️ `PsycheBase` тоже нужно расширить полем `linguistic_integrity: float = 1.0` — см. PATCH 11.3.

### 11.3. Расширение `PsycheBase`

Найти файл, где определён `PsycheBase` (вероятно `backend/app/domain/vital_state.py` или `backend/app/models/npc_state.py`).

```python
@dataclass(frozen=True)
class PsycheBase:
    willpower: int
    breakpoint: int
    loyalty_true: float
+   
+   # STUB (TZ_CONTENT_POLICY_FUNDAMENT §2.3) → ACTIVE (TZ-MEMETIC-02 §5.1)
+   linguistic_integrity: float = 1.0
+   """Сопротивление языковому дрейфу. 0..1.
+   В fundament режиме всегда 1.0.
+   В memetic режиме вычисляется по формуле:
+   willpower * class_factor * age_factor * identity_attachment"""
```

---

## 12. PATCH 12 — НОВЫЙ ПАКЕТ `backend/app/domain/memetic/` + `backend/app/services/memetic/`

**ТЗ-ссылка:** TZ-MEMETIC-01 (весь документ), TZ-MEMETIC-02 §1.2, §5.2
**Фаза:** M
**Зависимости:** PATCH 01-11

### 12.1. Создать доменные типы `backend/app/domain/memetic/`

```
backend/app/domain/memetic/
    __init__.py
    core_types.py            # CoreType enum (16 значений)
    domain_types.py          # DomainType + registry
    concept.py               # Concept dataclass
    expression.py            # Expression dataclass
    adoption.py              # Adoption + SpeakerVocabulary dataclasses
    cultural_norm.py         # CulturalNorm dataclass
    cultural_pressure.py     # CulturalPressureAccumulator dataclass
    voice_archetype.py       # VoiceArchetype dataclass
    transmission_event.py    # MemeticTransmissionEvent dataclass
    concept_registry.py      # ConceptRegistry (in-memory cache + lazy load)
```

Полные содержимые — см. TZ-MEMETIC-01 §1.2-1.6, §2.1-2.2, §4.2.

### 12.2. Создать сервисы `backend/app/services/memetic/`

```
backend/app/services/memetic/
    __init__.py
    # L1: Transmission
    transmission_calculator.py        # TransmissionCalculator
    memetic_transmission_recorder.py  # Запись в history.db
    
    # L1.5: Detection
    adoption_detector.py              # MemeticAdoptionDetector
    
    # L2.5: Crystallization
    lexicon_crystallization_engine.py  # IndividualLexiconCrystallizer
    community_norm_engine.py           # CommunityNormEngine
    
    # L3: Resolution
    expression_resolver.py             # ExpressionResolver
    speaker_vocabulary_cache.py        # SpeakerVocabularyCache (LRU)
    
    # Effective profile
    effective_content_profile.py       # EffectiveContentProfileComputer
    
    # Linguistic integrity
    linguistic_integrity_calculator.py  # LinguisticIntegrityCalculator
    
    # Cultural Pressure
    cultural_pressure_engine.py        # CulturalPressureEngine
    memetic_burst_trigger.py           # MemeticBurstTrigger
    
    # Burst pipeline
    burst_llm_contractor.py            # BurstLLMContractor
    burst_validator.py                 # BurstArtifactValidator
    burst_orchestrator.py              # MemeticBurstOrchestrator
    
    # Player memes
    player_expression_detector.py      # PlayerExpressionDetector
    player_expression_limiter.py       # PlayerExpressionLimiter
    
    # Analytical drift
    analytical_drift_engine.py         # AnalyticalDriftEngine (Bass diffusion)
    
    # Persistence
    memetic_persistence_adapter.py     # SQLite adapter for memetic tables
    
    # Migration
    profanity_concept_factory.py       # ProfanityConceptFactory
```

### 12.3. SQL-схемы

Создать `backend/app/services/memetic/schema.sql`:

```sql
-- History (append-only)
CREATE TABLE IF NOT EXISTS memetic_transmission_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tick INTEGER NOT NULL,
    source_npc_id TEXT NOT NULL,
    target_npc_id TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    expression_text TEXT NOT NULL,
    context TEXT NOT NULL,
    interaction_type TEXT,
    transmission_weight REAL NOT NULL,
    source_stress REAL,
    target_stress REAL,
    relationship_trust REAL,
    relationship_respect REAL,
    burst_event_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mte_target ON memetic_transmission_events(target_npc_id, concept_id);
CREATE INDEX IF NOT EXISTS idx_mte_tick ON memetic_transmission_events(tick);
CREATE INDEX IF NOT EXISTS idx_mte_burst ON memetic_transmission_events(burst_event_id);

CREATE TABLE IF NOT EXISTS memetic_burst_log (
    burst_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    community_id TEXT NOT NULL,
    trigger_tick INTEGER NOT NULL,
    pressure_score REAL NOT NULL,
    proposed_artifacts_json TEXT NOT NULL,
    validated_artifacts_json TEXT NOT NULL,
    accepted_concept_ids_json TEXT NOT NULL,
    accepted_expression_refs_json TEXT NOT NULL,
    status TEXT NOT NULL,
    rejection_reasons_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- State (mutable)
CREATE TABLE IF NOT EXISTS npc_adoptions (
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
CREATE INDEX IF NOT EXISTS idx_adoptions_npc_concept ON npc_adoptions(npc_id, concept_id);
CREATE INDEX IF NOT EXISTS idx_adoptions_preferred ON npc_adoptions(npc_id, is_preferred);

CREATE TABLE IF NOT EXISTS cultural_norms (
    community_id TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    dominant_expression TEXT NOT NULL,
    dominance_share REAL NOT NULL,
    last_computed_tick INTEGER NOT NULL,
    history_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (community_id, concept_id)
);

CREATE TABLE IF NOT EXISTS cultural_pressure_accumulators (
    event_id TEXT NOT NULL,
    community_id TEXT NOT NULL,
    notoriety REAL NOT NULL DEFAULT 0.0,
    retelling_count INTEGER NOT NULL DEFAULT 0,
    last_retell_tick INTEGER NOT NULL,
    emotional_weight REAL NOT NULL DEFAULT 0.0,
    faction_alignment REAL NOT NULL DEFAULT 0.0,
    pressure_score REAL NOT NULL DEFAULT 0.0,
    last_burst_tick INTEGER,
    burst_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (event_id, community_id)
);
```

### 12.4. Интеграция в `tick_orchestrator.py`

Добавить новую фазу `memetic_transmission` между существующими фазами:

```python
# backend/app/services/tick_orchestrator.py — РАСШИРЕНИЕ

class TickOrchestrator:
    PHASES = [
        Phase0_Simulation,
        Phase1_Input,
        Phase2_EventBus,
+       Phase2_5_MemeticTransmission,  # НОВОЕ: запись transmission events
        Phase3_Memory,
        Phase4_PreDecision,
        Phase5_Decision,
        Phase6_PostDecision,
+       Phase6_5_MemeticCrystallization,  # НОВОЕ: кристаллизация adoptions
        Phase8_Handlers,
        Phase9_Integration,
        Phase10_Persistence,
    ]
```

Каждая memetic-фаза запускается **только при `settings.memetic_integration_enabled=True`**. Иначе — no-op.

---

## 13. СВОДНАЯ ТАБЛИЦА ПАТЧЕЙ

| # | Файл | Фаза | Тип | ТЗ-ссылка | Зависимости |
|---|---|---|---|---|---|
| 01 | `backend/app/core/config.py` | F | Изменение | FUND §2.1, §3.4 | — |
| 02 | `backend/app/core/content_policy.py` | F | Новый | FUND §2.1, §3.4 | 01 |
| 03 | `backend/app/services/verbalization/verbalization_context.py` | F+M | Изменение | FUND §2.2, M02 §1.4 | 02 |
| 04 | `backend/app/services/verbalization/dm_contract_builder.py` | F+M | Изменение | FUND §4.1, M02 §2.2 | 03 |
| 05 | `backend/app/agents/dm_agent.py` | F+M | Изменение | FUND §4.2, M02 §1.5, §6.1 | 02, 03, 04 |
| 06 | `backend/app/services/verbalization/response_validator.py` | F+M | Изменение | FUND §4.3, M02 §3 | 03 |
| 07 | `backend/data/{sexual,violence,taboo}_lexicon_ru.json` + `lexicon_loader.py` | F | Новые | FUND §6 | — |
| 08 | `backend/app/services/verbalization/response_rephraser.py` | F+M | Новый | FUND §4.4, M02 §4 | 06 |
| 09 | `frontend/game_launcher.py` + `frontend/settings_screen.py` | F | Изменение + Новый | FUND §5 | 02 |
| 10 | `config/canon/*.yaml` + `config/user_settings.yaml` + NPC-конфиги | F+M | Новые + Изменение | FUND §3, M01 §3, M02 §1.3 | — |
| 11 | `backend/app/models/npc_profile.py` + `npc_loader.py` + `PsycheBase` | F+M | Изменение | FUND §2.3, M02 §5 | 03 |
| 12 | `backend/app/domain/memetic/` + `backend/app/services/memetic/` + SQL schema + tick_orchestrator | M | Новые + Изменение | M01 (весь), M02 §1.2, §5.2 | 01-11 |

---

## 14. ПОРЯДОК ПРИМЕНЕНИЯ

### Phase F (Fundament) — 7-10 дней

Реализует TZ_CONTENT_POLICY_FUNDAMENT. После Phase F система работает с глобальной политикой контента.

```
День 1-2: PATCH 01, 02 (config.py + content_policy.py)
День 3:   PATCH 03, 11 (ContentProfile + stub-поля)
День 4-5: PATCH 04, 05 (DMContractBuilder + DMAgent)
День 6:   PATCH 06, 07 (ResponseValidator + lexicons)
День 7:   PATCH 08 (ResponseRephraser)
День 8-9: PATCH 09, 10 (settings_screen + config files)
День 10:  Тесты из FUND §7
```

**После Phase F:**
- Игрок может переключать 18+ контент в настройках.
- Глобальная политика работает.
- `hardcore_mode` мигрирован.
- `memetic_integration_enabled = False` (по умолчанию).

### Phase M (Memetic) — 5-6 недель

Реализует TZ-MEMETIC-01 + TZ-MEMETIC-02. После Phase M система готова к активации memetic-режима.

```
Неделя 1: PATCH 12.1 (доменные типы) + PATCH 10.3-10.5 (Canon YAML)
Неделя 2: PATCH 12.2 (сервисы L1-L3) + PATCH 12.3 (SQL schema)
Неделя 3: PATCH 12.2 (Cultural Pressure + Burst)
Неделя 4: PATCH 12.2 (Player memes + Analytical drift)
Неделя 5: Интеграция PATCH 04, 05, 06, 08 (memetic-ветки)
Неделя 6: Тесты из M01 §10 + M02 §8 + E2E
```

**После Phase M:**
- `memetic_integration_enabled = True` активирует per-NPC ContentProfile.
- Concept Registry загружен.
- Memetic transmission pipeline работает.
- Burst pipeline готов (но LLM-judge опционален).

### Активация

После Phase M + тестов:

```python
# backend/app/core/config.py
class Settings(BaseSettings):
    memetic_integration_enabled: bool = True  # изменено с False на True
```

Или через `user_settings.yaml`:

```yaml
content:
  preset: "explicit"
  memetic_integration: true  # новое поле (опционально)
```

---

## 15. КОНФЛИКТ-ЧЕКЛИСТ (ГЛОБАЛЬНЫЙ)

### 15.1. Файлы, которые НЕЛЬЗЯ трогать

- `backend/app/services/llm/provider.py`, `llama_cpp_provider.py` — LLM-провайдер не фильтрует контент (см. TZ_CONTENT_POLICY_FUNDAMENT §12.3).
- `backend/prompts/dm_system.txt` — внешний системный промпт остаётся как есть. Policy-блок инжектится **поверх**.
- `backend/data/insults_ru.json` — переиспользуется как есть. Не дублировать.
- `backend/app/agents/rules_agent.py` — не затрагивается (ActionType.ROMANCE остаётся).

### 15.2. Файлы, которые требуют осторожности

- `backend/app/services/verbalization/scene_outcome_builder.py:872-883` — `_build_voice_constraints` расширить, не переписывать.
- `backend/app/services/tick_orchestrator.py` — добавлять memetic-фазы через стратегию плагинов, неinline'ить.
- `frontend/api_client.py` — добавить endpoint для настроек, не дублировать HTTP-логику.

### 15.3. Проверки перед коммитом

```bash
# 1. Все существующие тесты проходят
cd backend && pytest

# 2. Нет упоминаний удалённого DM_SYSTEM_PROMPT_HARDCORE
grep -r "DM_SYSTEM_PROMPT_HARDCORE" backend/
# Ожидание: 0 совпадений (или только в deprecated комментариях)

# 3. Нет упоминаний удалённого config.json.deprecated
grep -r "config.json" backend/
# Ожидание: только в migration коде

# 4. ContentPolicy загружается
python -c "from app.core.config import Settings; print(Settings().content_policy)"

# 5. Lexicons загружаются
python -c "from app.services.verbalization.lexicon_loader import ContentLexiconLoader; ..."

# 6. Memetic-режим отключается cleanly
python -c "from app.core.config import Settings; s = Settings(); s.memetic_integration_enabled = False; print('OK')"

# 7. NPC-конфиги загружаются с новыми полями
python -c "
from app.services.npc.npc_loader import load_profile_from_legacy_json
import json
data = json.load(open('config/npc/individuals/lusya.json'))
profile = load_profile_from_legacy_json(data)
print(profile.voice_archetype_id, profile.identity_attachment)
"
```

---

## 16. ТЕСТОВЫЙ ПЛАН ПО ПАТЧАМ

| Патч | Тесты |
|---|---|
| 01 | `test_settings_has_content_policy_property`, `test_memetic_flag_default_false` |
| 02 | `test_preset_off_all_axes_zero`, `test_hardcore_mode_alias_*` (FUND §7.2) |
| 03 | `test_content_profile_from_global_policy`, `test_content_profile_from_npc_state_stub` |
| 04 | `test_policy_block_injected_into_system_prompt`, `test_policy_off_injects_full_profanity_ban` (FUND §7.3) |
| 05 | `test_dm_agent_uses_content_profile`, `test_memetic_branch_not_called_when_disabled` |
| 06 | `test_profanity_detected_when_level_zero`, `test_memetic_validator_finds_known_expression` (FUND §7.4, M02 §8.4) |
| 07 | `test_lexicons_load_without_errors`, `test_sexual_lexicon_has_roots` |
| 08 | `test_rephraser_called_for_major_npc`, `test_rephraser_uses_concrete_alternatives` (M02 §8.5) |
| 09 | `test_selecting_preset_updates_individual_levels`, `test_apply_writes_to_user_settings_yaml` (FUND §7.5) |
| 10 | `test_canon_yaml_valid`, `test_npc_configs_have_new_fields` |
| 11 | `test_npc_profile_has_voice_archetype_id`, `test_psyche_has_linguistic_integrity` |
| 12 | Все тесты из TZ-MEMETIC-01 §10 и TZ-MEMETIC-02 §8 |

---

## 17. РЕЗЮМЕ ДЛЯ ИСПОЛНИТЕЛЯ

**Минимальный путь к работающей системе:**

1. **Phase F** (7-10 дней): PATCH 01-11 (без memetic-частей). Результат — игрок может включать/выключать 18+ контент в настройках, глобальная политика работает, `hardcore_mode` мигрирован.
2. **Тестирование Phase F**: все тесты из TZ_CONTENT_POLICY_FUNDAMENT §7 проходят.
3. **Phase M** (5-6 недель): PATCH 12 + memetic-ветки в PATCH 04, 05, 06, 08. Результат — per-NPC цензура, memetic transmission, burst pipeline.
4. **Тестирование Phase M**: все тесты из TZ-MEMETIC-01 §10 и TZ-MEMETIC-02 §8 проходят.
5. **Активация**: `memetic_integration_enabled = True`.

**Что НЕ делать:**
- ❌ Не удалять `hardcore_mode` (alias property, нужен для обратной совместимости).
- ❌ Не удалять `from_global_policy()` (нужен для fallback).
- ❌ Не удалять lexicon-валидацию (нужна для fallback на неизвестные слова).
- ❌ Не активировать `memetic_integration_enabled` до завершения Phase M.
- ❌ Не менять UI настроек (один тумблер + 4 слайдера).
- ❌ Не трогать `insults_ru.json` (переиспользуется как есть).

**Что ДЕЛАТЬ:**
- ✅ Добавлять stub-поля с defaults (не ломают существующий код).
- ✅ Использовать флаги для постепенной активации.
- ✅ Покрывать каждый патч тестами.
- ✅ Обновлять `architecture/*.yaml` после изменения кода (расхождение с документацией — ADR-нарушение).
- ✅ Логировать все изменения ContentPolicy (для аудита).

---

## 18. СВЯЗЬ С ADR

После применения всех патчей обновить:

- `docs/ADR (Architecture Decision Records).md` — добавить:
  - `ADR-O-MEMETIC-000: Ontological Storage Principle` (из FUND §10)
  - `ADR-O-MEMETIC-001: Memetic Transmission Domain` (из M01 §13)
  - `ADR-O-MEMETIC-002: Content Policy Integration` (из M02 §11)

- `architecture/verbalization.yaml` — обновить узлы:
  - `ContentProfile` — актуальные поля (4 оси + adopted + source).
  - `DMContractBuilder` — voice_constraints с VOCABULARY/FORBIDDEN.
  - `ResponseValidator` — memetic-режим.

- `architecture/identity.yaml` — добавить поддомен MEMETIC:
  - `L0: VoiceArchetype`
  - `L1: MemeticTransmissionEvent`
  - `L1.5: MemeticAdoptionDetector`
  - `L2.5-ind: IndividualLexiconCrystallizer`
  - `L2.5-comm: CommunityNormEngine`
  - `L3: ExpressionResolver`

- `architecture/pipeline.yaml` — добавить фазы:
  - `Phase2_5_MemeticTransmission`
  - `Phase6_5_MemeticCrystallization`

---

## 19. ИТОГ

Этот документ — **рабочий план** для исполнителя. Он содержит:

- 12 конкретных точек изменения с patch-примерами.
- 8 новых файлов для создания.
- Порядок применения (F → M).
- Конфликт-чеклист.
- Тестовый план.
- Сводную таблицу зависимостей.

После применения всех 12 патчей ENIGMA получит:

1. **Работающий переключатель 18+ в настройках** (Phase F).
2. **Per-NPC цензуру через memetic-домен** (Phase M).
3. **Культурную эволюцию языка** — слова, имена, праздники, поговорки рождаются и вымирают без скриптов.
4. **Графиня не матерится, вор матерится, крестьянин усваивает** — автоматически, без ручных настроек.

Это **первая в истории игровая симуляция культурной эволюции с локальной LLM**. Реализованная честно — по законам memetics, лингвистики и культурной антропологии, без фейковой «магии LLM».

---

**Конец документа.**
**Конец серии ТЗ (FUND + M01 + M02 + M03).**
