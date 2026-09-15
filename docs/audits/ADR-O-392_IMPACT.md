# ADR-O-392 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: docs/ADR (Architecture Decision Records).md

## Changed Domains
disclosure (вердикт → вербализация) · player_epistemics (EAVESDROP-метка) · execution (DialogueExecutor) · events (NpcDialogueSubscriber)

## Downstream Consumers
DiscoveryBridge (поверхности с secret_id/content_class — контракт не менялся, ожили FULL/CLUE-ветки map_surface) · UI-журнал игрока (тексты наблюдений «подслушано у X про Y» при метке) · ClaimEventSubscriber (НЕ тронут) · DialogueMaterializer (НЕ тронут — exposure уже был в payload)

## Runtime Impact
+1 retrieve_knowledge на NPC→NPC canonical-реплику в подписчике (O(narrative_cache), ~мкс) — отмечен как тайминг-чувствительный вклад в flaky-профиль INV-DIALOGUE-STM (механизм: позиционная хрупкость, НЕ регресс; см. досье W-фазу). Вердикт P5 — перенос существующего вызова по времени (до LLM), не новый.

## Sandbox Tests
tests/gameplay/test_p7_disclosure_verbalization.py — 9/9: директива в промпте · DENY-без-уровня · один вердикт (monkeypatch-счётчик) · LLM-OFF · whisper→FULL→IDENTIFIED · normal→CLUE · unwired-регресс E2 · no-knowledge · монотонность двух каналов. Регрессия: E1+E2+E3+P5+bridge 25/25; tests/gameplay 70/71 (FAILED = зарегистрированный gc09b-R2, pre-existing, git-доказано).

## Rollback
Три файла атомарно откатываемы (git checkout); wiring = одна строка game_loop:446; DTO/SSOT не менялись; тест-файл самодостаточен. Откат wiring гасит P7-B production-метку, не ломая E2 (fallback (None,None) = E2-наследие).

## Открытые долги сессии
DEBT-E1-WIRING (E1/P7-A production-проводка отсутствует) · FLAKE-CANDIDATE INV-DIALOGUE-STM (позиционная хрупкость: сетап зависит от случайных позиций NPC к тику 39 при async-слое; механизм доказан зондом MEMBRANE-CUT d=7.3; сетап-фикс — отдельная сессия с санкцией, IPT не ретушируется молча) · ruff-ордера game_loop 15 (pre-existing, scope-freeze).
