# ADR-TZ04 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-TZ04` [STANDARD] **IMPACT**
# ADR-TZ04 Impact Audit
> Этот файл — детальный аудит ТЗ-04 (Spatial Authority & Physics Repair). Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- DOM-01: Foundation (Core Pipeline, State)
- DOM-04: Spatial & Locomotion
- DOM-07: Frontend, Presentation & Input

## Downstream Consumers
- `combat_subscriber.py`: теперь зависит от `SpatialQueryService` для range gate.
- `r3_direct_builder.py`: теперь зависит от `SpatialQueryService` для DM distances.
- `SceneStateManager.apply_change`: теперь использует `KernelRNG` для deterministic jitter.
- `npc_orchestration.py` & `dm_phase.py`: теперь генерируют `SceneChange` вместо прямых мутаций.

## Runtime Impact
- **Determinism:** Повышена. Устранены `random.uniform` в физике.
- **Memory:** Уменьшена. Удалены мёртвые модули (`transit_tracker`, `location_graph`) и 122 строки dead code.
- **Latency:** Незначительная нагрузка на создание `SceneChange` для метаданных, но это необходимая плата за RCG (Reality Commit Gate).

## Sandbox Tests
- `backend/tests/test_tz4_spatial_authority.py` (12 тестов):
  - Проверка отсутствия zombie readers.
  - Проверка отсутствия `random.uniform` в `apply_change`.
  - Проверка удаления мёртвых модулей.
  - Проверка отсутствия `except Exception: pass` в Spatial Oracle.
  - Проверка использования `SpatialFactory`.
  - Проверка маршрутизации мутаций через `SceneChange`.
- `DriftLaboratory` (3 & 200 тиков): 0 крашей, `comparisons=499`, `rate=2.495/tick`.

## Rollback
1. Восстановить `transit_tracker.py` и `location_graph.py` из git history.
2. Вернуть `random.uniform` в `scene_state_manager.py` (строка 1408).
3. Вернуть прямые вызовы `SpatialService.build_for_location` во всех файлах (заменить `SpatialFactory.build_for_campaign`).
4. Вернуть прямые мутации `scene_state` в `npc_orchestration.py` и `dm_phase.py`.
5. Удалить `SpatialFactory` и `ChangeType.NPC_METADATA` / `SCENE_METADATA`.


Files: N/A
