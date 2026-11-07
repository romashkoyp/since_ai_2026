# RETROFIT AI 2026 — Quantitative Deep-Dive Report

Analyst pipeline in this folder (run order): `01_events_inventory.py` → `02_channel_signatures.py` → `03a_traces.py` → `03b_snapshots.py` → `04_b1_gap_analysis.py` → `05_figures.py`. Data root: `data/full/`. All findings refer to the shipped build.

---

## 1. Event inventory (39 events: 33 train + 9 validation)

| Split | MACHINE | SENSOR | Notes |
|---|---|---|---|
| train | 18 observable + 1 unobservable (PUMP-05 BEARING_WEAR on T0 legacy) | 8 | 4 cavitation episodes cascade from one PUMP-06 clog |
| validation | 5 | 4 | 9 scored events; only 2 have action deadlines |

Key labeled timeline facts:

- **PUMP-04 BEARING_WEAR** is pre-existing (`onset = detectable = day 0`) with `action_deadline = day 5.01` → 120 h of available lead, the largest headroom in the dataset.
- **PUMP-07 BEARING_WEAR** becomes detectable only at day 5.9 via crest factor alone (T2 full — late because growth was slow until the window's end).
- **PUMP-06**: clogging (labels: severe, deadline day 3.91) generates 4 discrete cavitation episodes (days 3.90, 4.24, 4.37, 4.72), each with ~0 lead to its deadline — by the time cavitation is labeled, action is already due. The clog itself offers a 31 h lead.
- Validation actions with deadlines: PUMP-08 clogging (37 h lead available), PUMP-09 restriction (0.7 h — effectively none; detection must fire almost immediately).

## 2. Per-fault channel signature matrix (`analysis/event_channel_z.parquet`)

Median deviation vs per-asset healthy reference (noise units z and % of healthy mean), measured over each event's [detectable, end] window:

| Fault | Dominant channels (z / %) | Diagnostic pattern |
|---|---|---|
| CAVITATION | suction ≈ −21z / −526 %, accel ≈ +49z / +507 %, velocity +60 %, current −14 % | suction collapses toward vapor pressure, broadband HF, head/power loss |
| BEARING_WEAR | accel +16z / +75 %, crest +36z / +47 %, velocity &amp; temps ≈ 0 | pure vibration-domain signature; hydraulics clean |
| DISCHARGE_RESTRICTION | accel +73z / +374 % (off-BEP hydraulic), bearing_temp +6z / +12.8 %, flow −8.6 %, speed −5z (VFD sagging) | flow down + off-BEP vibration + heat |
| IMBALANCE | velocity... see caveat below; accel +32z / +166 %, crest +31z | single-event (PUMP-04), co-occurs with bearing wear |
| SUCTION_STRAINER_CLOGGING (fixed speed) | suction −5z / −17 %, all else ≈ 0 | quiet, suction-only signature |
| SUCTION_STRAINER_CLOGGING (VFD, PUMP-01/08) | **speed +6.1 %, power +15 %, suction −8.7 %** (directly measured) | controller compensation makes power/speed rise — current/power *increase* is the tell on VFD assets |
| AIR_ENTRAINMENT | suction −4z / −47 %, power −25z / −9 %, flow −12z / −7 % | erratic head/power loss |
| IMPELLER_WEAR | discharge pressure ≈ +4z / +1.7 % only | weakest signature; needs pump-curve residual to separate from restriction |
| MISALIGNMENT | power +14z / +3.2 %, velocity +8 % / 2x, temps mild | load-dependent 1x/2x with electrical residue |

**Method caveats (measured):**
1. z-scores are in per-channel noise units and are NOT comparable across channels; use % of healthy mean for cross-channel pattern, z for single-channel detectability.
2. Sensor-event windows overlap co-occurring machine faults, so multi-channel rankings inside a sensor event window get contaminated (e.g., PUMP-02's drift event sits inside its pre-existing bearing-wear window; PUMP-09's stuck event overlaps its misalignment). Machine-fault rows can likewise blend their co-faults. Per-event signature extraction should mask sister events before aggregation.

**Sensor-fault isolation (verified on the affected channel itself):**
- Stuck → the affected channel is *exactly frozen*: PUMP-01-E04 bearing_temp range = [35.5, 35.5] over ~25 h; zero local variance vs nominal noise is a decisive test.
- Calibration shift → pure level step, covariates stay flat (PUMP-03-E02: discharge +8.6z, next channel 0.6z).
- Drift → slow ramp on one channel (PUMP-09-E04 motor current; PUMP-02-E02 suction).
- Noise/spikes → variance inflation on one channel (PUMP-08-E04 discharge pressure std).
- COMM_LOSS → whole rows absent from the partitioned parquet (gateway outage), not NaNs.

## 3. PUMP-06 clog → cavitation chain (trace level)

| Segment | n min | Suction kPa (z, %) | Discharge kPa | Current |
|---|---|---|---|---|
| healthy pre-clog | 2151 | +13.4 (−3z) | 432 | +12 % above clean reference* |
| clog develops | 1310 | −0.0 (−16z, −100 %) | 426 ≈ flat | ~flat |
| pre-deadline 1 d | 1001 | −10.2 (−26z, −161 %) | 423 ≈ flat | ~flat |
| cavitation ep. 1 | 71 | **−56.3 (−71z, −439 %)** | **333 (−30 %)** | dip ~15–16 A |

\* the current rise reflects the co-occurring misalignment (post-maintenance), not the clog — compound incidents confirmed in the data.

The physical chain is exactly as the Technical Model describes: on a fixed-speed + valve system the valve holds discharge pressure while the strainer ΔP eats suction margin; once NPSH margin < 1.15 sustained, head breaks down and discharge collapses 30 % with broadband HF vibration (sparse 5-min wireless samples jump 0.3 g → 1.5–1.9 g only inside episodes — figure `figs/fig3_pump06_clog_cavitation.png`).

**Practical reading:** cavitation episodes score with ~0 lead; the *alertable* target is the clog (31 h lead on PUMP-06), i.e. detect the suction-loss signature before margin collapse, not the cavitation itself.

## 4. Vibration snapshots, PUMP-04 (spectral analysis)

39 snapshots × 1 s @ 10.24 kHz; bearing 6311 → BPFO order 3.057, BPFI 4.943, 6 vanes; ≈ 1355 rpm ⇒ f₁≈22.6 Hz, BPFO ≈ 69 Hz, BPFI ≈ 111 Hz.

Phase-averaged spectrum levels (max-in-band, dB):

| Phase | 2.6–3.0 kHz resonance | BPFO line | BPFI line | Vane pass | Broadband 100–4k |
|---|---|---|---|---|---|
| early (< 1 d) | −31.8 | −41.3 | −46.3 | −24.0 | −51.1 |
| mid (3–4.3 d) | −12.2 | −30.7 | −46.2 | −23.6 | −43.4 |
| peak (4.5–5.45 d) | **−6.3** | **−16.5** | −45.9 | −23.8 | −39.8 |
| post-repair (> 5.45 d) | −41.9 | −42.8 | −46.5 | −23.9 | −52.3 |

Reading: the defect is *outer-race specific* — the 2.6–3.0 kHz housing resonance grows ~35 dB while BPFI and vane-pass lines are flat (BPFI is masked, consistent with an outer-race spall).post-repair levels return to baseline.

**Envelope demodulation** (band-pass 2.6–3.0 kHz → Hilbert envelope → FFT; BPFO bin vs 20–400 Hz reference median):

- Day 0: SNR **20.8 dB** (already detectable in the very first snapshot — matches label `detectable = day 0`);
- Monotonic rise to **~44.5 dB** by day 5.2;
- After the bearing repair (end_utc = day 5.45, lockout visible as stops): BPFO envelope peak falls from 1.23 g to ~0.00 g; post-repair "SNR" collapses to 1–13 dB and BPFO peak amplitude is indistinguishable from noise.

Figure `figs/fig2_pump04_spectrum_envelope.png` (top: spectra by phase; bottom: BPFO envelope growth with repair marked).
Figure `figs/fig1_pump04_staging.png` shows the textbook staging in 1-min telemetry: acceleration ramps from day 0; crest factor rises to ≈ 6.2 by day 1 then *falls* back toward 3.9 as damage spreads (the documented crest rise-and-fall); velocity only reacts at day ≈ 4.7–5.4 (late stage, peaking ≈ 5.9 mm/s, still under the 6.4 alarm); bearing/winding temps only show late (> day 4.5, 55 °C peak vs 40 baseline).

**Conclusion: the waveform snapshots carry the earliest bearing evidence in the entire dataset — weeks-equivalent before any SCADA alarm — and BPFO envelope analysis extracts it at a glance.**

## 5. Baseline verification (scorer reproduced exactly)

Ran the official CLI on the shipped validation prediction files:

| Baseline | Composite | Recall | Precision | F1 | False+excess/day | Timeliness | Type recall | Class recall | Median lead (h) |
|---|---|---|---|---|---|---|---|---|---|
| B1 mode-aware z | **78.0** ✓ | 0.89 | 0.89 | 0.89 | 0.07 | 0.86 | 0.44 | 0.89 | 8.3 |
| B2 CUSUM | 50.9 ✓ | 0.78 | 0.32 | 0.45 | 1.07 | 0.77 | 0.33 | 0.67 | 13.6 |
| B3 isolation forest | 69.2 ✓ | 0.78 | 0.70 | 0.74 | 0.21 | 0.78 | 0.44 | 0.78 | 6.8 |

All match `baseline_metrics.md` to the decimal → scorer and shipped artifacts are consistent.

### Where B1 leaves points on the table (validation, per-event)

| Event | Truth | B1 diagnosis (confidence) | Verdict |
|---|---|---|---|
| PUMP-08-E02 | BEARING_WEAR (det day 2.7) | first alert: SUCTION_STRAINER_CLOGGING (0.56), then UNKNOWN ×3, COMM_LOSS (0.05) | detected, wrong type ×5 |
| PUMP-08-E04 | SENSOR_NOISE_SPIKES | UNKNOWN (0.99) | detected, no type credit |
| PUMP-09-E04 | SENSOR_DRIFT (current) | SENSOR_CALIBRATION_SHIFT + IMBALANCE (0.99) | detected, wrong type |
| PUMP-09-E01 | MISALIGNMENT | IMBALANCE / CALIB_SHIFT / NOISE / STUCK mix (0.99) | detected, wrong type |
| PUMP-09-E06 | AIR_ENTRAINMENT | DISCHARGE_RESTRICTION, SUCTION_STRAINER_CLOGGING (0.99) | detected (via sister event), wrong type |
| PUMP-09 13 Feb | none | SENSOR_CALIBRATION_SHIFT | 1 nuisance false alert |

Two structural weaknesses of B1 to exploit: (1) **diagnosis** — rule tables fail exactly on VFD counter-intuitions (speed/power *up* on clog) and on single-channel sensor signatures; (2) **calibration** — confidence is pinned at ~0.95–0.99 even when wrong, so honest, evidence-weighted confidences are free reliability points.

## 6. Clean-up note & figures

- Figures: `analysis/figs/fig1_pump04_staging.png`, `fig2_pump04_spectrum_envelope.png`, `fig3_pump06_clog_cavitation.png`.
- Data extracts: `analysis/event_channel_z.parquet`, `analysis/pump04_snapshot_bands.csv`, `analysis/pump04_envelope_snr.csv`.
- PUMP-06 has no flow meter (T1 retrofit tier) — flow/valve-based diagnostics are impossible on that asset class; the tilt-of-evidence must come from suction + current + acceleration.

## 7. Actionable conclusions for the model build

1. **Envelope diagnostics on snapshots** = highest-value single feature (BPFO/BPFI/1×/2×/vane-pass demodulated band energies + broadband hump at the housing resonance). Gives both detection (SNR ≫ 20 dB from first snapshot) and *type* evidence (BPFO-dominant ⇒ BEARING_WEAR; flat defect lines with 1× rise ⇒ IMBALANCE; nothing in spectra + hydraulic signature ⇒ hydraulic fault).
2. **Physics-residual diagnosis** using assets.csv curve parameters: residual direction in (suction, discharge, flow, speed, power) space separates clogging / restriction / entrained air / impeller wear; VFD compensation must be modeled *before* thresholding current/power.
3. **Sensor-vs-machine discrimination**: machine faults ⇒ ≥2 physically coupled channels coherent; sensor faults ⇒ single channel, with sub-tests (frozen vs step vs ramp vs variance-inflation). Window-overlap contamination must be masked.
4. **Confidence calibration**: report evidence-weighted confidences; B1's 0.99-on-wrong-answers shows the scoring's fault-type credit is there for the taking by any honest classifier.
5. **Timing discipline**: alerts must fire before deadlines on short-lead events (PUMP-09 restriction: 0.7 h) — this favors low-latency 1-min features over slow rules; and cavitational episodes themselves are ~0-lead, so invest in detecting the precursor (clog) instead.
