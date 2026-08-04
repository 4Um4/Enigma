# backend/app/services/probes/probes/l3_ephemeral_probe.py
"""
L3-P1: EffectiveDrives эфемерны.
Проверяет, что L3 не персистится в scene_state или npc_dicts.
"""
from ..probe_registry import Probe, ProbeContext, ProbeResult

class L3EphemeralProbe(Probe):
    name = "INV-L3-EPHEMERAL"
    severity = "ERROR"

    def check(self, ctx: ProbeContext) -> ProbeResult:
        # 1. Проверяем scene_state
        for key in ctx.scene_state.keys():
            if key.lower() in ("effective_drives", "l3_drives", "l3_projection"):
                return ProbeResult(
                    name=self.name,
                    severity=self.severity,
                    passed=False,
                    details=f"scene_state contains persisted L3 key: '{key}' at tick {ctx.tick_id}"
                )
                
        # 2. Проверяем npc_dicts (all_npcs_raw)
        for npc in ctx.all_npcs_raw:
            if not isinstance(npc, dict):
                continue
            for key in npc.keys():
                if key.lower() in ("effective_drives", "l3_drives", "l3_projection"):
                    nid = npc.get("npc_id", "unknown")
                    return ProbeResult(
                        name=self.name,
                        severity=self.severity,
                        passed=False,
                        details=f"NPC '{nid}' dict contains persisted L3 key: '{key}' at tick {ctx.tick_id}"
                    )
                    
        return ProbeResult(name=self.name, severity=self.severity, passed=True)