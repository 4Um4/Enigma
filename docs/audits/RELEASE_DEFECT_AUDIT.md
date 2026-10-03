# RELEASE DEFECT AUDIT v2 — Bloodloom (финал, сессия «релиз ≠ ПК»)

**Статус:** аудит закрыт. 12 дефектов закрыто, 1 known-issue (решение Мастера), 3 долга зафиксированы.
**IPT: 45/45.** Дерево чистое, готово к сборке v0.5.4.0.8.

## §A. Почему релиз отличался от ПК — 4 доказанных механизма

1. **`architecture/` вырезалась robocopy** (`/XD ... architecture ...` в publish_release.ps1) → runtime-контракты отсутствовали в пакете (BUG-04). Закрыто: архитектура возвращена + content-gate.
2. **Сборка без гейтов в произвольные моменты** — staging = слепок момента; между релизами код уезжал (BUG-02/03: в dev уже исправлены, у пользователя старьё). Закрыто: content-gate + сборка свежим деревом.
3. **Inno Setup не удалял исчезнувшие файлы** при установке поверх (нет `[InstallDelete]`) — мусор накапливался вечно. Закрыто: секция InstallDelete.
4. **Мусор корня затягивался в staging** robocopy'ем (backup_*, *.bak, eatlog, TODO, backend\backend). Закрыто: /XD + /XF + ручная санация.

## §B. Реестр

| BUG | Суть | Фикс |
|-----|------|------|
| 01 | Краш тика: intent без target (REQUEST_SERVICE) | Слой 2: whitelist валидатора +REQUEST_SERVICE (npc_state.py); Слой 1: деградация OBSERVE в DecisionHub при target=None |
| 02/03 | Мёртвый _allies_cache; import dataclasses | Уже в dev; лечится пересборкой |
| 04 | architecture/*.yaml не в релизе | /XD-патч + content-gate (сборка падает при пустой architecture/) |
| 05 | 634 OVERFLOW дропа | Мягкий backpressure: ambient дропается при ≥70% заполнения (dialogue_queue.py) |
| 06 | Магический ×100 stress | Named-константы SOCIAL_TO_NPC_STRESS_SCALE/SOCIAL_STRESS_CAP=25 + clamp (propagation.py); персонализация уже в продюсере (_distort_intensity по trust) |
| 07 | Белый/бежевый фон спрайтов | Авто-детект фона по углам тайла в get_rect() (sprite_registry.py); ползунок редактора работает в игре; outline→1 (32 записи tavern.json) |
| 08 | diagnostics/ нет в релизе | /XD-патч |
| 09-11 | Мусор (backup_*, .bak, eatlog, TODO, backend\backend, test_campaign, calibration, build_graph) | Санация + /XD + /XF + iss Excludes + [InstallDelete] |
| 12 | 38 FAILED shadow-компилятора / тик | boundary_arrival → boundary snap (диспетчер); нормализация префикса loc:node в completion; cross-chunk гейт (фиксация факта без геометрии чужого графа) |
| 13 | SC-4 drift (NPC в координатах чужой локации) | KNOWN-ISSUE — решение Мастера: не чинить |

## §C. Долги

- DEBT-S72-7: личностный множитель stress (fear/willpower) — после прокидки профилей в SocialEngine;
- DEBT-E12: мёртвая fallback-ветка event_compiler :215+ после cross-chunk гейта;
- DEBT-BUG05-v2: адаптивный порог backpressure из CalibrationProfile.

## §D. Гейты против повтора

Content-gate сборки; [InstallDelete]; расширенный FAILED-контекст (постоянный); IPT-хвост после каждого патча (правило подтверждено срывом: преждевременное «закрыто» по BUG-12 стоило цикла отката).

