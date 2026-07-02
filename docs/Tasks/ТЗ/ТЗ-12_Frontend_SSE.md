## ТЗ-12: Frontend SSE — подключение стриминга

**Статус:** ❌ МЁРТВЫЙ | **Критичность:** HIGH | **Волна:** 1 (5-30 мин)

---

### Суть проблемы одной строкой

Весь SSE-стриминг реализован на бэкенде, но фронтенд **никогда его не вызывает**. Плюс два бага-убийцы в одной строке и в обработке ошибок.

---

### Баг 2 (HIGH): Error log — захардкоженный Windows-путь

**Файл:** `backend/app/api/routes.py` строка 462

```python
# СЕЙЧАС (сломано):
error_path = "C:/DDD/Codex/VSC_Enigma/Enigma/backend/error.log"
#             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
# На Linux/macOS → FileNotFoundError → маскирует оригинальную ошибку
```

**Что ломается:**
- При любой ошибке в `/game/action` обработчик пытается записать лог
- На Linux/macOS путь не существует → **вторичное исключение**
- Пользователь видит "Internal Server Error" без полезной информации
- Оригинальная ошибка потеряна

**Как чинить:**
```python
# ВАРИАНТ А: использовать settings
import os
error_path = os.path.join(settings.saves_dir, "error.log")

# ВАРИАНТ Б: использовать стандартный logging (рекомендуется)
import logging
logger = logging.getLogger("enigma.api")
try:
    ...
except Exception as e:
    logger.exception("Game action failed")  # автоматически запишет traceback
    raise HTTPException(status_code=500, detail=str(e))
```

---

### Баг 3 (HIGH): SSE endpoint мёртв — фронтенд не вызывает

**Файлы:**
- `backend/app/api/routes_stream.py` — SSE endpoint реализован
- `frontend/api_client.py` — вызывает **синхронный** `/api/game/action`
- `frontend/game_screen.py` — использует `GameLoopBridge` (in-process)

```python
# routes_stream.py — РЕАЛИЗОВАНО, НО МЁРТВО:
@router.post("/api/game/action/stream")
async def stream_game_action(request: ActionRequest):
    async def event_generator():
        async for token in game_loop.stream_turn(...):
            yield f"data: {json.dumps({'token': token})}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# api_client.py — ВЫЗЫВАЕТ СИНХРОННЫЙ:
class HttpGameGateway:
    async def action(self, ...):
        response = await self._http.post("/api/game/action", ...)  # ← НЕ /stream
```

**Как чинить — 3 шага:**

**Шаг А:** Добавить SSE-клиент в `api_client.py`:
```python
class HttpGameGateway:
    async def stream_action(self, request, on_token: Callable[[str], None]):
        """SSE-стриминг: вызывает /api/game/action/stream"""
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/game/action/stream",
                json=request,
                timeout=60.0,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if "token" in data:
                            on_token(data["token"])
                        elif "done" in data:
                            return data["result"]
```

**Шаг Б:** Добавить флаг режима в `game_screen.py`:
```python
class GameScreen:
    def __init__(self, ..., execution_mode: str = "in_process"):
        self.execution_mode = execution_mode
        # "in_process" → GameLoopBridge (desktop, по умолчанию)
        # "http_sse"   → HttpGameGateway.stream_action (web)

    async def submit_action(self, player_input: str):
        if self.execution_mode == "http_sse":
            # Стриминг: обновляем текст по мере поступления токенов
            self.dm_response_text = ""
            await self.gateway.stream_action(
                request={"input": player_input},
                on_token=lambda token: self._append_token(token),
            )
        else:
            # Синхронный: весь ответ разом
            result = await self.bridge.turn(player_input)
            self.dm_response_text = result.dm_response
```

**Шаг В:** Показывать typing indicator при стриминге:
```python
def _append_token(self, token: str):
    self.dm_response_text += token
    self._update_response_display()
    # Показать "..." или анимацию пока стриминг идёт
```

---

### Баг 4 (MEDIUM): Двойной путь выполнения — путаница

**Файлы:** `frontend/game_loop_bridge.py` vs `frontend/api_client.py`

```
Сейчас:
  game_screen.py ─→ GameLoopBridge ─→ импортирует backend напрямую (in-process)
  api_client.py  ─→ HttpGameGateway ─→ HTTP запросы к FastAPI (НИКОГДА НЕ ВЫЗЫВАЕТСЯ)

Проблема:
  - FastAPI сервер может не работать — игра всё равно идёт
  - SSE мёртв — нет HTTP пути
  - CORS не нужен — нет кросс-доменных запросов
  - Два набора типов: TurnResult vs GameActionResponse
```

**Как чинить:** Документировать выбор:
```python
# В game_screen.py или конфигурации:
EXECUTION_MODE = os.getenv("ENIGMA_MODE", "in_process")
# "in_process" — для desktop-приложения (PyQt/Pygame)
# "http_sse"   — для web-версии (браузерный клиент)

# При "in_process" — FastAPI не нужен, GameLoopBridge работает напрямую
# При "http_sse"   — нужен запущенный сервер, стриминг работает
```

---

### Порядок исправления

| # | Баг | Сложность | Время |
|---|-----|-----------|-------|
| 2 | Windows path → logging | 5 строк | 2 мин |
| 3 | SSE-клиент в api_client.py | 25 строк | 30 мин |
| 4 | Флаг execution_mode | 10 строк | 10 мин |
| 5 | Typing indicator | 5 строк | 10 мин |

**Баг 2 — фикс за 2 минуты.** Баг 3-5 — если нужен web-режим со стримингом.

---

Давать следующее? Это **ТЗ-03: MovementEngine injuries** (ранения теряются между тиками).