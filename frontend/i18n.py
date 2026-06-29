"""
path: /frontend/i18n.py
Назначение: Единый файл локализации (i18n). Все пользовательские строки — здесь.
Зависимости: нет
Основные сущности: L (словарь локализации)
"""

# Ключ = внутренний идентификатор, значение = русский текст
# Для перевода: заменить значения на другой язык

L = {
    # ── Активности (schedule keys → наблюдаемое действие) ──
    "act:sleeping": "спит",
    "act:working": "работает",
    "act:haggling": "торгуется",
    "act:serving_tables": "обслуживает столы",
    "act:guarding_gate": "охраняет вход",
    "act:market_trading": "торгует на рынке",
    "act:cleaning_tables": "убирает столы",
    "act:idle": "без дела",
    "act:social_drift": "осматривается",
    "act:eating": "ест",
    "act:drinking": "пьёт",
    "act:resting": "отдыхает",
    "act:talking": "разговаривает",
    "act:walking": "гуляет",
    "act:reading": "читает",
    "act:cooking": "готовит",
    "act:smithing": "куёт",
    "act:sweeping": "подметает",
    "act:mopping": "моет пол",
    "act:chatting": "болтает",
    "act:standing": "стоит",
    "act:sitting": "сидит",
    "act:watching": "наблюдает",
    "act:inspecting": "осматривает",
    "act:fleeing": "убегает",
    "act:approaching": "приближается",

    # ── Наблюдаемые симптомы (motor traces → что видит аватар) ──
    "sym:frozen": "окаменел",
    "sym:shaking": "дрожит",
    "sym:swaying": "покачивается",
    "sym:uneven_stance": "шатается",
    "sym:abrupt_stop": "резко замер",
    "sym:frequent_pauses": "частые паузы",
    "sym:wincing": "морщится от боли",
    "sym:holding_side": "придерживает бок",
    "sym:bleeding": "кровоточит",
    "sym:staggered": "шатается",
    "sym:tense_posture": "напряжён",

    # ── Наблюдаемые физические проявления (НЕ эмоции! тип моторики, не значение) ──
    "manifest:tense": "напряжён",
    "manifest:rigid": "скован",
    "manifest:unstable": "неуверен",
    "manifest:restless": "суетлив",
    "manifest:suffering": "страдает",
    "manifest:alert": "насторожен",

    # ── UI: Консоль наблюдений (Ё) ──
    "ui:obs_title": "── Наблюдение ──",

    # ── UI: Журнал (J) ──
    "ui:journal_title": "── Журнал Диалогов (J) ──",

    # ── UI: Смерть ──
    "ui:death_title": "ВЫ МЕРТВЫ",
    "ui:death_subtitle": "Смерть необратима. Мир продолжает жить без вас.",

    # ── UI: Прочее ──
    "ui:narrator": "Рассказчик",
    # ── UI: Меню (ТЗ-6 C2) ──
    "ui:menu_new_game": "Новая игра",
    "ui:menu_continue": "Продолжить",
    "ui:menu_editor": "Редактор карт",
    "ui:menu_settings": "Настройки",
    "ui:menu_exit": "Выход",
    "ui:scale_1x": "▶ 1x",
    "ui:scale_4x": "▶▶ 4x",
    "ui:scale_10x": "▶▶▶ 10x",
    "ui:scale_50x": " 50x⏩",
}


def t(key: str, fallback: str = "") -> str:
    """Получить локализованную строку по ключу. Fallback — если ключ отсутствует."""
    return L.get(key, fallback or key)


def activity_ru(activity_key: str) -> str:
    """Перевести внутренний ключ активности в наблюдаемый русский."""
    return t(f"act:{activity_key}", activity_key)


def manifest_color(manifest_key: str):
    """Цвет по типу физического проявления (НЕ эмоция!).
    Холодные = застывание. Серые = потеря координации. Тёплые = избыточная моторика. Тёмные = деградация."""
    _colors = {
        "manifest:tense": (180, 180, 130),      # серо-жёлтый — мышечный тонус
        "manifest:rigid": (140, 155, 185),      # холодный серо-синий — застывание
        "manifest:unstable": (160, 150, 140),   # рваный серый — потеря координации
        "manifest:restless": (185, 160, 120),   # шумный тёплый — избыточная моторика
        "manifest:suffering": (130, 110, 100),  # тёмный грязный — деградация состояния
        "manifest:alert": (200, 200, 160),      # резкий жёлто-белый — реактивность
    }
    return _colors.get(manifest_key, (160, 160, 160))