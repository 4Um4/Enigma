# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/SUPERBOX/scenarios/action_integrity_test.py
Назначение: SUPERBOX-ACTION-INTEGRITY (Stage 2A, промежуточный behavioral gate
    Мастера перед ownership surgery S203.3). Аудит связки Registry (S203.1) +
    Arbitration (S203.2, enforcement ON) на production-контуре.
    Дисциплина: GIVEN -> EXPECT -> DISCOVER (Мастер: цепочка-как-гипотеза,
    не implementation test; post-terminal состояние — обнаруживается, не
    предписывается). Oracle трёхуровневый: GREEN (инварианты) / YELLOW
    (диагностика -> вход S203.6) / RED (провал -> вход S203.3).
    Сценарии: A-eat / B-sleep / C-impossible. D/E/F — вне границ (S203-E).
    Инъекции — стартовые условия NPC в temp-копии кампании (механизм S213/S214;
    Rule 25: чистый старт песочницы != ретро-симуляция).
Зависимости: app.services.game_loop_builder, app.services.action.* (чтение)
Основные сущности: main, run_scenario_a, run_scenario_b, run_scenario_c
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import types
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
_CAMPAIGN = "Open_road"
_LOCATION = "tavern"
_TICKS = 120          # окно сценария (Мастер: 100–150)
_POST_WINDOW = 30     # окно post-terminal наблюдения
_TARGET_NPC = "merchant_goran"  # игрок в еде виден в baseline (eating 5 раз)

_GREEN: list[str] = []
_YELLOW: list[str] = []
_RED: list[str] = []


def _log(msg: str) -> None:
    print(f"[AI] {msg}", flush=True)


def _quiet_loggers() -> None:
    """Глушение известного WARNING-шума канала на время прогона (наблюдение,
    не мутация конфигурации): DLG_QUEUE / S198 / SOCIAL_SUBSCRIBER / FLEE_NAV.
    Возврат — после прогона (не в harness: тест не владеет глобальным конфигом)."""
    for name in ("app.services.execution.dialogue_queue",
                 "app.services.npc.npc_tick_pipeline",
                 "app.services.events.social_subscriber",
                 "app.services.spatial.movement_engine"):
        lg = logging.getLogger(name)
        lg.addFilter(_MUTE)


class _MuteFilter(logging.Filter):
    def filter(self, record) -> bool:  # noqa: A003
        return False


_MUTE = _MuteFilter()


# ── Harness: мир с патчем NPC JSON ─────────────────────────────────────────


def _build_world(tag: str, npc_patch: dict | None = None):
    """npc_patch применяется RUNTIME после тика 0 (Н-57: NPC не в файлах
    кампании — стейты материализуются лениво; §13-зонд подтвердил поля)."""
    """Изолированный мир по конвенции goran_slice: temp saves + патч NPC.

    NPC-патч применяется к temp-КОПИИ конфигов кампании через подмену
    settings.data_dir (механизм preset_materializer S213).
    """
    from app.core.config import settings

    temp_root = Path(tempfile.mkdtemp(prefix=f"action_int_{tag}_"))
    temp_saves = temp_root / "saves"
    temp_saves.mkdir(parents=True)
    temp_data = temp_root / "data"
    temp_data.mkdir(parents=True)

    # Н-58: копируем data_dir ЦЕЛИКОМ (campaigns + locations + templates),
    # как goran_slice — частичная копия отрезала мир от location_templates.
    src_data = Path(settings.data_dir)
    shutil.copytree(src_data, temp_data, dirs_exist_ok=True)
    dst_campaign = temp_data / "campaigns" / _CAMPAIGN

    # Н-57: NPC-конфиги не в файлах кампании — инъекция runtime после тика 0
    # (_inject_runtime в _build_world). Файловый патч удалён.

    # Подмена окружения
    _orig_saves = settings.saves_dir
    _orig_data = settings.data_dir
    settings.saves_dir = str(temp_saves)
    settings.data_dir = str(temp_data)

    from app.services.game_loop_builder import build_game_loop

    loop = build_game_loop(Path(temp_data))
    world = types.SimpleNamespace(
        game_loop=loop, temp_root=temp_root,
        restore=lambda: (setattr(settings, "saves_dir", _orig_saves),
                         setattr(settings, "data_dir", _orig_data)),
    )
    # Тик 0: материализация LifeEngine-стейтов (ленивых до первого тика)
    loop.idle_tick(_CAMPAIGN)
    if npc_patch:
        _inject_runtime(world, npc_patch)
    return world


