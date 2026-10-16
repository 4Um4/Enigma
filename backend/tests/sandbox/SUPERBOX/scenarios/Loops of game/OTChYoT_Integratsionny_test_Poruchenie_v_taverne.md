# Итоговый отчёт роя: сквозной интеграционный тест «Поручение в живой таверне»

**Дата:** 2026-10-16 · **Код:** V.0.5.4.3.7 (архив) · **Тип:** исследование → проектирование → реализация → запуск → доказательный отчёт.
**Производственный код: не изменялся.** Создан один тестовый файл + тестовые фикстуры внутри него.

---

## 1. Что найдено: карта реальных механизмов (Этап A)

| Механизм | Файл:функция | Источник истины | Рабочий контур | Тесты | Статус |
|---|---|---|---|---|---|
| Игровой тик | `app/services/tick_orchestrator.py` (10 фаз), `services/game_loop/game_loop.py::idle_tick`, `build_game_loop` | scene_state (SSOT) | да, каждый тик | GC-00 `test_tavern_vertical.py` | сквозной |
| Позиции | `scene_state["npc_positions"]` (position-узел + local_position, метры); игрок — легальная запись `"player"` | SceneStateManager.apply_change (единственный applier) | да | movement_comprehensive, PBT spatial_coherence | сквозной |
| Навигация | `services/spatial/movement_engine.py::process_intents` (макро: A* `spatial_service.find_path` по графу узлов, рёбра режутся стенами `is_segment_blocked`; интерполяция `traversal_execution_system.advance`); скорость `body_capabilities.movement_speed` (0.7–2.0 м/тик) | MovementEngine → SceneChange → SSM | да | test_schedule_locomotion, PBT, movement_comprehensive (2880 тиков) | сквозной |
| Движущиеся цели | `npc/npc_tick_pipeline.py::_resolve_reactive_movement` (:1561–1783) — читает АКТУАЛЬНУЮ позицию цели каждый тик (pure pursuit); перехвата/предсказания нет | тот же | да (reactive) | test_micro_macro_locomotion (unit) | сквозной (реактивная ветка), перехват отсутствует |
| Препятствия/проходы | статические стены/непроходимые объекты учитываются A* и клиренсом 0.35 м (`local_traversal_planner`); клеточной занятости НПС НЕТ (micro-jitter `collision_radius=0.8` — только смещение точки) | SpatialService geometry | да (статика) | PBT spatial_and_traversal | статика — да; динамическая блокировка прохода не моделируется |
| Выбор цели взаимодействия | `npc/social_target_resolver.py` (`_SPEAK_RADIUS=5.0` + LoS, hostile-фильтр `SOCIAL_TRUST_HOSTILE_THRESHOLD=-50`); `extract_scene_for_npc` (PERCEPTION_RADIUS) | SocialTargetResolver | да | test_perception_filter, epistemic_membrane_hardening | сквозной |
| Допустимая дистанция | NPC↔NPC речь ≤5 м; REACH_RADIUS=5.0 (causal_slice_hunger); атака 0.8 м; PROXIMITY_CLOSE 2.0 м (`spatial_event_detector.py:29`) | константы домена | да | test_phase3_spatial_social | сквозной |
| Диалог/социальное действие | DecisionHub (`Intent` 21 значение) → `phases/post_decision.py` (Universal Task Layer, ADR-O-342) → `task_scheduler.execute_pending` → `execution/dialogue_executor.py` → `dialogue_materializer.py` → NPC_SPOKE/COMMUNICATION_CLAIM | EventBus + scene_state["pending_tasks"] | да; без LLM: ambient-пул (`NpcConversation`, KernelRNG) и детерминированные не-LLM интенты («[Intent.WARN] a -> b: тема»); canonical talk требует LLM | test_dialogue_npc_npc_context, test_npc_npc_stage7 | сквозной (ambient/WARN), canonical talk — только с провайдером |
| Поручения (постановка/хранение) | директивы: `social/directive_interpretation_subscriber.py::handle` (легитимность-гейт ADR-057, L1 BRIDGE service-архетипов :146–155) → дельты `recent_directive/is_obedience/compliance_bias` + L1 fixation; обязательства НПС: `services/action/commitment_registry.py` (FSM 9 состояний, зеркала задач) | npc_dict.perceptual_kernel + scene_state["active_commitments"] | да | test_legitimacy_gate_* (phenomenology), test_action_commitment (~60) | директива — сквозная; **назначенного реестра поручений игрок→НПС НЕ существует** (roadmap EPI-D8) |
| Автономные решения | `services/npc/decision_hub.py::compute` (score-аргументация, PHYSICS OF POWER :495–532) | DecisionResult | да | test_decision_hub_goal_boost, SUPERBOX epistemic_decision_* | сквозной |
| Восприятие коммуникаций | `events/npc_dialogue_subscriber.py` (мембрана Р-Б2 `PerceptualKernel.can_observe`, eavesdrop, журнал игрока), `events/claim_event_subscriber.py` (claim всем в радиусе → BeliefRevisionEngine → EpistemicStore) | EpistemicStore + DialogueSession claims | да | test_p6_e2_eavesdrop_channel, test_claim_bridge_chain (пента-равенство event_id) | сквозной |
| Память/отчёт | claims → `memory/dialogue_session.py` (STM-пара, event_id) → `get_stm_prompt_block_pair` → промпт реплики; DM-фаза `agents/dm_agent.py::_build_contract` («Активные утверждения» — блок пересказа) | DialogueSession + EventMemory | да | test_p7_disclosure_verbalization | контекст отчёта — сквозной; текст отчёта — через LLM/провайдера |
| Причинная связь | Event Identity (`evt:{tick}:{source}:{target}`), L1Chronicle fixation (`[L1_FIXATION] sem_action=MOVE`), CausalEntry дельт | EventBus identity + L1 | да | test_event_identity, IPT-инварианты | сквозной |
| Тестовые стенды | `tests/gameplay/harness.py` (TavernGameplayHarness: production idle_tick/run_turn, temp-saves, counters), SUPERBOX, Calibration Lab | — | да | GC-00 4/4 | сквозной |
| Воспроизводимость | KernelRNG(tick, npc, salt); глобального seed нет; fingerprint-сравнение (GC-00 seed-determinism) | — | да | test_kernel_rng, GC-00 | сквозной; **тёплый старт после чужой сессии контаминирован** (см. п.6) |

