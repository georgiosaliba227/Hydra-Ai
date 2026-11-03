# Physical hydration milestone verification

## US units and automatic-context update

The reviewed update at `1ef152d` was installed over the original bundle and
launched without connection environment overrides. Strict signature verification,
HealthKit entitlement, profile expiry and inclusion of the paired iPhone were
checked. No uninstall/reset was issued. The owner then reported **Both update
successfully in US units** after choosing the new optional Health and automatic-
weather setup. This is owner-assisted evidence, with no health/weather values
requested in chat.

An additional physical UI test passed in **25.567 seconds**, zero failures:
`testSavedOwnerConnectionReportsReadinessWithoutInjectedCredentials`. It launched
with an empty app environment, used the saved URL/Keychain (no Save connection),
and verified the owner backend's ready/unverified-billing state. The financial
ledger was byte-identical across the test. No paid action or screenshot was
requested. The app was reopened normally afterward.

Private receipts: `us-context-app-install.json`, `us-context-app-launch.json`,
`us-context-install-summary.json`, and
`us-context-physical-saved-ready-verification.json` with its result bundle/log.
See the [feature report](US_UNITS_DAILY_CONTEXT_2026-11-03.md) for 217 native tests
and six Simulator UI flows. No unattended daily OS background delivery, real
calibration history or actual own-record Meta result is claimed by these checks.

## Latest continuation — original app installed and connected

The owner later resumed physical checks and unlocked the connected iPhone 17 Pro
(iOS 27.2). The complete original `com.georgiosaliba.hydraai` app was installed
and launched successfully, with HealthKit entitlement intact and strict signature
verification passing. The build uses the cached development profile for team
`DH2JX3X8S9`; no repository signing identifiers or entitlements were changed.
This supersedes the earlier installation-deferred status below.

One actual physical UI test passed in **21.620 seconds**, with zero failures:
`WonderReadinessUITests.testReadyOwnerRiskStatusStillDisclosesUnverifiedBillingWithoutDispatch`.
It saved the owner backend connection, reached that backend from the phone,
verified **Ready for a previewed, consented request**, checked the unverified-final-
billing/token-only warning, and verified that Home asks for the owner's own goal
instead of inventing one. No paid action was tapped, and financial ledger bytes
were identical before and after the run. The first attempt failed before test
initialization with LocalAuthentication cancellation while the phone was locked;
the passing run followed the owner's explicit unlock, with no app-code change.

The Mac's LAN address changed during the pause. The existing owner backend was
restarted on the current interface, and genuinely observed account/pricing
evidence was renewed using the existing standing waiver. Historical attempts,
holds and finality values remain unchanged. No new provider request was made in
this physical connection check. The app was then reopened without injected
connection environment variables for owner-assisted HealthKit/weather checks.
Connection persistence after that normal launch is not yet independently checked.

