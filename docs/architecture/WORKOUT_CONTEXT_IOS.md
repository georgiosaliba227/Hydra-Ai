# Workout context prefill (iOS)

Additive iOS contract, October 29, 2026. Status: data layer **implemented and
unit-tested**; no screen calls it yet. The workout forecast contract
(`WORKOUT_MODEL_API.md`) and request encoding are unchanged.

The workout forecast form can be prefilled from two sources instead of typing:

1. **Apple Health workouts**, read and summarized on device only.
2. **Weather** from the free Open-Meteo forecast API, only after an explicit,
   stored user consent, using a coordinate rounded to two decimals.

Every prefilled value is a suggestion shown in the editable form. The user reviews
it before requesting an estimate.

## API for the UI

Files: `ios/HydraAI/Data/WorkoutContextProvider.swift`,
`ios/HydraAI/Data/WeatherAutofill.swift`, `ios/HydraAI/Health/HealthWorkoutClient.swift`.

```swift
@MainActor final class WorkoutContextProvider: ObservableObject {
    static func live() -> WorkoutContextProvider        // real Health + CoreLocation + Open-Meteo
    init(health: any HealthWorkoutClient, weather: WeatherAutofillService,
         calendar: Calendar = .current, now: @escaping () -> Date = { .now })

    @Published private(set) var draft: WorkoutContextDraft
    @Published private(set) var workoutState: LoadState  // .idle/.loading/.loaded/.failed(message)
    @Published private(set) var weatherState: LoadState
    @Published private(set) var isWeatherConsentGranted: Bool
    var isHealthAvailable: Bool

    @discardableResult func useLastWorkout(plannedStart: Date? = nil) async -> WorkoutContextDraft
    @discardableResult func fillInWeather(startsAt: Date? = nil) async -> WorkoutContextDraft
    func setWeatherConsent(_ granted: Bool)   // "Use my location to fill in the weather"
    func clear()

    static let heartRateContextNote: String
}

struct WorkoutContextDraft: Equatable {
    var activity: String?            // running | cycling | walking | strength | other
    var startsAt: Date?
    var durationMinutes: Double?     // whole minutes
    var temperatureC: Double?        // one decimal
    var humidityPercent: Double?     // whole percent
    var averageHeartRate: Double?    // bpm, display only
    var activeEnergyKilocalories: Double?  // display only
    var workoutProvenance: String?   // "From your Apple Health workout on Oct 27, 2026 at 7:10 AM"
    var weatherProvenance: String?   // "Weather from Open-Meteo for your area"
    var activityNote: String?        // set when Other was used for an unmatched Health type
    var typicalSessions: TypicalWorkoutSessions?
    var provenance: [String]
}
```

Suggested wiring (one call per button; copy only non-nil fields into the form):

```swift
@StateObject private var context = WorkoutContextProvider.live()

Button("Use my last workout") { Task {
    let d = await context.useLastWorkout()
    if let a = d.activity { draft.activity = a }
    if let m = d.durationMinutes { draft.duration = String(Int(m)) }
    if let s = d.startsAt { draft.startsAt = s }
} }
Toggle("Use my location to fill in the weather",
       isOn: Binding(get: { context.isWeatherConsentGranted }, set: context.setWeatherConsent))
Button("Fill in the weather") { Task {
    let d = await context.fillInWeather(startsAt: draft.startsAt)
    if let t = d.temperatureC { draft.temperature = String(t) }
    if let h = d.humidityPercent { draft.humidity = String(Int(h)) }
} }.disabled(!context.isWeatherConsentGranted)
```

The current form parses text with `Double(_:)`, so use `String(_:)`, not locale-formatted text. Show `workoutState`/`weatherState` failure messages. Each one tells the user they
can enter the value manually. Show the provenance strings and `activityNote` next
to the prefilled fields. If heart rate is shown, show `heartRateContextNote` with it.
Call `clear()` when leaving the screen. Late replies after `clear()` or after
consent is withdrawn are discarded.

Lower-level pieces, for tests or custom flows:

- `protocol HealthWorkoutClient` with `isAvailable`, `requestWorkoutReadAccess()`
  and `recentWorkouts(limit:) -> [HealthWorkoutSummary]` (most recent first,
  limit clamped to 1...50). The extension method `typicalSessions(limit:)` builds
  the summary from them. Implementations: `HealthKitWorkoutClient` (real) and
  `SampleHealthWorkoutClient` (labeled sample data, no HealthKit calls).
- `TypicalWorkoutSessions.summarize(_:)` returns `sessionCount`,
  `medianDurationMinutes`, `mostCommonActivity`, `mostCommonActivityCount`,
  `earliestStart`, `latestStart` and `displayText`. Ties go to the activity
  done most recently.
- `WorkoutActivityMapping.map(_ HKWorkoutActivityType)`.
- `WeatherAutofillService.conditions(nearest:)`, `OpenMeteoWeatherClient`,
  `OpenMeteoForecastParser.nearestHour(in:to:coordinate:)`, `RoundedCoordinate`,
  `WeatherLocationConsentStore`, `protocol ApproximateLocationProvider`.

### Activity mapping

| Apple Health type | Forecast `activity` |
| --- | --- |
| Running | `running` |
| Cycling | `cycling` |
| Walking, Hiking | `walking` |
| Traditional / Functional strength training | `strength` |
| Anything else, including types added in future SDKs | `other`, with `isDirectMatch = false` and an `activityNote` |