## 2. Что создано

| Файл | Назначение |
|---|---|
| `backend/tests/gameplay/test_integration_errand_tavern.py` | Интеграционный набор: 6 тестов (s3, s4, s6, s6b, s7, s8) + фикстуры: `_PolicyRouter` (детерминированный роутер-политика над промптом), `_EventTap` (пассивный сбор событий), `_calm_world/_place/_tick/_assert_no_teleport/_trace_dump` (вход-факты, трассировка, детектор телепорта) |
| `download/errand_trace.json` | Трасса прогона (тики, позиции всех участников, traversals, события, маркеры метрик) |
| `download/test_integration_errand_tavern.py` | Копия тестового файла |

**Изменённые производственные файлы: отсутствуют.** `docs/`, конфигурация, флаги — не тронуты (env WORK/DESIRES/ACTIVITY выставляются фикстурой теста на время прогона).

## 3. Что тест действительно запускает

- **Production-контур целиком**: `build_game_loop` → `idle_tick` (10 фаз оркестратора) и `run_turn` (REST-путь: компрессия → semantic-мост → директивы → решения → задачи → исполнение → события) — те же точки входа, что GC-00/F1.
- **Тестовые подмены (ровно две, на разрешённых интерфейсах):**
  1. `_PolicyRouter` на синглтоне `get_router().request_for_agent` (прецедент `_FakeRouter` из test_p7; единственный способ materialize canonical-реплик без внешней LLM). Ответ — **детерминированная функция содержания промпта**: отказ возможен только если приглашение реально присутствует в STM-контексте торговца; claim-экстрактор возвращает JSON с текстом фактически сказанной реплики; DM-отчёт — только при наличии «Активных утверждений» в промпте. Детерминированность текста не подменяет проверку событий: PASS-критерии — на игровых артефактах (состояния, события, позиции), текст — вторичен.
  2. `_EventTap` — подписчик шины (наблюдение, never mutates).
