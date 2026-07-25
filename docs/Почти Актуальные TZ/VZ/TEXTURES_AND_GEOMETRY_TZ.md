# ТЗ: Геометрия тел, текстуры и визуальная система Enigma

**Версия:** 1.0
**Дата:** 2026-07-23
**Статус:** PLANNED (после MVP, Phase 3)
**Зависимости:** B-15 (BodySchema), B-08 (WorldChronicle — для старения)

---

## 0. НАЗНАЧЕЧЕНИЕ

Этот документ описывает визуальную систему Enigma: как геометрия тел, текстуры, предметы и окружение рендерятся в 2D. Документ объединяет:
1. Геометрию тел NPC и игрока
2. Текстуры персонажей (слоистая система)
3. Текстуры предметов и объектов мира
4. Портреты для диалогов
5. Анимацию эмоций
6. Старение и травмы в визуале

---

## 1. АРХИТЕКТУРА РЕНДЕРИНГА

### 1.1. Два уровня визуализации

| Уровень | Где | Размер | Назначение |
|---|---|---|---|
| **Игровое поле** | `scene_renderer.py` | 14-20px высотой | Overview, перемещение, spatial awareness |
| **Диалоговый портрет** | UI overlay | 128×128px | Эмоции, разговор, близкий контакт |

На игровом поле NPC — маленькая составная 2D-модель (14-20px). В диалоге — крупный портрет головы и плеч (128×128px) с анимацией эмоций.

### 1.2. Составная 2D-модель (игровое поле)

```
        [HEAD]          ← круг, диаметр = head_ratio × height × SCALE
         ║
    ┌────╫────┐        ← плечи, ширина = shoulder_width × SCALE
    │    │    │
   [ARM] [TORSO] [ARM]  ← торс: прямоугольник; руки: узкие прямоугольники
    │    │    │
    └────┴────┘        ← таз, ширина = hip_width × SCALE
     │       │
   [LEG]   [LEG]        ← ноги: узкие прямоугольники
```

**SCALE** = 8 пикселей/метр (при height=1.78 → 14px). Для читаемости на низких разрешениях можно поднять до 10-12.

### 1.3. Параметры рендеринга по BodySchema

```python
def render_npc_model(surface, body: BodySchema, sx, sy, scale=8):
    h_px = int(body.height * scale)
    head_px = int(h_px * body.head_ratio)
    shoulder_px = int(body.shoulder_width * scale)
    hip_px = int(body.hip_width * scale)
    torso_h = int(h_px * body.torso_ratio)
    limb_h = int(h_px * body.limb_length_ratio)
    
    # Голова
    head_y = sy - h_px + head_px
    pygame.draw.circle(surface, skin_color, (sx, head_y), head_px // 2)
    
    # Торс
    torso_y = head_y + head_px // 2
    torso_rect = pygame.Rect(sx - shoulder_px//2, torso_y, shoulder_px, torso_h)
    pygame.draw.rect(surface, clothing_color, torso_rect)
    
    # Руки (если функциональны)
    if body.parts["left_arm"].functional:
        pygame.draw.rect(surface, skin_color, 
            (sx - shoulder_px//2 - 2, torso_y, 2, limb_h))
    if body.parts["right_arm"].functional:
        pygame.draw.rect(surface, skin_color, 
            (sx + shoulder_px//2, torso_y, 2, limb_h))
    
    # Ноги (если функциональны)
    leg_y = torso_y + torso_h
    if body.parts["left_leg"].functional:
        pygame.draw.rect(surface, clothing_color, 
            (sx - hip_px//4, leg_y, 2, limb_h))
    if body.parts["right_leg"].functional:
        pygame.draw.rect(surface, clothing_color, 
            (sx + hip_px//4, leg_y, 2, limb_h))
```

---

## 2. СЛОИСТАЯ СИСТЕМА ТЕКСТУР

### 2.1. Принцип

Каждый NPC рендерится как **композиция слоёв**. Каждый слой — отдельный PNG с прозрачностью. Слои накладываются сверху вниз:

