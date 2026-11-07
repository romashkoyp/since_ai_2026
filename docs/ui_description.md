# RETROFIT AI — Operator UI Architecture Description

This document provides a concise, abstract functional description of each dashboard screen, detailing the underlying data lineage and operational necessity.

---

## Screen 1: Fleet Triage Matrix

* **Visual File:** [`images/screen1_fleet_triage.jpg`](images/screen1_fleet_triage.jpg)

### What it shows

* **High-Level System State:** Overall operational availability, active mechanical alerts, and the proportion of raw SCADA nuisance alarms suppressed by context awareness.
* **Multi-Asset Status Grid:** A unified matrix of all monitored pumps displaying operational modes (Running, Standby, Stopped), mechanical degradation severity, and distinct tags for instrument/sensor malfunctions.

### From where data comes

* **Equipment Metadata:** Equipment ratings, motor speeds, and service profiles from asset registry tables (`assets.csv`).
* **Operational Telemetry:** Aggregated 1-minute statistics capturing running state and speed regimes (`features_1min.parquet`).
* **Environmental & Transient Context:** Sea-state, vessel roll, and startup transition tables used by the anomaly detector to filter false alarms (`benign_windows_train_validation.csv`).
* **Alarm Benchmarks:** Raw fixed-threshold SCADA alarm logs (`alarms.csv`).

### Why it is necessary for operator

* **Mitigates Alarm Fatigue:** Filters out transient, non-fault operational spikes (e.g. vessel roll or load ramps), ensuring only genuine mechanical degradation prompts human attention.
* **Rapid Macro Triage:** Enables the operator to evaluate the health of the entire machinery room in seconds, identify degraded assets, verify ready standby units, and separate instrument faults from real mechanical failures.

---

## Screen 2: Unified Asset Diagnostic & Mitigation Cockpit

* **Visual File:** [`images/screen2_unified_asset_cockpit.jpg`](images/screen2_unified_asset_cockpit.jpg)

### What it shows

* **Diagnostic & Actionable Advisory Panel:** Primary failure classification, calibrated physical certainty, remaining safe operational window (RUL), step-by-step Standard Operating Procedures (SOP), and a human-in-the-loop sign-off log.
* **Synchronized Multi-Domain Sensor Trends:** Continuous multi-day time-series of physical process variables alongside demodulated high-frequency vibration spectra isolating rotational harmonics and structural resonance bands.
* **What-If Digital Twin Sandbox:** Interactive parameter adjustment (speed setpoint, valve position) linked to a live pump characteristic curve ($H$-$Q$), a thermal process safety limit bar, and projected risk and energy recovery metrics.

### From where data comes

* **Continuous Process Variables:** 1-minute mean and variance statistics for pressures, temperatures, electrical current, and power (`features_1min.parquet`).
* **High-Frequency Vibration Waveforms:** 10.24 kHz raw accelerometer snapshots demodulated into envelope spectrums (`vibration_snapshots.parquet`).
* **Physical Reference Curves:** Manufacturer head-flow characteristics, Best Efficiency Point (BEP) coordinates, and affinity law models (`assets.csv`).
* **Digital Twin Simulator:** Reduced-order physical simulation engine computing operating points, NPSH cavitation margins, and thermal duties (`retrofit_sim.sandbox`).

### Why it is necessary for operator

* **Eliminates Ambiguity:** Cross-correlates hydraulic, electrical, and spectral evidence to prove whether a fault is genuine mechanical degradation or a drifting transducer.
* **Closes the Loop from Alert to Action:** Answers what operational adjustments can stabilize the machine before maintenance can occur.
* **Guarantees Process Safety:** The thermal duty interlock prevents the operator from derating the pump below the minimum cooling required by the protected system.
* **Safe Human Governance:** Allows testing counterfactual operational changes in a sandbox environment without live PLC writes.

---

## Screen 3: Retrofit Feasibility & Engineering Scorecard

* **Visual File:** [`images/screen3_retrofit_roi_benchmark.jpg`](images/screen3_retrofit_roi_benchmark.jpg)

### What it shows

* **Instrumentation Tier Capability Comparison:** Functional matrix contrasting detection capabilities across legacy setups ($T0$) versus non-invasive retrofit packages ($T1$).
* **Edge Hardware Integration Architecture:** Orthogonal schematic of non-invasive sensing (clamp-on current, magnetic vibration) interfaced with edge processing and galvanically isolated plant automation.
* **Empirical Benchmark & Reliability Scorecard:** Validated performance metrics (detection quality, precision, lead time) measured against standardized benchmark events.
* **Fleet Deployment Economics:** Tabular summary of fleet-wide hardware costs, crew installation requirements, and payback metrics against avoided catastrophic downtime.

### From where data comes

* **Instrumentation Specifications:** Retrofit feasibility guide and asset sensor inventories (`RETROFIT_FEASIBILITY.md`, `assets.csv`).
* **Validation Performance:** Objective scoring results computed by the event-based evaluation benchmark (`scoring.py`, `events_validation.csv`).
* **Economic Assumptions:** Industrial downtime cost models and standardized marine component pricing (`examples/business_case.py`).

### Why it is necessary for operator

* **Investment Justification:** Provides chief engineers and fleet managers with transparent technical and economic justification for retrofitting older equipment.
* **Guarantees Edge Feasibility:** Proves that complex diagnostics run locally on lightweight edge hardware without requiring complete SCADA or PLC replacement.
* **Establishes Operational Trust:** Proves high precision and zero false-alarm rates through empirical benchmark data before deployment in safety-critical environments.