`other` is the safe default because the backend always accepts it. Intensity is
**not** prefilled. It is not inferred from heart rate or energy; the user picks it.

### Start time

`useLastWorkout()` suggests the next future occurrence of the last workout's local
time of day, for example tomorrow at 07:30. Pass `plannedStart` to keep the form's
current start instead.

## Privacy behavior and what leaves the device

| Data | Where it goes |
| --- | --- |
| Workout type, start, duration, active energy, average heart rate | Read on device. Held in memory only. Not persisted, logged or uploaded. |
| Typical-session summary | Computed on device from the last 20 workouts. Not uploaded. |
| Average heart rate, active energy | Display only. Not part of `WorkoutForecastRequest`. Never used as a hydration or dehydration signal. |
| Activity and duration the user keeps in the form | Sent to the user's own Hydra backend only when they request an estimate, as manually confirmed planned values (`duration_source = "manual"`). Raw Health samples and the past workout's dates are never sent. |
| Rounded coordinate (2 decimals, about 1 km) | Sent to `api.open-meteo.com` only when consent is on and the user taps "Fill in the weather". Not stored, and not sent to Hydra or Meta. |
| Temperature and humidity | Received from Open-Meteo. Stay in the form until the user submits; then they go to the Hydra backend as ordinary form values. |

- **Health permission.** `requestWorkoutReadAccess()` asks only for read access to
  workouts, active energy and heart rate. Nothing is written. It is called only from
  `useLastWorkout()`, which should run only from a button tap. iOS does not reveal
  read denial, so a denial looks the same as having no workouts (`noWorkouts`).
- **Weather consent.** `WeatherLocationConsentStore` (UserDefaults key
  `hydra.weatherLocationConsent`) defaults to **off**. Without it,
  `WeatherAutofillService` throws `consentRequired` before any location request or
  network call. Consent is checked again after the location fix. Turning consent off
  cancels a pending lookup and clears values that came from Open-Meteo.
- **Location.** `CoreLocationApproximateLocationProvider` asks for when-in-use
  permission and makes one `requestLocation()` call with
  `kCLLocationAccuracyReduced`. It does not track location continuously.
  `NSLocationDefaultAccuracyReduced` is set in `ios/Configuration/Info.plist`, so iOS
  offers approximate location only.
- **Open-Meteo request.** The request is a single GET to
  `https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&hourly=temperature_2m,relative_humidity_2m&timezone=auto&timeformat=unixtime`.
  It uses an ephemeral session with no cookies, no cache, no credentials and no
  app identifiers. `timeformat=unixtime` adds absolute hour timestamps, so local times
  never have to be parsed across a daylight-saving change.
- **Hour selection.** The service uses the forecast hour nearest the planned start
  that has both values. An exact tie goes to the earlier hour. A start more than 90
  minutes from every returned hour throws `outOfForecastRange`. Open-Meteo's default
  window is today plus 6 days.
- **Validation.** Responses larger than 512 KiB, mismatched arrays, a host other
  than `api.open-meteo.com`, a temperature outside -60...60 °C or humidity outside
  0...100 % all throw `invalidResponse`.
- **Failures.** The service maps failures to `WeatherAutofillError`: `offline`,
  `locationDenied`, `locationUnavailable`, `outOfForecastRange` (also used for HTTP
  400), `unavailable` and `invalidResponse`. Every message falls back to manual
  entry, and no values are invented.

Usage strings (`INFOPLIST_KEY_*` build settings in `project.pbxproj`):
`NSHealthShareUsageDescription` (extended to workouts, active energy and heart rate)
and `NSLocationWhenInUseUsageDescription` (names Open-Meteo and the 1 km rounding).

## Simulator and testing

The Simulator has no Health workouts. Use one of these:

- Add sample workouts in the Simulator's Health app.
- In a DEBUG build, launch with the environment variable
  `HYDRA_SAMPLE_HEALTH_WORKOUTS=1`. With `simctl launch`, use
  `SIMCTL_CHILD_HYDRA_SAMPLE_HEALTH_WORKOUTS=1`. `live()` then uses
  `SampleHealthWorkoutClient`, and its provenance reads
  "Sample workout (not your data) on …".

To test weather in the Simulator, set Features → Location in the Simulator. That is
a real Open-Meteo request, so it needs consent and network access.

`ios/HydraAITests/WorkoutContextTests.swift` covers activity mapping (every raw
type maps to an accepted value), the typical-session median, mode and ties,
coordinate rounding and the URL query, nearest-hour parsing from a fixture,
out-of-range and invalid payloads, consent gating with zero location and network
calls, withdrawn consent, the offline, HTTP, denied and invalid error mapping, the
prefill draft and provenance, sample labeling, and the minimal HealthKit read set.
The tests use `FixtureURLProtocol` stubs and make no real network calls.

Not verified: real HealthKit reads on a physical iPhone or Apple Watch, the
`HKStatisticsQueryDescriptor` heart-rate fallback, real CoreLocation prompts, and
live Open-Meteo responses.

Open policy question: the backend rejects `duration_source = "wearable_aggregate"`
until a separate policy review. A duration suggested from Health is sent as a
user-confirmed manual planned value. Human reviewers should confirm that this
counts as user-confirmed manual input.