```
СЛОЙ 1: BASE — силуэт тела (skin tone, обведёнка)
СЛОЙ 2: CLOTHING — одежда (платье, броня, фартук, плащ)
СЛОЙ 3: DETAILS — детали (шрам, ожог, татуировка, пятна на фартуке)
СЛОЙ 4: ACCESSORIES — аксессуары (поднос, молот, ключи, копьё, перстни)
СЛОЙ 5: AGE — возрастные маркеры (морщины, седина, сутулость)
СЛОЙ 6: WOUNDS — травмы (повязка, кровь, культя)
```

### 2.2. Формат текстур

| Параметр | Значение |
|---|---|
| Разрешение (игровое поле) | 24×32px на персонажа (достаточно для 14-20px модели + запас) |
| Разрешение (портрет) | 128×128px |
| Формат | PNG, 8-bit indexed (1bit/4bit palette) или RGBA |
| Палитра | 2-Bit Pack совместимая (4 цвета: чёрный, белый, прозрачный, акцент) |
| Именование | `frontend/textures/npc/{npc_id}/{layer}_{variant}.png` |

### 2.3. Структура папок

```
frontend/textures/
├── npc/
│   ├── maid_lusya/
│   │   ├── base.png          # силуэт тела
│   │   ├── clothing.png      # платье служанки + передник
│   │   ├── details.png       # усталые глаза, ожоги на руках
│   │   ├── accessories.png   # поднос
│   │   ├── age_young.png     # 19 лет — чистая кожа
│   │   ├── age_old.png       # 60+ лет — морщины, седина (для будущих сессий)
│   │   ├── wounds_burn.png   # ожог на руке
│   │   └── portrait.png      # 128×128 портрет для диалога
│   ├── guard_borko/
│   │   ├── base.png
│   │   ├── clothing.png      # кожаная броня + рубаха
│   │   ├── details.png       # шрам на шее, второй подбородок
│   │   ├── accessories.png   # копьё, дубинка
│   │   ├── age_middle.png
│   │   └── portrait.png
│   ├── thief_shadow/
│   │   ├── base.png
│   │   ├── clothing.png      # тёмный плащ + капюшон
│   │   ├── details.png       # перчатки, тень лица
│   │   ├── accessories.png   # (пусто — всё скрыто)
│   │   └── portrait.png      # только подбородок и губы
│   ├── tavern_keeper_tornin/
│   │   ├── base.png
│   │   ├── clothing.png      # фартук + рубаха
│   │   ├── details.png       # шрам на щеке, седина
│   │   ├── accessories.png   # связка ключей
│   │   ├── age_old.png       # морщины, грузность
│   │   └── portrait.png
│   ├── blacksmith_orm/
│   │   ├── base.png          # широкий, коренастый
│   │   ├── clothing.png      # прожжённый фартук кузнеца
│   │   ├── details.png       # обожжённые руки, борода в косе
│   │   ├── accessories.png   # молот
│   │   ├── age_old.png       # проседь в бороде
│   │   └── portrait.png
│   ├── merchant_goran/
│   │   ├── base.png          # полный, живот
│   │   ├── clothing.png      # цветной кафтан, шёлковый пояс
│   │   ├── details.png       # перстни на пальцах, проседь
│   │   ├── accessories.png   # кошель
│   │   └── portrait.png
│   └── player/
│       ├── base_male.png
│       ├── base_female.png
│       ├── clothing_default.png
│       └── portrait_male.png
├── objects/
│   ├── table.png
│   ├── chair.png
│   ├── bar.png
│   ├── bed.png
│   ├── door.png
│   ├── fireplace.png
│   ├── bookshelf.png
│   ├── chest.png
│   ├── barrel.png
│   └── ...
├── items/
│   ├── coin_gold.png
│   ├── coin_silver.png
│   ├── coin_copper.png
│   ├── ring.png
│   ├── letter.png
│   ├── key.png
│   ├── sword.png
│   ├── dagger.png
│   ├── hammer.png
│   ├── tray.png
│   ├── bottle_wine.png
│   ├── bottle_ale.png
│   └── ...
└── portraits/
    ├── emotions/
    │   ├── maid_lusya/
    │   │   ├── neutral.png
    │   │   ├── fear.png
    │   │   ├── anxiety.png
    │   │   ├── hope.png
    │   │   ├── pain.png
    │   │   └── hidden_joy.png
    │   ├── guard_borko/
    │   │   ├── neutral.png
    │   │   ├── greed.png
    │   │   ├── suspicion.png
    │   │   ├── boredom.png
    │   │   └── shame.png
    │   ├── thief_shadow/
    │   │   ├── neutral.png
    │   │   ├── cold_smile.png
    │   │   ├── threat.png
    │   │   └── silent_laugh.png
    │   ├── tavern_keeper_tornin/
    │   │   ├── neutral.png
    │   │   ├── anger.png
    │   │   ├── silence.png
    │   │   ├── bitterness.png
    │   │   └── shame.png
    │   ├── blacksmith_orm/
    │   │   ├── neutral.png
    │   │   ├── interest.png
    │   │   ├── irritation.png
    │   │   ├── rage.png
    │   │   └── grief.png
    │   └── merchant_goran/
    │       ├── neutral.png
    │       ├── trade_smile.png
    │       ├── panic.png
    │       ├── threat.png
    │       ├── greed.png
    │       └── fear.png
```

