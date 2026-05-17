"""
World Simulation Agent - World Event Generation

Uses capability-based routing for world simulation.
"""

from typing import Optional

from app.services.llm import ModelRouter, get_router


class WorldSimulationAgent:
    """
    World simulation agent with automatic model selection.
    
    Uses ModelRouter to request 'world_simulation' capability.
    """

    def __init__(self, router: Optional[ModelRouter] = None) -> None:
        self._router = router

    @property
    def router(self) -> ModelRouter:
        """Lazy initialization of router via global singleton."""
        if self._router is None:
            self._router = get_router()
        return self._router

    def simulate(
        self,
        location: str,
        actions: list,
        current_events: list[str],
    ) -> dict:
        """
        Simulate world events based on player actions.
        
        The agent requests 'world_simulation' capability.
        Router автоматически выбирает модель для симуляции.
        """
        prompt = self._build_prompt(location, actions, current_events)
        system_prompt = self._get_system_prompt()
        
        try:
            # request_for_agent — синхронная версия для агентов вне async-контекста
            response = self.router.request_for_agent(
                agent_name="world",
                prompt=prompt,
                system_prompt=system_prompt,
            )
            
            return {
                "world_events": [response],
                "simulation_log": f"Simulated in {location}",
            }
        except Exception as e:
            print(f"World Sim Agent error: {e}, using fallback")
            return self._fallback_simulate(location, actions, current_events)

    def generate_event(
        self,
        location: str,
        context: str,
    ) -> str:
        """Generate a world event for a location."""
        prompt = f"""Локация: {location}
Контекст: {context}

Сгенерируй одно событие которое происходит в этой локации.
Событие должно быть логичным для мира D&D 5e.
Будь краток (1-2 предложения)."""
        
        system_prompt = """Ты - симулятор мира D&D 5e.
Генерируй события которые логично развивают мир.
Учитывай текущую ситуацию и предыдущие события."""
        
        try:
            return self.router.request_for_agent(
                agent_name="world",
                prompt=prompt,
                system_prompt=system_prompt,
            )
        except Exception as e:
            print(f"World event error: {e}")
            return "Ничего особенного не происходит."

    def _build_prompt(
        self,
        location: str,
        actions: list,
        current_events: list[str],
    ) -> str:
        """Build simulation prompt."""
        action_str = "\n".join(f"- {a}" for a in actions) if actions else "- Нет действий"
        event_str = "\n".join(f"- {e}" for e in current_events) if current_events else "- Нет текущих событий"
        
        return f"""Локация: {location}
Текущие события:
{event_str}
Действия игроков:
{action_str}

Симулируй как эти действия повлияют на мир.
Опиши изменения в мире (события, NPC, погода, время)."""

    def _get_system_prompt(self) -> str:
        """Get system prompt for world simulation."""
        return """Ты - симулятор мира D&D 5e.
Отслеживай изменения в мире:
- NPC меняют локации
- События развиваются
- Квесты продвигаются
- Время течёт

Веди логику мира последовательно и логично."""

    def _fallback_simulate(
        self,
        location: str,
        actions: list,
        current_events: list[str],
    ) -> dict:
        """Fallback when LLM is unavailable."""
        return {
            "world_events": [f"Мир в {location} продолжает существовать."],
            "simulation_log": "Fallback mode",
        }

    def tick(self, world_id: str) -> dict:
        """
        Alias for backward compatibility.
        
        WorldScheduler and Orchestrator call this method,
        but the agent internally uses simulate() with location/actions.
        Since tick() doesn't have context, we simulate a generic world event.
        """
        # Try to get recent location from memory if available
        # For now, use a generic simulation
        return self.simulate(
            location="unknown",
            actions=[],
            current_events=[],
        )

