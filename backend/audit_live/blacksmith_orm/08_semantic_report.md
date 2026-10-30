# Semantic audit: blacksmith_orm

## Draft summary

- Entries: 48
- by_kind: {'EVENT': 8, 'TRAIT_SEED': 5, 'RELATIONSHIP': 10, 'BELIEF_SEED': 4, 'EFFECT': 2, 'PORTRET': 16, 'DESIRE_SEED': 2, 'LOCATION': 1}
- by_provenance: {'LLM_DRAFT': 48}
- object_id: null=37 set=11
- open_questions: 7
- author_text in draft: EMPTY

## Per-point semantic verdict

| # | chars | items | verdict | severity | issues |
|---|-------|-------|---------|----------|--------|
| HDR | 16 | 0 | NOT_DECOMPOSED | HIGH | NOT_DECOMPOSED: Декомпозиция не удалась после retry: items[0]: kind 'human_hint' вне реестра ['B |
| #1 | 53 | 2 | ISSUES | MID | EVENT без day, но в тексте есть возраст — нужно историзировать |
| #2 | 57 | 1 | OK | LOW | — |
| #3 | 88 | 0 | HTTP_FAIL | HIGH | HTTP 500: Internal Server Error |
| #4 | 414 | 0 | HTTP_FAIL | HIGH | HTTP 500: Internal Server Error |
| #5 | 340 | 3 | ISSUES | MID | BELIEF_SEED выглядит бытовым: 'все считают его самого такой же мебелью....'; RELATIONSHIP target_hint='мастер гильдии' — нужен resolve (placeholder NEW_NPC); EVENT без day, но в тексте есть возраст — нужно историзировать |
| #6 | 82 | 1 | ISSUES | MID | EVENT без day, но в тексте есть возраст — нужно историзировать |
| #7 | 231 | 2 | ISSUES | MID | EVENT без day, но в тексте есть возраст — нужно историзировать; EFFECT kind=trauma без triggers — seeder skip'нет (imprint не создан) |
| #8 | 254 | 1 | OK | LOW | — |
| #9 | 355 | 4 | ISSUES | MID | BELIEF_SEED выглядит бытовым: 'он ищет ответ из-за люси, потому что она похожа на эльру — и...' |
| #10 | 196 | 3 | ISSUES | MID | RELATIONSHIP target_hint='Борко' — нужен resolve (placeholder NEW_NPC) |
| #11 | 161 | 1 | OK | LOW | — |
| #12 | 617 | 3 | ISSUES | MID | BELIEF_SEED выглядит бытовым: 'информация, отданная бесплатно, не покупает благодарность, а...'; EVENT без day, но в тексте есть возраст — нужно историзировать |
| #13 | 164 | 1 | OK | LOW | — |
| #14 | 296 | 1 | OK | LOW | — |
| #15 | 876 | 5 | ISSUES | MID | RELATIONSHIP target_hint='Гильдия воров' — нужен resolve (placeholder NEW_NPC); RELATIONSHIP target_hint='городское правительство' — нужен resolve (placeholder NEW_NPC); EVENT без day, но в тексте есть возраст — нужно историзировать |
| #16 | 734 | 6 | ISSUES | MID | BELIEF_SEED выглядит бытовым: 'гном привык хранить в себе многое....'; EVENT без day, но в тексте есть возраст — нужно историзировать |
| #17 | 676 | 4 | ISSUES | MID | PORTRET × 3 — дробление внутреннего монолога (промпт требует один); RELATIONSHIP target_hint='Борко' — нужен resolve (placeholder NEW_NPC) |
| #18 | 499 | 2 | OK | LOW | — |
| #19 | 314 | 2 | OK | LOW | — |
| #20 | 332 | 2 | ISSUES | MID | RELATIONSHIP target_hint='Борко' — нужен resolve (placeholder NEW_NPC) |
| #21 | 373 | 4 | ISSUES | MID | EVENT без day, но в тексте есть возраст — нужно историзировать |

## Detailed issues

### HDR (items=0)
**Text**: кузнец Орм: гном...
**Items kinds**: []
- ⚠️ NOT_DECOMPOSED: Декомпозиция не удалась после retry: items[0]: kind 'human_hint' вне реестра ['B

### #1 (items=2)
**Text**: 1. 146 лет, из которых он кузнец в городе уже 57 лет....
**Items kinds**: ['EVENT', 'TRAIT_SEED']
- ⚠️ EVENT без day, но в тексте есть возраст — нужно историзировать

### #3 (items=0)
**Text**: 3. Хороший его друг Торнин, который напоминает ему старого друга, умершего 70 лет назад....
**Items kinds**: []
- ⚠️ HTTP 500: Internal Server Error

### #4 (items=0)
**Text**: 4. Когда Торнин заказал у него меч, он сразу же предупредил главу гильдии воров и городское правительство. Гильдии сказал: готовьтесь остановить и убить Торнина. Правительству — точнее, писарю квартал...
**Items kinds**: []
- ⚠️ HTTP 500: Internal Server Error

### #5 (items=3)
**Text**: 5. Писарь этот второй десяток лет сидит на содержании гильдии. К утру следующего дня мастер гильдии знал о предупреждении слово в слово — и знал, от кого оно исходило. Орм об этом не знает. Это единст...
**Items kinds**: ['RELATIONSHIP', 'BELIEF_SEED', 'EVENT']
- ⚠️ BELIEF_SEED выглядит бытовым: 'все считают его самого такой же мебелью....'
- ⚠️ RELATIONSHIP target_hint='мастер гильдии' — нужен resolve (placeholder NEW_NPC)
- ⚠️ EVENT без day, но в тексте есть возраст — нужно историзировать

### #6 (items=1)
**Text**: 6. Учился кузнечному делу у мастера Грунта Алмазной наковальни 100 лет тому назад....
**Items kinds**: ['EVENT']
- ⚠️ EVENT без day, но в тексте есть возраст — нужно историзировать

### #7 (items=2)
**Text**: 7. Последняя жена Эльра умерла от бреда и лихорадки уже 20 лет назад. Она долго болела, психика её слабела, галлюцинации и психоз жены на протяжении многих лет изводили характер гнома — многое с тех в...
**Items kinds**: ['EVENT', 'EFFECT']
- ⚠️ EVENT без day, но в тексте есть возраст — нужно историзировать
- ⚠️ EFFECT kind=trauma без triggers — seeder skip'нет (imprint не создан)

### #9 (items=4)
**Text**: 9. Непонятно, что тем вечером заставило его напасть на девочку и изнасиловать — то ли желание, то ли месть жене за тяжёлые последние годы с ней; даже он сам не понимает. Если он и ищет ответ, то тольк...
**Items kinds**: ['PORTRET', 'RELATIONSHIP', 'BELIEF_SEED', 'TRAIT_SEED']
- ⚠️ BELIEF_SEED выглядит бытовым: 'он ищет ответ из-за люси, потому что она похожа на эльру — и...'

### #10 (items=3)
**Text**: 10. Когда ему начал угрожать Борко и заставил продолжать спать с Люсей, гном не был напуган шантажом — скорее это была дополнительная легальная причина повторять то, что приносит ему удовольствие....
**Items kinds**: ['RELATIONSHIP', 'PORTRET', 'TRAIT_SEED']
- ⚠️ RELATIONSHIP target_hint='Борко' — нужен resolve (placeholder NEW_NPC)

### #12 (items=3)
**Text**: 12. Когда ещё и Горан на следующий день после Торнина попросил о мече, гном понял: заказ Торнина можно продать купцу. Продать не сталь, а факт — кому, когда и зачем куется меч. Одна и та же информация...
**Items kinds**: ['PORTRET', 'EVENT', 'BELIEF_SEED']
- ⚠️ BELIEF_SEED выглядит бытовым: 'информация, отданная бесплатно, не покупает благодарность, а...'
- ⚠️ EVENT без day, но в тексте есть возраст — нужно историзировать

### #15 (items=5)
**Text**: 15. Баланс Орма между Гильдией воров и городским правительством — это не двойная игра и не хитрый расчёт. Это стратегия выживания гнома, который живёт в этом городе 57 лет и пережил трёх старейшин Гил...
**Items kinds**: ['PORTRET', 'TRAIT_SEED', 'RELATIONSHIP', 'RELATIONSHIP', 'EVENT']
- ⚠️ RELATIONSHIP target_hint='Гильдия воров' — нужен resolve (placeholder NEW_NPC)
- ⚠️ RELATIONSHIP target_hint='городское правительство' — нужен resolve (placeholder NEW_NPC)
- ⚠️ EVENT без day, но в тексте есть возраст — нужно историзировать

### #16 (items=6)
**Text**: 16. Когда Торнин заказал меч, Орм не стал строить из себя верного друга. Торнин напоминает ему старого друга, который умер 70 лет назад, — но напоминает, не является. А гном, который прожил 146 лет, з...
**Items kinds**: ['PORTRET', 'EVENT', 'RELATIONSHIP', 'EFFECT', 'BELIEF_SEED', 'DESIRE_SEED']
- ⚠️ BELIEF_SEED выглядит бытовым: 'гном привык хранить в себе многое....'
- ⚠️ EVENT без day, но в тексте есть возраст — нужно историзировать

### #17 (items=4)
**Text**: 17. Борко не имеет власти над Ормом. Орм не испугался шантажа стражника. Орм просто понял, что Борко даёт ему разрешение. Не приказ. Разрешение. А гному, который 20 лет назад потерял жену в бреду и ли...
**Items kinds**: ['PORTRET', 'RELATIONSHIP', 'PORTRET', 'PORTRET']
- ⚠️ PORTRET × 3 — дробление внутреннего монолога (промпт требует один)
- ⚠️ RELATIONSHIP target_hint='Борко' — нужен resolve (placeholder NEW_NPC)

### #20 (items=2)
**Text**: 20. Наблюдатель. Сидит спиной к стене, лицом к залу: за 57 лет это рефлекс, а не осторожность — просто так устроено его место у стойки. Он видит весь зал, включая коридор на кухню. Он замечает, что Бо...
**Items kinds**: ['PORTRET', 'RELATIONSHIP']
- ⚠️ RELATIONSHIP target_hint='Борко' — нужен resolve (placeholder NEW_NPC)

### #21 (items=4)
**Text**: 21. Руки и речь. Обожжённые руки в старых ожогах — рукопожатие, которого избегают. Говорит односложно: «Да». «Нет». «Жди». Матерится только по-гномьи — зал не понимает ни слова, и его это устраивает. ...
**Items kinds**: ['PORTRET', 'LOCATION', 'EVENT', 'RELATIONSHIP']
- ⚠️ EVENT без day, но в тексте есть возраст — нужно историзировать
