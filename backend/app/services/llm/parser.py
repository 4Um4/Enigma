import json
import re
from typing import Dict

class ResponseParser:
    @staticmethod
    def parse_npc_response(raw_text: str, npc_name: str) -> Dict[str, str]:
        """Парсит JSON из ответа LLM. Если JSON битый — возвращает fallback."""
        try:
            # Очистка текста от возможных "мыслей" модели вне JSON
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return {
                    "action": data.get("action", f"{npc_name} молча наблюдает."),
                    "speech": data.get("speech", ""),
                    "target": data.get("target", "all")
                }
        except Exception:
            pass
            
        # Fallback если всё сломалось
        return {
            "action": f"{npc_name} выглядит растерянным.",
            "speech": "...",
            "target": "all"
        }
