# path: backend/tests/sandbox/probes/l1_archive_avalanche_probe.py
# Назначение: доказать/опровергнуть квадратичную лавину дубликатов в l1_chronicle_archive
# (INSERT..SELECT без очистки источника, Rule 28-наследие). Одноразовый зонд (ЧАСТЬ probes/).
# Зависимости: app.services.memory.sqlite_store, app.services.npc.l1_chronicle
# Основные сущности: probe_main()
"""
Запуск: cd backend; python tests/sandbox/probes/l1_archive_avalanche_probe.py; cd ..

"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # backend/ — корень пакета app

from app.domain.identity_events import TraitDriftEvent
from app.services.memory.sqlite_store import SqliteMemoryStore as SqliteStore
from app.services.npc.l1_chronicle import L1Chronicle


def probe_main() -> None:
    db = Path(__file__).parent / "_probe_l1.db"
    if db.exists():
        db.unlink()
    store = SqliteStore(str(db))
    chron = L1Chronicle(store, campaign_id="probe")

    # 100 событий в тиках 1..100 (все будут ниже порога архивации)
    for t in range(1, 101):
        chron.append(TraitDriftEvent(
            tick_id=t, target_id="npc_x", source_id=f"src_{t % 7}",
            effect_value=0.1, observation_weight=1.0, event_type="drift",
        ))
    print("[PROBE] events_in_ram_after_append:", len(chron._events.get("npc_x", [])))

    # Четыре вызова архивации с ОДНИМ порогом = симуляция %500-вызовов
    # при нечищеном источнике (каждый вызов копирует те же строки заново)
    for k in range(1, 5):
        chron.archive_old_events(current_tick=2100)  # threshold=100
        n_arch = store.query("SELECT COUNT(*) AS n FROM l1_chronicle_archive")[0]["n"]
        n_src = store.query("SELECT COUNT(*) AS n FROM l1_chronicle_events")[0]["n"]
        print(f"[PROBE] archive_call={k}: archive_rows={n_arch}, source_rows={n_src}, ram={len(chron._events.get('npc_x', []))}")

    # Смертельный тест: сколько событий видит PatternDetector
    seen = chron.query_raw("npc_x")
    print(f"[PROBE] query_raw_len_after_4_calls: {len(seen)} (честная история=0 RAM+100 архив; лавина даст >100)")
    store.close()
    db.unlink()


if __name__ == "__main__":
    probe_main()