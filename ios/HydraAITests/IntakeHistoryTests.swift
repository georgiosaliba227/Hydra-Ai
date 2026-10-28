import XCTest
@testable import HydraAI

private func historyJSON(date: String = "2026-10-27", timezone: String = "UTC", logged: Bool = false) throws -> Data {
    let formatter = DateFormatter(); formatter.calendar = Calendar(identifier: .gregorian)
    formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = TimeZone(identifier: timezone)
    formatter.dateFormat = "yyyy-MM-dd"
    var calendar = Calendar(identifier: .gregorian); calendar.timeZone = formatter.timeZone
    let prior = formatter.string(from: calendar.date(byAdding: .day, value: -1, to: formatter.date(from: date)!)!)
    let unavailable: [String: Any] = ["status": "insufficient_data", "lower_ml": NSNull(), "upper_ml": NSNull()]
    let history: [String: Any] = ["window_days": 7, "logged_days": logged ? 1 : 0, "days_without_logs": logged ? 6 : 7,
        "kind": "descriptive_logged_totals_not_needs", "completeness": "unverified",
        "beverage_lower_ml": logged ? 250 : NSNull(), "beverage_upper_ml": logged ? 250 : NSNull(),
        "days": logged ? [["local_date": prior, "timezone": timezone, "beverage_total_ml": 250]] : []]
    return try JSONSerialization.data(withJSONObject: ["version": "personal-exercise-loss-v1", "generated_at": "2026-10-27T12:00:00Z",
        "local_date": date, "timezone": timezone, "prediction_validated": false,
        "daily_requirement": unavailable, "exercise_loss": unavailable, "historical_logged_intake": history])
}

final class IntakeHistoryTests: XCTestCase {
    let configuration = APIConfiguration(baseURL: "http://127.0.0.1:8000", token: String(repeating: "x", count: 32), offline: false)
    override func tearDown() { FixtureURLProtocol.handler = nil }

