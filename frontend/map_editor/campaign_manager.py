"""
path: /frontend/map_editor/campaign_manager.py
Управление кампаниями: создание, открытие, сохранение
Кампания = папка campaigns/<name>/ с campaign.json и locations/*.json
Зависимости: data_manager, json, zipfile (для шага 13), pathlib, datetime, copy
Основные сущности: CampaignManager
"""
import json
import copy
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple

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
                    data = json.load(f)
                loc_dir = d / "locations"
                loc_count = len(list(loc_dir.glob("*.json"))) if loc_dir.exists() else 0
                result.append({
                    "name": data.get("name", d.name),
                    "folder": d.name,
                    "description": data.get("description", ""),
                    "location_count": loc_count,
                    "created_at": data.get("created_at", ""),
                    "modified_at": data.get("modified_at", ""),
                })
            except Exception:
                result.append({
                    "name": d.name, "folder": d.name,
                    "description": "(ошибка чтения)", "location_count": 0,
                    "created_at": "", "modified_at": "",
                })
        return sorted(result, key=lambda x: x["name"])

    def create_campaign(self, folder_name: str, name: str,
                        description: str = "") -> Tuple[bool, str]:
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
        meta = {
            "name": name[:70],
            "description": description[:70],
            "created_at": now,
            "modified_at": now,
        }
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
                self.campaign_data = json.load(f)
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

    def save_location(self, filename: str) -> bool:
        """Сохраняет указанную локацию в текущую кампанию"""
        result = self.dm.save(filename)
        if result:
            self._update_modified()
        return result

    def save_all_locations(self) -> int:
        """Сохраняет все локации текущей кампании"""
        count = 0
        for fname in list(self.dm.locations.keys()):
            if self.dm.save(fname):
                count += 1
        self._update_modified()
        return count

    def save_location_as(self, source_filename: str,
                         new_filename: str) -> Tuple[bool, str]:
        """Копирует локацию под новым именем в текущую кампанию"""
        if source_filename not in self.dm.locations:
            return False, "Исходный файл не найден"
        if not new_filename.endswith(".json"):
            new_filename += ".json"
        if new_filename in self.dm.locations:
            return False, "Файл уже существует"
        self.dm.locations[new_filename] = copy.deepcopy(
            self.dm.locations[source_filename]
        )
        self.dm.locations[new_filename]["filename"] = new_filename
        self.dm.save(new_filename)
        self._update_modified()
        return True, ""

    def _update_modified(self):
        """Обновляет дату изменения в campaign.json"""
        if not self.campaign_path or not self.campaign_data:
            return
        meta_file = self.campaign_path / "campaign.json"
        if meta_file.exists():
            self.campaign_data["modified_at"] = datetime.now().isoformat()
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