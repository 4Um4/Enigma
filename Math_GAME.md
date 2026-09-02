# ═══════════ НАЧАЛО ФАЙЛА Math_GAME.md ═══════════

# Math_GAME.md — Математическая модель ENIGMA

> **Версия:** 2.0 (полная перезапись после археологической верификации)
> **Метод:** каждая формула извлечена из фактического кода через 5 пакетов PowerShell-археологии (сессии S-верификации), кросс-валидирована числами MUTATIONS/S206–S217
> **Принцип:** CLAIM → CODE → TEST. Ничего не попало в этот файл без строки кода
> **Соглашения:** `[VERIFIED]` — код подтверждён · `[SANDBOX]` — только калибровочная песочница · `[DEAD]` — контракт есть, кода нет · `[PARTIAL]` — частично извлечено

---

## 0. Чейнджлог v1 → v2 (что опровергла археология)

| § v1 | Утверждение v1 | Вердикт | Судьба |
|---|---|---|---|
| 3.2 | ContactLevel, пороги AC±5 | ❌ выдумка | переписано по реальному коду (лента по margin) |
| 8.1 | кусочная $f_{trust}$ | ❌ | заменена реальным рампом |
| 8.1 | $c + \Delta c$, β-фактор | ⚠️ | переписано: 3 ветки, вес 1.0/0.2 подтверждён |
| 6.3 | decay λ ∈ {0.01,0.03,0.05} | ❌ | $e^{-\Delta t/100}$, forget 0.05 |
| 13.1 | decay памяти по surprise | ❌ | по importance: 0.005/0.03/0.05 |
| 9 | CFL суперпозиция в проде | ❌ | код не существует → песочница |
| 4.5 | can_hear = r·h | ❌ | sound_reach линейный |
| 7.3 | PE tanh | ❓ | файл жив, формула не извлечена → [DEAD-зона] |
| 6.5 | инерция old·ρ+Δ(1−ρ) | ❌ | ноль вхождений по backend/app |
| 8.4 | 0.992 | 💀 | ноль вхождений — могила |
| 10.5 | steal 0.8/0.08 | ❌ | base(1.0/0.1) × (0.5+desire) |
| 10.4 | Needs 0.8/Schedule 0.6 | ❌ | категориальный override |
| **новое** | — | 🏆 | TIFL полная (C-матрица), CouplingResolver, S72-веса, MemoryCrystal, диспозиции, бой 2-слойный, сравнительная оценка |

---

## 1. Пространство состояний

$$
\mathcal{S}_t = \left( W_t, \; \{S_i^t\}_{i=1}^{N}, \; \mathcal{E}_t, \; \mathcal{C}_t \right)
$$

| Символ | Код |
|---|---|
| $W_t$ — мир | `scene_state["world_objects"]`, `npc_positions` |
| $S_i^t = (B_i, M_i, H_i, R_i, P_i)$ — агент | `NPCState`: body, память, `PerceptualKernel`, отношения, психика |
| $\mathcal{E}_t$ — убеждения | `EpistemicStore` (per-agent) |
| $\mathcal{C}_t$ — обязательства | `scene_state["active_commitments"]` |

---

## 2. Оператор тика

$$
\boxed{\mathcal{S}_{t+1} = \Phi(\mathcal{S}_t, E_t)}, \qquad \Phi = \phi_{10} \circ \cdots \circ \phi_{0.6} \circ \phi_{0.5} \circ \phi_0
$$

Pure reducer (ADR-TZ09-1): фаза 5 даёт `TickMutation` (дельты), мутация — только `StateApplicator.apply_batch` (фаза 8), коммит — один `atomic_commit_all`. Время: `game_time_seconds += GAME_TICK_INTERVAL_SECONDS` — всегда (фаза 0.5).

---

## 2a. Центральная композиция ENIGMA `[VERIFIED]` — формула статьи

 $$ \boxed{
W_t \xrightarrow{\;\mathcal P_i\;} O_i^t \xrightarrow{\;\mathcal E\;} \varepsilon_i^t
\xrightarrow{\;\mathcal A\;} L_i^t \xrightarrow{\;\mathcal D\;} \mathbf d_i^{t+1}
\xrightarrow{\;\mathcal R\;} E_i^{t+1} \xrightarrow{\;\mathcal V \to U \to \arg\max\;} a_i^t
\xrightarrow{\;\mathcal T\;} W_{t+1}}
 $$ 
| Шаг | Оператор | Код | § |
|---|---|---|---|
| 1 | Мир $W_t$ | `scene_state`, `SpatialService` | §1 |
| 2 | Агент $X_i = (B, M, E, R, \mathbf d, C)$ | `NPCState` + `DRIVE_COUPLING` | §1, §7 |
| 3 | Перцепция $O_i = \mathcal P_i(W, X_i)$ | `perception_filter`, somatic gate | §4 |
| 4 | PE $\varepsilon = \mathcal E(O, \hat O)$ | $\delta = L_{pk} - m$ (единственный живой контур) | §5 |
| 5 | Аффект $L = \mathcal A(O, \varepsilon, \mathbf d, B)$ | S72-веса, $w_{somatic} = 1-0.5W$ | §5 |
| 6 | Личность $\mathbf d' = \mathcal D(\mathbf d, \varepsilon, C, \rho)$ | TIFL (живо: integration.py:213, state_applicator:1257) | §7 |
| 7 | Вера $E' = \mathcal R(E, O, Trust)$ | BeliefRevisionEngine | §10 |
| 8 | Решение $final = base + \sum_{k=1}^{7} m_k$ | Modifier Contract | §13.1 |
| 9 | Действие $a = \arg\max_{a \in \mathcal A_i} U(a)$, $\mathcal A_i = \mathcal V_i(W)$ | viability mask | §13.5 |
| 10 | Переход $W' = \mathcal T(W, A)$ | исполнители + `atomic_commit` | §2 |

**Тезисы композиции:**

 $$ \boxed{\text{Physics} \to \text{Feasible Set} \to \text{Utility} \to \text{Choice}} \quad \text{— возможность ≠ желание (§13.5)}
 $$ 
 $$ \boxed{\text{семь аддитивных полей (экономика/социум/память/личность/знания) — над ОДНИМ пространством решений}} \quad \text{— §13.1}
 $$ 
