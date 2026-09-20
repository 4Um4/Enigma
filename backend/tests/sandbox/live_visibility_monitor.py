# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/live_visibility_monitor.py
Назначение: живой монитор visibility-контракта k0t8yr во время production-сессии.
    Читает ЗАКОММИЧЕННОЕ состояние (SQLite state_kv — канал Фазы 10,
    atomic_commit_all) из отдельного процесса — наблюдение не создаёт
    причинность (CAUSAL_CONTRACT §11). Детекторы по вердикту Мастера:
    D1 не-сон невидим (нарушение контракта);
    D2 сон невидим, но позиция не BED (эвристика по имени узла — честно
       помечена; Н-4 гарантирует движок, D2 ловит наблюдаемое);
    D3 wake-переход без немедленного visible=True;
    D4 однотиковое мигание (класс brief_exit; ограничено частотой опроса);
    D5 stuck-False (длинный невидимый интервал при не-сне).
    По остановке (Ctrl+C) — финальный отчёт-вердикт: данные для MUTATIONS.
Зависимости: sqlite3, json (stdlib); БД backend/saves/enigma_runtime.db;
    app.services.npc.sleep_states.is_sleeping (канонический предикат V-1).
Основные сущности: main, _poll, _report
Запуск: cd backend; python tests/sandbox/live_visibility_monitor.py
    (игра запускается параллельно; монитор остановить Ctrl+C после сессии)
