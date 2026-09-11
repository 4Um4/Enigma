# path: /project/scripts/check_canon_sync.py
# Назначение: M1/P2 (ТЗ «Таверна тайн») — статическая половина canon-sync
#   чека: конфиги NPC <-> канон. Семантика: secret_id = идентичность ФАКТА
#   (вердикт Мастера); known_by конфигов = legacy-метадата, НЕ проверяется
#   (№1=CANON-PRESERVE). Runtime-половина (holders имеют EventMemory) —
#   tests/gameplay/test_p2_canon_sync.py. Выход 0/1 для CI.
# Зависимости: app.services.npc.npc_loader (канон-синглтон, корень конфигов)
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend" / "app"), str(ROOT / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.services.npc import npc_loader as L  # noqa: E402


def main() -> int:
    errors: list = []
    truth = L._canon_truth_state()
    canon_ids = set(truth.secrets)
    if len(canon_ids) != 17:
        errors.append(f"канон: {len(canon_ids)} секретов (ожидалось 17)")

    ind = L._CONFIG_NPC_ROOT / "individuals"
    npc_ids = set()
    n_secret_events = 0
    for f in sorted(ind.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8-sig"))
        npc_ids.add(data.get("id", f.stem))
        for ev in data.get("origin_events", []) or []:
            if not ev.get("is_secret"):
                continue
            n_secret_events += 1
            sid = ev.get("secret_id")
            if not sid:
                errors.append(
                    f"{f.name}: is_secret origin без secret_id "
                    f"({str(ev.get('summary', ''))[:60]!r})")
            elif sid not in canon_ids:
                errors.append(f"{f.name}: secret_id {sid!r} вне канона")

    for sec in truth.secrets.values():
        if not sec.initial_holders:
            errors.append(f"{sec.secret_id}: пустые initial_holders")
        for p in sec.participants:
            if p not in npc_ids:
                errors.append(f"{sec.secret_id}: participant {p!r} не NPC")
        for h in sec.initial_holders:
            if h not in npc_ids:
                errors.append(f"{sec.secret_id}: holder {h!r} не NPC")

    vr = L._CONFIG_NPC_ROOT / "social" / "village_relations.json"
    if not vr.exists():
        errors.append("village_relations.json отсутствует (notes-материал)")
    else:
        vrd = json.loads(vr.read_text(encoding="utf-8-sig"))
        n_notes = sum(1 for v in vrd.get("relations", {}).values()
                      if isinstance(v, dict) and v.get("notes"))
        if n_notes == 0:
            errors.append("village_relations: 0 notes-фактов")
        else:
            print(f"notes-факты: {n_notes}")

    print(f"конфиг-секретов с id: {n_secret_events}; NPC: {len(npc_ids)}; "
          f"канон: {len(canon_ids)}")
    if errors:
        print("CANON-SYNC: RED")
        for e in errors:
            print("  -", e)
        return 1
    print("CANON-SYNC: GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
