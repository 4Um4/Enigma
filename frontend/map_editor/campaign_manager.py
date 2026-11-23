"""
path: /frontend/map_editor/campaign_manager.py
Управление кампаниями: создание, открытие, сохранение
Кампания = папка campaigns/<name>/ с campaign.json и locations/*.json
Зависимости: data_manager, json, zipfile (для шага 13), pathlib, datetime, copy
Основные сущности: CampaignManager
"""

import copy
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from schema_validator import (
    _KEY_CREATED_AT,
    _KEY_DESCRIPTION,
    _KEY_MODIFIED_AT,
    _KEY_NAME,
    validate_campaign_meta,
)

CAMPAIGNS_DIR = Path(__file__).parent / "campaigns"
TEMPLATE_DIR = Path(__file__).parent / "location_templates"


class CampaignManager:
    """Управляет кампаниями — папками с набором локаций"""

    def __init__(self, dm):
        self.dm = dm
        self.current_campaign_name: Optional[str] = None
        self._campaign_dir: Optional[Path] = None  # полный путь к папке кампании
        self.campaign_data: Optional[dict] = None
        CAMPAIGNS_DIR.mkdir(exist_ok=True)

    @property
    def is_open(self) -> bool:
        return self._campaign_dir is not None

    @property
    def campaign_path(self) -> Optional[Path]:
        return self._campaign_dir

    def list_campaigns(self) -> List[dict]:
        """Возвращает список всех кампаний с метаданными"""
        result = []
        if not CAMPAIGNS_DIR.exists():
            return result
        for d in CAMPAIGNS_DIR.iterdir():
            if not d.is_dir():
                continue
            meta_file = d / "campaign.json"
            if not meta_file.exists():
                continue
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = validate_campaign_meta(json.load(f), str(meta_file))
                loc_dir = d / "locations"
                loc_count = len(list(loc_dir.glob("*.json"))) if loc_dir.exists() else 0
                result.append(
                    {
                        "name": data.get("name", d.name),
                        "folder": d.name,
                        "description": data.get("description", ""),
                        "location_count": loc_count,
                        "created_at": data.get("created_at", ""),
                        "modified_at": data.get("modified_at", ""),
                    }
                )
            except Exception:
                result.append(
                    {
                        "name": d.name,
                        "folder": d.name,
                        "description": "(ошибка чтения)",
                        "location_count": 0,
                        "created_at": "",
                        "modified_at": "",
                    }
                )
        return sorted(result, key=lambda x: x["name"])

    def create_campaign(self, folder_name: str, name: str, description: str = "") -> Tuple[bool, str]:
        """Создаёт новую кампанию с папкой и campaign.json"""
        safe = "".join(c if c.isalnum() or c in "_- " else "_" for c in folder_name).strip()
        if not safe:
            return False, "Пустое имя папки"
        campaign_dir = CAMPAIGNS_DIR / safe
        if campaign_dir.exists():
            return False, f"Папка '{safe}' уже существует"
        now = datetime.now().isoformat()
        campaign_dir.mkdir(parents=True)
        (campaign_dir / "locations").mkdir()
        # ME-1.6: auto-copy starter templates → new campaign locations (вердикт в.1: "автокопия")
        if TEMPLATE_DIR.exists():
            import shutil

            for tpl_file in TEMPLATE_DIR.glob("*.json"):
                shutil.copy2(tpl_file, campaign_dir / "locations" / tpl_file.name)
        meta = validate_campaign_meta(
            {
                _KEY_NAME: name[:70],
                _KEY_DESCRIPTION: description[:70],
                _KEY_CREATED_AT: now,
                _KEY_MODIFIED_AT: now,
            },
            str(campaign_dir / "campaign.json"),
        )
        with open(campaign_dir / "campaign.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        return True, ""

    def open_campaign(self, folder_name: str) -> Tuple[bool, str]:
        """Открывает кампанию из стандартной папки campaigns/"""
        campaign_dir = CAMPAIGNS_DIR / folder_name
        return self.open_campaign_from_path(campaign_dir)

    def open_campaign_from_path(self, campaign_dir: Path) -> Tuple[bool, str]:
        """Открывает кампанию по произвольному пути к папке с campaign.json"""
        campaign_dir = Path(campaign_dir)
        meta_file = campaign_dir / "campaign.json"
        if not campaign_dir.exists() or not meta_file.exists():
            return False, f"campaign.json не найден в {campaign_dir}"
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                self.campaign_data = validate_campaign_meta(json.load(f), str(meta_file))
        except Exception as e:
            return False, f"Ошибка чтения: {e}"
        self.current_campaign_name = campaign_dir.name
        self._campaign_dir = campaign_dir
        # Локации лежат рядом с campaign.json в подпапке locations/
        loc_dir = campaign_dir / "locations"
        if not loc_dir.exists():
            loc_dir.mkdir(exist_ok=True)
        self.dm.set_base_dir(loc_dir)
        return True, ""

    def close_campaign(self):
        """Закрывает кампанию, возвращает DataManager к шаблонам"""
        self.current_campaign_name = None
        self._campaign_dir = None
        self.campaign_data = None
        self.dm.set_base_dir(TEMPLATE_DIR)

    def save_location(self, filename: str):
        """Сохраняет указанную локацию в текущую кампанию.

        P3-01: возвращает SaveResult (bool-совместим). Успех означает только
        «файл записан»; состояние зеркал и реестра — предмет P4-01 (F-12).
        """
        result = self.dm.save(filename)
        if result:
            self._update_modified()
            self._sync_to_runtime()
        return result

    def save_all_locations(self):
        """Сохраняет все локации текущей кампании.

        P3-01 (F-5): SaveResult с count/failed; `_update_modified` только при
        реально записанных файлах — кампания не помечается сохранённой при 0.
        """
        try:
            from save_result import SaveResult
        except ImportError:
            from .save_result import SaveResult

        count = 0
        errors: List[str] = []
        failed: List[str] = []
        for fname in list(self.dm.locations.keys()):
            res = self.dm.save(fname)
            if res:
                count += 1
            else:
                failed.append(fname)
                errors.extend(res.errors)
        if count > 0:
            self._update_modified()
            self._sync_to_runtime()
        if failed:
            return SaveResult(ok=False, errors=errors, count=count, failed=failed)
        return SaveResult.success(count=count)

    def _sync_to_runtime(self) -> dict:
        """P4-01: Синхронизация с зеркалами (абсолютные пути, whitelist, mirror-delete).

        Возвращает: {"copied": int, "deleted": int, "failed": int, "errors": list[str]}
        """
        import logging
        logger = logging.getLogger(__name__)
        result = {"copied": 0, "deleted": 0, "failed": 0, "errors": []}

        if not self._campaign_dir or not self.current_campaign_name:
            return result

        campaign_name = self.current_campaign_name
        source_dir = self._campaign_dir / "locations"
        if not source_dir.exists():
            result["errors"].append(f"Source directory does not exist: {source_dir}")
            return result

        # 1. Абсолютный корень репозитория (не зависит от CWD)
        repo_root = Path(__file__).resolve().parents[2]
        abs_repo_root = repo_root.resolve()

        # 2. Белый список целей (строго относительно корня)
        target_paths = [
            repo_root / "saves" / campaign_name / "locations",
            repo_root / "build" / "staging" / "saves" / campaign_name / "locations",
            repo_root / "build" / "staging" / "frontend" / "map_editor" / "campaigns" / campaign_name / "locations",
        ]

        # Список файлов, которые ДОЛЖНЫ быть в зеркалах (только .json)
        source_files = {f.name for f in source_dir.glob("*.json")}

        for target_dir in target_paths:
            try:
                # 3. Проверка принадлежности и защита от выхода за корень / symlink
                abs_target = target_dir.resolve()
                if not abs_target.is_relative_to(abs_repo_root):
                    result["errors"].append(f"Target escapes repo root: {target_dir}")
                    continue
                if campaign_name not in abs_target.parts:
                    result["errors"].append(f"Target missing campaign name: {target_dir}")
                    continue

                abs_target.mkdir(parents=True, exist_ok=True)

                # 4. Mirror-delete: удаляем только .json, которых нет в source
                target_files = {f.name for f in abs_target.glob("*.json")}
                files_to_delete = target_files - source_files
                for fname in files_to_delete:
                    try:
                        (abs_target / fname).unlink()
                        result["deleted"] += 1
                    except Exception as e:
                        result["failed"] += 1
                        result["errors"].append(f"Delete failed {fname} in {target_dir}: {e}")

                # Предупреждение о посторонних файлах (не удаляем их, как требует D.3)
                for f in abs_target.iterdir():
                    if f.is_file() and f.suffix.lower() != ".json":
                        logger.warning(f"[EDITOR_SYNC] Non-JSON file ignored in mirror: {f.name}")

                # 5. Копирование/обновление
                # P4-02 (T26): copy2 открывает приёмник на запись и пишет СКВОЗЬ
                # symlink/hardlink, перезаписывая файл вне корня. Пишем во
                # временный файл и атомарно заменяем запись каталога — связь
                # с внешним inode рвётся, внешний файл не затрагивается.
                for fname in source_files:
                    src_file = source_dir / fname
                    tgt_file = abs_target / fname
                    tmp_file = abs_target / (fname + ".p402tmp")
                    try:
                        shutil.copy2(src_file, tmp_file)
                        tmp_file.replace(tgt_file)
                        result["copied"] += 1
                    except Exception as e:
                        result["failed"] += 1
                        result["errors"].append(f"Copy failed {fname} to {target_dir}: {e}")
                    finally:
                        if tmp_file.exists():
                            try:
                                tmp_file.unlink()
                            except OSError:
                                pass

            except Exception as e:
                result["errors"].append(f"Target processing failed {target_dir}: {e}")

        # 6. Пересборка реестра
        # P4-02 (T27): артефакт удаляется для форсирования пересборки, но при
        # отказе рабочий реестр ОБЯЗАН быть восстановлен — иначе потеря данных.
        artifact_path = self._campaign_dir / "compiled" / "spatial_registry.json"
        artifact_backup = None
        try:
            import sys
            frontend_dir = Path(__file__).parent.parent
            if str(frontend_dir) not in sys.path:
                sys.path.insert(0, str(frontend_dir))
            from spatial_compilation_orchestrator import SpatialCompilationOrchestrator

            if artifact_path.exists():
                artifact_backup = artifact_path.read_bytes()
                artifact_path.unlink()

            orch = SpatialCompilationOrchestrator()
            orch.rebuild_if_needed(campaign_name)
            logger.info(f"[EDITOR_SYNC] SpatialRegistry rebuilt for {campaign_name}")
        except Exception as e:
            result["errors"].append(f"Registry rebuild failed: {e}")
            logger.error(f"[EDITOR_SYNC] Failed to rebuild SpatialRegistry: {e}")
            if artifact_backup is not None:
                try:
                    artifact_path.parent.mkdir(parents=True, exist_ok=True)
                    artifact_path.write_bytes(artifact_backup)
                    logger.warning("[EDITOR_SYNC] Previous SpatialRegistry restored")
                except Exception as restore_err:
                    result["errors"].append(f"Registry restore failed: {restore_err}")
                    logger.error(f"[EDITOR_SYNC] Restore failed: {restore_err}")

        return result

    def save_location_as(self, source_filename: str, new_filename: str) -> Tuple[bool, str]:
        """Копирует локацию под новым именем в текущую кампанию"""
        if source_filename not in self.dm.locations:
            return False, "Исходный файл не найден"
        if not new_filename.endswith(".json"):
            new_filename += ".json"
        if new_filename in self.dm.locations:
            return False, "Файл уже существует"
        self.dm.locations[new_filename] = copy.deepcopy(self.dm.locations[source_filename])
        self.dm.locations[new_filename]["filename"] = new_filename
        res = self.dm.save(new_filename)
        if not res:
            # P3-01 (F-11, D-3): откат сироты — незаписанная локация не остаётся
            # в памяти и не исчезает «после перезапуска».
            self.dm.locations.pop(new_filename, None)
            return False, res.reason_text()
        self._update_modified()
        return True, ""

    def _update_modified(self):
        """Обновляет дату изменения в campaign.json"""
        if not self.campaign_path or not self.campaign_data:
            return
        meta_file = self.campaign_path / "campaign.json"
        if meta_file.exists():
            validate_campaign_meta(self.campaign_data, str(meta_file))
            self.campaign_data[_KEY_MODIFIED_AT] = datetime.now().isoformat()
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(self.campaign_data, f, indent=2, ensure_ascii=False)

    def export_to_zip(self, target_path: str) -> Tuple[bool, str]:
        """Упаковывает кампанию в zip-архив"""
        import zipfile

        if not self.campaign_path or not self.campaign_path.exists():
            return False, "Нет открытой кампании"
        try:
            with zipfile.ZipFile(target_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in self.campaign_path.rglob("*"):
                    if file_path.is_file():
                        arc_name = file_path.relative_to(self.campaign_path)
                        zf.write(file_path, arc_name)
            return True, ""
        except Exception as e:
            return False, f"Ошибка: {e}"

    def import_from_zip(self, zip_path: str, folder_name: str) -> Tuple[bool, str]:
        """Распаковывает zip-архив как новую кампанию"""
        import zipfile

        safe = "".join(c if c.isalnum() or c in "_- " else "_" for c in folder_name).strip()
        if not safe:
            return False, "Пустое имя папки"
        target_dir = CAMPAIGNS_DIR / safe
        if target_dir.exists():
            return False, f"Папка '{safe}' уже существует"
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(target_dir)
            # проверяем что campaign.json есть
            if not (target_dir / "campaign.json").exists():
                return False, "В архиве нет campaign.json"
            return True, ""
        except Exception as e:
            # убираем мусор если распаковка частичная
            if target_dir.exists():
                import shutil

                shutil.rmtree(target_dir, ignore_errors=True)
            return False, f"Ошибка: {e}"
