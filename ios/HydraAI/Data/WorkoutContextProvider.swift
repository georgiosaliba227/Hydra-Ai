import Foundation

/// Suggested values for the planned-workout form. Every field is a suggestion the user reviews and can edit;
/// nil means "leave the form field as it is".
struct WorkoutContextDraft: Equatable {
    /// One of `WorkoutForecastActivity` raw values: running, cycling, walking, strength, other.
    var activity: String?
    var startsAt: Date?
    /// Whole minutes.
    var durationMinutes: Double?
    var temperatureC: Double?
    var humidityPercent: Double?
    /// Display only. Never sent with a forecast request and never used as a hydration or dehydration signal.
    var averageHeartRate: Double?
    /// Display only. Never sent with a forecast request.
    var activeEnergyKilocalories: Double?
    /// For example "From your Apple Health workout on Oct 27, 2026 at 7:10 AM".
    var workoutProvenance: String?
    /// "Weather from Open-Meteo for your area".
    var weatherProvenance: String?
    /// The requested planned-workout time and actual forecast hour; current-area weather is separate.
    var weatherRequestedTime: Date?
    var weatherForecastHour: Date?
    /// Set when the Health activity type had no direct match and Other was used.
    var activityNote: String?
    var typicalSessions: TypicalWorkoutSessions?

    var provenance: [String] { [workoutProvenance, weatherProvenance].compactMap { $0 } }
}

/// Prefills the workout forecast form from Apple Health (on device) and, with consent, Open-Meteo.
/// Health records stay on device; only a rounded coordinate is sent to Open-Meteo, and only with consent.
@MainActor
final class WorkoutContextProvider: ObservableObject {
    static let heartRateContextNote = "Heart rate is shown for context only. Hydra never uses it to judge hydration or dehydration."
    static let weatherProvenanceText = "Weather from Open-Meteo for your area"
    static let sampleWorkoutProvenancePrefix = "Sample workout (not your data) on "
    static let healthWorkoutProvenancePrefix = "From your Apple Health workout on "
    /// How many recent workouts feed "Use my last workout" and the typical-session summary.
    static let recentWorkoutLimit = 20

    @Published private(set) var draft = WorkoutContextDraft()
    @Published private(set) var workoutState: LoadState = .idle
    @Published private(set) var weatherState: LoadState = .idle
    @Published private(set) var isWeatherConsentGranted: Bool

    private let health: any HealthWorkoutClient
    private let weather: WeatherAutofillService
    private let calendar: Calendar
    private let now: () -> Date
    private var workoutGeneration = UUID()
    private var weatherGeneration = UUID()

    init(health: any HealthWorkoutClient, weather: WeatherAutofillService,
         calendar: Calendar = .current, now: @escaping () -> Date = { .now }) {
        self.health = health
        self.weather = weather
        self.calendar = calendar
        self.now = now
        self.isWeatherConsentGranted = weather.consent.isGranted
    }

    /// Real Apple Health and Open-Meteo. In DEBUG, the launch environment `HYDRA_SAMPLE_HEALTH_WORKOUTS=1`
    /// substitutes labeled sample workouts for the Simulator, which has no Health workouts.
    static func live() -> WorkoutContextProvider {
        var health: any HealthWorkoutClient = HealthKitWorkoutClient()
        #if DEBUG
        if ProcessInfo.processInfo.environment["HYDRA_SAMPLE_HEALTH_WORKOUTS"] == "1" {
            health = SampleHealthWorkoutClient()
        }
        #endif
        return WorkoutContextProvider(health: health, weather: WeatherAutofillService())
    }

    var isHealthAvailable: Bool { health.isAvailable }

    /// "Use my last workout". Call from a button tap: it may show the Health permission sheet.
    /// Fills activity, duration (and start time of day unless `plannedStart` is given), heart rate and
    /// energy for display, provenance and the typical-session summary. Errors land in `workoutState`.
    @discardableResult
    func useLastWorkout(plannedStart: Date? = nil) async -> WorkoutContextDraft {
        await refreshWorkouts(requestAuthorization: true, plannedStart: plannedStart)
        return draft
    }

