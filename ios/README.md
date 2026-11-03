# Hydra AI native iOS prototype

SwiftUI app connected to the local FastAPI/SQLite backend. A selected, resized beverage photo is uploaded only after backend consent; guarded Meta mode additionally requires explicit consent to transmit it to Meta. HealthKit records stay on device. No Meta credentials exist in this client.

## Run

1. Start the root backend using the integration guide and a generated local development token (`HYDRA_API_TOKEN`, not a Meta key).
2. Open `HydraAI.xcodeproj`; choose HydraAI and an available iPhone simulator. Physical devices require your signing team/bundle setup.
3. Open Settings in the app. Enter `http://127.0.0.1:8000` for a simulator, or the Mac's private LAN address for a physical phone on a trusted network. Enter the local development token, then Save connection. The token stays in Keychain; the URL/mode use UserDefaults.
4. Today → Log a beverage → enter actual consumed mL → Save. The server's hydration engine supplies the daily beverage total. Water content remains unknown when composition is unsourced; no hydration goal or multiplier is invented.
5. Terminate/reopen the app: it reloads server history and summary from SQLite. Pull to refresh or use Refresh after connection errors.

Startup defaults to unconfigured backend mode. Offline demo is an explicit Settings choice with separate local JSON data; it never silently replaces a failed backend or uploads mock history.

## Delivery and failure behavior

The app persists the confirmed request and UUID idempotency key before POST. A timeout, lost response, or restart keeps that exact request available through **Retry pending beverage** on Today. New logging and changing destinations are blocked until confirmation resolves. Changing the credential for the same destination is allowed to correct authentication. A corrupt pending file blocks new submissions rather than risk a duplicate; preserve the file for recovery. There is deliberately no ambiguous-request discard button.

Server history pagination is followed to completion. The Today card uses the server summary, not the first history page. On refresh failure the previous view remains with an explicit error; no fresh total is fabricated. Pending acknowledgements are cleared only after server success and local removal succeeds.

## Transport and scope

HTTP is permitted only for localhost/private IPv4/LAN `.local` development hosts; remote URLs require HTTPS. Redirects are rejected to prevent credential forwarding. ATS allows local networking only, not arbitrary insecure traffic. The backend credential represents one local-demo account; this is not a production multi-user login. No public deployment is authorized.

## Tests/build

```sh
xcodebuild -project ios/HydraAI.xcodeproj -scheme HydraAI \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro,OS=26.5' \
  -derivedDataPath /tmp/hydra-integration-ios-signed CODE_SIGN_IDENTITY=- CODE_SIGNING_ALLOWED=YES test
```

Use ad-hoc signing for simulator runs: disabling signing omits the simulated application identity needed by Keychain and makes Save connection fail. Physical devices still require a valid developer signing team/profile. Do not work around Keychain errors by storing tokens in plaintext.

The suite covers inherited mock persistence/validation plus HTTP pagination/auth/idempotency/summary/errors, unsafe URL rejection, Keychain credential persistence, pending-request retry after store restart, and corrupt-pending fail-closed behavior. URLProtocol fixtures make no network calls. Physical-iPhone camera, HealthKit and LAN behavior need physical-device validation.

For DEBUG simulator verification only, launch-time `HYDRA_TEST_BACKEND_URL` and `HYDRA_TEST_API_TOKEN` override connection settings. With `simctl launch`, pass them through the documented `SIMCTL_CHILD_` environment prefix; never put a real token in source or a committed command. Release builds do not read these overrides.

Accessibility identifiers: `backendURL`, `backendToken`, `saveConnection`, `offlineMode`, `logBeverage`, `consumedVolume`, `saveBeverage`, `dailyTotal`, `retryPending`, `connectionError`.

## Opt-in real backend UI test

`HydraAIEndToEnd` is a separate shared scheme for `HydraAIUITests`. Its UI test skips unless the test runner receives `HYDRA_E2E_BACKEND_URL` and `HYDRA_E2E_API_TOKEN`. Use a running local backend with synthetic data; the test creates one 125 mL entry and deliberately leaves it for persistence inspection.

Build with `xcodebuild ... -scheme HydraAIEndToEnd ... build-for-testing`. Set those two environment values in the generated `.xctestrun` file's UI target `EnvironmentVariables` in a private temporary directory, then run `xcodebuild test-without-building -xctestrun <temporary-file> -destination <simulator>`. Never commit the populated file or print its token. The normal unit suite does not require backend access.

The UI test launches with runtime configuration, saves it through Settings/Keychain, logs 125 mL, checks the backend-derived total increases, terminates the app, then relaunches **without** configuration overrides and checks the same total. It fails if an existing pending beverage needs reconciliation. This validates simulator UI/network/persistence behavior, not physical-device camera/HealthKit behavior.

## Milestone 2 mock recognition

