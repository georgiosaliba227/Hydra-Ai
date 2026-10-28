# Contextual intelligence V2: implemented mock experiment

This extension adds a structured contextual reasoning boundary and A/B/C comparison
to the existing numerical forecast, while preserving all v1 APIs and the guarded
Meta integration. **No Spark or Wonder request has run.** Candidate model names
and Standard tiers are future experiment labels, not verified access, pricing or
successful inference. No ledger, account, permit, key or billable flag is changed.

## Product behavior

System A returns the existing numerical method. System B selects bounded relevant
factors, missing information, contradictions, uncertainty and measurement steps,
with no numerical prediction. System C displays the same A prediction plus B's
context. The local mock selects enum IDs; the server validates grounding and renders
reviewed text. Arbitrary prose, diagnoses, percentages, fluid goals and numerical
overrides are not part of the output schema. Contradictions and required uncertainty
cannot be omitted. No numeric hybrid improvement is claimed by attaching context.

The new `/v2/workout-forecasts` personal path invokes the separately evaluated
longitudinal component. Histories are supplied by the caller and processed in
memory. Personal inputs never enter the contextual adapter, including its mock.
The iPhone shows comparable/recent sample counts, observation times, missing inputs
and the experimental/session-only boundary. The synthetic display exposes A/B/C
with explicit mock provenance and unobserved provider metrics. It validates equal
A/C numbers, absent B numbers, allowed codes and null live-model/usage observations.

See the [wire contract](architecture/HYDRATION_CONTEXT_V2_API.md) and
[personalization evaluation](FORECAST_V2_EVALUATION.md). Existing logging, intake
history, camera confirmation and financial safeguards are preserved.

## Reproduce the local experiment

From the repository root with the backend environment:

```sh
python -m backend.hydration_context_v2 > /tmp/hydra-context-v2-report.json
python -m pytest tests/backend/test_context_v2.py
```

The committed [benchmark report](HYDRATION_CONTEXT_V2_BENCHMARK.json) contains five
server-owned scenarios evaluated under each of two candidate labels: supplied
context, missing measurements, inconsistent mass balance, incompatible conditions,
and biometrics/supplement context. Expected enum labels are handwritten independently
of the selector. Contradictory weighing uses the existing mass-balance calculation
on an explicitly synthetic 70 kg before / 71 kg after / zero intake and urine case.

Enum-groundedness, unsupported-selection count, uncertainty completeness,
appropriate abstention, missing-information and contradiction detection measure
this deterministic validator/fixture pipeline. A/C numerical equality and B/C
explanation equality check that contextual output cannot change the source result.
These are software fixture checks, not measured Meta quality, real-world accuracy,
or independent evidence that either candidate model is better. Candidate labels
use the same local implementation and must not be ranked by these scores.

System A has no contextual score; system B has no numerical accuracy score.
Numerical accuracy for real studies and longitudinal histories stays in its
separate reports. Provider latency, token counts and actual billed cost are null,
not fabricated zeros. There is no external validation or clinical claim.

## Future bounded live experiment

`Selection.model_json_schema()` and the reviewed `PROMPT` define the proposed
output boundary. No function in this module sends that prompt or opens a provider
transport. A future integration must independently verify candidate model identity,
Standard tier access, applicable terms, current price and a whole-request cost bound;
complete the reviewed account-specific batch policy, reconcile unresolved billing,
and obtain explicit human authorization before dispatch. Handwritten synthetic
cases must remain separate from withheld real outcomes and private user histories.
The proposed $10 allocation does not authorize spending or replace any existing
account cutoff or first-test policy. Spark Contributor/Open remain out of scope.
