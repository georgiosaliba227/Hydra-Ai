import Foundation
import XCTest
@testable import HydraAI

@MainActor
private final class DailyLocation: ApproximateLocationProvider {
    var hasExistingAuthorization = true
    var prompts = 0
    var automaticReads = 0
    func approximateCoordinate() async throws -> RoundedCoordinate {
        prompts += 1
        return try RoundedCoordinate(latitude: 40.1234, longitude: -73.9876)
    }
    func approximateCoordinateWithoutPrompt() async throws -> RoundedCoordinate {
        automaticReads += 1
        guard hasExistingAuthorization else { throw WeatherAutofillError.locationDenied }
        return try RoundedCoordinate(latitude: 40.1234, longitude: -73.9876)
    }
}

@MainActor
private final class DailyWeather: WeatherForecastClient {
    var calls = 0
    var error: Error?
    var offset: TimeInterval = 0
    var pending: CheckedContinuation<Void, Never>?
    var suspend = false
    func conditions(at coordinate: RoundedCoordinate, nearest start: Date) async throws -> WeatherConditions {
        calls += 1
        if suspend { await withCheckedContinuation { pending = $0 } }
        if let error { throw error }
        return WeatherConditions(temperatureC: 20, humidityPercent: 60,
            forecastHour: start.addingTimeInterval(offset), coordinate: coordinate, timezoneIdentifier: "America/New_York")
    }
}

@MainActor
private final class SuspendedDailyHealth: HealthWorkoutClient {
    var isAvailable = true
    var accessRequests = 0
    var reads = 0
    var suspend = true
    var pending: CheckedContinuation<Void, Never>?
    func requestWorkoutReadAccess() async throws { accessRequests += 1 }
    func recentWorkouts(limit: Int) async throws -> [HealthWorkoutSummary] {
        reads += 1
        if suspend { await withCheckedContinuation { pending = $0 } }
        return SampleHealthWorkoutClient.sampleWorkouts(endingAt: Date(timeIntervalSince1970: 1_793_750_000))
    }
}

@MainActor
final class DailyContextTests: XCTestCase {
    private var defaults: UserDefaults!
    private var suite = ""
    private var date = Date(timeIntervalSince1970: 1_793_750_000)
    private var health: SampleHealthWorkoutClient!
    private var location: DailyLocation!
    private var weather: DailyWeather!

    override func setUp() async throws {
        suite = "DailyContextTests.\(UUID())"
        defaults = UserDefaults(suiteName: suite)!
        health = SampleHealthWorkoutClient(now: date)
        location = DailyLocation()
        weather = DailyWeather()
    }
    override func tearDown() async throws { defaults.removePersistentDomain(forName: suite) }

    private func make() -> DailyContextCoordinator {
        DailyContextCoordinator(health: health, location: location, weather: weather, defaults: defaults,
            now: { self.date }, calendar: { var c = Calendar(identifier: .gregorian); c.timeZone = TimeZone(secondsFromGMT: 0)!; return c })
    }

    func testOldTapConsentNeverStartsAutomaticRequests() async {
        WeatherLocationConsentStore(defaults: defaults).isGranted = true
        let context = make()
        await context.refreshIfNeeded()
        XCTAssertFalse(context.weatherAutoEnabled)
        XCTAssertNil(context.currentWeather)
        XCTAssertEqual(weather.calls, 0)
        XCTAssertEqual(location.prompts, 0)
        XCTAssertEqual(health.reads, 0)
    }

    func testHealthConnectPromptsOnceThenAutomaticRefreshDoesNotPrompt() async {
        let context = make()
        await context.connectHealth()
        XCTAssertNotNil(context.lastHealthSuccess)
        XCTAssertEqual(health.accessRequests, 1)
        date.addTimeInterval(25 * 3600)
        await context.refreshIfNeeded()
        XCTAssertEqual(health.accessRequests, 1)
        XCTAssertEqual(health.reads, 2)
        XCTAssertNotNil(context.workoutContext.draft.typicalSessions)
    }

    func testNewLocalDayRefreshesEvenWhenRecentAndRestartLoadsHealthAgain() async {
        date = Date(timeIntervalSince1970: 1_793_750_390) // choose time via calendar below
        var c = Calendar(identifier: .gregorian); c.timeZone = TimeZone(secondsFromGMT: 0)!
        date = c.startOfDay(for: date).addingTimeInterval(86_390)
        let context = make()
        await context.connectHealth()
        date.addTimeInterval(20)
        await context.refreshIfNeeded()
        XCTAssertEqual(health.reads, 2)
        let restarted = make()
        await restarted.refreshIfNeeded()
        XCTAssertEqual(health.reads, 3)
        XCTAssertNotNil(restarted.workoutContext.draft.typicalSessions)
    }

