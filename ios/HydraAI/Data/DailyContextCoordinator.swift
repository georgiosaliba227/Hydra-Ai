import Foundation

enum DailyContextRefreshMode { case foreground, background }

/// Consent-first on-device context. It never uploads Health, logs drinks, or calls Meta.
@MainActor
final class DailyContextCoordinator: ObservableObject {
    let workoutContext: WorkoutContextProvider
    @Published private(set) var setupCompleted: Bool
    @Published private(set) var healthAutoEnabled: Bool
    @Published private(set) var weatherAutoEnabled: Bool
    @Published private(set) var healthState: LoadState = .idle
    @Published private(set) var weatherState: LoadState = .idle
    @Published private(set) var lastHealthSuccess: Date?
    @Published private(set) var lastWeatherSuccess: Date?
    @Published private(set) var lastHealthAttempt: Date?
    @Published private(set) var lastWeatherAttempt: Date?
    @Published private(set) var currentWeather: WeatherConditions?
    @Published private(set) var isRefreshing = false

    private let preferences: DailyContextPreferences
    private let location: any ApproximateLocationProvider
    private let weather: any WeatherForecastClient
    private let now: () -> Date
    private let calendar: () -> Calendar
    private var refreshTask: Task<Void, Never>?
    private var plannedWeatherTask: Task<WorkoutContextDraft?, Never>?
    private var plannedWeatherTime: Date?
    private var plannedRequestID = UUID()
    private var generation = UUID()
    private var healthSuccessDay: DateComponents?
    private var weatherSuccessDay: DateComponents?
    private let refreshInterval: TimeInterval = 3600
    private let failureBackoff: TimeInterval = 15 * 60

    init(health: any HealthWorkoutClient, location: any ApproximateLocationProvider,
         weather: any WeatherForecastClient, defaults: UserDefaults = .standard,
         now: @escaping () -> Date = { .now }, calendar: @escaping () -> Calendar = { .current }) {
        self.preferences = DailyContextPreferences(defaults: defaults)
        self.location = location
        self.weather = weather
        self.now = now
        self.calendar = calendar
        self.setupCompleted = preferences.setupCompleted
        self.healthAutoEnabled = preferences.healthAutoEnabled
        self.weatherAutoEnabled = preferences.weatherAutoEnabled
        self.workoutContext = WorkoutContextProvider(health: health,
            weather: WeatherAutofillService(consent: WeatherLocationConsentStore(defaults: defaults), location: location, weather: weather),
            calendar: calendar(), now: now)
        // A persisted success can never suppress the first in-memory Health load in a new process.
        if !weatherAutoEnabled { preferences.clearWeather() }
    }

    static func live(defaults: UserDefaults = .standard) -> DailyContextCoordinator {
        var health: any HealthWorkoutClient = HealthKitWorkoutClient()
        #if DEBUG
        if ProcessInfo.processInfo.environment["HYDRA_SAMPLE_HEALTH_WORKOUTS"] == "1" { health = SampleHealthWorkoutClient() }
        #endif
        return DailyContextCoordinator(health: health, location: CoreLocationApproximateLocationProvider(),
                                       weather: OpenMeteoWeatherClient(), defaults: defaults)
    }

    func completeSetup() { preferences.setupCompleted = true; setupCompleted = true }

    /// Explicit connect action only. Health read-denial cannot be distinguished from an empty result.
    func connectHealth() async { await setHealthAutoEnabled(true) }

    func setHealthAutoEnabled(_ enabled: Bool) async {
        cancelRefresh()
        preferences.healthAutoEnabled = enabled
        healthAutoEnabled = enabled
        if !enabled {
            workoutContext.clearHealthContext()
            healthState = .idle
            lastHealthAttempt = nil
            lastHealthSuccess = nil
            healthSuccessDay = nil
            return
        }
        let token = generation
        isRefreshing = true
        healthState = .loading
        lastHealthAttempt = now()
        let success = await workoutContext.refreshWorkouts(requestAuthorization: true)
        guard token == generation, healthAutoEnabled, !Task.isCancelled else { return }
        healthState = workoutContext.workoutState
        if success { lastHealthSuccess = now(); healthSuccessDay = localDay() }
        isRefreshing = false
    }

    /// Explicit separate opt-in to storing a rounded area and automatic Open-Meteo requests.
    /// Does not migrate or grant the existing manual weather toggle.
    func enableAutomaticWeather() async {
        cancelRefresh()
        preferences.weatherAutoEnabled = true
        weatherAutoEnabled = true
        let token = generation
        isRefreshing = true
        await refreshWeather(mode: .foreground, requestPermission: true, token: token)
        guard token == generation else { return }
        isRefreshing = false
    }

