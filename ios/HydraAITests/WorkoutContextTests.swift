import CoreLocation
import Foundation
import HealthKit
import XCTest
@testable import HydraAI

/// 2026-10-29T00:00:00Z.
private let fixtureBase: TimeInterval = 1_793_232_000

/// Shape of `GET /v1/forecast?...&hourly=temperature_2m,relative_humidity_2m&timezone=auto&timeformat=unixtime`.
private func openMeteoFixture(temperatures: [String] = ["9.8", "10.4", "11.6", "null", "14.2"],
                              humidity: [String] = ["88", "84", "79", "75", "61"]) -> Data {
    let times = (0..<temperatures.count).map { String(Int(fixtureBase) + $0 * 3600) }
    return Data("""
    {"latitude":48.86,"longitude":2.3399997,"generationtime_ms":0.04,"utc_offset_seconds":3600,
     "timezone":"Europe/Paris","timezone_abbreviation":"GMT+1","elevation":43.0,
     "hourly_units":{"time":"unixtime","temperature_2m":"°C","relative_humidity_2m":"%"},
     "hourly":{"time":[\(times.joined(separator: ","))],
               "temperature_2m":[\(temperatures.joined(separator: ","))],
               "relative_humidity_2m":[\(humidity.joined(separator: ","))]}}
    """.utf8)
}

/// Counts stubbed network requests from the URL loading thread.
private final class RequestCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var value = 0
    func increment() { lock.lock(); value += 1; lock.unlock() }
    var count: Int { lock.lock(); defer { lock.unlock() }; return value }
}

@MainActor
private final class StubLocationProvider: ApproximateLocationProvider {
    var result: Result<RoundedCoordinate, Error>
    private(set) var calls = 0
    init(_ result: Result<RoundedCoordinate, Error>) { self.result = result }
    func approximateCoordinate() async throws -> RoundedCoordinate {
        calls += 1
        return try result.get()
    }
}

@MainActor
final class WorkoutContextTests: XCTestCase {
    private var defaults: UserDefaults!
    private var suiteName = ""
    private let counter = RequestCounter()
    private var networkCalls: Int { counter.count }

    override func setUp() async throws {
        suiteName = "WorkoutContextTests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
    }

    override func tearDown() async throws {
        FixtureURLProtocol.handler = nil
        defaults.removePersistentDomain(forName: suiteName)
    }

    private func stubbedSession(_ handler: @escaping (URLRequest) throws -> (Int, Data)) -> URLSession {
        let options = URLSessionConfiguration.ephemeral
        options.protocolClasses = [FixtureURLProtocol.self]
        let counter = counter
        FixtureURLProtocol.handler = { request in
            counter.increment()
            return try handler(request)
        }
        return URLSession(configuration: options)
    }

    private func paris() throws -> RoundedCoordinate { try RoundedCoordinate(latitude: 48.856613, longitude: 2.352222) }

    private func workout(_ type: HKWorkoutActivityType, minutes: Double, daysAgo: Double, heartRate: Double? = nil,
                         now: Date = Date(timeIntervalSince1970: fixtureBase)) -> HealthWorkoutSummary {
        HealthWorkoutSummary(id: UUID(), source: .appleHealth, activityType: type,
                             startDate: now.addingTimeInterval(-daysAgo * 86_400), durationSeconds: minutes * 60,
                             activeEnergyKilocalories: 400, averageHeartRateBPM: heartRate)!
    }

    // MARK: Activity mapping