    func testEmptyHealthIsHonestFailureThrottledAndNeverFresh() async {
        health.workouts = []
        let context = make()
        await context.connectHealth()
        XCTAssertNil(context.lastHealthSuccess)
        guard case .failed(let message) = context.healthState else { return XCTFail("Missing empty/denied state") }
        XCTAssertTrue(message.contains("access was not allowed"))
        await context.refreshIfNeeded()
        XCTAssertEqual(health.reads, 1)
        XCTAssertNil(context.workoutContext.draft.durationMinutes)
    }

    func testBackgroundWithoutSavedAreaNeverRequestsLocationOrWeather() async {
        defaults.set(true, forKey: DailyContextPreferences.weatherAutoKey)
        let context = make()
        await context.refreshIfNeeded(mode: .background)
        XCTAssertEqual(location.prompts, 0)
        XCTAssertEqual(location.automaticReads, 0)
        XCTAssertEqual(weather.calls, 0)
        XCTAssertNil(context.lastWeatherSuccess)
    }

    func testWeatherUsesSeparateConsentAndBackgroundSavedRoundedArea() async {
        let context = make()
        await context.enableAutomaticWeather()
        XCTAssertEqual(location.prompts, 1)
        XCTAssertFalse(WeatherLocationConsentStore(defaults: defaults).isGranted)
        XCTAssertEqual(context.currentWeather?.coordinate.latitude, 40.12)
        XCTAssertNil(context.workoutContext.draft.temperatureC)
        date.addTimeInterval(25 * 3600)
        await context.refreshIfNeeded(mode: .background)
        XCTAssertEqual(location.automaticReads, 0)
        XCTAssertEqual(location.prompts, 1)
        XCTAssertEqual(weather.calls, 2)
    }

    func testIndependentSuccessTimestampsAndWeatherFailureThrottle() async {
        let context = make()
        await context.connectHealth()
        let healthTime = context.lastHealthSuccess
        weather.error = WeatherAutofillError.offline
        await context.enableAutomaticWeather()
        await context.refreshIfNeeded()
        XCTAssertEqual(context.lastHealthSuccess, healthTime)
        XCTAssertNil(context.lastWeatherSuccess)
        XCTAssertEqual(weather.calls, 1)
    }

    func testConcurrentRefreshCoalescesAndRevokedReplyCannotPublish() async {
        let context = make()
        await context.enableAutomaticWeather()
        date.addTimeInterval(25 * 3600)
        weather.suspend = true
        let first = Task { await context.refreshIfNeeded(mode: .background) }
        while weather.pending == nil { await Task.yield() }
        let second = Task { await context.refreshIfNeeded(mode: .background) }
        await Task.yield()
        XCTAssertEqual(weather.calls, 2)
        context.disableAutomaticWeather()
        weather.pending?.resume(); weather.pending = nil
        await first.value; await second.value
        XCTAssertNil(context.currentWeather)
        XCTAssertNil(context.lastWeatherSuccess)
        XCTAssertNil(DailyContextPreferences(defaults: defaults).savedCoordinate)
    }

    func testExpirationDiscardsReplyAndLeavesAttemptUnsuccessful() async {
        let context = make()
        defaults.set(true, forKey: DailyContextPreferences.weatherAutoKey)
        // Recreate so preference is read; enable explicitly first to obtain a cached area.
        await context.enableAutomaticWeather()
        let prior = context.lastWeatherSuccess
        date.addTimeInterval(25 * 3600)
        weather.suspend = true
        let task = Task { await context.refreshIfNeeded(mode: .background) }
        while weather.pending == nil { await Task.yield() }
        context.cancelRefresh()
        weather.pending?.resume(); weather.pending = nil
        await task.value
        XCTAssertEqual(context.lastWeatherSuccess, prior)
        XCTAssertFalse(context.isRefreshing)
    }

    func testStaleForecastHourRejectedAndPermissionRevocationClearsArea() async {
        let context = make()
        weather.offset = 3 * 3600
        await context.enableAutomaticWeather()
        XCTAssertNil(context.currentWeather)
        XCTAssertNil(context.lastWeatherSuccess)
        weather.offset = 0
        date.addTimeInterval(3600)
        await context.refreshIfNeeded()
        XCTAssertNotNil(context.currentWeather)
        location.hasExistingAuthorization = false
        date.addTimeInterval(3600)
        await context.refreshIfNeeded()
        XCTAssertNil(context.currentWeather)
        XCTAssertNil(DailyContextPreferences(defaults: defaults).savedCoordinate)
    }
    func testFreshWeatherIsClearedImmediatelyWhenLocationPermissionRevoked() async {
        let context = make()
        await context.enableAutomaticWeather()
        location.hasExistingAuthorization = false
        await context.refreshIfNeeded(mode: .background)
        XCTAssertNil(context.currentWeather)
        XCTAssertNil(context.lastWeatherSuccess)
        XCTAssertNil(DailyContextPreferences(defaults: defaults).savedCoordinate)
    }