**Три реальности** (доказано SUPERBOX-GORAN 12/12, S214): один $W_t$, три эпистемических мира —

 $$ W_t: player=thief \;\Rightarrow\; \mathcal R_A(\text{steal})=0.9 \text{ (видел)},\;\; E_B = r_A \cdot 1.0 \text{ (слышал)},\;\; \mathcal R_C = \varnothing; \qquad \mathcal R_A \neq \mathcal R_B \neq \mathcal R_C
 $$ 
**Детерминистическая непредсказуемость:** $a = f(S_t, E_t)$ детерминирован, но игрок видит только `PlayerPerceptionDTO` (эпистемическая граница) → $P(a|\text{observable})$ для игрока не вырожден. Непредсказуемость = скрытое состояние, не рандом. Скрытые медленные переменные уже в рантайме: `pressure_accumulator` (×0.85), `affective_memory`, `sleep_pressure`, `arousal`, `fatigue`.

## 3. Бой — четыре пути, из которых живы три `[VERIFIED формулы / ⚠️ wiring]

### 3.1. Слой 1: броски D&D 5e/2024 (`services/game/combat_math.py`)

$$
\text{total} = d20 + \underbrace{\left\lfloor\tfrac{A_{ab}-10}{2}\right\rfloor}_{\text{mod}} + \underbrace{\left[2 + \tfrac{L-1}{4}\right]}_{\text{prof}} + \sum_{c \in \text{env}} M_c
$$

$$
\text{fumble} = [d20 = 1], \quad \text{critical} = [d20 = 20], \quad \text{hit} = \neg\text{fumble} \wedge (\text{critical} \vee \text{total} \geq \text{AC})
$$

$$
\text{damage} = \max\!\left(0,\; \text{dice}\big(N \cdot (1 + \text{critical})\big) + \text{mod} + \text{bonus}\right)
$$

**Крит удваивает кубики, не бонусы.** Спасброски от смерти: 20 → чудо (1 HP); 1 → двойной провал; ≥10 успех; 3 успеха → стабилизация, 3 провала → смерть.

Окружение (`ENVIRONMENT_MODIFIERS`): темнота −5, тусклый свет −2, возвышение +2, фланг +2, укрытие ½ −2, укрытие ¾ −5, сильный ветер −3…

Сетка: расстояние Чебышёва (правило D&D); фланг — оппозиция векторов $(a_x+l_x-2t_x)^2 + (a_y+l_y-2t_y)^2 < 4$.

### 3.2. Слой 2: контакт и ткань (`services/combat/impact_engine.py`)

$$
\text{Contact} = \begin{cases} \text{MISS} & \neg\text{hit} \\ \text{PERFECT} & \text{critical} \\ \text{SOLID} & \text{margin} \geq 5 \\ \text{PARTIAL} & \text{margin} \geq 2 \\ \text{GLANCING} & \text{иначе} \end{cases}, \quad \text{margin} = \text{total} - \text{AC}
$$

$$
\text{structural\_damage} = \text{force} \times \mu(\text{Contact}), \qquad \mu = \{0,\; 0.3,\; 0.6,\; 1.0,\; 1.5\}
$$

Зона попадания — взвешенный выбор (`_ZONE_WEIGHTS`: torso_chest 35, … `[PARTIAL]`); кровотечение при `blood_loss_delta > 0.05` → `critical_effects=("bleeding",)`.

### 3.3. Проводка боя: карта путей ⚠️

| Путь | Математика | Живость |
|---|---|---|
| API `/combat/attack` → `CombatService.resolve_attack` | **клиентский d20** (`request.d20_roll`) | ✅ (routes.py:582) |
| DM-слой `rules_agent.run` | DC-таблицы, adv/dis max/min, `randint(2, 20)` | ✅ |
| Фаза 8 `rules_subscriber._compute_damage` | 4 + max(0, roll−dc) | ✅ |
| Ядро: `CombatSubscriber → resolve_physical_impact` | §3.1–3.2 | ✅ **ЖИВО** (импорт combat_subscriber:33, runtime-путь Фазы 8; вердикт «фантом» Части 6 отозван — артефакт паттернов поиска: движок = модуль функций, не класс) |

Входная точка: `resolve_physical_impact(attacker, defender, intent, rng_seed=42)` — имя верифицировано. П-9 признан кодом: «MVP FIX: Игрок всегда попадает... Временно отключено». П-11 усилен: клиент присылает d20 И damage. П-14: отключённая дистанционная проверка игрока (combat_subscriber:173). П-15: `p["hp"]` в resolve_attack мимо body_state SSOT.

**Аномалии:** П-7 (`rng or random`), П-9 (SOLID-чит игрока) — в фантомном слое; П-11 🔴 клиентский d20; П-12 тройная истина урона; П-13 `randint(2,20)` — натуральная 1 недостижима. Входная точка ImpactEngine — `impact_engine.py:~122`, `rng_seed=42` (имя — верифицировано микропакетом 8). Позитив: броски логируются в `combat_log.jsonl` (LOG-GATE).

```python
def process_impact(..., rng_seed: int = 42):   # дефолт: все бои на одном seed
    rng = random.Random(rng_seed)
...
if intent.actor_id == "player":                 # чит игрока
    contact = ContactLevel.SOLID                # без d20, без промаха, без крита
```

Позитив: все броски логируются в `data/logs/combat_log.jsonl` (LOG-GATE) — честность наблюдаема.

---

## 4. Мембраны восприятия `[VERIFIED]`

### 4.1. Видимость события (`NPCState.can_observe`, `models/npc_state.py:587`)

$$
\text{observe}(i, e) = \begin{cases} i = e.\text{source} & \text{private} \\ i \in \{e.\text{source}, \text{target}\} & \text{whisper} \\ d(i, e) \leq e.\text{radius} & \text{public} \end{cases}
$$

### 4.2. Слух (`perception_filter.py` + `spatial_runtime.py:279`)

$$
\text{hear}(i, e) = \text{conscious}(i) \vee e.\text{radius} > 15 \;\;\wedge\;\; d(i, e_{src}) \leq R
$$

$$
\boxed{R = \max\left(0.5,\; r + 4\,n_{\text{oise}} - 3\,d_{\text{ensity}}\right)}
$$

