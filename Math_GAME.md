# ENIGMA: Полная Математическая Реконструкция

> **Статус:** Реконструкция из CAUSAL CONTRACT v3.0, ADR Atlas, DTO Registry v8.0
> **Принцип:** CLAIM → CODE → TEST — только формулы, подтверждённые в runtime

---

## 1. Пространство состояний

### 1.1. Глобальное состояние системы

$$
\mathcal{S}_t = \left( W_t, \; \{S_i^t\}_{i=1}^{N}, \; \mathcal{E}_t, \; \mathcal{C}_t \right)
$$

где:

| Символ | Значение | Код |
|--------|----------|-----|
| $W_t$ | World State (пространство, объекты, топология) | `scene_state["world_objects"]` |
| $S_i^t$ | Состояние агента $i$ | `NPCState` |
| $\mathcal{E}_t$ | Epistemic Store (все убеждения) | `EpistemicStore` per-agent |
| $\mathcal{C}_t$ | Commitment Registry (активные обязательства) | `scene_state["active_commitments"]` |

### 1.2. Состояние агента

$$
S_i^t = \left( B_i^t, \; M_i^t, \; H_i^t, \; R_i^t, \; P_i^t \right)
$$

| Компонент | Описание | Код |
|-----------|----------|-----|
| $B_i^t$ | Body State (физиология) | `body_state` |
| $M_i^t$ | Memory (L1 Chronicle + L2 Beliefs + L3 Drives) | `L1Chronicle`, `CrystallizedBelief`, `EffectiveDrives` |
| $H_i^t$ | Perceptual Kernel (субъективное восприятие) | `PerceptualKernel` |
| $R_i^t$ | Relationship State (0–100) | `RelationshipStore` |
| $P_i^t$ | Psychic State (воля, стресс, аффект) | `psyche` |

---

## 2. Оператор тика (Master Equation)

$$
\boxed{
\mathcal{S}_{t+1} = \Phi(\mathcal{S}_t, \; E_t)
}
$$

где $E_t$ — внешние вмешательства (player/DM input), а $\Phi$ — оператор тика, реализуемый `TickOrchestrator._run_core_phases()`.

### 2.1. Разложение оператора

$$
\Phi = \phi_{10} \circ \phi_9 \circ \phi_8 \circ \phi_7 \circ \phi_6 \circ \phi_5 \circ \phi_4 \circ \phi_3 \circ \phi_2 \circ \phi_1 \circ \phi_{0.6} \circ \phi_{0.5} \circ \phi_0
$$

---

## 3. Слой L0: Тело (Body)

### 3.1. Физиологические оси

$$
B_i^t = \left( hp_i^t, \; pain_i^t, \; fatigue_i^t, \; blood_i^t, \; shock_i^t, \; consciousness_i^t, \; life_i^t \right)
$$

| Переменная | Диапазон | Код |
|------------|----------|-----|
| $hp_i^t$ | $[0, max\_hp]$ | `body_state["current_hp"]` |
| $pain_i^t$ | $[0, 100]$ | `body_state["pain"]` |
| $fatigue_i^t$ | $[0, 100]$ | `body_state["fatigue"]` |
| $blood_i^t$ | $[0, \infty)$ | `body_state["blood_loss"]` |
| $shock_i^t$ | $[0, 1]$ | `body_state["shock_impulse"]` |
| $life_i^t$ | $\{ALIVE, DEAD\}$ | `body_state["life_status"]` |

### 3.2. Уравнение урона (D&D 5e, ADR-164)

$$
\text{damage} = f(\text{attack\_roll}, \; \text{AC}_{target}, \; \text{contact\_level})
$$

где `attack_roll` вычисляется через `combat_math.py` с `KernelRNG(tick, npc_id, salt)`:

$$
\text{attack\_roll} = d20 + \text{modifier} \quad \text{via KernelRNG}
$$

$$
\text{ContactLevel} = \begin{cases}
\text{MISS} & \text{roll} < \text{AC} - 5 \\
\text{GLANCING} & \text{AC} - 5 \leq \text{roll} < \text{AC} \\
\text{PARTIAL} & \text{roll} = \text{AC} \\
\text{SOLID} & \text{AC} < \text{roll} < \text{AC} + 5 \\
\text{PERFECT} & \text{roll} \geq \text{AC} + 5
\end{cases}
$$

