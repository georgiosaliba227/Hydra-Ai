# Milestone 2 physical iPhone testing — 2026-10-27

Status: physical camera/picker and workflow verification completed within the limits below. No live Meta requests, deployment, main changes or PR merge.

## Environment and scope

Started from a clean `codex/meta-beverage-recognition` worktree at `0eb48e1`, synchronized with its remote. Physical iPhone 17 Pro (`iPhone18,1`), iOS 27.2; paired, Developer Mode enabled and unlocked. Built, installed and launched using the existing Apple Development identity and Hydra provisioning profile, team `DH2JX3X8S9`. Team selection was a command-line build setting; no team identifier or credentials were added to project source. Existing app sandbox data was preserved during installation.

A dedicated SQLite database on the Mac contains only synthetic test logs. The backend binds to the Mac's private LAN address, uses a random runtime development credential, and explicitly sets `HYDRA_AI_MODE=mock` and `META_BILLABLE_REQUESTS_ENABLED=false`. Health response confirmed `ai_mode:mock`, `billable_requests_enabled:false`. No Meta credential is loaded or sent to iOS. The phone reaches the backend over the trusted local network.

Temporary test evidence records only UTC time, HTTP method, route, status and body byte count. No photo bytes, request bodies, tokens, prompts, personal photos or HealthKit records are logged. The extended picker test disables retained automatic/custom XCTest screenshots and selects only a newly added, identifiable synthetic fixture. Local test-result bundles remain private and must not be published without review.

## Results and evidence

| Requested check | Result / evidence |
|---|---|
| Branch / working tree | Clean at start on the requested branch; remote synchronized. Only camera/privacy copy, scoped opt-in physical tests/fixture and this report are changed. |
| Camera denial | User-assisted on this physical iPhone: user confirmed “Camera access needed” and Choose photo / Log without photo remain available. |
| Photograph beverage | User-assisted: user confirmed physical capture and preview work, Analyze is disabled before consent, and the branded mock candidate shows medium confidence. No claim of model recognition accuracy. |
| Consented physical upload | Backend observed authenticated `POST /v1/recognitions` HTTP 200, approximately 572 KB, after the assisted capture/consent sequence. No beverage was created by analysis alone. |
| Identity and capacity correction / consumed volume | Existing native physical UI test passed: corrected identity, capacity 300 mL, consumed amount 125 mL, explicit confirmation; server persisted `source:confirmed_recognition`, capacity 300, consumed 125. |
| Daily total / app restart | Existing physical UI suite passed both tests: manual entry survives relaunch without injected configuration; corrected photo entry increases total only by 125 mL. Fresh database total after those tests: 250 mL (125 manual + 125 confirmed recognition). |
| Native photo selection | Passed on this physical phone: add-only synthetic asset creation; native PhotosPicker selected its 2050-marked image; preview, consent gate and HTTP 200 upload (12,792-byte request). No personal thumbnail selected. |
| API failure / explicit recognition retry / low confidence | Passed on the phone: API-failure scenario returned HTTP 503 and actionable alert; explicit retry with generic coffee returned HTTP 200 and a low-confidence candidate. Analysis/retry did not change daily volume. |
| Network timeout / pending save / restart / idempotent retry | Passed on the phone with the Mac mock backend process paused. URLSession timed out; pending confirmation survived force-quit/relaunch; backend resumed; retry returned HTTP 200 replay after the original HTTP 201. Exactly one 125 mL “Network retry tea” record; total 375 mL across three synthetic records. Relaunch retained the 375 mL total. |
| Python backend/domain/ledger tests | 148 passed + 32 subtests; existing Starlette/httpx deprecation warning. Preserved starter suite: 3 passed from its own directory. |
| iOS unit tests | 19 passed on the physical iPhone (including 6 recognition tests); the 19 simulator tests also passed. |
| Physical UI tests | Five distinct cases passed on the connected iPhone across final per-case runs: original two workflows, native picker, API failure/retry and transport timeout/pending recovery. Intermediate harness failures are recorded below, not counted as passes. |

## Scoped fixes and test additions

