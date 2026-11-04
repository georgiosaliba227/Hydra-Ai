# Hydra AI native iOS prototype

Camera analysis now opens a compact **Confirm / Edit** review with the drink and
supported liquid-volume estimate. It defaults to the user's assumption that all
the liquid is consumed; inference alone never logs a drink. Edit offers name/type,
volume presets, mL/US fl oz/L, and partial-amount entry. Unknown fill is not silently
replaced by capacity; a full-container amount requires an explicit choice. Corrections can
be remembered personally, while original Muse suggestions remain labeled. A
separate default-off training option stages the selected photo and corrections
on the user's backend for reviewed future training. It does not retrain Muse
automatically. Export/Delete all include these records and opted-in photos.
See [the correction contract](../docs/architecture/CAMERA_CORRECTIONS_API.md).

Inclusive date validation uses `DateBoundary` with finite timestamps. This avoids
the missing weak-linked Date >=/<= calls reproduced on the physical iOS 27.2
device, including during save and history refresh, without changing date limits.

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

See [Milestone 2](../docs/MILESTONE_2.md) and the current [camera contract](../docs/architecture/CAMERA_CORRECTIONS_API.md). Configure the local backend, open Camera, capture/select a photo, consent to backend upload and choose an explicitly synthetic demo scenario. Analyze opens Confirm/Edit. Confirm logs the displayed volume under the stated assumption; Edit changes name/type, volume/unit or partial consumption. Meta inference stays disabled. Unknown nutrition stays unknown. A failed confirmation uses the existing Today retry action with its persisted request/key.

## Guarded Meta mode

Camera fetches authenticated recognition capabilities and fails closed if mode cannot be verified. Meta mode requires both backend-upload consent and separate Meta disclosure consent. It never claims zero retention. Live results require a server-issued successful-recognition receipt, preserved in pending submissions, and confirmation of name/type and volume. That receipt does not imply billing finality. Assumed whole-liquid/full-container consumption is labeled in history; unknown capacity stays unknown. All provider credentials remain on the server. Mock is the default; no live spend is authorized. See [budget controls](../docs/API_BUDGET.md).

`run_ios_e2e.py --live-simulation` only accepts an explicitly marked nonbillable loopback fake-provider backend. It runs the opt-in live-consent UI case with generated synthetic image data. It must never be pointed at a real Meta transport. Physical-only tests skip in normal simulator runs.

If Xcode hangs after passing simulator tests while collecting verbose diagnostics, `--skip-simulator-diagnostics` adds `-collect-test-diagnostics never`. Assertions and result bundles remain enabled; the flag is refused for physical destinations. `run_live_simulation.py` forwards this optional switch.

## Simpler Insights and workouts

Today keeps logging and recent drinks together, with one **Explore insights** link.
Insights offers three compact rows: Your trends, Plan a workout, and Ask Hydra.
The previous-seven-days range and missing-log coverage now live under Logging
details in History, keeping the drink list easy to reach.

Workout uses **Your workout → Conditions → Review & estimate**. Back/Edit retain
the draft; leaving the flow or changing connection clears the session. Personal
estimates require comparable measured workouts and explicit processing consent.
**Past measurements** opens the full measured-workout form separately, including
all required instrument error bounds. Unknown measurements stay blank. A disabled
estimate action explains the missing prerequisite before any request is made.

**Try a demo instead** opens an independent simulated example. Its result is
labeled simulated and never changes confirmed consumption or the personal draft.
Recorded Muse explanations and research comparisons are available inside the demo,
with their recorded/mock labels. Model/provenance details stay collapsed; the result
always shows units, the returned range, essential uncertainty, and that it is not
a drinking target. No new inference or HealthKit integrations are enabled.

Your trends leads with any saved explanation and its own date window, then the
first complete insight. More insights and Sources & details reveal the rest.
**Review data & explain** opens a separate sheet with weekly totals and a complete
14-day summary. It includes all daily totals/counts, categories, timing, goal and
timezone; the exact typed data payload is also available. The Meta recipient,
selected account, maximum cost, default-off consent and send action stay together.
Opening/dismissing never sends; reopening or changing connection resets consent.
A mock backend offers no live send action. Existing server billing and validation
gates are unchanged, and no request is automatically retried.

Ask Hydra shows three common questions. **All questions**, **Answer options**, and
per-answer **Sources** reveal supporting choices. Recorded mode remains visibly
labeled and cannot include today's total or submit a free-text question. Reviewed
answer wording, urgent instructions, and essential limitations remain intact.

### UI verification fixture

`SimplerInsightsUITests` uses the existing opt-in loopback setup. Additional
`TrendsConsentUITests` requires `HYDRA_E2E_REVIEW_BACKEND_URL` pointing to
`scripts/insights_review_fixture.py`. This fixture always creates a disposable
synthetic database, forces mock mode, and rejects every trends POST before it can
reach provider code. It only exposes a fake capability so the native consent UI
can be checked. It is never a live backend and must not receive a provider key.

Run it with the backend test environment and a mode-0600 JSON file containing a
random **local test** token in its `token` field:

```sh
PYTHONPATH=. python scripts/insights_review_fixture.py --token-file /private/path/test-token.json
```

Pass that same token as `HYDRA_E2E_API_TOKEN` in a private UI `.xctestrun` file.
The consent test checks the fixture's explicit nonbillable identity before launch,
then verifies that opening, toggling consent, closing and reopening create no send
attempt and leave consent off. No tokens or populated test-run files are committed.

Simulator checks do not establish scientific accuracy or physical-device behavior.
