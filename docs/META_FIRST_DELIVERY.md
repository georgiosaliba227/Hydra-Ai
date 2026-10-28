# Meta-first implementation and activation handoff

October 27, 2026. **Real Meta camera and hydration inference have not run. The priority milestone is incomplete.** This work implements and tests the remaining safe integration path. It grants no spending or photo disclosure approval. The permanent ledger and private credentials remain unchanged.

October 28 update: restored from `ef7dc94`, already present identically on both the Meta-first and PR #13 branches. Additional parser, live-error and backend-generation safeguards are implemented; explicit existing-ledger migration tools and [exact-image preparation](META_CAMERA_ONE_REQUEST.md) now make the remaining technical operations reviewable. A read-only preview against the existing permanent ledger verified the seven-table predecessor is compatible and reports `migration_required`; no table, event or financial record was changed. Combined validation: **485 pytest + 32 subtests; 3 starter; 41 XCTest; 2 mock UI plus 1 fake-provider consent UI passed**, with 4 opt-in UI cases skipped. Evaluation reproduction and the offline rehearsal also passed. Current branch state is in [PROJECT_STATUS.md](PROJECT_STATUS.md). This update does not authorize the migration or any request.

## Existing foundation retained

Integration PR #13 (`codex/roadmap-integration`, inspected at `be4e492`) already contains #9, #10 including human-merged #12, and #11. The new work starts there in an isolated branch; it does not reapply #2/#4, rewrite source branches, merge PRs or expand unrelated UI. Amine coordination is [posted on #13](https://github.com/georgiosaliba227/Hydra-Ai/pull/13#issuecomment-6450854995).

