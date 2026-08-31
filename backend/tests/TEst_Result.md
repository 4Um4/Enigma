(.venv) PS C:\DDD\Codex\VSC_Enigma\Enigma\backend> $env:PYTHONPATH="."; pytest tests/test_npc_state_r6.py
=========================================================================================================================== test session starts ===========================================================================================================================
platform win32 -- Python 3.11.9, pytest-8.3.3, pluggy-1.6.0
rootdir: C:\DDD\Codex\VSC_Enigma\Enigma\backend
configfile: pytest.ini
plugins: anyio-4.12.1
collected 4 items                                                                                                                                                                                                                                                          

tests\test_npc_state_r6.py F...                                                                                                                                                                                                                                      [100%]

================================================================================================================================ FAILURES ================================================================================================================================= 
_________________________________________________________________________________________________________________________ test_r6_default_values __________________________________________________________________________________________________________________________ 

    def test_r6_default_values():
        """
        Проверяет:
        Новые параметры личности имеют корректные дефолты.

        Критично для:
        стабильного старта новых NPC.
        """

        npc = NPCState(npc_id="test_npc")

        assert npc.resentment == 0.0
        assert npc.dependency == 0.0
>       assert npc.identity_integrity == 100.0
E       AssertionError: assert 1.0 == 100.0
E        +  where 1.0 = NPCState(npc_id='test_npc', stress=0.0, resentment=0.0, dependency=0.0, identity_integrity=1.0, pressure_resistance=1....ent_change=0, relationship_cache={}, cache_timestamp=0, narrative_cache=(), cached_position=None, position_valid=False).identity_integrity

tests\test_npc_state_r6.py:32: AssertionError
============================================================================================================================ warnings summary ============================================================================================================================= 
..\.venv\Lib\site-packages\pydantic\_internal\_config.py:291
  C:\DDD\Codex\VSC_Enigma\Enigma\.venv\Lib\site-packages\pydantic\_internal\_config.py:291: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.9/migration/
    warnings.warn(DEPRECATION_MESSAGE, DeprecationWarning)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
========================================================================================================================= short test summary info ========================================================================================================================= 
FAILED tests/test_npc_state_r6.py::test_r6_default_values - AssertionError: assert 1.0 == 100.0
================================================================================================================= 1 failed, 3 passed, 1 warning in 0.07s ================================================================================================================== 
(.venv) PS C:\DDD\Codex\VSC_Enigma\Enigma\backend> $env:PYTHONPATH="."; pytest tests/test_npc_state_r6.py
=========================================================================================================================== test session starts ===========================================================================================================================
platform win32 -- Python 3.11.9, pytest-8.3.3, pluggy-1.6.0
rootdir: C:\DDD\Codex\VSC_Enigma\Enigma\backend
configfile: pytest.ini
plugins: anyio-4.12.1
collected 4 items                                                                                                                                                                                                                                                          

tests\test_npc_state_r6.py .FFF                                                                                                                                                                                                                                      [100%]

================================================================================================================================ FAILURES ================================================================================================================================= 
_________________________________________________________________________________________________________________________ test_r6_value_clamping __________________________________________________________________________________________________________________________ 

    def test_r6_value_clamping():
        """
        Проверяет:
        Значения автоматически ограничиваются диапазоном.

        Критично для:
        защиты от переполнения при накоплении давления.
        """

        npc = NPCState(
            npc_id="test_npc",
            resentment=999,
            dependency=-50,
            identity_integrity=250 # Pydantic или геттер сожмут это до 1.0
        )

        # Обида и зависимость могут оставаться на шкале до 100,
        # но целостность личности жестко ограничена 1.0
        assert npc.resentment == 100.0
        assert npc.dependency == 0.0
>       assert npc.identity_integrity == 1.0
E       AssertionError: assert 100.0 == 1.0
E        +  where 100.0 = NPCState(npc_id='test_npc', stress=0.0, resentment=100.0, dependency=0.0, identity_integrity=100.0, pressure_resistanc...ent_change=0, relationship_cache={}, cache_timestamp=0, narrative_cache=(), cached_position=None, position_valid=False).identity_integrity

tests\test_npc_state_r6.py:60: AssertionError
____________________________________________________________________________________________________________________ test_r6_snapshot_contains_fields _____________________________________________________________________________________________________________________ 

    def test_r6_snapshot_contains_fields():
        """
        Проверяет:
        snapshot() возвращает новые параметры личности.

        Критично для:
        логирования динамики слома.
        """

        npc = NPCState(
            npc_id="test_npc",
            resentment=999,
            dependency=-50,
            identity_integrity=250
        )

        snap = npc.snapshot()

        assert "resentment" in snap
        assert "dependency" in snap
        assert "identity_integrity" in snap

        assert snap["resentment"] == 100.0
        assert snap["dependency"] == 0.0
>       assert snap["identity_integrity"] == 1.0
E       assert 100.0 == 1.0

tests\test_npc_state_r6.py:91: AssertionError
_____________________________________________________________________________________________________________________ test_r6_legacy_adapter_defaults _____________________________________________________________________________________________________________________ 

    def test_r6_legacy_adapter_defaults():
        """
        Проверяет:
        Старые данные корректно получают новые параметры.

        Критично для:
        совместимости старых сохранений.
        """

        legacy_data = {
            "psyche": {}
        }

        npc = NPCStateAdapter.from_legacy(legacy_data)

        assert npc.resentment == 0.0
        assert npc.dependency == 0.0
>       assert npc.identity_integrity == 1.0
E       AssertionError: assert 100.0 == 1.0
E        +  where 100.0 = NPCState(npc_id='unknown', stress=0.0, resentment=0.0, dependency=0.0, identity_integrity=100.0, pressure_resistance=0...st': 0.0, 'fear': 0.0, 'debt': 0.0}, cache_timestamp=0, narrative_cache=(), cached_position=None, position_valid=False).identity_integrity

tests\test_npc_state_r6.py:115: AssertionError
============================================================================================================================ warnings summary ============================================================================================================================= 
..\.venv\Lib\site-packages\pydantic\_internal\_config.py:291
  C:\DDD\Codex\VSC_Enigma\Enigma\.venv\Lib\site-packages\pydantic\_internal\_config.py:291: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.9/migration/
    warnings.warn(DEPRECATION_MESSAGE, DeprecationWarning)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
========================================================================================================================= short test summary info ========================================================================================================================= 
FAILED tests/test_npc_state_r6.py::test_r6_value_clamping - AssertionError: assert 100.0 == 1.0
FAILED tests/test_npc_state_r6.py::test_r6_snapshot_contains_fields - assert 100.0 == 1.0
FAILED tests/test_npc_state_r6.py::test_r6_legacy_adapter_defaults - AssertionError: assert 100.0 == 1.0
================================================================================================================= 3 failed, 1 passed, 1 warning in 0.09s =======================================================================================

«Фаза A Шаг 9.6 (финал): digest-суффикс mem_id; 22/22 замков, IPT 45/45; дамп: уникальные id, одинаковый контент дедупится, Торнин imp=0.8; PROBE 9.7: подписчик NPC_SPOKE не зарегистрирован в run_turn-wiring — цель финального фикса».