    func testActivityMappingUsesForecastValuesAndSafeDefault() {
        XCTAssertEqual(WorkoutActivityMapping.map(.running).activity, .running)
        XCTAssertEqual(WorkoutActivityMapping.map(.cycling).activity, .cycling)
        XCTAssertEqual(WorkoutActivityMapping.map(.walking).activity, .walking)
        XCTAssertEqual(WorkoutActivityMapping.map(.hiking).activity, .walking)
        XCTAssertEqual(WorkoutActivityMapping.map(.traditionalStrengthTraining).activity, .strength)
        XCTAssertEqual(WorkoutActivityMapping.map(.functionalStrengthTraining).activity, .strength)
        XCTAssertTrue(WorkoutActivityMapping.map(.running).isDirectMatch)
        XCTAssertNil(WorkoutActivityMapping.map(.running).note)

        let yoga = WorkoutActivityMapping.map(.yoga)
        XCTAssertEqual(yoga.activity, .other)
        XCTAssertFalse(yoga.isDirectMatch)
        XCTAssertTrue(yoga.note?.contains("Yoga") == true)
        XCTAssertEqual(WorkoutActivityMapping.map(.swimming).activity, .other)

        // Every type, including ones added in future SDKs, lands on a value the backend accepts.
        let accepted: Set<String> = ["running", "cycling", "walking", "strength", "other"]
        XCTAssertEqual(Set(WorkoutForecastActivity.allCases.map(\.rawValue)), accepted)
        for raw in UInt(0)...UInt(4000) {
            guard let type = HKWorkoutActivityType(rawValue: raw) else { continue }
            XCTAssertTrue(accepted.contains(WorkoutActivityMapping.map(type).activity.rawValue))
        }
    }

    // MARK: Typical sessions

    func testTypicalSessionSummaryUsesMedianAndMostCommonActivity() {
        let workouts = [
            workout(.running, minutes: 45, daysAgo: 1),
            workout(.cycling, minutes: 90, daysAgo: 2),
            workout(.running, minutes: 30, daysAgo: 3),
            workout(.yoga, minutes: 20, daysAgo: 4),
            workout(.running, minutes: 50, daysAgo: 5),
        ]
        let summary = TypicalWorkoutSessions.summarize(workouts)
        XCTAssertEqual(summary.sessionCount, 5)
        XCTAssertEqual(summary.medianDurationMinutes, 45)
        XCTAssertEqual(summary.mostCommonActivity, .running)
        XCTAssertEqual(summary.mostCommonActivityCount, 3)
        XCTAssertEqual(summary.latestStart, workouts[0].startDate)
        XCTAssertEqual(summary.earliestStart, workouts[4].startDate)
        XCTAssertTrue(summary.displayText?.contains("45 min") == true)

        let even = TypicalWorkoutSessions.summarize(Array(workouts.prefix(4)))
        XCTAssertEqual(even.medianDurationMinutes, 37.5)
    }

    func testTypicalSessionTieGoesToMostRecentActivityAndEmptyHasNoSummary() {
        let tie = TypicalWorkoutSessions.summarize([
            workout(.cycling, minutes: 60, daysAgo: 1),
            workout(.running, minutes: 40, daysAgo: 2),
            workout(.running, minutes: 40, daysAgo: 3),
            workout(.cycling, minutes: 60, daysAgo: 4),
        ])
        XCTAssertEqual(tie.mostCommonActivity, .cycling)
        XCTAssertEqual(tie.mostCommonActivityCount, 2)

        let empty = TypicalWorkoutSessions.summarize([])
        XCTAssertEqual(empty.sessionCount, 0)
        XCTAssertNil(empty.medianDurationMinutes)
        XCTAssertNil(empty.mostCommonActivity)
        XCTAssertNil(empty.displayText)
    }

    func testWorkoutSummaryRejectsUnusableDurationsAndDropsImplausibleContext() {
        let start = Date(timeIntervalSince1970: fixtureBase)
        XCTAssertNil(HealthWorkoutSummary(id: UUID(), source: .appleHealth, activityType: .running, startDate: start,
                                          durationSeconds: 0, activeEnergyKilocalories: nil, averageHeartRateBPM: nil))
        XCTAssertNil(HealthWorkoutSummary(id: UUID(), source: .appleHealth, activityType: .running, startDate: start,
                                          durationSeconds: 1441 * 60, activeEnergyKilocalories: nil, averageHeartRateBPM: nil))
        XCTAssertNil(HealthWorkoutSummary(id: UUID(), source: .appleHealth, activityType: .running, startDate: start,
                                          durationSeconds: .nan, activeEnergyKilocalories: nil, averageHeartRateBPM: nil))
        let odd = HealthWorkoutSummary(id: UUID(), source: .appleHealth, activityType: .running, startDate: start,
                                       durationSeconds: 600, activeEnergyKilocalories: -5, averageHeartRateBPM: 900)
        XCTAssertNil(odd?.activeEnergyKilocalories)
        XCTAssertNil(odd?.averageHeartRateBPM)
    }

