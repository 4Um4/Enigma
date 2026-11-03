# Crosswalk: старый канон vs новый draft

- Старый канон: 59 записей
- Новый draft: 49 записей
- Строк crosswalk: 59

## Сводка по статусам

| Статус | Кол-во |
|--------|--------|
| PRESERVED | 13 |
| RECLASSIFIED | 18 |
| MERGED | 2 |
| DUPLICATED | 1 |
| LOST | 25 |
| AMBIGUOUS | 0 |

## Сводка по kind (только критичные: EFFECT, LOCATION, BELIEF_SEED)

### EFFECT

| Статус | Кол-во |
|--------|--------|
| LOST | 5 |
| MERGED | 1 |
| PRESERVED | 1 |
| RECLASSIFIED | 8 |

### BELIEF_SEED

| Статус | Кол-во |
|--------|--------|
| LOST | 3 |
| MERGED | 1 |
| RECLASSIFIED | 4 |

## LOST (полная потеря)

| ordinal | kind | summary |
|---------|------|---------|
| 100 | EVENT | семья убита бандитами |
| 201 | RELATIONSHIP | отношение к ней нельзя назвать доброжелательным | Гильдия воров | вражда | negat |
| 203 | EFFECT | других отношений она и не знала | loss |
| 204 | EVENT | так прошло ещё 4 года её жизни |
| 600 | EVENT | регулярно, когда Торнин напивался, он периодически избивал её |
| 700 | EVENT | Гильдия отправила её следить за тайным ходом в таверне и за Торнином. |
| 1000 | TRAIT_SEED | влюблена | с 12 лет она влюблена в стражника |
| 1001 | RELATIONSHIP | искренняя доброжелательность к себе | стражник Борко | доверие | positive |
| 1002 | EVENT | приняла его наблюдение за искреннюю доброжелательность к себе |
| 1003 | TRAIT_SEED | влюблена | с 12 лет она влюблена в стражника |
| 1200 | EFFECT | предполагает, что таверну могут доверить ей после смерти Торнина | таверну | gai |
| 1300 | EVENT | стал постоянным посетителем таверны агент гильдии воров Тень |
| 1301 | EFFECT | улучшить жизнь | desire |
| 1303 | EFFECT | не навредит её возлюбленному стражнику Борко | возлюбленный стражник Борко | des |
| 1304 | RELATIONSHIP | более думает о шансах и меньше о побеге | возлюбленный стражник Борко | dependen |
| 1400 | EVENT | совершенно не помнит, кем были её родители и были ли у неё иные родственники; не |
| 1402 | BELIEF_SEED | она ощущает текущий этап жизни как миссию, дарованную организацией, через котору |
| 1602 | TRAIT_SEED | расчётливый | это не покорность, а расчёт ребёнка |
| 1603 | PORTRET | Люся злится. Злится часто, глухо, изнутри… |
| 1704 | RELATIONSHIP | Два человека реагируют на один звук. | synchronization | neutral |
| 1800 | TRAIT_SEED | умеет считать лучше, чем говорить | П.16 — не метафора: она действительно умеет  |
| 1901 | BELIEF_SEED | источник горький — это в основном деньги Орма |
| 1902 | EFFECT | деньги Орма, то самое «хорошее отношение» являются источником её заначки | gain |
| 1903 | BELIEF_SEED | для неё это просто «её» деньги — первый в жизни предмет, который принадлежит тол |
| 2103 | TRAIT_SEED | живое лицо | лицо становится живым |

## AMBIGUOUS (неоднозначно)

| ordinal | kind | summary | candidates |
|---------|------|---------|-----------|

## RECLASSIFIED (kind изменился)

