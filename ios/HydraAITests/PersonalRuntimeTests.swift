import XCTest
@testable import HydraAI

final class PersonalRuntimeTests: XCTestCase {
    private func data(_ name: String, _ kind: String) throws -> Data {
        try Data(contentsOf: XCTUnwrap(Bundle(for: Self.self).url(forResource: "runtime-v3-" + name + "-" + kind, withExtension: "json")))
    }
    private func request(_ name: String) throws -> WorkoutForecastRequest {
        if name == "synthetic" { return .demonstration(timezone: "UTC") }
        let body = try JSONSerialization.jsonObject(with: data(name, "request")) as! [String: Any]
        let exercise = body["exercise"] as! [String: Any]
        return .init(mode: "personal", timezone: "UTC", exercise: .init(event_id: UUID(uuidString: exercise["event_id"] as! String)!,
            starts_at: exercise["starts_at"] as! String, duration_minutes: exercise["duration_minutes"] as! Double,
            conditions: try JSONDecoder().decode(WorkoutForecastRequest.Conditions.self, from: JSONSerialization.data(withJSONObject: exercise["conditions"]!)),
            comparable_conditions_confirmed: true),
            samples: try JSONDecoder().decode([WorkoutForecastRequest.Sample].self, from: JSONSerialization.data(withJSONObject: body["samples"]!)), calibration_processing_consent: true)
    }
    private func forecast(_ name: String) throws -> WorkoutForecast { try JSONDecoder().decode(WorkoutForecast.self, from: data(name, "forecast")) }

    func testRealRuntimeFixturesKeepSelectedFitBaselineAndSyntheticDistinct() throws {
        XCTAssertFalse(WorkoutDraft().experimentalPersonalModel)
        for name in ["selected", "fallback", "partial-fold", "synthetic"] {
            let request = try request(name), forecast = try forecast(name)
            try forecast.validate(request: request, workflow: .experimentalRuntime)
            let analysis = try JSONDecoder().decode(HydrationAnalysis.self, from: data(name, "analysis"))
            try analysis.validate(request: request, forecast: forecast, workflow: .experimentalRuntime)
            let preview = try JSONDecoder().decode(WonderAnalysisPreview.self, from: data(name, "preview"))
            try preview.validate(request: request, forecast: forecast, workflow: .experimentalRuntime)
            XCTAssertFalse(preview.live_available)
        }
        XCTAssertEqual(try forecast("selected").learning?.selectedMethod, .fitted)
        XCTAssertEqual(try forecast("selected").learning?.title, "Experimental personal fit selected")
        XCTAssertTrue(try XCTUnwrap(forecast("selected").learning?.reasonText).contains("not independent accuracy validation"))
        XCTAssertEqual(try forecast("selected").valueMl, 441.6666666666667)
        XCTAssertEqual(try forecast("fallback").learning?.selectedMethod, .baseline)
        XCTAssertEqual(try forecast("partial-fold").learning?.trainingSamples, 0)
        XCTAssertEqual(try forecast("partial-fold").learning?.validationFolds, 1)
        XCTAssertEqual(try forecast("partial-fold").learning?.reason, .folds)
        XCTAssertNil(try forecast("synthetic").learning)
    }
    func testMalformedLearningCannotInventSelectionCoverageOrExtraFields() throws {
        let original = try JSONSerialization.jsonObject(with: data("selected", "forecast")) as! [String: Any]
        for mutation in ["missing", "extra", "coverage", "alpha", "count", "folds", "hash", "domain", "gain", "method", "history", "research", "actual"] {
            var body = original, learning = original["learning"] as! [String: Any]
            switch mutation {
            case "missing": learning.removeValue(forKey: "training_sha256")
            case "extra": learning["accuracy_percent"] = 99
            case "coverage": learning["nominal_coverage"] = 0.95
            case "alpha": learning["ridge_alpha"] = 2
            case "count": learning["training_samples"] = 33
            case "folds": learning["validation_folds"] = 2
            case "hash": learning["training_sha256"] = "not-a-hash"
            case "domain": learning["supported_duration_minutes"] = ["minimum": 70.0, "maximum": 80.0]
            case "gain": learning["paired_gain_ml"] = -1
            case "method": learning["selected_method"] = "existing_personal_baseline"
            case "history": var history = original["longitudinal_history"] as! [String: Any]; history["method"] = "recent_comparable_median_with_historical_error_envelope"; body["longitudinal_history"] = history
            case "actual": learning["reason"] = "actual_measurement_preserved"
            default: body["research_only"] = false
            }
            body["learning"] = learning
            XCTAssertThrowsError(try JSONDecoder().decode(WorkoutForecast.self, from: JSONSerialization.data(withJSONObject: body)).validate(request: request("selected"), workflow: .experimentalRuntime), mutation)
        }
    }
    @MainActor func testRuntime404NeverCallsLegacyForecastAsFallback() async throws {
        let service = RefusedRuntimeService(legacy: try forecast("selected"))
        let controller = WorkoutForecastController()
        await controller.load(try request("selected"), service: service, workflow: .experimentalRuntime)
        let calls = await service.calls()
        XCTAssertEqual(calls.0, 1); XCTAssertEqual(calls.1, 0)
        XCTAssertNil(controller.result)
        if case .failed = controller.state { } else { XCTFail("Unavailable v3 must fail visibly") }
    }
    func testNonmatchingSuppliedSampleCannotInventAnExtraFittedValidationFold() throws {
        let base = try request("selected"), first = try XCTUnwrap(base.samples.first)
        let older = try XCTUnwrap(CalibrationHistoryValidation.date(first.observed_at)).addingTimeInterval(-86400)
        let nonmatching = WorkoutForecastRequest.Sample(event_id: UUID(), observed_at: ISO8601DateFormatter().string(from: older),
            conditions: .init(activity: "cycling", intensity: "moderate", temperature_c: 22, humidity_percent: 55),
            measurement: first.measurement, errors: first.errors)
        let request = WorkoutForecastRequest(mode: base.mode, timezone: base.timezone, exercise: base.exercise,
            samples: base.samples + [nonmatching], calibration_processing_consent: true)
        var body = try JSONSerialization.jsonObject(with: data("selected", "forecast")) as! [String: Any]
        var learning = body["learning"] as! [String: Any], history = body["longitudinal_history"] as! [String: Any]
        learning["validation_folds"] = 4; history["total_samples"] = 7
        body["learning"] = learning; body["longitudinal_history"] = history
        let changed = try JSONDecoder().decode(WorkoutForecast.self, from: JSONSerialization.data(withJSONObject: body))
        XCTAssertThrowsError(try changed.validate(request: request, workflow: .experimentalRuntime))
    }