    // MARK: Coordinate rounding

    func testCoordinatesAreRoundedToTwoDecimalsBeforeLeavingDevice() throws {
        let coordinate = try paris()
        XCTAssertEqual(coordinate.latitude, 48.86)
        XCTAssertEqual(coordinate.longitude, 2.35)
        XCTAssertEqual(coordinate.latitudeText, "48.86")
        XCTAssertEqual(coordinate.longitudeText, "2.35")

        let southWest = try RoundedCoordinate(latitude: -33.868_820, longitude: -151.209_296)
        XCTAssertEqual(southWest.latitudeText, "-33.87")
        XCTAssertEqual(southWest.longitudeText, "-151.21")

        let nearZero = try RoundedCoordinate(latitude: -0.004, longitude: 0.004)
        XCTAssertEqual(nearZero.latitudeText, "0.00")
        XCTAssertEqual(nearZero.longitudeText, "0.00")

        XCTAssertThrowsError(try RoundedCoordinate(latitude: 91, longitude: 0))
        XCTAssertThrowsError(try RoundedCoordinate(latitude: 0, longitude: -181))
        XCTAssertThrowsError(try RoundedCoordinate(latitude: .nan, longitude: 0))

        let url = OpenMeteoWeatherClient.url(for: coordinate)
        let items = Dictionary(uniqueKeysWithValues: URLComponents(url: url, resolvingAgainstBaseURL: false)!
            .queryItems!.map { ($0.name, $0.value ?? "") })
        XCTAssertEqual(url.scheme, "https")
        XCTAssertEqual(url.host, "api.open-meteo.com")
        XCTAssertEqual(url.path, "/v1/forecast")
        XCTAssertEqual(items, ["latitude": "48.86", "longitude": "2.35",
                               "hourly": "temperature_2m,relative_humidity_2m",
                               "timezone": "auto", "timeformat": "unixtime"])
    }

    // MARK: Nearest-hour parsing

    func testParserPicksHourNearestPlannedStart() throws {
        let coordinate = try paris()
        // 01:20 is nearest 01:00.
        let early = try OpenMeteoForecastParser.nearestHour(in: openMeteoFixture(),
            to: Date(timeIntervalSince1970: fixtureBase + 80 * 60), coordinate: coordinate)
        XCTAssertEqual(early.temperatureC, 10.4)
        XCTAssertEqual(early.humidityPercent, 84)
        XCTAssertEqual(early.forecastHour, Date(timeIntervalSince1970: fixtureBase + 3600))
        XCTAssertEqual(early.timezoneIdentifier, "Europe/Paris")
        XCTAssertEqual(early.coordinate, coordinate)

        // Exactly between 01:00 and 02:00 goes to the earlier hour.
        let tie = try OpenMeteoForecastParser.nearestHour(in: openMeteoFixture(),
            to: Date(timeIntervalSince1970: fixtureBase + 90 * 60), coordinate: coordinate)
        XCTAssertEqual(tie.temperatureC, 10.4)

        // 03:00 has a missing temperature, so the nearest complete hour (02:00 vs 04:00 tie -> 02:00) is used.
        let gap = try OpenMeteoForecastParser.nearestHour(in: openMeteoFixture(),
            to: Date(timeIntervalSince1970: fixtureBase + 3 * 3600), coordinate: coordinate)
        XCTAssertEqual(gap.temperatureC, 11.6)
        XCTAssertEqual(gap.humidityPercent, 79)
    }

