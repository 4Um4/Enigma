# ADR-O-388 Impact Audit
> Детальный аудит одного ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Решение
Testimony-симметрия player→NPC (Stage-1.5): PLAYER_SPOKE с DM-вектором → мембрана →
ClaimEvent → belief слышащего NPC. Не понимание речи: proposition только из DM-классификации
(ADR-035); без вектора — no-op. Self-relevance/secret — M2/D, вне Stage-1.5.

## Changed Domains
epistemics (новый входной канал убеждений для NPC: player-testimony), events (подписка
PLAYER_SPOKE в epistemic core).

## Downstream Consumers
DecisionHub слушателей (belief → эпистемические модификаторы), будущий Stage-2 (M2/D
self-relevance — получит готовый testimony-слой), GORAN-гейты (без изменений: канал
NPC→player не тронут).

## Runtime Impact
O(1) на PLAYER_SPOKE при наличии вектора (маппинг + делегация в существующий
on_claim_event с его мембраной O(N)); no-op без вектора. Персистенция: без новых ключей.

## Sandbox Tests
micro 30/30 (player_speech_claim 4 + liveness 7 + materializer 4 + sentinel 11 +
exposure 4); gc_social_test: S1 4/4, S3 7/7, S2.5 жив; S2.6–8 — LLM-зависимые (механизм
= замок; end-to-end = живая сессия); IPT 45/45; GORAN β+vertical GREEN.

## Rollback
Снять подписку PLAYER_SPOKE в _register_epistemic_core — канал глохнет, остальное
нетронуто (метод on_player_spoke остаётся мёртвым кодом до удаления).

## Открытые пункты (честно)
1. DM-классификация ACCUSE недетерминирована при живом LLM (UNCERTAIN возможен) —
   кандидат S122-fast-path для обвинительной лексики; решение Мастера.
2. read_trust=None в harness-мире: пара player не создаётся player_interacts-путём —
   кандидат на аудит V2-бутстрапа пар.
3. S3-атака не доводит hp до 0 за окно 4 тиков (β-fallback авторинга законен; окно/урон —
   калибровка сценария, не production).
4. S2.6–8 end-to-end — чеклист живой сессии (единый с пп.1–2 GC-01).

## Ретракции
№191/№194/№195: три «призрачные формы» (несуществующие _shared_context / DTO в schemas /
модуль intent_dto) — допущения по памяти против диска; урок: СТОП после второго призрака,
следующий ход = grep.