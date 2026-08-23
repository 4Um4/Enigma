"""
map_editor/ui_components.py
ФАСАД. Реальная логика перенесена в ui.components, ui.panels, ui.dialogs.
Этот файл существует для обратной совместимости с editor_core.py.
"""
from ui.components import Button, ToggleButton, TextInput, Dropdown, DropDownMenu, Slider, COLORS
from ui.panels import Toolbar, PropertyPanel
from ui.dialogs import ModalDialog

__all__ = [
    'Button', 'ToggleButton', 'TextInput', 'Dropdown', 'DropDownMenu', 'Slider',
    'Toolbar', 'PropertyPanel', 'ModalDialog', 'COLORS'
]