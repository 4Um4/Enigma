# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/probes/d3_autonomous_chain_probe.py
Назначение: Э-3 acceptance (Phase D, главный): АВТОНОМНАЯ причинная цепь
    bootstrap-unlock. Ноль инъекций знания/цели: noseed NPC с конфиговым
    schedule (guarding_gate→city_gate) сам проходит:
    UNKNOWN → _unknown_route → consume → frontier-выбор (печать «почему»)
    → EXPLORATION intent → Arbiter ACCEPT (idle-окно) → intra-loc traversal
    → TES arrival → boundary_dwell → existing transfer → physical crossing
    → direct EXITS_TO → PERSONAL_ROUTE=KNOWN → delivery → NPC в city_gate.
    Негативы: ДО crossing store пуст (нет EXITS_TO/neighbor-утечки).
Зависимости: tests.gameplay.harness
Основные сущности: main
Запуск: cd backend; python -m tests.sandbox.probes.d3_autonomous_chain_probe
"""

from tests.gameplay.harness import TavernGameplayHarness

_C = "Open_road"
_NID = "guard_borko"
_MAX_TICKS = 80  # миграция через idle-окна арбитража: запас

_GREEN = []
_RED = []


def _log(m: str) -> None:
    print(f"[DIAG_D3] {m}", flush=True)


def _scene(h, loc: str) -> dict:
    return h.game_loop.scene_manager.get_scene_state(_C, loc) or {}


def main() -> int:
    import logging as _logging

    # Capture-канон RCB (:29-55): маркеры причинной цепи без него невидимы
    # (logger по умолчанию глушит INFO). Слепота первого прогона — урок.
    class _Col(_logging.Handler):
        def __init__(self) -> None:
            super().__init__(level=_logging.DEBUG)
            self.lines: list = []

        def emit(self, record: _logging.LogRecord) -> None:
            try:
                m = record.getMessage()
                if any(k in m for k in (
                    "UNKNOWN_ROUTE", "EXPLORATION", "PERSONAL_ROUTE",
                    "SPATIAL_KNOWLEDGE", "BOUNDARY_DWELL", "SCHED_TRACE",
                    "cross-loc relocation", "ARBITER_REJECT",
                    "GATE_B1_5", "MOVEMENT_TRACE", "TRAV_EXEC",
                    "GATE_A", "GATE_B2", "IDLE_SPATIAL",
                    # Не содержат npc_id в тексте — ловим по маркеру
                    "GATE_B1]", "BORKO_TRACE", "BORKO_RELOC",
                    # D-3: локации тиков и инжекты (не содержат borko)
                    "S186_DEBUG", "S186_INJECT", "S186_TRANSFER",
                    "SPATIAL_KNOWLEDGE", "DIRECT_EXPERIENCE",
                )) and ("borko" in m or "GATE_" in m or "BORKO_" in m
                        or "S186_" in m or "SPATIAL_KNOWLEDGE" in m
                        or "merchant_goran" in m or "maid_lusya" in m):
                    self.lines.append(m[:200])
            except Exception:  # noqa: S110
                pass

    _col = _Col()
    _svc_log = _logging.getLogger("app.services")
    _svc_log.setLevel(_logging.DEBUG)
    _svc_log.addHandler(_col)

    with TavernGameplayHarness(location="tavern") as h:
        # НОЛЬ модификаций NPC: конфиговый guarding_gate сам генерирует
        # relocation-интенты (production-факт RCB-трассы).
        h.advance_ticks(2)
        # Активация schedule (канал среды RCB :124-132 — НЕ знание, НЕ цель:
        # night-time это вход мира, тот же GIVEN, что в RCB). Без него
        # guarding_gate неактивен → мигрантский UNKNOWN не рождается
        # (диагноз прогона 108: borko осел eating в kitchen).
        sc0 = _scene(h, "tavern")
        sc0["game_time_seconds"] = 0.5 * 3600.0
        sc0.setdefault("environment", {})["time_of_day"] = "ночь"
        # Верdikт A (Мастер): голод 0.95 = артефакт фикстуры (ECO-рост без
        # разрядки), need-lock душил exploration 7/7 (прогон 109). Сброс
        # потребности = вход тела по прецеденту RCB :133-135 (sleep_pressure).
        # НОСИТЕЛЬ — LifeEngine-кэш-дикт (inspect_npc, канал RCB activity_map):
        # hunger читается LifeEngine из кэша (life_engine:1404 npc.get("needs")),
        # НЕ из npc_positions записи. Прогон 110: запись в scene_state-носитель
        # не дошла (числа байт-в-байт как в 109) — ловушка второго носителя.
        _n_cache = h.inspect_npc(_NID)
        if isinstance(_n_cache, dict):
            _n_cache.setdefault("needs", {})["hunger"] = 0.05
            _back = (h.inspect_npc(_NID) or {}).get("needs", {}).get("hunger")
            _log(f"GIVEN: hunger сброшен в кэш-дикт, back-read={_back}")
        else:
            _log("GIVEN WARN: кэш-дикт недоступен, hunger НЕ сброшен")
        _log("GIVEN: ночь активирована (канон RCB, канал среды); hunger сброшен (вход тела, вердикт A)")

        # НЕГАТИВ A: до каких-либо crossing персональный store пуст
        _ep = getattr(getattr(h.game_loop, "_tick_orch", None), "_epistemic_store", None)
        if _ep is None:
            _RED.append("NEG-A: store недоступен")
        else:
            _recs = (getattr(getattr(h.game_loop, "_tick_orch", None), "_epistemic_store", None) or _ep).get_all_for_agent(_NID) or []
            _exits = [
                r for r in _recs
                if getattr(getattr(r, "proposition", None), "predicate", None) is not None
                and getattr(r.proposition.predicate, "value", "") == "exits_to"
            ]
            if not _exits:
                _GREEN.append(f"NEG-A: store пуст по EXITS_TO до crossing ({len(_recs)} записей всего)")
            else:
                _RED.append(f"NEG-A: EXITS_TO уже есть до crossing: "
                            f"{[str(r.proposition.subject_id) for r in _exits]}")

        _exploration_seen = False
        _knowledge_tick = None
        _left_tavern_tick = None
        _stale_signals = set()

        for t in range(_MAX_TICKS):
            h.advance_ticks(1)
            # Печать «почему выбран boundary» идёт из резолвера ([EXPLORATION]
            # в логе) — probe фиксирует факт рождения кандидата через позицию.
            sc = _scene(h, "tavern")
            entry = (sc.get("npc_positions") or {}).get(_NID)
            dwell = sc.get("boundary_dwell") or {}
            if _NID in dwell and not _exploration_seen:
                # dwell без сидированного KNOWN-гейта = NPC дошёл до двери сам
                pass
            if entry is None:
                _left_tavern_tick = t
                _log(f"tick={t}: NPC покинул tavern")
                # Пересечение состоялось: фиксируем тик знания (dwell-ветка
                # пишет при transfer). Через 1 тик проверяем store.
                _knowledge_tick = t
                break
            _pos = entry.get("position", "")
            _sig = entry.get("_unknown_route")
            if _sig is not None:
                _stale_signals.add(str(_sig.get("tick")))
            _trav_b = (sc.get("active_traversals") or {}).get(_NID)
            _cmt_b = (sc.get("active_commitments") or {}).get(_NID)
            _log(f"tick={t}: pos={_pos} dwell={'DA' if _NID in dwell else 'net'} "
                 f"trav={_trav_b.get('status') if isinstance(_trav_b, dict) else None} "
                 f"cmt={_cmt_b.get('status') if isinstance(_cmt_b, dict) else None}")

        # НЕГАТИВ B: neighbor не утёк — после crossing в store только
        # direct-записи (проверка после выхода из tavern)
        if _knowledge_tick is not None:
            # Вердикт: ждать transfer ИМЕННО borko (any(...) всегда True от
            # чужих 'dwell complete' — player tick=5, shadow tick=7-9; прогон
            # v6: RED при живом dump). После факта transfer'а borko даём
            # 2 тика (transfer-ветка исполняется PRE-TICK следующего тика)
            # и проверяем store — fresh getattr (не stale-ссылка).
            _borko_transfer_idx = next(
                (i for i, ln in enumerate(_col.lines) if "dwell complete" in ln and "guard_borko" in ln),
                None,
            )
            if _borko_transfer_idx is not None:
                h.advance_ticks(2)
            _recs = (getattr(getattr(h.game_loop, "_tick_orch", None), "_epistemic_store", None) or _ep).get_all_for_agent(_NID) or []
            _bad = [
                r for r in _recs
                if getattr(getattr(r, "proposition", None), "source_claim_id", "") or ""
                and not str(getattr(r.proposition, "source_claim_id", "")).startswith(("direct:", "seed:"))
            ]
            # Вердикт: запись может быть легально перезаписана claim-каналом
            # (provenance 'direct:' → 'claim-*' — перезапись последним upsert'ом
            # того же Proposition, находка прогона v8) — проверяем ФАКТ ребра,
            # соответствующего фактическому crossing'у, а не provenance.
            _exits_direct = [
                r for r in _recs
                if getattr(getattr(r.proposition, "predicate", None), "value", "") == "exits_to"
            ]
            # Вердикт: дверь первого crossing выбирает frontier (не хардкод
            # exit_east) — проверяем ФАКТИЧЕСКУЮ direct-запись, любая дверь.
            if _exits_direct:
                _GREEN.append(f"NEG-B/CHAIN: direct EXITS_TO после crossing: "
                              f"{[(str(r.proposition.subject_id), str(r.proposition.object_id)) for r in _exits_direct]}")
            else:
                _RED.append("NEG-B: после crossing нет direct EXITS_TO")
            if not _bad:
                _GREEN.append("NEG-B: все записи direct — neighbor-утечки нет")
            else:
                _RED.append(f"NEG-B: записи с чужим provenance: {len(_bad)}")
        else:
            _RED.append(f"CHAIN: NPC не покинул tavern за {_MAX_TICKS} тиков")

        # CHAIN: PERSONAL_ROUTE=KNOWN → delivery → NPC физически в city_gate
        if _left_tavern_tick is not None:
            # S186-inject в целевой локации на следующем тике; даём доезд
            for _t2 in range(_MAX_TICKS):
                h.advance_ticks(1)
                if (_scene(h, "city_gate").get("npc_positions") or {}).get(_NID):
                    _GREEN.append(f"CHAIN: NPC физически в city_gate (tick={_t2})")
                    break
            else:
                _RED.append("CHAIN: NPC не материализовался в city_gate")

        # Полный EXITS_TO-dump всех агентов (вердикт: отсутствие строки в trace
        # ≠ отсутствие события — store — истина). ДОЛЖЕН быть ВНУТРИ with:
        # после dispose store недоступен (оплачено прогонами 191/205/211 —
        # dump молча пропущен трижды).
        _ep_final = getattr(getattr(h.game_loop, "_tick_orch", None), "_epistemic_store", None)
        if _ep_final is not None:
            for _aid in ("guard_borko", "thief_shadow", "merchant_goran", "tavern_keeper_tornin", "maid_lusya", "blacksmith_orm", "player"):
                _recs = [r for r in (_ep_final.get_all_for_agent(_aid) or [])
                         if getattr(getattr(r, "proposition", None), "predicate", None) is not None
                         and getattr(r.proposition.predicate, "value", "") == "exits_to"]
                if _recs:
                    _log(f"EXITS_DUMP {_aid}: {[(str(r.proposition.subject_id), str(r.proposition.object_id), f'{getattr(r, 'confidence', 0):.2f}', str(getattr(r, 'source_claim_id', ''))[:30]) for r in _recs]}")
                else:
                    _log(f"EXITS_DUMP {_aid}: (нет)")

    # Трасса причинной цепи из capture (доказательство «почему/что произошло»)
    _trace = getattr(_col, "lines", [])
    if any("exploration:frontier" in ln for ln in _trace):
        _GREEN.append(f"TRACE: exploration-кандидат рождался ({sum(1 for ln in _trace if 'exploration:frontier' in ln)}x)")
    if any("UNKNOWN_ROUTE" in ln for ln in _trace):
        _GREEN.append(f"TRACE: UNKNOWN факты ({sum(1 for ln in _trace if 'UNKNOWN_ROUTE' in ln)}x)")
    if any("BOUNDARY_DWELL" in ln for ln in _trace):
        _GREEN.append("TRACE: boundary_dwell/arrival в живой цепи")
    if any("SPATIAL_KNOWLEDGE" in ln for ln in _trace):
        _GREEN.append("TRACE: DIRECT_EXPERIENCE записан")
    if any("exploration:frontier" in ln and "REJECT" in ln for ln in _trace):
        _log(f"NOTE: exploration REJECT'ился арбитром {sum(1 for ln in _trace if 'exploration' in ln and 'REJECT' in ln)}x до ACCEPT (политика Э-0, не баг)")

    # Полный дамп причинной трассы (артефакт досье; без него различить
    # «погиб в арбитре / в GATE_B1_5 / не родился» невозможно)
    try:
        with open("../d3_trace_full.txt", "w", encoding="utf-8") as _tf:
            _tf.write("\n".join(_trace))
        _log(f"TRACE: {len(_trace)} строк -> ../d3_trace_full.txt")
    except Exception as _e:  # noqa: BLE001 — probe-инфраструктура
        _log(f"TRACE DUMP FAIL: {_e}")

    for g in _GREEN:
        _log(f"GREEN: {g}")
    for r in _RED:
        _log(f"RED:   {r}")
    _log(f"Итог: GREEN={len(_GREEN)} RED={len(_RED)}")
    return 0 if not _RED else 1


if __name__ == "__main__":
    raise SystemExit(main())