---

## 3. ПОРТРЕТЫ ДЛЯ ДИАЛОГОВ

### 3.1. Назначение

Портрет — крупное изображение головы и плеч NPC (128×128px). Показывается в диалоговом окне. Анимируется эмоциями.

### 3.2. Эмоциональные состояния

Каждый NPC имеет **5-6 уникальных эмоциональных состояний** (из character description). Каждое состояние — отдельный PNG.

**Принцип:** эмоция — это не мимика в реальном времени (слишком сложно для 2D). Это **статичный портрет** с определённым выражением. Переключение между портретами = смена эмоции.

```python
# В VerbalizationContext уже есть emotion: str
# Маппинг: emotion → portrait PNG
_EMOTION_TO_PORTRAIT = {
    "neutral": "neutral.png",
    "fearful": "fear.png",
    "angry": "anger.png",
    "suspicious": "suspicion.png",
    "joyful": "hidden_joy.png",
    "sad": "grief.png",
    "manipulative": "cold_smile.png",
    "panic": "panic.png",
}
```

### 3.3. Композиция портрета

```
┌───────────────────────────────┐
│                               │
│         [ГОЛОВА]              │
│     глаза, брови, рот         │  ← эмоция
│                               │
│    ┌─────[ПЛЕЧИ]─────┐        │
│    │   [ОДЕЖДА]      │        │
│    │   [АКСЕССУАР]   │        │
│    └─────────────────┘        │
│                               │
└───────────────────────────────┘
128×128px
```

Портрет **не** анимируется плавно. При смене эмоции — мгновенная замена PNG. Это стилистически совместимо с 1bit/pixel art.

---

## 4. ТЕКСТУРЫ ПРЕДМЕТОВ И ОБЪЕКТОВ

### 4.1. Объекты локации (tavern.json)

Объекты уже имеют тип (`type`) в JSON. Маппинг `type → texture`:

| Тип объекта | Текстура | Размер (px) |
|---|---|---|
| `table` | `objects/table.png` | 24×16 |
| `chair` | `objects/chair.png` | 8×12 |
| `bar` | `objects/bar.png` | 48×16 |
| `bed` | `objects/bed.png` | 24×16 |
| `door` | `objects/door.png` | 8×24 |
| `fireplace` | `objects/fireplace.png` | 24×24 |
| `bookshelf` | `objects/bookshelf.png` | 16×24 |
| `barrel` | `objects/barrel.png` | 12×16 |
| `chest` | `objects/chest.png` | 16×12 |
| `stove` | `objects/stove.png` | 20×20 |

### 4.2. Предметы (inventory items)

Предметы — отдельные текстуры малого размера (8-16px). Используются в:
- Инвентаре игрока (если будет)
- Speech bubble (NPC держит поднос → рисуется рядом)
- Сцене (меч на столе, кольцо на полу)

| Предмет | Текстура | Размер |
|---|---|---|
| Золотая монета | `items/coin_gold.png` | 4×4 |
| Серебряная монета | `items/coin_silver.png` | 4×4 |
| Медная монета | `items/coin_copper.png` | 4×4 |
| Кольцо | `items/ring.png` | 6×6 |
| Письмо | `items/letter.png` | 8×10 |
| Ключ | `items/key.png` | 4×8 |
| Меч | `items/sword.png` | 4×16 |
| Кинжал | `items/dagger.png` | 3×10 |
| Молот | `items/hammer.png` | 6×12 |
| Поднос | `items/tray.png` | 12×4 |
| Бутылка вина | `items/bottle_wine.png` | 4×10 |
| Бутылка эля | `items/bottle_ale.png` | 4×10 |

