"""
Causal Audit Script
Запуск: powershell -ExecutionPolicy Bypass -File .\scripts\causal_audit.ps1
"""

cd backend

pytest tests/sandbox/test_causal_movement.py
pytest tests/sandbox/system/test_causal_closure.py
pytest tests/sandbox/test_micro_macro_locomotion.py

cd ..