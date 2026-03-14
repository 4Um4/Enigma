# README2.md: Dev Audit — Заявлено vs Реально работает

Структура для разработчиков: анализ по компонентам на основе README.md (заявлено) vs фактическое состояние (учитывая TODO и Tasks).

| Компонент / Система | Заявлено | Реальное | Противоречие / Риск | Рекомендация |
|---------------------|----------|----------|---------------------|--------------|
| Multi-Agent Pipeline | Player → RULES → WORLD → NPC → DM → MEMORY | Чаще используется только DM; lazy switching частично (ThreadPool есть, но GPU модель одна) | 70–80% риск, pipeline формально мультиагентный, но работает однолинейно | Реализовать полное lazy switching и unload/load моделей; включить параллельное выполнение RULES, WORLD, NPC с последовательным LLM |
| Lazy Loading моделей | Поддерживается через ModelPool / ModelRouter / LlamaCppProvider | Модели не выгружаются полностью после генерации; last_used_model cache частично | 65% риск переполнения VRAM и неконсистентной работы агентов | Завершить реализацию unload предыдущей модели перед загрузкой новой; full VRAM management |
| Статус моделей | qwen_7b/DM ✅, qwen_9b/World ⚠️, saiga ⚠️, npc_major ⚠️, npc_mass ⚠️ | qwen2.5-7b/DM ✅, Qwen3.5-9B/World ✅, saiga_mistral ✅, YandexGPT-5-Lite/NPC ✅ (npc_importance: major/mass) | 50% риск путаницы: статус обновлён, но docs lagging | Обновить документацию и таблицы статусов; синхронизировать с agent_model_map |
| World Simulation | Частично реализован (maybe_tick работает), план: snapshot, NPC timers, Event Queue | Snapshot, фоновые таймеры и очереди отсутствуют; только maybe_tick | 75% риск неконсистентной симуляции NPC и мира | Реализовать snapshot локаций, таймеры NPC, очередь событий; интегрировать с Orchestrator |
| Memory / Context | Trёхслойная память ✅, Dynamic Context ✅ | Контекст длинных кампаний (>3–5k токенов) не поддерживается, sliding window нет (limit=20 recent) | 80% риск потери логики при длинных сессиях | Реализовать sliding/retrieval window, lazy loading релевантного контекста; VectorDB |
| Storage / Infrastructure | SQLite / JSON, Vector DB (Chroma/FAISS/Qdrant) | SQLite отсутствует, Vector DB отсутствует (JSONL только) | 75% риск неконсистентности и невозможности хранения долгого контекста | Внедрить SQLite/JSON для snapshot; подключить Vector DB для retrieval |
| NPC уровни | Major NPC → npc_major, Crowd NPC → npc_mass | Массовые NPC частично активированы (importance field добавлено, _get_capability_for_npc); реакции упрощённые | 60% риск неконсистентного поведения; progress made | Полностью активировать npc_major/mass; настроить приоритеты реакций и memory интеграцию |
| Frontend / UI | Web UI базовый; Desktop UI нет | index.html исправлен, но отсутствует синхронизация памяти, панель игроков, Debug Console | 65% UX риск: игрок видит неполные данные, команды ограничены | Добавить синхронизацию состояния, панель игроков, Debug Console |
| Streaming / Token-by-Token | Планируется token streaming | Частично: stream_complete() добавлено в llama_cpp_provider, но не в UI/pipeline | 60% UX риск: “живой” DM частично, не full | Реализовать token streaming в Orchestrator/UI для постепенной генерации |
| Orchestrator / Потоки | CPU, async queue, управление приоритетами | ThreadPoolExecutor реализован; DM sequential, но switch_to_agent не всегда | 55% риск: команды /model работают частично | Полностью реализовать очередь агентов с приоритетами и VRAM-aware потоками |

✅ **Итог**: ключевые противоречия касаются:

- Реальной работы мультиагентного pipeline (full lazy switching и VRAM).
- Полноценной симуляции мира и NPC (snapshot, timers, очереди).
- Памяти и контекста для длинных кампаний (retrieval).
- Инфраструктуры хранения (SQLite/Vector DB).
- UI/UX (full streaming, панели).

**Прогресс по Tasks4 (TODO)**: Streaming/NPC levels частично fixed; remaining ~65% tasks.

**Если исправить по приоритету**:

1. Lazy switching и unload/load моделей → 
2. Memory / Context для длинных кампаний → 
3. World Simulation snapshot + NPC timers → 
4. Vector DB / Persistent storage → 
5. Streaming + Frontend улучшения.

