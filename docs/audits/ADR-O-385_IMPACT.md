# ADR-O-385 Speech-Tube Sanitation — Impact Audit
> Детальный аудит одного ADR. Единый атлас: docs/ADR (Architecture Decision Records).md

## Суть
Пять раундов археологии доказали: речевой контур player→NPC существует в коде целиком
(PLAYER_SPOKE → perception_filter/_can_hear → SocialInputProjector → DecisionHub →
DialogueRequest → DialogueExecutor → NPC_SPOKE → подписчики; pair-STM двусторонний:
dm_phase:169 — игрок, npc_dialogue_subscriber — NPC). Player Dialogue подключается к
трубе, не строит новую (§ENIGMA-002: DialogueSession/DialogueField/SpeechEvent-субстраты
не введены).

Закрыты четыре класса дефектов:
- Р-А: SELF_TALK_SENTINEL (dom/communication) — солилоквий = экстернализованное
  бормотание; фантомный агент «soliloquy» лишён STM-сессий, рёбер отношений, L1-записей
  (guard в подписчике); подслушивание игроком (journal, dist<8) сохранено; лог-фантом мёртв.
- Р-Б1: NpcDialogueSubscriber — седьмой write-маршрут замкнут на RelationshipWriteGate
  (паттерн M1b.2.4 wrap-own-gate); D2-греп прямых .update() — 0.
- Р-Б2: мембрана адресата PerceptualKernel.can_observe (S192-паритет с
  ClaimEventSubscriber), fail-open по S198-прецеденту (dict-события / нет позиции / ошибка
  дистанции — адресат слышит).
- Р-В: SpeechExposure Contract — SSOT-лестница exposure_radius() (private 0 / secret 1.5 /
  whisper 3 / normal 6 / loud 10 / shout 15); parity со стороной игрока держится тестом
  test_speech_radius_parity; materializer / adapter / working_memory_tick комплаентны;
  999-утечка ambient-реплик закрыта; secret→whisper (адресат слышит, ADR-O-311-паритет).

## Changed Domains
communication, social (write-path), perception (мембрана/радиусы), memory (STM-гигиена),
events (продюсеры NPC_SPOKE).

## Downstream Consumers
SocialInputProjector (состав LISTEN-слушателей сузился: normal 10→6, ambient 999→6),
ClaimEventSubscriber, End-Screen (фантом инертен), DialogueExecutor (pair-STM).

## Runtime Impact
O(1) на реплику, ноль новых сторов/DTO. Дельты: NPC-normal-речь 10→6; солилоквий 10→3
(+whisper); ambient 999→6; secret-адресат через адаптер глух→слышит.

## Sandbox Tests
tests/micro/test_self_talk_sentinel.py (6), tests/micro/test_speech_exposure.py (4),
IPT 45/45 (два полных прогона), drift-зонд WARNING=0, дрейф A-E=0 (CSV).

## Rollback
Р-А/Р-Б: git revert a92278cc. Р-В: внутри bac0c6d6 (communication / materializer /
adapter / working_memory_tick).

## Долги
- LISTEN A/B полный замер (stdout слеп, CSV без колонки, worktree занят) — до TAB-среза.
- D5: дефолт EventDTO.create radius=999.0 — разоружение после аудита вызывателей.
- Р-Г: журнал игрока (dist<8.0 без visibility) → порог из event.radius.
- Doc-drift: relationship_store путь в DTO Registry (svc/social/ vs svc/memory/).
- Stage-2 (Люся-наблюдатель): SECRET-Proposition + self-relevance — M2/D-координация.
