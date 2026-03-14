Очень рекомендую добавить DEBUG вывод

В handleSendMessage() добавь:

console.log("Sending to API:", content);
console.log("API response:", response);

И смотри DevTools → Console.

Самый правильный способ исправить

Навсегда отключи  и забудь про демо режим.

Замени блок:

catch (error) {

на

catch (error) {
    showError("Сервер недоступен");
    return;
}

Теперь если LLM не работает — ты сразу увидишь ошибку.


Почему в истории видны команды типа
/attack tree
/open banana
/save save

Это потому что frontend не фильтрует команды.

Сейчас handleSendMessage() отправляет любой текст:

const content = elements.messageInput.value.trim();

То есть DM получает:

/attack tree

хотя это должна быть системная команда.

3. Как это исправить (правильная система команд)

Добавь обработчик команд.

В JS перед отправкой:
if (content.startsWith("/")) {
    handleCommand(content);
    elements.messageInput.value = "";
    return;
}
Пример функции
function handleCommand(cmd) {

    const parts = cmd.split(" ");
    const command = parts[0];

    switch(command) {

        case "/roll":
            handleDiceRoll(parts[1] || "d20");
            break;

        case "/clear":
            elements.chatArea.innerHTML = "";
            break;

        case "/help":
            addMessage(
                "Система",
                "Команды: /roll d20, /clear, /help",
                "dm"
            );
            break;

        default:
            showError("Неизвестная команда");
    }
}

Теперь команды не будут идти в LLM.

4. Вторая проблема интерфейса

В HTML есть сломанные div.

Например:

<div class="panel-header">
...
<div class="chat-area">

Но panel-header не закрыт.

Должно быть:

<div class="panel-header">
</div>

<div class="chat-area">

Таких мест несколько.

Это может ломать layout.

5. Очень важное улучшение

Сейчас frontend не знает состояние игры.

Но у тебя уже есть API:

/session/state
/interface/players
/interface/facts

Сделай автообновление состояния.

Добавь:

setInterval(updateGameState, 3000);

Функция:

async function updateGameState() {
    try {
        const players = await API.getPlayers(state.campaignId);
        state.players = players;
        updatePlayersList();
    } catch(e) {}
}
6. Следующий уровень (очень мощная идея)

Сейчас у тебя LLM реагирует на текст.

Но можно сделать структурированный ответ.

Пример ответа DM:

{
 "dm_text": "Орк атакует",
 "dice_roll": "d20",
 "target": "Артём",
 "damage": 5
}

Тогда UI может:

показывать анимацию

менять HP

показывать броски

Это делает игру настоящей системой, а не просто чат.

7. Ещё одна очень полезная вещь

Добавь Debug Console в панель мастера.

Новая вкладка:

DEBUG

И лог:

API Request
LLM Prompt
LLM Response
Token usage
Latency

Это золото для разработки AI игр.

А так же: Техническое задание для LLM: интеграция Debug Mode в start_enigma.bat
Цель

Обеспечить автоматическую проверку и визуальное отображение состояния всех критических компонентов Enigma при запуске:

LLaMA Server

FastAPI Backend

Frontend HTTP Server

Браузерный интерфейс

Вывод должен содержать:

Статус компонента: запущен / ошибка / не найден

Время ответа (если применимо)

Подробности ошибки (например, порт занят, Python не найден)

Рекомендации по исправлению

Требования к реализации

Проверка зависимостей

Python 3.10+

Наличие всех нужных папок и скриптов

Порты: 8080 (LLaMA), 8000 (FastAPI), 8081 (Frontend)

Запуск компонентов

LLaMA Server → проверка доступности http://127.0.0.1:8080/ping

FastAPI → проверка доступности http://127.0.0.1:8000/docs

Frontend → проверка доступности http://127.0.0.1:8081/ui/index.html

Реализация дебаг-вывода

Цветовое оформление:

✅ зелёный – работает

⚠️ жёлтый – запускается, но не отвечает

❌ красный – не найден / не запускается

Логирование в консоль и опционально в файл debug_log.txt

Авто-проверка браузера

После запуска Frontend попытка открыть браузер

Если не удаётся – сообщение с предложением открыть вручную

Таймауты и повторные проверки

Таймаут ожидания старта каждого компонента: 10 секунд

Если компонент не отвечает, пробовать 2 повторные попытки

Флаги запуска

/debug – включить режим дебага

/silent – запуск без проверки (для быстрого старта)

Интеграция в BAT

Минимальная модификация текущего start_enigma.bat

Использовать встроенные команды Windows (timeout, curl / powershell Invoke-WebRequest)

Для более точного ответа можно использовать Python скрипт check_services.py с возвратом JSON статусов, BAT его парсит

Пример логики проверки (псевдокод)

for each component:
    start component in background
    wait X секунд
    try:
        ping component endpoint
        if response ok:
            print ✅ Component running
        else:
            print ⚠️ Component started but not responding
    except:
        print ❌ Component failed to start

Дополнительно

Опционально подсветка, какая служба «тормозит» и где нужно вмешательство

Возможность сохранять состояние запуска для последующей диагностики