    func testParserRejectsOutOfRangeStartsAndInvalidPayloads() throws {
        let coordinate = try paris()
        let start = Date(timeIntervalSince1970: fixtureBase)
        XCTAssertThrowsError(try OpenMeteoForecastParser.nearestHour(in: openMeteoFixture(),
            to: Date(timeIntervalSince1970: fixtureBase + 10 * 86_400), coordinate: coordinate)) {
            XCTAssertEqual($0 as? WeatherAutofillError, .outOfForecastRange)
        }
        XCTAssertThrowsError(try OpenMeteoForecastParser.nearestHour(in: openMeteoFixture(),
            to: Date(timeIntervalSince1970: fixtureBase - 3 * 3600), coordinate: coordinate)) {
            XCTAssertEqual($0 as? WeatherAutofillError, .outOfForecastRange)
        }
        let invalid: [Data] = [
            Data("not json".utf8),
            Data("{\"hourly\":{\"time\":[],\"temperature_2m\":[],\"relative_humidity_2m\":[]}}".utf8),
            openMeteoFixture(temperatures: ["10"], humidity: ["50", "60"]),
            openMeteoFixture(temperatures: ["75"], humidity: ["50"]),
            openMeteoFixture(temperatures: ["10"], humidity: ["101"]),
        ]
        for data in invalid {
            XCTAssertThrowsError(try OpenMeteoForecastParser.nearestHour(in: data, to: start, coordinate: coordinate)) {
                XCTAssertEqual($0 as? WeatherAutofillError, .invalidResponse)
            }
        }
        XCTAssertThrowsError(try OpenMeteoForecastParser.nearestHour(
            in: openMeteoFixture(temperatures: ["null"], humidity: ["50"]), to: start, coordinate: coordinate)) {
            XCTAssertEqual($0 as? WeatherAutofillError, .outOfForecastRange)
        }
    }

    // MARK: Consent gating

    func testNoLocationOrNetworkRequestWithoutConsent() async throws {
        let consent = WeatherLocationConsentStore(defaults: defaults)
        XCTAssertFalse(consent.isGranted, "Weather fill-in must default to off")
        let location = StubLocationProvider(.success(try paris()))
        let client = OpenMeteoWeatherClient(session: stubbedSession { _ in (200, openMeteoFixture()) })
        let service = WeatherAutofillService(consent: consent, location: location, weather: client)

        do {
            _ = try await service.conditions(nearest: Date(timeIntervalSince1970: fixtureBase))
            XCTFail("Expected consentRequired")
        } catch {
            XCTAssertEqual(error as? WeatherAutofillError, .consentRequired)
        }
        XCTAssertEqual(location.calls, 0)
        XCTAssertEqual(networkCalls, 0)

        let provider = WorkoutContextProvider(health: SampleHealthWorkoutClient(), weather: service)
        let draft = await provider.fillInWeather(startsAt: Date(timeIntervalSince1970: fixtureBase))
        XCTAssertNil(draft.temperatureC)
        XCTAssertEqual(provider.weatherState, .failed(WeatherAutofillError.consentRequired.errorDescription!))
        XCTAssertEqual(location.calls, 0)
        XCTAssertEqual(networkCalls, 0)
    }

    func testConsentedWeatherFillSendsOnlyRoundedCoordinate() async throws {
        let location = StubLocationProvider(.success(try paris()))
        let client = OpenMeteoWeatherClient(session: stubbedSession { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
            XCTAssertNil(request.value(forHTTPHeaderField: "Cookie"))
            XCTAssertTrue(request.url!.absoluteString.contains("latitude=48.86&longitude=2.35&"))
            XCTAssertFalse(request.url!.absoluteString.contains("48.8566"))
            return (200, openMeteoFixture())
        })
        let service = WeatherAutofillService(consent: WeatherLocationConsentStore(defaults: defaults),
                                             location: location, weather: client)
        let provider = WorkoutContextProvider(health: SampleHealthWorkoutClient(), weather: service)
        XCTAssertFalse(provider.isWeatherConsentGranted)
        provider.setWeatherConsent(true)
        XCTAssertTrue(defaults.bool(forKey: WeatherLocationConsentStore.key))

        let draft = await provider.fillInWeather(startsAt: Date(timeIntervalSince1970: fixtureBase + 7200))
        XCTAssertEqual(provider.weatherState, .loaded)
        XCTAssertEqual(draft.temperatureC, 11.6)
        XCTAssertEqual(draft.humidityPercent, 79)
        XCTAssertEqual(draft.weatherProvenance, "Weather from Open-Meteo for your area")
        XCTAssertEqual(location.calls, 1)
        XCTAssertEqual(networkCalls, 1)

        // Withdrawing consent clears the Open-Meteo values.
        provider.setWeatherConsent(false)
        XCTAssertNil(provider.draft.temperatureC)
        XCTAssertNil(provider.draft.humidityPercent)
        XCTAssertNil(provider.draft.weatherProvenance)
        XCTAssertFalse(defaults.bool(forKey: WeatherLocationConsentStore.key))
    }