### 3.3. Injury Processor (ADR-123)

$$
\text{bleeding\_rate} = \text{structural\_damage} \times \text{zone\_rate} \times \text{damage\_type\_modifier}
$$

### 3.4. Vital State (три независимые оси)

$$
\text{Life}: \{ALIVE, DEAD\} \quad \text{via } evaluate\_vital\_state(B_i^t)
$$

$$
\text{Consciousness}: \{CONSCIOUS, UNCONSCIOUS\} \quad \text{via } is\_conscious(B_i^t)
$$

$$
\text{Capability}: \{CAPABLE, INCAPABLE\} \quad \text{via } is\_capable(B_i^t)
$$

---

## 4. Слой L0: Восприятие (Perception)

### 4.1. Функция наблюдения

$$
O_i^t = \mathcal{P}_i(W_t)
$$

где $\mathcal{P}_i$ зависит от:
- позиции $pos_i$
- радиуса восприятия $r_i$
- линии видимости $LOS_i$
- состояния тела $B_i^t$ (Somatic Gate)
- режима связанности (сон/бодрствование)

### 4.2. PerceptualKernel (субъективная модель)

$$
H_i^t = \left( \text{threat}, \; \text{trust}, \; \text{uncertainty}, \; \text{anomaly}, \; \text{aggr\_inh}, \; \text{compliance}, \; \text{somatic\_urg} \right)
$$

Все поля в $[0, 1]$.

### 4.3. Аффективная нагрузка (ADR-O-206)

$$
\text{surprise\_delta} = |L_i^t - L_i^{t-1}|
$$

где $L_i^t$ — `affective_load`.

$$
\text{stress\_mod} = \begin{cases}
1.25 & \text{if } stress_i > 70 \wedge \text{surprise\_delta} > 0.2 \\
1.10 & \text{if } stress_i > 50 \vee \text{surprise\_delta} > 0.1 \\
1.00 & \text{otherwise}
\end{cases}
$$

### 4.4. CouplingProfile (сон, ADR-O-356)

$$
\kappa_i^t = \left( v_i^t, \; h_i^t, \; m_i^t, \; a_i^t, \; \text{mode}_i^t \right)
$$

где:

| Параметр | Диапазон | Значение |
|----------|----------|----------|
| $v_i^t$ (vision mult) | $[0, 1]$ | Внешнее зрение |
| $h_i^t$ (hearing mult) | $[0, 1]$ | Внешний слух |
| $m_i^t$ (motor mult) | $[0, 1]$ | Моторный выход |
| $a_i^t$ (activation mult) | $[0, 1]$ | Активация памяти |
| $\text{mode}$ | enum | FULL_WAKE / DROWSY / SLEEP / DEEP_SLEEP / REM |

Вычисляется каждый тик из $sleep\_pressure + arousal$ через `CouplingResolver`.

### 4.5. Мембрана слуха

$$
\text{can\_hear}(i, e) = \begin{cases}
\text{true} & d(i, e_{source}) \leq e_{radius} \times h_i^t \\
\text{false} & \text{otherwise}
\end{cases}
$$

---

## 5. Слой L1: Хроника (Chronicle)

### 5.1. Append-only запись

$$
L1_i = \left[ e_1, e_2, \ldots, e_k \right], \quad e_j \text{ immutable}
$$

Каждое $e_j$:

$$
e_j = (\text{tick}, \; \text{source\_id}, \; \text{target\_id}, \; \text{effect\_value}, \; \text{observation\_weight}, \; \text{event\_type})
$$

**Закон:** $|L1_i|$ только растёт. Удаление запрещено (ADR-O-208).

### 5.2. Temporal Identity Formation (TIFL, ADR-TIFL-001)

$$
\Delta d_{i,x} = \epsilon \cdot \text{PE}_{i,x} \cdot \text{plasticity}_i
$$

где:
- $\Delta d_{i,x}$ — дрейф драйва $x$ агента $i$
- $\epsilon$ — LEARNING_RATE (константа)
- $\text{PE}_{i,x}$ — prediction error по оси $x$
- $\text{plasticity}_i = \max(0.1, \; 1.0 - \text{rigidity}_i)$

