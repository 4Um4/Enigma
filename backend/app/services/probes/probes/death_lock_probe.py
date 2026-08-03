# backend/app/services/probes/probes/death_lock_probe.py
"""
ADR-127: Death Lock.
Мёртвый NPC не может иметь активных перемещений или генерировать интенты.
"""
from ..probe_registry import Probe, ProbeContext, ProbeResult

class DeathLockProbe(Probe):
    name = "INV-DEATH-LOCK"
    severity = "ERROR"

    def check(self, ctx: ProbeContext) -> ProbeResult:
        travs = ctx.scene_state.get("active_traversals", {})
        if not travs or not ctx.all_npcs_raw:
            return ProbeResult(name=self.name, severity=self.severity, passed=True)
            
        for npc in ctx.all_npcs_raw:
            if not isinstance(npc, dict):
                continue
            nid = npc.get("npc_id") or npc.get("id")
            if not nid:
                continue
                
            # Проверяем статус смерти (может быть на верхнем уровне или в body_state)
            life_status = npc.get("life_status", "").upper()
            if not life_status:
                life_status = npc.get("body_state", {}).get("life_status", "").upper()
                
            if life_status == "DEAD":
                if nid in travs:
                    return ProbeResult(
                        name=self.name,
                        severity=self.severity,
                        passed=False,
                        details=f"Dead NPC '{nid}' has active traversal at tick {ctx.tick_id}. ADR-127 violation."
                    )
                    
        return ProbeResult(name=self.name, severity=self.severity, passed=True)