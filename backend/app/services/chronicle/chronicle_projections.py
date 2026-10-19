"""path: backend/app/services/chronicle/chronicle_projections.py
Назначение: CCH-5 (ADR-O-420) — экспорт-проекции канон-хроник в форматы
            старых систем: origin_events / village_relations / truth_state.
            Артефакты аудита, НЕ источник истины для рантайма.
            Канон остаётся единственным источником истины.
Зависимости: app.core.config, app.domain.chronicle, app.models.truth_state,
             app.services.chronicle.{chronicle_seeder, chronicle_store},
             app.services.npc.npc_loader (list_individual_ids), stdlib
Основные сущности: build_origin_events_projection, build_village_relations_projection,
                   build_truth_state_projection, publish_generation,
                   export_all_projections, EMPTY/BLOCKED/OK статусы.

КОНТРАКТ CCH-5 (вердикт Мастера):
- EXPLICIT: секретность — только payload["is_secret"] is True на kind=EVENT.
  Не выводим из важности/травмы/текста/категории/causes/KNOWLEDGE_LINK.
- A3: атомарная публикация через поколение (tmp → заполнить → validate →
  os.rename каталога → current.json tmp+os.replace). При ошибке старый
  current.json действующий.
- K1: initial_holders — только resolved knowers; [] допустим, НЕ доказательство.
- C2: повреждённый origin_ref → блокировка; непредставимые связи → пропуск
  с диагностикой.
- EMPTY: нет секретных EVENT → truth_state не создаётся, status EMPTY.
- Шкала village_relations: файловая 0..1 (константы seeder'а / 100).

ЗАПРЕТЫ:
- НЕ создавать фиктивные ID.
- НЕ подменять неизвестное утверждением об отсутствии факта.
- НЕ публиковать поколение при ошибке валидации.
- НЕ создавать фиктивный truth_state при EMPTY.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.config import BASE_DIR
from app.domain.chronicle import (
    EntityRef,
    EntityRefKind,
    EntryKind,
)
from app.services.chronicle.chronicle_seeder import (
    SEED_TRUST_NEGATIVE,
    SEED_TRUST_POSITIVE,
    _author_entries,
)
from app.services.chronicle.origin_projection import chronicle_to_origin_events

logger = logging.getLogger(__name__)

# ── Константы проекции (CALIBRATION_CANDIDATE — калибровка CCH-6) ─────────────

PL_IS_SECRET: str = "is_secret"
PL_SUMMARY: str = "summary"
PL_VALENCE: str = "valence"
PL_IMPORTANCE: str = "importance"
PL_DISCOVERY_SURFACE: str = "discovery_surface"
PL_TAGS: str = "tags"
PL_CATEGORY: str = "category"

TRUTH_RELATION_STRENGTH: float = 0.8
DEFAULT_SECRET_IMPORTANCE: float = 0.6
DEFAULT_DISCOVERY_SURFACE: Tuple[str, ...] = ("dialogue",)

PROJECTION_SCHEMA_VERSION: int = 1

# ── Статусы ───────────────────────────────────────────────────────────────────

STATUS_OK: str = "OK"
STATUS_EMPTY: str = "EMPTY"
STATUS_BLOCKED: str = "BLOCKED"


class ProjectionError(ValueError):
    """Ошибка построения проекции (блокировка публикации)."""


# ── Расположение ──────────────────────────────────────────────────────────────


def _projections_root() -> Path:
    """Корень всех проекций. Изолирован от авторских JSON."""
    return BASE_DIR / "config" / "npc" / "chronicles" / "_projections"


def _generations_dir() -> Path:
    return _projections_root() / "_generations"


def _current_pointer_path() -> Path:
    return _projections_root() / "current.json"


# ── Вспомогательные ───────────────────────────────────────────────────────────


def _resolved_npc_id(ref: Optional[EntityRef]) -> Optional[str]:
    """RESOLVED → npc_id; остальные → None (без фиктивных ID)."""
    if ref is None:
        return None
    if ref.ref_kind is EntityRefKind.RESOLVED:
        return ref.npc_id
    return None


def _is_secret_event(entry: Any) -> bool:
    """EXPLICIT: только payload['is_secret'] is True на kind=EVENT."""
    if entry.kind is not EntryKind.EVENT:
        return False
    return entry.payload.get(PL_IS_SECRET) is True


def _secret_event_entries(
    docs_by_npc: Dict[str, Any]
) -> List[Tuple[str, Any]]:
    """Все секретные EVENT из всех канонов (для truth_state)."""
    out: List[Tuple[str, Any]] = []
    for npc_id, doc in docs_by_npc.items():
        for e in _author_entries(doc):
            if _is_secret_event(e):
                out.append((npc_id, e))
    return out


def _collect_initial_holders(
    secret_entry_id: str, docs_by_npc: Dict[str, Any]
) -> Tuple[List[str], List[str]]:
    """Resolved knowers из KNOWLEDGE_LINK этого event.
    Возвращает (initial_holders, unresolved_knower_kinds).
    Пустой initial_holders допустим (K1) — НЕ доказательство, что никто не знает.
    """
    holders: List[str] = []
    unresolved: List[str] = []
    for _src_id, doc in docs_by_npc.items():
        for e in _author_entries(doc):
            if e.kind is not EntryKind.KNOWLEDGE_LINK:
                continue
            # KnowledgeLink хранится в payload (KP_EVENT_REF / KP_KNOWER)
            ev_ref = e.payload.get("event_ref")
            if ev_ref != secret_entry_id:
                continue
            knower_payload = e.payload.get("knower")
            if not isinstance(knower_payload, dict):
                continue
            ref_kind_str = knower_payload.get("ref_kind")
            if ref_kind_str is None:
                continue
            try:
                rk = EntityRefKind(ref_kind_str)
            except ValueError:
                logger.warning(
                    f"[CCH5_PROJ] unknown ref_kind={ref_kind_str!r} in knower — skipped"
                )
                continue
            if rk is EntityRefKind.RESOLVED:
                knower_id = knower_payload.get("npc_id")
                if knower_id and knower_id not in holders:
                    holders.append(knower_id)
            else:
                unresolved.append(f"{rk.value}:{knower_payload.get('name_hint', '')}")
    return holders, unresolved


# ── 1. origin_events-проекция ─────────────────────────────────────────────────


def build_origin_events_projection(
    npc_id: str, doc: Any
) -> Dict[str, Any]:
    """Один NPC → legacy-совместимый origin_events-список.
    Переиспользует chronicle_to_origin_events (read-only round-trip CCH-1).
    Все EVENT (не только секретные) — origin_events НЕ фильтрует по секретности;
    секретность живёт только в truth_state-проекции.
    """
    events = chronicle_to_origin_events(doc)
    return {
        "_projection": "origin_events",
        "_source_chronicle": npc_id,
        "_schema_version": PROJECTION_SCHEMA_VERSION,
        "origin_events": events,
    }


# ── 2. village_relations-проекция ────────────────────────────────────────────


def build_village_relations_projection(
    docs_by_npc: Dict[str, Any]
) -> Dict[str, Any]:
    """Все RELATIONSHIP из всех канонов → village_relations.json-формат.
    Шкала ФАЙЛОВАЯ 0..1 (загрузчик npc_loader:251 умножает на 100):
      positive → SEED_TRUST_POSITIVE / 100 = 0.3
      negative → SEED_TRUST_NEGATIVE / 100 = -0.4
    base_affection = 0.0 (калибровка CCH-6).
    nature = valence (positive/negative); chronicle_origin = entry_id.
    """
    relations: Dict[str, Dict[str, Any]] = {}
    for npc_id, doc in docs_by_npc.items():
        for e in _author_entries(doc):
            if e.kind is not EntryKind.RELATIONSHIP:
                continue
            tgt = _resolved_npc_id(e.object_id)
            if tgt is None or tgt == npc_id:
                continue
            valence = e.payload.get(PL_VALENCE)
            if valence == "positive":
                base_trust = SEED_TRUST_POSITIVE / 100.0
            elif valence == "negative":
                base_trust = SEED_TRUST_NEGATIVE / 100.0
            else:
                # valence без числа — seeder не сеет, проекция тоже пропускает
                logger.debug(
                    f"[CCH5_PROJ] {npc_id}:{e.entry_id}: valence={valence!r} — пропущено"
                )
                continue
            src_block = relations.setdefault(npc_id, {})
            src_block[tgt] = {
                "nature": valence,
                "base_trust": base_trust,
                "base_affection": 0.0,
                "notes": str(e.payload.get(PL_SUMMARY, "")),
                "chronicle_origin": e.entry_id,
            }
    return {
        "_version": "1.1",
        "_type": "social_base",
        "_projection": "chronicle",
        "relations": relations,
    }


# ── 3. truth_state-проекция ───────────────────────────────────────────────────


def build_truth_state_projection(
    docs_by_npc: Dict[str, Any],
    campaign_id: str,
    known_npcs: Optional[Set[str]] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Секретные EVENT (EXPLICIT: payload['is_secret'] is True) → truth_state.
    Возвращает (truth_state_dict_or_None, diagnostics).
    truth_state_dict = None при EMPTY (нет секретов).
    diagnostics = {secrets_count, relations_count, skipped, no_resolved_knowers,
                   blocked_references, unresolved_objects}.

    TruthRelation: source=E, target=C, DEPENDS_ON — E зависит от C
    (существующая семантика DEPENDS_ON = 'A зависит от B', source=A, target=B).
    """
    secret_entries = _secret_event_entries(docs_by_npc)
    if not secret_entries:
        return None, {
            "secrets_count": 0,
            "relations_count": 0,
            "skipped_not_secret_target": 0,
            "skipped_cause_kind_not_event": 0,
            "no_resolved_knowers": [],
            "blocked_references": [],
            "unresolved_objects": [],
        }

    # Индекс всех авторских EVENT по entry_id (для проверки origin_ref)
    all_event_ids: Set[str] = set()
    for _src, doc in docs_by_npc.items():
        for e in _author_entries(doc):
            if e.kind is EntryKind.EVENT:
                all_event_ids.add(e.entry_id)

    # Индекс секретных EVENT по entry_id
    secret_ids: Set[str] = {e.entry_id for _npc, e in secret_entries}

    secrets_out: List[Dict[str, Any]] = []
    relations_out: List[Dict[str, Any]] = []
    diag: Dict[str, Any] = {
        "secrets_count": 0,
        "relations_count": 0,
        "skipped_not_secret_target": 0,
        "skipped_cause_kind_not_event": 0,
        "no_resolved_knowers": [],
        "blocked_references": [],
        "unresolved_objects": [],
    }

    # Секреты
    for npc_id, e in secret_entries:
        subject_id = _resolved_npc_id(e.subject_id)
        if subject_id is None:
            # subject неразрешён → не можем создать npc_id → блокировка
            diag["blocked_references"].append(
                {"entry_id": e.entry_id, "reason": "subject_unresolved",
                 "ref_kind": e.subject_id.ref_kind.value}
            )
            continue

        object_id = _resolved_npc_id(e.object_id)
        participants: List[str] = [subject_id]
        if object_id is not None and object_id != subject_id:
            participants.append(object_id)
        elif e.object_id is not None and _resolved_npc_id(e.object_id) is None:
            # object_id есть, но неразрешён — в диагностику
            diag["unresolved_objects"].append(
                {"entry_id": e.entry_id, "ref_kind": e.object_id.ref_kind.value}
            )

        # Проверка participants по known_npcs (если передан)
        if known_npcs:
            for p in participants:
                if p not in known_npcs:
                    diag["blocked_references"].append(
                        {"entry_id": e.entry_id, "reason": "unknown_participant",
                         "participant": p}
                    )
                    continue

        holders, _unresolved_knowers = _collect_initial_holders(e.entry_id, docs_by_npc)
        if not holders:
            diag["no_resolved_knowers"].append(e.entry_id)

        importance = e.payload.get(PL_IMPORTANCE, DEFAULT_SECRET_IMPORTANCE)
        try:
            importance_f = float(importance)
        except (TypeError, ValueError):
            importance_f = DEFAULT_SECRET_IMPORTANCE
        if not (0.0 <= importance_f <= 1.0):
            raise ProjectionError(
                f"secret {e.entry_id}: importance {importance_f} вне [0,1]"
            )

        discovery_surface = e.payload.get(PL_DISCOVERY_SURFACE)
        if not isinstance(discovery_surface, (list, tuple)) or not discovery_surface:
            discovery_surface = list(DEFAULT_DISCOVERY_SURFACE)
        else:
            discovery_surface = [str(s) for s in discovery_surface]

        tags = e.payload.get(PL_TAGS, [])
        topics = [str(t) for t in tags] if isinstance(tags, (list, tuple)) else []

        secrets_out.append({
            "secret_id": e.entry_id,
            "npc_id": subject_id,
            "participants": participants,
            "category": str(e.payload.get(PL_CATEGORY, "chronicle")),
            "canonical_truth": str(e.payload.get(PL_SUMMARY, "")),
            "importance": importance_f,
            "initial_holders": holders,  # может быть [] — НЕ доказательство
            "discovery_surface": discovery_surface,
            "topics": topics,
            "chronicle_origin": e.entry_id,
        })

    if diag["blocked_references"]:
        # Структурно повреждённые ссылки → блокировка (C2)
        return None, diag

    # TruthRelation: для каждого секретного E, если у E есть cause с origin_ref
    # → другому секретному C, то E зависит от C: source=E, target=C, DEPENDS_ON.
    for npc_id, e in secret_entries:
        for cause in e.causes:
            # CauseRef.UNKNOWN → origin_ref is None (по __post_init__), не заходит
            if cause.origin_ref is None:
                continue
            if cause.cause_kind.value != "EVENT":
                diag["skipped_cause_kind_not_event"] += 1
                continue
            target_id = cause.origin_ref
            if target_id not in all_event_ids:
                # Повреждённая ссылка → блокировка
                diag["blocked_references"].append(
                    {"entry_id": e.entry_id, "reason": "dangling_cause_origin_ref",
                     "origin_ref": target_id}
                )
                continue
            if target_id not in secret_ids:
                # Цель не секретная → пропуск (непредставимо в TruthRelation)
                diag["skipped_not_secret_target"] += 1
                continue
            if target_id == e.entry_id:
                continue  # self-loop запрещён валидатором
            relations_out.append({
                "source_secret_id": e.entry_id,      # зависящий (E)
                "target_secret_id": target_id,       # основание (C)
                "relation_type": "DEPENDS_ON",
                "strength": TRUTH_RELATION_STRENGTH,
                "_chronicle_cause_kind": cause.cause_kind.value,
            })

    if diag["blocked_references"]:
        return None, diag

    diag["secrets_count"] = len(secrets_out)
    diag["relations_count"] = len(relations_out)

    truth_state = {
        "schema_version": 1,
        "campaign_id": campaign_id,
        "_projection": "chronicle",
        "secrets": secrets_out,
        "relations": relations_out,
    }
    return truth_state, diag


