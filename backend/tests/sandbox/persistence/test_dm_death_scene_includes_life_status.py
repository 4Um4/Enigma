# backend/tests/sandbox/persistence/test_dm_death_scene_includes_life_status.py
"""
S76 P3: DM Death Scene Pipeline (ADR-140)

Верификация: DM получает life_status из player_state и генерирует
соответствующий нарративный блок. DM НЕ вычисляет смерть — только читает.

Rule 62: DM narration без проверки player life_status = каузальный обман.

Запуск: cd backend; python -m pytest tests/sandbox/persistence/test_dm_death_scene_includes_life_status.py -v --tb=short; cd ..
"""

import pytest
from app.agents.dm_agent import DmAgent
from app.services.game_loop.phase_6_avatar import avatar_to_prompt


# ── Фабрика: реалистичный pdata через avatar_to_prompt ──────────

class _MockAvatarAlive:
    """Живой аватар — проекция через avatar_to_prompt."""
    hp = 95; max_hp = 100; stress = 30.0
    emotion = type('E', (), {'value': 'neutral'})()
    will_state = type('W', (), {'value': 'free'})()
    posture = 'standing'; wounds = []; conditions = {}
    identity_integrity = 1.0
    body_state = {'life_status': 'ALIVE', 'pain': 0.0}


class _MockAvatarDead:
    """Мёртвый аватар — проекция через avatar_to_prompt."""
    hp = 0; max_hp = 100; stress = 100.0
    emotion = type('E', (), {'value': 'panic'})()
    will_state = type('W', (), {'value': 'broken'})()
    posture = 'collapsed'; wounds = []; conditions = {}
    identity_integrity = 0.0
    body_state = {'life_status': 'DEAD', 'pain': 80.0, 'blood_loss': 0.95}


# ── Тест 1: avatar_to_prompt пробрасывает life_status ──────────

def test_avatar_to_prompt_includes_life_status_alive():
    """Живой аватар: life_status = ALIVE в pdata."""
    result = avatar_to_prompt(_MockAvatarAlive())
    assert result.get('life_status') == 'ALIVE', \
        'ALIVE avatar must have life_status=ALIVE in pdata'


def test_avatar_to_prompt_includes_life_status_dead():
    """Мёртвый аватар: life_status = DEAD в pdata."""
    result = avatar_to_prompt(_MockAvatarDead())
    assert result.get('life_status') == 'DEAD', \
        'DEAD avatar must have life_status=DEAD in pdata'


def test_avatar_to_prompt_life_status_fallback_when_no_body_state():
    """Нет body_state: fallback = ALIVE (безопасное предположение)."""
    class _NoBodyState(_MockAvatarAlive):
        body_state = None
    result = avatar_to_prompt(_NoBodyState())
    assert result.get('life_status') == 'ALIVE', \
        'Missing body_state must fallback to ALIVE'


# ── Тест 2: DM Contract — death scene block ────────────────────

def test_dm_contract_dead_player_gets_death_block():
    """Мёртвый игрок: DM промпт содержит СМЕРТЬ ИГРОКА block."""
    agent = DmAgent()
    pdata = avatar_to_prompt(_MockAvatarDead())
    context = {'player_state': {'Player': pdata}, 'scene_state': {}}

    contract = agent._build_contract(
        location='tavern', actions_str='Player: последнее действие',
        rules_result={}, npc_result={}, world_result={}, context=context,
    )

    assert 'СМЕРТЬ ИГРОКА' in contract.user_prompt, \
        'DEAD player must trigger death scene block'
    assert 'необратимо' in contract.user_prompt, \
        'Death block must contain irreversible clause'
    assert 'МЁРТВ' in contract.user_prompt, \
        'Player state block must show DEAD marker'


def test_dm_contract_alive_player_no_death_block():
    """Живой игрок: DM промпт НЕ содержит death block."""
    agent = DmAgent()
    pdata = avatar_to_prompt(_MockAvatarAlive())
    context = {'player_state': {'Player': pdata}, 'scene_state': {}}

    contract = agent._build_contract(
        location='tavern', actions_str='Player: осматривает комнату',
        rules_result={}, npc_result={}, world_result={}, context=context,
    )

    assert 'СМЕРТЬ ИГРОКА' not in contract.user_prompt, \
        'ALIVE player must NOT get death scene block'


# ── Тест 3: DM НЕ вычисляет смерть — только читает ─────────────

def test_dm_death_block_only_from_player_state_not_computed():
    """Death block появляется ТОЛЬКО если player_state.life_status=DEAD.
    
    Если pdata не содержит life_status (legacy формат) — death block НЕ появляется.
    DM не имеет собственной логики определения смерти.
    """
    agent = DmAgent()
    # Legacy pdata без life_status
    legacy_pdata = {
        'hp': '0/100', 'stress': 100.0, 'emotion': 'panic',
        'wounds': 'голова(тяжёлое)', 'conditions': 'нет',
        'posture': 'collapsed', 'will_state': 'broken',
        'identity_integrity': 0.0,
    }
    context = {'player_state': {'Player': legacy_pdata}, 'scene_state': {}}

    contract = agent._build_contract(
        location='tavern', actions_str='Player: падает',
        rules_result={}, npc_result={}, world_result={}, context=context,
    )

    # DM НЕ должен угадывать смерть по косвенным признакам (hp=0, stress=100)
    assert 'СМЕРТЬ ИГРОКА' not in contract.user_prompt, \
        'DM must NOT compute death from indirect signals — only from life_status'