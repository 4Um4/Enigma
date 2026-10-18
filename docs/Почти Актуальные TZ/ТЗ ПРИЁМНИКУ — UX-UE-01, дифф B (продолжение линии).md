# ТЗ ПРИЁМНИКУ — UX-UE-01, дифф B (продолжение линии)

Контур: ENIGMA, ветка `V.0.5.4.3.8_Замыкание_1`. Закрываемая сессия: **S358** (номер = max(диска)+1 НЕПОСРЕДСТВЕННО перед записью — Anti-Race §11.1.1; S355 занят EPI-0, S357 занят параллельной B′ E-BM1 — их записи не трогать). Коммиты сессии: 8c5c3bbb (гейт L1 + стрип + тест + tooling, 495+/1−), 86405519 (ruff-косметика tooling, 6+/6−).

## §0. Что закрыто и сертифицировано (факты, не перепроверять)

- Readiness-гейт фиксации player-L1 `TraitDriftEvent` на commit-выходе `backend/app/services/game_loop/npc_orchestration.py` (единственный эмиттер `[L1_FIXATION]` в бэкенде): PARTIAL/FAILED = попытка ≠ событие; чтение `_ue_l1_readiness` getattr-цепью, дефолт `RESOLVED` (контексты без intent_resolution неизменны); warning `[UE-GATE-L1]` при подавлении; try-тело байт-в-байт.
- Стрип мёртвого хелпера `_player_directive_l1_events` (42 строки, остаток недовставленного v1; `git grep` пуст, в т.ч. по неотслеживаемым тестам).
- Сертификация: GREEN-тест 7 инвариантов (`tests/sandbox/micro/test_ue_d4_l1_sibling_red.py`); UE-сьюта 12 файлов — 56 passed / 7 xfailed / 0 failed; боевые замки — 24 passed / 1 skipped; IPT — 53 passed / 0 failed (0 CRITICAL); живая приемка run_terminal_mvp: PARTIAL THREATEN подавлён / FAILED UNCERTAIN не диспетчеризован / контроль RESOLVED ATTACK — `[L1_FIXATION]` сохранён. Дифф носителя +13/−1, точечный (хук [OK]).

## §1. Первый пункт приёмника — долг закрытия S358: ADR-запись

- Атлас: max ID = ADR-O-427 → запись **ADR-O-428 [FIX]** (сиблинг ADR-O-424 «UE-Kernel Readiness Gate — D4» — дифф A этой же линии; прецедент-исключение ADR-409 [FIX] без O- существует — при сомнении решает структура атласа после ПОЛНОГО чтения, §3). Перепроверить max перед записью (параллельные сессии).
- adr_cli impact (выполнен, граф 457/352): npc_orchestration.py затрагивает ADR-O-402 [STRUCT] Turn Pipeline Ownership — табу O-402 чисты (фазовые контракты/NpcOrchDeps не тронуты; коммиты при зелёных гейтах; seam/extraction не смешивались).
- Черновик записи (адаптировать по атласу):
  - Суть: sibling-утечка диффа A — player-директивы MOVE/THREATEN/PERSUADE/GIVE фиксировались в L1-хронику при intent_readiness=PARTIAL/FAILED (живой лог тик 41: `[L1_FIXATION] THREATEN` при PARTIAL). Лечение: readiness-гейт на единственном выходе фиксации (commit-блок npc_orchestration); контракт ADR-O-424 расширен на L1-границу; дефолт RESOLVED сохраняет поведение контекстов без intent_resolution. Стрип мёртвого хелпера (остаток недовставленной v1-реконструкции, вызовов 0).
  - ❌ Taboo: фиксация L1-директив при readiness ≠ RESOLVED; тихое подавление (warning обязателен); второй писатель readiness; изменения try-тела commit; фильтр по sem_action вместо readiness (гейт фильтрует готовность, не тип действия).
  - Status: ACTIVE (7 инвариантов GREEN; UE 56/7xf; IPT 53/0; живая приемка).
  - Files (full: ADR-O-428_IMPACT.md): `backend/app/services/game_loop/npc_orchestration.py`, `backend/tests/sandbox/micro/test_ue_d4_l1_sibling_red.py`.
- IMPACT-файл `docs/audits/ADR-O-428_IMPACT.md` по §3.10: downstream — l1_chronicle + потребители L1; ресурсы — один getattr-гейт на тик, warning только при подавлении; rollback — revert 8c5c3bbb либо точечное снятие гейта (вернуть `if _l1_events:`); sandbox — 7 инвариантов + батарея §5.
- Хук-WARNING «ADR IMPACT AUDIT REQUIRED» по npc_orchestration.py снимается записью (прецедент S356 / IMPACT §10).

## §2. Реестр наблюдений → roadmap (находки; прецедент S353 → §7.12)

- RE-D2 RuntimeError (DIALOGUE_UPDATE, event-loop): ДВА воспроизведения (stm_len=0 / stm_len=355), пре-существующий — есть в пре-стрипном прогоне, НЕ след гейта/стрипа; потоковый гарвард отрабатывает (дедлок предотвращён).
- INV-DM-HALLUCINATION: DM нарративит физический контакт при отклонённом ImpactEngine-ударе (7.4 м > 0.8 м досягаемости; combat_data out-of-range получен и проигнорирован).
- beliefs-утечка: `+ [tavern_keeper_tornin] attacked(player→…) conf=0.5` при PARTIAL — материал диффа B (§3-B1).
- DM-дубль текста в блоке NPC-реакций — материал §3-B3.
- WV-квирк: «у тебя нет 'нос'» — парсинг части тела как цели.
- [SCENE] location_templates.json не найден (мелочь; проверить, известен ли).

## §3. Дифф B — основная работа

Доктрина та же: «попытка ≠ событие» на ВСЕХ каналах проекции интента игрока.

- **B1 beliefs-канал**: при PARTIAL/FAILED — ноль записей attacked/директивных предикатов о действии игрока (сигнатура живого лога: `attacked(player->X) conf=0.5`). Атрибуция `build_intent_projection` + DTO `comprehension_status` — из компактированной сессии, диском НЕ верифицирована → сначала археология, носитель найти по факту.
- **B2 sibling-ветка интервенций** `tick_orchestrator.py:1690` (верифицировано дампом A/B/C): ветка `("MOVE","THREATEN","PERSUADE","GIVE")` — тот же readiness-гейт.
- **B3 DM-дубль в NPC-реакциях**: канал рендера; FE-зона (game_screen/api_client) — D61/COV-2 скоуп, с Мастером до правок.
- Метод (обязателен, оплачен этой сессией): (1) археология ДО диффа — только буквальный код реального носителя; (2) RED-first: XFAIL(strict)-контракты → патч → XPASS = GREEN; (3) стадийно-агностичные якоря в GREEN-тесте; (4) сертификация полной батареей (§5); (5) коммиты pathspec, БЕЗ amend (§11.1.1 — инцидент S318).
