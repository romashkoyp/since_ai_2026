Build an operator assistance that
- 12 simulated pumps
- raises early alerts
- says what is wrong and whether it's the machine or the sensor
- show evidence and uncertainty
- recommends something a human approves


**12 pumps are different types.**

| Pumps         | Site                       | Pump type                         |
| ------------- | -------------------------- | --------------------------------- |
| 01, 02, 03    | Vessel A (ferry)           | seawater cooling, freshwater loop |
| 07, 08        | Vessel B (ferry)           | seawater cooling                  |
| 10 (test)     | Vessel C (ferry)           | seawater cooling                  |
| 04, 05, 09    | Plant C (food processing)  | industrial cooling water          |
| 11 (test)     | Plant E (paper converting) | industrial cooling water          |
| 06, 12 (test) | Plant D (chemical process) | process transfer pump             |
A model that memorises the training pumps’ behaviour will fail there. It needs to learn what “normal” looks like for each pump on its own, from its first hours of healthy running (as baseline B1 does), rather than relying on fixed thresholds.


**For Generalizability to other rotating machines:**
- **Unchanged:** learning each machine’s normal behaviour from healthy data, sensor fault checks (stuck, drift, communication loss), bearing defect detection in vibration spectra, the operator dashboard and the human-approval workflow. Any machine with bearings has the same bearing frequencies, and a stuck sensor looks the same on any machine.
- **Swapped per machine:** the physics model. For a pump you compare measured pressure and power with the pump curve; for a fan you’d use the fan curve, for a compressor its pressure-ratio map. The fault list also changes: fans don’t cavitate, but they do get fouled blades and belt wear.

---

**There are 8 machine fault types**
- bearing wear
- strainer clogging
- cavitation
- restriction
- misalignment
- imbalance
- impeller wear
- air entrainment
and 5 sensor fault types
- drift
- stuck
- calibration shift
- noise spikes
- communication loss
Telling “the gauge is lying” apart from “the pump is failing” is explicitly rewarded.

|Fault|What’s happening, in plain words|How it tends to show in the data|
|---|---|---|
|**Bearing wear**|The bearings the shaft spins on are slowly getting damaged, like a bicycle wheel bearing that starts to grind.|High-frequency vibration rises first, days later overall vibration and bearing temperature. A peak appears at the bearing’s defect frequency in the vibration spectrum.|
|**Suction strainer clogging**|The inlet filter fills with debris, mussels or seaweed, so the pump struggles to suck in water, like drinking through a straw that’s getting blocked.|Suction pressure slowly drops, flow falls, and it can eventually turn into cavitation.|
|**Cavitation**|Inlet pressure gets so low that the water briefly “boils” into bubbles, which then collapse violently against the impeller, like tiny explosions eroding the metal.|Noisy, erratic vibration, a drop in discharge pressure and flow, low suction pressure. Often comes in episodes.|
|**Discharge restriction**|Something on the outlet side blocks the flow: a valve left half-closed after maintenance, or a heat exchanger fouled inside. The pump pushes against a partly closed door.|Discharge pressure goes up while flow goes down, and motor power typically drops a bit because less water is moved.|
|**Misalignment**|The motor shaft and pump shaft aren’t perfectly in line, usually after someone worked on the pump, so the coupling between them wobbles.|Vibration at 1× and 2× the running speed, warmer bearings. Often starts right after a maintenance stop.|
|**Imbalance**|Weight on the spinning impeller is uneven, for example from deposits on one side, like a washing machine with all the clothes bunched up.|Vibration at exactly 1× the running speed, growing strongly when the pump speeds up.|
|**Impeller wear**|The impeller blades and the gaps around them wear down over time, so the pump gets weaker and delivers less pressure for the same effort.|A slow decline in pressure at the same speed and flow; the pump falls below its pump curve. Very gradual.|
|**Air entrainment**|Air bubbles get sucked into the pump, for example in heavy weather when the ship rolls and air reaches the seawater inlet, or when a tank runs low.|Pressure drops and fluctuates, vibration becomes erratic. Often linked to sea state or tank level|


---

| Fault                  | What’s happening                                                                                                       | How it tends to show in the data                                                                     |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **Sensor drift**       | A sensor slowly walks away from the true value over hours or days, like a bathroom scale that gradually reads heavier. | One channel trends slowly while physically related channels (current, power, speed) stay consistent. |
| **Sensor stuck**       | The sensor freezes and keeps reporting the same number.                                                                | A perfectly flat line while the pump’s load and speed are clearly changing.                          |
| **Calibration shift**  | The sensor suddenly jumps by a fixed amount and stays there, as if someone re-set it wrongly.                          | A sudden step change in one channel only, with no matching change anywhere else.                     |
| **Noise spikes**       | The sensor signal becomes noisy or jumps around randomly, often from a bad cable or electrical interference.           | Sudden unrealistic spikes and higher variance, with no real physical cause.                          |
| **Communication loss** | Data stops arriving because the network, gateway or wireless sensor drops out.                                         | Missing rows or values; the quality flags in the data mark it.                                       |

