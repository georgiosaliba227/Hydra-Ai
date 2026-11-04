# Guided starting-goal policy v1

The owner's November 3 request adds birthday/age, height, weight and supplement
questions to goal setup. This authorizes an additive, transparent starting-reference
workflow. It does not validate a personal physiological requirement equation.

## Numerical authority

`adult-beverage-reference-nasem-2005-v1` uses the National Academies' published
approximate beverage portions for generally healthy adults aged **19 or older**:
Men reference group **3000 mL/day**; Women reference group **2200 mL/day**. These
are stable across the adult age bands in the source. The food-inclusive total-
water references, 3700/2700 mL, are explanatory context and never become the
logged-beverage goal. Use the published beverage values directly, not a new 80%
formula. Source: [Water, adult summaries, pp145–150](https://www.nationalacademies.org/read/10925/chapter/6).

This is an approximate population starting reference for ordinary conditions,
not a measured individual requirement, a minimum, or a hydration-status test.
Height, weight and supplement answers are optional local context; they apply
**no numerical coefficient**. In particular there is no creatine addition or
body-weight multiplier. Exercise/heat forecasts remain separately labeled and
do not automatically increase the goal. [NIH supplement evidence](https://ods.od.nih.gov/factsheets/ExerciseAndAthleticPerformance-HealthProfessional/).

Missing age/reference group/eligibility, age under19, pregnancy/breastfeeding,
clinician-directed fluid management, or an uncertain applicability answer produce
an unavailable reference and access to a custom goal. Do not infer a source group.
The source groups are explicit Men/Women choices, with a decline/custom option;
they are not an inferred gender identity. Existing HYDRATION_MODEL exclusions stay.

## Profile and input contract

Manual on-device profile only, no extra HealthKit permission:

- `birthDate: String?` strict Gregorian `YYYY-MM-DD`, or `ageYears: Int?` (one
  method at a time). Birthday derives current age in the user's local timezone;
  the UI shows that age. Future/impossible dates are invalid. Age-only values are
  explicitly self-entered, not automatically aged. Input ages are0...130 for
  either method (an app input bound, not a clinical threshold). Use Gregorian
  year/month/day comparison; a February29 birthday advances on March1 in a
  non-leap year. A future/invalid optional date is not silently discarded.
- `referenceGroup: GoalReferenceGroup?`: `.men`, `.women`, `.preferNotToSay`.
- `eligibility: GoalEligibility?`: `.generalAdult`, `.pregnantOrBreastfeeding`,
  `.clinicianDirectedFluid`, `.unsure`.
- Optional `heightCm` and `weightKg`, finite and strictly positive when present;
  schema maximums300cm/500kg are input bounds, not medical thresholds.
- `supplements: [GoalSupplement]`: `.creatine`, `.electrolytes`, `.other`; empty
  means none supplied. Values are distinct, at most3. No dose or free-text
  clinical inference.

US presentation uses feet/inches and lb; metric uses cm/kg. Saved values are
canonical and untouched values must not drift after display-unit changes. Profile
shape validation is distinct from eligibility for the numerical reference.

## Privacy, persistence and confirmation

Use the existing on-device connection UUID resolver for profile isolation; reuse
`CalibrationConnectionScope.resolve` without changing its registry/credentials.
Store separate protected `HydraAI/goal-profiles-v1/<UUID>.json` envelopes. No profile
save for offline demo or invalid/unconfigured connection; an unsaved form may still
show a local reference. Returning to the exact connection restores its profile.
Files use complete protection, atomic writes, backup exclusion, size/schema checks,
and symlink/corruption rejection; unreadable records are not silently overwritten.

Only an explicitly confirmed integer goal uses existing `PUT /v1/settings`:
`{"daily_beverage_goal_ml": 3000}` (or another user-confirmed value). No birthday,
age, height, weight, supplements, eligibility or reference-group data goes to
the backend, Meta, logs or analytics. Exact existing Wonder consent remains.

The action explains local profile storage and the selected goal's destination.
Save the profile with explicit consent before requesting the backend update.
If the backend reply fails, preserve the profile and current confirmed UI state;
say confirmation failed rather than asserting the server did not change.
Capture connection generation and candidate at the tap, discard stale replies,
and never apply an old connection's result to the new connection.
Serialize goal submissions and protect existing custom-goal get/set paths with
the same connection-generation checks; a late Settings load cannot replace a
newly edited field or another connection's goal. Detect dangling symlinks as well
as existing symbolic links before reading or writing profile files.

Allow explicit local profile export/deletion; deletion-all includes every local
profile. A custom goal remains available, including for unavailable references.
No profile is seeded with simulated data on a real device. Changing profile
answers does not silently change an already confirmed backend goal.

## User experience

Home's goal entry and Settings lead with guided setup; the older custom goal is
available as an explicit alternative. Ask age/birthday, source applicability,
optional body measures and supplements, then show the starting reference, source,
used-versus-context-only inputs and confirmation. Use “Starting beverage reference”
and “Use as my goal,” not “optimal,” “you require,” or clinical deficit language.
The Home research score remains goal alignment/recording support, not physiology.