Inspection found stale camera, Photos, local-network and Settings explanations claiming photos always stay on device. Those claims are wrong for consented mock-backend analysis. The installed build now accurately explains consented backend upload, disabled Meta uploads and on-device HealthKit records.

`PhysicalRecognitionTests` adds explicit opt-in physical coverage. Tests use the existing DEBUG synthetic-image button for deterministic correction/failure cases. The native-picker case creates a code-drawn bottle asset, `HYDRA_SYNTHETIC_BEVERAGE_2050.png`, with a visible 2050 date marker. It requests **add-only**, never broad photo-library read access, and does not enumerate personal assets. The fixture creation button requires `HYDRA_TEST_LIBRARY_FIXTURE=1` in a DEBUG build; helper code and its add-only usage description are absent from Release configuration. Test assets can remain in Photos; remove the identifiable synthetic 2050 entries manually if no longer needed. No existing photos are deleted or modified.

For the network test, the Mac-side test driver watches explicit stdout markers and pauses/resumes only the dedicated mock backend process. No fault-control HTTP endpoint is present in the app or backend and no provider is invoked. The test must observe a transport timeout, a durable pending mutation after app relaunch, and exactly one 125 mL contribution after retry. The driver has a finalizer that resumes the backend on test failure.

The first extended run exposed test harness issues: a coordinate tap missed off-screen consent, and an async UI-test launch ran off the main thread. Test helpers now scroll/use the native consent action, assert Analyze is enabled and use synchronous native UI-test operations. An initial HTTP-based fault controller was also blocked by the UI runner’s local-network privacy permission; the Mac-side stdout driver avoids requesting that extra permission. The network test uses synchronous XCTest UI operations with verified tab transitions. These initial failures are not reported as passing app behavior.

## Limits

Camera aiming/capture and denial are user-assisted confirmations, not automated shutter tests. Real recognition, calibrated confidence, physical volume accuracy, nutritional completeness and scientific hydration validity are not validated by mock tests. No biometrics or raw HealthKit records are transmitted. Background/locked-device recovery, offline iCloud-only originals, large/unsupported photos, rotation/accessibility variations, camera revocation during an active capture and interrupted OS picker downloads need separate coverage. Synthetic fixture upload does not prove a photo was interpreted by Meta; the mock deliberately does not inspect pixels.

## Reproduction and handoff

Physical builds used `xcodebuild -project ios/HydraAI.xcodeproj -scheme HydraAI` / `HydraAIEndToEnd`, Debug, the connected physical iOS destination, `DEVELOPMENT_TEAM=DH2JX3X8S9` and `-allowProvisioningUpdates`. No ad-hoc simulator identity was used for physical-device installation. Unit tests run with the signed physical `HydraAI_iphoneos27.0-arm64.xctestrun`; UI tests use the corresponding signed `HydraAIEndToEnd` run configuration. Credentials are inserted into private mode-0600 runtime test configurations, never command-line literals/source, and those temporary test configurations are removed after each run.

Original UI cases use `HYDRA_E2E_BACKEND_URL` and `HYDRA_E2E_API_TOKEN`. Extended cases additionally require `HYDRA_E2E_PHYSICAL_EXTRAS=1`. The picker helper requires the DEBUG-only `HYDRA_TEST_LIBRARY_FIXTURE=1` launch flag. The pending-network test requires `HYDRA_E2E_FAULT_DRIVER=stdout-v1`: a Mac-side driver must watch `HYDRA_PHYSICAL_PAUSE_BACKEND_V1` / `HYDRA_PHYSICAL_RESUME_BACKEND_V1`, signal only its own dedicated mock backend and always resume it in a finalizer. Without explicit flags these cases skip; no production fault-control route is added. The executed local driver is `/tmp/hydra-m2-physical-session/run_ui.py`; its private runtime configuration/result bundles are intentionally not committed. Never use a real/shared backend for this fault test.

The test backend is resumed and available for continued synthetic local testing. The temporary HTTP control listener was stopped after being replaced with stdout control. No live Meta transport is enabled, no PR is merged, and main remains unchanged. Only the permission/settings copy correction, opt-in DEBUG test fixture, physical UI tests and verification documentation are included in this change.
