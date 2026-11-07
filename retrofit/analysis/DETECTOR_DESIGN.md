# DETECTOR DESIGN — "SENTRY" (Sensor-Enabled Early Notification Terminal-lite)

Operator-assist layer for the RETROFIT AI 2026 benchmark.
Design grounded in the measured evidence of `DEEP_DIVE_REPORT.md`; every threshold below cites its
empirical or scoring basis. Target: beat baseline B1 (validation composite 78.0) decisively, with a
projected ~88–92 from quantified levers (§10).

```
telemetry (1 s parquet) ─┐
operating_context (1 min)├─► [1] INGEST & CANONICALIZE ─► 1-min feature grid + quality mask
assets.csv (static)     ─┘                                   │
                                                             ▼
                                             [2] REGIME MODEL  (per-asset, per-speed-bin
                                                  robust baselines; benign-transient veto)
                                                             │
                        ┌────────────────────────────────────┼──────────────────────────┐
                        ▼                                    ▼                          ▼
        [3] PHYSICS RESIDUAL ENGINE              [4] SNAPSHOT ENVELOPE ANALYZER   [5] CHANNEL-HEALTH
        (pump-curve residuals, NPSH margin,      (BPFO/BPFI/1x/2x/VP demod;       (stuck/step/drift/
         VFD-compensation-aware)                  resonance-hump trend)            noise/gateway)
                        │                                    │                          │
                        └──────────────────┬─────────────────┴──────────────────────────┘
                                           ▼
                            [6] FUSION & DIAGNOSIS  (fault-hypothesis evidence scores,
                             benign vetoes, sensor-vs-machine gating, UNKNOWN fallback)
                                           ▼
                            [7] CONFIDENCE CALIBRATION (per-class isotonic on train)
                                           ▼
                            [8] ALERT MANAGER (burst discipline, 12-h reminder cadence,
                             deadline-aware escalation, actions & evidence text)
                                           ▼
                        predictions CSV (+ evidence, recommended_action) · operator UI feed
```

---

## 1. Scoring math → design budget (from BENCHMARK_RULES.md §4)

Composite = 100·(0.35·F1 + 0.20·Timeliness + 0.25·FaultTypeRecall + 0.10·ClassRecall + 0.10·AlertBurden).

| Lever | B1 measured | Design target | Δ composite |
|---|---|---|---|
| Fault-type recall | 0.444 | ≥ 0.70 | +2.5 pts per +0.10 → **+6.5** |
| Timeliness | 0.863 | ≥ 0.93 | **+1.4** |
| Event F1 | 0.889 | ≥ 0.93 | **+1.5** |
| Alert burden (false+excess/day) | 0.07 | ≤ 0.05 | **+0.1** |
| Class recall | 0.889 | keep ≥ 0.89 | 0 |
| | | **projected** | **≈ 88–90** |

Hard constraints that shape the pipeline:
- **Causality**: at alert time t, only data ≤ t. The pipeline is streaming by construction (1-min steps;
  snapshots every 4 h as they arrive). No batch leakage anywhere.
- **Burst rule**: alerts < 5 min apart merge into one burst scored once. ⇒ 1-min decision cadence with a
  per-asset in-burst latch; a burst may name exactly ONE fault_type and ONE event_class (else both credits
  void). Merge-then-name is handled in [8].
- **Repeat rule**: one free repeat episode per 12 h; further repeats count as false. ⇒ reminder latch.
- **Event window opens** at `max(onset, detectable − 6h)`; alerts earlier than that match nothing and cost
  precision if no event exists. ⇒ detection thresholds are set just above the *label's own* detectability
  rule (10-min mean > 3× noise) so we fire inside the window, not before it opens.
- **Unobservable events are removed** (e.g., PUMP-05 bearing wear on T0). ⇒ tier-aware capability map in
  [6] so we never *guess* an unobservable fault type (a wrong-type alert on an unobservable event still
  matches nothing → false alert).

## 2. Module [1] — Ingest & canonicalize

- Read the partitioned parquet per asset/day; restore `asset_id`, `day` partition keys.
- Reindex to the 1 s grid; **absent rows = gateway outage candidate** (DATA_DICTIONARY §telemetry:
  rows are absent during outages, not NaN) — pass gap run-lengths to [5][6] (COMMUNICATION_LOSS needs
  ≥ ~30 min of missing rows to be confident; TRAIN shows 1.2–1.4 h min duration).
