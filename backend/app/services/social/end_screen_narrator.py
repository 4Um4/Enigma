"""
path: /project/backend/app/services/social/end_screen_narrator.py
Назначение: Детерминированный генератор нарратива для End-Screen.
Зависимости: app.models.fate, app.models.evaluation
Основные сущности: EndScreenNarrator
"""
from __future__ import annotations
from app.models.fate import FateState

class EndScreenNarrator:
    """Переводит сухие метрики в живой язык."""
    
    @staticmethod
    def narrate_verdict(score: int) -> str:
        if score >= 80: return "Вы стали легендой Таверны Серебряной Луны. Ваше имя будут помнить долгие годы."
        if score >= 50: return "Вы неплохо проявили себя, но многие тайны так и остались погребены во мраке."
        if score >= 20: return "Вы ушли ни с чем, оставив после себя лишь ворох слухов и неразрешённых противоречий."
        return "Ваш визит прошёл впустую. Мир остался безучастным к вашему присутствию."

    @staticmethod
    def narrate_fate(npc_id: str, fate_state: FateState) -> str:
        if fate_state.resolved_fate:
            outcomes = {
                "escape": f"{npc_id} бежал из города, спасая свою жизнь.",
                "death": f"{npc_id} погиб при трагических обстоятельствах.",
                "broken": f"{npc_id} сломлен духовно и физически, его дни сочтены.",
                "liberated": f"{npc_id} освободился от своих демонов и начал новую жизнь.",
                "empowered": f"{npc_id} обрёл силу и влияние, став вершителем судеб.",
                "imprisoned": f"{npc_id} брошен в темницу за свои деяния."
            }
            return outcomes.get(fate_state.resolved_fate.value, f"Судьба {npc_id} разрешилась: {fate_state.resolved_fate.value}.")

        traj = fate_state.fate_trajectory.value
        stab = fate_state.stability
        threat = fate_state.threat_level
        
        if traj == "critical": return f"{npc_id} находится на грани гибели. Угроза вокруг него сгущается."
        if traj == "deteriorating":
            if threat > 0.5: return f"Жизнь {npc_id} висит на волоске. Он окружён врагами и опасностями."
            return f"Дела {npc_id} идут всё хуже. Он медленно теряет почву под ногами."
        if traj == "improving" and stab > 0.9: return f"{npc_id} расцветает. Он чувствует себя в безопасности и смотрит в будущее с надеждой."
        if traj == "stable": return f"Жизнь {npc_id} идёт своим чередом, без взлётов и падений."
        return f"Положение {npc_id} неопределённо."

    @staticmethod
    def narrate_relationship(src: str, tgt: str, trust: float, fear: float) -> str:
        src_name = "Игрок" if src == "player" else src
        tgt_name = "Игрока" if tgt == "player" else tgt

        if trust > 70: return f"{src_name} глубоко предан {tgt_name}."
        if trust > 30 and fear < 20: return f"{src_name} доверяет {tgt_name} и ценит их общество."
        if trust < -70: return f"{src_name} люто ненавидит {tgt_name}."
        if trust < -30: return f"{src_name} испытывает сильную антипатию к {tgt_name}."
        if fear > 70: return f"{src_name} до смерти боится {tgt_name}."
        if fear > 30 and trust < 0: return f"{src_name} опасается {tgt_name} и старается избегать их."
        if trust > 0 and fear > 0: return f"{src_name} уважает {tgt_name}, но и побаивается его."
        return f"{src_name} относится к {tgt_name} нейтрально."