The original bundle was updated without an uninstall or data reset. Its reported
data-container absolute path changed across installation; this alone does not
prove data loss. Apple documents container-path changes across updates and
preservation of Documents/Library excluding Caches in
[TN2285](https://developer.apple.com/library/archive/technotes/tn2285/_index.html).
No pre-update content inventory exists, so byte-for-byte preservation of personal
files is not claimed. Raw personal files were not copied to the Mac for this check.

Private local evidence is retained under the owner-only operational directory:
`physical-full-app-install.json`, `physical-full-app-launch.json`,
`physical-ready-native-verification.json` (failed initialization), and
`physical-ready-unlocked-native-verification.json` plus its `.xcresult` and log
(passing run). Device diagnostics and screenshots are not committed or uploaded.

The owner then completed the permission choices on the phone and reported
**A real workout imports**. For the consented location/Open-Meteo check the owner
reported that everything fills. These are **owner-assisted hardware outcomes**,
separate from the automated connection test; no workout values, weather values
or location were requested in chat or copied for the report. The owner requested
US units and first-use setup with subsequent automatic context updates.

Still unverified: populated Home score, final personal forecast/analysis screens,
normal-launch backend connection persistence, and the actual own-record Meta
preview/consent/result/replay flow. No real calibration measurements have been
substituted with simulated training records. A future units/setup build needs
its own post-change verification; these outcomes apply to the installed milestone.

## Earlier signing-only continuation

Later November 3 continuation: the original app identifier's cached development
profile was found to include HealthKit and the paired phone. The complete updated
app successfully built using automatic signing and that profile, without removing
HealthKit. Its signature and entitlement were verified locally. The phone was
unreachable, and the owner explicitly chose Simulator, so this adds signed-build
evidence only. No installation, real HealthKit/workout import, location/weather
lookup or final physical UI pass is claimed. The earlier separate-bundle report
below retains its original scope.

Executed November 3, 2026 on the connected iPhone 17 Pro, iOS 27.2, using Xcode
27.2. This is scoped physical evidence, not a claim that the final v3 runtime
workflow or HealthKit permissions passed on hardware.

## Isolated test installation and signing

The original installed Hydra app and sandbox were preserved. Tracked iOS sources
from `d73584f` (the `8186caa` rich-analysis milestone plus documentation) were copied
to a private temporary directory. Only that copy used a separate
`com.georgiosaliba.hydraai.hydrationverify` identifier and “Hydra Verify” display
name. No repository identifier, credential, entitlement or provisioning setting
was changed for signing.

The available local wildcard development profile lacked HealthKit, and Xcode had
no account available to provision the new identifier with that capability. The
first build failed for those explicit reasons. The temporary copy then omitted
the HealthKit entitlement, keeping the repository entitlement intact. No real
HealthKit authorization/read, photo access, location lookup, Meta dispatch or
personal-record upload was attempted. This installation therefore cannot verify
the production HealthKit signing/permission path.

## Reproduced physical crash and correction experiment

The initial physical unit run passed 33 tests and recorded 22 failures before it
was interrupted. Crash reports repeatedly reported `CODESIGNING / Invalid Page`
with program counter zero at non-strict `Date` comparison sites, including
pre-existing beverage validation and new history validation. The local app passed
`codesign --verify --deep --strict`. The report alone does not establish the
underlying SDK or OS defect.

A four-case temporary probe isolated the behavior on this device/build:

| Operation | Result |
| --- | --- |
| ISO8601 parsing and expected timestamp | Pass |
| `Date < Date` | Pass |
| `Date <= Date` | Reproduced crash |
| Numeric timestamp `<=` | Pass |

A second independent crash located `Date >=` in beverage validation. In the
temporary app only, direct non-strict date comparisons were replaced with
comparisons of `timeIntervalSinceReferenceDate`. This preserves reference-time
precision without adding an epoch offset. Numeric comparisons, calculation
rules, consent and validation bounds were unchanged.

The complete **132 XCTest passed, zero failures**, on the physical phone with
that correction. This includes the actual-device assertion of complete file
protection and backup exclusion for saved manual history. The run took 0.401
seconds in test cases; overall launch time included waiting for the user to
unlock the phone. The standalone deliberately crashing probe was not included
in the green suite.

## Evidence and limits

Local evidence, retained outside Git:

- `/tmp/hydra-intelligence-physical-session/unit-results-initial-interrupted.xcresult`
- `/tmp/hydra-intelligence-physical-session/unit-results-date-probe-red.xcresult`
- `/tmp/hydra-intelligence-physical-session/unit-results.xcresult`
- `/tmp/hydra-intelligence-physical-session/unit-date-workaround.log`
- Private crash reports and the temporary source copy in the same directory.

The user then requested Xcode Simulator for remaining tests while going to sleep.
No physical UI workflow or final v3 runtime run is claimed. The date correction
is integrated into the maintained native code with equality/subsecond boundary
coverage. Final verification passed 145 Simulator unit tests and three actual mock
UI flows, including a selected fit from six saved synthetic records through the
real backend, matching analysis/preview and in-app deletion. These later checks
used Simulator and do not expand the hardware scope above. The temporary physical backend
was stopped after this check. Device diagnostics remain private; nothing was
sent to a provider or posted to GitHub.
