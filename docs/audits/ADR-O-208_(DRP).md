# ADR-O-208 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-208` [STANDARD] **(DRP)**
### ADR-O-208: DRIVE RESOLUTION PIPELINE (DRP)

**1. Тип АДР:** ONTOLOGY (ADR-O). Личность становится вычислимым полем, а не хранимым словарем.

**2. Инвариант DRP (Единственный Закон Драйвов):**
> `EffectiveDrives = Projection(L0_Archetype, L1_Scars, Context)`
> Эффективные драйвы не существуют в персистентности. Они живут ровно один тик.

**3. Новая Каузальная Петля:**
*   **L0 (Архетип):** `NPCPersonality.drives_base` — неизменен.
*   **L1 (Шрамы):** `NPCIdentityL1.active_traits` — единственный mutable-аккумулятор деформаций.
*   **L2 (Проекция):** `NPCState.drives_projection` (readonly) — генерируется `DriveResolver` на старте тика.
*   **Мутация:** TIFL генерирует `StateDelta(target=L1)`.
*   **Коммит:** StateApplicator складывает дельту в `active_traits`. `npc_raw["drives"]` уничтожается как источник правды.



Files: N/A