- Pull `features_1min.parquet` (mean/std/min/max/count per channel) as the analysis grid — it matches the
  upstream aggregation exactly (proven in deep-dive stage 2) so we avoid recomputing 7.2 M rows on-device:
  the edge implementation computes the same 1-min aggregates from the raw stream.
- Sparse T1 wireless channels (300 s update): keep `__count` to distinguish "device silent (sensor
  fault)" from "low-variance but present".
- Output: per-asset 1-min frame `{channel__mean, __std, __count, operating_mode, running_fraction,
  quality_any, rows}` + static `assets.csv` row.

## 3. Module [2] — Regime model (supersedes B1's first-24 h z)

Measured problem (deep-dive §2, stage-1 labels): faults are pre-existing from window start (PUMP-02/04),
the healthy reference must come from *regime-conditional* structure, not a single "healthy" median.
Also VFD assets span 0.5–1.0 r with regime-dependent noise.

- **Features for conditioning**: `motor_speed_rpm` bins (0.1 r-width), `operating_mode == RUNNING`,
  `duty_demand_pct` (context), `supply_water_temp_c` (season), schedule state.
- **Baseline per (asset, channel, speed-bin)**: robust median + 1.4826·MAD, fit on the most recent
  rolling 7 days of minutes that are (a) RUNNING, (b) not currently latched as event, (c) not in
  transient veto (see below), (d) updated online — *never* conditioned on future data.
- **Drift subtraction**: slow baseline drift of the *asset* (not the sensor) is tracked by an
  exponential smoother with τ = 48 h; sensor-drift detection in [5] works on the residual of the
  10-min means against the *drift-corrected but not yet confirmed* baseline, so slow growth is not
  silently absorbed before diagnosis completes (τ chosen > all observed fault growth rates in the data:
  clog to deadline ≈ 1.3–2 d).
- **Transient veto list** (mute detection, record for later benign annotation):
  STARTING +3 min (DOL inrush 6.5–7×, ramp), STOPPING + coast-down (4–8 s tc), minutes with
  `quality_any` STALE/STARTUP_INHIBIT, load change = speed-bin boundary crossing with z-change < 3σ on
  coupling set (benign by construction), supply-voltage sag signature (current up + power down + fast —
  physically impossible for a pump fault, veto 10 min), HEAVY_WEATHER proxy: context has
  `sea_state_hs_m ≥ 3` AND suction-pressure oscillation dominant period ≈ roll period (7–12 s band in
  1-s data) ⇒ veto hydraulic alarms for its duration but keep a "stow investigation" annotation.

## 4. Module [3] — Physics residual engine (targets the +6.5 pts from fault typing)

### 4.1 Expected operating point from assets.csv

For each 1-min RUNNING step, with r = n/n_rated and x = valve position:
- Pump curve: `H(Q,r) = H_BEP·(h0 r² − (h0−1)(Q/Q_BEP)²)`, `h0 = P_shutoff/H_BEP` (P_shutoff in assets).
- Efficiency: `η = η_r·q(2−q)`, `q = Q/(r·Q_BEP)`, `η_r = 1−(1−η_BEP)·r^−0.1`.
- Expected shaft power `P_exp(Q,r,η)`; electrical `P_in = P_shaft/η_motor`, with motor model
  (losses, pf(λ)) to compare against `motor_power_kw`.
- System curve: `H_sys = H_static + (K_pipe·R̂ + K_valve(x̂) + K_suction(ĉ))·Q²` with the equal-percentage
  valve law `K ∝ 50^{2(1−x)}`; R̂, ĉ = slowly-tracked multipliers (init 1.0).

Two cases:
- **Flow available (T2)**: solve expected Q* from pump∩system given r̂; residuals
  `r_H = H_meas − H(Q*); r_Q = Q_meas − Q*; r_P = P_meas − P_exp; r_suc = suction_meas − expected`.
- **No flow meter (T0/T1)**: use the *pressure-pair* and current as Q-proxies on fixed-speed assets
  (Q fixed by curve at r=1): residual set degrades to (P_dis, P_suc, I). Track implied-Q from the
  head-flow inversion of the suction-discharge pair where both gauges exist.

### 4.2 Measured fault-direction table (from deep-dive stage 2 — these numbers ARE the classifier prior)

