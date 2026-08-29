# ADR-O-369 Impact Audit
> Детальный аудит одного ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- SOCIAL — регистрация нового SSOT-домена КАК КОНТРАКТА (7 компонентов §4.1 + 20 событий §5.5 + 6 предикатов §5.4); рантайм-изменений НЕТ (M0).
- ARCHITECTURE — architecture/relationship_engine.yaml (45 узлов, 15 edges, 9 constraints).
- ENFORCEMENT — scripts/lint_relationship_engine.py + CI-шаг + pre-commit hook.
- DOCS — ADR-атлас, DTO-реестр (секция 13), настоящий аудит.

## Downstream Consumers
- Фазы B–K ТЗ-RE-01 (RelationshipStateStore M1, NeedProvider B, AttractionVector+PartnerDesire C, семантика событий M2/D, предикаты M4/E, Satisfaction G, фрустрация H, RU+сценарный слой K) — каждая читает контракт как входной гейт.
- CI/pre-commit — каждый будущий RE-патч проходит линтер.
- build_graph.py — потребитель yaml (совместимость подтверждена: лоader читает только type/layer/label/style + инжектит domain; служебные ключи узлов игнорируются).
- Калибровочный полигон RE (фаза M) — presets, INV-1, О-2.

## Runtime Impact
- RAM: 0. CPU: 0. Сейвы: не затронуты. Ни один файл backend/app не изменён (M0: «рантайм не меняется»).

## Sandbox Tests
- M0 (контрактный): `python scripts/lint_relationship_engine.py` — зелёный; базовая линия IPT 44/44 (включая INV-ADR-NET, INV-LLM-EXILE, INV-KERNEL-RNG, INV-EPISTEMIC-BOUNDARY — запреты N7/N14/N2 опираются на них).
- Отложенные (зарегистрированы в prohibitions с фазами): С6/Сат6/№22 (G); трёх-состояний (H); четырёх-паттернов ПД (C); линз-аудит §11.2 п.16 (E); РУ6/п.13/п.14/п.15 (K); INV-1 (J); О-2 (полигон).

## Rollback
Атомарный: удалить yaml + линтер + 3 doc-записи + 2 регистрации CI. Рантайм и сейвы не затронуты.

## Verification Log (гейты M0 — все зелёные)
1. ADR number verified: max(атлас) = 368 → ADR-O-369.
2. frustration writers = 0 (grep backend/app) → FrustrationByNeedProjection = derived read-only (вердикт Мастера).
3. tombstone residual scan = 0 (backend/app, 24 паттерна); allowlist канона = ровно 3 файла config/.
4. build_graph loader: инжекция domain подтверждена кодом (строки 43–79).
5. node-id анти-коллизия: 45 имён свободны в 22 существующих yaml.
6. IPT baseline: 44/44, 0 CRITICAL (долг S217 L4 — downloader.py ×3 except:pass — закрыт попутно, фиксация в MUTATIONS при закрытии сессии).
