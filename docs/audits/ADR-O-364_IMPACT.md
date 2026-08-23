# ADR-O-364 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`
## Changed Domains
- Concurrency / ThreadPoolExecutor (022)
- Backpressure / Queue Overflow (027)
- Error handling / Persistence / Reconstruction (038)

## Downstream Consumers
- `DialogueExecutor` (получает строгий `QueuedTask` или дропает его)
- `DialogueMaterializer` (публикует `NPC_SPOKE` только для успешно исполненных задач)
- `ClaimEventSubscriber` (слушает `NPC_SPOKE`, защищён от потери canonical реплик)
- `EventBus` (доставка событий)
- `scene_state["pending_tasks"]` (источник задач)

## Runtime Impact
- RAM: Введение `MAX_PENDING_TASKS = 20` (baseline) ограничивает рост кучи `DialogueQueue`. Трекинг `max_pending` добавляет O(1) к `enqueue`.
- Latency: Per-task timeout (`_L_TIMEOUT_SEC = 30.0`) гарантирует, что пул не будет заблокирован дольше 30 секунд. Таймер живёт в отдельном потоке, не блокирует main loop.
- CPU: `heapify` при вытеснении ambient задачи — O(N log N), при размере кучи ≤ 20 абсолютно дёшево.

## Sandbox Tests
- `test_scheduler_timeout_recovery.py` (планируется: зависшая задача не блокирует последующие)
- `test_queue_drop_low_priority.py` (планируется: при переполнении дропаются только ambient)
- `test_reconstruction_logging.py` (планируется: падение реконструкции canonical логирует и отбрасывает)
- Текущий IPT: 44/44 passed (baseline не сломан)

## Rollback
- Feature flags не вводились (согласно решению пользователя).
- Откат осуществляется revert'ом коммита.
- В случае критической регрессии в production, `_abort_generation` можно отключить, вернувшись к зависанию (старое поведение), но это не рекомендуется.

## Post-Implementation (027.1 Fix)
- **Artefact:** `intent_profiles.py` дополнен `produces_claim` для социальных/экономических интентов.
- **Artefact:** `task_scheduler.py` (`execute_pending`) переведён на `intent_profiles` вместо хардкода.
- **Artefact:** Non-LLM задачи (`requires_llm == False`) пущены в fast-path, минуя `DialogueQueue`.
- **Result:** Canonical queue saturation (741 overflow) полностью устранена. Ambient-задачи поглощают перегрузку. Canonical loss = 0.
