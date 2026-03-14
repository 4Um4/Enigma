# ARCHITECTURE: Model Router System

## Overview

Model Router - это система автоматического выбора LLM моделей для различных задач агентов. Система полностью автоматическая и не требует ручного переключения моделей пользователями.

---

## До и После

### Было (Single Model)
```
Agents → LlmManager → llama.cpp → single model
```
- Все агенты используют одну модель
- Ручное переключение модели пользователем
- Нет автоматической маршрутизации

### Стало (Multi-Provider Router)
```
┌─────────────────────────────────────────────────────────────┐
│                        AGENTS                                │
│  DmAgent | NpcAgent | RulesAgent | WorldAgent | MemoryAgent │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    ModelRouter                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Capability-based Routing                            │   │
│  │  - narrative → qwen_7b (preferred), qwen_9b         │   │
│  │  - dialogue → yandex (preferred), qwen_7b           │   │
│  │  - rules_reasoning → saiga (preferred)              │   │
│  │  - world_simulation → qwen_9b (preferred)           │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  ProviderManager                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│  │ qwen_7b     │ │ qwen_9b     │ │ saiga       │ ...        │
│  │ Provider    │ │ Provider    │ │ Provider    │            │
│  └─────────────┘ └─────────────┘ └─────────────┘            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    LlmProvider Interface                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐     │
│  │ LlamaCppProv │ │ OpenAIProv   │ │ AnthropicProvider│     │
│  └──────────────┘ └──────────────┘ └──────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Concepts

### 1. Capability-based Routing

Агенты запрашивают **capability** (возможность), а не модель:

```python
# BAD (старая система)
agent.request(model="saiga")

# GOOD (новая система)
agent.request(capability="dialogue")
```

Система автоматически выбирает лучшую доступную модель для запрошенной capability.

### 2. Capabilities

```python
class Capability(str, Enum):
    NARRATIVE = "narrative"           # DM storytelling
    DIALOGUE = "dialogue"             # NPC conversations
    DIALOGUE_GENERATION = "dialogue_generation"
    RULES_REASONING = "rules_reasoning"  # D&D rules
    WORLD_SIMULATION = "world_simulation" # World events
    STRATEGY = "strategy"             # Combat tactics
    MEMORY_SUMMARIZATION = "memory_summarization"
    FACT_EXTRACTION = "fact_extraction"
    GENERAL = "general"               # Default
    FAST = "fast"                    # Quick responses
```

### 3. Model Preferences

```python
CAPABILITY_MODEL_PREFERENCES = {
    Capability.NARRATIVE: ["qwen_7b", "qwen_9b", "yandex"],
    Capability.DIALOGUE: ["yandex", "qwen_7b"],
    Capability.WORLD_SIMULATION: ["qwen_9b", "qwen_7b"],
    Capability.RULES_REASONING: ["saiga", "qwen_7b"],
    # ...
}
```

### 4. Agent to Capability Mapping

```python
DEFAULT_AGENT_CAPABILITY_MAP = {
    "dm": Capability.NARRATIVE,         # DM Agent → narrative
    "world": Capability.WORLD_SIMULATION,  # World Agent → world_simulation
    "npc": Capability.DIALOGUE,         # NPC Agent → dialogue
    "rules": Capability.RULES_REASONING,   # Rules Agent → rules_reasoning
    "memory": Capability.MEMORY_SUMMARIZATION,
}
```

---

## Components

### 1. LlmProvider (Interface)

Абстрактный интерфейс для всех провайдеров:

```python
class LlmProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, params: GenerationParams, system_prompt: str) -> str:
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        pass
    
    @abstractmethod
    def get_info(self) -> ProviderInfo:
        pass
```

### 2. ProviderManager

Менеджер всех провайдеров (Singleton):

```python
class ProviderManager:
    def initialize_all(self) -> dict[str, bool]:
        """Инициализировать все провайдеры при старте."""
        
    def get_provider_for_capability(self, capability: str, preferred_keys: list[str]) -> ModelProvider:
        """Получить лучший провайдер для capability."""
        
    def health_check(self) -> dict[str, dict]:
        """Проверить здоровье всех провайдеров."""
