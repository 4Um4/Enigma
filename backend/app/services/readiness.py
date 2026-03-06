from app.models.schemas import ReadinessCheck, ReadinessReport


class ReadinessService:
    """Simple project completeness report against target product requirements."""

    def report(self) -> ReadinessReport:
        checks = [
            ReadinessCheck(
                area="Backend API",
                status="done",
                details="Есть рабочие endpoint'ы для хода, кампаний, персонажей, readiness, world tick и импорта знаний (TXT/MD/PDF).",
            ),
            ReadinessCheck(
                area="D&D 5e rules",
                status="partial",
                details="Добавлен базовый цикл боя (инициатива/ход/атака), но нет полного rules engine: saving throws, эффекты заклинаний и состояния."
            ),
            ReadinessCheck(
                area="LLM providers",
                status="partial",
                details="Есть маршрутизация выбора модели, но реальные адаптеры провайдеров ещё не интегрированы.",
            ),
            ReadinessCheck(
                area="Memory",
                status="partial",
                details="Есть layered JSONL память, включая NPC memory, но нет векторной БД (Chroma/FAISS/Qdrant).",
            ),
            ReadinessCheck(
                area="World simulation",
                status="partial",
                details="Есть world tick и скрытый журнал, но нет автономного фонового планировщика процесса.",
            ),
            ReadinessCheck(
                area="Desktop UI",
                status="missing",
                details="Electron/Tauri интерфейс, карта, токены, fog of war и панели игры отсутствуют.",
            ),
        ]

        status_points = {"done": 1.0, "partial": 0.5, "missing": 0.0}
        score = round(sum(status_points.get(c.status, 0.0) for c in checks) / len(checks) * 100, 2)
        return ReadinessReport(
            score_percent=score,
            summary="Сейчас это расширенный backend MVP, но ещё не полный локальный AI DM продукт.",
            checks=checks,
            next_steps=[
                "Интегрировать реальные LLM-адаптеры (локальные и API).",
                "Реализовать полный движок D&D 5e (combat/initiative/spells/conditions).",
                "Добавить векторную память и расширенную долговременную NPC memory.",
                "Сделать desktop UI с chat/map/player/event log и кнопкой SWITCH MODEL.",
                "Добавить отдельный фоновый scheduler world simulation каждые N минут.",
            ],
        )
