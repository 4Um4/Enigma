# Dynamic Ports Support Implementation

## Steps (Plan approved)

### 1. Edit backend/start_backend.bat ✅ Completed
- Add JSON parse for api_port after venv setup
- Replace hardcoded port 8000 with %API_PORT%
- Update echo messages

### 2. Edit backend/start_llm.bat ✅ Completed
- Add JSON parse for llm_port 
- Replace set PORT=8080 with %LLM_PORT%
- Update echo

### 3. Edit frontend/ui/index.html ✅ Completed
- Add loadApiPort() async fetch from runtime_ports.json
- Make API dynamic with fallback
- Adjust init()

### 4. Test ✅ Completed
- Run python backend/tests/test_startup_checks.py (generate JSON)
- Run backend/start_backend.bat → verify --port matches JSON api_port
- Run backend/start_llm.bat → verify --port matches llm_port
- Open frontend/ui/index.html → verify connects to dynamic port

### 5. Cleanup ✅ [Pending]
- Update any TODOs
- Mark complete