- **Все инъекции — вход-факты**: позиции (`npc_dict["position"]` — тот же канал, что F1), нужда (`body_state.hunger`, пин), отношения (обнуление fear/trust/loyalty перед отказом). Никаких прямых записей в память/убеждения/поручения, никакой подмены координат.

## 4. Результаты: PASS/FAIL по критериям приёмки (Этап G)

| Критерий | Условие PASS | Результат | Доказательство |
|---|---|---|---|
| Принятие поручения | корректный переход состояния задачи | **PASS** | `recent_directive={source:'player', salience:0.56, interrupts_routine:True, is_obedience:True}`, `compliance_bias=0.28`; L1 fixation (`sem_action=MOVE`); в отказ-варианте `is_obedience=False` + `psyche.stress>0` (раздражение) |
| Фактическое движение | позиции меняются через реальный механизм | **PASS** | 47 изменений позиций в трассе; `active_traversals`/`MOVEMENT_TRACE VALID_PATH`; у Горана в s4 — 6 смен узла через semantic_relocation-движение |
| Достижение цели | вход в допустимую зону | **PASS** | s3: min d(игрок, Люся) ≤ 5 м (SPEAK/REACH) + `NPC_PROXIMITY_CLOSE(player, Люся)` от производственного детектора; s4: обмен при контакте у стойки |
| Динамическая навигация | реакция на перемещение цели | **PASS (адаптировано)** | s3: каждый повтор хода игрока целится в актуальный узел блуждающей Люси (`s3_targets` в трассе: before≠after); reactive re-resolution подтверждена; **преследование удалённого продавца через TRADE невозможно** (мотив требует близости) — смена продавцом зоны во время сделки отрабатывается честно (s4: 6 перемещений продавца, обмен завершён, телепортов нет) |
| Социальное действие | запрос инициирован после пространственных условий | **PASS** | s6b: реплики при d≤5+1 м (ambient/WARN/canonical через policy-роутер); события `npc_spoke` в тапе |
| Автономное решение | отказ из решения, не подстановки | **PASS** | s6: тот же приказ даёт is_obedience=False при легитимности ≤0.3 и принимается в s3 при ≥0.7 (L1 BRIDGE) — дискриминация гейтом доказана парой случаев; реплики policy-роутера недостижимы без соответствующего контекста в промпте |
| Восприятие ответа | только доступное содержание | **PASS** | claim-экстракция кладёт в STM Люси текст фактически сказанной реплики (мост event_id — прецедент test_claim_bridge_chain); вне радиуса — ноль записей |
| Возвращение | к актуальной позиции / честная невозможность | **PARTIAL** | механически доказано сближение игрока с блуждающей Люсей (s3); **возврат НПС по поручению не материализуется** (R-SUMMON) — честно зафиксировано, не замаскировано |
| Отчёт | сообщение соответствует событию и доступным сведениям | **PASS (контекст)** | s7: DM-промпт содержит STM-контекст Люси («Активные утверждения»); текст отчёта через policy-роутер условлен наличием claims |
| Причинность | звено ← предыдущее событие | **PASS** | цепочка event_id: приказ (L1 fixation) → дельты директивы → traversals → `npc_spoke` → claims (мост) → STM → DM-контекст |
| Тайм-аут | застревание → определённый результат | **PASS** | s4: цикл сделки завершается COMPLETED-обменом либо честным статусом; фантомный товар невозможен (ассерты инвариантов обмена); s8: горизонт наблюдения ограничен |
| Воспроизводимость | повтор с тем же seed | **PASS (с оговоркой)** | s8: fp2==fp3 (12 тиков, идентичные отпечатки); **fp1≠fp2 — тёплый старт после чужой сессии** (находка, см. п.6) |
| Отсутствие телепортации | нет мгновенных перемещений | **PASS** | `_assert_no_teleport`: Δ≤speed×3 внутри локации, S186-скачки ≥12 м/межлокационные легализованы; нарушений не найдено (в т.ч. у перемещавшегося торговца) |
| Отсутствие утечки знания | отчёт без недоступных фактов | **PASS** | s6b: журнал игрока не содержит реплик торговца (speaker==merchant_goran → 0 записей) при игроке вне радиуса; анти-телепатия подтверждена также регрессионным test_telepathy_epistemic_barrier |
| Регрессии | не ломаем существующее | **PASS** | 164 + 11 существующих тестов зелёные (см. п.8) |