    func testDisablingHealthClearsInMemorySuggestionsAndTimestamps() async {
        let context = make()
        await context.connectHealth()
        await context.setHealthAutoEnabled(false)
        XCTAssertNil(context.workoutContext.draft.typicalSessions)
        XCTAssertNil(context.workoutContext.draft.averageHeartRate)
        XCTAssertNil(context.lastHealthSuccess)
        XCTAssertNil(context.lastHealthAttempt)
        XCTAssertFalse(context.healthAutoEnabled)
    }

    func testUnavailableHealthNeverReportsZeroOrFreshSuccess() async {
        let context = make()
        await context.connectHealth()
        health.isAvailable = false
        date.addTimeInterval(3600)
        await context.refreshIfNeeded()
        guard case .failed = context.healthState else { return XCTFail("Unavailable Health must be reported") }
        XCTAssertNotEqual(context.lastHealthSuccess, context.lastHealthAttempt)
    }

    func testPlannedWeatherKeepsRequestedAndActualHoursThenInvalidatesOnStartChange() async throws {
        let consent = WeatherLocationConsentStore(defaults: defaults)
        consent.isGranted = true
        let provider = WorkoutContextProvider(health: health,
            weather: WeatherAutofillService(consent: consent, location: location, weather: weather))
        let requested = date.addingTimeInterval(6 * 3600)
        weather.offset = -10 * 60
        let draft = await provider.fillInWeather(startsAt: requested)
        XCTAssertEqual(draft.weatherRequestedTime, requested)
        XCTAssertEqual(draft.weatherForecastHour, requested.addingTimeInterval(-600))
        provider.invalidateWeather(for: requested.addingTimeInterval(3600))
        XCTAssertNil(provider.draft.weatherProvenance)
        XCTAssertNil(provider.draft.weatherRequestedTime)
        XCTAssertNil(provider.draft.weatherForecastHour)
        XCTAssertNil(provider.draft.temperatureC)
    }

    func testCancellingCallerReleasesRefreshAndDoesNotPublishDelayedReply() async {
        let context = make()
        await context.enableAutomaticWeather()
        let prior = context.lastWeatherSuccess
        date.addTimeInterval(25 * 3600)
        weather.suspend = true
        let task = Task { await context.refreshIfNeeded(mode: .background) }
        while weather.pending == nil { await Task.yield() }
        task.cancel()
        weather.pending?.resume(); weather.pending = nil
        await task.value
        XCTAssertFalse(context.isRefreshing)
        XCTAssertEqual(context.lastWeatherSuccess, prior)
    }

    func testClearedInMemoryHealthLoadsAgainWithoutPermissionPrompt() async {
        let context = make()
        await context.connectHealth()
        context.workoutContext.clear()
        await context.refreshIfNeeded()
        XCTAssertNotNil(context.workoutContext.draft.typicalSessions)
        XCTAssertEqual(health.reads, 2)
        XCTAssertEqual(health.accessRequests, 1)
    }

    func testTimezoneChangeUsesNewLocalDayAndPersistsNoHealthRecords() async {
        var zone = TimeZone(secondsFromGMT: 0)!
        var initial = Calendar(identifier: .gregorian); initial.timeZone = zone
        date = initial.startOfDay(for: date).addingTimeInterval(12 * 3600)
        let context = DailyContextCoordinator(health: health, location: location, weather: weather,
            defaults: defaults, now: { self.date }, calendar: {
                var c = Calendar(identifier: .gregorian); c.timeZone = zone; return c
            })
        await context.connectHealth()
        zone = TimeZone(secondsFromGMT: 14 * 3600)!
        await context.refreshIfNeeded()
        XCTAssertEqual(health.reads, 2)
        let domain = defaults.persistentDomain(forName: suite) ?? [:]
        XCTAssertEqual(Set(domain.keys), [DailyContextPreferences.healthAutoKey])
    }

