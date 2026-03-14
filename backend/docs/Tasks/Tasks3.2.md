Техническое задание
Стабильная система выбора и активации персонажа
1. Цель

Обеспечить корректную работу игрового цикла:

выбор персонажа
→ активация персонажа
→ ввод сообщений
→ обработка сервером

Система должна:

сохранять выбранного персонажа

синхронизировать состояние frontend и backend

исключить ситуации когда персонаж «теряется»

блокировать отправку сообщений без активного персонажа

автоматически восстанавливать состояние после reload / переключения вкладки

2. Основной архитектурный принцип

Single Source of Truth

Единственный источник истины:

Backend session

Frontend не хранит состояние как факт,
он только запрашивает состояние у сервера.

3. Новый жизненный цикл игрока
Шаг 1 — загрузка страницы

Frontend вызывает:

GET /api/player/session

Ответ:

{
  "player": "Демеург",
  "active": true
}

или

{
  "player": null,
  "active": false
}
Шаг 2 — выбор персонажа

Frontend вызывает:

POST /api/player/select
{
  "player": "Демеург"
}

Ответ:

{
  "status": "ok",
  "player": "Демеург"
}

Backend:

создаёт player session

ставит active = true

Шаг 3 — активация heartbeat

После успешного select:

Frontend запускает:

POST /api/player/heartbeat

каждые

2 секунды
Шаг 4 — отправка сообщений

Перед отправкой:

Frontend проверяет

session.active == true

Если нет:

кнопка SEND disabled
4. Новый API
4.1 Получение сессии
GET /api/player/session

Ответ:

{
  player: string | null,
  active: bool
}
4.2 Выбор персонажа
POST /api/player/select

Body

{
  player: string
}

Ответ

{
  status: "ok"
}
4.3 Heartbeat
POST /api/player/heartbeat

Body

{
  player: string
}

Ответ

{
  active: true
}
4.4 Проверка активных игроков
GET /api/player/active

Ответ

{
  players: ["Демеург"]
}
5. Изменения Frontend
5.1 Удалить

Полностью удалить:

GlobalStore
localStorage currentPlayer
storage event listener
visibility listener

Они создают рассинхронизацию.

5.2 Новый frontend state

Единственный state:

let session = {
  player: null,
  active: false
}
5.3 Инициализация

При загрузке:

loadSession()
GET /api/player/session
5.4 Выбор персонажа
async selectPlayer(player)
POST /api/player/select

После успеха:

session.player = player
session.active = true
startHeartbeat()
5.5 Heartbeat
setInterval(() => {
    POST /api/player/heartbeat
}, 2000)
5.6 Кнопка отправки

Правило:

if (!session.active)
   disable send button
6. Изменения Backend
6.1 PlayerSessionService

Структура:

sessions = {
   campaign_id : {
       player : {
           last_heartbeat
       }
   }
}
6.2 TTL

Heartbeat timeout

10 секунд
6.3 Проверка перед обработкой сообщения

Если

player not active

вернуть

412 PLAYER_NOT_ACTIVE
7. Удалить race conditions

Активация должна происходить строго в порядке

select player
→ create session
→ heartbeat
→ allow messages
8. UI изменения
Экран 1
Выберите персонажа
Экран 2
чат

Переход возможен только если

session.active == true
9. Логирование

Добавить лог:

PLAYER_SELECTED
PLAYER_HEARTBEAT
PLAYER_DEACTIVATED
MESSAGE_REJECTED_NO_PLAYER




Улучшения (опционально)

После стабилизации системы:

WebSocket вместо heartbeat
persistent connection
Multiplayer
несколько игроков в одной кампании