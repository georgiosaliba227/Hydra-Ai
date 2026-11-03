# Physical hydration milestone verification

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
is being integrated into the maintained native code with equality/subsecond
boundary coverage and full simulator verification. The temporary physical backend
was stopped after this check. Device diagnostics remain private; nothing was
sent to a provider or posted to GitHub.
