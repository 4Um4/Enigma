# D61 LLM Outage Doctrine — живой прогон (COV-2)

Итог: GREEN=31 RED=1

| check | verdict | detail |
|---|---|---|
| p0_llm_online | GREEN | health не отвечает после самоподъёма |
| p0_router_initialized | GREEN |  |
| p0_status_online | RED | payload={'status': 'unconfirmed', 'reason': 'health offline: URLError: <urlopen error timed out>'} |
| g1_world_ticks | GREEN | ran=5 |
| g2_inflight_honest_failure | GREEN | inflight={'ok': False, 'exc': 'RuntimeError', 'msg': 'Все модели пула недоступны для capability=Capability.NARRATIVE'} |
| g2_pool_backoff_proven | GREEN | pool_status={'degraded': True, 'models': {'qwen_7b': {'backoff_until': 1791740429.7358878, 'active': True}}} |
| g2_status_outage | GREEN | payload={'status': 'outage', 'reason': 'pool backoff доказан (до 1791740430)'} |
| g2_pause_immediate | GREEN | paused=True modal=OUTAGE |
| g2_no_debounce_path | GREEN | unconfirmed=0 |
| g2_idle_frozen | GREEN | ticks_during_pause=0 |
| g2_run_turn_no_fake_narrative | GREEN | rr={'dm': 'Движок не ответил — мир ждёт.'} |
| g4_restart_success | GREEN | modal=SUCCESS reason= |
| g4_backoff_reset | GREEN | pool_status={'degraded': False, 'models': {}} |
| g4_status_online | GREEN | payload={'status': 'online', 'reason': ''} |
| g4_pause_holds_after_success | GREEN | ticks=0 paused=True |
| g4_resume_ticks_flow | GREEN | ticks=3 paused=False |
| g4_reply_end_to_end | GREEN | len=234 |
| g4_run_turn_e2e | GREEN | rr=ok |
| g5_outage_reproven | GREEN | fail={'ok': False, 'exc': 'RuntimeError'} |
| g5_pause_before_retry | GREEN | payload={'status': 'outage', 'reason': 'pool backoff доказан (до 1791740464)'} |
| g5_failed_with_reason | GREEN | modal=FAILED reason=exe_missing — C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama\llama_server_d61_sabotage_missing.exe |
| g5_pause_persists | GREEN | paused=True |
| g5_retry_fails_again | GREEN | modal=FAILED |
| g5_recovery_after_restore | GREEN | res={'restarted': True, 'reason': 'ok', 'detail': 'модель загружена и готова'} |
| g6_unconfirmed_status | GREEN | payload={'status': 'unconfirmed', 'reason': 'health offline: URLError: <urlopen error timed out>'} |
| g6_debounce_first_probe | GREEN | paused=False |
| g6_debounce_second_probe | GREEN | paused=True modal=OUTAGE |
| g6_watcher_live_debounce | GREEN | paused=True unconfirmed=2 |
| g7_modal_renders_all_states | GREEN |  |
| g7_button_map | GREEN |  |
| g7_rising_edge_hold_is_not_click | GREEN | hold=None |
| g8_final_server_healthy | GREEN | res={'restarted': True, 'reason': 'ok', 'detail': 'модель загружена и готова'} |