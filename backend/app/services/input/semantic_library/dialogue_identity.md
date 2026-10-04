# semantic-module: dialogue_identity
> version: 1
> status: experimental (Э2 interference gate; production source of truth = inline)
> origin: Э2-вердикт (один relation: референт вопроса о имени — третье лицо vs собеседник)
> family: identity

## contrast-block

- Контрастная пара для границы классов: "Как зовут твоего караванщика?" — вопрос об ИМЕНИ ТРЕТЬЕГО ЛИЦА, факт мира -> acts: [{"type": "QUESTION", "params": {"topic": "имя караванщика"}}]; "Как тебя зовут?" — вопрос об ИДЕНТИЧНОСТИ СОБЕСЕДНИКА -> acts: [{"type": "ASK_IDENTITY"}]. Первый спрашивает факт о третьем лице; второй — кто перед ним.

## notes
- anchor семейства = вторая нога пары ("Как тебя зовут?" -> ASK_IDENTITY); ASK_IDENTITY в production A мёртв ("Кто ты?" -> QUESTION) — оживление = identity-transfer тест Э2
- add-only модуль: enum-tail секции НЕТ, перечисление semantic_acts не заменяет
- отрицания identity ("Я не Мю") сознательно не включены (вердикт: сложная семантика correction/denial) — остаются независимыми probe
