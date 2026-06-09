# ADR-O-112 Impact Audit: Actor-Agnostic Combat Pipeline (Universal Violence)

**Тип АДР:** ONTOLOGY (ADR-O) — Введение новой фундаментальной абстракции
**Статус:** PROPOSED

## 1. Обоснование (Устав §ENIGMA-001)

Текущий боевой конвейер асимметричен: `Player → NPC`. Это искусственный ограничитель причинной глубины. 
Внедрение актор-агностичной модели (`Any Actor → Any Actor`) увеличивает количество устойчивых причинных структур (смерть, месть, репутация) и длину причинных цепочек (убийство → свидетель → вера → политика) на порядки. 

Без универсального насилия убеждения (R8) бесполезны, так как не имеют смертельных последствий.

## 2. Затронутые домены
- `combat` (Полная реорганизация подписок и снапшотов)
- `will` (Intent.ATTACK должен проходить до EventDTO)
- `physiology` (Урон должен применяться к любому телу)
- `perception` (Свидетели боя должны видеть агрессора и жертву симметрично)
- `memory/beliefs` (Потребители смертей и ранений)

## 3. Связанные потребители (Downstream)
- `DecisionHub` (Генератор ATTACK)
- `IntentEventAdapter` (Транслятор в событие)
- `CombatSubscriber` (Маршрутизатор и сборщик снапшотов)
- `StateApplicator` (Исполнитель урона)
- `PlayerAvatarService` (Владелец состояния аватара)

## 4. Бюджет ресурсов
- RAM: +0% (Используются существующие словари и DTO)
- Tick Latency: +5-10% на фазе 8 (из-за универсального резолва снапшотов)

## 5. Откат (Rollback)
Откат возможен путем возврата к жесткой проверке `if actor_id == "player"` в CombatSubscriber. Новые EventType будут просто игнорироваться.

## 6. Регрессия
- `tests/sandbox/micro/test_command_compliance.py` (Проверка ATTACK)
- `tests/test_impact_engine.py` (Проверка чистой физики)
- Требуется новый тест: `tests/sandbox/phenomenology/test_actor_agnostic_combat.py`

## 7. План внедрения (4 Этапа)

### Этап 1: Труба Агрессии (Intent → Event)
Убрать хардкод `npc_spoke` в `IntentEventAdapter`. Маппить `Intent.ATTACK` → `EventType.ACTOR_ATTACKS`.

### Этап 2: Универсальный Снапшот (Event → Target)
Внедрить `UniversalSnapshotBuilder`. Если `target_id == "player"`, собирать снапшот из `AvatarState`, а не из `npc_by_id`.

### Этап 3: Универсальный Урон (Impact → State)
Научить `StateApplicator` применять `PhysiologyPayload` к `AvatarState.body_state`, если `npc_id == "player"`.

### Этап 4: Смерть и Последствия
Проверка `hp <= 0` или `shock_impulse >= 1.0` для любого Actor. Генерация `EventType.ACTOR_DEATH`. Публикация в память свидетелей.