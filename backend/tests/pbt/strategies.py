# backend/tests/pbt/strategies.py
"""
Генераторы данных (strategies) для property-based тестов.
АDR-013: Объекты создаются через from_legacy, не через конструктор.
"""
from hypothesis import strategies as st
from typing import Dict, Any

# Базовая стратегия: генерирует валидный psyche dict
psyche_strategy = st.fixed_dictionaries({
    "willpower": st.floats(min_value=0.0, max_value=1.0),
    "stress": st.floats(min_value=0.0, max_value=1.0),
    "state": st.sampled_from(["free", "coerced", "deceptive", "loyal", "comply", "reluctant", "delay", "misinterpret", "negotiate", "partial_comply", "distressed", "panicked", "dissociating", "broken", "conditioned", "counter_offer", "refuse"]),
    "loyalty_true": st.floats(min_value=0.0, max_value=1.0)
})

# Базовая стратегия: генерирует body_state dict
body_state_strategy = st.fixed_dictionaries({
    "current_hp": st.floats(min_value=0.0, max_value=100.0),
    "max_hp": st.floats(min_value=1.0, max_value=100.0),
    "shock": st.floats(min_value=0.0, max_value=1.0)
})

# Стратегия: генерирует минимально валидный NPC dict (legacy формат)
npc_legacy_strategy = st.fixed_dictionaries({
    "id": st.text(min_size=1, max_size=20, alphabet=st.characters(blacklist_categories=('Cs',))),
    "name": st.text(min_size=1, max_size=30, alphabet=st.characters(blacklist_categories=('Cs',))),
    "psyche": psyche_strategy,
    "body_state": body_state_strategy,
    "social_stats": st.dictionaries(
        keys=st.text(min_size=1, max_size=10),
        values=st.floats(min_value=0.0, max_value=100.0),
        max_size=5
    )
})

# Стратегия: генерирует список NPC
npcs_legacy_strategy = st.lists(npc_legacy_strategy, min_size=1, max_size=10)