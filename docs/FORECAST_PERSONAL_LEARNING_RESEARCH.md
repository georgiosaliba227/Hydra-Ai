# Regularized personal-learning candidate

November 2, 2026. Implemented and evaluated as an **offline research candidate**;
it is not enabled by the app, analysis API or Muse Wonder. The application retains
the existing personal median and conservative measurement envelope. Neither
synthetic success nor a within-person fit establishes physiological accuracy.

`ai.forecasting.personal_learning.predict_personal_research` consumes the existing
validated exercise and earlier manual calibration history. It requires at least
six comparable, protocol-confirmed measurements with independently supplied error
bounds. No population prior is transferred from incompatible study targets.
The backend does not persist any fitted personal model or acquire user records.

The candidate fits rate in mL/hour to standardized elapsed days with an unpenalized
intercept and a ridge-penalized time slope. It learns both coefficients from the
person's measurements. Alpha is selected from the fixed set 0.1, 1 and 10 using
rolling earlier-only prediction errors. Overlapping or current measurements are
withheld from each fold; duplicate completion instants are rejected. At least three
validation outcomes are required. A candidate replaces the baseline **inside the
research comparison only** when its paired gain exceeds one empirical standard
error (and numerical tolerance); this is an engineering heuristic, not a test of
statistical significance. Stronger shrinkage wins exact ties.

A planned completion beyond the largest observed interval between comparable
sessions abstains from the learned trend. Missing or shifted conditions, a cold
start or completed actual measurement also retains the existing method. No
temperature, humidity, heart-rate, supplement or drinking-need effect is fitted.
When selected, the research envelope is the union of the existing full measurement
envelope and duration-scaled historical one-step errors. It cannot narrow the
existing range; it has **no nominal coverage guarantee**.

## Fixed synthetic prospective comparison

Ten invented participants each have twelve 60-minute sessions every three days.
Base rate is 300 + 20 × participant mL/hour; scenarios add a 30 mL/hour trend or a
200 mL/hour step after six sessions. Uniform ±10 mL noise and ±10 g per weighing
are simulation assumptions. The environment-shift label does not attribute a
temperature effect. Each forecast fits/selects using only earlier observations;
the next outcome is scored afterward. Results are in
`ai/forecasting/artifacts/personal-learning-research.json`.

| Scenario | Scored / attempted | Baseline MAE, mL | Research selected MAE, mL | Selected-range inclusion |
| --- | ---: | ---: | ---: | ---: |
| Stable | 110 / 120 | 5.85 | 5.85 | 100% |
| Gradual change | 110 / 120 | 75.65 | 29.75 | 59.09% |
| Abrupt change | 110 / 120 | **58.95** | 61.13 | 90.91% |
| Condition shift | 100 / 120 | 6.23 | 6.23 | 100% |

Cold starts and the first changed-condition session are unavailable and are
excluded from conditional error/inclusion metrics, rather than counted as correct
zero predictions. The chronological model adapts to the trajectory it was designed
to explore but worsens MAE under an abrupt change, and its interval inclusion under
gradual drift is poor. **These counterexamples block promotion.** More history and
regularization do not make its uncertainty calibrated. No parameters or thresholds
were changed after seeing these scenario results.

The real studies do not supply verified dated repeat-workout histories: QDE's
cumulative intervals are one session, and SpectroPhon's apparent repeated identity
groups lack a validated chronology/protocol sequence. Real held-out-person,
time-ordered testing and a defensible prior remain missing. Persistent iPhone
manual records make later consented evaluation possible; they are not silently
sent for model training.

## Reproduce

The learner uses only the standard library and the existing calculation engine.

```sh
python -m pytest tests/forecasting/test_personal_learning.py -q
python -m ai.forecasting.personal_learning --output /tmp/hydra-personal-learning.json
```

Tests cover cold starts, actual-outcome authority, learning/selection from earlier
data, stable-baseline retention, shifted conditions, bounded extrapolation,
duplicate/future measurements, withheld outcomes, envelope preservation and exact
benchmark reproduction. They validate software behavior; no real longitudinal
accuracy or clinical validation is claimed.
