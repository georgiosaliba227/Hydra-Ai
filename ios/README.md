# Hydra AI native iOS prototype

SwiftUI app connected to the local FastAPI/SQLite backend. Existing camera and HealthKit views remain on device; no images or biometric records are sent to the backend or AI. No Meta credentials or requests exist in this client.

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
