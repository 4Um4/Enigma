# Crosswalk: старый канон vs новый draft

- Старый канон: 59 записей
- Новый draft: 53 записей
- Строк crosswalk: 59

## Сводка по статусам

| Статус | Кол-во |
|--------|--------|
| PRESERVED | 18 |
| RECLASSIFIED | 13 |
| MERGED | 2 |
| DUPLICATED | 1 |
| LOST | 22 |
| AMBIGUOUS | 3 |

## Сводка по kind (только критичные: EFFECT, LOCATION, BELIEF_SEED)

### EFFECT

| Статус | Кол-во |
|--------|--------|
| AMBIGUOUS | 1 |
| LOST | 7 |
| RECLASSIFIED | 7 |

### BELIEF_SEED

| Статус | Кол-во |
|--------|--------|
| AMBIGUOUS | 2 |
| LOST | 2 |
| MERGED | 2 |
| RECLASSIFIED | 2 |

## LOST (полная потеря)

| ordinal | kind | summary |
|---------|------|---------|
| 100 | EVENT | семья убита бандитами |
| 202 | EFFECT | она единственные, кто вообще хоть как-то ей помогал | gain |
| 203 | EFFECT | других отношений она и не знала | loss |
| 204 | EVENT | так прошло ещё 4 года её жизни |
| 401 | EFFECT | ее приставили к нему не просто так | она | gain |
| 600 | EVENT | регулярно, когда Торнин напивался, он периодически избивал её |
| 1000 | TRAIT_SEED | влюблена | с 12 лет она влюблена в стражника |
| 1002 | EVENT | приняла его наблюдение за искреннюю доброжелательность к себе |
| 1003 | TRAIT_SEED | влюблена | с 12 лет она влюблена в стражника |
| 1200 | EFFECT | предполагает, что таверну могут доверить ей после смерти Торнина | таверну | gai |
| 1300 | EVENT | стал постоянным посетителем таверны агент гильдии воров Тень |
| 1301 | EFFECT | улучшить жизнь | desire |
| 1302 | TRAIT_SEED | готова на всё ради шанса | она готова на всё ради этого шанса |
| 1400 | EVENT | совершенно не помнит, кем были её родители и были ли у неё иные родственники; не |
| 1600 | BELIEF_SEED | Она не покорна Гильдии от любви или веры. Она покорна, потому что считала вариан |
| 1602 | TRAIT_SEED | расчётливый | это не покорность, а расчёт ребёнка |
| 1603 | PORTRET | Люся злится. Злится часто, глухо, изнутри… |
| 1704 | RELATIONSHIP | Два человека реагируют на один звук. | synchronization | neutral |
| 1800 | TRAIT_SEED | умеет считать лучше, чем говорить | П.16 — не метафора: она действительно умеет  |
| 1900 | EFFECT | копится её юг: медяки и серебро | gain |
| 1903 | BELIEF_SEED | для неё это просто «её» деньги — первый в жизни предмет, который принадлежит тол |
| 2101 | EFFECT | видит весь зал: где кто сидит, кто сколько выпил, кто задержался у стойки дольше |

## AMBIGUOUS (неоднозначно)

| ordinal | kind | summary | candidates |
|---------|------|---------|-----------|
| 1901 | BELIEF_SEED | источник горький — это в основном деньги Орма | 3 |
| 1902 | EFFECT | деньги Орма, то самое «хорошее отношение» являются источником её заначки | gain | 3 |
| 2004 | BELIEF_SEED | господин стражник, господин купец | 2 |

## RECLASSIFIED (kind изменился)

