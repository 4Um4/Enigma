#!/usr/bin/env python3 
"""
map_editor/editor_launcher.py
Точка входа для редактора карт R4 Spatial

Запуск: python frontend/map_editor/editor_launcher.py
"""

import os
import sys

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from editor_core import EditorCore


def print_help():
    """Выводит справку по использованию"""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║           R4 Spatial Map Editor v2.0                             ║
║           Редактор помещений с навигационным графом              ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  📁 ДИРЕКТОРИИ:                                                  ║
║     location_templates/  - JSON-файлы локаций                    ║
║     runtime_cache/       - Скомпилированные данные               ║
║                                                                  ║
║  🎮 УПРАВЛЕНИЕ:                                                  ║
║     [File]               - Создать новую локацию                 ║
║     [TAB]                - Переключение Мир/Локация              ║
║     [ЛКМ]                - Выделить / Разместить                 ║
║     [ПКМ + движение]     - Перемещение камеры                    ║
║     [Ctrl + S]           - Сохранить                             ║
║     [+/-]                - Масштаб                               ║
║     [ESC]                - Отмена / Сброс выделения              ║
║                                                                  ║
║  🛠️ ИНСТРУМЕНТЫ:                                                 ║
║     👆 Выбор        - Выделение объектов                         ║
║     🧱 Стена        - Рисование стен (клик и тянуть)             ║
║     📦 Комната      - Создание комнат (клик и тянуть)            ║
║     🔵 Узел         - Навигационные узлы                         ║
║     🪑 Объект       - Мебель и декор                             ║
║     🚪 Портал       - Двери, лестницы, переходы                  ║
║     🗑️ Удалить      - Удаление объектов                          ║
║                                                                  ║
║  📐 СЕТКА: 1 метр = 40 пикселей                                  ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")


def main():
    """Главная функция"""
    # Проверяем аргументы
    if "--help" in sys.argv or "-h" in sys.argv:
        print_help()
        return

    print("""
╔══════════════════════════════════════════════════════════════════╗
║           R4 Spatial Map Editor v2.0                             ║
╚══════════════════════════════════════════════════════════════════╝
    """)

    # Создаём необходимые директории
    os.makedirs("location_templates", exist_ok=True)
    os.makedirs("runtime_cache", exist_ok=True)

    # Запускаем редактор
    try:
        app = EditorCore(width=1400, height=900)
        app.run()
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