| ordinal | old_kind | new_kind | old_summary | new_text |
|---------|----------|----------|-------------|----------|
| 200 | EVENT | RELATIONSHIP | примерно в то же время её подобрала Гильдия воров | Гильдия воров подобрала Люсю, отношения не доброжелательные  |
| 202 | EFFECT | RELATIONSHIP | она единственные, кто вообще хоть как-то ей помогал | gain | Гильдия воров подобрала Люсю, отношения не доброжелательные  |
| 401 | EFFECT | BELIEF_SEED | ее приставили к нему не просто так | она | gain | Люсю приставили к Торнину не просто так | danger |
| 900 | EVENT | EFFECT | стражник Борко задержался у кухни и застал сцену насилия Орм | Борко открыл в себе наклонность наблюдать за насилием и маст |
| 1101 | EFFECT | PORTRET | понимает, что Гильдия с её связями быстро найдёт её и «накаж | Люся не дура. В четырнадцать лет она понимает больше, чем ин |
| 1202 | BELIEF_SEED | TRAIT_SEED | она даже предполагает, что таверну могут доверить ей после с | расчетный подход к жизни | Она верит в сделку: моя полезност |
| 1302 | TRAIT_SEED | PORTRET | готова на всё ради шанса | она готова на всё ради этого шанс | Люся готова на всё ради шанса улучшить жизнь, но беспокоится |
| 1401 | EFFECT | PORTRET | помнит смутно, но оценивает: тогда жизнь была беднее и пусте | жизнь в подземных убежищах гильдии была беднее и пустее, но  |
| 1600 | BELIEF_SEED | PORTRET | Она не покорна Гильдии от любви или веры. Она покорна, потом | Она покорна, потому что считала варианты — и их нет. Бежать  |
| 1700 | EFFECT | EVENT | Звон посуды заставляет её замечать паузу в своей работе. | t | Звон бьющейся посуды |
| 1701 | EFFECT | EVENT | Звон посуды вызывает вздрагивание у Торнина. | Торнин | trau | Звон бьющейся посуды |
| 1702 | RELATIONSHIP | EVENT | Звон посуды вызывает вздрагивание у Торнина. | Торнин | atte | Звон бьющейся посуды |
| 1703 | RELATIONSHIP | EVENT | Звон посуды вызывает вздрагивание у Торнина. | Торнин | sync | Звон бьющейся посуды |
| 2004 | BELIEF_SEED | RELATIONSHIP | господин стражник, господин купец | адресative: стражник, купец; обращение: господин | формально |
| 2007 | BELIEF_SEED | TRAIT_SEED | боится наказания, а не неприличия | не ругается матом | Не ругается матом — боится наказания, а  |
| 2100 | TRAIT_SEED | PORTRET | шпион | привычка шпиона, вшитая гильдией в ребёнка (п.7) и р | Держится у стен, глаза по полу — но видит весь зал: где кто  |
| 2101 | EFFECT | PORTRET | видит весь зал: где кто сидит, кто сколько выпил, кто задерж | Держится у стен, глаза по полу — но видит весь зал: где кто  |
| 2102 | EFFECT | RELATIONSHIP | возле Борко задерживается дольше, чем требует поднос | Борко | Возле Борко задерживается дольше, чем требует поднос, — един |

## Полная таблица

| ordinal | kind | status | rationale |
|---------|------|--------|-----------|
| 0 | PORTRET | DUPLICATED | >1 matches with same kind (top=1.00, 2nd=0.25) |
| 100 | EVENT | LOST | no semantic match (score < 0.2) |
| 200 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → RELATIONSHIP |
| 201 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 202 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 203 | EFFECT | LOST | no semantic match (score < 0.2) |
| 204 | EVENT | LOST | no semantic match (score < 0.2) |
| 300 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 400 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 401 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → BELIEF_SEED |
| 500 | EVENT | PRESERVED | 1 match, same kind (EVENT) |
| 600 | EVENT | LOST | no semantic match (score < 0.2) |
| 700 | EVENT | LOST | no semantic match (score < 0.2) |
| 900 | EVENT | RECLASSIFIED | 1 match, kind changed: EVENT → EFFECT |
| 1000 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 1001 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 1002 | EVENT | LOST | no semantic match (score < 0.2) |
| 1003 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 1004 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 1005 | RELATIONSHIP | PRESERVED | 1 match, same kind (RELATIONSHIP) |
| 1100 | DESIRE_SEED | PRESERVED | 1 match, same kind (DESIRE_SEED) |
| 1101 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → PORTRET |
| 1200 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1201 | EFFECT | MERGED | meaning distributed across 2 new entries (top=0.80, 2nd=0.29) |
| 1202 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → TRAIT_SEED |
| 1300 | EVENT | LOST | no semantic match (score < 0.2) |
| 1301 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1302 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → PORTRET |
| 1303 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1304 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 1400 | EVENT | LOST | no semantic match (score < 0.2) |
| 1401 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → PORTRET |
| 1402 | BELIEF_SEED | LOST | no semantic match (score < 0.2) |
| 1600 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → PORTRET |
| 1601 | BELIEF_SEED | MERGED | meaning distributed across 2 new entries (top=1.00, 2nd=0.69) |
| 1602 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 1603 | PORTRET | LOST | no semantic match (score < 0.2) |
| 1700 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → EVENT |
| 1701 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → EVENT |
| 1702 | RELATIONSHIP | RECLASSIFIED | 1 match, kind changed: RELATIONSHIP → EVENT |
| 1703 | RELATIONSHIP | RECLASSIFIED | 1 match, kind changed: RELATIONSHIP → EVENT |
| 1704 | RELATIONSHIP | LOST | no semantic match (score < 0.2) |
| 1800 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |
| 1900 | EFFECT | PRESERVED | 1 match, same kind (EFFECT) |
| 1901 | BELIEF_SEED | LOST | no semantic match (score < 0.2) |
| 1902 | EFFECT | LOST | no semantic match (score < 0.2) |
| 1903 | BELIEF_SEED | LOST | no semantic match (score < 0.2) |
| 2000 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2001 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2002 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2003 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2004 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → RELATIONSHIP |
| 2005 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2006 | TRAIT_SEED | PRESERVED | 1 match, same kind (TRAIT_SEED) |
| 2007 | BELIEF_SEED | RECLASSIFIED | 1 match, kind changed: BELIEF_SEED → TRAIT_SEED |
| 2100 | TRAIT_SEED | RECLASSIFIED | 1 match, kind changed: TRAIT_SEED → PORTRET |
| 2101 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → PORTRET |
| 2102 | EFFECT | RECLASSIFIED | 1 match, kind changed: EFFECT → RELATIONSHIP |
| 2103 | TRAIT_SEED | LOST | no semantic match (score < 0.2) |