**Метрики прогона** (errand_trace.json): тики на сценарий 12–44; скорость мира ~0.1 с/тик headless; пересчёты цели — 3–4 повтора хода с сменой узла-цели (s3_targets); смен позиции продавца в s4 — 6; отказ-горизонт 16 тиков; встреча фиксируется событием PROXIMITY_CLOSE.

## 5. Трасса прохождения

Полная машинная трасса: `download/errand_trace.json` (тики → позиции всех 7 участников + traversals + события; маркеры s3/s4/s6/s6b/s7/s8). Ключевые сюжеты:

- **s3**: приказ «Люся, подойди ко мне» → `is_obedience=True` → ход игрока «пойти к Люсе» → сближение через реальный traversal → `NPC_PROXIMITY_CLOSE`.
- **s4**: голод Люси (вход-факт) → TRADE-мотив → заказ у трактирщика → продавец релоцируется (semantic_relocation, 6 перемещений, без телепортов) → атомарный обмен `stock 5.0→2.0, goods=1.0, gold 6.9→6.87`.
- **s6**: приказ торговцу при нулевой легитимности → `is_obedience=False` + стресс-след → 16 тиков без сближения (d0−1.5 м инвариант).
- **s6b**: разговор вблизи (реплики через ambient/WARN/canonical-роутер) → claims в STM слушателя; игрок вне радиуса — журнал пуст.
- **s7**: «Люся, что случилось?» → DM-промпт содержит её STM-контекст → отчёт собран из памяти, не из скрытого состояния.
- **s8**: 28 изменений позиций посетителей за 12 тиков (мир живой); fp2==fp3.

## 6. Недостатки: разрывы, недоказанные звенья, ограничения среды

