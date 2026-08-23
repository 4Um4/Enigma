# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/traversal_liveness_probe.py
Назначение: Одноразовый зонд v2 (ANOMALY S203.1): где теряется реестр между
    материализацией traversal и чтением get_scene_state.
    Дифференцирует: H-K (persistence селективно теряет новые ключи) /
    H-M (применение мимо SSM-ветки — dual rail) / H-I (get_scene_state
    читает persistence вместо RAM-кэша _tick_scenes).
    Проверяет три источника после одного тика:
      1) RAM-кэш SSM (_tick_scenes) — живой dict;
      2) get_scene_state — тот, кем читает production/зонд;
      3) повторный тик — если реестр теряется на round-trip, T2 снова пуст.
Зависимости: tests.sandbox.SUPERBOX.drift_laboratory
Основные сущности: main
"""


def _report(tag: str, scene: dict) -> None:
    travs = scene.get("active_traversals") or {}
    reg = scene.get("active_commitments") or {}
    hist = scene.get("commitment_history") or {}
    ordn = scene.get("commitment_ordinals") or {}
    print(
        f"  [{tag}] tick={scene.get('tick')} travs={sorted(travs)} "
        f"registry={sorted(reg)} history={len(hist)} ordinals={len(ordn)}"
    )


def main() -> None:
    from tests.sandbox.SUPERBOX.drift_laboratory import DriftConfig, DriftLaboratory

    lab = DriftLaboratory(DriftConfig())
    lab._setup()
    try:
        print("=== TICK 1 ===")
        lab._run_idle_tick_direct()

        # Источник 1: RAM-кэш SSM (живой dict, куда пишет apply_change)
        tick_scenes = getattr(lab._scene_manager, "_tick_scenes", None)
        if tick_scenes is None:
            print("  [RAM] _tick_scenes отсутствует (атрибут не найден)")
        else:
            for loc, sc in tick_scenes.items():
                if isinstance(sc, dict):
                    _report(f"RAM:{loc}", sc)

        # Источник 2: get_scene_state (путь production-чтения)
        ss = (
            lab._scene_manager.get_scene_state(
                lab.config.campaign_id, lab.config.location_id
            )
            or {}
        )
        _report("GET", ss)

        print("=== TICK 2 (round-trip проверка: реестр выживает между тиками?) ===")
        lab._run_idle_tick_direct()
        ss = (
            lab._scene_manager.get_scene_state(
                lab.config.campaign_id, lab.config.location_id
            )
            or {}
        )
        _report("GET", ss)
        for loc, sc in (tick_scenes or {}).items():
            if isinstance(sc, dict):
                _report(f"RAM:{loc}", sc)
    finally:
        lab._teardown()


if __name__ == "__main__":
    main()