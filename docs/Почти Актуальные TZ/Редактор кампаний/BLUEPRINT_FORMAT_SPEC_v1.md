
## 4. Слои (нумерация §2.2)

**4.1 geometry (Форма).** `{source: "primitive"|"imported", ref?, size{w,h,d}, rotation, parts[]}`. Часть: `{id, shape|ref, pivot:[x,y], anchors:[{kind: wall|floor|object, spec}]}`; в v1 `parts` может быть пуст (объект = одна часть — сегодняшняя модель). Источник знает только слой 1 (§8.1).

**4.2 appearance (Вид).** `{palette?, variants[], sprites: {state: sprite_ref}, animations?}`. Форма `sprite_ref` — СВЕРИТЬ С ФАКТОМ (сегодня в коде: 3-элементная `[sheet,col,row]` или 7-элементная `[sheet,x,y,w,h,threshold,outline]`); в спеке не фиксировать до археологии.

**4.3 physics (Физика).** `{passability{walk,jump_over,crawl_under,climb_on,walk_around}, cover, height?, mass?, durability?, movable, destructible, collision_mode}`. Дефолты живут в чертеже; экземпляр их не дублирует (устраняет класс ME-D8).

**4.4 function (Функция).** `{components: [{type, ...}]}`. Типы v1: `storage{capacity}`, `opener{mechanism, states}`, `lockable{key_ref}`, `ownership{owner_ref, legality}`, `surface`, `light_source`. Резерв ME-1.11: `destructible{...}`, `concealable{...}`, `vertical_link{...}` — схемы объявлены, наполняются Этапом 03 (ME-3.9-3.11).

**4.5 behavior (Поведение).** `{actions: [{id, preconditions[], effects[], events[]}]}` — типизированные поля; исполнение — ядро игры (S-ME3), редактор код правил не пишет (ME-3.3). Наполняется Этапом 03.

**4.6 semantics (Смысл).** `{owner?, origin?, value?, legality?, history?, knowledge_seeds?}`. `knowledge_seeds` — только seed-знания до старта, провенанс «автор задал» (§5.3). Убеждения в рантайме редактор не пишет.

## 5. Экземпляр в location.json — ФОРМА СВЕРИТЬ С ФАКТОМ

Целевая форма (roadmap §2.1): `{blueprint_id, position, rotation, overrides, initial_state}`. Статус: черновик до археологии реального объекта (ключи `id`, `room_id`, `wall_id`, форма `position` — проверить в campaigns/Open_road/locations/*.json и в add_object/add_object_full). Дискриминатор: есть `blueprint_id` — экземпляр; нет — легаси-объект, читается адаптером (ME-1.3).

**5.1 overrides — закрытый реестр ключей (AR-ME-2).** v1: `variant`, `semantics.owner`, `semantics.origin`, `semantics.history`, `color`. Неизвестный ключ = ошибка валидатора. Расширение реестра = ревизия спеки, не тихое добавление.

**5.2 initial_state.** Только ключи, объявленные компонентами чертежа (`opener->open`, `lockable->locked`, `storage->contents`, `destructible->damage`) и `physics.durability`. После старта симуляции меняется только игрой (§2.1).