```

### 3. ModelRouter

Основной компонент маршрутизации (Singleton):

```python
class ModelRouter:
    def request(self, capability: Capability, prompt: str, ...) -> str:
        """Отправить запрос с автовыбором модели."""
        
    def request_for_agent(self, agent_name: str, prompt: str, ...) -> str:
        """Отправить запрос от имени агента (автоопределение capability)."""
```

---

## File Structure

```
backend/app/
├── main.py                          # Startup initialization
├── agents/
│   ├── dm_agent.py                  # Uses: router.request(Capability.NARRATIVE)
│   ├── npc_agent.py                 # Uses: router.request(Capability.DIALOGUE)
│   ├── world_sim_agent.py           # Uses: router.request(Capability.WORLD_SIMULATION)
│   └── rules_agent.py               # Uses: router.request(Capability.RULES_REASONING)
├── services/
│   └── llm/
│       ├── __init__.py              # Exports
│       ├── provider.py              # LlmProvider interface
│       ├── provider_manager.py      # ProviderManager (NEW)
│       ├── router.py                 # ModelRouter (refactored)
│       ├── factory.py               # ProviderFactory
│       └── llama_cpp_provider.py    # LlamaCpp implementation
└── core/
    └── config.py                    # Model configurations
```

---

## How Agents Use the Router

### Example: DM Agent

```python
from app.services.llm import get_router, Capability

class DmAgent:
    def __init__(self):
        self.router = get_router()  # Get global singleton
    
    def narrate(self, ...):
        # Запрашиваем capability, не модель!
        response = self.router.request(
            capability=Capability.NARRATIVE,
            prompt=prompt,
            system_prompt=system_prompt,
        )
        return response
```

### Example: NPC Agent

```python
class NpcAgent:
    def react(self, ...):
        # Автоматически выбирается лучшая модель для диалогов
        response = self.router.request(
            capability=Capability.DIALOGUE,
            prompt=prompt,
        )
```

---

## Fallback Logic

1. **Try preferred model** - Пробуем первую предпочтительную модель
2. **Try other preferred** - Пробуем остальные предпочтительные
3. **Try any available** - Пробуем любую доступную модель
4. **Use legacy mode** - Fallback на старый single-provider режим

---

## Initialization Flow

```
1. FastAPI starts
   ↓
2. startup_event() in main.py
   ↓
3. initialize_router()
   ↓
4. ProviderManager.initialize_all()
   - Creates provider for each model in settings.available_models
   - Sets up health checks
   ↓
5. ModelRouter ready
   ↓
6. Agents can now use get_router()
```

---

## Migration from Old System

### Old Code (Single Provider)
```python
from app.services.llm.factory import get_provider

provider = get_provider()
response = provider.complete(prompt)
```

### New Code (Router)
```python
from app.services.llm import get_router, Capability

router = get_router()
response = router.request(
    capability=Capability.NARRATIVE,
    prompt=prompt,
)
```

### Or even simpler (Agent-based)
```python
router = get_router()
response = router.request_for_agent(
    agent_name="dm",  # Auto-maps to NARRATIVE
    prompt=prompt,
)
```

---

## Configuration

Models are configured in `app/core/config.py`:

```python
class Settings(BaseSettings):
    # Model paths
    model_saiga_path: str = "..."
    model_yandex_path: str = "..."
    model_qwen_7b_path: str = "..."
    model_qwen_9b_path: str = "..."
    
    # Available models registry
    available_models: Dict[str, ModelConfig] = {
        "saiga": ModelConfig(name="saiga", path=..., ...),
        "yandex": ModelConfig(...),
        ...
    }
```

---

## Benefits

1. **Automatic** - Никакого ручного переключения моделей
2. **Optimal** - Каждый агент использует лучшую модель для своей задачи
3. **Resilient** - Fallback логика при недоступности моделей
4. **Extensible** - Легко добавить новые модели и провайдеры
5. **Maintainable** - Централизованная логика маршрутизации

---

## Future Enhancements

- [ ] Add OpenAI/Anthropic API providers
- [ ] Add model hot-swap without restart
- [ ] Add usage metrics per capability
- [ ] Add dynamic model loading based on VRAM
- [ ] Support multiple simultaneous models