    func testHistoryRequestContainsNoCalibrationHealthOrPhotoData() async throws {
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        let service = try HTTPBeverageService(configuration: configuration, session: URLSession(configuration: options))
        FixtureURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST"); XCTAssertEqual(request.url?.path, "/v1/forecasts")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer \(self.configuration.token)")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Cache-Control"), "no-store")
            let data: Data
            if let body = request.httpBody { data = body } else {
                let stream = try XCTUnwrap(request.httpBodyStream); stream.open(); defer { stream.close() }
                var body = Data(); var buffer = [UInt8](repeating: 0, count: 1024)
                while stream.hasBytesAvailable { let count = stream.read(&buffer, maxLength: buffer.count); if count <= 0 { break }; body.append(contentsOf: buffer.prefix(count)) }
                data = body
            }
            let body = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            XCTAssertEqual(Set(body.keys), ["date", "timezone", "history_days"])
            XCTAssertEqual(body["date"] as? String, "2026-10-27"); XCTAssertEqual(body["timezone"] as? String, "UTC")
            XCTAssertEqual(body["history_days"] as? Int, 7)
            return (200, try historyJSON(logged: true))
        }
        let history = try await service.intakeHistory(date: "2026-10-27", timezone: "UTC")
        XCTAssertEqual(history.historicalLoggedIntake.loggedDays, 1)
        XCTAssertEqual(history.historicalLoggedIntake.beverageUpperMl, 250)
    }

    func testRejectsWrongContextInventedTargetsAndInvalidHistory() throws {
        let valid = try XCTUnwrap(String(data: historyJSON(logged: true), encoding: .utf8))
        let changes = [
            ("personal-exercise-loss-v1", "unknown-v2"),
            ("\"local_date\":\"2026-10-27\"", "\"local_date\":\"2026-10-28\""),
            ("\"timezone\":\"UTC\"", "\"timezone\":\"Europe/Paris\""),
            ("\"status\":\"insufficient_data\"", "\"status\":\"estimated\""),
            ("\"lower_ml\":null", "\"lower_ml\":2000"),
            ("\"prediction_validated\":false", "\"prediction_validated\":true"),
            ("\"days_without_logs\":6", "\"days_without_logs\":7"),
            ("\"beverage_upper_ml\":250", "\"beverage_upper_ml\":249"),
            ("\"beverage_total_ml\":250", "\"beverage_total_ml\":-1"),
            ("\"beverage_upper_ml\":250", "\"beverage_upper_ml\":1e309"),
            ("2026-10-26", "2026-10-10"),
            ("2026-10-27T12:00:00Z", "not-a-timestamp")
        ]
        for (before, after) in changes {
            XCTAssertTrue(valid.contains(before), before)
            let data = Data(valid.replacingOccurrences(of: before, with: after).utf8)
            XCTAssertThrowsError(try JSONDecoder().decode(IntakeHistoryForecast.self, from: data).validate(date: "2026-10-27", timezone: "UTC"), after)
        }
        let empty = try JSONDecoder().decode(IntakeHistoryForecast.self, from: historyJSON())
        XCTAssertNoThrow(try empty.validate(date: "2026-10-27", timezone: "UTC"))
    }

    @MainActor func testUnsupportedForecastDoesNotBlockBeveragesOrLogging() async throws {
        let service = HistoryRecordingService(fail: true)
        let store = BeverageStore(service: service, pendingURL: temporaryPending(), configuration: configuration)
        await store.refresh()
        await fulfillment(of: [service.firstStarted], timeout: 2)
        await settle { if case .failed = store.intakeHistoryState { return true }; return false }
        XCTAssertNil(store.intakeHistory); XCTAssertEqual(store.summary?.beverageTotalMl, 250)
        XCTAssertEqual(store.state, .loaded); XCTAssertTrue(store.canLog)
    }

    @MainActor func testRefreshDiscardsCancelledStaleHistoryAndMutationInvalidatesLoadedHistory() async throws {
        let service = HistoryRecordingService()
        let file = temporaryPending(); defer { try? FileManager.default.removeItem(at: file.deletingLastPathComponent()) }
        let store = BeverageStore(service: service, pendingURL: file, configuration: configuration)
        await store.refresh(); await fulfillment(of: [service.firstStarted], timeout: 2)
        await store.refresh(); await fulfillment(of: [service.secondStarted], timeout: 2)
        XCTAssertNil(store.intakeHistory)
        try await service.release(1, logged: true)
        await settle { store.intakeHistory != nil }
        XCTAssertEqual(store.intakeHistory?.historicalLoggedIntake.loggedDays, 1)
        try await service.release(0, logged: false)
        await Task.yield()
        XCTAssertEqual(store.intakeHistory?.historicalLoggedIntake.loggedDays, 1, "Old refresh must not overwrite current history")
        do { try await store.add(category: "tea", consumedMl: 125, at: Date(timeIntervalSince1970: 1_700_000_000)); XCTFail("Expected synthetic timeout") } catch { }
        XCTAssertNil(store.intakeHistory); XCTAssertNotNil(store.pending)
    }

    @MainActor func testConnectionChangeInvalidatesInFlightHistory() async throws {
        let saved = try SavedConnectionState(); defer { saved.restore() }
        let service = HistoryRecordingService()
        let store = BeverageStore(service: service, pendingURL: temporaryPending(), configuration: configuration)
        await store.refresh(); await fulfillment(of: [service.firstStarted], timeout: 2)
        try store.configure(APIConfiguration(baseURL: configuration.baseURL, token: configuration.token, offline: true))
        try await service.release(0, logged: true)
        await Task.yield()
        XCTAssertNil(store.intakeHistory); XCTAssertEqual(store.intakeHistoryState, .idle)
        XCTAssertNil(store.summary); XCTAssertTrue(store.isOffline)
    }

    @MainActor func testOfflineDoesNotRequestForecast() async throws {
        let service = HistoryRecordingService()
        let offline = APIConfiguration(baseURL: configuration.baseURL, token: configuration.token, offline: true)
        let store = BeverageStore(service: service, pendingURL: temporaryPending(), configuration: offline)
        await store.refresh(); await Task.yield()
        XCTAssertNil(store.intakeHistory); XCTAssertEqual(store.intakeHistoryState, .idle)
        let count = await service.count; XCTAssertEqual(count, 0)
    }

    private func temporaryPending() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString).appendingPathComponent("pending.json")
    }
    @MainActor private func settle(_ ready: () -> Bool) async {
        for _ in 0..<100 { if ready() { return }; try? await Task.sleep(for: .milliseconds(10)) }
        XCTFail("History did not reach expected state")
    }
}

private actor HistoryRecordingService: BeverageService {
    let firstStarted = XCTestExpectation(description: "First history started")
    let secondStarted = XCTestExpectation(description: "Second history started")
    let fail: Bool
    var count = 0
    private var pending: [Int: (String, String, CheckedContinuation<IntakeHistoryForecast, Error>)] = [:]
    init(fail: Bool = false) { self.fail = fail }
    func listBeverages() async throws -> [BeverageLog] { [] }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary {
        DailySummary(localDate: date, timezone: timezone, beverageTotalMl: 250, estimatedWaterMl: nil, forecastStatus: "insufficient_data")
    }
    func intakeHistory(date: String, timezone: String) async throws -> IntakeHistoryForecast {
        let index = count; count += 1
        if fail { firstStarted.fulfill(); throw ServiceError.server(404) }
        return try await withCheckedThrowingContinuation { continuation in
            pending[index] = (date, timezone, continuation)
            (index == 0 ? firstStarted : secondStarted).fulfill()
        }
    }
    func release(_ index: Int, logged: Bool) throws {
        let (date, timezone, continuation) = pending.removeValue(forKey: index)!
        continuation.resume(returning: try JSONDecoder().decode(IntakeHistoryForecast.self, from: historyJSON(date: date, timezone: timezone, logged: logged)))
    }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw URLError(.timedOut) }
}
