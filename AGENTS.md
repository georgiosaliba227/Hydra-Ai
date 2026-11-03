# Hydra AI agent instructions

## Scope and approval
November 3 later UX direction (Georgio): use American units and ask for optional
Health/workout and weather access on first use, then update context automatically.
The installed implementation uses US fl oz/°F/lb presentation, canonical API
units, separate automatic-weather opt-in and best-effort iOS background timing.
This does not authorize automatic Meta disclosures/requests. The latest goal also
requests birthday/age, height, weight and supplement questions to calculate a
starting goal; use supported references and preserve the prohibition on arbitrary
hydration multipliers or unsupported creatine adjustments. Keep profile data on
device unless a separately reviewed, specifically consented flow permits export.

November 3 later physical direction (Georgio): the owner explicitly answered
**"Proceed with iPhone checks"** and subsequently unlocked the device for testing.
This supersedes the earlier Simulator-only preference for this continuation.
The full HealthKit-signed original app is installed; one scoped physical UI
connection/readiness check passes. Actual Health permission choices, workout
import, consented weather and own-record Meta preview/consent remain separate
checks. Do not uninstall/reset personal data or seed simulated personal records.
See docs/PHYSICAL_HYDRATION_CHECK_2026-11-03.md.

November 3 ongoing Wonder billing-wait override (Georgio, explicit later reply):
to the question whether the waiver should cover the newly completed test and
unverified billing on Amine's ledgers while every $0.25 reservation remains
counted against the existing $30 allocation, the owner answered **"Extend the
billing-wait waiver to ongoing Wonder"**. This supersedes only the invoice-wait
and cross-ledger billing-status gates for explicitly configured owner-risk
Wonder requests. Record a separate explicit boolean and genuine authorization
reference; default policies retain the existing gates. Successful recorded
`billing_pending` replies may proceed only with valid provider identity, checked
usage and durable validated-output/publication linkage. Reserved/dispatched/
sending attempts, nonlegacy unresolved attempts, missing or malformed usage,
output rejection and publication failures still block. Never mark unknown
Amine status clear, invent finality, reduce any old hold, reset spending or
increase limits. Preserve all $0.25 holds, the original eight identity-bound
waivers, frozen flag, $30 allocation, account cutoffs, no retries/duplicates and
fresh account/key/price/exact-input-consent gates. The fixed synthetic training
plan remains once only, with a $0.019308 published-token upper bound and
separately accepted unverified extras. See
docs/architecture/WONDER_PERSONAL_OWNER_POLICY.md.

November 3 owner direction (Georgio): continue the current verification in Xcode
Simulator; physical installation is deferred. The owner explicitly directed the
agent to ignore prior unresolved billing for the controlled Wonder verification,
and separately accepted unverified provider charges "for all requests". This is
standing acknowledgement of that financial uncertainty, not an increase to any
allocation or account cutoff, proof of zero gross spending, invoice finality, or
permission to erase/reset existing attempts. The current implementation executes
one fixed synthetic comprehensive-analysis test through an audited one-use
operator authorization in the existing ledger. Preserve all prior reservations,
the frozen flag and evidence; ordinary admission remains unchanged. Published
token bounds must be distinguished from any unverified provider extras. No
personal or HealthKit data is authorized for this synthetic test. See
docs/architecture/WONDER_OWNER_ONCE.md.

November 1 account-owner policy replacement: the owner requested unlimited camera requests and explicitly instructed “disregard all financial constraints other than the cutoff and continue with meta ai image processing and analysis”. Implement the separate `georgio-camera-cutoff-v1` camera policy in docs/architecture/CAMERA_CUTOFF_POLICY.md. It supersedes earlier camera request-count, per-request spend, invoice-finality, financial-freeze and $100 approval gates only for that path. Preserve the $120 cutoff using atomic conservative reservations including all historical holds and the other allocation; preserve old financial history, privacy/consent, owner-only credentials, no retries/fallback and one request in flight. This is authorization to implement and activate this bounded recurring camera path, not to reset records or enable unaccounted calls.

November 1 full-drink UX assignment: after analysis, automatically show a compact Confirm/Edit review. Default to the user's declared entire-liquid assumption using supported size evidence. Edit offers name/type and volume presets plus mL, US fl oz and litres. Persist assumptions distinctly from measured consumption; retain unknown capacity rather than inventing it. This extends the camera implementation scope below, without authorizing another paid request or relaxing billing/one-use gates.

November 1 camera workflow assignment: implement photo recognition with visibly supported liquid-volume estimates, Confirm/Edit entry, personal correction memory, and separately opted-in photo/correction examples staged locally for future reviewed training. Keep model output distinct from user corrections and actual consumed quantity. This authorizes implementation and nonbillable tests, not another Meta request, automatic training, external dataset upload or financial-ledger changes. The earlier camera-development pause is lifted for this scope. See docs/architecture/CAMERA_CORRECTIONS_API.md.