### 4.3. Интеграция с scene_renderer

```python
# Текущий код (scene_renderer.py):
sprite = get_entity_sprite(entity.entity_id) or get_entity_sprite("person")
if sprite:
    scaled = pygame.transform.scale(sprite, (npc_size, npc_size))
    self.screen.blit(scaled, ...)

# После ТЗ:
sprite = compose_npc_texture(entity.entity_id, body_schema, emotion)
if sprite:
    self.screen.blit(sprite, ...)
```

`compose_npc_texture` — новая функция, которая:
1. Загружает base.png для NPC
2. Накладывает clothing.png
3. Накладывает details.png (если есть)
4. Накладывает accessories.png (если есть)
5. Накладывает age.png (по age_years)
6. Накладывает wounds.png (по BodyPart.wounds)
7. Кэширует результат (по的组合ному ключу слоёв)

---

## 5. СТАРЕНИЕ В ВИЗУАЛЕ

### 5.1. Возрастные этапы

| Возраст | Этап | Визуальные изменения |
|---|---|---|
| 0-3 | Младенец | head_ratio=0.28, can_walk=False, маленькое тело |
| 4-12 | Ребёнок | head_ratio=0.22, низкий рост, короткие конечности |
| 13-17 | Подросток | head_ratio=0.17, рост почти взрослый, худой |
| 18-50 | Взрослый | head_ratio=0.14, базовые пропорции |
| 51-70 | Пожилой | морщины, седина, -2% рост, +10% жир |
| 71+ | Старик | глубокие морщины, сильная седина, сутулость, -4% рост |

### 5.2. Реализация

```python
def get_age_texture(body: BodySchema) -> Optional[pygame.Surface]:
    age = body.age_years
    if age < 4:
        return load_texture("age_infant.png")
    elif age < 13:
        return load_texture("age_child.png")
    elif age < 18:
        return load_texture("age_teen.png")
    elif age < 51:
        return None  # базовая текстура, без возрастного слоя
    elif age < 71:
        return load_texture("age_old.png")
    else:
        return load_texture("age_elder.png")
```

### 5.3. Влияние на пропорции

```python
def apply_aging(body: BodySchema) -> BodySchema:
    if body.age_years > 60:
        body.height *= 0.98
        body.body_fat = min(1.0, body.body_fat * 1.1)
    if body.age_years > 80:
        body.height *= 0.96
        body.body_fat = min(1.0, body.body_fat * 1.05)
    return body
```

---

## 6. ТРАВМЫ В ВИЗУАЛЕ

### 6.1. Типы травм

| WoundSeverity | Визуальный эффект | Текстура |
|---|---|---|
| MINOR | Царапина, маленькое красное пятно | `wounds_scratch.png` |
| MODERATE | Порез, бинт, кровавое пятно | `wounds_bandage.png` |
| SEVERE | Глубокая рана, много крови | `wounds_bleeding.png` |
| CRIPPLING | Ампутация, культя | `wounds_stump_{part}.png` |

### 6.2. Отображение

```python
def get_wound_texture(part: BodyPart) -> Optional[pygame.Surface]:
    if not part.wounds:
        return None
    worst = max(part.wounds, key=lambda w: w.severity)
    if worst.severity == WoundSeverity.CRIPPLING:
        return load_texture(f"wounds_stump_{part.name}.png")
    elif worst.severity == WoundSeverity.SEVERE:
        return load_texture("wounds_bleeding.png")
    elif worst.severity == WoundSeverity.MODERATE:
        return load_texture("wounds_bandage.png")
    else:
        return load_texture("wounds_scratch.png")
```

### 6.3. Потеря конечностей

```python
# В render_npc_model:
if not body.parts["left_arm"].functional:
    # Не рисовать левую руку
    # Вместо неё — культя (короткий обрубок, тёмный цвет)
    pygame.draw.rect(surface, dark_skin, 
        (sx - shoulder_px//2 - 1, torso_y, 1, 3))
```