    override func tearDown() { FixtureURLProtocol.handler = nil }
    func testRuntimeAnalysisRejectsDifferentLearningNumbersAndRootDuplication() throws {
        let original = try JSONSerialization.jsonObject(with: data("selected", "analysis")) as! [String: Any]
        for mutation in ["root", "learning", "number", "embedded_wonder"] {
            var body = original, numeric = original["numerical_forecast"] as! [String: Any]
            switch mutation {
            case "root": body["learning"] = numeric["learning"]
            case "learning": var learning = numeric["learning"] as! [String: Any]; learning["training_sha256"] = String(repeating: "a", count: 64); numeric["learning"] = learning
            case "embedded_wonder": var wonder = original["wonder"] as! [String: Any]; wonder["status"] = "preview_only"; body["wonder"] = wonder
            default: numeric["value_ml"] = 442
            }
            body["numerical_forecast"] = numeric
            XCTAssertThrowsError(try JSONDecoder().decode(HydrationAnalysis.self, from: JSONSerialization.data(withJSONObject: body)).validate(request: request("selected"), forecast: forecast("selected"), workflow: .experimentalRuntime), mutation)
        }
    }
    func testFittedRateScalesByFractionalDurationWithFiniteTolerance() throws {
        let original = try JSONSerialization.jsonObject(with: data("selected", "forecast")) as! [String: Any]
        let base = try request("selected"), exercise = try XCTUnwrap(base.exercise)
        for duration in [0.5, 1.5, 59.99, 60.01] {
            var body = original, learning = original["learning"] as! [String: Any]
            learning["supported_duration_minutes"] = ["minimum": 0.5, "maximum": 90.0]
            body["learning"] = learning
            let point = 441.6666666666667 * duration / 60
            body["value_ml"] = point; body["lower_ml"] = 0; body["upper_ml"] = max(700, point)
            let request = WorkoutForecastRequest(mode: base.mode, timezone: base.timezone,
                exercise: .init(event_id: exercise.event_id, starts_at: exercise.starts_at, duration_minutes: duration,
                    conditions: exercise.conditions, comparable_conditions_confirmed: true), samples: base.samples, calibration_processing_consent: true)
            let forecast = try JSONDecoder().decode(WorkoutForecast.self, from: JSONSerialization.data(withJSONObject: body))
            try forecast.validate(request: request, workflow: .experimentalRuntime)
        }
    }
    func testAllV3HTTPPathsKeepOneVersionWithoutRetryOrLegacyFallback() async throws {
        let fixtures = try ["/v3/workout-forecasts": data("selected", "forecast"), "/v3/hydration-analysis": data("selected", "analysis"), "/v3/wonder/analysis/preview": data("selected", "preview")]
        var paths: [String] = []
        FixtureURLProtocol.handler = { request in
            let path = request.url!.path; paths.append(path)
            XCTAssertEqual(request.httpMethod, "POST"); XCTAssertEqual(request.value(forHTTPHeaderField: "Cache-Control"), "no-store")
            if let fixture = fixtures[path] { return (200, fixture) }
            XCTAssertEqual(path, "/v3/wonder/analysis")
            return (503, Data("{\"code\":\"wonder_unavailable\"}".utf8))
        }
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        let service = try HTTPBeverageService(configuration: .init(baseURL: "http://127.0.0.1:8000", token: String(repeating: "x", count: 32), offline: false), session: URLSession(configuration: options))
        let request = try request("selected")
        _ = try await service.workoutForecastV3(request)
        _ = try await service.hydrationAnalysisV3(request)
        let preview = try await service.wonderAnalysisPreviewV3(request)
        do { _ = try await service.explainHydrationAnalysisV3(.init(forecast: request, payload_sha256: preview.payload_sha256)); XCTFail("Expected disabled dispatch") }
        catch let error as WonderRequestError { XCTAssertEqual(error.status, 503) }
        XCTAssertEqual(paths, ["/v3/workout-forecasts", "/v3/hydration-analysis", "/v3/wonder/analysis/preview", "/v3/wonder/analysis"])
    }
    func testComparisonUsesPythonTiesToEvenForHalfUnitInputs() throws {
        var body = try JSONSerialization.jsonObject(with: data("selected", "preview")) as! [String: Any]
        var facts = body["facts"] as! [String: Any]
        var activity = facts["activity"] as! [String: Any], environment = facts["environment"] as! [String: Any]
        activity["duration_minutes"] = 60.5; environment["temperature_c"] = 22.5; environment["humidity_percent"] = 54.5
        facts["activity"] = activity; facts["environment"] = environment
        facts["workout_comparison"] = ["planned_duration_minutes": 60, "typical_duration_minutes": 60, "planned_temperature_c": 22, "typical_temperature_c": 22, "planned_humidity_percent": 54, "typical_humidity_percent": 54]
        body["facts"] = facts
        let original = try request("selected"), exercise = try XCTUnwrap(original.exercise)
        let request = WorkoutForecastRequest(mode: "personal", timezone: "UTC", exercise: .init(event_id: exercise.event_id, starts_at: exercise.starts_at, duration_minutes: 60.5, conditions: .init(activity: "running", intensity: "moderate", temperature_c: 22.5, humidity_percent: 54.5), comparable_conditions_confirmed: true), samples: original.samples, calibration_processing_consent: true)
        // Use the baseline fixture: only comparison rounding is under test, not a refit.
        var baseline = try JSONSerialization.jsonObject(with: data("fallback", "forecast")) as! [String: Any]
        baseline.removeValue(forKey: "learning"); baseline.removeValue(forKey: "research_only")
        let forecast = try JSONDecoder().decode(WorkoutForecast.self, from: JSONSerialization.data(withJSONObject: baseline))
        var numeric = facts["forecast"] as! [String: Any]
        numeric["value_ml"] = 400; numeric["lower_ml"] = 380; numeric["upper_ml"] = 420; numeric["interval_kind"] = "historical_error_envelope"
        facts["forecast"] = numeric
        let changed = try JSONDecoder().decode(WonderAnalysisFacts.self, from: JSONSerialization.data(withJSONObject: facts))
        try changed.validate(request: request, forecast: forecast)
    }
    func testPositiveLoggedDaysRequireNonNullBoundsBeforeRendering() throws {
        let preview = try JSONSerialization.jsonObject(with: data("selected", "preview")) as! [String: Any]
        var facts = preview["facts"] as! [String: Any], trends = facts["trends"] as! [String: Any]
        trends["logged_days"] = 1; trends["beverage_lower_ml"] = NSNull(); trends["beverage_upper_ml"] = NSNull(); facts["trends"] = trends
        let changed = try JSONDecoder().decode(WonderAnalysisFacts.self, from: JSONSerialization.data(withJSONObject: facts))
        XCTAssertThrowsError(try changed.validateShape())
        XCTAssertThrowsError(try WonderAnalysisRenderer.placeholders(changed))
    }