| Hypothesis | Evidence vector (units: % of healthy-mean, sign) | Discriminating note |
|---|---|---|
| SUCTION_STRAINER_CLOGGING (fixed speed) | suc −17, dis −4, I −0.4, rest ≈0; later: cavitation pre-signature σ̂↓ | suction-only, quiet |
| SUCTION_STRAINER_CLOGGING (VFD) | **speed +6, power +15, suc −9**, dis ≈flat | controller compensates — current/power *rise* |
| CAVITATION | suc →−526 %, accel +507 %, vel +60 %, I −14; σ̂<1.15 ≥5 min | emergent; label ≈0-lead ⇒ fires with event |
| DISCHARGE_RESTRICTION | flow −8.6, bearing_temp +12.8, accel +374 % (off-BEP), dis +2 fixed-speed, speed −1 on VFD | flow↓ + off-BEP vibration + temp↑ (heat), NOT suction↓ |
| AIR_ENTRAINMENT | suc −47, power −9, flow −7, erratic vel | head loss + erratic broadband; correlates w/ low basin level / Hs |
| IMPELLER_WEAR | dis −small, H-residual −small at same Q, power ≈flat, NO acceleration rise | vs restriction: no off-BEP accel, no temp rise |
| IMBALANCE | 1× vel ↑ w/ r² pattern, accel RMS mild, crest ≈flat, no hydraulic residual | snapshots: 1× line growth, no BPFO/BPFI |
| MISALIGNMENT | 1×/2× vel ↑ *load-dependent* (0.5+0.5λ), power +3, bearing/wind temp mild ↑, small I↑ | 2× line in snapshot is the physical tell |
| BEARING_WEAR | accel +75 %, crest +47 %, hydraulics clean, BPFO envelope growth | snapshots decisive (§5) |

Implementation: fuzzy scoring `S_h = Σ_c w_c · clip(z_c·dir_{h,c}, 0, ∞)` over the pattern matrix with
weights = inverse of the measured cross-contamination (deep-dive caveat about overlapping sister events
is handled by masking co-latched event windows when fitting the weights on TRAIN; labels provide ground
truth). Pattern scores feed [6]; no hard rules.

### 4.3 NPSH margin estimator (cavitation precursor)

