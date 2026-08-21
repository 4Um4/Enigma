# ADR-O-325 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-325` [STANDARD] **IMPACT**
# ADR-O-325 Impact Audit: Authoring Data Isolation
> Этот файл — детальный аудит онтологического сдвига.

## Changed Domains
- PERCEPTION & PHENOMENOLOGY

## Ontological Shift
Файл `signal_causes.yaml` вынесен в директорию `authoring/`.
Все статические `prior` (вероятности) удалены. 
Теперь это База Знаний для когнитивного слоя (Inference).

## Constraints
Runtime-физика (Manifestation, Perception) не имеет права читать `signal_causes.yaml`.
Иначе авторинг случайно станет "истиной мира".
Priors должны вычисляться отдельной динамической моделью во время Inference, исходя из контекста сцены (например, после драки prior страха падает, на морозе — prior холода растёт).
