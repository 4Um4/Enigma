# ADR-O-420 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

ADR-O-420 [STANDARD] **IMPACT** (S331; Ступень 0 CCH-0 — doc-only, код не затронут)

## Changed Domains
- authoring — НОВЫЙ домен контракта (Character Chronicle, Слой 0 канонического порядка)
- контрактно затронуты (реализация CCH-1…6): identity/authoring, memory (EventMemory seed), social (RelationshipStore seed), epistemics (TruthState/EpistemicRecord seed), frontend (новое приложение редактора)
- тик-пайплайн, каузальное ядро, EventBus — изменений НЕТ (хроника работает до первого тика и вне тика)

## Downstream Consumers
- CCH-1: chronicle_store, white_spot_registry (writer-guard), age_math + birth_epoch/age_at_game_start в NPCProfileL0 (снимает блокер аудита #9 / age_factor психо-фазы)
- CCH-2: biography_decomposer (capability FACT_EXTRACTION), routes_chronicle, chronicle_decompose_system.txt, ChronicleDecompositionNormalizer
- CCH-3: frontend/chronicle_editor (автономное приложение + MenuAction.CHRONICLE_EDITOR) + MODE_CHRONICLE в Map Editor
- CCH-4: chronicle_seeder (правило приоритета над legacy _convert_origin_events) + character_debugger_window (Workbench layer 4, реестровый хоткей, кандидат K_c — финал CCH-4)
- CCH-5: экспорт-проекции origin_events / village_relations / truth_state; гейт T-CCH-09 (NPC без хроники — дрифт 0)
- Writer-allowlist BeliefState/NPCIdentityL1 — расширение ТОЛЬКО отдельным ADR в CCH-4 (сеялка — единственный новый охраняемый писатель)

## Runtime Impact
- CCH-0: нулевой (doc-only). RAM / VRAM / Tick Latency — без изменений.
- Прогноз трека: LLM-вызовы декомпозитора — вне тика, через ModelRouter (общий семафор VRAM); seed — одноразово при new_game; replay-кэш промптов покрывает декомпозицию.

## Sandbox Tests (реестр приёмки — ТЗ CCH-01 §10 / roadmap §9.3d)
- T-CCH-01 round-trip Люси · T-CCH-02 эталонный разбор · T-CCH-03 белые пятна (4 опции) · T-CCH-04 канонизация-блок с fix_hint · T-CCH-05 детерминизм seed · T-CCH-06 эпистемическая изоляция (unknown → Марк = ноль записей) · T-CCH-07 вертикаль «звон кружки» → avoidance · T-CCH-08 дрейл-даун + изоляция layer 4 от HUD · T-CCH-09 legacy-дифф 0 · T-CCH-10 IPT + линтеры
- Запреты roadmap §13.4 (1–10) — каждый с тестом («запрет → тест», канон DTO Registry)

## Rollback
- CCH-0: git revert доков (этот файл, запись DOM-10 атласа, §14 DTO Registry, roadmap §0.2/§1.3, MUTATIONS). Кода нет — откат тривиален.
- Трек: удаление config/npc/chronicles/ + services/chronicle/ + routes_chronicle + frontend/chronicle_editor возвращает legacy-путь (он не удаляется — правило приоритета FR-11.2 / T-CCH-09).

## Вердикты ТЗ §12 (утверждены Мастером, S331)
1. Хоткей Character Debugger: окно Workbench layer 4, реестровый хоткей (кандидат K_c; финал — CCH-4).
2. day<0: единая конверсия age_math; авторитет — ось Calendar.total_seconds; точный отрицательный day — нормальная историческая координата; −1000 = legacy-sentinel «точная дата неизвестна»; drift 360/365 сверить с фактическим кодом в CCH-1 (не чинить по памяти).
3. PdfDropImporter: вне скоупа трека (паттерн импорта — да, код — нет); судьба модуля — отдельная долговая сессия.
4. Human-формулировки убеждений: только в хронике; типизированная проекция в ядро; BeliefFragment.label НЕ вводится.
5. unknown_person: лёгкая сущность хроники без NPC-конфига и L0-профиля.
6. LLM-авто-дополнение хроники: анти-цель ADR (вне скоупа).

## Реализация CCH-1 (S332)
- `backend/app/domain/chronicle.py` — 6 DTO (frozen) + EntityRef/CauseRef-инварианты + KP_*-ключи payload-схемы + make_entry_id (md5, replay-safe).
- `backend/app/services/chronicle/age_math.py` — единственная конверсия age⇄total_seconds⇄day<0; SENTINEL_DAY=−1000; дрейф 360/365 закрыт кодом (DAYS_PER_YEAR=365 = 360 регулярных + 5 межсезонья, constants.py).
- `chronicle_store.py` — WARA-пара, валидатор fail-loud (запреты 1/3/4 + «Save = Contract»), атомарная запись.
- `white_spot_registry.py` — writer-guard (запрет 2, D-атака → ArchitecturalViolationError); цензус писателей: registry (CCH-1), UI/API-канал — CCH-3.
- `origin_projection.py` — origin_events↔хроника (opaque deepcopy-payload; kind-семантика — CCH-2).
- `NPCProfileL0` + `birth_epoch/age_at_game_start` (None=Vacuum) + проводка `npc_loader`.
- Гейт T-CCH-01 GREEN: Люся 5/5 EventMemory эквивалентны через живой `_convert_origin_events`; 16 micro-тестов `tests/micro/test_chronicle_cch1.py`; ruff 0; IPT 51/51.
- Оговорка: блокер аудита #9 — age дан; полный разблок LinguisticIntegrityCalculator — Эпоха 8 (ещё нужны voice_archetype_id + identity_attachment-источник).

## Реализация CCH-2 (S335)
- `decomposition_normalizer.py` — fail-loud без silent-fallback (DecompositionError ×6 веток); мембрана vague-relation: закрытый реестр маркеров неточной связи (_VAGUE_RELATION_MARKERS) при model-confidence=1.0 → conf ≤0.4 + инъекция канонического вопроса (4 опции, П3). Расширение реестра — через корпус CCH-6, не руками.
- `chronicle_decompose_system.txt` — реестр kind с payload-схемами; EVENT/EFFECT-граница с антипримером («смерть родителей» = EVENT); обязательные вопросы (неточная связь/пол-возраст/неясное событие) с conf ≤0.5.
- `biography_decomposer.py` — Fast-препарсинг якорей ([N лет]/в N/с N) + router.request(FACT_EXTRACTION, temp=0, response_format) + ровно один retry; DecomposeResult (ok/error/age_anchors) — честные отказы.
- `routes_chronicle.py` — decompose/draft-чтение-запись (прецедент routes_board); подключён в main.py (вне тик-контура).
- `tests/sandbox/scenarios/chronicle_decompose_probe.py` — живой гейт T-CCH-02: самоподъём сервера менеджером проекта (паттерн IPT; SPAWN-ребёнок живёт в процессе пробы) + initialize_router (прод-прецедент main.py:120) + Итог-строка §3.12; LLM_UNAVAILABLE — честный RED.
- Гейт T-CCH-02 GREEN 6/0 (Q4_K_M): EVENT-граница удержана, мембрана инъектирует вопрос (conf 1.0→0.4), детерминизм = структурная сигнатура (канон S316 — canonical output = структура, не дословность summary).
- Канон модели: Q4_K_M (вердикт Мастера S335); user_settings.yaml синхронизирован; Qwen3.5-9B — план миграции. Находка-хвост владельцу settings_dm/npc/rules/world: stale Q5_K_M-дефолты + factory-инстанцирование на import — выстрелит при миграции.
- Находка-хвост владельцу tests/conftest.py:143 — патч model_qwen_7b_path на несуществующий Q5_K_M печатает [CONFIG]-шум во все pytest-прогоны.
- DEBT-CHRONICLE-REPLAY: replay-кэш промптов декомпозитора не подключён (рекордер привязан к тик-сессии) — владелец: контур replay.

## Реализация CCH-3 (S337/S340; MVP по вердикту Мастера)
- Backend: POST /api/chronicle/{campaign}/{npc}/canonize — draft→canonical (canonical_version++, replace-стиль), валидатор store = единственная инстанция «Save = Contract» (LLM_DRAFT/открытые вопросы/dangling → 422-класс ValueError с русским сообщением).
- Frontend: frontend/chronicle_editor/ (chronicle_app: 3 панели, F1/F2=decompose Ord-навигация, C+1..4=карточка вопросов 4-опций → resolve_question → draft PUT, F9=канонизация) + frontend/map_editor/chronicle/editor_screen.py (F7 MODE_CHRONICLE, паттерн MODE_LAB: enter/handle_event/update/draw) + MenuAction.CHRONICLE_EDITOR.
- Инфра: HttpClient.put (по прецеденту _execute); двойной sys.path-корень фронта решён явно (map_editor-файлы поднимают frontend-путь от __file__); rename editor_core→chronicle_app (дизамбигуация с map_editor/editor_core).
- Коммиты: d85ef720 (step B) / 37d30584 (fixup rename — урок: git mv НОВЫЙ путь обязателен в pathspec) / d6c11b3f (C-backend) / b9f147e8 (C-frontend, частично) / 0b4249a0 (D).
- Отложено решением Мастера: E (MERGE_CANDIDATE-карточки склеек → event_groups) и F (глубина F7-экрана) — до доказанной потребности использования.