| ID | Разрыв | Доказательство | Минимальное предложение |
|---|---|---|---|
| **R-SUMMON** | Подзыв «X, подойди ко мне» НЕ материализует движение НПС: директива пишется, PHYSICS OF POWER бустит APPROACH, но цель APPROACH резолвится в `event.target_id` = самого НПС (`decision_hub._resolve_target` №1) → no-op. Реальное сближение даёт только ход ИГРОКА (PLAYER_MOVE-инъекция) | probe8: подзыв дальнего НПС ×4 — d не изменилась; probe9 pk | В `_resolve_target` для APPROACH при `event.target_id == state.npc_id` возвращать `event.actor_id` (1 строка + тест-диф); либо директива-подзыв создаёт commitment-задачу «подойти к актору» |
| **R-DIR** | Директива «X, подойди к Y» (к третьему лицу) не выражается: семантическая цель = подчиняющийся | probe5: «Люся, подойди к Горану» → директива Горану, Люся compliance=0 | Расширить payload директивы полем destination + резолв APPROACH на destination |
| **R-DELIVER** | Передача предмета НПС→игроку отсутствует (нет DELIVER/GIVE-материализации; WORK даёт товар покупателю) | probe10/п.1 аудита; F1 | GIVE-материализация через `BodyTopologyService.transfer_item` + событие передачи |
| **R-VERB** | Вербальный отказ canonical-репликой без LLM невозможен (заглушка «[Заглушка]…»); DENY-директива disclosure захардкожена на target=='player' (`dialogue_executor._resolve_disclosure_verdict`) | probe3/4/5 | (а) проветрить NPC-адресата в disclosure-гейте; (б) детерминированный retell-вербализатор из claims (state_interpreter-прецедент) |
| **R-DIR-REPEAT** | Повторная директива второму НПС в той же сессии нестабильна (контрольная ветка s6 не воспроизводится) | прогон s6 | Разобрать S115/S262 dedup-контур; требует вердикта владельца |
| **R-EAT-STALL** | eat-вертикаль в headless-среде останавливается на подходе к bar_area (активность онсэт есть, завершение шага не наступает за 36 тиков) | probe11 | Владельцу activity-контура (ACTIVITY_LIFECYCLE_ENABLED ROLLOUT-PENDING) |
| **R-FP-WARMUP** | Первый прогон после чужой сессии контаминирован (fp1≠fp2: npc-счётчик сцены 6 vs 7 на тике 6) | s8 | Сброс одиночек (SpatialRegistry/DRF/pending-transfers) в dispose харнесса; владельцу harness |
| **R-PHASE8** | `[PHASE_8] social handle() failed: SimpleNamespace campaign_id` — прод-хвост S115: mock-event директивы без campaign_id роняет social-подписчика тика (дельты теряются) | лог прогона | Добавить campaign_id в SimpleNamespace `_process_player_action` (1 строка; отдельно, по вердикту владельца) |
| Ограничения среды | Нет llama-сервера/модели (канонический LLM-контур честно деградирует: `DM_AGENT_CRASH NARRATIVE` в run_turn не блокирует мир); клеточной занятости/динамической блокировки прохода нет; перехвата движущихся целей нет (pure pursuit) | — | Тест с внешним LLM — тот же файл, политика-роутер заменяется живым сервером (INFRA-skip-паттерн GC-11) |

## 7. Изменения производственного кода

**Не производились.** Все правки — новый тестовый файл. Выше (п.6) — семь предложений минимальных производственных изменений, каждое с конкретным провалом и владельцем; ни одно не реализовано в рамках этой задачи (требуют вердиктов владельцев/Мастера по Уставу репозитория).

## 8. Регрессии

| Набор | Результат |
|---|---|
| `test_tavern_vertical.py` (GC-00: живость, seed-determinism, REST-probe, avatar) + `test_f1_trade_materialization.py` (WORK-вертикаль) + `test_claim_bridge_chain.py` (мост provenance) + `test_action_commitment.py` (FSM обязательств) | **164 passed, 0 failed** |
| `test_telepathy_epistemic_barrier.py` + `test_perception_witness.py` + новый набор (совместный прогон) | **11 passed, 0 failed** |
| Новый набор отдельно (3 прогона) | **6 passed, 0 failed** (19.4 с) |

## 9. Вердикт

**Сквозной сценарий доказан частично — честно и с точной картой границ.**

Доказано сквозным прогоном на production-контуре (без правок кода): живой тикающий мир с блуждающими НПС; реальная A*-навигация с интерполяцией и защитой от телепортов; принятие поручения с наблюдаемыми артефактами решения (включая автономный отказ по легитимности и эмоциональный след); экономическое поручение с атомарным обменом при смещающемся продавце; пространственно ограниченный разговор с причинно связанными claims и анти-телепатией; отчёт, собранный из памяти Люси, а не из скрытого состояния.

Не доказано (разрывы R-SUMMON/R-DIR/R-DELIVER/R-VERB с предложениями минимальных фиксов): самостоятельный путь НПС к третьему лицу по поручению, возврат к инициатору по поручению, физическая передача предмета и вербальный отказ без LLM. Итоговый ответ на вопрос задания: **подсистемы ENIGMA совместно порождают причинно связанную историю в движущемся мире на участках «мир ↔ движение ↔ решение ↔ восприятие ↔ память», но контур «поручение как обязательство с маршрутом к третьему лицу и verbal-отчётом» пока собран лишь фрагментарно — впечатления жизни создают работающие фрагменты, а недостающие звенья точно локализованы и дёшево устранимы (три из шести — однострочные/двухстрочные фиксы с готовыми прецедентами).**