    func testV3PreviewRequiresMarkerAndRoundedNumericBinding() throws {
        let original = try JSONSerialization.jsonObject(with: data("selected", "preview")) as! [String: Any]
        for mutation in ["marker", "number", "raw_point"] {
            var body = original
            if mutation == "marker" { body.removeValue(forKey: "numerical_contract") }
            else {
                var facts = original["facts"] as! [String: Any], numeric = facts["forecast"] as! [String: Any]
                numeric["value_ml"] = mutation == "number" ? 443 : 441.6666666666667
                facts["forecast"] = numeric; body["facts"] = facts
            }
            XCTAssertThrowsError(try JSONDecoder().decode(WonderAnalysisPreview.self, from: JSONSerialization.data(withJSONObject: body)).validate(request: request("selected"), forecast: forecast("selected"), workflow: .experimentalRuntime), mutation)
        }
    }
}

private actor RefusedRuntimeService: BeverageService {
    let legacy: WorkoutForecast
    var runtimeCalls = 0, legacyCalls = 0
    init(legacy: WorkoutForecast) { self.legacy = legacy }
    func calls() -> (Int, Int) { (runtimeCalls, legacyCalls) }
    func workoutForecastV3(_ request: WorkoutForecastRequest) async throws -> WorkoutForecast { runtimeCalls += 1; throw ServiceError.server(404) }
    func workoutForecast(_ request: WorkoutForecastRequest) async throws -> WorkoutForecast { legacyCalls += 1; return legacy }
    func listBeverages() async throws -> [BeverageLog] { [] }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw ServiceError.invalidResponse }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary { throw ServiceError.invalidResponse }
}
