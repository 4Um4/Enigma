"""
map_editor/ui_components.py
ФАСАД. Реальная логика перенесена в ui.components, ui.panels, ui.dialogs.
Этот файл существует для обратной совместимости с editor_core.py.
"""
from ui.components import COLORS, Button, Dropdown, DropDownMenu, Slider, TextInput, ToggleButton
from ui.dialogs import ModalDialog
from ui.panels import PropertyPanel, Toolbar

__all__ = [
    'Button', 'ToggleButton', 'TextInput', 'Dropdown', 'DropDownMenu', 'Slider',
    'Toolbar', 'PropertyPanel', 'ModalDialog', 'COLORS'
]