Тиры: `PERCEPTION_RADIUS = {minor: 3.0, major: 15.0}` — экономика симуляции (minor-NPC слышат вплотную).

### 4.3. Наблюдение очевидцем (`observation_subscriber.py`)

$$
\text{witness}(i, e) = i \neq \text{actor} \;\wedge\; d(i, \text{actor}) \leq 10.0 \;\wedge\; \text{walls\_LOS}(i, \text{actor})
$$

`event.radius` игнорируется (DEBT-R1). Радиус 10.0 — хардкод. Свидетель → `ClaimEvent(witness → witness)` — **один движок ревизии для обоих каналов знания**.

### 4.4. Somatic Gate (ADR-O-139/143)

$$
u_{\text{somatic}} = \frac{\text{pain}/100 + \text{shock}}{2} \;\;\xrightarrow{\text{вес}}\;\; \text{см. §5}
$$

Тело — фильтр до семантики: порядок `Body → Somatic → Semantic`.

---

## 5. Аффективный контур: Active Inference `[VERIFIED]` ⭐

`affective_integrator.py` — **закон релятивистского восприятия (§ENIGMA-S72) в формулах**:

**Шаг 1. Личность взвешивает мир** (веса = драйвы из psyche):

$$
w_{\text{threat}} = \text{fear}, \quad w_{\text{unc}} = \text{control}, \quad w_{\text{anom}} = \text{significance} \quad (\text{дефолт } 0.25)
$$

$$
\boxed{w_{\text{somatic}} = 1 - 0.5\,W}, \qquad W = \text{willpower} \in [0,1]
$$

Воля модулирует боль: $W=1 \Rightarrow$ боль весит половину; $W=0 \Rightarrow$ полную.

**Шаг 2. Мгновенная нагрузка:**

$$
L_{pk} = \min\left(1,\; \text{threat}\cdot w_{\text{threat}} + \text{uncertainty}\cdot w_{\text{unc}} + \text{anomaly}\cdot w_{\text{anom}} + u_{\text{somatic}}\cdot w_{\text{somatic}}\right)
$$

**Шаг 3. Surprise + шрам памяти (prior):**

$$
\delta = L_{pk} - m, \qquad s_{\text{scar}} = 0.1 + 0.4\,|\delta|^{1.5}
$$