Teal boxes are where the water flows; purple boxes are the moving parts. You can click any box to ask which faults happen there.
Mapping the faults onto this picture:
- **Strainer:** strainer clogging, which can lead to cavitation.
- **Suction side and impeller:** cavitation, air entrainment and impeller wear.
- **Shaft, bearings and motor:** bearing wear, misalignment and imbalance.
- **Valve and heat exchanger:** discharge restriction.

**The sensors sit along this path**: suction pressure before the impeller, discharge pressure after it, vibration and bearing temperature on the pump unit, and motor current and power at the motor.
![[cooling_water_pump_overview.png]]

---

**Pumps have three instrumentation levels.** 
- T0 legacy is only motor current, discharge pressure and temperatures.
- T1 adds a cheap wireless vibration sensor reporting every 5 minutes.
- T2 is fully instrumented.
Your model has to degrade gracefully when sensors are missing.

Not every pump has the same sensor

|Level|Sensors|Real-world meaning|
|---|---|---|
|**T0 legacy**|motor current, discharge pressure, fluid and room temperature (plus speed and power if the pump has a speed drive)|an old pump with whatever came with it|
|**T1 retrofit**|T0 + suction pressure + a battery wireless sensor giving vibration and bearing temperature **once every 5 minutes**|a cheap upgrade someone added last year|
|**T2 full**|T1 but vibration every second, plus flow, motor winding temperature and sometimes valve position|a well-equipped modern installation|
Even within a level the sensors vary. Fixed-speed pumps have no speed signal, and only some pumps report valve position.

Our system should degrade gracefully with the current info available:
- **With all sensors:** detect early and name the exact fault (“bearing wear, outer race, 85% confident”).
- **With fewer sensors:** still detect problems, but maybe later and with a broader diagnosis (“mechanical problem, likely bearing or misalignment, 55% confident”), or `UNKNOWN` when it genuinely can’t tell.
- **Never:** crash because a column is missing, invent readings for sensors that don’t exist, or give the same confident answer it would give with full data.

**Why it matters for you**
1. **The test set forces it.** The three test pumps are one of each level: PUMP-10 is T1, PUMP-11 is T0, PUMP-12 is T2. A model built only for fully instrumented pumps scores badly on two test.
2. **There’s an unseen combination.** PUMP-11 is a legacy pump with a speed drive. Both legacy pumps in training are fixed-speed, so your model has never seen a T0 pump whose speed changes. If your code assumes “T0 means constant speed,” it will raise false alarms every time the speed changes.
3. **Some faults are physically invisible on T0.** Bearing wear without a vibration sensor may show up only late, as a bit more motor current or heat, or not at all. The organisers mark such events `observable = False` and don’t score them, so you’re not penalised for missing what can’t be seen. But you should say so in your limitations.
4. **Sensors drop out during operation too.** Communication loss means even a T2 pump can temporarily act like a T1 or T0 pump. The same logic handles that.
5. **It’s part of the judging.** Reliability includes “missing sensors,” and retrofit feasibility is about what you can do with cheap sensors.

**How to build it**
- **Read `channels_available` from `assets.csv` at startup** and only run the checks whose required sensors exist. Don’t assume a column is there.
- **Build modular checks, each declaring what it needs.** For example: “pump curve check needs speed + discharge pressure (+ flow if available)”, “bearing check needs vibration acceleration”, “stuck sensor check works on any channel.” The system activates whatever modules fit the pump.
- **Make confidence depend on evidence.** A diagnosis backed by three independent signals gets high confidence. One backed by a single channel gets lower confidence or `UNKNOWN`. Bearing temperature alone is weak evidence; temperature plus rising acceleration plus a peak at the bearing frequency is strong.
- **Handle the 5-minute wireless data properly.** On T1 pumps vibration arrives only every 300 seconds, so forward-fill it with a “data age” feature rather than treating the gaps as missing or as zero


---
---
---

**How you’re scored**

There are two layers.

**The benchmark (feeds the 25% technical criterion).** You submit a CSV of alerts for the hidden test pumps 10–12, and their scorer computes:

> Composite = 35% event F1 + 20% timeliness + **25% fault-type recall** + 10% machine/sensor class recall + 10% alert burden