The camera uses `POST https://api.meta.ai/v1/responses`, `muse-spark-1.3`, `text.format` JSON Schema, minimal reasoning, at most 512 output tokens, no tools, no history and no retries. Standard model selection and transport structure match the official [Responses documentation](https://dev.meta.ai/docs/protocols/responses), [model catalogue](https://dev.meta.ai/docs/models), and [pricing](https://dev.meta.ai/docs/pricing-rate-limits), checked October 27. Public documentation is not authenticated account access or a whole-request billing guarantee.

The existing iPhone flow prepares/exports one JPEG, requires backend and Meta disclosure consent, and requires confirmation of beverage identity and quantity consumed. Model capacity estimates and unverified label transcription never become confirmed consumption or nutrition. No iOS key or raw HealthKit upload is introduced.

## Implemented and verified in this follow-up

- Authenticated `POST /v1/hydration-explanations` and capability endpoint, initially synthetic-only. `HYDRA_META_HYDRATION_ENABLED=false` remains independent of the camera flag. An approved live service uses Amine's key/account and the same ledger object; it never selects another account automatically. See the [hydration contract](architecture/HYDRATION_INTELLIGENCE_API.md). The model selects grounded signals for intake, exercise, weather and synthetic patterns; reviewed text renders them and unsupported selections are counted. No model-written numerical or medical recommendation is accepted.
- Camera and hydration attempt observations bind the returned structured output digest, API latency, HTTP status and failure stage to the existing ledger's usage records. Only compact metadata is persisted. Usage-derived token cost is separate from externally reviewed final billing. No permanent schema migration occurred.
- [Offline evaluation](META_EVALUATION.md) covers category/brand accuracy, capacity errors, abstention, unsupported selections, human hallucination/quality rubrics, consistency, latency, tokens and separate account costs. Exact-input/output ledger evidence is required for live results; a `meta_live` label alone is insufficient. The seven-case synthetic dataset has six handcrafted observations and one unrun case. Its reproducible [report](../evaluation/synthetic-report.json) explicitly records **zero actual Meta runs**; it does not measure model performance.

Validation on the combined changes: **410 pytest tests + 32 subtests passed**, **31 XCTest unit tests passed**, and **1 camera consent/confirmation UI test passed against a loopback fake provider**. The seven-group offline backend rehearsal passed with network attempts blocked. The evaluation command below exactly reproduced the committed report. Independent code review found and corrected malformed-preflight handling and two scoring edge cases. One existing Starlette/httpx deprecation warning remains. No physical-device, real model, live account, or invoice validation is claimed; no new dependency was added.

```sh
python -m pytest tests -q
python -m scripts.evaluate_meta --dataset evaluation/synthetic-dataset.json --observations evaluation/synthetic-observations.json
```

## Credential preflight

Run the local, read-only diagnostic without starting a server or contacting Meta:

```sh
python -m scripts.meta_preflight \
  --env-file '/Users/georgiosaliba/Library/Application Support/HydraAI/private/backend-georgio.env' \
  --database '/Users/georgiosaliba/Library/Application Support/HydraAI/private/meta.sqlite3'
```

The existing Georgio credential loads and passes the official transport's local syntax validation. The private file is owned and mode 0600; selected account is Georgio, configured mode is mock, and billable requests are disabled. No credential or fingerprint is printed. This does **not** verify authentication or model access. Current preflight reports no notification credential, no recorded account/key binding, no finality table, and no matching authoritative-ledger path in this env file. Nothing was activated or migrated. Amine's credentials were not opened or modified.

On October 28 Georgio signed in and the selected account's billing/credit and all-key/all-model usage views were inspected read-only. A displayed credit amount, outstanding balance and selected-window usage do not establish lifetime gross spend or finality of pending financial activity. Account-specific free-credit content-use terms require explicit review alongside Standard-model documentation before any disclosure consent. No private account/payment identifiers or evidence were added to GitHub, and no account attestation was imported into the ledger. Public [Standard rates](https://dev.meta.ai/docs/pricing-rate-limits), [Responses format](https://dev.meta.ai/docs/protocols/responses) and [model identity](https://dev.meta.ai/docs/models) were rechecked October 28 and still match source.

## One actionable activation checklist

1. **Reviewed code and one authority:** Georgio and Amine review the exact integration/Meta-first commits. Separately review [preview-finality-schema and migrate-finality-schema](META_LEDGER_MIGRATION.md) for the existing permanent ledger and configure the approved runtime to that same path; never run init again, initialize another authority or reset history. Supply and verify the existing notification path to both developers.
2. **Private account evidence:** Georgio supplies authenticated provider identity/key binding, Standard model access, current credits/expiry/grant coverage, gross and pending usage across all keys, exclusive gateway custody and retention terms. Amine supplies his own independent evidence before hydration. Local key presence and reported $150 credits do not establish any of these facts.
3. **Enforceable gross bound and policy:** obtain provider evidence bounding the whole request, including failed/partial/internal/extra charges and invoice finality. Current full-context token reservation is $1.312256 before extras, which fails the active $0.25 first-request ceiling. Either establish an enforceable smaller provider-backed bound with reviewed enforcement, or explicitly adopt a different policy. The proposed $2 ceiling is **not approved**; a larger ceiling alone does not verify costs. Amine's later hydration request also needs explicit policy authorization beyond the current one-image/project-wide permit.
4. **Exact input and one-use authorization:** export the actual prepared iPhone JPEG, verify its backend-normalized SHA256, and obtain owner consent for those exact bytes plus expiring Georgio-specific spending approval bound to account, model, price, policy and input. Amine separately approves the exact synthetic context hash and his own later request. Each request keeps <=512 output tokens, one in flight, no retries/tools/Files/SAM and no unresolved prior billing.
5. **Execute, reconcile, then evaluate:** after all gates pass, enable only the approved path for one request, restore disabled settings, retain the original ledger, and compare the request ID/usage with authenticated final billing. Unknown or mismatched charges freeze further work. Evaluate the linked output and record real metrics; do not substitute the offline fixture scores. Confirm camera identity/consumption on iPhone. Only after camera billing finality can a separately authorized hydration attempt proceed.

Per-account $75 notices to both developers, $100 further approval, rejection reaching $120 and the $150 absolute ceiling remain in force. Credits never offset gross accounting or transfer between accounts. No automatic rotation or fallback exists. The provider support inquiry remains prepared and unsent.
