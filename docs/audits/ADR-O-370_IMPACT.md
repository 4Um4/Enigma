# ADR-O-370 Impact Audit
> Детальный аудит одного ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- SOCIAL — RelationshipStateStore: SSOT-субстрат RE (scene_state["relationship_state"];
  dormant — не вызывается рантаймом); контракты NeedSlot/NeedLevel/PreferenceModel/
  HardConstraint/ExclusivityRequirement.
- PERSISTENCE — бэкинг через scene_state → atomic_commit_all (Foundation Freeze);
  собственных файловых путей НЕТ; старые сейвы совместимы (ключ отсутствует → дефолты).
- DECISION/APPLICATOR — StateApplicator.update_needs (единственный runtime-writer,
  caller-guard); санация легаси файла: F821 cause ×2 (apply_physical, apply_deltas_only),
  F841 ×4 (мёртвый IdentityPayload-extraction), TYPE_CHECKING BeliefDelta, whitespace.

## Downstream Consumers
- M2/D — RelationshipEventSemantics (первый реальный писатель через update_needs;
  тогда же — полная О1-интеграция Cause: формат RE-событий в causal-машинерии).
- G/H — динамика Satisfaction/фрустрации (читают/пишут через стор).
- M1b — миграция 5 скаляров RelationshipStore в v2-схему (отдельный ADR).
- Полигон M — пресеты будут патчить NeedSlot-дефолты (сейчас — плейсхолдеры).

## Runtime Impact
- RAM: ~КБ (N NPC × 2 слота × 3 float + структуры).
- CPU: 0 (dormant). Tick-поведение байтово идентично (IPT 44/44 до == после).
- Сейвы: +1 ключ scene_state; старые сейвы грузятся без миграции.
- Санация apply_deltas_only: путь восстановления стресса больше не рискует NameError
  (семантика не менялась — сатурация ADR-121 сохранена, подтверждено 50.0 → 47.5).

## Sandbox Tests
- backend/tests/test_relationship_state_store.py — приёмка фазы B: round-trip
  бит-в-бит (из реальной write-машины), single-writer позитив+негатив, диапазоны,
  Ф2, реестр, clamp, старый сейв, frozen-DTO, повреждённая структура.
- Гейты: pytest (сьюта + полный прогон), IPT 44/44, RE-linter PASSED, ruff чист.

## Rollback
Атомарный: удалить relationship_contracts.py, relationship_state_store.py,
test_relationship_state_store.py; откатить update_needs/imports в state_applicator,
init-ключ в SSM. Данные кампаний не затронуты (ключ отсутствует = легитимно).

## Verification Log
1. Сигнатуры получены до патчей (Cause: все поля optional; apply_physical —
   позиционные state/outcome).
2. Инцидент-урок (закрыт в сессии): патч с «условным применением» не выдаётся —
   сначала факт, потом патч (SyntaxError параметра пойман compileall, устранён).
3. Guard доказан честно: smoke-скрипт как чужой модуль отклонён ДО мутации;
   легальный вызывающий (StateApplicator) проходит; alias-мутация read-DTO невозможна.
4. Латентный краш apply_deltas_only (F821 cause) закрыт: дельта применяется
   по канонической сатурации (50.0 → 47.5 при −5.0 × headroom 0.5).