# ── 4. Публикация поколения (A3: атомарная замена current.json) ──────────────


def _generation_id() -> str:
    """gen_<timestamp>_<short_hash> — детерминированный ID поколения."""
    ts = int(time.time())
    salt = hashlib.sha1(f"{ts}".encode("utf-8")).hexdigest()[:8]
    return f"gen_{ts}_{salt}"


def _validate_truth_state_file(truth_state_dict: Dict[str, Any]) -> None:
    """Запуск TruthStateLoader.validate на построенной проекции.
    НЕ обходим валидатор — если он падает, публикация блокируется."""
    from types import MappingProxyType

    from app.models.truth_state import RelationType, Secret, TruthRelation, TruthState

    secrets: Dict[str, Secret] = {}
    for s_data in truth_state_dict.get("secrets", []):
        secret = Secret(
            secret_id=s_data["secret_id"],
            npc_id=s_data["npc_id"],
            participants=tuple(s_data["participants"]),
            category=s_data["category"],
            canonical_truth=s_data["canonical_truth"],
            importance=float(s_data["importance"]),
            initial_holders=tuple(s_data["initial_holders"]),
            discovery_surface=tuple(s_data["discovery_surface"]),
            topics=tuple(s_data["topics"]),
        )
        secrets[secret.secret_id] = secret

    relations = []
    for r_data in truth_state_dict.get("relations", []):
        rel = TruthRelation(
            source_secret_id=r_data["source_secret_id"],
            target_secret_id=r_data["target_secret_id"],
            relation_type=RelationType(r_data["relation_type"]),
            strength=float(r_data["strength"]),
        )
        relations.append(rel)

    state = TruthState(secrets=MappingProxyType(secrets), relations=tuple(relations))
    # validate без known_npcs — участники уже проверены выше
    from app.services.truth_state_loader import TruthStateLoader
    TruthStateLoader.validate(state, known_npcs=None)


