# Muse-guided simulated training, kept separate from personal measurements

The owner reports that actual measurements still need to be collected and
requests Muse-generated simulated training data. Muse chooses a bounded training
scenario mixture; Hydra emits reproducible numerical records under explicitly
declared simulation assumptions. Neither the plan nor its labels are measured
physiological truth or the owner's calibration history.

## Fixed Muse interface

`backend/muse_training_plan.py` exports `fixed_payload() -> dict`,
`validate_payload(payload) -> None` and `parse_reply(ProviderReply) -> dict`.
The payload has no inputs from a person or study records. It contains only the
fixed recipe descriptions below. Use `muse-wonder-1.0`, minimal reasoning,
512 maximum output tokens, store/stream/background false, no tools and a strict
JSON schema. The exact output is:

```json
{"version":"muse-synthetic-plan-v1","training_weights":{"base":2,"missing_covariates":1,"wide_noise":1,"outlier":1}}
```

Each weight must be a genuine integer 1 or 2. Reject extra/missing keys, duplicate
JSON keys, booleans, free prose, incorrect versions/models, incomplete responses
and unsupported output parts. No physiological coefficient or numerical loss
label is requested from Muse.

`OwnerPersonalWonderGateway.generate_training_plan(quote, consent_reference)`
uses the same authoritative financial policy and one-use ticket, purpose
`synthetic_training_plan`, and requires the explicit research authorization
reference. No HTTP training-plan dispatch route or separate ledger is added.
The ordinary finality/readiness/budget gates still apply. No real generation is
claimed from a fake transport or an offline fixture.

Result envelope:

```text
version: "muse-training-plan-result-v1"
plan: the strict object above
generated_at: UTC ISO8601
provenance:
  mode: "meta_live"
  provider: "Meta"
  model: "muse-wonder-1.0"
  account_id: "georgiosaliba227"
  attempt_id: canonical UUID
  payload_sha256: SHA256 of the fixed payload
  personal_data_used: false
provider_observations:
  latency_ms, input_tokens, output_tokens, usage_derived_cost_micro_usd: nonnegative
  billed_cost_usd: null
```

Store a hash of the validated plan in the attempt's output-check event, never
private prompts/facts. A production training run claiming `plan_origin=muse_wonder`
must verify its envelope's attempt, purpose, payload and plan digest against the
existing ledger read-only. A standalone supplied file is not proof that Muse
generated it. Offline test plans use `plan_origin=offline_stub` and are labeled
that way throughout the report/artifact.

## Deterministic simulation and frozen evaluation

Reuse `ai/forecasting/synthetic.py` and the current trainer, without editing their
frozen behavior. Its anchors come only from the real SpectroPhon TRAIN split.
The duration-linear mapping from a study mass-loss proxy to simulated exercise
loss, its noise, and reconstructed mass balance are software assumptions, not
a validated physiological model. Weather, humidity, intensity, HR/HRV, caffeine
and creatine do not gain numerical effects.

Generate a fresh base cohort with seed 20261103 and 240 simulated users, rekeyed
to study `muse-guided-synthetic-v1` and target
`simulated_exercise_loss_proxy_ml`. Retain source-anchor participant grouping.
Freeze train/validation/calibration/test assignments and record their hashes
**before consulting the Muse plan**. Augment only the base TRAIN groups. Keep
their source-anchor participant IDs across every recipe and clone; the original
validation/calibration/test rows remain byte-for-byte unchanged.

Each weight produces one or two training-sized recipe blocks:

- `base`: independently sampled bounded observation noise, ±40 mL.
- `missing_covariates`: the same label mechanism, with 50% missing mass/age.
- `wide_noise`: bounded observation noise, ±150 mL.
- `outlier`: base noise plus +500 mL contamination on every fourth augmented
  row; record the full 540 mL noise/contamination bound.

These magnitudes are declared software stress settings, not instrument accuracy
or physiological effects. Reconstruct post-mass consistently from the observed
label/intake/urine. Keep the latent generator loss separate from the noisy label.
Validate units, finite/nonnegative values, provenance and duplicate/leakage
invariants. Do not alter holdouts to accommodate augmentation.

Fit cohort, ridge, random-forest and gradient-boosting candidates with the
existing training-only preprocessing and validation-only model selection.
Compare the unaugmented base experiment with the Muse-guided training mixture on
the same frozen synthetic holdouts. Report MAE/RMSE/bias and simulated interval
coverage, plus predeclared missing-input/noise/outlier/duration-shift stress
tests. Report a privileged latent-generator oracle separately; it is not a model
available for an unseen real person. Never select another Muse plan in response
to published test scores.

## Artifacts, operation and serving exclusion

Add `ai/forecasting/muse_synthetic.py` and
`scripts/muse_simulated_training.py` with explicit prepare, offline-stub training,
real-plan training and confirmed live-plan generation operations. Live generation
uses the financial gateway above; it cannot bypass a blocked readiness result.
Use the already-installed research dependencies, with no new package.

Write records, split manifest, plan provenance, model and evaluation to a new
research-only output directory. Mark the model `runtime_use=offline_research_only`
and synthetic. Never overwrite `synthetic_demo.json`, real-study artifacts,
the current app baseline, personal serving artifacts or on-device history.
Genuine measured-data evaluation remains separate and uncontaminated. Simulated
scores cannot establish accuracy for Georgio or satisfy the real-history goal.

Tests must prove payload/parser bounds, reproduction, mass-balance consistency,
source/group separation, unchanged holdouts, invalid/forged plan rejection,
offline-stub honesty and serving exclusion. The real Muse request/training step
remains pending until current financial admission gates pass.
