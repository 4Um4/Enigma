"""
path: /project/scripts/consumer_gap_debts.py
Назначение: debt-реестр Слоя 1 INV-CONSUMER-GAP (ADR-O-414). Каждая запись:
    census-ключ → authority-ID (roadmap v4.2 §7.x / GC-xx / S-номер / AUD-Dx).
    Это НЕ молчаливое исключение: реестр публичен, каждая запись = строка в диффе
    с обязательной ссылкой; запись без authority = CRITICAL линтера (§7 D2, урок P18).
    Запись здесь = санкционированный ответ на находку первичного аудита
    («находка ≠ приказ на исправление», вердикт Мастера). Удаление записи =
    починка поля владельцем ИЛИ декларация в манифесте Этапа 2 (mode=DEBT,
    тот же authority). Stale-запись (ключ ушёл из census) = CRITICAL.
Зависимости: не имеет (чистые данные).
Основные сущности: DEBT_FIELDS
"""
from typing import Dict

# ключ census ("domain.field") → authority-ссылка
# Канон: "body_state.energy": "NL-D9"  (§7.7:729 — выборка 3 State Consumer Gap)
DEBT_FIELDS: Dict[str, str] = {
    # ── Урожай первичного аудита Этапа 1 (reports/CONSUMER_GAP_AUDIT_E1.txt,
    #    перегон №7: NO_READER=18, NO_WRITER=14; строки → roadmap §7.8 CG-D) ──

    # ★ born-dead субъективные градиенты PK — прямая рифма RE-D2/GC-09B
    "perceptual_kernel.trust_gradient": "CG-D-01",
    "perceptual_kernel.dominant_emotion": "CG-D-02",
    "perceptual_kernel.last_hostile_direction": "CG-D-03",
    # Мёртвый read-контракт: DecisionView не конструируется никем
    # (memory_manager:903 — docstring = doc-drift); .state/.profile
    # замаскированы коллизиями имён — классификация по классу в Этапе 2
    "decision_view.identity": "CG-D-04",
    # Двойной носитель: typed-поле мёртво, жив legacy-дикт
    # (idle_services:66/75, input.py:115/304)
    "npc_state.affective_imprints": "CG-D-05",
    # Сирота P1 ARCH FIX (кэш стал эфемерным — timestamp остался)
    "npc_state.cache_timestamp": "CG-D-06",
    # Write-persist-dead: writers state_applicator:616/722 + npc_loader:791,
    # readers — только сериализация models
    "npc_state.last_intent_change": "CG-D-07",
    # Phantom-read: somatic_gate_probe:23 читает незаписываемый ключ
    # (легаси-имя; канон — shock_impulse)
    "body_state.shock": "CG-D-08",
    # Dead-twice: не передаётся даже в personality_from_legacy (:1356-1366)
    "npc_personality.gregariousness": "CG-D-09",
    # Loaded-dead: грузятся из конфига, не читаются никем
    "npc_personality.breakpoint": "CG-D-10",
    "npc_personality.loyalty_base": "CG-D-10",
    "npc_personality.can_awaken": "CG-D-10",
    # Write-only: writer memory_manager:343, читателей нет
    "event_memory.contract_ref": "CG-D-11",
    # Write-only: сжатие памяти без читателя (территория NL-10)
    "event_memory.compressed_from": "CG-D-12",
    # Diagnostic-only по собственной декларации (история смен ролей)
    "role_change_entry.from_role": "CG-D-13",
    "role_change_entry.to_role": "CG-D-13",
    # ADR-123: info-only by design (строковые флаги в InjuryProcessor — taboo)
    "state_delta.injury_dto.critical_effects": "ADR-123",
    # Carrier-gap: payload → сериализация → dict-ключ; ридер vital_state:198
    # читает по дикту body_state["injuries"] — статическая связка невидима
    "state_delta.injury_dto.functional_loss": "ADR-123",
    # S310 TRADE β-Stage 2: goods→EAT→body_state — задокументированные
    # «живые швы» (roadmap §0.1/хвосты S310)
    "state_delta.economic_payload.goods_delta": "S310",
    # Never-write с тремя читателями дефолта 1.0 (tick_utils:165,
    # body_engine:103, combat_subscriber:378); комментарий «placeholder
    # 1.0 до S2B.7» — S2B.7 закрыт (S309), масса так и не подключена
    "body_state.body_mass": "CG-D-14",
    # Документированная граница Слоя 1: writers через d[k]=v / .append() /
    # методы объектов / tuple-ключи / **-unpacking — невидимы тупому скану.
    # Точность добирает манифест Этапа 2 (CG-D-B1 в roadmap §7.8)
    "npc_state.pressure_accumulator": "CG-D-B1",
    "npc_state.strain_memory": "CG-D-B1",
    "npc_state.threat_accumulator": "CG-D-B1",
    "npc_state.trait_activation": "CG-D-B1",
    "npc_state.role_history": "CG-D-B1",
    "state_delta.trait_updates": "CG-D-B1",
}