    // MARK: Error handling

    func testWeatherErrorsFailGracefully() async throws {
        let consent = WeatherLocationConsentStore(defaults: defaults)
        consent.isGranted = true
        let start = Date(timeIntervalSince1970: fixtureBase)
        let cases: [(Result<RoundedCoordinate, Error>, (URLRequest) throws -> (Int, Data), WeatherAutofillError)] = [
            (.failure(WeatherAutofillError.locationDenied), { _ in (200, openMeteoFixture()) }, .locationDenied),
            (.success(try paris()), { _ in throw URLError(.notConnectedToInternet) }, .offline),
            (.success(try paris()), { _ in throw URLError(.timedOut) }, .offline),
            (.success(try paris()), { _ in throw URLError(.badServerResponse) }, .unavailable),
            (.success(try paris()), { _ in (500, Data()) }, .unavailable),
            (.success(try paris()), { _ in (400, Data("{\"error\":true,\"reason\":\"Latitude must be in range\"}".utf8)) }, .outOfForecastRange),
            (.success(try paris()), { _ in (200, Data("{}".utf8)) }, .invalidResponse),
        ]
        for (locationResult, handler, expected) in cases {
            let location = StubLocationProvider(locationResult)
            let service = WeatherAutofillService(consent: consent, location: location,
                                                 weather: OpenMeteoWeatherClient(session: stubbedSession(handler)))
            do {
                _ = try await service.conditions(nearest: start)
                XCTFail("Expected \(expected)")
            } catch {
                XCTAssertEqual(error as? WeatherAutofillError, expected)
            }
            let provider = WorkoutContextProvider(health: SampleHealthWorkoutClient(), weather: service)
            let draft = await provider.fillInWeather(startsAt: start)
            XCTAssertNil(draft.temperatureC)
            XCTAssertEqual(provider.weatherState, .failed(expected.errorDescription!))
        }
    }

    // MARK: Workout prefill

    func testUseLastWorkoutPrefillsDraftWithProvenanceAndContextOnlyHeartRate() async throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let now = Date(timeIntervalSince1970: fixtureBase + 12 * 3600) // 12:00 UTC
        let lastStart = Date(timeIntervalSince1970: fixtureBase - 86_400 + 7 * 3600 + 30 * 60) // yesterday 07:30
        let last = HealthWorkoutSummary(id: UUID(), source: .appleHealth, activityType: .yoga, startDate: lastStart,
                                        durationSeconds: 44.6 * 60, activeEnergyKilocalories: 210.4, averageHeartRateBPM: 118.6)!
        let health = SampleHealthWorkoutClient(workouts: [last, workout(.running, minutes: 40, daysAgo: 3),
                                                          workout(.running, minutes: 50, daysAgo: 4)])
        let service = WeatherAutofillService(consent: WeatherLocationConsentStore(defaults: defaults),
                                             location: StubLocationProvider(.success(try paris())),
                                             weather: OpenMeteoWeatherClient(session: stubbedSession { _ in (200, openMeteoFixture()) }))
        let provider = WorkoutContextProvider(health: health, weather: service, calendar: calendar, now: { now })