    func disableAutomaticWeather() {
        cancelRefresh()
        preferences.weatherAutoEnabled = false
        preferences.clearWeather()
        weatherAutoEnabled = false
        currentWeather = nil
        lastWeatherAttempt = nil
        lastWeatherSuccess = nil
        weatherSuccessDay = nil
        weatherState = .idle
    }

    /// Call on foreground, local-day boundary, or a best-effort BGAppRefreshTask.
    /// Automatic refresh never raises permission prompts or requests background location.
    func refreshIfNeeded(mode: DailyContextRefreshMode = .foreground) async {
        if weatherAutoEnabled && !location.hasExistingAuthorization { clearRevokedWeather() }
        if let refreshTask { await refreshTask.value; return }
        guard !isRefreshing else { return }
        let token = generation
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            self.isRefreshing = true
            defer {
                if self.generation == token {
                    self.isRefreshing = false
                    self.refreshTask = nil
                }
            }
            if self.healthAutoEnabled && self.eligible(success: self.lastHealthSuccess, attempt: self.lastHealthAttempt,
                day: self.healthSuccessDay, failed: self.hasFailed(self.healthState), missingMemory: self.workoutContext.draft.typicalSessions == nil) {
                self.lastHealthAttempt = self.now()
                self.healthState = .loading
                let success = await self.workoutContext.refreshWorkouts()
                guard self.valid(token) else { return }
                self.healthState = self.workoutContext.workoutState
                if success { self.lastHealthSuccess = self.now(); self.healthSuccessDay = self.localDay() }
            }
            guard self.valid(token) else { return }
            if self.weatherAutoEnabled && self.location.hasExistingAuthorization && self.eligible(
                success: self.lastWeatherSuccess, attempt: self.lastWeatherAttempt, day: self.weatherSuccessDay, failed: self.hasFailed(self.weatherState)) {
                await self.refreshWeather(mode: mode, requestPermission: false, token: token)
            }
            guard self.valid(token) else { return }
        }
        refreshTask = task
        await withTaskCancellationHandler { await task.value } onCancel: { task.cancel() }
    }

    /// A separate requested-hour suggestion for a pristine planned-workout form. Never reuses
    /// current-area weather, changes its freshness, requests location, or grants manual consent.
    func plannedWeatherSuggestion(startsAt: Date) async -> WorkoutContextDraft? {
        guard weatherAutoEnabled, !Task.isCancelled else { return nil }
        guard location.hasExistingAuthorization else { clearRevokedWeather(); return nil }
        guard let coordinate = preferences.savedCoordinate else { return nil }
        if plannedWeatherTime == startsAt, let plannedWeatherTask {
            let result = await plannedWeatherTask.value
            return Task.isCancelled ? nil : result
        }
        plannedWeatherTask?.cancel()
        let requestID = UUID()
        plannedRequestID = requestID
        plannedWeatherTime = startsAt
        let token = generation
        let task = Task<WorkoutContextDraft?, Never> { @MainActor [weak self] in
            guard let self else { return nil }
            defer {
                if self.plannedRequestID == requestID {
                    self.plannedWeatherTask = nil
                    self.plannedWeatherTime = nil
                }
            }
            do {
                let conditions = try await self.weather.conditions(at: coordinate, nearest: startsAt)
                guard self.valid(token), self.weatherAutoEnabled, self.plannedRequestID == requestID else { return nil }
                guard self.location.hasExistingAuthorization else { self.clearRevokedWeather(); return nil }
                guard self.preferences.savedCoordinate == coordinate,
                      self.usable(conditions, coordinate: coordinate, requestedTime: startsAt) else { return nil }
                var suggestion = WorkoutContextDraft()
                suggestion.temperatureC = conditions.temperatureC
                suggestion.humidityPercent = conditions.humidityPercent
                suggestion.weatherProvenance = WorkoutContextProvider.weatherProvenanceText
                suggestion.weatherRequestedTime = startsAt
                suggestion.weatherForecastHour = conditions.forecastHour
                return suggestion
            } catch { return nil }
        }
        plannedWeatherTask = task
        let result = await withTaskCancellationHandler { await task.value } onCancel: { task.cancel() }
        return Task.isCancelled ? nil : result
    }

    /// BGTask expiration/owner cancellation. Provider replies may finish but cannot publish.
    func cancelRefresh() {
        generation = UUID()
        refreshTask?.cancel()
        refreshTask = nil
        plannedWeatherTask?.cancel()
        plannedWeatherTask = nil
        plannedWeatherTime = nil
        plannedRequestID = UUID()
        workoutContext.cancelPendingWorkouts()
        isRefreshing = false
        if healthState == .loading { healthState = .idle }
        if weatherState == .loading { weatherState = .idle }
    }

    var nextRefreshDate: Date {
        let current = now()
        let tomorrow = calendar().date(byAdding: .day, value: 1, to: calendar().startOfDay(for: current)) ?? current.addingTimeInterval(86_400)
        let candidates = [(healthAutoEnabled, lastHealthSuccess, lastHealthAttempt, healthSuccessDay, healthState),
                          (weatherAutoEnabled, lastWeatherSuccess, lastWeatherAttempt, weatherSuccessDay, weatherState)].compactMap { enabled, success, attempt, day, state -> Date? in
            guard enabled else { return nil }
            if let attempt, hasFailed(state) { return max(current, attempt.addingTimeInterval(failureBackoff)) }
            if day != localDay() { return current }
            return min(tomorrow, (success ?? current).addingTimeInterval(refreshInterval))
        }
        return candidates.min() ?? tomorrow
    }

    private func valid(_ token: UUID) -> Bool { token == generation && !Task.isCancelled }

    private func localDay() -> DateComponents { calendar().dateComponents([.era, .year, .month, .day], from: now()) }

    private func clearRevokedWeather() {
        preferences.clearWeather()
        currentWeather = nil
        lastWeatherSuccess = nil
        lastWeatherAttempt = nil
        weatherSuccessDay = nil
        weatherState = .failed(WeatherAutofillError.locationDenied.errorDescription!)
    }

    private func hasFailed(_ state: LoadState) -> Bool {
        if case .failed = state { return true }
        return false
    }

    private func eligible(success: Date?, attempt: Date?, day: DateComponents?, failed: Bool, missingMemory: Bool = false) -> Bool {
        let current = now()
        if let attempt, failed {
            // A failed read is an attempt, never a fresh value. Avoid repeated foreground/day loops.
            if current.timeIntervalSince(attempt) < failureBackoff { return false }
        }
        guard let success else { return true }
        return missingMemory || day != localDay() || current.timeIntervalSince(success) >= refreshInterval
    }

    private func usable(_ conditions: WeatherConditions, coordinate: RoundedCoordinate, requestedTime: Date) -> Bool {
        abs(conditions.forecastHour.timeIntervalSince(requestedTime)) <= OpenMeteoForecastParser.maximumDistance &&
        conditions.coordinate == coordinate && conditions.temperatureC.isFinite &&
        (-60...60).contains(conditions.temperatureC) && conditions.humidityPercent.isFinite &&
        (0...100).contains(conditions.humidityPercent)
    }

    private func refreshWeather(mode: DailyContextRefreshMode, requestPermission: Bool, token: UUID) async {
        guard weatherAutoEnabled, valid(token) else { return }
        lastWeatherAttempt = now()
        weatherState = .loading
        do {
            let coordinate: RoundedCoordinate
            if requestPermission {
                coordinate = try await location.approximateCoordinate()
            } else {
                guard location.hasExistingAuthorization else { throw WeatherAutofillError.locationDenied }
                switch mode {
                case .foreground: coordinate = try await location.approximateCoordinateWithoutPrompt()
                case .background:
                    guard let saved = preferences.savedCoordinate else { throw WeatherAutofillError.locationUnavailable }
                    coordinate = saved
                }
            }
            guard valid(token), weatherAutoEnabled else { return }
            preferences.savedCoordinate = coordinate
            let requestedTime = now()
            let conditions = try await weather.conditions(at: coordinate, nearest: requestedTime)
            guard valid(token), weatherAutoEnabled else { return }
            guard location.hasExistingAuthorization else { throw WeatherAutofillError.locationDenied }
            guard usable(conditions, coordinate: coordinate, requestedTime: requestedTime),
                  abs(conditions.forecastHour.timeIntervalSince(now())) <= OpenMeteoForecastParser.maximumDistance else {
                throw WeatherAutofillError.invalidResponse
            }
            currentWeather = conditions
            lastWeatherSuccess = now()
            weatherSuccessDay = localDay()
            weatherState = .loaded
        } catch {
            guard valid(token), weatherAutoEnabled else { return }
            if (error as? WeatherAutofillError) == .locationDenied {
                clearRevokedWeather()
            }
            weatherState = .failed((error as? LocalizedError)?.errorDescription ?? "Weather could not be refreshed.")
        }
    }
}
