# ADR-115 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-115` [STANDARD] **IMPACT**
# ADR-115 Impact Audit: DOUBLE TRUTH perceptual_kernel

## Changed Domains
- Perception (PerceptualKernel serialization)
- Affect (affective_load serialization)
- Decision (threat_gradient/initiative_suppression теперь переживают тики)

## Downstream Consumers
- LifeEngine: читает 	hreat_gradient из 
pc.get("perceptual_kernel") для GAP9 (пробуждение от сна)
- DecisionHub: читает _kernel.threat_gradient для risk_penalty и obedience pressure
- PressureDerivation: читает kernel.threat_gradient + kernel.compliance_bias
- PressureTranslator: читает kernel.threat_gradient для escape_salience
- AffectiveIntegrator: читает kernel.threat_gradient для affective_load
- TickOrchestrator: строит projected_kernel из pk_dict.get("threat_gradient")
- BehaviorManifestationService: читает initiative_suppression из all_npcs_raw

## Runtime Impact
- RAM: +200 bytes per NPC (PerceptualKernel dict в npc_dict)
- Tick Latency: 0 (только сериализация при apply_batch)
- Persistence: affective_load и perceptual_kernel теперь переживают запись в SQLite

## Sandbox Tests
- 	est_perceptual_kernel_survives_legacy_roundtrip (smoke-test пройден: WRITE/READ/DEFAULT/ROUNDTRIP ✅)
- Runtime верификация: fear 0.537→0.556→0.590→0.590 (монотонный рост + персистенция)

## Rollback
1. Удалить блок perceptual_kernel из write_to_legacy() (строки после body_state)
2. Удалить ffective_load из write_to_legacy()
3. Удалить _pk_from_dict() helper
4. Удалить perceptual_kernel= и ffective_load= из rom_legacy()
5. Очистить __pycache__

## Files Changed
- ackend/app/models/npc_state.py: write_to_legacy(), from_legacy(), _pk_from_dict()
- rchitecture/physiology.yaml: добавлено правило ADR-115



Files: N/A
