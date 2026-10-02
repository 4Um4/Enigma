# ADR-NET-PARSER-V2 [FIX] **IMPACT** (S{MAX+1})

## Changed Domains
- observability (ADR-Net parser; симуляция не затронута)

## Downstream Consumers
- adr_graph.ADRGraphBuilder (контракт run_parser: {adr_id: ADRNode} — сохранён), adr_cli.get_impact, INV-ADR-NET (IPT), Правила Фикса БАГОВ §1 (ADR-Net CLI)

## Runtime Impact
- граф 242 ADR-узлов / 55 with_files; 411n/265e; парсинг +~50 мс при старте CLI

## Sandbox Tests
- backend/tests/micro/test_adr_files_forms.py (5 форм)

## Rollback
- git revert df83c2ce