See [Milestone 2](../docs/MILESTONE_2.md). Configure the local backend, open Camera, capture/select a photo, consent to backend upload and choose an explicitly synthetic demo scenario. Analyze, review/correct identity and container capacity, enter actual consumed mL and confirm before Save. Meta inference stays disabled. Unknown nutrition stays unknown. A failed confirmation uses the existing Today retry action with its persisted request/key.

## Guarded Meta mode

Camera fetches authenticated recognition capabilities and fails closed if mode cannot be verified. Meta mode requires both backend-upload consent and separate Meta disclosure consent. It never claims zero retention. Live results require a server-issued settled recognition receipt, preserved in pending submissions, and confirmation of identity/capacity/consumption. All provider credentials remain on the server. Mock is the default; no live spend is authorized. See [budget controls](../docs/API_BUDGET.md).

`run_ios_e2e.py --live-simulation` only accepts an explicitly marked nonbillable loopback fake-provider backend. It runs the opt-in live-consent UI case with generated synthetic image data. It must never be pointed at a real Meta transport. Physical-only tests skip in normal simulator runs.

If Xcode hangs after passing simulator tests while collecting verbose diagnostics, `--skip-simulator-diagnostics` adds `-collect-test-diagnostics never`. Assertions and result bundles remain enabled; the flag is refused for physical destinations. `run_live_simulation.py` forwards this optional switch.

## Workout forecast prototype

Today → **Workout forecast · separate from intake** opens a separate estimate screen. **Run synthetic demonstration** submits only mode/timezone and requests the server-owned fixed fixture; the result is labeled simulated, never added to consumption. The local mock Meta explanation integration is explicitly labeled mock and makes no live provider request.

For a personal estimate, manually enter a planned workout and comparable conditions. Add completed manual weighing measurements with recorded intake/urine and independently established absolute error bounds. Explicit calibration-processing consent is required before upload. Unknown values must stay unknown: do not enter zero or invent instrument bounds. Missing usable calibration returns insufficient data; the trained research artifact does not silently supply physiological ground truth.

Session measurements/results remain in screen memory and clear when leaving or changing connection. **Save these manual measurements on this iPhone** is a separate, default-off choice followed by **Save session measurements**. Saved manual history restores across launches; use a record or the saved set explicitly in a new session, then give fresh consent for one estimate and its backend summaries. Meta consent is never saved or restored. Revisit fills the manual form for review without automatically adding evidence.

Manual history is capped at 32 records per connection, validates units/ranges/error bounds and explicit timestamps, and rejects duplicate event IDs or equivalent completion instants. Its atomic Application Support files use complete file protection and are excluded from backup. Only native Security and CryptoKit APIs are used, with no new package dependency. Random UUID profiles are bound to normalized endpoint plus a token fingerprint in device-only Keychain; neither endpoint nor token/fingerprint appears in filenames or exports. A different token or backend receives a separate profile, preserving prior profiles without exposing them to that connection. Corrupt/unavailable storage is visible and blocks overwrite until a successful read or explicit deletion. No raw HealthKit records, applied workout/heart-rate context, backend or Meta consent, forecasts or explanations are persisted by this store.

Saved records show their date, conditions, manual-weighing provenance and reported error bounds. Selective deletion also removes a loaded session copy. **Export saved manual measurements (JSON)** exports only the active profile's manual records; it contains sensitive weights, intake and urine, so the user chooses the destination. **Delete all saved manual measurements** removes every local connection profile's history. Settings → **Delete all my data** also clears all local manual history before requesting backend erasure; a backend failure remains visible and does not restore local history. Backend export remains separate from local history export.

After an estimate, `POST /v1/hydration-analysis` receives the same reviewed request once, with no Meta dispatch. Eight local research sections cover summary, workout loss, activity, environment, beverages, trends, uncertainty and measurements. Typed validation binds its numerical result to the already validated forecast. Missing endpoint/network failures leave the estimate usable. The existing separate Wonder preview/hash/consent flow handles explanation and saved replay. All results and consent remain transient; edits, deletion, new estimates, leaving and connection changes invalidate late responses. The backend processes calibration in memory. Numbers are estimated workout sweat loss, not consumed water, remaining need, diagnosis or recommended intake. A simulator run cannot validate physiology or physical-device behavior.