    func testPlannedSuggestionUsesNewConsentAndSavedAreaWithoutChangingCurrentContext() async {
        let context = make()
        let absent = await context.plannedWeatherSuggestion(startsAt: date)
        XCTAssertNil(absent)
        await context.enableAutomaticWeather()
        let current = context.currentWeather
        let currentSuccess = context.lastWeatherSuccess
        let requested = date.addingTimeInterval(6 * 3600)
        let suggestion = await context.plannedWeatherSuggestion(startsAt: requested)
        XCTAssertEqual(suggestion?.weatherRequestedTime, requested)
        XCTAssertEqual(suggestion?.weatherForecastHour, requested)
        XCTAssertEqual(suggestion?.temperatureC, 20)
        XCTAssertEqual(suggestion?.weatherProvenance, WorkoutContextProvider.weatherProvenanceText)
        XCTAssertNil(suggestion?.workoutProvenance)
        XCTAssertEqual(context.currentWeather, current)
        XCTAssertEqual(context.lastWeatherSuccess, currentSuccess)
        XCTAssertEqual(location.prompts, 1)
        XCTAssertEqual(location.automaticReads, 0)
    }

    func testPlannedSuggestionCoalescesAndRejectsReplyAfterRevocation() async {
        let context = make()
        await context.enableAutomaticWeather()
        let requested = date.addingTimeInterval(6 * 3600)
        weather.suspend = true
        let first = Task { await context.plannedWeatherSuggestion(startsAt: requested) }
        while weather.pending == nil { await Task.yield() }
        let second = Task { await context.plannedWeatherSuggestion(startsAt: requested) }
        await Task.yield()
        XCTAssertEqual(weather.calls, 2)
        context.disableAutomaticWeather()
        weather.pending?.resume(); weather.pending = nil
        let firstResult = await first.value
        let secondResult = await second.value
        XCTAssertNil(firstResult)
        XCTAssertNil(secondResult)
        XCTAssertNil(context.currentWeather)
    }

    func testPlannedSuggestionRejectsWrongHourAndCancelledCaller() async {
        let context = make()
        await context.enableAutomaticWeather()
        let requested = date.addingTimeInterval(6 * 3600)
        weather.offset = 3 * 3600
        let wrongHour = await context.plannedWeatherSuggestion(startsAt: requested)
        XCTAssertNil(wrongHour)
        weather.offset = 0
        weather.suspend = true
        let pending = Task { await context.plannedWeatherSuggestion(startsAt: requested) }
        while weather.pending == nil { await Task.yield() }
        pending.cancel()
        weather.pending?.resume(); weather.pending = nil
        let cancelled = await pending.value
        XCTAssertNil(cancelled)
    }

    func testEmptyReadAfterPriorSuccessClearsHealthSuggestionsAndBacksOff() async {
        let context = make()
        await context.connectHealth()
        let prior = context.lastHealthSuccess
        health.workouts = []
        date.addTimeInterval(3600)
        await context.refreshIfNeeded()
        XCTAssertNil(context.workoutContext.draft.typicalSessions)
        XCTAssertNil(context.workoutContext.draft.averageHeartRate)
        XCTAssertNil(context.workoutContext.draft.workoutProvenance)
        XCTAssertEqual(context.lastHealthSuccess, prior)
        await context.refreshIfNeeded()
        XCTAssertEqual(health.reads, 2)
    }

    func testFailedReloadAtSameClockInstantStillBacksOff() async {
        let context = make()
        await context.connectHealth()
        context.workoutContext.clear()
        health.workouts = []
        await context.refreshIfNeeded()
        await context.refreshIfNeeded()
        XCTAssertEqual(health.reads, 2)
    }

    func testCancelledExplicitHealthConnectReleasesStateAndAllowsAutomaticRead() async {
        let suspended = SuspendedDailyHealth()
        let context = DailyContextCoordinator(health: suspended, location: location, weather: weather,
            defaults: defaults, now: { self.date })
        let connect = Task { await context.connectHealth() }
        while suspended.pending == nil { await Task.yield() }
        connect.cancel()
        suspended.pending?.resume(); suspended.pending = nil
        await connect.value
        XCTAssertFalse(context.isRefreshing)
        XCTAssertNotEqual(context.healthState, .loading)
        XCTAssertNotEqual(context.workoutContext.workoutState, .loading)
        XCTAssertNil(context.lastHealthSuccess)
        suspended.suspend = false
        await context.refreshIfNeeded()
        XCTAssertEqual(suspended.accessRequests, 1)
        XCTAssertEqual(suspended.reads, 2)
        XCTAssertNotNil(context.lastHealthSuccess)
    }

