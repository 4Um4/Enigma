"""
Сервис для проверки доступности LLM с кэшированием.
"""
import time
from typing import Optional

import httpx


class LLMService:
    """
    Сервис для мониторинга состояния LLM.
    
    Особенности:
    - Кэширование результата проверки на 5 секунд
    - Проверка через /v1/models endpoint
    """
    
    def __init__(self, llm_url: str = "http://127.0.0.1:8080"):
        from app.core.config import settings  # импорт внутри конструктора
        self.llm_url = llm_url
        self._cache: Optional[dict] = None
        self._cache_timestamp: float = 0
        self._cache_ttl: float = settings.llm_health_check_interval_sec
    
    def _is_cache_valid(self) -> bool:
        """Проверить, валиден ли кэш."""
        if self._cache is None:
            return False
        return (time.time() - self._cache_timestamp) < self._cache_ttl
    
    def check_health(self, use_cache: bool = True) -> dict:
        """
        Проверить здоровье LLM.
        
        Args:
            use_cache: использовать кэшированный результат
            
        Returns:
            dict с полями status и details
        """
        # Возвращаем кэшированный результат если валиден
        if use_cache and self._is_cache_valid():
            return self._cache
        
        # Проверяем LLM
        try:
            with httpx.Client(timeout=settings.llama_cpp_timeout_sec) as client:
                response = client.get(f"{self.llm_url}/v1/models")
                
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("data", [])
                    model_name = models[0].get("id", "unknown") if models else "unknown"
                    
                    self._cache = {
                        "status": "online",
                        "model": model_name,
                        "url": self.llm_url
                    }
                else:
                    self._cache = {
                        "status": "error",
                        "code": response.status_code,
                        "details": f"HTTP {response.status_code}"
                    }
        except httpx.ConnectError:
            self._cache = {
                "status": "offline",
                "details": "Connection refused"
            }
        except httpx.TimeoutException:
            self._cache = {
                "status": "timeout",
                "details": "Connection timeout"
            }
        except Exception as e:
            self._cache = {
                "status": "error",
                "details": str(e)
            }
        
        self._cache_timestamp = time.time()
        return self._cache
    
    def is_online(self) -> bool:
        """Быстрая проверка - онлайн ли LLM."""
        result = self.check_health()
        return result.get("status") == "online"
    
    def invalidate_cache(self) -> None:
        """Сбросить кэш."""
        self._cache = None
        self._cache_timestamp = 0


# Глобальный экземпляр
llm_service = LLMService()