`CalibrationHistoryTests` uses real local files and Keychain with synthetic manual fixtures, and verifies backup exclusion in Simulator. Physical data-protection attributes require a device and are asserted only in device test runs. `HydrationAnalysisTests` uses the backend wire fixtures (the request fixture's source labels are adapted to the iOS manual-only boundary). `CalibrationHistoryUITests` types synthetic manual values, opts into saving, relaunches, reloads with consent off and selectively deletes without needing an external service. Run simulator tests with ad hoc signing as above; unsigned apps cannot exercise Keychain.


The separate **Detailed Muse Wonder analysis** card uses `wonder-analysis-v2`. It remains off by default on the backend (`HYDRA_WONDER_ANALYSIS_ENABLED=false`). Nothing is prepared until the user grants fresh backend-processing consent and taps **Preview detailed Muse Wonder analysis**. Every allowlisted aggregate field is displayed; exact JSON is available for review. Unknown fields, changed prediction/condition facts, unsupported result sections and incorrect cost attestations fail closed. Costs are labeled **Reference cost estimate**, separate from a verified admission quote or final invoice. The backend independently enforces account, ledger, current quote, one-in-flight and invoice-finality gates.

Only a matching preview with enabled server gates offers separate Meta consent. A request sends the exact reviewed forecast request plus preview hash and strict consent; no retry occurs. Its digest is quarantined before dispatch, including timeout, cancellation after start, malformed success and unknown server failures. Quarantine survives edits/invalidation within the controller. Only recognized pre-reservation refusals clear it; stale data requires an explicitly prepared new preview. A matching saved server result replays all eight sections for free. Muse Wonder selects and ranks supported findings, while Hydra renders every factual clause and number; the UI does not claim that Wonder authored those numbers. Native reconstruction checks every selected ID against its evidence conditions, verifies each insight and section template/text against the exact facts, and requires the fixed limitation set. The UI renders canonical local text as an additional boundary. Whole-mL amounts use outward interval bounds and locale-independent formatting; workout durations retain their supplied fractional minutes. Explanations remain transient on iPhone and are never put into manual history. A save failure is shown explicitly and the same controller does not offer another charge. Leaving the app cannot establish billing finality; that remains a backend/operator check.

`WonderAnalysisTests` covers exact request/hash/consent, default-off, saved replay, stale refusal, unknown HTTP/timeout failures, concurrent taps, malformed success and late canceled results using synthetic fixtures and fake transports. Those fixtures are not evidence of a real Meta response or billing settlement. `WorkoutFlowUITests` additionally prepares the actual detailed preview on an isolated mock backend and asserts that no live Explain button or Meta consent is available. No camera, private ledger, provider credential or live-inference configuration is changed by the client feature.

The existing personal baseline remains the default. **Experimental personal model** is an explicit, default-off research choice that routes the entire forecast, deterministic analysis and comprehensive Wonder preview/request workflow to `/v3/`. It never falls back to older HTTP endpoints on failure; the older workout-only Wonder flow is hidden for this choice because it uses a different predictor. Switching models clears results, previews and consent. The experimental stationary duration fit uses only supplied earlier manual measurements; the app labels a selected fit or the baseline fallback reason and makes no validated accuracy or interval-coverage claim. Unreported changes can make it worse. Typed native validation checks the exact learning metadata, full-precision forecast/analysis agreement and the preview's outward rounded mL projection plus explicit v3 contract marker. No fitted metadata is stored in manual history or sent in provider facts.

Inclusive timestamp checks compare `timeIntervalSinceReferenceDate` values, preserving subsecond ordering. This avoids Date's non-strict operator thunk that crashed in the separate iPhone verification build; strict/numeric comparisons and privacy/signing settings are unchanged.

`WorkoutFlowUITests.testSavedSyntheticMeasurementsFitPersonalRuntimeAgainstLocalBackend` is separately gated by `HYDRA_E2E_SAVED_CALIBRATION_RUNTIME=1`. It requires an externally prepared Simulator-only profile with six invented manual sessions and the isolated mock backend on `127.0.0.1:19998`, using the same nonsecret test connection as `CalibrationHistoryUITests`. It exercises explicit loading and fresh consent through the actual selected v3 fit, local numeric analysis and separately consented rich preview, verifies live dispatch is absent, then deletes the synthetic history through the app. It never seeds records in production code or sends an explanation request. Normal test runs skip this scenario.

Use a dedicated Simulator containing synthetic data only. Run `CalibrationHistoryUITests` first; its successful cleanup leaves one empty profile for its test connection. Capture that profile's UUID from the generated history filename. Launch the test app with `xcrun simctl launch <SIMULATOR_UUID> com.georgiosaliba.hydraai`, then run `python3 scripts/prepare_runtime_ui_fixture.py --simulator <SIMULATOR_UUID> --expected-profile <UUID_FROM_SYNTHETIC_SETUP> --confirm-synthetic-fixture` from the repository root. The caller identifies the profile from the successful setup; the helper does not infer connection identity from a random UUID or read Keychain. It requires that exact filename/envelope profile and successful app termination before rechecking that history is empty. An unconfirmed stop (including an already-stopped app), nonempty history or ambiguous history refuses the write. File attributes are preserved. The helper dates the six invented sessions relative to now and stores no processing/Meta consent. Start the isolated mock backend on port 19998 with a new beverage database and all Meta flags false, then set the opt-in flag in the UI **test runner** environment and run the selected testcase. Its final in-app deletion must pass; do not use this fixture workflow on a physical phone or a personal-data Simulator.