| ordinal | old_kind | new_kind | old_summary | new_text |
|---------|----------|----------|-------------|----------|
| 200 | EVENT | RELATIONSHIP | примерно в то же время её подобрала Гильдия воров | Гильдия воров к ней относятся недоброжелательно, но помогают |
| 700 | EVENT | RELATIONSHIP | Гильдия отправила её следить за тайным ходом в таверне и за  | Гильдия отправила следить за тайным ходом в таверне и за Тор |
| 900 | EVENT | TRAIT_SEED | стражник Борко задержался у кухни и застал сцену насилия Орм | наблюдает за насилием и мастурбирует | задержался у кухни и  |
| 1101 | EFFECT | PORTRET | понимает, что Гильдия с её связями быстро найдёт её и «накаж | Люся не дура. В четырнадцать лет она понимает больше, чем ин |
| 1201 | EFFECT | TRAIT_SEED | выслужиться перед Гильдией и попасть в лучшие условия | лучш | хочет выслужиться перед Гильдией | Отчасти поэтому её второй |
| 1202 | BELIEF_SEED | TRAIT_SEED | она даже предполагает, что таверну могут доверить ей после с | рассчитывает на выгодную сделку с Гильдией | Она верит в сде |
| 1303 | EFFECT | RELATIONSHIP | не навредит её возлюбленному стражнику Борко | возлюбленный  | Люся ожидает приказа от гильдии воров, готовая на всё ради ш |
| 1401 | EFFECT | PORTRET | помнит смутно, но оценивает: тогда жизнь была беднее и пусте | жизнь в подземных убежищах гильдии была беднее и пустее, но  |
| 1402 | BELIEF_SEED | EVENT | она ощущает текущий этап жизни как миссию, дарованную органи | ощущает текущий этап жизни как миссию, дарованную организаци |
| 1700 | EFFECT | RELATIONSHIP | Звон посуды заставляет её замечать паузу в своей работе. | t | Торнин реагирует на звон посуды | Торнин |
| 1701 | EFFECT | RELATIONSHIP | Звон посуды вызывает вздрагивание у Торнина. | Торнин | trau | Торнин реагирует на звон посуды | Торнин |
| 2100 | TRAIT_SEED | PORTRET | шпион | привычка шпиона, вшитая гильдией в ребёнка (п.7) и р | Это не любопытство — это привычка шпиона, вшитая гильдией в  |
| 2102 | EFFECT | EVENT | возле Борко задерживается дольше, чем требует поднос | Борко | Борко задерживается дольше, чем требует поднос | Стражник Бо |

## Полная таблица

| ordinal | kind | status | rationale |
|---------|------|--------|-----------|
| 0 | PORTRET | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.20) |
| 100 | EVENT | LOST | no semantic match (score < 0.2) |
| 200 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → RELATIONSHIP |
| 201 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 202 | EFFECT | LOST | no semantic match (score < 0.2) |
| 203 | EFFECT | LOST | no semantic match (score < 0.2) |
| 204 | EVENT | LOST | no semantic match (score < 0.2) |
| 300 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 400 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 401 | EFFECT | LOST | no semantic match (score < 0.2) |
| 500 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 600 | EVENT | LOST | no semantic match (score < 0.2) |
| 700 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → RELATIONSHIP |
| 900 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → TRAIT_SEED |
| 1000 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 1001 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 1002 | EVENT | LOST | no semantic match (score < 0.2) |
| 1003 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 1004 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 1005 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 1100 | DESIRE_SEED | PRESERVED | 1 match, same kind (DESIRE_SEED) |
| 1101 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → PORTRET |
| 1200 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1201 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → TRAIT_SEED |
| 1202 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → TRAIT_SEED |
| 1300 | EVENT | LOST | no semantic match (score < 0.2) |
| 1301 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1302 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 1303 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 1304 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 1400 | EVENT | LOST | no semantic match (score < 0.2) |
| 1401 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → PORTRET |
| 1402 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → EVENT |
| 1600 | BELIEF_SEED | LOST | no semantic match (score < 0.2) |
| 1601 | BELIEF_SEED | MERGED | meaning distributed across 2 new entries (top=0.95, 2nd=0.69) |
| 1602 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 1603 | PORTRET | LOST | no semantic match (score < 0.2) |
| 1700 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 1701 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 1702 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 1703 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 1704 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 1800 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 1900 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1901 | BELIEF_SEED | AMBIGUOUS | multiple candidates with close scores (top=0.60, 2nd=0.60) |
| 1902 | EFFECT | AMBIGUOUS | multiple candidates with close scores (top=0.26, 2nd=0.24) |
| 1903 | BELIEF_SEED | LOST | no semantic match (score < 0.2) |
| 2000 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2001 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2002 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2003 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2004 | BELIEF_SEED | AMBIGUOUS | multiple candidates with close scores (top=0.67, 2nd=0.67) |
| 2005 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2006 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2007 | BELIEF_SEED | MERGED | meaning distributed across 2 new entries (top=0.40, 2nd=0.20) |
| 2100 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → PORTRET |
| 2101 | EFFECT | LOST | no semantic match (score < 0.2) |
| 2102 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → EVENT |
| 2103 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |