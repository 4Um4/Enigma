# ARCHITECTURE FLOW (Auto-generated)

> Внимание: Этот файл сгенерирован автоматически из `architecture/*.yaml`.
> Не редактируйте его вручную. Изменяйте YAML файлы и запускайте `python build_graph.py`.

## 🔗 Топология системы (Flowchart)

```mermaid
flowchart TD

    %% === БАЗОВЫЕ СТИЛИ ===
    classDef ui fill:#e0f7fa,stroke:#006064,stroke-width:2px;
    classDef application fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px;
    classDef domain fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef infrastructure fill:#ffebee,stroke:#b71c1c,stroke-width:2px;
    classDef forbidden fill:#f66,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5;

    end

    %% === ПОТОКИ ДАННЫХ ===

    %% === АРХИТЕКТУРНЫЕ ЗАПРЕТЫ ===
```

## 📊 Каузальная Карта (Micro-details)

> Детальная логика работы системы: условия срабатывания, привязка к коду и ADR.

### Потоки данных (Edges)

| Откуда | Куда | Описание | Условие / Логика | Код | ADR/GAP |
|--------|------|----------|------------------|-----|---------|

### Архитектурные запреты (Constraints)

| Источник | Цель | Правило | Код/Документ |
|----------|------|---------|--------------|
