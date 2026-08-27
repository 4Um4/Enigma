"""EXTENSION POINT :: World Economy. AUDIT #6 VERDICT=BURIED (2026-08).

Runtime-контур MarketState / TradeResolver / TransactionEngine / Traveller
захоронен: продашен-пути не резолвили сделки, экономического тика в
execute() не существовало (TODO подтверждён). Файлы — в _archive.

Контракт возврата (одна точка в TickOrchestrator.execute(), второго
pipeline не создавать):
    Post-Phase 0:  market.observe(deltas); traveller.generate_visits()
    Post-Phase 5:  trade.resolve(economic_intents) -> DeltaBuffer
Часть economic_profiles, живая сегодня, продолжает работать через DecisionHub.
"""