| Part                  | Weight | Plain meaning                                                                                                                                                                 |
| --------------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Event F1**          | 35%    | Did you catch the real problems, without raising many false alerts? Combines “how many real problems you found” (recall) and “how many of your alerts were real” (precision). |
| **Timeliness**        | 20%    | Did you catch problems early, before a conventional alarm would have fired? Full credit if early, decreasing credit if late, zero if missed.                                  |
| **Fault-type recall** | 25%    | For each problem you caught, did you name the right cause (e.g. `BEARING_WEAR` and not `MISALIGNMENT`)?                                                                       |
| **Class recall**      | 10%    | Did you at least get machine vs sensor right?                                                                                                                                 |
| **Alert burden**      | 10%    | How much noise do operators get? Every false or repeated alert per pump per day costs points.                                                                                 |

An example. A pump has a clogging strainer from Tuesday to Thursday:

- You raise one alert Tuesday afternoon saying `MACHINE / SUCTION_STRAINER_CLOGGING`: a detection, early, correct cause, correct class. Full marks for that event.
- You raise the alert Thursday saying `MACHINE / CAVITATION`: still a detection, but late (less timeliness) and the wrong cause (no fault-type credit), though the class is right.
- You alert every 10 minutes all week: after the first alert and one free reminder per 12 hours, every extra alert counts as noise and hurts your burden and precision.

The baselines on validation:

| Baseline                  | Composite | Fault-type recall |
| ------------------------- | --------- | ----------------- |
| B0 plant alarms           | 23.1      | 0.11              |
| **B1 mode-aware z-score** | **78.0**  | 0.44              |
| B3 Isolation Forest       | 69.2      | 0.44              |

B1 already detects well (F1 0.89). Its weakness is diagnosis: it names the right fault type less than half the time. That 25% weight is your biggest opportunity. Build a better diagnostician on top of a good detector.

The organisers built simple reference methods so you know what “good” looks like:

- **B0, plant alarms (23.1):** what the plant already has, fixed limits like “alarm if pressure < X.” It catches only 11% of problems, and only when it’s already late.
- **B1, mode-aware z-score (78.0):** learns each pump’s normal values from its first healthy day, separately for each speed range, and alerts when readings drift too far from normal. Simple, but very effective.
- **B3, Isolation Forest (69.2):** a standard machine learning anomaly detector. Worse than B1, even though it sounds fancier.

Here are B1’s validation numbers and how much each part could still add to the score:

| Part                  | B1 now   | If perfect | Max extra points |
| --------------------- | -------- | ---------- | ---------------- |
| Event F1              | 0.89     | 1.00       | +3.9             |
| Timeliness            | 0.86     | 1.00       | +2.8             |
| **Fault-type recall** | **0.44** | 1.00       | **+14.0**        |
| Class recall          | 0.89     | 1.00       | +1.1             |
| Alert burden          | 0.97     | 1.00       | +0.4             |

The cause: B1 diagnoses with hand-written rules like “if suction pressure dropped, say clogging.” Many faults look similar on one sensor, so the rules guess wrong more than half the time.

So split the system into 2:
1. **Detector (triage nurse):** “Is something wrong with this pump right now?” B1’s approach already does this well. Copy it, check that you reproduce its score, and move on.
2. **Diagnostician (specialist):** only after the detector fires, it looks at which signals changed, how, and together with what, then names the cause.

The diagnostician is where your weekend should go. It looks at the “signature” of the problem:

- **Which channels moved:** suction pressure, discharge pressure, power, vibration, temperature.
- **In which direction:** pressure up with flow down suggests a restriction; suction pressure down suggests clogging.
- **How fast:** a sudden step suggests a calibration shift; slow growth over days suggests wear.
- **Whether the channels agree physically:** if only one sensor moved and nothing else did, it’s probably a sensor fault.
- **Vibration spectra:** a peak at the bearing frequency means bearing wear; energy at 1× and 2× running speed means imbalance or misalignment.

You turn these signatures into features and train a classifier (LightGBM, for example) on the labelled training events.

**Two cautions**
1. **Validation has only 9 events,** so one event equals about 11% of fault-type recall. Don’t trust small differences. Score on training and validation pumps together (B1 scores lower on train, 58.2 with fault-type recall 0.27) to get a more honest picture. (check caution no 1 tab).
2. **A wrong guess and `UNKNOWN` score the same.** Neither earns fault-type credit. So in the CSV, a reasonable best guess is free on the benchmark. But in the operator interface, show the confidence honestly and flag low-confidence cases for human review, because the judges score reliability separately. A good design: always output your best guess plus a calibrated confidence, and let the dashboard show uncertain ones as “possible X, check Y to confirm.”

**The jury criteria:**
- operational usefulness: 25%
- technical validity (the benchmark): 25%
- reliability and safety (false alarms, missing sensors, uncertainty, human review): 20%
- retrofit feasibility and transfer (sensor costs, edge deployment, another machine class): 20%
- working demo and clarity: 10%

So 75% is judged on things other than raw model performance. The demo, the cost story and honest uncertainty matter as much as the model. They watch your demo and read your materials, scoring usefulness, safety, retrofit cost and presentation.