$$
d_{i,x}^{t+1} = d_{i,x}^t + \Delta d_{i,x}
$$

### 5.3. Evidence Aggregation (L1.5 PatternDetector)

$$
\text{cumulative\_effect}(source) = \sum_{j} e_j.\text{effect\_value} \cdot e_j.\text{observation\_weight}
$$

$$
\text{behavior\_variance}(source) = \text{Var}\left[ \{e_j.\text{effect\_value}\} \right]
$$

---

## 6. Слой L2: Идентичность и убеждения

### 6.1. Triple Membrane (ADR-O-306)

$$
\text{passed}_{membrane} = \text{Physics}(e) \wedge \text{Personality}(e, \text{archetype}) \wedge \text{Social}(e, \text{norms})
$$

### 6.2. Belief Crystallization (L2.5)

$$
w_{new} = w_{old} + \alpha \cdot \text{evidence\_strength}
$$

где $\alpha$ — калибруемая скорость.

**Асимметричная травма (ADR-O-307):**

$$
w_{refute} = w_{confirm} \times 6
$$

Опровержение сильнее подтверждения в 6 раз.

### 6.3. Belief Decay (ADR-O-305.1)

$$
w(t) = w(t_0) \cdot e^{-\lambda (t - t_0)}
$$

где $\lambda$ зависит от каузальной глубины:

$$
\lambda = \begin{cases}
0.01 & \text{surprise} > 0.3 \quad \text{(травма — забывается очень медленно)} \\
0.03 & \text{load} > 0.5 \quad \text{(вовлечённость — медленно)} \\
0.05 & \text{otherwise} \quad \text{(базовая скорость)}
\end{cases}
$$

### 6.4. Identity Stability Kernel (ISK, ADR-O-211)

Микро-шум $\xi$ инъектируется в психику:

$$
\delta_g = \|g(\text{psyche} + \xi) - g(\text{psyche})\|
$$

Классификация:

$$
\text{Mode} = \begin{cases}
\text{CRYSTAL} & \mu < 0.01 \wedge \sigma < 0.01 \\
\text{PLASTIC} & \mu > 0.01 \wedge \sigma < 0.5\mu \\
\text{BRITTLE} & \sigma > 1.5\mu \\
\text{CHAOTIC} & \text{otherwise}
\end{cases}
$$

где $\mu = \mathbb{E}[\delta_g]$, $\sigma = \text{Var}[\delta_g]$.

### 6.5. Inertia of Identity

$$
\text{value}_{new} = \text{value}_{old} \cdot \rho + \Delta \cdot (1 - \rho)
$$

где $\rho = \text{rigidity} \in [0, 1]$.

---

## 7. Слой L3: Драйвы (эфемерные)

### 7.1. Drive Resolution Pipeline (DRP, ADR-O-208)

$$
\text{EffectiveDrives}_i^t = \text{Projection}(L0_{\text{archetype}}, \; L1_{\text{scars}}, \; \text{Context}_i^t)
$$

**Жизненный цикл:** рождается в начале тика, умирает в конце. Персистенция запрещена.

### 7.2. Нормализация

$$
\sum_{x} \text{drive}_{i,x}^t = 1.0
$$

**Инвариант L5:** $\text{sum} \neq 1.0 \Rightarrow$ `OntologyViolationError`.

### 7.3. PE → Drive Modifier (L6, ADR-S93.2)

$$
\text{mod}_{i,x} = \tanh\left(\text{PE}_{i,x}\right) \cdot \text{Clamp}(0.25)
$$

где Clamp ограничивает $|\text{mod}| \leq 0.25$ (PE не доминирует).

---

## 8. Эпистемический слой (Epistemic Core)

### 8.1. Claim → Belief Revision

**Вход:** `ClaimEvent(speaker, listener, proposition, target, confidence, tick)`

$$
\text{reliability} = f_{\text{trust}}(\text{trust}_{listener \to speaker})
$$

где $f_{\text{trust}}$ — `TrustBasedReliabilityProvider.compute()`:

$$
f_{\text{trust}}(\tau) = \begin{cases}
\tau / 100 & \tau > 0 \quad \text{(позитивный)} \\
-0.5 & \tau < -30 \quad \text{(обратный эффект)} \\
0.0 & \text{otherwise}
\end{cases}
$$