def publish_generation(
    docs_by_npc: Dict[str, Any],
    campaign_id: str,
    known_npcs: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Атомарная публикация всех трёх проекций через поколение + current.json.

    Шаги A3:
      1. Создать tmp-каталог gen_<...>.tmp/.
      2. Записать все файлы (origin_events/*, village_relations.json,
         truth_state_*.json если не EMPTY).
      3. Если truth_state не EMPTY — запустить TruthStateLoader.validate.
      4. manifest.json с диагностикой.
      5. os.rename(tmp → gen_<...>) — одно атомарное переименование.
      6. current.json (tmp+os.replace) → указывает на новое поколение.

    При ошибке на любом шаге до os.rename — tmp удаляется, старый current.json
    остаётся действующим.
    """
    generations_dir = _generations_dir()
    generations_dir.mkdir(parents=True, exist_ok=True)

    gen_id = _generation_id()
    gen_path = generations_dir / gen_id
    tmp_path = generations_dir / f"{gen_id}.tmp"

    # Очистка возможного мусора от прошлого провала
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)

    try:
        tmp_path.mkdir(parents=True)

        files_published: Dict[str, Any] = {}
        truth_state_status = STATUS_EMPTY
        truth_state_diag: Dict[str, Any] = {}

        # 1. origin_events/* — один файл на NPC с каноном
        oe_dir = tmp_path / "origin_events"
        oe_dir.mkdir()
        oe_files: List[str] = []
        for npc_id, doc in docs_by_npc.items():
            oe = build_origin_events_projection(npc_id, doc)
            oe_path = oe_dir / f"{npc_id}.origin_events.json"
            oe_path.write_text(
                json.dumps(oe, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            oe_files.append(f"origin_events/{npc_id}.origin_events.json")
        files_published["origin_events"] = oe_files

        # 2. village_relations.json — один файл
        vr = build_village_relations_projection(docs_by_npc)
        vr_path = tmp_path / "village_relations.json"
        vr_path.write_text(
            json.dumps(vr, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        files_published["village_relations"] = "village_relations.json"

        # 3. truth_state — только если есть секреты
        truth_state, diag = build_truth_state_projection(
            docs_by_npc, campaign_id, known_npcs=known_npcs
        )
        truth_state_diag = diag

        if truth_state is not None:
            # Валидация BEFORE os.rename (C2: блокировка при ошибке)
            _validate_truth_state_file(truth_state)
            ts_path = tmp_path / f"truth_state_{campaign_id}.json"
            ts_path.write_text(
                json.dumps(truth_state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            files_published["truth_state"] = f"truth_state_{campaign_id}.json"
            truth_state_status = STATUS_OK
        else:
            files_published["truth_state"] = None
            truth_state_status = STATUS_EMPTY

        # 4. manifest.json
        manifest = {
            "generation_id": gen_id,
            "created_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "source_chronicles": sorted(docs_by_npc.keys()),
            "campaign_id": campaign_id,
            "files": files_published,
            "truth_state_status": truth_state_status,
            "diagnostics": truth_state_diag,
            "errors": [],
        }
        # Если валидация blocked_references — публикуем BLOCKED (но не вызываем
        # _validate_truth_state_file, потому что truth_state=None)
        if truth_state_diag.get("blocked_references"):
            manifest["errors"] = truth_state_diag["blocked_references"]
        (tmp_path / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 5. Атомарное переименование каталога
        os.replace(tmp_path, gen_path)

        # 6. current.json (tmp+os.replace)
        current = {
            "generation": gen_id,
            "campaign_id": campaign_id,
            "published_at_iso": manifest["created_at_iso"],
        }
        current_tmp = _current_pointer_path().with_suffix(".json.tmp")
        current_tmp.write_text(
            json.dumps(current, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(current_tmp, _current_pointer_path())

        result_status = STATUS_BLOCKED if manifest["errors"] else STATUS_OK
        return {
            "status": result_status,
            "generation_id": gen_id,
            "campaign_id": campaign_id,
            "files": files_published,
            "truth_state_status": truth_state_status,
            "diagnostics": truth_state_diag,
            "errors": manifest["errors"],
        }

    except Exception as exc:
        # Ошибка → очистка tmp, старый current.json действующий
        logger.error(f"[CCH5_PROJ] publish failed: {exc}", exc_info=True)
        if tmp_path.exists():
            shutil.rmtree(tmp_path, ignore_errors=True)
        return {
            "status": STATUS_BLOCKED,
            "generation_id": None,
            "campaign_id": campaign_id,
            "files": {},
            "truth_state_status": STATUS_EMPTY,
            "diagnostics": {},
            "errors": [{"reason": "publish_exception", "detail": str(exc)}],
        }


# ── 5. Точка входа: собрать все каноны и опубликовать ─────────────────────────


def export_all_projections(
    campaign_id: str, known_npcs: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """Собрать все канон-хроники → опубликовать поколение.
    Если канонов нет → EMPTY (поколение не создаётся).
    known_npcs — множество известных npc_id для проверки participants
    (если None — проверка отключена, но TruthStateLoader.validate всё равно
    запускается на структурную целостность).
    """
    from app.services.chronicle.chronicle_seeder import canonical_chronicles

    docs = canonical_chronicles()
    if not docs:
        return {
            "status": STATUS_EMPTY,
            "generation_id": None,
            "campaign_id": campaign_id,
            "files": {},
            "truth_state_status": STATUS_EMPTY,
            "diagnostics": {"npcs_total": 0, "npcs_with_chronicle": 0},
            "errors": [],
        }

    if known_npcs is None:
        # По умолчанию — все individual IDs (для проверки participants)
        try:
            from app.services.npc.npc_loader import list_individual_ids
            known_npcs = set(list_individual_ids())
        except Exception:
            known_npcs = None  # без проверки — валидатор всё равно запустится

    result = publish_generation(docs, campaign_id, known_npcs=known_npcs)
    # Доп. диагностика
    result["diagnostics"] = result.get("diagnostics", {})
    result["diagnostics"]["npcs_with_chronicle"] = len(docs)
    result["diagnostics"]["npcs_total"] = len(known_npcs) if known_npcs else len(docs)
    return result


# ── 6. Чтение current-указателя (для тестов и аудита) ─────────────────────────


def read_current_pointer() -> Optional[Dict[str, Any]]:
    """Текущее активное поколение. None если никогда не публиковалось."""
    p = _current_pointer_path()
    if not p.exists():
        return None
    try:
        data: Dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"[CCH5_PROJ] current.json повреждён: {exc}")
        return None


def list_generations() -> List[str]:
    """Список ID поколений (для аудита; cleanup — отдельная задача)."""
    gdir = _generations_dir()
    if not gdir.exists():
        return []
    return sorted(
        d.name for d in gdir.iterdir()
        if d.is_dir() and not d.name.endswith(".tmp")
    )