    /// Existing Health access only by default. The daily coordinator never requests read permission.
    @discardableResult
    func refreshWorkouts(requestAuthorization: Bool = false, plannedStart: Date? = nil) async -> Bool {
        let generation = UUID()
        workoutGeneration = generation
        workoutState = .loading
        return await withTaskCancellationHandler {
            defer {
                if Task.isCancelled { cancelWorkout(ifCurrent: generation) }
            }
            do {
                try Task.checkCancellation()
                if requestAuthorization { try await health.requestWorkoutReadAccess() }
                try Task.checkCancellation()
                let workouts = try await health.recentWorkouts(limit: Self.recentWorkoutLimit)
                guard generation == workoutGeneration, !Task.isCancelled else { return false }
                guard let last = workouts.first else { throw HealthWorkoutError.noWorkouts }
                draft.activity = last.activity.rawValue
                draft.activityNote = last.mapping.note
                draft.durationMinutes = max(1, last.durationMinutes.rounded())
                draft.startsAt = plannedStart ?? nextOccurrence(ofTimeOfDayOf: last.startDate)
                draft.averageHeartRate = last.averageHeartRateBPM.map { $0.rounded() }
                draft.activeEnergyKilocalories = last.activeEnergyKilocalories.map { $0.rounded() }
                let when = last.startDate.formatted(date: .abbreviated, time: .shortened)
                draft.workoutProvenance = (last.source == .sample ? Self.sampleWorkoutProvenancePrefix : Self.healthWorkoutProvenancePrefix) + when
                draft.typicalSessions = TypicalWorkoutSessions.summarize(workouts)
                workoutState = .loaded
                return true
            } catch {
                guard generation == workoutGeneration, !Task.isCancelled else { return false }
                // Read denial is indistinguishable from no workouts. Do not retain private
                // suggestions when a subsequent read returns empty; other failures stay stale.
                if (error as? HealthWorkoutError) == .noWorkouts { clearHealthContext() }
                workoutState = .failed((error as? LocalizedError)?.errorDescription
                    ?? "Apple Health workouts could not be read. You can still enter the workout yourself.")
            }
            return false
        } onCancel: {
            // HealthKit may not return promptly after cancellation. Release the button now,
            // but never reset a newer read that has since taken ownership of this provider.
            Task { @MainActor [weak self] in self?.cancelWorkout(ifCurrent: generation) }
        }
    }

    private func cancelWorkout(ifCurrent generation: UUID) {
        guard generation == workoutGeneration else { return }
        cancelPendingWorkouts()
    }

    /// "Fill in the weather". Requires `isWeatherConsentGranted`; otherwise nothing is requested and
    /// `weatherState` explains why. Uses the hour nearest `startsAt` (default: the draft's start, else now).
    @discardableResult
    func fillInWeather(startsAt: Date? = nil) async -> WorkoutContextDraft {
        let generation = UUID()
        weatherGeneration = generation
        weatherState = .loading
        do {
            let requestedTime = startsAt ?? draft.startsAt ?? now()
            let conditions = try await weather.conditions(nearest: requestedTime)
            guard abs(conditions.forecastHour.timeIntervalSince(requestedTime)) <= OpenMeteoForecastParser.maximumDistance else {
                throw WeatherAutofillError.outOfForecastRange
            }
            guard generation == weatherGeneration, weather.consent.isGranted else { return draft }
            draft.temperatureC = conditions.temperatureC
            draft.humidityPercent = conditions.humidityPercent
            draft.weatherProvenance = Self.weatherProvenanceText
            draft.weatherRequestedTime = requestedTime
            draft.weatherForecastHour = conditions.forecastHour
            weatherState = .loaded
        } catch {
            guard generation == weatherGeneration else { return draft }
            weatherState = .failed((error as? LocalizedError)?.errorDescription
                ?? WeatherAutofillError.unavailable.errorDescription!)
        }
        return draft
    }

    /// Backs the "Use my location to fill in the weather" toggle. Turning it off cancels a pending lookup
    /// and clears weather values that came from Open-Meteo.
    func setWeatherConsent(_ granted: Bool) {
        weather.consent.isGranted = granted
        isWeatherConsentGranted = granted
        if !granted {
            weatherGeneration = UUID()
            weatherState = .idle
            if draft.weatherProvenance != nil {
                draft.temperatureC = nil
                draft.humidityPercent = nil
                draft.weatherProvenance = nil
                draft.weatherRequestedTime = nil
                draft.weatherForecastHour = nil
            }
        }
    }

    /// Invalidate weather provenance when a planned start changes; late replies cannot restore it.
    func invalidateWeather(for startsAt: Date) {
        // A matching cached hour may coexist with a pending request for another start.
        // Invalidate that reply before deciding whether the cached values can be retained.
        weatherGeneration = UUID()
        guard draft.weatherRequestedTime != startsAt else {
            if weatherState == .loading { weatherState = .loaded }
            return
        }
        draft.temperatureC = nil
        draft.humidityPercent = nil
        draft.weatherProvenance = nil
        draft.weatherRequestedTime = nil
        draft.weatherForecastHour = nil
        weatherState = .idle
    }

    func cancelPendingWorkouts() {
        workoutGeneration = UUID()
        if workoutState == .loading { workoutState = .idle }
    }

    func clearHealthContext() {
        cancelPendingWorkouts()
        draft.activity = nil
        draft.startsAt = nil
        draft.durationMinutes = nil
        draft.averageHeartRate = nil
        draft.activeEnergyKilocalories = nil
        draft.workoutProvenance = nil
        draft.activityNote = nil
        draft.typicalSessions = nil
        workoutState = .idle
    }

    /// Forget all suggestions (for example when leaving the screen). Late replies are discarded.
    func clear() {
        workoutGeneration = UUID()
        weatherGeneration = UUID()
        draft = WorkoutContextDraft()
        workoutState = .idle
        weatherState = .idle
    }

    /// The same local clock time as `date`, on the first day it is still in the future.
    func nextOccurrence(ofTimeOfDayOf date: Date) -> Date {
        let current = now()
        let parts = calendar.dateComponents([.hour, .minute], from: date)
        guard let candidate = calendar.nextDate(after: current, matching: parts, matchingPolicy: .nextTime) else {
            return current.addingTimeInterval(3600)
        }
        return candidate
    }
}