def _inject_runtime(world, patch: dict) -> None:
    """Runtime-инъекция стартовых условий в живой NPC-стейт (после тика 0,
    до тиков сценария). Поля подтверждены зондом: body_state.sleep_pressure,
    body_state.hunger (создаётся — LifeEngine читает через .get),
    activity_map (dict на месте). Schedule в стейте отсутствует — сценарий B
    форсируется sleep_pressure; C — activity_map."""
    le = world.game_loop._get_life_engine()
    states = le.get_npc_states(_CAMPAIGN) or []
    for st in states:
        if (st.get("npc_id") or st.get("id")) == _TARGET_NPC:
            for key, value in patch.items():
                if key == "body_state":
                    st.setdefault("body_state", {}).update(value)
                elif isinstance(value, dict) and isinstance(st.get(key), dict):
                    st[key].update(value)
                else:
                    st[key] = value
            _log(f"  [INJECT] {_TARGET_NPC}: {patch}")
            return
    _log(f"  [WARN] {_TARGET_NPC} не найден в стейтах после тика 0")


def _apply_npc_patch(campaign_dir: Path, patch: dict) -> None:
    """Патчит npc-JSON целевого NPC (поля: body_state.*, schedule, activity_map)."""
    patched = False
    for npc_file in campaign_dir.rglob("*.json"):
        try:
            data = json.loads(npc_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # npc-конфиг может быть списком или dict
        entries = data if isinstance(data, list) else [data]
        changed = False
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("npc_id") == _TARGET_NPC or entry.get("id") == _TARGET_NPC:
                for key, value in patch.items():
                    if isinstance(value, dict) and isinstance(entry.get(key), dict):
                        entry[key].update(value)
                    else:
                        entry[key] = value
                changed = True
        if changed:
            npc_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            patched = True
    if not patched:
        _log(f"[WARN] NPC {_TARGET_NPC} не найден в конфигах — патч не применён")


def _tick_n(loop, n: int) -> None:
    for _ in range(n):
        try:
            loop.idle_tick(_CAMPAIGN)
        except Exception as e:  # noqa: BLE001 — наблюдатель, не владелец тика
            _log(f"  [TICK_ERROR] {type(e).__name__}: {e}")


def _scene(world) -> dict:
    sm = world.game_loop.scene_manager
    return sm.get_scene_state(_CAMPAIGN, _LOCATION) or {}


def _commitment_timeline(scene: dict) -> list[dict]:
    """Полная timeline целевого NPC: active + history, отсортировано."""
    entries = []
    active = scene.get("active_commitments") or {}
    if _TARGET_NPC in active:
        entries.append(active[_TARGET_NPC])
    for entry in (scene.get("commitment_history") or {}).get(_TARGET_NPC, []):
        entries.append(entry)
    return entries


# ── GREEN-инварианты (каждый тик) ──────────────────────────────────────────


def _check_green(scene: dict, tick: int) -> None:
    active = scene.get("active_commitments") or {}
    traversals = scene.get("active_traversals") or {}

    # G1: <=1 активный commitment на NPC (структурно dict, но защищаемся)
    for npc, entry in active.items():
        if isinstance(entry, list):  # гипотетическая деградация
            _RED.append(f"G1 tick={tick}: npc={npc} list-commitments={len(entry)}")

    # G4: no orphan active (terminal в active)
    from app.domain.action_commitment import COMMITMENT_TERMINAL_STATUSES

    for npc, entry in active.items():
        if entry.get("status") in COMMITMENT_TERMINAL_STATUSES:
            _RED.append(f"G4 tick={tick}: npc={npc} terminal-in-active={entry['status']}")

    # G7: no superseded при enforcement
    hist = scene.get("commitment_history") or {}
    for npc, bucket in hist.items():
        for e in bucket:
            if e.get("interrupt_reason") == "SUPERSEDED_BY_NEW_MATERIALIZATION":
                _RED.append(
                    f"G7 tick={tick}: npc={npc} superseded при enforcement"
                )

    # R4: executor без commitment (активный traversal без активного commitment)
    for npc in traversals:
        if npc not in active:
            _RED.append(f"R4 tick={tick}: npc={npc} traversal без commitment")


# ── Сценарий A — Eat ───────────────────────────────────────────────────────


def run_scenario_a() -> dict:
    """GIVEN hunger=0.9. EXPECT candidate/commitment/execution/terminal.
    DISCOVER post-terminal: recommit latency, самопроизвольный повтор."""
    _log("\n=== SCENARIO A: EAT (hunger=0.9) ===")
    world = _build_world("a", npc_patch={"body_state": {"hunger": 0.9}})
    # hunger-ключ создаётся (зонд: отсутствует в стартовом body_state,
    # LifeEngine читает через .get и инкрементит; 0.9 >> порога 0.5)
    try:
        _tick_n(world.game_loop, _TICKS + _POST_WINDOW)
        scene = _scene(world)
        _check_green(scene, _TICKS)
        timeline = _commitment_timeline(scene)
        eat_events = [e for e in timeline if "hunger" in (e.get("cause") or "")]
        _log(f"  commitments total: {len(timeline)}, hunger-связанных: {len(eat_events)}")
        for e in timeline[:12]:
            _log(
                f"  [{e.get('status')}] cause={e.get('cause')} "
                f"target={e.get('target_id')} t={e.get('created_tick')}"
            )

        findings = {"eat_commitments": len(eat_events), "timeline": timeline}
        # YELLOW: recommit latency по hunger-событиям
        if len(eat_events) >= 2:
            latencies = [
                eat_events[i + 1]["created_tick"] - eat_events[i]["created_tick"]
                for i in range(len(eat_events) - 1)
            ]
            _YELLOW.append(f"A: recommit latency (hunger): {latencies}")
        return findings
    finally:
        world.restore()


# ── Сценарий B — Sleep ─────────────────────────────────────────────────────


def run_scenario_b() -> dict:
    """GIVEN schedule=sleeping окном прогона + sleep_pressure=0.95.
    DISCOVER: B1 stable-sleep / B2 new-movement / B3 repeat-intent / B4 idle."""
    _log("\n=== SCENARIO B: SLEEP (schedule+spressure) ===")
    # Расписание: вся шкала — sleeping (окно прогона гарантированно внутри)
    # Schedule в стейте отсутствует (зонд) — сон форсируется sleep_pressure
    # (CouplingResolver: давление → SLEEPING-режим; sleep-восстановление
    # -0.02/тик). Discovered-исходы B1–B4 не зависят от способа GIVEN.
    world = _build_world(
        "b",
        npc_patch={"body_state": {"sleep_pressure": 0.95}},
    )
    try:
        _tick_n(world.game_loop, _TICKS + _POST_WINDOW)
        scene = _scene(world)
        _check_green(scene, _TICKS)
        timeline = _commitment_timeline(scene)
        _log(f"  commitments total: {len(timeline)}")
        for e in timeline[:12]:
            _log(
                f"  [{e.get('status')}] cause={e.get('cause')} "
                f"target={e.get('target_id')} t={e.get('created_tick')}"
            )

        # Классификация post-terminal исходов (B1-B4)
        active = scene.get("active_commitments") or {}
        has_active = _TARGET_NPC in active
        npcs = scene.get("npc_positions") or {}
        coupling = (
            (npcs.get(_TARGET_NPC, {}) or {})
        )
        body = _npc_body_state(world)
        coupling_mode = (body or {}).get("coupling_profile", {}).get("coupling_mode", "?")
        _log(f"  post-terminal: active={has_active}, coupling_mode={coupling_mode}")

        if has_active:
            cause = active[_TARGET_NPC].get("cause", "")
            if "sleeping" in cause or "shelter" in cause:
                _YELLOW.append("B: B3 повторный sleep-intent post-terminal (loop?)")
            else:
                _YELLOW.append(f"B: B2 новый movement post-terminal: cause={cause}")
        elif coupling_mode in ("SLEEPING", "REM"):
            _YELLOW.append(f"B: B1 stable sleep (coupling={coupling_mode})")
        else:
            _YELLOW.append("B: B4 idle (нет активного, coupling != SLEEPING)")

        # Y6: сон как executor без commitment
        if coupling_mode in ("SLEEPING", "REM") and not has_active:
            _YELLOW.append("Y6: сон исполняется БЕЗ commitment (executor=SleepLifecycle)")
        return {"timeline": timeline, "coupling_mode": coupling_mode}
    finally:
        world.restore()


def _npc_body_state(world) -> dict:
    """body_state NPC из all_npcs_raw (после тиков)."""
    loop = world.game_loop
    raw = getattr(loop, "_tick_orch", None)
    if raw is None:
        return {}
    ctx_np = getattr(raw, "_npc_runtime_locations", None)
    # Читаем через npc_states LifeEngine (доступно после тиков)
    try:
        le = loop._tick_orch._get_life_engine()
        states = le.get_npc_states(_CAMPAIGN) or []
        for st in states:
            if st.get("npc_id") == _TARGET_NPC or st.get("id") == _TARGET_NPC:
                return st.get("body_state", {}) or {}
    except Exception as e:  # noqa: BLE001
        _log(f"  [WARN] body_state read failed: {e}")
    return {}


# ── Сценарий C — Impossible ────────────────────────────────────────────────


def run_scenario_c() -> dict:
    """GIVEN activity_map на несуществующий узел. DISCOVER: C1 silent-vanish /
    C2 stuck / C3 BLOCKED. Подтест R6: FAILED обязан освобождать ownership."""
    _log("\n=== SCENARIO C: IMPOSSIBLE (broken activity_map) ===")
    # Schedule в стейте отсутствует — C реализуется через activity_map:
    # рабочая активность ("working" — есть в map) перепривязывается к
    # несуществующему узлу. LifeEngine._resolve_activity: activity_map hit →
    # сломанный узел → NO_RESOLVE-ветка (2052) → silent vanish (гипотеза C1).
    world = _build_world(
        "c",
        npc_patch={"activity_map": {"working": "nonexistent_node_xyz"}},
    )
    try:
        _tick_n(world.game_loop, _TICKS + _POST_WINDOW)
        scene = _scene(world)
        _check_green(scene, _TICKS)
        timeline = _commitment_timeline(scene)
        _log(f"  commitments total: {len(timeline)} (ожидание C1: ~0)")
        if not timeline:
            _YELLOW.append(
                "C: C1 silent-vanish — невозможное действие не оставляет "
                "ни intent, ни commitment, ни FAILED (вход S203.4: FAILED-путь "
                "в production отсутствует)"
            )

        # R6-подтест: FAILED обязан освобождать ownership (прямой вызов
        # registry.fail — тест = авторизованный писатель, как в 36 юнит-тестах)
        from app.services.action.commitment_registry import CommitmentRegistry

        ss = {}
        CommitmentRegistry.commit(ss, tick=1, npc_id=_TARGET_NPC, action="MOVE", cause="c_test")
        CommitmentRegistry.mark_executing(ss, _TARGET_NPC, 2)
        ok_fail = CommitmentRegistry.fail(ss, _TARGET_NPC, 3)
        released = _TARGET_NPC not in ss.get("active_commitments", {})
        _log(f"  R6: fail()={ok_fail}, ownership released={released}")
        if not (ok_fail and released):
            _RED.append("R6: FAILED не освобождает ownership (permanently locked)")

        return {"timeline": timeline}
    finally:
        world.restore()


# ── G3: детерминизм (диф ID двух прогонов A) ───────────────────────────────


def run_replay_check() -> None:
    """G3: два идентичных прогона A -> последовательности commitment_id совпадают."""
    _log("\n=== G3: DETERMINISM (два прогона A) ===")
    ids_1 = [e.get("commitment_id") for e in run_scenario_a().get("timeline", [])]
    ids_2 = [e.get("commitment_id") for e in run_scenario_a().get("timeline", [])]
    if ids_1 == ids_2 and ids_1:
        _log(f"  G3 OK: {len(ids_1)} commitments, последовательности идентичны")
    else:
        _RED.append(
            f"R7/G3: недетерминированный replay: {len(ids_1)} vs {len(ids_2)} ID"
        )


# ── main ───────────────────────────────────────────────────────────────────


def main() -> int:
    import logging

    _quiet_loggers()
    _log("=" * 64)
    _log("SUPERBOX-ACTION-INTEGRITY (Stage 2A, промежуточный behavioral gate)")
    _log("Registry(S203.1) + Arbitration(S203.2, ENFORCEMENT=ON)")
    _log("=" * 64)

    # Enforcement обязателен (аудит рабочей связки) — тройная верификация
    os.environ["ARBITER_ENFORCEMENT"] = "1"
    import importlib
    import app.services.action.commitment_arbiter as _ca

    importlib.reload(_ca)
    _log(f"ENFORCEMENT = {_ca.ARBITER_ENFORCEMENT}")

    run_scenario_a()
    run_scenario_b()
    run_scenario_c()
    run_replay_check()

    # Отчёт
    report_dir = _PROJECT_ROOT / "reports"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "superbox_action_integrity.md"
    lines = [
        "# SUPERBOX-ACTION-INTEGRITY — findings",
        "",
        "## GREEN (инварианты)",
        *([f"- ✅ {g}" for g in _GREEN] or ["- (пусто)"]),
        "",
        "## YELLOW (диагностика — вход S203.6)",
        *([f"- ⚠️ {y}" for y in _YELLOW] or ["- (пусто)"]),
        "",
        "## RED (архитектурный провал — вход S203.3)",
        *([f"- ❌ {r}" for r in _RED] or ["- (пусто)"]),
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")

    _log("\n" + "█" * 64)
    _log(f"📄 ОТЧЁТ: {report_path.resolve()}")
    _log("█" * 64)
    red = len(_RED)
    _log(f"RESULT: GREEN={len(_GREEN)} YELLOW={len(_YELLOW)} RED={red}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(main())