---

## 7. ПОЛОВЫЕ РАЗЛИЧИЯ

### 7.1. Строение тела

| Параметр | Мужской | Женский |
|---|---|---|
| Shoulder width | 0.40-0.55 м | 0.35-0.45 м |
| Hip width | 0.30-0.38 м | 0.35-0.45 м |
| Body fat (базовый) | 0.15-0.25 | 0.20-0.30 |
| Height | 1.65-2.00 м | 1.50-1.85 м |
| Head ratio | 0.13-0.14 | 0.14-0.15 |

### 7.2. Визуальные различия

| Элемент | Мужской | Женский |
|---|---|---|
| Силуэт | V-образный (плечи > таз) | Песочные часы (плечи ≈ таз, талия узкая) |
| Грудь | Плоская | Объёмная (зависит от body_fat) |
| Бёдра | Узкие | Широкие |
| Лицо | Квадратный подбородок | Овальный подбородок |

### 7.3. Одежда

Одежда (`clothing.png`) рисуется **поверх** base силуэта. Разные текстуры для мужской и женской одежды:
- `clothing_dress.png` — для Люси
- `clothing_armor_male.png` — для Борко
- `clothing_apron.png` — для Торнина

---

## 8. РАСОВЫЕ РАЗЛИЧИЯ

| Раса | Рост | Ширина | Особенности |
|---|---|---|---|
| Human | 1.50-2.00 | Стандарт | Базовые пропорции |
| Half-dwarf | 1.20-1.50 | +30% ширина | Короткие ноги, широкий торс, густая борода |
| Elf | 1.70-2.10 | -10% ширина | Длинные конечности, худой, острые черты |
| Dwarf | 1.10-1.40 | +40% ширина | Очень коренастый, без шеи |

---

## 9. ПЛАН РЕАЛИЗАЦИИ

### Этап 1: BodySchema в JSON (сейчас, 1 час)
- Добавить `body_schema` секцию в каждый `config/npc/individuals/*.json`
- Значения из спецификации выше
- `BodyCapabilities` пока остаётся hardcoded — просто данные готовы

### Этап 2: Составная 2D-модель (Phase 3, 2-3 дня)
- Заменить `pygame.draw.circle` на составную модель
- Загрузить base.png для каждого NPC
- Реализовать `compose_npc_texture()`

### Этап 3: Слои текстур (Phase 3, 3-4 дня)
- Clothing, details, accessories слои
- Кэширование композиций
- Интеграция с BodyPart (показ/скрытие конечностей)

### Этап 4: Портреты и эмоции (Phase 3, 2-3 дня)
- 128×128 портреты для каждого NPC
- 5-6 эмоций на NPC
- Диалоговое окно с портретом
- Переключение эмоций по VerbalizationContext.emotion

### Этап 5: Предметы и объекты (Phase 3, 1-2 дня)
- Текстуры для всех объектов локации
- Текстуры для предметов (монеты, кольца, оружие)
- Интеграция с scene_renderer

### Этап 6: Старение и травмы (Phase 4, 2-3 дня)
- Возрастные текстуры (age_old, age_elder)
- Травмы (wounds_bandage, wounds_bleeding, wounds_stump)
- Интеграция с B-08 WorldChronicle (ageing)
- Интеграция с PhysicalOutcome (wounds)

---

## 10. ИНСТРУМЕНТЫ

### 10.1. Создание текстур

Рекомендуемые инструменты:
- **Aseprite** — pixel art, слои, палитры
- **LibreSprite** — бесплатная альтернатива Aseprite
- **Pixaki** (iOS) — для iPad

### 10.2. Палитра

2-Bit Pack совместимая:
- Чёрный: #000000
- Белый: #FFFFFF
- Прозрачный: (alpha=0)
- Акцент: #FF0040 (красный, для крови/шрамов) или #00FF00 (зелёный, для яда)

Или расширенная 4-bit палитра (16 цветов):
- 4 оттенка кожи
- 4 оттенка одежды
- 4 оттенка волос
- 4 специальных (кровь, металл, дерево, ткань)

---

*ТЗ сохранено в `/home/z/my-project/download/TEXTURES_AND_GEOMETRY_TZ.md`*