$$
\boxed{m' = \min\left(1,\; 0.85\,m + L_{pk}\,s_{\text{scar}}\right)}
$$

**Шаг 4. Posterior — чистая функция ошибки** (память — не источник энергии, а ожидание):

$$
L_{\text{adj}} = \min\left(1,\; 1.2\,|\delta|\right)
$$

**Шаг 5. Гистерезис** (воля = скорость возвращения в себя):

$$
\alpha = \begin{cases} 0.30 & L_{pk} > L_{\text{adj}} \quad \text{(подъём быстрый)} \\ 0.05 + 0.1\,W & \text{иначе} \quad \text{(спад медленный)} \end{cases}
$$

$$
\boxed{L' = \operatorname{clamp}\left(L_{\text{adj}} + (L_{pk} - L_{\text{adj}})\cdot\alpha\right)}
$$

**Свойства:** показатель $1.5$ разделяет шум и событие (×2 ошибки → ×2.8 шрама); «характер = скорость успокоения»; формального вариационного $F$ нет — это феноменологический контур минимизации ошибки предсказания.

---

## 5b. ExpectationStore — FEP-хранилище `[DEAD, DEEP-015]`

 $$E_r' = 0.7\,E_r + 0.3\,r_{\text{actual}}, \qquad \kappa' = \min(1,\ \kappa + 0.05), \qquad \text{decay: } x \mathrel{\times}= e^{-0.01\,\Delta t}$$ 
Докстринг: «Pure projection store for Free Energy Principle». Статус: **никогда не инициализировался, все блоки no-op, проводка удалена DEEP-015** (tick_orchestrator:1814, state_applicator:698, idle_services:54). Повторная интеграция — TODO «Фаза 2 / Эпоха 7». П-10: файл-сирота нарушает контракты (SQLite в обход atomic_commit, `memory.db` вне кампании, докстринг-ложь «строго через StateApplicator», silent except).

## 6. Математика сна `[VERIFIED]` ⭐ (`coupling_resolver.py`)

Входы: $s$ = sleep_pressure, $a$ = arousal (оба clamped [0,1]).

$$
\omega = \max(0,\; a - 0.5\,s) \quad \text{(wakefulness)}
$$

| Множитель | Формула | Физиология |
|---|---|---|
| $v_{\text{vision}}$ | $\max(0.05,\ \omega)$ | слепота во сне, 5% — сны имеют визуал |
| $v_{\text{hearing}}$ | $\max(0.2,\ 0.8\omega + 0.2a)$ | **слух отключается последним**; $0.2a$ — пробуждение шумом как математика |
| $v_{\text{motor}}$ | $\max(0,\ 1 - 1.2s)$ | паралич сна |
| $v_{\text{memory}}$ | $0.5 + 0.5s$ | **консолидация растёт во сне** |
| $v_{\text{imag}}$ | $0.1 + 0.9s$ | сны при высоком $s$ |

Режим (диагностическая метка, вердикт В1 — производное факта `sleep_onset_tick`): $s<0.3$ FULL_WAKE · $s<0.7$ DROWSY · $a>0.6$ REM · $s>0.9 \wedge a<0.1$ DEEP_SLEEP · иначе SLEEP.

---

## 7. TIFL: личность как градиентная система `[VERIFIED]` ⭐⭐⭐

### 7.1. Матрица внутреннего напряжения (`break_progress_engine.py:256`)

$$
C = \begin{pmatrix} 0 & 0.6 & 0.2 & 0.1 \\ 0.6 & 0 & -0.3 & -0.2 \\ 0.2 & -0.3 & 0 & -0.4 \\ 0.1 & -0.2 & -0.4 & 0 \end{pmatrix} \; (\text{fear, control, significance, desire}), \qquad C = C^{T}
$$

Антагонизмы: fear↔control (+0.6, макс.), fear↔significance, fear↔desire. Синергии: significance↔desire (−0.4, макс.), control↔significance, control↔desire.

$$
T(\mathbf{d}) = \tfrac{1}{2}\,\mathbf{d}^{T} C\,\mathbf{d} \quad \text{— энергия внутреннего конфликта}
$$

### 7.2. Непрерывный дрейф (ICDF + ICL)

$$
\boxed{
\dot{\mathbf{d}} = \pi\left[\underbrace{0.005\,\varepsilon\left(\mathbf{e} - \tfrac{\mathbf{d}}{\|\mathbf{d}\|_1}\right)}_{\text{давление мира}} - \underbrace{0.002\,C\,\mathbf{d}}_{-\nabla T\ \text{релаксация}}\right], \quad \pi = \max(0.1,\ 1-\rho)
}
$$

- $\varepsilon$ — prediction_error из Котла; мёртвая зона $\varepsilon < 0.05 \Rightarrow 0$
- событие L1 при $|\Delta d| > 10^{-6}$, `source_id="tifl_pressure_model"`, type=`pressure`
- **массосохранение:** zero-sum — только ICDF-член (при $\|\mathbf{e}\|_1 = 1$); ICL-член НЕ сохраняет массу ($\mathbf 1^T C = (0.9, 0.1, -0.5, -0.5) \neq 0$). Инвариант $\Sigma d = 1$ поддерживается downstream (L5 post-commit / нормализация проекции DRP)

### 7.5. Аттрактор ландшафта — аналитическое решение `[ANALYTICAL]` ⭐

KKT для $\min T(\mathbf d) = \tfrac12 \mathbf d^T C \mathbf d$ на симплексе. Внутреннего минимума нет:

 $$ \mathbf d^* = \left(0,\; \tfrac{4}{23},\; \tfrac{10}{23},\; \tfrac{9}{23}\right), \quad T^* \approx -0.104, \quad \lambda = -0.2087, \quad \mu_{fear} = 0.439
 $$ 
1. **Аттрактор бесстрашный**: $\mathbf 1^T C = (0.9, 0.1, -0.5, -0.5)$ — масса страха *создаёт* напряжение, significance/desire *поглощают*; релаксация вытекает из страха.
2. **Таймскейл травмы**: `will_broken` (+0.05π fear) релаксирует за ≈ **109 тиков** (π сокращается). На уровне base «травма временная» — количественный факт.
3. **Следствие**: постоянный страх возможен только уровнем II — L1-шрам (append-only) смещает EffectiveDrives каждый тик через DRP. ENIGMA уже так устроена: base расслабляется, effective — нет.

### 7.6. Иерархия личности

 $$ C \;(\text{архитектура, const}) \;\to\; \mathbf d \;(\text{положение}) \;\to\; M/E/R \;(\text{история}) \;\to\; \text{hidden state} \;\to\; \text{action}
 $$ 
| Уровень | Носитель | Перmanence | Реализация |
|---|---|---|---|
| I. Состояние | $\mathbf d$, аффект | временно (~10² тиков) | TIFL, Котёл |
| II. История | L1 / L2.5 / Epistemic / R | надолго → навсегда | L1 append-only; Epistemic без decay (П-2!) |
| III. Архитектура | $C$ | «стал другим человеком» | НЕ реализовано — см. MATH-4 (Roadmap) |

 $$ \boxed{\text{Состояние ломается временно; история меняет надолго; изменение } C \text{ меняет архитектуру.}}
 $$ ```
IPT: N/A (документация)

**Патч M4** — §18.4 финал + терминология.

Файл: Math_GAME.md
БЫЛО:

### 7.3. Острые травмы (TRAUMA_TOPOLOGY) — шаги по осям $C$

| Травма | $\Delta\mathbf{d}$ | Ось антагонизма |
|---|---|---|
| will_broken | $+0.05_{\text{fear}} - 0.05_{\text{control}}$ | fear↔control (**0.6 — самая дорогая**) |
| humiliated | $-0.05_{\text{sig}} + 0.05_{\text{fear}}$ | fear↔significance |
| betrayed | $+0.05_{\text{control}} - 0.05_{\text{desire}}$ | control↔desire |
| near_death | $+0.08_{\text{fear}} - 0.08_{\text{sig}}$ | fear↔significance |

Все векторы нулевой суммой; $\Delta = v \cdot \max(0.2,\ 1-\rho)$ (пол травмы выше пола дрейфа). «Слом воли» ходит ровно по оси максимального напряжения.

### 7.4. Лестница BREAK_DELTA (constants.py:375)

$$
\text{resistance} = -0.002 \;<\; \text{cracks} = -0.005 \;<\; \text{rationalization} = -0.008 \;<\; \text{adaptation} = -0.015 \;<\; \text{deformation} = -0.03
$$

---

## 8. L1 Хроника и паттерны `[VERIFIED]`

Append-only SQLite; $|L1_i|$ только растёт.

**L1.5 PatternDetector:**

$$
\text{cum} = \sum_j e_j \cdot w_j, \qquad \text{var} = \underbrace{\mathrm{Var}[\{e_j\}]}_{\text{стат. разброс}} \times \underbrace{\text{flips}}_{\text{смена знака (врем. осцилляция)}} \quad \text{— только произведение: стабильный поток} \Rightarrow 0
$$

---

## 9. L2.5 Кристаллизация `[VERIFIED]` (`belief_crystallization_engine.py`)

$$
w_{\text{base}} = \min\left(\tfrac{|\text{cum}|}{10},\; 1\right) \cdot \text{sensitivity} \quad (\text{sensitivity: fear} \to 0.25 \text{ дефолт})
$$

| Случай | Формула |
|---|---|
| подтверждение | $w' = \min(w + w_{\text{base}},\ 1)$ — линейный рост |
| опровержение | $w' = w - w_{\text{base}} \cdot 6$; если $\leq 0$ → старое удалено, новое $=\min(w_{\text{base}}, 1)$ |
| новое | создаётся при $w_{\text{base}} > 0.05$ |

**Decay:** $w(t) = w(t_0)\, e^{-\Delta t / 100}$ (полураспад ≈ 70 тиков); забывание при $w \leq 0.05$.

**TRAUMA_MULTIPLIER = 6.0** — опровержение в 6 раз сильнее подтверждения (тест `test_asymmetric_trauma_x6`).

---

## 10. Эпистемический слой `[VERIFIED]` ⭐⭐⭐

### 10.1. Надёжность источника (`trust_based_reliability_provider.py`)

$$
r = \begin{cases} 0.9 & \text{channel} = \text{direct\_observation (DOR)} \\[2pt] \operatorname{clamp}\left(\tfrac{\tau}{100}, 0, 1\right) & \tau \geq -30 \\[2pt] -\dfrac{|\tau| - 30}{70} & \tau < -30 \end{cases}
$$

Prior неизвестного источника: $\tau_0 = 50 \Rightarrow r = 0.5$. Непрерывность в $\tau = -30$ (гладко), монотонность всюду (INV-EPISTEMIC-TRUST-MONOTONICITY — свойство формы), враг $\tau=-100 \Rightarrow r = -1$.

### 10.2. Ревизия убеждений — три ветки (`belief_revision_engine.py`)

$$
c_{\text{in}} = r \cdot \underbrace{1.0}_{\text{\_CLAIM\_WEIGHT}}
$$

| Ветка | Формула |
|---|---|
| новая запись | $c = \max(0, c_{\text{in}})$ |
| тот же источник | $c' = \operatorname{clamp}(c + c_{\text{in}} \cdot 0.2)$ — **эхо-демпфирование** |
| независимый | $c' = \operatorname{clamp}(c + c_{\text{in}})$ |

**Кросс-валидация S206 (аналитическое закрытие):** при $c_0 = 0.8$:

$$
\tau = -31: \; 0.8 - \tfrac{1}{70} = 0.786 \;\checkmark \qquad \tau = -50: \; 0.8 - \tfrac{20}{70} = 0.514 \;\checkmark \qquad \tau = -100: \; \max(0, 0.8 - 1) = 0.0 \;\checkmark
$$

Формула воспроизводит задокументированные числа точно.

### 10.3. Модификаторы и диспозиции (`epistemic_context_resolver.py` + `domain/epistemic_dispositions.py`)

$$
m_{\text{intent}} = 1.5 \cdot c_{\max} \cdot D_{\text{arch}}[\text{intent}], \qquad m_{\text{block\_path}} = 0.75 \cdot c_{\max}, \qquad m_{\text{ally}} = 0.2 \cdot c_{\max}
$$

| Архетип | report | warn | attack | rumor | talk |
|---|---|---|---|---|---|
| guard | **1.4** | 0.5 | 0.4 | 0.0 | 0.2 |
| maid/barmaid | 0.1 | 0.3 | 0.0 | **1.3** | 0.6 |
| merchant | 0.4 | **1.4** | 0.3 | 0.2 | 0.3 |
| tavern_keeper | 0.2 | 0.6 | 0.3 | 0.3 | **1.2** |
| thief/bandit | 0.0 | 0.1 | 0.0 | 0.2 | 0.2 (**молчит**) |
| priest | 0.3 | 0.8 | 0.0 | 0.1 | 0.9 |
| commoner (дефолт) | 0.2 | 1.0 | 0.3 | 0.3 | 0.4 |

Guard доносит, хозяйка шепчет по углам, вор молчит: спектр реакций на одно знание. Табу npc_id-хардкодов; калибровка через Calibration Lab.

---

## 11. Память `[VERIFIED]`

### 11.1. Importance (`importance_engine.py`)

$$
\text{imp} = \operatorname{round}\left(\max\left(0.05,\; \min\left(1,\; \text{base} \cdot \max(0.4, \text{clarity}) \cdot \text{stress\_mod}\right)\right),\; 4\right)
$$

$$
\text{stress\_mod} = \begin{cases} 1.25 & \text{stress} > 70 \wedge \text{PE} > 0.2 \\ 1.10 & \text{stress} > 50 \vee \text{PE} > 0.1 \\ 1.0 & \text{иначе} \end{cases} \quad (\text{ключ — prediction\_error, не EmotionTag; ADR-O-206})
$$

### 11.2. Двухрежимный decay ⭐ (новое в v2)

**Скорость при записи** (`memory_manager.py:244`):

$$
\lambda = \begin{cases} 0.005 & \text{imp} \geq 0.9 \quad \text{(структурный шок)} \\ 0.03 & \text{imp} > 0.6 \quad \text{(значимая коррекция)} \\ 0.05 & \text{иначе} \end{cases} \qquad \lambda \mathrel{\times}= 0.4 \;\text{ для контрактов}
$$

**Episodic** (`EventMemory.decayed`, EMRL E1.1): $\text{imp}' = \text{imp} \cdot e^{-\lambda \cdot \text{days}}$, **с полом** — инвариант «разговор был» не умирает, детали распадаются.

**Semantic** (`MemoryCrystal.decayed`, EMRL E1.2) — ключевые инварианты:

$$
\text{conf}' = \text{conf} \cdot e^{-0.005 \cdot \text{days}} \quad (30 \text{ дней} \Rightarrow \times 0.86)
$$

$$
\text{знание бессмертно}; \qquad \text{retrieval\_strength} = f(\text{times\_recalled}) \neq f(t) \quad \text{— припоминание растит доступность, не истинность}
$$

Legacy-путь: `apply_decay` ×0.92, архивация < 0.05.

---

## 12. Социальный слой `[VERIFIED]`

**Детерминированные триггеры** (`social_subscriber.py:163`): gossip −2.0 trust (игрок→сплетник) · praise +1.5 (игрок→хвалимый) · accuse +1.0 fear (игрок→обвиняемый) · talk +0.5 · intimidate/attack +1.0 fear. Запись через `RelationshipWriteGate`.

**FateTracker:** $s = 1 - \text{stress}/100$; DEATH по `life_status` (SSOT, не hp); ESCAPE — покинул локацию; **BROKEN при `_critical_ticks ≥ 5`** подряд в CRITICAL.

---

## 13. Решение (DecisionHub) `[VERIFIED]`

### 13.1. Modifier Contract (ADR-O-355, `decision_hub.py:378`)

$$
\text{final} = \text{base} + \sum_{k=1}^{7} m_k \quad (\text{eco, social, reputation, drives, contract, memory, epistemic})
$$

Копия входа, аддитивность, коммутативность, ноль побочных эффектов.

### 13.2. Приоритеты и арбитраж (S203.4, `action_priority.py`)

$$
p \in \{1_{\text{EXPL}}, 2_{\text{ROUT}}, 3_{\text{SOC}}, 6_{\text{SLEEP}}, 6_{\text{SURV}}, 7_{\text{WINDOW}}\}
$$

$$
\text{INTERRUPT}(p_{\text{cand}} > p_{\text{inc}} + \theta), \qquad \theta = 3 \;\; (\theta = 0 \text{ если incumbent PROPOSED})
$$

task/windup EXECUTING и sleep — protected (INCUMBENT_PROTECTED). `commitment_id = cmt-{md5(tick:npc:action:ordinal)}` — uuid4 запрещён.

### 13.3. Давление и маски (`decision_hub.py`)

$$
a' = \begin{cases} \min(a + p,\ 1) & \text{повтор ключа} \\ 0.85\,a & \text{затухание} \end{cases} \quad \text{(pressure accumulator)}
$$

$$
\sigma = \max(0.1,\ 0.8 - 0.7 \cdot \text{intensity}); \quad \text{COLLAPSE: } \text{IDLE} \to 1.0 + \text{intensity}, \;\text{прочее} \to \sigma
$$

### 13.4. Специфические affinity

$$
\text{steal} = \underbrace{(1.0 \mid 0.1)}_{\text{thief | прочий}} \times (0.5 + \text{desire}); \qquad \text{fear входит через } \times 0.65; \quad \text{свидетель директивы} -0.8
$$

### 13.5. Viability mask — физика возможностей (`life_engine.py:1068`)

$$
\text{threat} > 0.3 \Rightarrow \text{ROUTINE} \notin \mathcal{A}_i \quad \text{— сжатие пространства ДО скоринга, не штраф внутри}
$$

Needs: порог 0.5, прирост 0.08/тик (×100 = 8.0 в шкале body); критическая потребность **категориально** перезаписывает расписание. Порог реактивной тревоги: stress/100 > 0.8.

---

## 14. RNG и детерминизм `[VERIFIED]`

$$
\text{seed} = \operatorname{int}\big(\text{sha256}(\texttt{f"{tick}:{npc_id}:{salt}"}).\text{hexdigest}(),\; 16\big) \quad \text{— полный 256-бит}
$$

`KernelRNG` обёртывает `random.Random(seed)`; $\text{KernelRNG}(t, i, s) = \text{const}$. Путь: `services/npc/kernel_rng.py` (НЕ core/, как в ADR — doc-drift). Windup: ATTACK 2 тика, STEAL 2 тика (окно обнаружения).

---

## 15. CFL и ISK — калибровочная песочница `[SANDBOX]`

Продакшн-код CFL **не существует** (ноль вхождений `CausalEmissionPacket|causal_field` в backend/app). Весь аппарат живёт в `tests/sandbox/calibration/`:

- `CausalPressureVector` — 5D (fear, control, significance, desire, volatility) — **те же оси, что драйвы и C-матрица**
- ISK (`isk.py`): $\delta_g = \|g_{\text{warped}} - g_{\text{base}}\|$ при микро-шуме $\sigma = 0.1 \cdot 0.1$:

$$
\text{режим} = \begin{cases} \text{CRYSTAL} & \mu < 0.01 \wedge \sigma < 0.01 \\ \text{PLASTIC} & \mu > 0.01 \wedge \sigma < 0.5\mu \\ \text{BRITTLE} & \sigma > 1.5\mu \\ \text{CHAOTIC} & \text{иначе} \end{cases}
$$

---

## 16. Контракты без кода `[DEAD]` — карта долгов для будущих ADR

| Контракт | Где должен жить | Статус |
|---|---|---|
| `to_modifiers(): max_conf × 0.992` | epistemic_context_resolver | **ноль вхождений** — заменён на 1.5×диспозиции |
| PE → drive modifier через tanh + Clamp(0.25) (ADR-S93.2, L6) | `services/npc/expectation_store.py` | ❌ ЗАКРЫТО: tanh в файле отсутствует; файл — EMA-store-надгробие, wiring удалён DEEP-015 («никогда не инициализировалось, no-op»); интеграция — TODO Эпоха 7 (npc_tick_pipeline:387) |
| инерция `old·ρ + Δ(1−ρ)` (Устав §12.1) | state_applicator / calibration | **ноль вхождений паттерна** по backend/app |
| CFL суперпозиция+cap (ADR-O-209/210) | services/social | только песочница |
| `svc/combat/combat_math.py` (L12.2) | — | файл в `services/game/` — doc-drift |
| `core/kernel_rng.py` (DOM-02 L2) | — | файл в `services/npc/` — doc-drift |

---

## 17. Инварианты (математические законы)

1. **Epistemic Isolation:** belief ≠ truth; `confidence ≠ P(truth)` — не-вероятностная семантика by design
2. **Causal Closure:** каждое изменение $W$ объяснимо цепью в $\Phi$
3. **Temporal Isolation:** шаг не меняет собственные входы
4. **L3 Ephemerality:** драйвы пересчитываются каждый тик
5. **Массосохранение TIFL:** $\sum \dot d = 0$ на симплексе драйвов
6. **Append-only:** $|L1_i|$ не убывает
7. **Modifier Additivity:** коммутативная сумма
8. **KernelRNG Determinism:** $(t,i,s) \to \text{const}$ — **кроме П-7**
9. **Single Writer:** один писатель на поле
10. **Монотонность trust→reliability** — свойство формы рампа

---

## 18. СРАВНИТЕЛЬНАЯ ОЦЕНКА

> Правила: `[VERIFIED]` — факт кода · `[PROPOSAL]` — предложение, не реализовано. Всё проходит фильтр §ENIGMA-001 (каузальная глубина) и anti-Bond (Р17-П1: паттерн, не субстанция). Калибровка — только через Calibration Lab (ADR-O-361).

### 18.1. Жемчужины — «удивительно, что так вообще кто-то сделал»

**Ж-1. TIFL: личность как градиентная система** `[VERIFIED]` ⭐⭐⭐ (§7)
Репликаторная динамика по ошибке мира + градиентный спуск по честному потенциалу $\tfrac12 \mathbf{d}^T C \mathbf{d}$ с сохранением массы. Личность = точка на симплексе в собственном ландшафте напряжений. Аналогов в game AI не встречал: обычно либо статические трейты, либо скалярные сдвиги.

**Ж-2. Релятивистское восприятие (S72) в формулах** `[VERIFIED]` ⭐⭐⭐ (§5)
Веса мира = драйвы личности: fear-driven агент живёт в *более угрожающем* мире при том же `threat`. Воля модулирует боль ($1-0.5W$). Мир объективен, опыт — субъективен, и это не декларация, а четыре строки кода.

**Ж-3. Аффект: двухмасштабный surprise-контур** `[VERIFIED]` ⭐⭐⭐ (§5)
Шрам $0.1+0.4|\delta|^{1.5}$, posterior = чистая функция ошибки, гистерезис с willpower-асимметрией (в панику 0.30, из паники $0.05+0.1W$). «Характер = скорость успокоения». Феноменологический Active Inference без вариационного $F$.

**Ж-4. Психология в двух константах: ×6 и 0.2** `[VERIFIED]` ⭐⭐ (§9, §10)
Потеря-неприятие ×6 (против ~2.25 в prospect theory — намеренная драматическая гипербола) + эхо-демпфирование 0.2 («один свидетель десять раз ≠ десять свидетелей»). Оба кросс-валидированы (тест + числа S206).

**Ж-5. Viability mask: возможность ≠ предпочтение** `[VERIFIED]` ⭐⭐ (§13.5)
`threat > 0.3` *исключает* ROUTINE из пространства генерации: «NPC не может выбрать работу при угрозе — это вопрос существования». Философски чистое разделение physics/utility.

**Ж-6. Канальная унификация знания** `[VERIFIED]` ⭐⭐ (§4.3, §10)
`ClaimEvent(witness→witness)`: слух и прямое наблюдение проходят один движок ревизии, различаясь только источником надёжности (trust-функция vs 0.9). Один extension-point вместо двух систем убеждений.

**Ж-7. Математика сна** `[VERIFIED]` ⭐⭐⭐ (§6)
Сон как топология связанности, а не флаг. Слух отключается последним (floor 0.2 + член $0.2a$ — пробуждение шумом как математика). Память и воображение *растут* во сне — нейронаучно корректная консолидация. Mode = производное факта `sleep_onset_tick` (вердикт В1: метка ≠ состояние).

**Ж-8. Когерентность травм с матрицей напряжения** `[VERIFIED]` ⭐⭐⭐ (§7.3)
Острые травмы — нулевые суммы вдоль осей антагонизма $C$; «слом воли» ходит ровно по самой дорогой оси (fear↔control 0.6). Два слоя личности (острый + непрерывный) согласованы одной матрицей. Здесь «никто не додумался» — буква́льно.

**Ж-9. Двухрежимное забывание** `[VERIFIED]` ⭐⭐⭐ (§11.2, EMRL E1.1/E1.2)
Episodic: умирают *детали*, инвариант «разговор был» живёт (floor). Semantic: умирает *уверенность*, знание бессмертно; доступность растёт от припоминаний, не от времени. Разделение truth/availability, которое в когнитивной науке стандарт, а в играх не встречается.

### 18.2. «Сейчас так → лучше бы так»

**П-1. `claim.confidence` мёртв.** `[VERIFIED проблема]`
Сейчас: $c_{in} = r \cdot 1.0$ — уверенность утверждения не потребляется. Лучше: $c_{in} = r \cdot \psi_{claim}$. Одна строка + SUPERBOX-прогон. Эффект: слухи градуируются.

**П-2. Эпистемическое остывание отсутствует.** `[PROPOSAL]`
Сейчас: `EpistemicRecord` не затухает — слух тика 5 живёт с той же confidence на тике 5000 (L2.5 имеет decay, эпистемика — нет). Лучше: $c(t) = c_0 e^{-\Delta t/\tau_e}$, калибруемое $\tau_e$. Появляется возраст информации — прямое удлинение каузальных цепочек (§ENIGMA-001). Прямо просится в M2/D контур RE-01.

**П-3. `sound_reach` — линейная аномалия.** `[VERIFIED проблема]`
Сейчас: $r + 4n - 3d$: шум *усиливает* дальность шёпота (семантически гул должен маскировать). Лучше: $R = r(1+\gamma n)\,e^{-\kappa d}$. В защиту: разборчивость уже разведена в `AuditoryDistortionPolicy` — двухслойность грамотная, вопрос только в форме reach-члена.

**П-4. Сон-мембрана не подключена к CouplingProfile.** `[VERIFIED разрыв]`
Сейчас: спящий слышит iff `radius > 15` — бинарный клифф; `_npc_is_conscious` читает строку state, не `hearing_mult` (мягкий DOUBLE TRUTH, нарушение Phase E.0 ADR-O-356). Лучше: $R_{eff} = r \cdot h(\kappa)$, $arousal \mathrel{+}= g(R_{eff})$. Это не новая математика — **исполнение уже принятого ADR**. Кандидат №1 по соотношению ценa/эффект.

**П-5. Observation-радиус 10.0 хардкод.** `[VERIFIED, DEBT-R1]`
Лучше: SSOT-таблица `action_perception_radius()` (прецедент S210) + `light_level`-зависимость (`base_range="dim"` уже существует).

**П-6. Насыщение кристаллизации.** `[PROPOSAL, minor]`
Сейчас: $\min(|\text{cum}|/10, 1)$ — evidence свыше 10 теряется. Лучше: $1-e^{-|\text{cum}|/10}$ — та же шкала, без обрезки на длинных кампаниях.

**П-7. RNG-двойная бомба в бою.** `[VERIFIED проблема, call-sites не проверены]`
Сейчас: (а) `combat_math`: `rng or random` — fallback на глобальный генератор; (б) `impact_engine`: `rng_seed=42` — все бои с дефолтным seed бросают *одинаковую* последовательность кубиков. Детерминизм INV-REPLAY-DETERMINISM дыряв в обе стороны. Лучше: обязательный `rng: random.Random` без default + инъекция `KernelRNG(tick, actor_id, "combat")`. AST-линтер это не ловит — вызов спрятан за `Optional`.

**П-8. `target["status"]` в `apply_damage`.** `[VERIFIED, minor]`
Display-статус `"dead"/"incapacitated"` пишется рядом с каноническим `life_status`. По прецеденту HP-UNIFICATION: combat-слой должен быть reader, не writer.

**П-9. SOLID-чит игрока.** `[VERIFIED нарушение]` 🔴
Сейчас: `actor_id == "player" → contact = SOLID` — атаки игрока не бросают d20, не промахиваются, не критуют. Прямое нарушение CAUSAL CONTRACT §1 («Нет читов… симуляция честна») и прецедента «Игрок подвержен мембранам, как и NPC». Вся честная D&D-машина с KernelRNG для NPC обходится одной строкой для игрока. Лучше: удалить ветку, поднять игрока через `KernelRNG(tick, "player", "combat")` — симметрия восстановится, d20 для игрока уже реализован. Вероятная причина — MVP-упрощение эпохи таверны; по собственным законам проекта это долг, а не фича.

**П-11. Клиентский d20.** `[VERIFIED нарушение]` 🔴 — бросок приходит из запроса: чит + RNG вне ядра. Лучше: серверный `KernelRNG(tick, actor_id, "combat")`.

**П-12. Тройная истина урона.** `[VERIFIED, кандидат DOUBLE TRUTH]` — три живых формулы; канон (ADR-164, ImpactEngine) — фантом. Лучше: провести проводку канона, остальные — проекции.

**П-13. `randint(2, 20)`.** `[VERIFIED]` — фамбл недостижим, крит достижим. Лучше: `randint(1, 20)` или мини-ADR о намеренном исключении.

**Ж-10. Дисциплина DEEP-015.** `[VERIFIED]` ⭐⭐ — проект удалил собственный мёртвый FEP-код с честным комментарием и TODO. Инженерная честность как жемчужина.

### 18.3. Сознательно НЕ предлагаем

- **Log-odds ревизия** — ломает читаемость, перекалибровка всех SUPERBOX ради редкого кейса
- **Байесовский posterior для confidence** — нарушение §18/ADR-O-354 (`confidence ≠ truth probability`)
- **Сигмоиды вместо ступеней** (stress_mod) — реплей-простота и калибровочность ценнее гладкости
- **«Месть/обида/влюблённость» как формулы** — только derived из существующих механизмов (anti-Bond, Р17-П1)

---

## 18.4. Приговор: Active Inference

**«Базируется ли поведение на минимизации свободной энергии?» — НЕТ, подтверждено кодом проекта.**

Контурная карта (финал): аффект ✅ · TIFL ✅ wired (integration.py:213 + state_applicator:1257) · ExpectationStore 💀 DEEP-015 · L6 tanh 💀 никогда не существовал.

**Терминология (обязательна для всех документов):** «prediction-error-driven dynamics inspired by Active Inference» / «Active-Inference-inspired phenomenological architecture». Формулировка «базируется на минимизации свободной энергии» ЗАПРЕЩЕНА до появления вариационного $F[q] = \mathbb E_q[\ln q - \ln p]$ и $\arg\min$-политики. Ожидаемый вопрос рецензента «Where is the variational objective?» — сегодня без ответа; честная граница сильнее ложного клейма. Улии-цитаты: tick_orchestrator:1814, state_applicator:698, idle_services:54, npc_tick_pipeline:387 (TODO «Эпоха 7»).

Выбор действия — argmax аддитивной utility, не argmin G(π). Словарь FEP пережил математику: докстринг «Free Energy Principle» висит на файле-надгробии. Формулировка для статьи (verbatim) — §3.3 Части 6 верификационного отчёта. Два независимых аудита (наш и DEEP-015) — один ответ.

## 19. Таблица: Формула → Код → Тест

| Формула | Файл | Тест |
|---|---|---|
| оператор тика $\Phi$ | `services/tick_orchestrator.py` | `test_tick_orchestrator_full_loop.py` |
| d20/урон D&D | `services/game/combat_math.py` (потребитель — фантом) | `test_impact_engine.py` (tested-but-unwired) |
| клиентский d20 / урон фазы 8 | `api/routes.py:582`, `events/rules_subscriber.py:285` | — (П-11, П-12) |
| ContactLevel лента | `services/combat/impact_engine.py:45` | `test_impact_engine.py` |
| S72-веса + шрам + гистерезис | `services/affective/affective_integrator.py` | `test_physiology_flow.py` |
| CouplingResolver | `services/npc/coupling_resolver.py` | S235/S236 (сон-машина) |
| TIFL + $C$-матрица + травмы | `services/npc/break_progress_engine.py` | `test_decision_calibration.py` |
| кристаллизация ×6 + decay | `services/npc/belief_crystallization_engine.py` | `test_asymmetric_trauma_x6`, `test_belief_decay_model` |
| trust-рамп + ревизия | `trust_based_reliability_provider.py`, `belief_revision_engine.py` | SUPERBOX-RELIABILITY-BASELINE, 002–013 |
| диспозиции | `domain/epistemic_dispositions.py` | SUPERBOX-DISPOSITIONS 6/6 |
| ревизия×S206-числа | — | аналитическое закрытие (§10.2) ✓✓✓ |
| двухрежимный decay | `models/npc_state.py:267`, `models/npc/memory_crystal.py:67` | EMRL E1 приёмка |
| importance | `services/memory/importance_engine.py` | `test_memory_manager_r53.py` |
| соц-триггеры + Fate | `events/social_subscriber.py`, `social/fate_tracker.py` | S198b/S199 |
| модификаторы + приоритеты + маски | `npc/decision_hub.py:378`, `domain/action_priority.py` | `test_action_commitment.py`, SUPERBOX-ACTION-INTEGRITY |
| KernelRNG sha256 | `services/npc/kernel_rng.py` | `test_kernel_rng.py` |
| commitment md5 | `domain/action_commitment.py:102` | `test_commitment_ssm_integration.py` |
| мембраны | `npc/perception_filter.py`, `events/observation_subscriber.py` | SUPERBOX-OBSERVATION 5/5 |
| ISK `[SANDBOX]` | `tests/sandbox/calibration/isk.py` | калибровочная лаборатория |

---

*Файл верифицирован. Секция 18 — для статьи и для roadmap: П-4 и П-9 — дешёвые и честные; П-2 — следующая каузальная глубина; Ж-1…Ж-9 — то, ради чего всё это строилось.*

# ═══════════ КОНЕЦ ФАЙЛА ═══════════