**Обновление убеждения:**

$$
c_{new} = \max\left(0.0, \; c_{old} + \Delta c\right)
$$

где:

$$
\Delta c = \text{reliability} \cdot \text{speaker\_confidence} \cdot \beta
$$

и $\beta$ — калибруемый параметр.

### 8.2. Two-Channel Reliability (ADR-O-360)

$$
r_{\text{source}} = \begin{cases}
f_{\text{trust}}(\tau) & \text{if channel} = \text{testimony} \\
r_{\text{obs}} & \text{if channel} = \text{direct\_observation}
\end{cases}
$$

где $r_{\text{obs}} = \text{DIRECT\_OBSERVATION\_RELIABILITY} < 1.0$ (калибруемая, по умолчанию 0.9).

### 8.3. Epistemic Modifier Contract (ADR-O-355)

$$
\boxed{
\text{final\_score} = \text{base\_score} + \sum_{k} m_k
}
$$

**Свойства:**
- Аддитивность (нет multiplier, cap, override)
- Коммутативность (порядок не важен)
- Изоляция (нет мутации входа)
- Чистая функция

### 8.4. Epistemic Context → DecisionHub

$$
\text{modifiers} = \text{max\_confidence} \times 0.992
$$

Точная формула из `to_modifiers()`.

### 8.5. Observation Channel (ADR-O-360)

Мембрана наблюдения:

$$
\text{witness}(i, e) = \begin{cases}
\text{true} & LOS(i, e) \wedge d(i, e_{src}) \leq r_{\text{event}} \\
\text{false} & \text{otherwise}
\end{cases}
$$

---

## 9. Социальная физика (Causal Field Layer)

### 9.1. Эмиссия давления

Агент $i$ излучает 5-мерный вектор:

$$
\mathbf{E}_i = (\text{fear}, \; \text{control}, \; \text{significance}, \; \text{desire}, \; \text{volatility})
$$

### 9.2. Суперпозиция с насыщением (CFL)

$$
\boxed{
S_{\text{env}}(p) = \min\left(\sum_{i} \mathbf{E}_i \cdot e^{-d(p, p_i) / r_i}, \; C_{\max}\right)
}
$$

где:
- $p$ — точка пространства
- $d(p, p_i)$ — расстояние от агента $i$ до точки $p$
- $r_i$ — `decay_radius` агента $i$
- $C_{\max}$ — cap насыщения

### 9.3. Total Pressure

$$
S_{\text{total}} = S_{\text{internal}} + S_{\text{env}}
$$

(после весовой нормализации CPN)

### 9.4. Emergent Topology

Из суперпозиции + cap возникают:
- **Fear Basins:** области с критическим $\text{fear\_pressure}$
- **Authority Wells:** области высокого $\text{control\_pressure}$
- **Social Fronts:** границы между зонами

---

## 10. Слой L4: Решение (DecisionHub)

### 10.1. Utility Deformation

$$
\text{score}(a) = \text{base}(a) + \sum_{k} m_k(a)
$$

где $m_k$ — модификаторы из:
- `epistemic_modifiers` (§8.3)
- `social_modifiers_map` (Relationship)
- `reputation_modifiers_map`
- `drives_modifiers` (L3)
- `pe_modifiers` (L6)

### 10.2. Выбор действия

$$
a_i^* = \arg\max_{a \in A_i} \left[ \text{score}(a) \right]
$$

### 10.3. Intent → Commitment

$$
\text{candidate\_priority}(a) = \begin{cases}
1 & \text{if domain} = \text{EXPLORATION} \\
2 & \text{if domain} = \text{ROUTINE} \\
3 & \text{if domain} = \text{SOCIAL} \\
6 & \text{if domain} = \text{SLEEP} \\
6 & \text{if domain} = \text{SURVIVAL} \\
7 & \text{if domain} = \text{WINDOWED}
\end{cases}
$$

**Арбитраж (S203.4):**

$$
\text{verdict} = \begin{cases}
\text{INTERRUPT} & \text{if candidate\_priority} > \text{incumbent\_priority} + 3 \\
\text{REJECT} & \text{otherwise}
\end{cases}
$$

### 10.4. Needs vs Schedule

$$
\text{weight}(\text{Needs}) = 0.8 > \text{weight}(\text{Schedule}) = 0.6
$$

