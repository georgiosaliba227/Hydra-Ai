# Isolated hydration calculation engine

Owned by `georgiosaliba227` under [issue #3](https://github.com/georgiosaliba227/Hydra-Ai/issues/3).
The user approved the proposal and subsequently reported Amine's confirmation in
chat. No GitHub approval comment was present at the implementation inspection;
this records the source of authorization without attributing a GitHub review to him.

Implemented: confirmed beverage accounting, sourced composition conversion,
local-day aggregation, measured workout loss and comparable-workout projections,
and a contract-shaped insufficient-data forecast. Not implemented: personalized
daily requirements, HTTP endpoints, persistence, authentication, provider inference,
or spending-controller enforcement. No new dependencies; Python standard library only.

## Boundary for Amine's backend

Import `ai.hydration` from the repository root. The existing starter has a separate
`ai` package; run its tests separately from `Hydra-Ai-Starter/`. No parent package,
backend, database, integration, shared contract, or starter files are changed.

- Construct frozen `BeverageLog` instances only after authentication and confirmation.
  Supply UUID IDs, positive integer revisions, finite nonnegative consumed mL,
  aware datetimes, IANA timezone names, source (`manual` or `confirmed_recognition`),
  and nonempty provenance tuples. The engine does not authenticate ownership.
- `Composition` describes source-backed values per positive `basis_ml`. Optional
  fields are `water_ml`, `sodium_mg`, `potassium_mg`, and `carbohydrate_g`. Missing
  nutrients stay `None`; zero is a known value. Evidence retrieval/verification
  belongs to the caller: an identifier's presence does not verify its source.
- `calculate_contribution(log)` converts known composition using consumed/basis
  volume. Every category counts toward beverage volume. Water content is distinct
  from retention, hydration state, and total dietary water. Unknown composition
  stays unknown even for categories named water or coffee.
- `summarize_day(logs, local_date, timezone)` requires one current revision per ID
  in an already-owned snapshot. Duplicate IDs anywhere in the snapshot are errors,
  including identical requests or conflicting revisions. Backend owns request
  idempotency, revision selection, pagination completeness, and invalidation.
  Selection uses each instant's date in the requested timezone, including 23/25-hour
  days. An empty snapshot means zero *logged* intake, not measured zero intake.
  If any selected composition lacks water, the complete water total is `None`.
- `estimate_workout_loss(measurement)` accepts positive masses in kg and duration
  in minutes, nonnegative consumed/urine mL, protocol confirmation, and provenance.
  Missing measurements, unconfirmed protocol, inconsistent negative balance, or
  unrepresentable arithmetic yield `insufficient_data`. Invalid numeric types or
  negative measurements raise `CalculationError`. Missing urine is not assumed zero.
- `project_workout_loss(measurement, duration_minutes, comparable_conditions=...)`
  scales the measured rate only after explicit comparability confirmation. Results
  are loss estimates, not drinking targets; uncertainty is qualitative, not a
  fabricated confidence interval. Protocol confirmation means comparable dry
  weighing with recorded fluid/urine and no known unaccounted mass changes;
  comparability includes environment, intensity, equipment, and activity context.
- `calculate_forecast(summary, generated_at=...)` consumes an engine-produced
  `DailySummary` and explicit aware clock, returning UTC `generated_at`, intake totals,
  component ledger, provenance, version, assumptions, uncertainty, reasons, and
  missing inputs. Requirement bounds remain `None` with `insufficient_data` until
  the baseline/population method is approved. No weight-per-kg heuristic, weather
  bonus, HR/HRV adjustment, or creatine rule is implemented. Workout losses are not
  added to an unapproved daily baseline or counted twice as planned and actual work.

`Composition`, `BeverageLog`, and `WorkoutMeasurement` validate construction.
Result dataclasses are trusted internal outputs, not untrusted HTTP request models.
Forecast assembly additionally checks that totals are finite, nonnegative, and
estimated water does not exceed beverage volume.
Unknown constructor keywords fail. Backend must parse/validate wire schemas,
reject extra fields, enforce reviewed domain upper bounds and request limits,
map nutrition/provenance structures, and serialize dates/UUIDs. This engine rejects
nonfinite arithmetic but does not invent physiological upper limits.

Map `CalculationError.code`/`.field` to the existing
`{code, message, request_id, retryable}` envelope in the backend. Error messages
contain field identifiers, never supplied values. Internal snake_case field names
match the contract concepts; final HTTP status enums, provenance, ledger, and
nutrition JSON structures still need a frozen OpenAPI agreement. No endpoint or
shared contract is changed by this module.

## Scientific basis and limits

[NATA 2017, Table 2](https://pmc.ncbi.nlm.nih.gov/articles/PMC5634236/)
provides the measurement-based sweat-loss equation. This implementation uses
`(pre_mass_kg - post_mass_kg) * 1000 + consumed_ml - urine_ml`, then divides by hours.
The approximate mass-to-volume conversion and unmeasured mass changes limit the
estimate. Repeated assessments in realistic, comparable conditions are needed;
a single measurement is not a calibrated forecast interval. The published Table 3
runner example (0.8 kg loss, 400 mL consumed, 45 minutes) supplies an independent
1,600 mL/hour numerical fixture. No replacement percentage or diagnostic threshold
is applied. Reference checked October 26, 2026.

Composition conversion is dimensional accounting: a sourced amount per serving
scales with consumed volume. Electrolytes never multiply water. See the existing
[hydration design](../../docs/HYDRATION_MODEL.md) for the pending baseline review.
Tests establish software arithmetic and failure behavior, not clinical validity.

## Tests

From repository root:

```sh
python3 -m unittest discover -s tests/hydration -v
python3 -m pytest tests/hydration -q
```

Run the preserved starter suite separately from `Hydra-Ai-Starter/`:

```sh
python3 -m unittest discover -s tests -v
python3 -m pytest tests -q
```

The package has no network/provider SDK, API credential, file-write, or persistence
path. All billable Meta behavior remains outside this engine and disabled for this
work. A no-network test exercises calculation paths with socket connections blocked;
it does not verify Amine's future gateway, shared cap, or bypass prevention. The
$150 shared ceiling and $120 operational cutoff are unchanged.

## PR #4 correctness review

The review found and fixed intermediate ratio overflow/underflow in composition
and workout projection arithmetic, decimal mass-balance cancellation residue,
unchecked forecast totals, and untyped timezone conversion overflow. Nonexistent
ZoneInfo wall times in a DST gap are rejected; both valid fall-back folds remain
valid. Local-day selection also has a half-hour DST-transition regression test.
Duplicate checks reject all repeated IDs in a supplied snapshot, including outside
the selected day; callers must not submit multiple users or revision histories.

Numeric policy: input int/float values are interpreted through their decimal string
representation for serving conversion and workout arithmetic, using standard-library
Fraction intermediates. This avoids range loss from intermediate multiplication or
division and decimal subtraction residue. Results round to float at each public
output boundary. A positive value too small to represent is rejected as
numeric_underflow, never reported as known zero. Workout numeric failures return
insufficient_data with a reason. This policy cannot recover precision lost before
input and is not an uncertainty model. Extreme test values verify safe failure, not
physiological plausibility. Daily nonnegative totals use math.fsum.

Ready for backend adapter development after PR review, with these remaining gates:

- Freeze and test HTTP schemas, error mappings, and serialization. Preserve the
  requested date/timezone and log-revision context alongside forecast output.
- Enforce ownership, complete snapshot retrieval, current revisions, idempotency,
  stale-result invalidation, and reviewed domain/request-size limits in the backend.
- Verify nutrition evidence and basis units. Mass-based water composition (g/100 g)
  cannot be passed as mL/100 mL without a justified density conversion.
- Validate the weighing protocol, measurement resolution, repeatability, and
  comparable exercise conditions before using projections with users. Constant
  sweat rate over another duration remains an assumption, not a validated personal
  forecast. Do not present it as a required intake or hydration-state diagnosis.
- Approve a daily baseline method and supported population before replacing the
  insufficient-data fallback. Numerical tests are not scientific validation.

The legacy starter's heuristic forecast is preserved and is not used by this engine.
Its passing tests do not approve those formulas for backend integration.
