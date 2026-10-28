# Prepare the exact one-request camera test

`scripts.meta_camera_prepare` produces a redacted **local plan**, never a request or authorization. It accepts only explicit existing file paths. It does not send authentication probes, token-count calls, model requests or notifications; create/copy/migrate a ledger; source shell configuration; change environment variables; reserve money; or record consent/approvals. No live Meta result is established by running it.

Use the existing backend Python environment, with the actual private server environment, authoritative ledger and exact JPEG exported by the iPhone preparation flow:

```sh
python -m scripts.meta_camera_prepare \
  --env-file /absolute/private/backend.env \
  --database /absolute/private/existing-meta.sqlite3 \
  --image /absolute/private/iphone-prepared.jpg \
  --account georgiosaliba227
```

All files must be existing, owned regular files with mode 0600 and absolute paths with no symlink component. Configuration contains literal assignments; it is parsed, never executed. The command reads only Georgio's selected credential for local construction/binding checks and never prints keys, key fingerprints, provider account identifiers, private evidence references, file paths, JPEG bytes or prompts. Do not put private files in Git or paste keys into commands. Standard output contains image/payload hashes and redacted per-gate statuses; keep it private with the exact-input approval record.

The ledger opens through SQLite `mode=ro` and `query_only`. Preparation refuses WAL or recovery sidecars, malformed/missing schema and non-private files instead of attempting repairs or creating an alternate ledger. The existing authoritative ledger uses rollback journaling. Resolve any active writer/recovery condition through the reviewed operator procedure; never delete sidecars to make this command pass. The command cannot establish ledger custody and should never point to a copied test database.

## What the plan establishes

The command invokes the same `AnalysisRequest`, `sanitized_jpeg` and `request_payload` functions as the camera gateway. It reports the backend-normalized JPEG SHA256 and canonical complete payload SHA256. Metadata stripping and bounds therefore match the existing recognition path. Structural JPEG validation does not decode pixels or establish image ownership. True consent flags used to construct this local payload are not consent evidence, and there is no sender in the preparation command.

Export the **actual prepared JPEG** from the iPhone before granting consent. Import or submit those same bytes later; resizing, rotation, quality changes or re-encoding can change the normalized hash. A source-camera/photo-library hash does not automatically identify the prepared JPEG. The backend strips metadata from the supplied image, then matches its normalized hash against the permit. A mismatch requires a new review of the exact input; it is not permission to retry or reset a permit. Identity and consumption confirmation remain in the existing iPhone workflow.

Fixed local request options are Muse Spark `muse-spark-1.3` Standard, Responses API structured beverage output, `store:false`, `stream:false`, `background:false`, minimal reasoning, one image, at most 512 total output tokens, no tools/Files/SAM/history and no retries. The plan never takes a caller-supplied smaller token bound. Existing code uses the model context bound of 1,048,576 tokens, less 512 reserved output tokens: **1,048,064 input tokens**. Existing integer `Price.cost` arithmetic, assuming no cache discount, yields a **$1.312256 token-only reservation reference**. This is not expected request cost, a complete provider billing guarantee, or an account-approved price attestation.

The active first-request ceiling remains **$0.25**. The proposed **$2** dual-test policy stays disabled and cannot become authorized through configuration or this plan. Missing account/price evidence leaves the locally attested total bound `null`, never zero. Where valid local evidence and the permit-bound price exist, their token and extra-charge components are displayed separately. All are local attestations; provider verification remains a separate requirement.

## Gate meanings and next actions

`locally_satisfied` means this read-only snapshot meets the specific local check. `blocked` means its requirement failed. `not_evaluated` means prerequisites were unavailable; it never means passed. `unverified` identifies required external facts that this command cannot authenticate. `dispatch_authorized` is **always false**.

The command reuses existing ledger evidence/price/permit validators, `_policy`, `grant`, `verify_project_unfrozen` and `verify_prior_finalities` on the read-only connection. It checks exact-image matching, the selected account/key binding, permit policy and one-use state, prior attempts, unresolved billing, freezes and pending developer notices. It does not implement a second reservation/admission engine. The authoritative gateway retains the atomic race checks, separate account spending, $75 notifications to both developers, $100 further approval, $120 rejection boundary and $150 absolute ceiling.

Resolve the reported requirements before requesting a live run:

1. **Account and billing evidence:** Georgio privately verifies provider identity/key binding, Standard model access, gross/pending usage across keys, credits/expiry/grant terms, exclusive gateway custody, retention, all charge categories and request-level billing/finality. Verify notification delivery to both developers. Local key presence proves none of those facts.
2. **Cost bound and policy:** obtain a reliable total bound within $0.25 plus reviewed enforcement, or separately request an explicit human policy decision. The current full-context reservation reference exceeds $0.25 before possible extra charges; the $2 proposal is not permission.
3. **Exact input and approval:** identify the normalized hash of Georgio's owned, nonsensitive prepared JPEG; obtain disclosure consent under reviewed retention terms and an expiring one-request approval bound to the account, input, model, price and active policy. Both developer reviews are required. Any schema migration is separately reviewed, never performed by this command.
4. **One guarded attempt, only when authorized:** use the existing authenticated iPhone camera path once. Preserve every attempt/reservation and resolve unknown billing before any later request. Amine's synthetic hydration request requires its own independently authorized account/input/policy after prior billing finality; it cannot borrow this approval.

Preparation reports do not establish real inference. After an approved execution, use the existing result-observation ledger and [offline evaluation](META_EVALUATION.md) to link the actual response, usage, latency and separately verified final charges. Unknown or mocked results stay clearly labelled.
