# Задачи Enigma - План развития

## Архитектура которую нужно построить

Целевая схема:

```
Enigma backend

Agents
  │
  ├─ DM agent
  ├─ Rules agent
  ├─ NPC agent
  ├─ World agent
  └─ Memory agent

        │
        ▼

Model Router

        │
        ▼

LLM Server (llama.cpp router mode)

        │
 ┌──────┼────────┬───────────┐
 ▼      ▼        ▼           ▼

Qwen3.5-9B
Qwen2.5-7B
Saiga-7B
YandexGPT-8B
```

Каждый агент просто указывает:
- model="npc"
- model="dm"
- model="rules"

## Что реально возможно:

| модель | VRAM |
| ------ | ---- |
| 7B Q4  | ~4GB |
| 9B Q4  | ~5GB |

Одновременно в VRAM: 1 модель

Но router mode делает swap моделей:
- agent → request model
- server → load model
- respond
Это нормально.

## Стратегия LLM инфраструктуры

Я бы сделал 3 уровня моделей:

**Уровень 1 (быстрые)**
- Rules agent: saiga_mistral_7b_model-q4_K.gguf
- Memory agent: saiga_mistral_7b_model-q4_K.gguf
- World simulation / DM agent: qwen3.5-9b

**Уровень 2 (диалоги)**
- NPC: YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf

**Уровень 3 (мозг)**
- qwen2.5-7b-instruct-q4_k_m.gguf

## Следующие шаги:

### 1. Запустить router mode
- Тест запроса
- Тест запроса

### 2. Добавить router в model_router.py
- Каждый агент выбирает модель

### 3. GPU offload параметры
для 3070ti:
- --n-gpu-layers 30
- --ctx-size 4096
- --threads 8

---

## Следующий критический шаг (после моделей)

### JSONL memory

### Следующий шаг: vector DB
Я бы поставил:
- Qdrant или Chroma

### Архитектура памяти (идеальная):

```
WORLD_CANON
     │
     ▼
Vector DB

CAMPAIGN_MEMORY
     │
     ▼
SQLite

SESSION_MEMORY
     │
     ▼
RAM
```

---

## Следующий большой шаг после этого:

### Function calling для агентов

Пример:

DM агент вызывает:
- roll_check()
- get_npc_state()
- update_world_event()

Следующий уровень (Stage 3)

Когда этот UI заработает, система готова к:

WebSocket архитектуре

где исчезнут:

heartbeat
polling
race conditions

и Enigma станет реальным realtime-движком.

Если хочешь — я дальше покажу архитектуру WebSocket слоя,
которая превратит ваш проект в настоящий игровой сервер, а не HTTP-чат.