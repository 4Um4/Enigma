import pathlib

FILE_PATH = pathlib.Path("backend/app/services/npc/state_applicator.py")

FIXES = [
    # 1. Добавляем импорты WillConflictPayload и KernelRNG
    (
        "from app.models.state_delta import StateDeltas, StateChange, LegacyStateDeltaAdapter",
        "from app.models.state_delta import StateDeltas, StateChange, LegacyStateDeltaAdapter\nfrom app.models.will_state import WillConflictPayload\nfrom app.services.npc.kernel_rng import KernelRNG"
    ),
    # 2. Явная типизация списка
    (
        "_l1_events: list = []  # C7 FIX: Инициализация списка для L1 событий",
        "_l1_events: list[Any] = []  # C7 FIX: Инициализация списка для L1 событий"
    ),
    # 3. Явный float для StateChange
    (
        "delta=wound.severity.value,",
        "delta=float(wound.severity.value),"
    ),
    # 4. Убираем кавычки у KernelRNG
    (
        "rng: Optional[\"KernelRNG\"] = None,",
        "rng: Optional[KernelRNG] = None,"
    ),
    # 5. Типизация dict
    (
        "all_npcs_raw: List[dict],",
        "all_npcs_raw: List[dict[str, Any]],"
    ),
    # 6. Обработка Optional у DeltaDomain
    (
        "key=lambda d: _DOMAIN_APPLICATION_ORDER.get(d.domain, _DEFAULT_ORDER),",
        "key=lambda d: _DOMAIN_APPLICATION_ORDER.get(d.domain if d.domain else DeltaDomain.PERCEPTION, _DEFAULT_ORDER),"
    )
]

def main():
    content = FILE_PATH.read_text(encoding="utf-8")
    applied = 0
    
    for old, new in FIXES:
        if old in content:
            content = content.replace(old, new)
            applied += 1
            print(f"[FIX] Applied: {old[:50]}...")
        else:
            print(f"[WARN] Pattern not found: {old[:50]}...")
            
    FILE_PATH.write_text(content, encoding="utf-8")
    print(f"\nDone. Applied {applied}/{len(FIXES)} fixes.")

if __name__ == "__main__":
    main()