Needs перезаписывают Schedule при конфликте.

### 10.5. Steal Affinity (ADR-O-362)

$$
\text{steal\_affinity}_i = \begin{cases}
0.8 & \text{archetype}_i = \text{thief} \\
0.08 \times \text{desire}_i & \text{otherwise}
\end{cases}
$$

---

## 11. Движение (Traversal)

### 11.1. TraversalState

$$
T_i = \left( \text{source}, \; \text{target}, \; \text{waypoints}, \; \text{progress}, \; \text{speed}, \; \text{status} \right)
$$

**FSM:**

$$
\text{PENDING} \to \text{MOVING} \to \text{COMPLETED} | \text{CANCELLED}
$$

### 11.2. Движение как результат

$$
\text{Intent} \to \text{DecisionHub} \to \text{MovementEngine} \to \text{SceneChange} \to \text{apply}
$$

### 11.3. Позиция

$$
pos_i^{t+1} = \begin{cases}
\text{interpolate}(pos_i^t, \; \text{target}) & \text{if MOVING} \\
pos_i^t & \text{otherwise}
\end{cases}
$$

### 11.4. Windup (подготовка действия)

$$
\text{attack}: \text{windup} = 2 \text{ тика}
$$

$$
\text{steal}: \text{window} = 2 \text{ тика}
$$

---

## 12. Отношения (Relationship)

### 12.1. RelationshipStore (SSOT, 0–100)

$$
r_{ij} \in [0, 100], \quad \forall i \neq j
$$

### 12.2. Детерминированные триггеры (S199)

| Действие | $\Delta r$ | Домен |
|----------|-----------|-------|
| gossip | $-2.0$ | trust |
| accuse | $+1.0$ | fear |
| praise | $+1.5$ | trust |

### 12.3. FateTracker

$$
\text{stability}_i = g(\text{stress}_i)
$$

$$
\text{threat}_i = g(\text{threat\_gradient}_i)
$$

$$
\text{Fate}_i = \begin{cases}
\text{BROKEN} & \text{critical\_ticks} \geq 5 \\
\text{DEATH} & \text{life} = \text{DEAD} \\
\text{ESCAPE} & \text{left scene} \\
\text{ALIVE} & \text{otherwise}
\end{cases}
$$

---

## 13. Память (Memory)

### 13.1. Decay Speed (ADR-O-206)

$$
\text{decay\_rate} = \begin{cases}
0.01 & \text{surprise} > 0.3 \\
0.03 & \text{load} > 0.5 \\
0.05 & \text{otherwise}
\end{cases}
$$

### 13.2. Importance Weight

$$
\text{importance} = h(\text{surprise\_delta}, \; \text{context})
$$

Не зависит от `EmotionTag` (ADR-O-206).

### 13.3. Memory Hierarchy

$$
\text{STM} \xrightarrow{\text{promote}} \text{L2} \xrightarrow{\text{promote}} \text{Campaign}
$$

при $\text{importance} > \theta_{\text{promote}}$.

---

## 14. RNG и детерминизм

### 14.1. KernelRNG (ADR-O-301)

$$
\xi = \text{KernelRNG}(tick, \; npc\_id, \; salt)
$$

**Гарантия:** одинаковый $(tick, npc\_id, salt) \Rightarrow$ одинаковый $\xi$.

### 14.2. Replay Determinism

$$
\text{replay}(\mathcal{S}_0, E_{0:t}) = \mathcal{S}_t \quad \forall \text{ runs}
$$

(при том же seed и LLM-кэше)

---

## 15. LLM-граница

### 15.1. Позиция LLM в системе

$$
\text{LLM}: (B_i^t, M_i^t, R_i^t, I_i^t) \to \text{text}_i^t
$$

LLM **не участвует** в вычислении $\Phi$. Ядро:

$$
\boxed{
\text{Simulation} \to \text{State} \to \text{LLM} \to \text{Language}
}
$$

### 15.2. DeltaGate (E2.0)

$$
\text{Proposal} \xrightarrow{\text{Gate}} \text{StateDelta} \xrightarrow{\text{StateApplicator}} \mathcal{S}_{t+1}
$$

LLM предлагает, Gate фильтрует, Applicator применяет.

---

## 16. Итоговая каузальная цепочка

