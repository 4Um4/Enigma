"""
path: backend/app/services/calibration/preset_materializer.py
Назначение: Материализация пресета лаборатории калибровки (ADR-O-361):
    временная копия config/npc → патч individuals-JSON (npc_overrides:
    wildcard "*" первым, точечный npc_id перекрывает) → редирект
    npc_loader._CONFIG_NPC_ROOT на копию → поведенческая верификация
    РЕАЛЬНЫМ загрузчиком. Мутация NPCState запрещена — только данные
    загрузки (per-NPC параметры — не константы).
    Редирект — ПРЯМОЕ присваивание единственного канонического биндинга
    (S208, фикс двух красных прогонов: entry-side identity-скан по
    Path-объектам хрупок и не нужен — A4-археология показала отсутствие
    внешних from-import биндингов _CONFIG_NPC_ROOT; потребитель читает
    module-global в момент вызова). Обратный скан по temp-корню сохранён
    как защита late-импортёров.
Зависимости: app.services.npc.npc_loader, app.services.calibration.preset_io.
Основные сущности: MaterializationError, MaterializedNpcConfig,
    materialize_preset (context manager).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import types
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Set, Tuple

from app.services.calibration.preset_io import NpcOverride, Preset
from app.services.npc import npc_loader

# Вложенность = неопределённое состояние единственного корня config/npc
# (симметрия запрету вложенных overlay, ADR-O-361).
_ACTIVE = False


class MaterializationError(RuntimeError):
    """Громкий отказ материализации (L4): нет config/npc, NPC из
    npc_overrides не найден в кампании, загрузчик не видит патч,
    биндинги не восстановлены."""


@dataclass(frozen=True)
class MaterializedNpcConfig:
    """Результат материализации. Жизненным циклом (restore/cleanup)
    владеет context manager — DTO только факт."""

    temp_root: Path
    patched_npc_ids: Tuple[str, ...]
    files_patched: int


def _verify(condition: bool, message: str) -> None:
    if not condition:
        raise MaterializationError(message)


def _identity_bindings(target: object) -> List[Tuple[types.ModuleType, str]]:
    """Все (модуль, атрибут) в sys.modules, чьё значение — ТОТ ЖЕ объект.

    Используется ТОЛЬКО в обратном направлении (temp → original):
    чинит late-импортёров, связавших temp через from-import во время
    эксперимента. Прямой редирект делает присваивание, не скан.
    """
    found: List[Tuple[types.ModuleType, str]] = []
    for module in list(sys.modules.values()):
        if not isinstance(module, types.ModuleType):
            continue
        for attr_name, value in list(vars(module).items()):
            if value is target:
                found.append((module, attr_name))
    return found


def _effective_override(
    npc_id: Optional[str], preset: Preset
) -> Optional[NpcOverride]:
    """Единственный источник семантики приоритетов оверрайдов:
    wildcard "*" применяется первым, точечный npc_id перекрывает
    (psyche — по-ключевое слияние, drives — точечный целиком, иначе
    wildcard). Используется И патчером, И верификатором — расхождение
    их семантик невозможно by construction (S208: тест
    test_specific_npc_overrides_wildcard поймал расхождение —
    верификатор требовал wildcard-значение у точечно перекрытого NPC)."""
    wildcard = preset.npc_overrides.get("*")
    specific = preset.npc_overrides.get(npc_id) if npc_id else None
    if wildcard is None and specific is None:
        return None
    if wildcard is None:
        return specific
    if specific is None:
        return wildcard
    return NpcOverride(
        psyche={**wildcard.psyche, **specific.psyche},
        drives=specific.drives if specific.drives is not None else wildcard.drives,
    )


def _patch_individuals(temp_root: Path, preset: Preset) -> Tuple[Set[str], int]:
    """Патчит individuals/*.json копии. Wildcard первым, точечный
    npc_id перекрывает (последний wins в dict.update)."""
    patched_ids: Set[str] = set()
    files_patched = 0
    individuals_dir = temp_root / "individuals"
    for json_file in sorted(individuals_dir.glob("*.json")):
        data = json.loads(json_file.read_text(encoding="utf-8"))
        npc_id = data.get("id")
        override = _effective_override(npc_id, preset)
        if override is None:
            continue
        if override.psyche:
            psyche = data.setdefault("psyche", {})
            _verify(
                isinstance(psyche, dict),
                f"{json_file.name}: psyche не является отображением",
            )
            psyche.update(override.psyche)
        if override.drives is not None:
            # Замена ЦЕЛИКОМ: частичная сломала бы sum=1.0
            # (полнота и сумма валидированы в preset_io).
            data["drives"] = dict(override.drives)
        json_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        files_patched += 1
        if npc_id is not None:
            patched_ids.add(npc_id)
    return patched_ids, files_patched


def _verify_through_loader(preset: Preset) -> None:
    """Поведенческая верификация: реальный загрузчик возвращает патч.

    Ловит: неверный редирект, stale-биндинги, тень архетипа в цепочке
    наследования. Это главный предохранитель — механика редиректа
    доказывается поведением, а не предположением о ней.
    """
    npcs = npc_loader.load_npcs_merged(runtime_path=None)
    _verify(bool(npcs), "верификация: загрузчик вернул пустой список NPC")
    by_id = {n.get("id"): n for n in npcs}
    # 1) Точечные npc_overrides обязаны существовать в кампании.
    for npc_key in preset.npc_overrides:
        if npc_key == "*":
            continue
        _verify(
            by_id.get(npc_key) is not None,
            f"npc_overrides: NPC {npc_key!r} не найден в кампании "
            f"(доступные: {sorted(i for i in by_id if i)})",
        )
    # 2) Каждый NPC — против ЭФФЕКТИВНОГО оверрайда (тот же резолвер,
    # что и у патчера: точечный перекрывает wildcard).
    for npc in npcs:
        override = _effective_override(npc.get("id"), preset)
        if override is None:
            continue
        psyche = npc.get("psyche") or {}
        for key, expected in override.psyche.items():
            _verify(
                psyche.get(key) == expected,
                f"верификация: {npc.get('id')}.psyche.{key}: ожидалось "
                f"{expected!r}, получено {psyche.get(key)!r}",
            )
        if override.drives is not None:
            _verify(
                npc.get("drives") == override.drives,
                f"верификация: {npc.get('id')}.drives не совпадают "
                f"(ожидалось {override.drives!r}, получено {npc.get('drives')!r})",
            )


def _restore(original_root: Path, temp_root: Path) -> None:
    """Восстановление: (1) прямой возврат канонического биндинга;
    (2) обратный identity-скан по temp — late-импортёры. Идемпотентен:
    повторный вызов — no-op (прямое присваивание + пустой скан)."""
    npc_loader._CONFIG_NPC_ROOT = original_root
    for module, attr_name in _identity_bindings(temp_root):
        setattr(module, attr_name, original_root)
    remaining = _identity_bindings(temp_root)
    if remaining:
        broken = [f"{m.__name__}.{a}" for m, a in remaining]
        raise MaterializationError(
            f"восстановление config/npc неполное, temp держат: {broken}"
        )


@contextmanager
def materialize_preset(
    preset: Preset,
    *,
    base_npc_root: Optional[Path] = None,
) -> Iterator[MaterializedNpcConfig]:
    """Материализует npc_overrides пресета во временной копии config/npc.

    base_npc_root: источник копии (по умолчанию — текущий
    npc_loader._CONFIG_NPC_ROOT; чтение в момент вызова).
    """
    global _ACTIVE
    if _ACTIVE:
        raise MaterializationError(
            "Вложенная материализация запрещена (ADR-O-361): корень "
            "config/npc единственный; одновременные эксперименты — "
            "только изоляция процессами."
        )
    # БЕЗ Path()-обёртки: не строим корректность на identity-семантике
    # Path (S208, два красных прогона).
    original_root = npc_loader._CONFIG_NPC_ROOT
    base_root = Path(base_npc_root) if base_npc_root is not None else original_root
    _verify(base_root.is_dir(), f"config/npc не найден: {base_root}")
    _verify(
        (base_root / "individuals").is_dir(),
        f"каталог individuals не найден: {base_root / 'individuals'}",
    )

    temp_root = Path(tempfile.mkdtemp(prefix="calib_npc_"))
    _ACTIVE = True
    try:
        try:
            shutil.copytree(base_root, temp_root, dirs_exist_ok=True)
            patched_ids, files_patched = _patch_individuals(temp_root, preset)

            # Редирект: прямое присваивание единственного канонического
            # биндинга (A4: внешних from-import биндингов нет; чтение —
            # в момент вызова).
            npc_loader._CONFIG_NPC_ROOT = temp_root
            try:
                _verify_through_loader(preset)
            except BaseException:
                _restore(original_root, temp_root)
                raise

            yield MaterializedNpcConfig(
                temp_root=temp_root,
                patched_npc_ids=tuple(sorted(patched_ids)),
                files_patched=files_patched,
            )
        finally:
            # Ошибка restore не должна глотать исключение тела:
            # original re-raise, restore-failure — cause.
            _body_exc = sys.exc_info()[1]
            try:
                _restore(original_root, temp_root)
            except Exception as restore_exc:
                if _body_exc is None:
                    raise
                raise restore_exc from _body_exc
            finally:
                # Утечка temp-каталога недопустима даже при отказе restore.
                shutil.rmtree(temp_root, ignore_errors=True)
    finally:
        _ACTIVE = False