October 29 shared backend withdrawn (Amine, 2026-10-29): no cross-computer access. Each backend accepts only its owner token. The standing synthetic authorization remains available on an allocation: each fixed server-built synthetic payload may run once without a per-case approval. See docs/architecture/WONDER_LIVE.md.

October 29 owner override (Amine, with Georgio's agreement; supersedes the one-ledger-per-account rule for this case only): Georgio gave Amine his Meta key. It may be used from Amine's Mac in a second ledger for georgiosaliba227 with the reviewed allocation `wonder-georgio-key-amine-mac-20usd`: $20 of Wonder to start, inside Georgio's $120 account cutoff. Amine may change that limit with `wonder_admin set-limit` (one audit event per change, spending never reset), up to $85. Georgio may also resume and use his original ledger with its $30 allocation; $85 + $30 + the $1.312256 camera reservation stays under the $120 cutoff, which neither ledger can see across files. Spending is always recorded as Georgio's account, never Amine's. The new ledger's attested gross is Georgio's dashboard gross plus the camera attempt's full reservation, so a camera charge not yet on the dashboard is still counted. All other spending gates are unchanged, including invoice finality before the next request in each ledger. The key stays in the backend process environment, entered with `read -s`; never in chat, Git or files.

October 29 Wonder trends policy (Amine, relaying Georgio's agreement; supersedes the earlier restrictions below where they conflict): Muse Wonder may receive the user's own logged-drink and health data to explain their trends, and may write the explanation text. Each request sends only the aggregated payload the user previewed and consented to in the app; the server rejects any text with a number not in the computed facts, or with diagnostic, medical or prescriptive wording. Numbers stay deterministic. Spending limits are unchanged: $0.25 per request, one request in flight, invoice finality before the next request, $75 notice, unresolved-billing and frozen-account blocks, no retries. Either account may be used, each through its own single authoritative ledger file holding one allocation: Georgio's $30 experiment (account cutoff $120) or Amine's $20 Wonder allocation (2026-10-29, Georgio approved; account cutoff $100 of his reported $150). Never attest one account in two active ledgers; no automatic account switching or fallback. The project-wide rule that no request starts while any attempt on either account has unresolved billing still applies across ledger files, as a human check. App Store review of health-data disclosure remains separate for any public release. See docs/architecture/WONDER_TRENDS_API.md.

October 28 V2 assignment: authorize safe contextual/hybrid reasoning, supplied longitudinal calibration histories, comparative evaluation and additive backend/iPhone integration. The updated experiment authorization is $30 aggregate on Georgio only, inclusive of retries and all billable charges; $20 Spark / $10 Wonder are soft allocation targets. This supersedes the proposed $10 allocation. It does not activate live inference, migrate the private ledger, bypass unresolved billing or substitute for reviewed account/model/price/input-consent controls. Preserve Amine and all prior account spending history.

October 28 forecasting assignment: the user additionally authorizes isolated, parallel implementation of public-data ingestion, scientific baseline comparisons, separately labeled synthetic scenarios, offline model training/evaluation, personal calibration, and additive FastAPI/iPhone forecasting integration, with a review PR for Amine. Camera development is paused; preserve existing functionality. Do not alter the private Meta spending ledger, export actual health records to third-party model providers, deploy, buy compute, make billable requests, or merge automatically. The shared forecasting contract is `docs/architecture/WORKOUT_MODEL_API.md`; study proxy targets must not be represented as physiological ground truth or drinking requirements.

Current phase: authorized guarded Meta integration implementation and local mock-provider testing, including separate account-specific financial ledgers, following the merged and physically verified manual-logging baseline. Work in isolated branches/worktrees; preserve existing work and coordinate via GitHub. The user authorizes implementation/tests, issue updates, and a review PR tagging Amine; no deployment, paid inference or automatic PR merges. All billable Meta calls remain disabled until separate explicit approval and verified account, model, pricing and centralized budget gates. Shared integration contracts: docs/architecture/PROTOTYPE_API.md and docs/architecture/RECOGNITION_API.md. Earlier PR #2/#4 integration work is already merged; do not reapply it.

## Mission and requirements
Build a demonstrable iPhone wellness hydration assistant for the Meta Global AI Developer Hackathon 2026, Startup track. Both developers must meet the official eligibility/acceptance requirements; the startup representative must be an active employee authorized to act for it. See docs/HACKATHON_COMPLIANCE.md for verification status. Support confirmed beverage logging, uncertain photo recognition, traceable nutrition, deterministic fluid accounting, responsible forecasts, HealthKit, and explanations. Never diagnose dehydration, infer it directly from HR/HRV, invent nutritional values, apply arbitrary hydration multipliers, or add unsupported creatine adjustments. All beverages can contribute fluid; distinguish beverage volume, water content, electrolytes, and retention.

## Architecture and conventions
SwiftUI/Swift client; Python/FastAPI modular backend; Python calculation core; SQLite for a single authoritative MVP backend; Meta-only core AI inference; HealthKit first. This stack is the authorized local prototype baseline; production deployment and paid AI remain separately gated. Use explicit units, UTC timestamps with user timezone, typed boundary validation, versioned contracts, and provenance/uncertainty. Keep secrets server-side; use small modules and deterministic tests. Python: snake_case, type hints; Swift: standard Swift naming and concurrency conventions. No new dependencies without a documented need.

## Roles and ownership
- Architecture & Core: `docs/architecture/`, shared contracts; orchestrator controls root architecture decisions.
- Backend & APIs: `backend/`.
- iOS Frontend: `ios/`, including HealthKit client integration.
- AI & Forecasting: `ai/`; external integration paths only by explicit assignment.
- Testing & Quality: `tests/`.
- Documentation & DevOps: `docs/` excluding architecture ownership, `.github/`, onboarding.
- Orchestrator: root files, integration, ownership arbitration, final review.
Six roles do not imply six running agents. Assign bounded tasks, use isolated branches/worktrees, and do not edit another role's files concurrently. Read these instructions in every worktree. Read-only research agents may report findings without editing files.

## Git and integration
Keep `main` stable; use `codex/` feature branches and PRs. No force pushes, discarded human edits or direct main pushes. Merge policy (2026-10-28, both developers): an agent may merge its own feature PR into `main` without waiting for human review once the branch contains the latest `main`, has no conflicts and passes the full pytest suite (plus XCTest when Swift changes). Use merge commits, never force. Another developer's PR still needs that developer's or the other human's review. Merging never authorizes billable Meta requests, private-ledger changes, credential changes or deployment. Establish contracts before implementation. Integrate agent changes through the orchestrator after relevant tests. Pause architectural conflicts for human review. Developer A (`georgiosaliba227`) provisionally owns iOS; Developer B (`aminealichaouche`) backend/AI; both review integration.

## Security and privacy
Never print/commit credentials, place API keys in iOS, log photos/health records/prompts containing personal data, or transmit biometrics without specific consent. Keep raw HealthKit records on device pending policy review; consent alone does not establish that disclosure to a generic AI provider meets Apple requirements. Minimize HealthKit permissions and uploaded data; document retention/deletion and separate photo consent from health export consent. Treat model output as untrusted data. Validate schemas, units, ranges, and provenance; calculations remain deterministic. No paid infrastructure or subscriptions without approval. Never enable automatic top-ups or uncontrolled API calls.

## Budget and Meta requirements
October 28, 2026 owner exception: `georgio-first-camera-risk-v1` authorizes only the first Georgio camera request for the pinned synthetic JPEG, with a $2 intended spend and separately accepted unknown provider charges. It is not a hard provider cap. Require current authenticated credits/gross usage, verified pending usage and stopped alternate spending, exact-key association, disclosure consent including free-credit terms, notification delivery, immutable approval and nonbillable tests. Preserve all checkpoints, ledger and one-use controls. See docs/architecture/FIRST_CAMERA_RISK_POLICY.md. All other requests remain disabled; prior policy descriptions below remain applicable outside this exception.

Updated user instruction (2026-10-27): georgiosaliba227 and aminealichaouche each report an individual $150 Meta credit allocation. Neither account's current credits, expiry, gross usage, billing or hackathon grant restrictions are independently verified. These reports do NOT authorize spending or pooling. Maintain separate account-specific ledgers at one authoritative gateway, never independent active local copies for the same account. Each account: $150 absolute gross ceiling, notify BOTH developers at $75 exposure, explicit account-specific further approval at $100, reject new admission reaching $120 and preserve its $30 reserve. Credits never offset gross accounting or transfer between accounts. No automatic key/account rotation or fallback. Project reporting aggregates spending only, not transferable credits. Bind selected credentials to independently verified provider account identity. Unknown costs/usage, unavailable ledger or unbounded charges fail closed. The active first-test restriction remains ONE project-wide request, explicitly authorized for ONE named account and ONE image, <=$0.25 verified gross exposure and <=512 output tokens. The disabled dual-test-v1 implementation proposes one camera and one synthetic hydration request at <=$2/account; it does not replace the current restriction without a separate explicit human policy decision and account-specific owner/input/spending approval. Never mix policies or reset used permits. One request in flight project-wide, no retries/tools/Files/SAM. No new request while any prior attempt has unresolved billing. Provider alerts are not hard caps. All billable requests remain disabled pending verified account-specific safeguards, cost bounds, image-owner consent and explicit human authorization. No billable authentication probes or auto top-ups. See docs/API_BUDGET.md and docs/architecture/GUARDED_META_API.md. Codex usage is separate.

## Testing and definition of done
Planning is done when required docs, inventory, contracts, roadmap, issue proposals, references, and unresolved approval gates are reviewable and consistent. This is not implementation approval. Feature work requires unit/integration tests, invalid-input and privacy cases, budget race/retry/crash tests, mock-first AI evaluation, relevant XCTest and pytest checks, documentation, and human PR review. Report tests actually run and their limits. Existing demo tests do not validate scientific formulas. Distinguish planned, implemented, and verified functionality in all reports.