        let draft = await provider.useLastWorkout()
        XCTAssertEqual(provider.workoutState, .loaded)
        XCTAssertEqual(health.accessRequests, 1)
        XCTAssertEqual(draft.activity, "other")
        XCTAssertTrue(draft.activityNote?.contains("Yoga") == true)
        XCTAssertEqual(draft.durationMinutes, 45)
        XCTAssertEqual(draft.averageHeartRate, 119)
        XCTAssertEqual(draft.activeEnergyKilocalories, 210)
        // Next 07:30 after 12:00 is tomorrow 07:30.
        XCTAssertEqual(draft.startsAt, Date(timeIntervalSince1970: fixtureBase + 86_400 + 7 * 3600 + 30 * 60))
        XCTAssertTrue(draft.workoutProvenance?.hasPrefix("From your Apple Health workout on ") == true)
        XCTAssertNil(draft.weatherProvenance)
        XCTAssertEqual(draft.typicalSessions?.sessionCount, 3)
        XCTAssertEqual(draft.typicalSessions?.mostCommonActivity, .running)
        XCTAssertEqual(draft.typicalSessions?.medianDurationMinutes, 44.6)
        XCTAssertEqual(networkCalls, 0, "Workout prefill must not touch the network")

        let planned = Date(timeIntervalSince1970: fixtureBase + 2 * 86_400)
        let explicit = await provider.useLastWorkout(plannedStart: planned)
        XCTAssertEqual(explicit.startsAt, planned)

        // Heart rate is display context only: the forecast request has no heart-rate field.
        let conditions = WorkoutForecastRequest.Conditions(activity: draft.activity!, intensity: "moderate",
                                                           temperature_c: 20, humidity_percent: 50)
        let encoded = String(decoding: try JSONEncoder().encode(conditions), as: UTF8.self)
        XCTAssertFalse(encoded.lowercased().contains("heart"))
        XCTAssertTrue(WorkoutContextProvider.heartRateContextNote.contains("never"))
    }

    func testSampleWorkoutsAreLabeledAndHealthFailuresAreGraceful() async throws {
        let service = WeatherAutofillService(consent: WeatherLocationConsentStore(defaults: defaults),
                                             location: StubLocationProvider(.success(try paris())),
                                             weather: OpenMeteoWeatherClient(session: stubbedSession { _ in (200, openMeteoFixture()) }))
        let sample = WorkoutContextProvider(health: SampleHealthWorkoutClient(), weather: service)
        let sampleDraft = await sample.useLastWorkout()
        XCTAssertTrue(sampleDraft.workoutProvenance?.hasPrefix("Sample workout (not your data)") == true)
        XCTAssertEqual(sampleDraft.activity, "running")

        let empty = WorkoutContextProvider(health: SampleHealthWorkoutClient(workouts: []), weather: service)
        let emptyDraft = await empty.useLastWorkout()
        XCTAssertEqual(emptyDraft, WorkoutContextDraft())
        XCTAssertEqual(empty.workoutState, .failed(HealthWorkoutError.noWorkouts.errorDescription!))

        let unavailableClient = SampleHealthWorkoutClient(isAvailable: false)
        let unavailable = WorkoutContextProvider(health: unavailableClient, weather: service)
        XCTAssertFalse(unavailable.isHealthAvailable)
        _ = await unavailable.useLastWorkout()
        XCTAssertEqual(unavailable.workoutState, .failed(HealthWorkoutError.unavailable.errorDescription!))
        XCTAssertEqual(unavailableClient.reads, 0)

        sample.clear()
        XCTAssertEqual(sample.draft, WorkoutContextDraft())
        XCTAssertEqual(sample.workoutState, .idle)
    }

    func testRecentWorkoutsAreMostRecentFirstAndLimited() async throws {
        let client = SampleHealthWorkoutClient(workouts: [
            workout(.running, minutes: 30, daysAgo: 5),
            workout(.cycling, minutes: 60, daysAgo: 1),
            workout(.walking, minutes: 20, daysAgo: 3),
        ])
        let recent = try await client.recentWorkouts(limit: 2)
        XCTAssertEqual(recent.map(\.activity), [.cycling, .walking])
        let typical = try await client.typicalSessions(limit: 3)
        XCTAssertEqual(typical.medianDurationMinutes, 30)
    }

    func testHealthKitClientRequestsOnlyWorkoutEnergyAndHeartRate() {
        let client = HealthKitWorkoutClient()
        XCTAssertEqual(client.readTypes, [HKObjectType.workoutType(), HKQuantityType(.activeEnergyBurned), HKQuantityType(.heartRate)])
    }
}