    func testCancelledManualHealthReadReleasesLoadingBeforeCompletionAndAllowsRetryWithAutoOff() async {
        let suspended = SuspendedDailyHealth()
        let context = DailyContextCoordinator(health: suspended, location: location, weather: weather,
            defaults: defaults, now: { self.date })
        XCTAssertFalse(context.healthAutoEnabled)
        let provider = context.workoutContext
        let first = Task { await provider.useLastWorkout(plannedStart: self.date) }
        while suspended.pending == nil { await Task.yield() }
        let firstRead = suspended.pending; suspended.pending = nil
        first.cancel()
        // The Health client deliberately ignores cancellation and stays suspended.
        for _ in 0..<100 { await Task.yield() }
        XCTAssertEqual(provider.workoutState, .idle, "The import button must become actionable before Health returns")
        XCTAssertNil(provider.draft.workoutProvenance)
        suspended.suspend = false
        let retryStart = date.addingTimeInterval(3600)
        _ = await provider.useLastWorkout(plannedStart: retryStart)
        XCTAssertEqual(provider.workoutState, .loaded)
        XCTAssertEqual(provider.draft.startsAt, retryStart)
        firstRead?.resume()
        _ = await first.value
        XCTAssertEqual(provider.workoutState, .loaded)
        XCTAssertEqual(provider.draft.startsAt, retryStart, "The canceled read must not republish its old start")
        await context.refreshIfNeeded()
        XCTAssertFalse(context.healthAutoEnabled)
        XCTAssertEqual(suspended.reads, 2)
    }

    func testCancellationOfOlderManualReadCannotClearNewerLoadingGeneration() async {
        let suspended = SuspendedDailyHealth()
        let context = DailyContextCoordinator(health: suspended, location: location, weather: weather,
            defaults: defaults, now: { self.date })
        let provider = context.workoutContext
        let first = Task { await provider.useLastWorkout() }
        while suspended.pending == nil { await Task.yield() }
        let firstRead = suspended.pending; suspended.pending = nil
        let newerStart = date.addingTimeInterval(3600)
        let second = Task { await provider.useLastWorkout(plannedStart: newerStart) }
        while suspended.pending == nil { await Task.yield() }
        let secondRead = suspended.pending; suspended.pending = nil
        first.cancel()
        for _ in 0..<100 { await Task.yield() }
        XCTAssertEqual(provider.workoutState, .loading)
        firstRead?.resume()
        _ = await first.value
        XCTAssertEqual(provider.workoutState, .loading)
        XCTAssertNil(provider.draft.workoutProvenance)
        secondRead?.resume()
        _ = await second.value
        XCTAssertEqual(provider.workoutState, .loaded)
        XCTAssertEqual(provider.draft.startsAt, newerStart)
    }

    func testManualWeatherReturningToCachedStartRejectsConflictingPendingReply() async {
        let consent = WeatherLocationConsentStore(defaults: defaults)
        consent.isGranted = true
        let provider = WorkoutContextProvider(health: health,
            weather: WeatherAutofillService(consent: consent, location: location, weather: weather))
        let startA = date
        let startB = date.addingTimeInterval(6 * 3600)
        _ = await provider.fillInWeather(startsAt: startA)
        weather.suspend = true
        let pending = Task { await provider.fillInWeather(startsAt: startB) }
        while weather.pending == nil { await Task.yield() }
        provider.invalidateWeather(for: startA)
        weather.pending?.resume(); weather.pending = nil
        let returned = await pending.value
        XCTAssertEqual(provider.draft.weatherRequestedTime, startA)
        XCTAssertEqual(provider.draft.weatherForecastHour, startA)
        XCTAssertEqual(returned.weatherRequestedTime, startA)
        XCTAssertNotEqual(provider.weatherState, .loading)
    }

    func testObservedSystemRevocationRejectsOldCurrentWeatherReplyAfterRegrant() async {
        let context = make()
        await context.enableAutomaticWeather()
        date.addTimeInterval(25 * 3600)
        weather.suspend = true
        let original = Task { await context.refreshIfNeeded(mode: .background) }
        while weather.pending == nil { await Task.yield() }
        location.hasExistingAuthorization = false
        let observeRevocation = Task { await context.refreshIfNeeded(mode: .background) }
        // Wait for the entry-point revocation cleanup, independently of the old network reply.
        while context.currentWeather != nil { await Task.yield() }
        XCTAssertNil(DailyContextPreferences(defaults: defaults).savedCoordinate)
        location.hasExistingAuthorization = true
        weather.pending?.resume(); weather.pending = nil
        await original.value
        await observeRevocation.value
        XCTAssertNil(context.currentWeather)
        XCTAssertNil(context.lastWeatherSuccess)
        XCTAssertEqual(weather.calls, 2)
        XCTAssertNotEqual(context.weatherState, .loaded)
        XCTAssertFalse(context.isRefreshing)
    }

}
