## ADR-159 [FIX] Shelter Urge Saturation — BED Role Extension & DEFAULT Fallback

**Проблема:** `shelter_urge` рос до 1.0 и никогда не удовлетворялся — в city_gate и market_square нет BED-узлов. `resolve_node(role=NodeRole.BED)` возвращал None. NPC стояли на месте с максимальной потребностью.

**Причина:** `RoleResolver._ROLE_KEYWORDS[NodeRole.BED]` не содержал "караульн" — Караульня/Караульная не распознавались как места для сна. При отсутствии BED-узлов fallback не существовал.

**Фикс 1:** Добавлено ключевое слово `"караульн"` в `RoleResolver._ROLE_KEYWORDS[NodeRole.BED]` → Караульня/Караульная стали BED-узлами.

**Фикс 2:** Добавлен DEFAULT fallback в `_check_need_driven_movement` — если `resting` не находит BED, ищет DEFAULT узел (скамейка, земля). `sleeping` требует BED строго, `resting` — нет.

**Файлы:**
- `backend/app/services/spatial/role_resolver.py` — +1 ключевое слово
- `backend/app/services/npc/life_engine.py` — +7 строк fallback логики

**Taboo:**
- ❌ Добавлять новые потребности без `_NEED_ROLE_MAP` записи (ADR-150, сохраняется)
- ❌ `resting` без semantic fallback при отсутствии BED (теперь DEFAULT fallback)