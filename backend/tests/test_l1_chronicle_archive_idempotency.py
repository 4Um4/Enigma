# path: backend/tests/test_l1_chronicle_archive_idempotency.py
# Назначение: Regression S270 — (1) архивация L1 идемпотентна: повторные вызовы
# archive_old_events не лавинно дублируют строки (проб доказал 99→396, гейт 99×4);
# (2) чтение query_raw детерминировано при равных tick_id (tiebreak source_id, id);
# (3) порядок событий стабилен между инстансами (RAM-reload из той же БД).
# Зависимости: app.services.memory.sqlite_store.SqliteMemoryStore,
#              app.services.npc.l1_chronicle.L1Chronicle, app.domain.identity_events
# Основные сущности: test_archive_idempotent_no_avalanche,
#                    test_query_raw_order_deterministic_and_reload_stable

"""
Запуск: cd backend; python -m pytest tests/test_l1_chronicle_archive_idempotency.py -v; cd ..
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from app.domain.identity_events import TraitDriftEvent
from app.services.memory.sqlite_store import SqliteMemoryStore
from app.services.npc.l1_chronicle import L1Chronicle


def _seed_events(chron: L1Chronicle) -> None:
    for t in range(1, 101):
        chron.append(TraitDriftEvent(
            tick_id=t,
            target_id="npc_x",
            source_id=f"src_{t % 7}",
            effect_value=0.1,
            observation_weight=1.0,
            event_type="drift",
        ))


def test_archive_idempotent_no_avalanche(tmp_path):
    store = SqliteMemoryStore(str(tmp_path / "a.db"))
    chron = L1Chronicle(store, campaign_id="reg")
    _seed_events(chron)
    counts = []
    for _ in range(4):
        chron.archive_old_events(current_tick=2100)  # threshold=100
        counts.append(
            store.query("SELECT COUNT(*) AS n FROM l1_chronicle_archive")[0]["n"]
        )
    # Гейт Мастера: лавина 99→198→297→396 недопустима
    assert counts == [99, 99, 99, 99], f"archive avalanche: {counts}"
    # PatternDetector видит честную историю: 99 архив + 1 RAM
    assert len(chron.query_raw("npc_x")) == 100
    store.close()


def test_query_raw_order_deterministic_and_reload_stable(tmp_path):
    db = str(tmp_path / "b.db")
    store1 = SqliteMemoryStore(db)
    chron1 = L1Chronicle(store1, campaign_id="reg")
    # Ties по tick_id: три источника в одном тике (легальная федерация писателей)
    for src in ("src_c", "src_a", "src_b"):
        chron1.append(TraitDriftEvent(
            tick_id=7, target_id="npc_x", source_id=src,
            effect_value=0.2, observation_weight=1.0, event_type="drift",
        ))
    # Контракт S270 (археология зафиксировала): RAM-ветка query_raw отдаёт
    # события в порядке вставки (детерминировано последовательностью append
    # внутри рана). Канонический порядок (tick, source, id) гарантируют
    # SQL-ветки: архив (Б-1) и reload (Б-2).
    order_ram = [(e.tick_id, e.source_id) for e in chron1.query_raw("npc_x")]
    assert order_ram == [(7, "src_c"), (7, "src_a"), (7, "src_b")], (
        f"RAM insertion order изменился: {order_ram}"
    )
    store1.close()

    # Reload (SQL-ветка Б-2): канонический порядок по (tick_id, source_id, id)
    store2 = SqliteMemoryStore(db)
    chron2 = L1Chronicle(store2, campaign_id="reg")
    chron2._ensure_loaded()
    order_reloaded = [(e.tick_id, e.source_id) for e in chron2.query_raw("npc_x")]
    assert order_reloaded == [(7, "src_a"), (7, "src_b"), (7, "src_c")], (
        f"reload не отсортирован по tiebreak: {order_reloaded}"
    )
    store2.close()

    # Третий инстанс: reload стабилен байт-в-байт между инстансами
    store3 = SqliteMemoryStore(db)
    chron3 = L1Chronicle(store3, campaign_id="reg")
    chron3._ensure_loaded()
    order_reloaded2 = [(e.tick_id, e.source_id) for e in chron3.query_raw("npc_x")]
    assert order_reloaded2 == order_reloaded, (
        f"reload нестабилен: {order_reloaded} vs {order_reloaded2}"
    )
    store3.close()