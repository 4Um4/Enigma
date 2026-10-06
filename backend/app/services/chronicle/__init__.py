"""
Character Chronicle — сервисный домен авторинг-компилятора (ADR-O-420).

Файл: backend/app/services/chronicle/__init__.py
Назначение: Слой 0 канонического порядка — авторский текст → машинная хроника
            → seed стартового состояния ДО первого тика. Трек НЕ входит в
            тик-пайплайн (Фазы 0–10 не расширяются).
Зависимости: app.domain.chronicle, app.core.constants
Основные сущности: age_math (CCH-1) · chronicle_store (CCH-1) ·
                   white_spot_registry (CCH-1) · biography_decomposer (CCH-2) ·
                   chronicle_seeder (CCH-4)
"""
