"""
path: /project/backend/app/services/social/relationship_state_store.py
Назначение: RelationshipStateStore — SSOT-субстрат Relationship Engine (фаза B / M1a;
    ТЗ-RE-01 v1.9 §4.1/§5.1; ADR-O-370). Статический сервис над
    scene_state["relationship_state"] (прецедент: CommitmentRegistry /
    TraversalExecutionSystem — «статический сервис над scene_state»).
    КРАСНЫЙ ИНВАРИАНТ M1a (вердикт Мастера): стор создаёт МЕСТО ХРАНЕНИЯ, но не
    механизм изменения. Persistence lifecycle стору НЕ принадлежит: запись на
    диск — только через существующий atomic_commit_all (Foundation Freeze);
    собственные файловые пути запрещены (в отличие от старого RelationshipStore
    из svc/memory — его disk-on-update — зона M1b, здесь не трогается).
    Поверхность записи M1a — ровно один метод (apply_need_deltas); в рантайме
    его никто не вызывает (писатели — фазы M2/D и G/H): поведение тика
    байтово идентично до подключения.
    WRITE-КОНТРАКТ (вердикт Мастера): StateApplicator → RelationshipStateStore →
    scene_state["relationship_state"]; mutate-метод защищён caller-guard'ом по
    образцу NPCState._ALLOWED_WRITERS: чужой модуль → ArchitecturalViolationError
    (второй writer = DOUBLE TRUTH, запрет №5 ТЗ-RE-01). Расширение allowlist —
    только через ADR.
    READ-КОНТРАКТ (вердикт Мастера): read-методы (1) НЕ возвращают внутренний
    mutable dict — только frozen DTO в свежих коллекциях (alias-мутация через
    get_* исключена по построению); (2) НЕ мутируют scene_state — никакого
    lazy-init на чтении (чистота совместима с Pure Reducer фазы 5); отсутствующий
    ключ = легитимные дефолты (старые сейвы совместимы); повреждённая структура
    (не-dict на месте словаря) = громкий ContractValidationError — молчаливая
    маскировка повреждённых данных дефолтами запрещена (DOUBLE TRUTH).
    Записи создаются лениво, ТОЛЬКО на write-пути. Неизвестные need_id в сейве
    (форвард-совместимость) — сохраняются, но не читаются (реестр-управляемое
    чтение). Стохастики нет — KernelRNG (№14) станет актуален только с
    динамикой G+. Кампания-специфичность наследуется от самого scene_state.
Зависимости: app.domain.relationship_contracts (чистый домен), app.errors.
Основные сущности: RelationshipStateStore.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, Final, FrozenSet

from app.domain.relationship_contracts import (
    RE_NEED_SLOTS,
    ContractValidationError,
    ExclusivityRequirement,
    HardConstraint,
    NeedLevel,
    PreferenceModel,
    exclusivity_requirement_from_dict,
    hard_constraint_from_dict,
    need_level_from_dict,
    need_level_to_dict,
    preference_from_dict,
)
from app.errors import ArchitecturalViolationError

# ═══ Ключи scene_state — КОНСТАНТЫ (Устав §12.1: inline-строки в адаптерах запрещены) ═══

_KEY_ROOT: Final[str] = "relationship_state"
_KEY_NEEDS: Final[str] = "needs"
_KEY_PREFERENCES: Final[str] = "preferences"
_KEY_CONSTRAINTS: Final[str] = "constraints"
_KEY_EXCLUSIVITY: Final[str] = "exclusivity"

# ── M1b.1 (ADR-O-371): константы legacy-формата и v2-поддерева directed ──
_KEY_DIRECTED: Final[str] = "directed"  # v2-поддерево 5 скаляров (M1b)
_LEGACY_FILENAME: Final[str] = "npc_relationships.json"
_MIGRATED_SUFFIX: Final[str] = ".migrated"
_LEGACY_SCALARS: Final[tuple] = ("trust", "fear", "debt", "respect", "attraction")

# ═══ Caller-guard: единственный writer-маршрут (вердикт Мастера) ═══
# Мутация scene_state[_KEY_ROOT] разрешена ТОЛЬКО из этих модулей.
# Расширение списка = отдельный ADR (второй writer = DOUBLE TRUTH, запрет №5).

_ALLOWED_WRITER_MODULES: Final[FrozenSet[str]] = frozenset(
    {
        "app.services.social.relationship_state_store",  # собственные методы стора
        "app.services.npc.state_applicator",  # единственный runtime-writer (M1a: update_needs)
    }
)


def _require_dict(value: Any, where: str) -> Dict[str, Any]:
    """Гарантия структуры: повреждённые данные (не-dict) — громкий отказ, не дефолт."""
    if not isinstance(value, dict):
        raise ContractValidationError(
            f"{where}: повреждён ({type(value).__name__}, ожидается dict) — "
            f"маскировка дефолтом = DOUBLE TRUTH, запрещена"
        )
    return value


def _clamp01(value: float) -> float:
    """Clamp аккумулятора в [0,1] (инвариант диапазона NeedLevel)."""
    return max(0.0, min(1.0, value))


class RelationshipStateStore:
    """SSOT-субстрат RE над scene_state.

    Прямая dict-хирургия scene_state["relationship_state"] извне стора =
    ArchitecturalViolation. SSM может лишь бутстрапнуть ПУСТОЙ корневой ключ
    (прецедент active_commitments); заполнение — только через этот стор.
    """

    # ── READ: чистые проекции (без мутации scene_state; наружу — frozen DTO) ──

    @staticmethod
    def _read_subtree(scene_state: Dict[str, Any], subkey: str) -> Dict[str, Any]:
        """Чтение subtree (needs/preferences/constraints/exclusivity):
        отсутствует → {} (легитимный дефолт); повреждён → громкий отказ."""
        root = scene_state.get(_KEY_ROOT)
        if root is None:
            return {}
        root = _require_dict(root, f"scene_state['{_KEY_ROOT}']")
        subtree = root.get(subkey)
        if subtree is None:
            return {}
        return _require_dict(subtree, f"scene_state['{_KEY_ROOT}']['{subkey}']")

    @staticmethod
    def get_need_levels(scene_state: Dict[str, Any], npc_id: str) -> Dict[str, NeedLevel]:
        """Все потребности NPC → свежий Dict[need_id, NeedLevel(frozen)].

        Реестр-управляемое чтение: ровно ключи RE_NEED_SLOTS (M1a: sexual,
        intimacy); отсутствующие записи → нулевые аккумуляторы (давление
        растёт динамикой G+, не чтением). scene_state не мутируется.
        """
        if not npc_id:
            raise ContractValidationError("get_need_levels: npc_id пуст")
        npc_needs = RelationshipStateStore._read_subtree(scene_state, _KEY_NEEDS).get(npc_id)
        if npc_needs is None:
            npc_needs = {}
        else:
            npc_needs = _require_dict(npc_needs, f"needs[{npc_id}]")
        result: Dict[str, NeedLevel] = {}
        for need_id in RE_NEED_SLOTS:
            raw = npc_needs.get(need_id)
            result[need_id] = (
                NeedLevel(need_id=need_id) if raw is None else need_level_from_dict(raw)
            )
        return result

    @staticmethod
    def get_need_level(scene_state: Dict[str, Any], npc_id: str, need_id: str) -> NeedLevel:
        """Одна потребность NPC → NeedLevel(frozen). Отсутствие → нулевой дефолт."""
        if need_id not in RE_NEED_SLOTS:
            raise ContractValidationError(
                f"get_need_level: need_id '{need_id}' вне закрытого реестра M1a"
            )
        return RelationshipStateStore.get_need_levels(scene_state, npc_id)[need_id]

    @staticmethod
    def get_preferences(scene_state: Dict[str, Any], npc_id: str) -> Dict[str, PreferenceModel]:
        """Предпочтения NPC → свежий Dict[pref_id, PreferenceModel(frozen)].

        Закрытого реестра pref_id нет (§5.1): честное отсутствие → {}.
        Писатели предпочтений — будущие фазы (обучение §6.17); в M1a пусто.
        """
        if not npc_id:
            raise ContractValidationError("get_preferences: npc_id пуст")
        npc_prefs = RelationshipStateStore._read_subtree(scene_state, _KEY_PREFERENCES).get(npc_id)
        if npc_prefs is None:
            return {}
        npc_prefs = _require_dict(npc_prefs, f"preferences[{npc_id}]")
        return {pid: preference_from_dict(raw) for pid, raw in npc_prefs.items()}

    @staticmethod
    def get_constraints(scene_state: Dict[str, Any], npc_id: str) -> Dict[str, HardConstraint]:
        """Жёсткие ограничения NPC → свежий Dict[constraint_id, HardConstraint(frozen)].

        Отсутствие → {} (честное отсутствие; применение — фазы K/L).
        """
        if not npc_id:
            raise ContractValidationError("get_constraints: npc_id пуст")
        npc_cons = RelationshipStateStore._read_subtree(scene_state, _KEY_CONSTRAINTS).get(npc_id)
        if npc_cons is None:
            return {}
        npc_cons = _require_dict(npc_cons, f"constraints[{npc_id}]")
        return {cid: hard_constraint_from_dict(raw) for cid, raw in npc_cons.items()}

    @staticmethod
    def get_exclusivity(
        scene_state: Dict[str, Any], npc_id: str, target_id: str
    ) -> ExclusivityRequirement:
        """Направленная норма эксклюзивности npc_id → target_id (вердикт №3).

        Отсутствие → дефолт scope="none" (направленный, НЕ парный: пары нет).
        Писатели — переговоры (M2+, §8.1 negotiation_*); в M1a — только чтение.
        """
        if not npc_id or not target_id:
            raise ContractValidationError("get_exclusivity: npc_id/target_id пуст")
        npc_excl = RelationshipStateStore._read_subtree(scene_state, _KEY_EXCLUSIVITY).get(npc_id)
        if npc_excl is None:
            return ExclusivityRequirement()
        npc_excl = _require_dict(npc_excl, f"exclusivity[{npc_id}]")
        raw = npc_excl.get(target_id)
        if raw is None:
            return ExclusivityRequirement()
        return exclusivity_requirement_from_dict(raw)

    # ── WRITE: единственный mutate-метод M1a (caller-guard → StateApplicator) ──

    @staticmethod
    def apply_need_deltas(
        scene_state: Dict[str, Any],
        npc_id: str,
        need_id: str,
        pressure_delta: float = 0.0,
        satiation_delta: float = 0.0,
        frustration_delta: float = 0.0,
    ) -> NeedLevel:
        """Применить дельты к аккумуляторам NeedLevel (clamp [0,1]) и вернуть НОВЫЙ
        frozen NeedLevel. Внутренние dict наружу не отдаются.

        Порядок операций: caller-guard → валидация входа → ленивая инициализация
        записи → read-modify-write через immutable контракт. Guard срабатывает
        ДО любой мутации scene_state. Вызывающий в M1a — только
        StateApplicator.update_needs (Шаг 3); сам метод в рантайме не вызывается.
        """
        # 1) Caller-guard: единственный writer-маршрут (вердикт Мастера, ADR-O-370)
        caller = sys._getframe(1).f_globals.get("__name__", "")
        if caller not in _ALLOWED_WRITER_MODULES:
            raise ArchitecturalViolationError(
                f"apply_need_deltas({npc_id}, {need_id})", caller
            )
        # 2) Валидация входа (до мутации)
        if not npc_id:
            raise ContractValidationError("apply_need_deltas: npc_id пуст")
        if need_id not in RE_NEED_SLOTS:
            raise ContractValidationError(
                f"apply_need_deltas: need_id '{need_id}' вне закрытого реестра M1a "
                f"{{sexual, intimacy}} — новая потребность только через вердикт GPT "
                f"+ ADR (запрет №17)"
            )
        deltas: Dict[str, float] = {}
        for name, value in (
            ("pressure_delta", pressure_delta),
            ("satiation_delta", satiation_delta),
            ("frustration_delta", frustration_delta),
        ):
            try:
                d = float(value)
            except (TypeError, ValueError) as e:
                raise ContractValidationError(
                    f"apply_need_deltas.{name}: не число: {value!r}"
                ) from e
            if d != d:  # NaN
                raise ContractValidationError(f"apply_need_deltas.{name}: NaN запрещён")
            deltas[name] = d
        # 3) Ленивая инициализация (единственный путь, мутирующий scene_state)
        root = scene_state.get(_KEY_ROOT)
        if root is None:
            root = {}
            scene_state[_KEY_ROOT] = root
        root = _require_dict(root, f"scene_state['{_KEY_ROOT}']")
        needs_root = root.get(_KEY_NEEDS)
        if needs_root is None:
            needs_root = {}
            root[_KEY_NEEDS] = needs_root
        needs_root = _require_dict(needs_root, f"scene_state['{_KEY_ROOT}']['{_KEY_NEEDS}']")
        npc_needs = needs_root.get(npc_id)
        if npc_needs is None:
            npc_needs = {}
            needs_root[npc_id] = npc_needs
        npc_needs = _require_dict(npc_needs, f"needs[{npc_id}]")
        # 4) Read-modify-write через immutable контракт (тройная семантика §5.1:
        #    давление / сатурация / фрустрация — раздельные аккумуляторы, №20/№21/№23)
        raw = npc_needs.get(need_id)
        current = NeedLevel(need_id=need_id) if raw is None else need_level_from_dict(raw)
        updated = NeedLevel(
            need_id=need_id,
            current_intensity=_clamp01(current.current_intensity + deltas["pressure_delta"]),
            satiation=_clamp01(current.satiation + deltas["satiation_delta"]),
            frustration=_clamp01(current.frustration + deltas["frustration_delta"]),
        )
        npc_needs[need_id] = need_level_to_dict(updated)
        return updated

    # ── M1b.1: MIGRATION ADAPTER (ADR-O-371; ТЗ-RE-01 §8.6 M1 — режим «Заменить») ──
    # Контракт (вердикт Мастера): legacy JSON → deterministic transform → v2 scene_state.
    # Перенос БЕЗ пересчёта: никакой headroom-сатурации, никакого округления — сырые
    # значения как лежат (D3: migration не преобразует поведение; round(4) остаётся
    # read-контрактом get_pair, не миграцией). Идемпотентность: маркер .migrated
    # рядом с legacy-файлом; повторный вызов при живом маркере = no-op (второго
    # импорта не существует). Cutover НЕ входит в M1b.1: legacy runtime нетронут,
    # writers/readers не переключаются, cache не трогается.

    @staticmethod
    def migrate_legacy_relationships(
        scene_state: Dict[str, Any],
        campaign_id: str,
        data_dir: str,
    ) -> Dict[str, int]:
        """Однократный перенос npc_relationships.json → scene_state["relationship_state"]["directed"].

        Возвращает отчёт {"migrated_pairs": N, "skipped": bool} — наблюдаемость
        без молчания (L4). Детерминизм: одинаковый JSON → одинаковое поддерево
        (никакого wall-clock/RNG в transform). Vacuum сохраняется: пара,
        отсутствующая в JSON, НЕ материализуется нулями (§ENIGMA-003).

        Идемпотентность по построению: (а) живой .migrated → no-op; (б) даже без
        маркера повторный перенос перезаписывает те же ключи теми же значениями
        (transform — чистая функция от файла), но маркер отсекает повторное
        чтение диска — контракт «.migrated не создаёт второй импорт».
        """
        import json
        import os

        if not campaign_id:
            raise ContractValidationError("migrate_legacy: campaign_id пуст")
        # (а) Сначала ВСЕ skip-пути — без мутации scene_state: скип обязан быть
        # чистым no-op (поймано собственным тестом marker_prevents_second_import:
        # прежний setdefault-до-скипа создавал пустой корень даже при «skipped»).
        legacy_path = os.path.join(data_dir, campaign_id, _LEGACY_FILENAME)
        migrated_path = legacy_path + _MIGRATED_SUFFIX
        if os.path.exists(migrated_path):
            return {"migrated_pairs": 0, "skipped": True}
        if not os.path.exists(legacy_path):
            # Нет legacy-данных — не ошибка (новые кампании), маркер не ставим:
            # файл может появиться позже в старой сессии до cutover.
            return {"migrated_pairs": 0, "skipped": True}
        root = scene_state.setdefault(_KEY_ROOT, {})
        if not isinstance(root, dict):
            raise ContractValidationError(f"scene_state['{_KEY_ROOT}']: повреждён")
        # (б) Чтение legacy (REAL формат: {"src→tgt": {scalar: num, ...}})
        try:
            with open(legacy_path, "r", encoding="utf-8-sig") as f:
                legacy_data = json.load(f)
        except (OSError, ValueError) as e:
            raise ContractValidationError(
                f"migrate_legacy: повреждённый {legacy_path}: {e}"
            ) from e
        if not isinstance(legacy_data, dict):
            raise ContractValidationError(
                f"migrate_legacy: {legacy_path} — не dict ({type(legacy_data).__name__})"
            )
        # (в) Deterministic transform: сырые числа как лежат — БЕЗ сатурации/round
        directed: Dict[str, Dict[str, float]] = {}
        for pair_key, raw in legacy_data.items():
            if not isinstance(pair_key, str) or "→" not in pair_key or not isinstance(raw, dict):
                # Повреждённая запись — громкий отказ всего переноса (не тихий скип):
                # частичная миграция хуже отсутствия (двойная поверхность)
                raise ContractValidationError(
                    f"migrate_legacy: повреждённая пара '{pair_key}' в {legacy_path}"
                )
            entry: Dict[str, float] = {}
            for attr, val in raw.items():
                if attr not in _LEGACY_SCALARS:
                    continue  # посторонние ключи legacy — не переносим, не падаем
                try:
                    entry[attr] = float(val)
                except (TypeError, ValueError) as e:
                    raise ContractValidationError(
                        f"migrate_legacy: '{pair_key}'.{attr} не число: {val!r}"
                    ) from e
            if entry:
                directed[pair_key] = entry
        # (г) Запись в v2 (существующее поддерево directed не затираем — merge:
        # миграция добавляет legacy-пары, v2-пары приоритетнее (созданы позже))
        existing = root.get(_KEY_DIRECTED)
        if existing is None:
            existing = {}
            root[_KEY_DIRECTED] = existing
        if not isinstance(existing, dict):
            raise ContractValidationError(f"relationship_state.{_KEY_DIRECTED}: повреждён")
        for k, v in directed.items():
            existing.setdefault(k, v)  # merge: v2-пара уже есть → legacy не перезаписывает
        # (д) Маркер: повторного импорта не существует. Сам legacy-файл НЕ удаляем
        # (до cutover legacy runtime продолжает его читать — M1b.1 его не трогает).
        try:
            with open(migrated_path, "w", encoding="utf-8") as f:
                f.write("migrated\n")
        except OSError as e:
            raise ContractValidationError(
                f"migrate_legacy: не могу записать маркер {migrated_path}: {e}"
            ) from e
        return {"migrated_pairs": len(directed), "skipped": False}

    @staticmethod
    def get_directed_pair(
        scene_state: Dict[str, Any], source: str, target: str
    ) -> Dict[str, float]:
        """READ v2 (M1b): направленная пара source→target; Vacuum = {} (нет записи —
        нет знания, §ENIGMA-003); round(4) — read-контракт, унаследован от legacy
        get_pair (D3: точность — контракт персистентности/чтения)."""
        if not source or not target:
            return {}
        root = scene_state.get(_KEY_ROOT)
        if root is None:
            return {}
        root = _require_dict(root, f"scene_state['{_KEY_ROOT}']")
        directed = root.get(_KEY_DIRECTED)
        if directed is None:
            return {}
        directed = _require_dict(directed, f"relationship_state.{_KEY_DIRECTED}")
        raw = directed.get(f"{source}→{target}")
        if raw is None:
            return {}  # Vacuum: не материализуем 0.0 из пустоты
        raw = _require_dict(raw, f"directed[{source}→{target}]")
        return {
            attr: round(float(val), 4)
            for attr, val in raw.items()
            if attr in _LEGACY_SCALARS
        }