`σ̂ = NPSHa/NPSH3(Q)`, NPSHa from suction gauge + velocity-head correction + Antoine p_v(T_fluid) +
loop/sea contributions (context `suction_static_head_m`), NPSH3 from assets curve
`NPSH3_BEP·r²(0.55+0.45q²·⁶)`. With roll oscillation on ships: use a 60-s robust low-pass of the
1-s suction signal (roll periods 7–12 s, i.e. 0.08–0.14 Hz — a 60-s window suppresses it) before σ̂.
- σ̂ < 1.30 sustained 60 s ⇒ "margin shrinking" (precursor, feeds clog diagnosis weight, no alert alone).
- σ̂ < 1.15 sustained 5 min ⇒ CAVITATION alert instantly (label counts episode at onset; 0.1-h lead is
  achievable only by matching the label's own definition).

## 5. Module [4] — Snapshot envelope analyzer (bearing early evidence; the deep-dive's 21 dB day-0 result)

Trigger: each new `vibration_snapshots.parquet` row (every ~4 h on T1/T2 while running).

1. Hann-windowed PSD (fs 10.24 kHz, N = 10240); f₁ = rpm_at_capture/60.
2. **Learned resonance band** per asset: peak of the running median spectrum in 2–3.5 kHz from the
   asset's earliest snapshots (PUMP-04 measured: 2.6–3.0 kHz). Set once, verify against drift.
3. Band-pass the raw record around the resonance → Hilbert envelope → envelope spectrum 0–250 Hz.
4. Measure: `E_BPFO, E_BPFI, E_1x, E_2x, E_3x, E_VP` = max envelope spectral line in ±2 Hz of each
   order×f₁; SNR vs median of envelope spectrum over 20–400 Hz excluding ±6 Hz around all named lines
   (the deep-dive's corrected metric; naive max-vs-σ overestimates because the floor rides with signal).
5. Also collect PSD-based: broadband hump ΔdB in the learned band; 1×/2× PSD-line (velocity-band) levels.
6. **Trend tracker per asset** (robust EWMA τ = 3 snapshots + CUSUM on log E_BPFO):
   - BEARING_WEAR alert when E_BPFO SNR ≥ 15 dB for ≥ 2 consecutive snapshots (8 h) AND upward
     CUSUM > 4σ — day-0 SNR was 20.8 ⇒ fires immediately on pre-existing faults, as the label does.
   - Post-repair latch: if E_BPFO falls > 30 dB below its running peak, close the event (repair seen).
   - Type discrimination: BPFO-dominant ⇒ BEARING_WEAR; if instead 2×/3× lines grow with load-dependence
     and BPFO flat ⇒ MISALIGNMENT; 1× PSD growth with r² and clean envelope ⇒ IMBALANCE.
   - This also *clears* PUMP-08-E02-type confusion (B1 guessed strainer/cavitation on a bearing fault).

Edge cost: one 10.24k record / 4 h → trivial CPU; the only FFT pipeline on-device.

## 6. Module [5] — Channel-health (sensor faults; +10 % class recall protection, +type credit)

Detection always covariate-gated: a sensor hypothesis requires the *physically coupled channels to be
healthy* (measured coupling sets: suc↔Q↔dis↔I/P; b_temp↔accel; I↔P; Q↔dis). Machine hypotheses require
≥ 2 coupled channels coherent. Conflict resolution goes to [6].

| Fault | Test (on 1-min stats) | Label-rule alignment |
|---|---|---|
| SENSOR_STUCK | rolling 30-min count>0 and (max−min) < 0.2·noise_p99.9 over ≥ 30 min | observable after > normal constant-run p99.9 (≥10 min per TECHNICAL_MODEL §11) |
| SENSOR_CALIBRATION_SHIFT | level step ≥ 3σ×10-min-mean with covariates flat ≥ 5 min | label: step > 3σ at 5 min |
| SENSOR_DRIFT | monotone ramp of 10-min means: |slope| > 3σ/24h sustained ≥ 1 h | label: drift > 3σ of 10-min mean |
| SENSOR_NOISE_SPIKES | std__mean / baseline MAD > 2.5 or spike cadence > 5σ, ≥ 5 min | label: 5 min |
| COMMUNICATION_LOSS | minutes with absent rows ≥ 30 min (gateway) or a single channel `__count` = 0 while channel exists ≥ 30 min + quality bit 1 | gateway ⇒ whole-row absence |

**Masking propagation (the documented test-set trap: drifting suction transmitter hides a clog)**: when
a channel is latched SENSOR-faulted, exclude it from the machine-evidence vector of [3]/[6] and *raise*
the weight of its covariates; if the remaining coherent channels form a machine pattern, alert MACHINE
with a note "sensor X drifted; evidence from Y,Z" — the scorer gives detection credit and the operator
gets the honest story. This is the only architecture that can catch that compound incident.

## 7. Module [6] — Fusion & diagnosis

- Hypothesis set: 8 MACHINE types + 5 SENSOR types + BENIGN (transient veto list) + UNKNOWN.
- Evidence aggregation: `P(h | evidence) ∝ π_h · exp(S_h / T)`, with π_h a *rate prior*
  (machine 0.6 vs sensor 0.4 — measured mix on train+val is 27/13) and T tuned on train.
- Coherence hard gates (measured): MACHINE needs ≥2 coupled channels ≥ 3σ coherently *unless* the fault's
  measured signature is genuinely single-channel-dominant for that asset tier (bearing on T1: accel/crest
  + snapshots — still "2 " because snapshots are an independent measurement stream).
- Sensor latch inhibits the affected channel in machine patterns (§6 masking).
- UNKNOWN emitted when max(S) > alert-threshold but top-2 hypotheses within 0.2 of each other — honest
  ambiguity, scores detection credit, zero false-type cost.
- **Tier capability map**: T0 assets never emit BEARING_WEAR/IMBALANCE/MISALIGNMENT (unmeasurable →
  unobservable labels removed from scoring anyway; emitting them risks false alerts only). T1 emits but
  with latency floor 5 min on vibration channels. T2 full path.

## 8. Module [7] — Confidence calibration

- Per-fault-class isotonic regression fit on TRAIN (pattern score → empirical P(event ∩ type correct)),
  verified on validation (no refit).
- Calibration set built from train regions: score all 1-min windows under the same pipeline (shifted
  causally), match to events within scoring windows, negatives = everything else (incl. benign windows).
- Output `confidence = P(type correct)`; per the scorer this is display-only (burst type credit is
  binary), but it feeds the *decision policy*: alert iff expected utility `P(type)·U_type + P(anyevent)·
  U_detect − P_false·U_false > 0`, with the false-alert cost read from measured precision economics
  (RETROFIT_FEASIBILITY §5: ≈ EUR 43 k/yr per false alert/day → asymmetric: U_false = 3× U_type).

## 9. Module [8] — Alert manager

- 1-min decision steps; burst latch: minimum 6 min between distinct bursts, suppress repeats while
  evidence unchanged; **reminder** at 12 h cadence while event latched open (free per scorer) and only
  then if escalation status changed (severity/lead-time narrative).
- Deadline-awareness: events with measured short deadlines (PUMP-09-DISCHARGE_RESTRICTION had 0.7 h)
  get relaxed persistence on their fast channels (restriction vector: flow−, dis+, temp+ — persistent
  2 of 3 for 5 min ⇒ alert) — cannot wait 15 min.
- Recommended-action table (human-reviewable, no control):
  | Type | Action |
  |---|---|
  | clog | "Inspect/clean suction strainer; check ΔP across strainer" |
  | cavitation | "Check NPSH margin: sea chest level/strainer, reduce speed until σ̂ recovers" |
  | restriction | "Check discharge valve position & heat-exchanger ΔT/ΔP" |
  | bearing | "Vibration route at next opportunity; quantify BPFO envelope; plan bearing change before ISO trip" |
  | imbalance/misalignment | "Inspect coupling & foundation; balance impeller after clog-clean" |
  | drift/stuck/shift/spikes | "Check transmitter X wiring/zero; compare with coupled gauges before any machine work" |
  | COMM_LOSS | "Check fieldbus/gateway segment; note diagnostics blind until fixed" |
- Evidence text: top-3 channels with signed deviation % (the measured matrix), σ̂ if relevant, snapshot
  band results if bearing — built for operator legibility and jury demo.

## 10. Validation plan & expected composite

`python -m retrofit_sim score --predictions ... --split validation`:
- Ablation ladder on validation (allowed for model selection): full → −snapshots → −physics → −coherence;
  each step's ΔF1/Δtype-recall reported (mirrors the deep-dive evidence for each).
- Acceptance: recall ≥ 0.9, F1 ≥ 0.93, type ≥ 0.70, timeliness ≥ 0.93, false+excess ≤ 0.05/day
  ⇒ composite ≈ 88–90; stretch: type 0.78 (all but fused-type events) ⇒ ~91.
- Test predictions produced once, from the frozen pipeline; no test-derived tuning (rules §2).

## 11. Edge/deployment mapping (transfer & retrofit criterion)

- Runs offline on RevPi Connect 4 / IOT2050 class edge (BOM option ≈ EUR 2.1–2.4 k list + install):
  1-min aggregates and rolling stats are O(1) per step; the only FFT work is 1 record / 4 h.
- Memory: per asset ~ (13 channels × 7-day 1-min stats) ≪ 100 MB. Multi-asset trivially.
- MQTT/Sparkplug B read-only output mirroring `retrofit_sim replay` messages; no write path, IEC 62443
  zone/conduit compliant; class-approval path documented in RETROFIT_FEASIBILITY §3.
- Tiers parameterized entirely by `assets.csv` (`channels_available`, `wireless_update_s`,
  BPFO/BPFI orders, curve constants) — no per-asset code. Same package transfers to fans/blowers/
  other rotating machines with a pump-curve family substitution.

## 12. Risks & honest limitations

1. **9 validation events** — differences of a few points are noise (benchmark states this); all tuning
   on train only, validation single-shot per candidate config, test once.
2. **Compound type confusion** (clog→cavitation) is *by design* two events; must emit CLOG early,
   CAVITATION at episode time — never merge (both windows exist; one burst each).
3. Vibration snapshot cadence (4 h) limits bearing-removal latency detection to ~4 h — fine vs
   multi-hour minimum event scales, and the scorer's 6-h window opening forgives it.
4. Physics residual quality degrades outside 0.5≤r≤1.0 / 0.3≤q≤1.3 — model validity window (§12 of
   TECHNICAL_MODEL); the transient veto plus speed-bin conditioning handles this.
   Simulator-specific risk: pattern-matrix weights are fit to this generator; transfer claims must stay
   qualitative until shadow-mode on real assets (pilot path §4 of RETROFIT_FEASIBILITY).
