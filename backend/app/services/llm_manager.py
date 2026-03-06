from app.models.schemas import ModelSelection
from app.services.model_router import ModelRouter


class LlmManager:
    """Facade for model switching and prompt dispatch."""

    def __init__(self) -> None:
        self.router = ModelRouter()

    def switch_model(self, selection: ModelSelection) -> ModelSelection:
        return self.router.switch(selection)

    def active_model(self) -> str:
        return self.router.describe()

    def run(self, prompt: str) -> str:
        # MVP stub: replace with provider-specific API/local inference adapters.
        return f"[LLM:{self.active_model()}] {prompt}"
