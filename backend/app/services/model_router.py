from dataclasses import dataclass

from app.models.schemas import ModelSelection


@dataclass
class ModelRouter:
    """Runtime model selection for local/API providers."""

    current: ModelSelection | None = None

    def switch(self, selection: ModelSelection) -> ModelSelection:
        self.current = selection
        return selection

    def describe(self) -> str:
        if not self.current:
            return "Модель не выбрана"
        endpoint = f" ({self.current.endpoint})" if self.current.endpoint else ""
        return f"{self.current.provider}:{self.current.model_name}{endpoint}"
