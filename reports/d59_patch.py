from __future__ import annotations

# reports/d59_patch.py
"""
Одноразовый патч COV-D59 (Шаг 2 COV-1; ADR-O-426; вердикты Мастера В1-В8):
К3 lifecycle «детект-и-мигрировать» + честный отказ (В3/В7);
К4a routes version-aware ридер; К4b SSM no-port fallback ×2 (В4);
К5 save_scene_at: drop легаси-ключа + штамп версии; schemas: load_refusal_reason.
Гейты якорей до записи; line-ending-агностик (LF/CRLF рабочей копии).
После исполнения и коммита НЕ перезапускать.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = {
    "lifecycle": ROOT / "backend/app/services/game_loop/campaign_lifecycle.py",
    "routes": ROOT / "backend/app/api/routes.py",
    "ssm": ROOT / "backend/app/services/scene_state_manager.py",
    "adapter": ROOT / "backend/app/services/state/json_persistence_adapter.py",
    "schemas": ROOT / "backend/app/models/schemas.py",
}


def _abort(msg: str) -> None:
    print(f"[ABORT] {msg}")
    print("[ABORT] Стоп ДО записи: файлы не изменены.")
    sys.exit(1)


def _load(p: Path) -> tuple[str, bool]:
    raw = p.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig" if bom else "utf-8"), bom


def _save(p: Path, text: str, bom: bool) -> None:
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))


def _m(text: str, s: str) -> str:
    """Якорь/вставка под line-ending живого файла."""
    return s.replace("\n", "\r\n") if "\r\n" in text else s


def _sub(text: str, old: str, new: str, label: str, expect: int = 1) -> str:
    o, n = _m(text, old), _m(text, new)
    if text.count(o) != expect:
        _abort(f"{label}: якорь найден {text.count(o)} раз (ожидался {expect})")
    if text.count(n) != 0:
        _abort(f"{label}: СТАЛО уже присутствует (идемпотентность)")
    print(f"[OK] {label} (x{expect})")
    return text.replace(o, n)


LIFECYCLE_DEPS_OLD = "Зависимости: app.models.world_state_diff (лениво), app.services.state.world_diff_applicator (лениво), app.services.state.save_format_detector (лениво), app.models.schemas.CampaignLoadResponse"
LIFECYCLE_DEPS_NEW = "Зависимости: app.models.world_state_diff (лениво), app.services.state.world_diff_applicator (лениво), app.services.state.save_format_detector (лениво; inventory), app.services.state.save_migrations (детект-и-мигрировать, COV-D59), app.models.schemas.CampaignLoadResponse"

LIFECYCLE_OLD = """        # Дополнение Б (п. Б.12): Детектор старых сейвов
        try:
            from app.services.state.save_format_detector import detect_legacy_saves
            _legacy_campaigns = detect_legacy_saves(self._saves_dir)
            if campaign_id in _legacy_campaigns:
                logger.warning(f"[SAVE_MIGRATION] Обнаружен сейв старого формата для кампании '{campaign_id}'. Удаление...")
                _old_save_file = self._saves_dir / campaign_id / "campaign_state.json"
                if _old_save_file.exists():
                    _old_save_file.unlink()
        except Exception as _migr_err:
            logger.error(f"[SAVE_MIGRATION] Ошибка при удалении старого сейва: {_migr_err}")"""

LIFECYCLE_NEW = """        # COV-D59 / ADR-O-426 Шаг 2 (вердикты Мастера В1-В8): «детект-и-
        # удалить» заменён на «детект-и-мигрировать». Удаление сейва запрещено:
        # MIGRABLE -> верифицированная конвертация (.pre-migration.bak, В6);
        # UNMIGRABLE -> честный отказ, файл не тронут (В3/В7).
        from app.services.state.save_migrations import (
            STATUS_MIGRATED,
            STATUS_REFUSED,
            migrate_save_file_if_needed,
        )

        _migration = migrate_save_file_if_needed(
            self._saves_dir / campaign_id / "campaign_state.json"
        )
        if _migration.status == STATUS_REFUSED:
            # В7: машинно различимый отказ; событие campaign_loaded не пишем —
            # загрузки не было (история кампании не лжёт).
            logger.error(
                f"[SAVE_MIGRATION] Отказ загрузки '{campaign_id}': {_migration.reason}"
            )
            self.memory_manager.persist_campaign_event(
                campaign_id,
                event="campaign_load_refused",
                world_id=world_id,
                data={"reason": _migration.reason},
            )
            return CampaignLoadResponse(
                campaign_id=campaign_id,
                world_id=world_id,
                status=STATUS_REFUSED,
                loaded_files=[],
                load_refusal_reason=_migration.refusal_text,
            )
        if _migration.status == STATUS_MIGRATED:
            loaded = {"status": STATUS_MIGRATED, "files": {}}"""

ROUTES_OLD = """                cs = json.loads(cs_path.read_text(encoding="utf-8-sig"))
                current_location = cs.get("scene_state", {}).get(
                    "location_id"
                ) or cs.get("metadata", {}).get("current_location")"""

ROUTES_NEW = """                cs = json.loads(cs_path.read_text(encoding="utf-8-sig"))
                # COV-D59 (В4): version-aware читатель — v1 scenes-layout и
                # легаси v0 единым правилом; fallback metadata.current_location
                # (SSOT локации, routes:1053).
                from app.services.state.save_migrations import resolve_current_location

                current_location = resolve_current_location(cs)"""

SSM_OLD = """        else:
            data = self._read_campaign_json(campaign_id)
            scene = data.get("scene_state")"""

SSM_NEW = """        else:
            # COV-D59 (В4): version-aware no-port fallback — v1 scenes-layout и
            # легаси v0 единым правилом (мёртвый путь обязан быть корректным).
            from app.services.state.save_migrations import extract_scene_payload

            data = self._read_campaign_json(campaign_id)
            scene = extract_scene_payload(data, location_id or None)"""

ADAPTER_IMPORT_OLD = "from app.services.state.persistence_port import PersistencePort"
ADAPTER_IMPORT_NEW = """from app.services.state.persistence_port import PersistencePort
from app.services.state.save_format_detector import SAVE_SCHEMA_VERSION"""

ADAPTER_BODY_OLD = """            if "scenes" not in data:
                data["scenes"] = {}

            data["scenes"][location_id] = scene_state"""

ADAPTER_BODY_NEW = """            if "scenes" not in data:
                data["scenes"] = {}

            # ADR-O-426 (COV-D59): писатель — авторитет формата: каждый
            # write-path штампует версию (безверсионные файлы не плодятся);
            # остаток легаси-ключа scene_state (stale по определению) убираем —
            # штамп поверх легаси-ключа давал бы INCONSISTENT_V1.
            data.pop("scene_state", None)
            data["scenes"][location_id] = scene_state
            data["schema_version"] = SAVE_SCHEMA_VERSION"""

SCHEMAS_OLD = """class CampaignLoadResponse(BaseModel):
    campaign_id: str
    world_id: str
    status: str
    loaded_files: List[str]"""

SCHEMAS_NEW = """class CampaignLoadResponse(BaseModel):
    campaign_id: str
    world_id: str
    status: str
    loaded_files: List[str]
    # ADR-O-426 Шаг 2 (COV-D59, вердикт В7): None = загрузка/миграция успешны;
    # текст = машинно различимый честный отказ (исходник сохранён).
    load_refusal_reason: str | None = None"""


def main() -> None:
    print("[D59] Патч К3/К4a/К4b/К5/schemas.")

    t, bom = _load(P["lifecycle"])
    t = _sub(t, LIFECYCLE_DEPS_OLD, LIFECYCLE_DEPS_NEW, "К3-докстринг зависимости")
    t = _sub(t, LIFECYCLE_OLD, LIFECYCLE_NEW, "К3 load_campaign: детект-и-мигрировать")
    _save(P["lifecycle"], t, bom)

    t, bom = _load(P["routes"])
    t = _sub(t, ROUTES_OLD, ROUTES_NEW, "К4a routes: version-aware ридер")
    _save(P["routes"], t, bom)

    t, bom = _load(P["ssm"])
    t = _sub(t, SSM_OLD, SSM_NEW, "К4b SSM no-port fallback", expect=2)
    _save(P["ssm"], t, bom)

    t, bom = _load(P["adapter"])
    t = _sub(t, ADAPTER_IMPORT_OLD, ADAPTER_IMPORT_NEW, "К5 import")
    t = _sub(t, ADAPTER_BODY_OLD, ADAPTER_BODY_NEW, "К5 save_scene_at: штамп + drop")
    _save(P["adapter"], t, bom)

    t, bom = _load(P["schemas"])
    t = _sub(t, SCHEMAS_OLD, SCHEMAS_NEW, "schemas: load_refusal_reason (В7)")
    _save(P["schemas"], t, bom)

    print("[OK] Патч применён: 5 файлов, 7 правок.")


if __name__ == "__main__":
    main()
