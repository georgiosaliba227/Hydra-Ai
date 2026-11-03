import XCTest
@testable import HydraAI

final class HydrationAnalysisTests: XCTestCase {
    override func tearDown() { FixtureURLProtocol.handler = nil }
    private func fixture(_ name: String) throws -> Data {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "hydration-analysis-" + name, withExtension: "json"))
        return try Data(contentsOf: url)
    }
    private func request(_ mode: String) throws -> WorkoutForecastRequest {
        if mode == "demo" { return .demonstration(timezone: "UTC") }
        if mode == "cold" { return .init(mode: "personal", timezone: "UTC", exercise: nil, samples: [], calibration_processing_consent: false) }
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: fixture("personal-request")) as? [String: Any])
        let item = try XCTUnwrap(body["exercise"] as? [String: Any])
        return WorkoutForecastRequest(mode: "personal", timezone: "UTC", exercise: .init(
            event_id: UUID(uuidString: item["event_id"] as! String)!, starts_at: item["starts_at"] as! String,
            duration_minutes: item["duration_minutes"] as! Double,
            conditions: try JSONDecoder().decode(WorkoutForecastRequest.Conditions.self, from: JSONSerialization.data(withJSONObject: item["conditions"]!)),
            comparable_conditions_confirmed: true),
            samples: try JSONDecoder().decode([WorkoutForecastRequest.Sample].self, from: JSONSerialization.data(withJSONObject: body["samples"]!)),
            calibration_processing_consent: true)
    }
    private func forecast(_ mode: String) throws -> WorkoutForecast {
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: fixture(mode)) as? [String: Any])
        var numeric = body["numerical_forecast"] as! [String: Any]
        numeric["generated_at"] = body["generated_at"]; numeric["timezone"] = "UTC"
        numeric["mode"] = mode == "demo" ? "synthetic_demo" : "personal"
        numeric["explanation_policy"] = "Meta_may_explain_reviewed_results_only_no_numeric_recalculation"
        return try JSONDecoder().decode(WorkoutForecast.self, from: JSONSerialization.data(withJSONObject: numeric))
    }
    func testActualBackendFixturesKeepNumericAuthorityAndSeparateSyntheticIntake() throws {
        for mode in ["cold", "personal", "demo"] {
            let analysis = try JSONDecoder().decode(HydrationAnalysis.self, from: fixture(mode))
            try analysis.validate(request: request(mode), forecast: forecast(mode))
            XCTAssertEqual(analysis.sections.count, 8)
            XCTAssertFalse(analysis.wonder.provider_called)
        }
        let personal = try JSONDecoder().decode(HydrationAnalysis.self, from: fixture("personal"))
        XCTAssertEqual(personal.numerical_forecast.value_ml, 700)
        XCTAssertEqual(personal.numerical_forecast.lower_ml, 645)
        XCTAssertNil(personal.exercise_accounting.value_ml, "A future forecast is not an incurred loss")
        let demo = try JSONDecoder().decode(HydrationAnalysis.self, from: fixture("demo"))
        XCTAssertNil(demo.intake.beverage_volume_ml)
    }
    func testRejectsChangedNumbersFakeMetaCallMislabelingAndInvalidComposition() throws {
        let original = try XCTUnwrap(JSONSerialization.jsonObject(with: fixture("personal")) as? [String: Any])
        func validate(_ body: [String: Any]) throws {
            try JSONDecoder().decode(HydrationAnalysis.self, from: JSONSerialization.data(withJSONObject: body))
                .validate(request: request("personal"), forecast: forecast("personal"))
        }
        var changed = original, numeric = original["numerical_forecast"] as! [String: Any]
        numeric["value_ml"] = 701; changed["numerical_forecast"] = numeric
        XCTAssertThrowsError(try validate(changed))
        changed = original; changed["research_only"] = false
        XCTAssertThrowsError(try validate(changed))
        changed = original; var wonder = original["wonder"] as! [String: Any]; wonder["provider_called"] = true; changed["wonder"] = wonder
        XCTAssertThrowsError(try validate(changed))
        changed = original; var intake = original["intake"] as! [String: Any]; intake["water_ml"] = -1; changed["intake"] = intake
        XCTAssertThrowsError(try validate(changed))
        changed = original; var sections = original["sections"] as! [[String: Any]]; sections[1] = sections[0]; changed["sections"] = sections
        XCTAssertThrowsError(try validate(changed))
        changed = original; sections = original["sections"] as! [[String: Any]]
        var facts = sections[1]["facts"] as! [String: Any]; facts["value_ml"] = 701
        sections[1]["facts"] = facts; changed["sections"] = sections
        XCTAssertThrowsError(try validate(changed), "Detailed cards must not contradict the authoritative numerical result")
    }
    func testPlannedOnlyRequestRejectsCompletedExerciseAccountingEvenWithValidSignedBounds() throws {
        var body = try XCTUnwrap(JSONSerialization.jsonObject(with: fixture("personal")) as? [String: Any])
        body["exercise_accounting"] = ["status": "estimated", "quantity": "logged_intake_minus_measured_exercise_loss",
            "timezone": "UTC", "start_utc": "2026-11-02T14:00:00Z", "end_utc": "2026-11-02T15:00:00Z",
            "value_ml": -500.0, "lower_ml": -600.0, "upper_ml": -400.0, "logged_beverage_volume_ml": 200.0,
            "reasons": [], "provenance": ["manual_measurement"]] as [String: Any]
        let analysis = try JSONDecoder().decode(HydrationAnalysis.self, from: JSONSerialization.data(withJSONObject: body))
        XCTAssertThrowsError(try analysis.validate(request: request("personal"), forecast: forecast("personal")),
                             "A planned-only iPhone request cannot have completed exercise accounting")
    }

    func testEnvironmentAndActivityMustMatchReviewedWorkout() throws {
        let original = try XCTUnwrap(JSONSerialization.jsonObject(with: fixture("personal")) as? [String: Any])
        for field in ["temperature_c", "humidity_percent", "intensity", "duration_minutes", "activity"] {
            var body = original, sections = original["sections"] as! [[String: Any]]
            let isEnvironment = ["temperature_c", "humidity_percent", "intensity"].contains(field)
            let value: Any = field == "intensity" ? "high" : field == "activity" ? "cycling" : 40.0
            if isEnvironment {
                var environment = original["environmental_context"] as! [String: Any]
                environment[field] = value; body["environmental_context"] = environment
                var facts = sections[3]["facts"] as! [String: Any]; facts[field] = value; sections[3]["facts"] = facts
            } else {
                var facts = sections[2]["facts"] as! [String: Any]; facts[field] = value; sections[2]["facts"] = facts
            }
            body["sections"] = sections
            let analysis = try JSONDecoder().decode(HydrationAnalysis.self, from: JSONSerialization.data(withJSONObject: body))
            XCTAssertThrowsError(try analysis.validate(request: request("personal"), forecast: forecast("personal")), field)
        }
    }
    func testResearchProjectionCannotBeLabeledMeasuredEvidence() throws {
        let original = try XCTUnwrap(JSONSerialization.jsonObject(with: fixture("personal")) as? [String: Any])
        for index in [0, 1] {
            var body = original, sections = original["sections"] as! [[String: Any]]
            sections[index]["evidence_status"] = "measured"; body["sections"] = sections
            let analysis = try JSONDecoder().decode(HydrationAnalysis.self, from: JSONSerialization.data(withJSONObject: body))
            XCTAssertThrowsError(try analysis.validate(request: request("personal"), forecast: forecast("personal")))
        }
    }

    func testHTTPAnalysisSendsOnlyReviewedManualRequestAndNeverRetriesAnError() async throws {
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        let config = APIConfiguration(baseURL: "http://127.0.0.1:8000", token: String(repeating: "t", count: 32), offline: false)
        let service = try HTTPBeverageService(configuration: config, session: URLSession(configuration: options))
        var calls = 0
        FixtureURLProtocol.handler = { request in
            calls += 1
            XCTAssertEqual(request.url?.path, "/v1/hydration-analysis")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Cache-Control"), "no-store")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer " + config.token)
            let data: Data
            if let body = request.httpBody { data = body }
            else {
                let stream = try XCTUnwrap(request.httpBodyStream); stream.open(); defer { stream.close() }
                var body = Data(), buffer = [UInt8](repeating: 0, count: 1024)
                while stream.hasBytesAvailable {
                    let count = stream.read(&buffer, maxLength: buffer.count)
                    if count <= 0 { break }; body.append(contentsOf: buffer.prefix(count))
                }
                data = body
            }
            let body = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            XCTAssertEqual(Set(body.keys), ["mode", "timezone", "exercise", "samples", "calibration_processing_consent"])
            XCTAssertEqual(body["mode"] as? String, "personal")
            XCTAssertEqual(body["calibration_processing_consent"] as? Bool, true)
            XCTAssertEqual((body["samples"] as? [Any])?.count, 1)
            return (503, Data("{}".utf8))
        }
        do { _ = try await service.hydrationAnalysis(request("personal")); XCTFail("Expected a visible backend error") }
        catch ServiceError.server(503) { }
        XCTAssertEqual(calls, 1)
    }

    @MainActor func testInvalidationDiscardsLateAnalysisAndUnavailableEndpointFailsIndependently() async throws {
        let controller = HydrationAnalysisController()
        let result = try JSONDecoder().decode(HydrationAnalysis.self, from: fixture("cold"))
        let request = try request("cold"), forecast = try forecast("cold")
        let service = DelayedAnalysisService()
        let task = Task { await controller.load(request, forecast: forecast, service: service) }
        await fulfillment(of: [service.started], timeout: 2)
        controller.invalidate()
        await service.complete(result)
        await task.value
        XCTAssertNil(controller.result); XCTAssertEqual(controller.state, .idle)
        await controller.load(request, forecast: forecast, service: UnavailableAnalysisService())
        XCTAssertNil(controller.result)
        if case .failed(let text) = controller.state { XCTAssertTrue(text.contains("estimate")) }
        else { XCTFail("Expected independent unavailable state") }
    }
}

private actor DelayedAnalysisService: BeverageService {
    let started = XCTestExpectation(description: "Analysis started")
    private var continuation: CheckedContinuation<HydrationAnalysis, Error>?
    func hydrationAnalysis(_ request: WorkoutForecastRequest) async throws -> HydrationAnalysis {
        try await withCheckedThrowingContinuation { continuation in self.continuation = continuation; started.fulfill() }
    }
    func complete(_ result: HydrationAnalysis) { continuation?.resume(returning: result); continuation = nil }
    func listBeverages() async throws -> [BeverageLog] { [] }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw ServiceError.invalidResponse }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary { throw ServiceError.invalidResponse }
}
private actor UnavailableAnalysisService: BeverageService {
    func listBeverages() async throws -> [BeverageLog] { [] }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw ServiceError.invalidResponse }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary { throw ServiceError.invalidResponse }
}
