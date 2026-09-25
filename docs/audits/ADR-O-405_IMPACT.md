# ADR-O-405 Impact Audit — Investigation Board (Presentation-Persistence)
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- presentation-persistence (новый домен: saves/<campaign>/board_state.json)
- REST API (+4 эндпоинта /api/board/*)
- frontend UI Workbench (+окно board, +5 api_client-методов, +бинд open_board)

## Downstream Consumers
- НЕТ в ядре: board вне тик-пайплайна (Фазы 0-10 не затронуты — доказано
  гейтом G3: player_beliefs живого снапшота byte-for-byte не изменились
  после полного цикла операций)
- Читает: frontend board_window ← dialog_journal снапшота (event_id джойн,
  только чтение) ← project_journal (ADR-O-404)
- Пишет: только PlayerBoardService в board_state.json (единственный писатель)

## Runtime Impact
- RAM: пренебрежимо (кэш доски в Workbench — одна JSON-структура, загружается
  при открытии окна)
- Latency: 0 в тик-пути; HTTP-операции только при интеракциях пользователя
  (мир на F12-паузе опционально; lock per campaign в store делает операции
  безопасными и вне паузы)

## Sandbox Tests
- backend/tests/test_player_board_service.py (8) — round-trip, self-repair,
  idempotent link, каскад, битый JSON, изоляция (unit-контур)
- backend/tests/test_routes_board.py (11) — REST-контракт, 422-семантика,
  traversal-защита, каскад через REST
- backend/tests/test_board_acceptance_gates.py (5) — гейты приёмки ТЗ §6:
  G1 round-trip, G2 пустая карточка + opaque refs, G3 изоляция (живой
  EpistemicStore), G4 M7
- backend/tests/IPT.py 46/46 — baseline не тронут (board вне ядра)

## Rollback
1. main.py: убрать импорт routes_board + include_router (2 строки)
2. game_screen.py: убрать присваивания self._gateway/self.campaign_folder (3 строки)
3. workbench_screen.py: unregister-веток нет — BOARD_MANIFEST не регистрировать
   (1 строка импорта + 1 строка register; ветки elif и интеракции — мёртвый код
   без регистрации, безопасны)
Файл board_state.json у пользователей остаётся (данные не теряются), читается
никем — чистый откат без миграции данных.

## Known Gaps (честно)
- ADD_CARD только через REST (UI-выбор материала из журнала — следующая итерация)
- Текст гипотезы — placeholder (inline text-input не реализован)
- except Exception в UI-интеракциях шире BackendError (ошибка рисуется —
  не тихий отказ, но сузить корректно)
- Рёбра между карточками не рисуются (только хранятся)