"""
import json
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

from app.services.npc.sleep_states import is_sleeping

_CAMPAIGN = "Open_road"
# Канал персистенции — фактический write-path production (game_loop_builder:45):
# SqlitePersistenceAdapter("saves/enigma_runtime.db"), таблица state_kv,
# ключи scene:{campaign_id}:{location_id} (адаптер :72-80, WAL — читатель не блокирует).
# БД может быть пустой до первого коммита игры — терпеливо ждём.
# ФАКТ (живая сессия): production-backend пишет относительно cwd КОРНЯ
# репо (launcher запускает uvicorn из корня) — O-верифицировано:
# живой файл = <repo>/saves/enigma_runtime.db, backend/saves/ — мёртвая
# 0-байтовая заготовка. Абсолютный путь — cwd-независимость монитора.
_DB = str(Path(__file__).resolve().parents[3] / "saves" / "enigma_runtime.db")
_POLL_SEC = 1.0
_STUCK_POLLS = 5          # D5: подряд невидим при не-сне ~5 сек
# Целевые NPC вердикта — маркер отчёта, не логика движка (ID-хардкоды
# запрещены в механизмах; здесь — диагностический фокус наблюдения)
_TARGETS = {"tavern_keeper_tornin", "merchant_goran", "blacksmith_orm"}


def _norm_node(s):
    # тот же канон, что Н-4: сравнение по хвосту узла
    return s.split(":")[-1] if s else s


def _poll():
    out = {}
    try:
        conn = sqlite3.connect(_DB)
        try:
            rows = conn.execute(
                "SELECT key, value FROM state_kv WHERE key LIKE ?",
                (f"scene:{_CAMPAIGN}:%",),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return out  # таблицы ещё нет — игра не стартовала/не коммитила; ждём
    for _k, v in rows:
        loc = _k.split(":")[-1]
        d = json.loads(v)
        for nid, e in (d.get("npc_positions") or {}).items():
            if nid == "player":
                continue
            out[nid] = {
                "loc": loc,
                "visible": e.get("visible", True),
                "act": str(e.get("activity") or ""),
                "pos": str(e.get("position") or ""),
            }
    return out


def main() -> int:
    hist = defaultdict(list)          # nid -> [(ts, visible, act, pos)]
    cnt = defaultdict(lambda: defaultdict(int))   # nid -> {D1..D5, LEGAL_SLEEP}
    active = defaultdict(bool)        # nid -> сейчас внутри D1/D5-нарушения
    print("[LVIS] монитор запущен; Ctrl+C — остановка и отчёт", flush=True)
    _last_beat = 0.0
    _data_seen = False
    try:
        while True:
            now = time.time()
            snap = _poll()
            if snap and not _data_seen:
                _data_seen = True
                print(f"[LVIS] КАНАЛ ЖИВ: NPC={len(snap)} "
                      f"({', '.join(sorted(snap))[:120]})", flush=True)
            if now - _last_beat >= 30.0:
                _last_beat = now
                print(f"[LVIS] heartbeat t={time.strftime('%H:%M:%S')}: "
                      f"NPC в кадре={len(snap)} (нарушений в потоке — тишина)",
                      flush=True)
            for nid, e in snap.items():
                h = hist[nid]
                h.append((now, e["visible"], e["act"], e["pos"]))
                vis, act, pos = e["visible"], e["act"], e["pos"]
                sleeping = is_sleeping(act)
                # D1: не-сон невидим
                if vis is False and not sleeping:
                    if not active[nid]:
                        active[nid] = True
                        cnt[nid]["D1"] += 1
                        print(f"[LVIS][D1] {nid} t={time.strftime('%H:%M:%S')} "
                              f"act={act!r} pos={pos} loc={e['loc']}", flush=True)
                else:
                    active[nid] = False
                # D2 (v2, живое наблюдение Мастера): sleeping-лейбл вне
                # BED-узла — независимо от visible. После Н-4 такой NPC
                # ЧЕСТНО ВИДИМ: лжёт ярлык activity, не видимость.
                if sleeping:
                    if "bed" in _norm_node(pos).lower():
                        cnt[nid]["LEGAL_SLEEP"] += 1
                    else:
                        cnt[nid]["D2"] += 1
                        print(f"[LVIS][D2] {nid} t={time.strftime('%H:%M:%S')} "
                              f"act={act!r} но pos={pos} не BED loc={e['loc']} "
                              f"visible={vis}", flush=True)
                # D3: wake без немедленного True
                if len(h) >= 2:
                    _p, pvis, pact, _pp = h[-2]
                    if is_sleeping(pact) and not sleeping and vis is False:
                        cnt[nid]["D3"] += 1
                        print(f"[LVIS][D3] {nid} t={time.strftime('%H:%M:%S')} "
                              f"wake {pact!r}->{act!r} но visible=False", flush=True)
                    # D4: blink True->False->True при неизменной не-сонной activity
                    if len(h) >= 3:
                        _pp, v2, a2, _p3 = h[-3]
                        if (v2 is True and pvis is False and vis is True
                                and a2 == act and not sleeping):
                            cnt[nid]["D4"] += 1
                            print(f"[LVIS][D4] {nid} t={time.strftime('%H:%M:%S')} "
                                  f"blink act={act!r}", flush=True)
                # D5: stuck-False при не-сне
                if vis is False and not sleeping:
                    streak = 0
                    for _ts, v2, a2, _p4 in reversed(h):
                        if v2 is False and not is_sleeping(a2):
                            streak += 1
                        else:
                            break
                    if streak > _STUCK_POLLS:
                        if cnt[nid]["D5"] == 0 or streak == cnt[nid]["_d5_last"] + 1:
                            pass
                        if streak == _STUCK_POLLS + 1:
                            cnt[nid]["D5"] += 1
                            print(f"[LVIS][D5] {nid} stuck-False "
                                  f">{_STUCK_POLLS} опросов act={act!r}", flush=True)
            time.sleep(_POLL_SEC)
    except KeyboardInterrupt:
        pass
    _report(hist, cnt)
    return 0


def _report(hist, cnt) -> None:
    print("\n[LVIS] ===== ФИНАЛЬНЫЙ ОТЧЁТ ЖИВОЙ СЕССИИ =====", flush=True)
    if not hist:
        # Анти-фальсификация (урок протокола Мастера): пустая выборка —
        # не «ЧИСТО», а невалидное измерение.
        print("[LVIS] ВЕРДИКТ: ПУСТОЕ ИЗМЕРЕНИЕ — ни один NPC не наблюдался; "
              "INVALID RUN, живой сессии не было", flush=True)
        return
    total_bad = 0
    for nid in sorted(hist):
        c = cnt[nid]
        polls = len(hist[nid])
        bad = c["D1"] + c["D2"] + c["D3"] + c["D4"] + c["D5"]
        total_bad += bad
        mark = " <<< ЦЕЛЕВОЙ" if nid in _TARGETS else ""
        print(f"[LVIS] {nid}: опросов={polls} D1={c['D1']} D2={c['D2']} "
              f"D3={c['D3']} D4={c['D4']} D5={c['D5']} "
              f"легальных_снов_на_BED={c['LEGAL_SLEEP']}{mark}", flush=True)
    verdict = "ЧИСТО" if total_bad == 0 else f"НАРУШЕНИЙ={total_bad}"
    print(f"[LVIS] ВЕРДИКТ: {verdict}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())