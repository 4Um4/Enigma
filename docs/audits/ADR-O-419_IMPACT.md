# ADR-O-419 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`
## Changed Domains
- RELATIONSHIP: time-driven динамика потребностей (gen_rate/фон Фр1/распад Фр2) + derived-readout Satisfaction (Ф1/С5)
- STATE-MUTATION: NeedSlot.gen_rate (валидация ≥0); дельты через единственный write-path (delta_buffer → сплит Ф9/Ф10 → apply_relationship_deltas)
- TEMPORAL: личный цикл = сон/WAKE (мех.3); время — независимый контур (мех.1); квант 3600 с — дискретизация вычисления
## Downstream Consumers
- DecisionHub / Affective Pipeline — будущие потребители Фр4 (мост сознательно не строится — вердикт Мастера)
- Calibration Lab (O-361/367): gen_rate=0.1, RE_DYNAMICS_BG_FRUSTRATION_RATE=0.02, RE_DYNAMICS_DECAY_FRACTION_PER_DAY=0.1, порог=rigidity — CALIBRATION_CANDIDATE
- Calibration Arena (§11 ТЗ): кривые накопления фрустрации — материал п.9
## Runtime Impact
- RAM: +1 float на NeedSlot; книга кванта — 1 dict per scene (ленивый, только при ON)
- Tick: peek O(1) при elapsed<квант; дельты раз в 360 тиков/NPC/need
## Sandbox Tests
- backend/tests/test_re_gh_contracts.py (5) + test_re_gh_dynamics.py (16): Ф1/Ф3/Ф4/С5, noop-чистота, uuid5-детерминизм, клампы
- SUPERBOX re_gh_dynamics_test 2/2: Control (OFF: книга не создаётся) / Treatment (ON: mark=46800, p_sexual=0.0542)
## Rollback
- env RELATIONSHIP_DYNAMICS_ENABLED unset → полный no-op (Control байт-идентичность доказана)
- gen_rate остаётся неактивным полем с валидацией; манифест-запись DEBT не влияет на рантайм
## Уроки (для протокола)
- Манифест O-414 = транскрипция census: dict-ключ вне CONTAINER_DOMAINS не декларировать (M-STALE честный)
- Якорь БЫЛО = точная строка файла, не реконструкция по памяти (повтор S326-урока)
