"""
path: /frontend/ui_workbench/registry.py
Назначение: Единственный владелец состояний окон. Рендер и ввод читают ТОЛЬКО отсюда.
Зависимости: ui_workbench.manifests
Основные сущности: WindowRegistry
"""
from typing import Dict, List, Optional

from ui_workbench.manifests import WindowManifest, WindowState


class WindowRegistry:
    """Реестр окон: манифест (статика) + текущее состояние (динамика).
    FSM-переходы легальны только через методы этого класса."""

    _LEGAL_TRANSITIONS = {
        # HIDDEN → только FULL: свернутое состояние — результат действия
        # пользователя, не способ появления окна. Восстановление снимка
        # из persistence — отдельный путь restore() (не FSM-переход).
        WindowState.HIDDEN: {WindowState.FULL},
        WindowState.COLLAPSED_TO_TITLE: {WindowState.FULL, WindowState.HIDDEN},
        WindowState.FULL: {WindowState.COLLAPSED_TO_TITLE, WindowState.HIDDEN},
    }

    def restore(self, window_id: str, state_value: str) -> None:
        """Загрузка состояния из persistence (вне FSM: это не действие
        пользователя, а восстановление снимка прошлой сессии)."""
        try:
            state = WindowState(state_value)
        except ValueError:
            raise ValueError(
                f"WindowRegistry[{window_id}]: неизвестное состояние '{state_value}'"
            )
        self._states[window_id] = state

    def __init__(self) -> None:
        self._manifests: Dict[str, WindowManifest] = {}
        self._states: Dict[str, WindowState] = {}

    def register(self, manifest: WindowManifest) -> None:
        """Регистрация окна. Повторная регистрация того же id = ошибка (SSOT, не молчаливая перезапись)."""
        manifest.validate()
        if manifest.window_id in self._manifests:
            raise ValueError(f"WindowRegistry: окно '{manifest.window_id}' уже зарегистрировано")
        self._manifests[manifest.window_id] = manifest
        self._states[manifest.window_id] = manifest.default_state

    def manifest(self, window_id: str) -> WindowManifest:
        return self._manifests[window_id]

    def state(self, window_id: str) -> WindowState:
        return self._states[window_id]

    def transition(self, window_id: str, new_state: WindowState) -> None:
        """Единственный легальный FSM-переход. Незаконный = ValueError (громко)."""
        current = self._states[window_id]
        if new_state not in self._LEGAL_TRANSITIONS[current]:
            raise ValueError(
                f"WindowRegistry[{window_id}]: {current.value} → {new_state.value} запрещён"
            )
        self._states[window_id] = new_state

    def toggle(self, window_id: str) -> None:
        """Типовая кнопка (hotkey/click): HIDDEN→FULL, FULL→COLLAPSED, COLLAPSED→FULL."""
        current = self._states[window_id]
        target = WindowState.FULL if current != WindowState.FULL else WindowState.COLLAPSED_TO_TITLE
        self.transition(window_id, target)

    def visible_ids(self, layers: Optional[List[int]] = None) -> List[str]:
        """id видимых окон (COLLAPSED или FULL), отсортированных по z_order — порядок рендера."""
        out = [
            wid for wid, st in self._states.items()
            if st != WindowState.HIDDEN
            and (layers is None or self._manifests[wid].layer in layers)
        ]
        return sorted(out, key=lambda wid: self._manifests[wid].z_order)

    def all_ids(self) -> List[str]:
        return list(self._manifests.keys())