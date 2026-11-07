# SENTRY — implementation summary & results

Physics-grounded operator-assist detector for the RETROFIT AI 2026 benchmark.
Design: `analysis/DETECTOR_DESIGN.md` · Evidence behind every rule: `analysis/DEEP_DIVE_REPORT.md`
+ per-event calibration dumps `analysis/08_out*.txt`.

## Run

```bash
python -X utf8 -m sentry.run --data data\full --split train       --out build\predictions_sentry_train.csv
python -X utf8 -m sentry.run --data data\full --split validation  --out build\predictions_sentry_validation.csv
python -X utf8 -m sentry.run --data data\full --split test        --out build\predictions_sentry_test.csv

python -m retrofit_sim score --predictions build\predictions_sentry_train.csv \
    --events data\full\events_train.csv --assets data\full\assets.csv \
    --benign data\full\benign_windows_train_validation.csv --split train
python -m retrofit_sim score --predictions build\predictions_sentry_validation.csv \
    --events data\full\events_validation.csv --assets data\full\assets.csv \
    --benign data\full\benign_windows_train_validation.csv --split validation
```

Causality: the engine is a streaming state machine over the 1-min grid; baselines are causal
(expanding/rolling trailing windows), snapshots consumed in arrival order. Alerts carry their
timestamp only with data ≤ t. No test-derived tuning was performed; thresholds were set from
train-split traces + validation diagnosis only.

## Measured results

| Split | Baseline B1 (mode-aware z) | SENTRY v8 | Δ |
|---|---|---|---|
| validation (2 pumps, 9 events) | 78.0 | **87.7** | **+9.7** |
| train (7 pumps, 26 scored events) | 58.2 | **66.5** | **+8.3** |

Validation detail: recall 0.889 (8/9), precision 1.000 (0 false-alert episodes, 0 excess repeats),
timeliness 0.819, fault-type recall 0.778 (B1: 0.444), class recall 0.889, median lead 13.3 h.
Train detail: recall 0.731, precision 0.792, fault-type recall 0.423 (B1: 0.27), median lead 14.3 h.

## Architecture (sentry/)

| Module | Role |
|---|---|
| `regime.py` | Causal regime-conditioned robust baselines (12 h rolling median/MAD per speed-bin, 3-min buckets), per-channel absolute noise floors (documented instrument noise), z-residuals; frozen-range and noise-ratio helpers |
| `physics.py` | Vectorized pump-curve wrapper reusing the simulator's own physics (`solve_operating_point` family); NPSH margin estimator σ̂ = NPSHa/NPSH3 from gauges + Antoine vapor pressure + velocity-head correction |
| `snapshots.py` | 10.24 kHz snapshot analyzer: Hann PSD, defect lines (1×/2×/3×, BPFO, BPFI, vane-pass) with median-reference SNR, auto-learned 2–3.5 kHz housing resonance band, Hilbert envelope demodulation |
| `detect.py` | The rule cascade + alert manager (bursts, 12-h reminders, per-minute priority, storm/voltage-sag vetoes, tier capability map) |
| `run.py` | Split runner; writes submission-format CSV |

### Rule set (all thresholds traceable to measured signatures)

- **Cavitation**: σ̂ < 1.15 sustained 5 min (the label's own definition); re-arms when σ̂ > 1.16 for 6 min;
  10-min-robust suction filter during heavy weather. Emits per episode.
- **Strainer clog**: fixed-speed: z(suction) < −4 sustained 30 min; VFD: counterfactual-free
  suction-loss trend (dev < −2.2 kPa vs expanding 48 h regime median, 2 h sustained) with flow-coupling
  guard (Q-deviation < −3 % → restriction instead) and VFD-min-speed handling (PUMP-08: drive pinned →
  no speed/power response expected). Suppressed while vibration-domain machine latches are open.
- **Discharge restriction**: VFD: flow ↓ + discharge ↑ or speed sag sustained 5 min (the off-BEP-only
  alternative was removed after it mis-typed imbalance ramps); T0: discharge ↑ + current ↓.
- **Air entrainment**: flow/discharge/power triple-collapse sustained 15 min with NPSH margin healthy, or
  the **f̂H residual rule** (T2-flow assets): f̂H = H_meas/H_curve(Q,r) < 0.94 sustained → typed AIR when the
  drop is fast (> 3 %/8 h), MACHINE UNKNOWN otherwise (slow head-factor loss ≈ impeller wear).
- **Bearing wear**: (a) snapshot BPFO envelope SNR ≥ 15 dB on two consecutive 4-h snapshots (usually ~4 h
  to detect, BPFO-specific so it types the fault); (b) crest-factor trend > 2.3 MAD sustained with
  hydraulics flat (catches crest-only T1 cases).
- **Imbalance / misalignment**: velocity umbrella: z(vel) > 3.5 sustained 45 min with hydraulics flat →
  hold ≤ 48 h for the next snapshot; 1×/2× line steps vs the asset's first-6-snapshot baseline type it
  (misalignment needs 2× ≥ +7 dB, imbalance 1× ≥ +6 dB with BPFO quiet). No snapshot confirmation →
  MACHINE UNKNOWN (honest, scores detection + class credit).
- **Sensor faults** (vibration-family and control-pinned channels excluded from sensor rules):
  stuck = 60-min range < 5 % of noise sustained 30 min (exact-freeze only, avoids
  wireless-resolution plateaus); calibration shift = |z| > 3.5 sustained 45 min with coupled channels
  flat, warmup-stability gate, clog-trend guard on suction; drift = dev ≥ 1 MAD sustained 60 min
  with monotone fraction ≥ 0.62 (candidates restricted to suction/current/bearing-temp); noise spikes =
  per-minute std > 3× noise + > 6σ spikes sustained 15 min (wired channels only); gateway loss =
  ≥ 30 min of absent telemetry rows.
- **Machine-hydraulic UNKNOWN fallback** when discharge/power both deviate but no specific pattern holds.

## Known limitations (honest)

1. Missed validation event: PUMP-09-E04 sensor drift on motor current — detected 14 min after the scoring
   window closed via the load-coupling residual (trailing-couple absorbs slow drift; the I(P)-regression
   variant false-fired and was disabled). All other 8/9 detected & typed correctly.
2. Missed train events: 4 PUMP-06 cavitation episodes (episode re-arm now works on validation-style
   margin excursions but the PUMP-06 train cascade sits just above 1.15 with heavily clogged strainer);
   PUMP-07 air entrainment with flow-channel corrupted by a live calibration shift (the f̂H rule targets
   this class of masked cases but did not trigger there); PUMP-05 impeller wear is physically near-
   unobservable on T0 (headresco residual too small vs the 4 kPa pressure floor).
3. The rule set was calibrated on this synthetic builder; transfer hypotheses (BPFO envelope analysis,
   suction-dev clog detection, I(P) coupling, day-over-day drift) are physically motivated and
   documented, but field shadow-mode validation per `RETROFIT_FEASIBILITY.md` §4 is required before any
   operational claim.
4. Burst discipline caps repeats at one initial + one 12-h reminder per fault type; the scorer's repeat
   credit across co-occurring events is not explicitly modeled ( contributed 3 excess-repeat episodes on
   train; 0 on validation).

## Files

- `build/predictions_sentry_v8_validation.csv` (scored = 87.7)
- `build/predictions_sentry_v8_train.csv` (scored = 66.5)
- `build/predictions_sentry_v8_test.csv` — submission for the organizers' scorer
