Предлагаю дорожную карту:

1. Убрать дублирование прибытия NPC (критично)
Каждый тик life_engine добавляет "прибыл" для blacksmith_orm. Это яд для 7B.

2. Починить TARGET логику
После успешного S.0 MATCH不应 быть "No target found".

3. Логировать DM ответ
Видеть что реально ответила модель — без этого слепая отладка.

Лог работает. Вижу **пять проблем** из лога:

**1. TARGET противоречие:**
```
[TARGET] Selected Люся (maid_lusya) from 1 candidates at pos 0
[TARGET] Extracted: Люся (maid_lusya)
[TARGET] No target found in: Люся привет...
```
Нашла → извлекла → "не найдена". **Таргет не попадает в промпт.**

**2. Телеграф NPC как действие игрока:**
```
[TELEGRAPH] event-driven: blacksmith_orm проявляет инициативу
...
Действия игроков:
Демеург: blacksmith_orm проявляет инициативу
```
Промпт получает мусор + устаревший таргет "Обращение к Торнину".

**3. Кузнец прибывает 3 раза за тик:**
```
[LIFE_ENGINE] Прибыли в сцену: ['blacksmith_orm', 'blacksmith_orm', 'blacksmith_orm']
```

**4. Гендерная ошибка:**
```
[NPC] Люся... имя, которое он произнёс
```
"он" вместо "она" — pronoun `[он]` не работает для female.

**5. Первый ответ — описание таверны вместо реакции:**
```
[DM] Люся привет
[NPC] Ты видишь ярко освещенные барные стойки...
```

---

Начинаю с **пункта 1** — TARGET. Найду где теряется таргет после Extracted:

```
Get-ChildItem -Path "backend/" -Filter "*.py" -Recurse | Select-String -Pattern "No target found" | Select-Object Path, LineNumber
```