$$
\boxed{
\begin{aligned}
W_t &\xrightarrow{\mathcal{P}_i} O_i^t \xrightarrow{\text{Filter}} H_i^t \\
&\xrightarrow{\text{L1}} M_i^t \xrightarrow{\text{L2.5}} B_i^t \\
&\xrightarrow{\text{DRP}} D_i^t \xrightarrow{\text{DecisionHub}} I_i^t \\
&\xrightarrow{\text{Executor}} X_i^t \xrightarrow{\text{Applicator}} W_{t+1}
\end{aligned}
}
$$

где:
- $O_i^t$ — наблюдение
- $H_i^t$ — PerceptualKernel
- $M_i^t$ — память (L1 + L2)
- $B_i^t$ — убеждения (L2.5)
- $D_i^t$ — драйвы (L3)
- $I_i^t$ — интент
- $X_i^t$ — действие
- $W_{t+1}$ — новый мир

---

## 17. Инварианты (математические законы)

### INV-1: Epistemic Isolation
$$
\text{Belief} \neq \text{Truth}, \quad \text{confidence} \neq P(\text{truth})
$$

### INV-2: Causal Closure
$$
\forall \text{ change in } W: \exists \text{ causal chain in } \Phi
$$

### INV-3: Temporal Isolation
$$
\Phi(S_t, E_t) \text{ не может изменить входные данные } S_t
$$

### INV-4: L3 Ephemerality
$$
D_i^t \neq D_i^{t+1} \text{ (рекомпьютится каждый тик)}
$$

### INV-5: Drive Normalization
$$
\sum_x D_{i,x}^t = 1.0
$$

### INV-6: CFL Saturation
$$
\|\mathbf{S}_{\text{env}}(p)\| \leq C_{\max} \quad \forall p
$$

### INV-7: Append-Only Chronicle
$$
|L1_i(t+1)| \geq |L1_i(t)|
$$

### INV-8: Modifier Additivity
$$
\text{final} = \text{base} + \sum_k m_k, \quad \text{commutative}
$$

### INV-9: Kernel RNG Determinism
$$
\text{KernelRNG}(t, i, s) = \text{const} \quad \text{for fixed } (t, i, s)
$$

### INV-10: Single Writer
$$
\forall \text{ field } f: |\{\text{writers of } f\}| = 1
$$

---

## 18. Таблица соответствия: Формула → Код

| Формула | Файл | Тест |
|---------|------|------|
| $\Phi$ (оператор тика) | `svc/tick_orchestrator.py` | `test_tick_orchestrator_full_loop.py` |
| $S_{\text{env}}$ (CFL) | `svc/social/causal_field_layer.py` | — |
| $c_{new}$ (belief revision) | `svc/npc/belief_revision_engine.py` | `SUPERBOX-002..013` |
| $\text{score}(a)$ (DecisionHub) | `svc/npc/decision_hub.py` | `test_decision_calibration.py` |
| $\text{damage}$ (D&D 5e) | `svc/combat/combat_math.py` | `test_impact_engine.py` |
| $\Delta d_{i,x}$ (TIFL) | `svc/npc/break_progress_engine.py` | — |
| ISK | `tests/sandbox/calibration/isk.py` | — |
| $\text{CouplingProfile}$ | `svc/npc/sleep_lifecycle_service.py` | — |
| $\text{steal\_affinity}$ | `svc/npc/decision_hub.py` | `SUPERBOX-AGENCY-STEAL` |
| CFL Superposition | `svc/social/causal_field_layer.py` | — |

---

## 19. Что НЕ реализовано (Future / Research)

| Гипотеза | Статус |
|----------|--------|
| $F = D_{KL}[Q(s) \| P(s\|o)] - \ln P(o)$ (Free Energy) | не в runtime |
| $\pi^* = \arg\min_\pi G(\pi)$ (Active Inference policy) | не в runtime |
| $U_M = I \cdot R \cdot U - C$ (Bounded Rationality) | не в runtime |
| Second-order ToM ($A$ believes $B$ believes $X$) | не в runtime |
| $d(h) = 0.8^h$ (information propagation decay) | не подтверждено |

---

*Документ: полная математическая реконструкция. Только формулы, доказанные в production runtime ENIGMA V.0.5.3.9.5.*