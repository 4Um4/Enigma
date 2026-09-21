"""
path: /project/backend/tests/sandbox/probes/scale_population.py
Назначение: генератор населения для лестницы SCALE (S272). Строит временную копию
кампании Open_road с N клонами особи-шаблона (goran.json) и записями в
npc_positions временной копии campaign_state.json. Живые данные не трогаются:
всё пишется в temp-каталог, которыйScaleInstrument подменяет после _setup().
Зависимости: json, shutil, pathlib (без app.* — чистый файловый инструмент)
Основные сущности: build_population, main
Запуск: cd backend; python tests/sandbox/probes/scale_population.py 12
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]  # backend/tests/sandbox/probes → repo root
_STATE_SRC = _REPO / "backend" / "data" / "campaigns" / "Open_road" / "campaign_state.json"
_NPC_SRC = _REPO / "config" / "npc"
_TEMPLATE = "goran.json"  # особь-шаблон: минимальный объём, merchant-архетип
_TEMPLATE_ID = "merchant_goran"


def build_population(target_npcs: int) -> Path:
    """Строит temp-дерево кампании с target_npcs NPC. Возвращает корень temp."""
    if target_npcs < 6:
        raise ValueError(f"target_npcs={target_npcs}: минимум 6 (baseline без клонов)")

    tmp = Path(tempfile.mkdtemp(prefix="scale_pop_"))

    # 1. state-копия: патч npc_positions
    state = json.loads(_STATE_SRC.read_text(encoding="utf-8"))
    positions = state["scene_state"]["npc_positions"]
    # эталон записи — первый реальный NPC (не player)
    _ref_name, ref_entry = next((k, v) for k, v in positions.items() if k != "player")
    base_x = ref_entry.get("local_position", {}).get("x", 0.0)
    base_y = ref_entry.get("local_position", {}).get("y", 0.0)

    # 2. особь-шаблон
    tmpl = json.loads((_NPC_SRC / "individuals" / _TEMPLATE).read_text(encoding="utf-8"))

    clone_count = target_npcs - 6
    for i in range(clone_count):
        nid = f"scale_npc_{i:02d}"
        # 2а. особь-клон: патч id/name, location — та же tavern
        ind = json.loads(json.dumps(tmpl))  # deep copy
        ind["id"] = nid
        ind["name"] = f"Scale-{i:02d}"
        ind["location"] = "tavern"
        # GROUND_TRUTH-валидатор требует авторитетное поле (ADR: location_id авторитетен)
        ind["location_id"] = "tavern"
        # клоны без каузальной истории: чистый масштабный эксперимент
        ind["origin_events"] = []
        (_NPC_SRC / "individuals").name  # noqa: B018 — якорь читаемости
        ind_dir = tmp / "npc" / "individuals"
        ind_dir.mkdir(parents=True, exist_ok=True)
        (ind_dir / f"{nid}.json").write_text(
            json.dumps(ind, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 2б. запись npc_positions: клон пространственной записи + детерминированный сдвиг
        entry = json.loads(json.dumps(ref_entry))
        entry["name"] = f"Scale-{i:02d}"
        lp = entry.get("local_position", {})
        lp["x"] = base_x + 0.5 * ((i % 6) + 1)  # сетка 6 колонок — расселение без коллизий
        lp["y"] = base_y + 0.5 * (i // 6)
        entry["local_position"] = lp
        positions[nid] = entry

    # 3. выгрузка state-копии
    camp_dir = tmp / "campaigns" / "Open_road"
    camp_dir.mkdir(parents=True, exist_ok=True)
    (camp_dir / "campaign_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # 4. архетипы/mixins/social — копируем как есть (загрузчик ожидает полную структуру)
    shutil.copytree(_NPC_SRC / "archetypes", tmp / "npc" / "archetypes")
    shutil.copytree(_NPC_SRC / "mixins", tmp / "npc" / "mixins")
    shutil.copytree(_NPC_SRC / "social", tmp / "npc" / "social")
    # 4б. ОРИГИНАЛЬНЫЕ особи — обязательно: load_npcs_merged читает ВСЕХ из
    # individuals/ (npc_loader:307); без них шестёрка теряет психику при redirect'е
    shutil.copytree(_NPC_SRC / "individuals", ind_dir, dirs_exist_ok=True)

    # 5. Само-верификация через живой загрузчик (прецедент _verify_through_loader, S213):
    # redirect → count → restore. Громкий ответ на вопрос «кого видит merge».
    from app.services.npc import npc_loader

    _orig_root = npc_loader._CONFIG_NPC_ROOT
    npc_loader._CONFIG_NPC_ROOT = tmp / "npc"
    try:
        _merged = npc_loader.load_npcs_merged()
        _ids = sorted(str(d.get("id", d.get("npc_id", "?"))) for d in _merged)
        _scale_seen = sum(1 for i in _ids if i.startswith("scale_npc_"))
        print(f"[SCALE_POP] LOADER SEES: {len(_merged)} npcs; scale-клонов: {_scale_seen}")
        if len(_merged) != target_npcs or _scale_seen != clone_count:
            raise RuntimeError(
                f"[SCALE_POP] верификация провалена: ожидано {target_npcs}, "
                f"видно {len(_merged)}; клонов ожидано {clone_count}, видно {_scale_seen}"
            )
    finally:
        npc_loader._CONFIG_NPC_ROOT = _orig_root

    print(f"[SCALE_POP] {clone_count} клонов создано → {tmp}")
    print(f"[SCALE_POP] население верифицировано загрузчиком: {target_npcs}")
    return tmp


def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python scale_population.py <target_npcs>")
        sys.exit(1)
    build_population(int(sys.argv[1]))


if __name__ == "__main__":
    main()