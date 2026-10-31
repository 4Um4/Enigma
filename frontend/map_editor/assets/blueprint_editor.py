"""path: /frontend/map_editor/assets/blueprint_editor.py

Назначение: EditSession — независимая рабочая копия Blueprint для редактирования
    (ME-2.1-G-2). UI работает только через EditSession; AssetStore остаётся
    единственным владельцем сохранённого состояния. Между ними нет обходного пути.

    Контракт Master (G-2):
    - Редактор изменяет рабочую копию. AssetStore изменяет сохранённое состояние.
    - EditSession не получает ссылку на BlueprintRecord.data — только deepcopy.
    - Сохранение — ТОЛЬКО через store.save_blueprint_atomic (G-1).
    - dirty по содержимому, не по факту вызова set_field.
    - После save/cancel сессия закрыта для изменений (state OPEN→SAVED/CANCELLED).

Зависимости: assets.asset_store (AssetStore, BlueprintRecord, SaveResult,
    VersionConflict, SaveBlocked, AssetStoreError). Стандартная библиотека.
    Backend не импортируется (граница фронта, Закон 1.1 Устава).

Основные сущности: EditSession, BlueprintEditor, SessionState.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Callable, Optional

from assets.asset_store import (
    AssetStore,
    AssetStoreError,
    BlueprintRecord,
    SaveResult,
)


class SessionState(str, Enum):
    """Состояние EditSession. После save/cancel сессия закрыта для изменений."""

    OPEN = "open"
    SAVED = "saved"
    CANCELLED = "cancelled"


def _deep_copy(data: dict) -> dict:
    """Глубокая копия через json round-trip.

    Blueprint JSON-сериализуем, поэтому json round-trip безопасен и идемпотентен
    (без зависимости от copy.deepcopy на вложенных структурах).
    """
    return json.loads(json.dumps(data))


def _get_by_path(data: dict, path: str) -> Any:
    """Чтение значения по dotted-path: 'geometry.size.w'.

    Fail-loud если путь не существует (KeyError) — UI должен использовать
    существующие пути; для интроспекции есть get_data().
    """
    keys = path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            raise KeyError(f"Путь '{path}' не найден в данных Blueprint (ключ '{key}')")
        current = current[key]
    return current


def _set_by_path(data: dict, path: str, value: Any) -> None:
    """Запись значения по dotted-path.

    Промежуточные ключи должны существовать (fail-loud если нет) — UI не должен
    молча создавать новые вложенные структуры. Последний сегмент может быть новым
    ключом в существующем dict (например, metadata._custom_field).
    """
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if not isinstance(current, dict):
            raise KeyError(f"Путь '{path}' невозможен: '{key}' — не dict")
        if key not in current:
            raise KeyError(f"Путь '{path}' невозможен: промежуточный ключ '{key}' не существует")
        if not isinstance(current[key], dict):
            raise KeyError(f"Путь '{path}' невозможен: '{key}' существует, но не dict")
        current = current[key]
    if not isinstance(current, dict):
        raise KeyError(f"Путь '{path}' невозможен: последний сегмент — не dict")
    current[keys[-1]] = value


class EditSession:
    """Независимая рабочая копия одного Blueprint (ME-2.1-G-2).

    Инварианты (ТЗ Master):
    - Независимость: мутация working НЕ меняет AssetStore._blueprints[id].data
    - Изоляция: get_data()/get_field() возвращают deepcopy — UI не получает ссылку
    - Версия: opened_version + opened_fingerprint сохраняются на момент open
    - Конфликт: save() использует G-1 (version + fingerprint check)
    - Валидация: невалидные данные не передаются на save (G-1 гейтит через validator)
    - Отмена: cancel() восстанавливает working = deepcopy(original)
    - Dirty по содержимому: working == original → dirty=False (не по факту set_field)
    - Сохранение: ТОЛЬКО через store.save_blueprint_atomic (никаких write_text)
    - Повторное открытие: новая EditSession читает актуальный record из store

    Состояние:
    - OPEN: можно set_field / set_working / validate / cancel / save
    - SAVED: после успешного save — закрыта для изменений
    - CANCELLED: после cancel/close — закрыта для изменений
    """

    def __init__(
        self,
        blueprint_id: str,
        original: dict,
        working: dict,
        opened_version: int,
        opened_fingerprint: str,
        opened_record: BlueprintRecord,
        store: AssetStore,
        validator: Optional[Any] = None,
    ) -> None:
        self._blueprint_id = blueprint_id
        self._original = original  # frozen snapshot (deepcopy на момент open)
        self._working = working  # мутируется UI (deepcopy на момент open)
        self._opened_version = opened_version
        self._opened_fingerprint = opened_fingerprint
        self._opened_record = opened_record  # frozen BlueprintRecord для save
        self._store = store  # weak ref, НЕ владеет
        self._validator = validator  # duck-typed (как в G-1)
        self._state = SessionState.OPEN
        self._last_validation: Optional[Any] = None

    # ===== Свойства (read-only) =====

    @property
    def blueprint_id(self) -> str:
        return self._blueprint_id

    @property
    def opened_version(self) -> int:
        return self._opened_version

    @property
    def opened_fingerprint(self) -> str:
        return self._opened_fingerprint

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def dirty(self) -> bool:
        """Dirty по содержимому, НЕ по факту вызова set_field.

        Если пользователь изменил значение и вернул исходное — dirty=False.
        Сравнение через != (dict __eq__ — глубокое в Python).
        """
        return self._working != self._original

    @property
    def last_validation(self) -> Optional[Any]:
        """Результат последней валидации (ValidationResult | None).

        None если validate() не вызывался и set_field/set_working не вызывались
        с переданным validator.
        """
        return self._last_validation

    # ===== Чтение (UI получает копии, не ссылки) =====

    def get_data(self) -> dict:
        """Полная deepcopy working. UI не получает ссылку на внутренний dict.

        Чтение разрешено в любом state (OPEN/SAVED/CANCELLED) — пользователь
        может посмотреть состояние после save/cancel. Только запись гейтится
        _require_open() (set_field/set_working/save).
        """
        return _deep_copy(self._working)

    def get_field(self, path: str) -> Any:
        """Чтение поля по dotted-path: 'geometry.size.w'.

        Для dict/list возвращает deepcopy (изоляция UI). Примитивы — по значению.
        Чтение разрешено в любом state (OPEN/SAVED/CANCELLED).
        """
        value = _get_by_path(self._working, path)
        if isinstance(value, (dict, list)):
            return _deep_copy(value)
        return value

    # ===== Мутация (только в состоянии OPEN) =====

    def set_field(self, path: str, value: Any) -> list:
        """Изменить поле по dotted-path. Возвращает list[ValidationIssue] (errors).

        Live validation: если validator передан, валидирует working после мутации
        и сохраняет результат в last_validation. Возвращает errors list.
        """
        self._require_open()
        # Изолировать value от внешних мутаций (deepcopy для контейнеров)
        if isinstance(value, (dict, list)):
            value = _deep_copy(value)
        _set_by_path(self._working, path, value)
        return self._live_validate()

    def set_working(self, new_data: dict) -> list:
        """Заменить working целиком. Возвращает list[ValidationIssue] (errors).

        new_data deepcopy'ится — UI не保留 ссылку.
        """
        self._require_open()
        self._working = _deep_copy(new_data)
        return self._live_validate()

    def validate(self) -> Optional[Any]:
        """Полная валидация working. Возвращает ValidationResult (или None).

        Если validator не передан — возвращает None (без валидации).
        Сохраняет результат в last_validation.
        """
        self._require_open()
        if self._validator is None:
            self._last_validation = None
            return None
        self._last_validation = self._validator.validate_blueprint(self._working)
        return self._last_validation

    # ===== Операции сессии =====

    def cancel(self) -> None:
        """Отмена: working = deepcopy(original); state=CANCELLED.

        После cancel сессия закрыта для изменений. dirty=False.
        """
        self._require_open()
        self._working = _deep_copy(self._original)
        self._state = SessionState.CANCELLED

    def save(self, on_cache_refresh: Optional[Callable[[], None]] = None) -> SaveResult:
        """Сохранить working через G-1 (store.save_blueprint_atomic).

        Поднимает VersionConflict / SaveBlocked / AssetStoreError (от G-1).
        После успешного save state=SAVED — сессия закрыта для изменений.

        Контракт: ТОЛЬКО этот путь сохранения. Никаких write_text/json.dump
        в EditSession. AssetStore — единственный владелец сохранённого состояния.
        """
        self._require_open()
        result = self._store.save_blueprint_atomic(
            self._opened_record,
            self._working,
            validator=self._validator,
            on_cache_refresh=on_cache_refresh,
        )
        self._state = SessionState.SAVED
        return result

    def close(self) -> None:
        """Закрыть сессию без сохранения. Очищает working/original.

        После close сессия непригодна для использования (state=CANCELLED).
        """
        self._state = SessionState.CANCELLED
        self._working = {}
        self._original = {}
        self._last_validation = None

    # ===== Внутренние =====

    def _require_open(self) -> None:
        """Гейт: операция разрешена только в состоянии OPEN."""
        if self._state != SessionState.OPEN:
            raise AssetStoreError(
                f"EditSession для '{self._blueprint_id}' закрыта "
                f"(state={self._state.value}). "
                f"Откройте новую сессию через BlueprintEditor.open()."
            )

    def _live_validate(self) -> list:
        """Live validation после set_field/set_working. Возвращает errors list.

        Если validator не передан — пустой list (без валидации).
        """
        if self._validator is None:
            return []
        self._last_validation = self._validator.validate_blueprint(self._working)
        return self._last_validation.errors


class BlueprintEditor:
    """Фасад для создания EditSession (ME-2.1-G-2).

    Не владеет состоянием — только открывает сессии поверх AssetStore.
    Каждый open() создаёт независимую EditSession с deepcopy snapshot.

    Контракт: UI получает EditSession, НЕ BlueprintRecord. AssetStore остаётся
    единственным владельцем сохранённого состояния.
    """

    def __init__(
        self,
        asset_store: AssetStore,
        validator: Optional[Any] = None,
    ) -> None:
        self._store = asset_store
        self._validator = validator

    def open(self, blueprint_id: str) -> EditSession:
        """Открыть EditSession для blueprint_id.

        Читает актуальный record из store (повторное открытие получает актуальное
        состояние — инвариант 7). Поднимает AssetStoreError если blueprint_id
        не найден.
        """
        record = self._store.get_blueprint(blueprint_id)
        if record is None:
            raise AssetStoreError(f"Blueprint '{blueprint_id}' не найден в AssetStore — open невозможен")
        original = _deep_copy(record.data)
        working = _deep_copy(record.data)
        return EditSession(
            blueprint_id=blueprint_id,
            original=original,
            working=working,
            opened_version=record.version,
            opened_fingerprint=record.fingerprint,
            opened_record=record,
            store=self._store,
            validator=self._validator,
        )

    def new_from(self, source_id: str, new_id: str) -> EditSession:
        """Создать EditSession для нового blueprint на основе существующего.

        G-8 (ME-2.1-G-8). В G-2 — заглушка NotImplementedError; полная реализация
        в G-8 (deepcopy → new_id → save as new file).
        """
        raise NotImplementedError("new_from — G-8 (ME-2.1-G-8). В G-2 заглушка; не реализовано.")
