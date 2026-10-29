import Foundation
import XCTest
@testable import HydraAI

private func workoutJSON(mode: String = "synthetic_demo") -> Data {
    Data("""
    {"version":"workout-forecast-v1","status":"estimated","model_version":"synthetic-ridge-v1",
     "quantity":"estimated_sweat_loss","units":"mL","value_ml":600,"lower_ml":400,"upper_ml":800,
     "interval_kind":"synthetic_empirical_prediction_interval","data_sufficiency":"synthetic_only",
     "personalization_status":"not_personalized","sample_count":0,"provenance":["synthetic-fixture"],
     "input_factors":{"duration_minutes":60,"temperature_c":24},"limitations":["not_a_drinking_target"],
     "synthetic":\(mode == "synthetic_demo"),"generated_at":"2026-10-28T12:00:00Z","timezone":"UTC",
     "mode":"\(mode)","mock_explanation":null,
     "explanation_policy":"Meta_may_explain_reviewed_results_only_no_numeric_recalculation"}
    """.utf8)
}

final class WorkoutForecastTests: XCTestCase {
    private let configuration = APIConfiguration(baseURL: "http://127.0.0.1:8000", token: String(repeating: "x", count: 32), offline: false)
    override func tearDown() { FixtureURLProtocol.handler = nil }

    func testDemoRequestContainsNoMeasurementsAndUsesAuthNoStore() async throws {
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        FixtureURLProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/v2/workout-forecasts")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer \(self.configuration.token)")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Cache-Control"), "no-store")
            // URLSession can transfer the encoded body to an input stream.
            let data: Data
            if let body = request.httpBody { data = body }
            else {
                let stream = try XCTUnwrap(request.httpBodyStream); stream.open(); defer { stream.close() }
                var bytes = [UInt8](repeating: 0, count: 4096)
                let count = stream.read(&bytes, maxLength: bytes.count)
                XCTAssertGreaterThan(count, 0); data = Data(bytes.prefix(max(0, count)))
            }
            let body = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            XCTAssertEqual(Set(body.keys), ["mode", "timezone", "samples", "calibration_processing_consent"])
            XCTAssertEqual(body["mode"] as? String, "synthetic_demo")
            XCTAssertEqual((body["samples"] as? [Any])?.count, 0)
            XCTAssertEqual(body["calibration_processing_consent"] as? Bool, false)
            return (200, workoutJSON())
        }
        let service = try HTTPBeverageService(configuration: configuration, session: URLSession(configuration: options))
        let result = try await service.workoutForecast(.demonstration(timezone: "UTC"))
        XCTAssertTrue(result.synthetic); XCTAssertEqual(result.valueMl, 600)
    }

    func testPersonalCalibrationRequiresConsentAndCannotBecomeSynthetic() throws {
        let conditions = WorkoutForecastRequest.Conditions(activity: "running", intensity: "moderate", temperature_c: 20, humidity_percent: 50)
        let sample = WorkoutForecastRequest.Sample(event_id: UUID(), observed_at: "2026-10-27T12:00:00Z", conditions: conditions,
            measurement: .init(pre_mass_kg: 70, post_mass_kg: 69.5, consumed_ml: 250, urine_ml: 0, duration_minutes: 60),
            errors: .init(pre_mass_kg: 0.05, post_mass_kg: 0.05, consumed_ml: 10, urine_ml: 0, duration_minutes: 1))
        let denied = WorkoutForecastRequest(mode: "personal", timezone: "UTC", exercise: nil, samples: [sample], calibration_processing_consent: false)
        XCTAssertThrowsError(try denied.validate())
        let allowed = WorkoutForecastRequest(mode: "personal", timezone: "UTC", exercise: nil, samples: [sample], calibration_processing_consent: true)
        XCTAssertNoThrow(try allowed.validate())
        let forged = WorkoutForecastRequest(mode: "synthetic_demo", timezone: "UTC", exercise: nil, samples: [sample], calibration_processing_consent: true)
        XCTAssertThrowsError(try forged.validate())
    }

    func testRejectsMislabeledInvalidAndUnboundedResponse() throws {
        let valid = String(decoding: workoutJSON(), as: UTF8.self)
        let request = WorkoutForecastRequest.demonstration(timezone: "UTC")
        for (before, after) in [
            ("\"synthetic\":true", "\"synthetic\":false"),
            ("\"units\":\"mL\"", "\"units\":\"L\""),
            ("\"quantity\":\"estimated_sweat_loss\"", "\"quantity\":\"recommended_intake\""),
            ("\"lower_ml\":400", "\"lower_ml\":700"),
            ("\"upper_ml\":800", "\"upper_ml\":1e309"),
            ("\"value_ml\":600", "\"value_ml\":null"),
            ("\"status\":\"estimated\"", "\"status\":\"insufficient_data\""),
            ("\"timezone\":\"UTC\"", "\"timezone\":\"Europe/Paris\""),
            ("2026-10-28T12:00:00Z", "2026-10-28T12:00:00"),
            ("\"sample_count\":0", "\"sample_count\":33")
        ] {
            XCTAssertThrowsError(try JSONDecoder().decode(WorkoutForecast.self,
                from: Data(valid.replacingOccurrences(of: before, with: after).utf8)).validate(request: request), after)
        }
    }

    func testMockExplanationsCannotClaimLiveInferenceOrNumericAuthority() throws {
        let valid = String(decoding: workoutJSON(), as: UTF8.self)
        let explanation = "\"mock_explanation\":{\"version\":\"hydration-explanation-v1\",\"mode\":\"mock\",\"provider\":null,\"model\":null,\"account_id\":null,\"attempt_id\":null,\"prediction\":null,\"explanations\":[\"Reviewed fixture\"]}"
        let withMock = valid.replacingOccurrences(of: "\"mock_explanation\":null", with: explanation)
        let request = WorkoutForecastRequest.demonstration(timezone: "UTC")
        XCTAssertNoThrow(try JSONDecoder().decode(WorkoutForecast.self, from: Data(withMock.utf8)).validate(request: request))
        for (before, after) in [("\"provider\":null", "\"provider\":\"Meta\""),
                                ("\"prediction\":null", "\"prediction\":600"),
                                ("\"mode\":\"mock\"", "\"mode\":\"meta_live\"")] {
            XCTAssertThrowsError(try JSONDecoder().decode(WorkoutForecast.self,
                from: Data(withMock.replacingOccurrences(of: before, with: after).utf8)).validate(request: request))
        }
    }

    func testV2ContextCannotBeSilentlyIgnoredWhenItContainsNumericalOverride() throws {
        let source = String(decoding: workoutJSON(), as: UTF8.self)
        let value = source.replacingOccurrences(of: "\"mock_explanation\":null", with:
            "\"mock_explanation\":null,\"context_comparison\":{\"systems\":{\"C\":{\"prediction\":{\"value_ml\":12345}}}}")
        XCTAssertThrowsError(try JSONDecoder().decode(WorkoutForecast.self, from: Data(value.utf8))
            .validate(request: .demonstration(timezone: "UTC")))
    }

    func testV2ContextValidatesNumbersNullUsageAndStrictInterpretationSchema() throws {
        var outer = try XCTUnwrap(JSONSerialization.jsonObject(with: workoutJSON()) as? [String: Any])
        let numericKeys: Set<String> = ["version", "status", "model_version", "quantity", "units", "value_ml", "lower_ml", "upper_ml", "interval_kind", "sample_count", "synthetic"]
        let prediction = outer.filter { numericKeys.contains($0.key) }
        let interpretation: [String: Any] = ["factors": [], "missing_information": [], "contradictions": [],
            "uncertainty": ["synthetic_evidence_only", "not_daily_requirement"], "measurement_suggestions": [], "numerical_abstention": false,
            "reviewed_text": ["factors": [], "missing_information": [], "contradictions": [],
                              "uncertainty": ["Synthetic fixture only.", "Not a daily requirement."], "measurement_suggestions": []]]
        let comparison: [String: Any] = ["version": "hydration-context-comparison-v2", "scenario": "complete", "synthetic": true,
            "provenance": ["mode": "mock", "provider": NSNull(), "model": NSNull(), "candidate_model": "muse-spark-1.3", "candidate_tier": "Standard",
                           "model_identity_verified": false, "live_dispatch_enabled": false, "interpretation_origin": "local_rules_and_reviewed_text"],
            "provider_observations": ["latency_ms": NSNull(), "input_tokens": NSNull(), "output_tokens": NSNull(), "billed_cost_usd": NSNull()],
            "systems": ["A": ["prediction": prediction, "interpretation": NSNull()],
                        "B": ["prediction": NSNull(), "interpretation": interpretation],
                        "C": ["prediction": prediction, "interpretation": interpretation]], "limitations": ["Not a Meta observation."]]
        outer["context_comparison"] = comparison
        let request = WorkoutForecastRequest.demonstration(timezone: "UTC")
        func validate(_ body: [String: Any]) throws {
            try JSONDecoder().decode(WorkoutForecast.self, from: JSONSerialization.data(withJSONObject: body)).validate(request: request)
        }
        XCTAssertNoThrow(try validate(outer))
        var wrongNumbers = comparison
        var badPrediction = prediction; badPrediction["value_ml"] = 650
        wrongNumbers["systems"] = ["A": ["prediction": prediction, "interpretation": NSNull()],
            "B": ["prediction": NSNull(), "interpretation": interpretation], "C": ["prediction": badPrediction, "interpretation": interpretation]]
        var mutated = outer; mutated["context_comparison"] = wrongNumbers
        XCTAssertThrowsError(try validate(mutated))
        var wrongUsage = comparison
        wrongUsage["provider_observations"] = ["latency_ms": 20, "input_tokens": NSNull(), "output_tokens": NSNull(), "billed_cost_usd": NSNull()]
        mutated["context_comparison"] = wrongUsage
        XCTAssertThrowsError(try validate(mutated))
        var inventedGoal = interpretation; inventedGoal["daily_goal_ml"] = 3000
        var wrongContext = comparison
        wrongContext["systems"] = ["A": ["prediction": prediction, "interpretation": NSNull()],
            "B": ["prediction": NSNull(), "interpretation": inventedGoal], "C": ["prediction": prediction, "interpretation": inventedGoal]]
        mutated["context_comparison"] = wrongContext
        XCTAssertThrowsError(try validate(mutated), "Unknown quantitative advice must not be silently accepted")
    }

    func testV2PersonalColdStartRequiresConsistentSessionHistoryMetadata() throws {
        var body = try XCTUnwrap(JSONSerialization.jsonObject(with: workoutJSON(mode: "personal")) as? [String: Any])
        body["model_version"] = "personal-longitudinal-v2"; body["interval_kind"] = "historical_error_envelope"
        body["status"] = "insufficient_data"; body["value_ml"] = NSNull(); body["lower_ml"] = NSNull(); body["upper_ml"] = NSNull()
        let request = WorkoutForecastRequest(mode: "personal", timezone: "UTC", exercise: nil, samples: [], calibration_processing_consent: false)
        func validate(_ body: [String: Any]) throws {
            try JSONDecoder().decode(WorkoutForecast.self, from: JSONSerialization.data(withJSONObject: body)).validate(request: request)
        }
        XCTAssertThrowsError(try validate(body))
        var history: [String: Any] = ["total_samples": 0, "comparable_samples": 0, "recent_samples": 0,
            "first_observed_at": NSNull(), "last_observed_at": NSNull(),
            "method": "recent_comparable_median_with_historical_error_envelope", "history_retained_by_caller": true]
        body["longitudinal_history"] = history
        XCTAssertNoThrow(try validate(body))
        history["total_samples"] = 1; body["longitudinal_history"] = history
        XCTAssertThrowsError(try validate(body))
    }

    private func recordedWonder() throws -> [String: Any] {
        let outer = try XCTUnwrap(JSONSerialization.jsonObject(with: workoutJSON()) as? [String: Any])
        let numericKeys: Set<String> = ["version", "status", "model_version", "quantity", "units", "value_ml", "lower_ml", "upper_ml", "interval_kind", "sample_count", "synthetic"]
        let prediction = outer.filter { numericKeys.contains($0.key) }
        let interpretation: [String: Any] = ["factors": ["workout_duration"], "missing_information": [], "contradictions": [],
            "uncertainty": ["synthetic_evidence_only", "not_daily_requirement"], "measurement_suggestions": [], "numerical_abstention": false,
            "reviewed_text": ["factors": ["Workout duration provides context."], "missing_information": [], "contradictions": [],
                              "uncertainty": ["Synthetic scenario.", "Not a daily requirement."], "measurement_suggestions": []]]
        return ["version": "hydration-context-comparison-v2", "scenario": "complete", "synthetic": true,
            "provenance": ["mode": "meta_live", "provider": "Meta", "model": "muse-wonder-1.0", "candidate_model": "muse-wonder-1.0",
                           "candidate_tier": "Standard", "model_identity_verified": true, "live_dispatch_enabled": true,
                           "interpretation_origin": "meta_selection_and_reviewed_text", "account_id": "georgiosaliba227",
                           "attempt_id": UUID().uuidString.lowercased()],
            "provider_observations": ["latency_ms": 812, "input_tokens": 900, "output_tokens": 120,
                                      "usage_derived_cost_micro_usd": 6000, "billed_cost_usd": NSNull()],
            "systems": ["A": ["prediction": prediction, "interpretation": NSNull()],
                        "B": ["prediction": NSNull(), "interpretation": interpretation],
                        "C": ["prediction": prediction, "interpretation": interpretation]], "limitations": ["Recorded result."]]
    }

    private func decodeComparison(_ body: [String: Any]) throws -> HydrationContextComparison {
        try JSONDecoder().decode(HydrationContextComparison.self, from: JSONSerialization.data(withJSONObject: body))
    }

    func testRecordedWonderResultValidatesAndRejectsTampering() throws {
        let valid = try recordedWonder()
        XCTAssertNoThrow(try decodeComparison(valid).validateRecorded())
        func provenance(_ key: String, _ value: Any) -> [String: Any] {
            var body = valid; var item = body["provenance"] as! [String: Any]; item[key] = value; body["provenance"] = item; return body
        }
        func observation(_ key: String, _ value: Any) -> [String: Any] {
            var body = valid; var item = body["provider_observations"] as! [String: Any]; item[key] = value; body["provider_observations"] = item; return body
        }
        for tampered in [provenance("model", "muse-spark-1.3"), provenance("mode", "mock"), provenance("account_id", "someone-else"),
                         provenance("attempt_id", "not-a-uuid"), provenance("model_identity_verified", false),
                         observation("billed_cost_usd", 0.01), observation("input_tokens", -1), observation("latency_ms", NSNull())] {
            XCTAssertThrowsError(try decodeComparison(tampered).validateRecorded())
        }
        var changedNumbers = valid
        var systems = valid["systems"] as! [String: Any]
        var c = systems["C"] as! [String: Any]; var cPrediction = c["prediction"] as! [String: Any]
        cPrediction["value_ml"] = 9999; c["prediction"] = cPrediction; systems["C"] = c; changedNumbers["systems"] = systems
        XCTAssertThrowsError(try decodeComparison(changedNumbers).validateRecorded(), "Wonder must never change the numbers")
    }

    @MainActor func testRecordedWonderControllerReportsMissingRecordAndLoadsValidResult() async throws {
        let controller = RecordedWonderController()
        await controller.load(service: RecordedWonderService(result: .failure(ServiceError.server(404))))
        XCTAssertNil(controller.result)
        XCTAssertEqual(controller.state, .failed("No recorded Muse Wonder result is available yet."))
        let valid = try decodeComparison(try recordedWonder())
        await controller.load(service: RecordedWonderService(result: .success(valid)))
        XCTAssertEqual(controller.state, .loaded)
        XCTAssertEqual(controller.result?.provenance.model, "muse-wonder-1.0")
        controller.invalidate()
        XCTAssertNil(controller.result); XCTAssertEqual(controller.state, .idle)
    }

    @MainActor func testInvalidationDiscardsLateForecastAndClearsLoadedResult() async throws {
        let controller = WorkoutForecastController()
        let service = DelayedWorkoutService()
        let task = Task { await controller.load(.demonstration(timezone: "UTC"), service: service) }
        await fulfillment(of: [service.started], timeout: 2)
        controller.invalidate() // same invalidation used for connection changes, edits and leaving screen
        await service.complete()
        await task.value
        XCTAssertNil(controller.result); XCTAssertEqual(controller.state, .idle)
    }

    @MainActor func testUnavailableEndpointShowsIndependentFailure() async {
        let controller = WorkoutForecastController()
        await controller.load(.demonstration(timezone: "UTC"), service: UnsupportedWorkoutService())
        XCTAssertNil(controller.result)
        if case .failed(let message) = controller.state { XCTAssertTrue(message.contains("Beverage logging still works")) }
        else { XCTFail("Expected unavailable state") }
    }
}

private actor DelayedWorkoutService: BeverageService {
    let started = XCTestExpectation(description: "Workout request started")
    private var continuation: CheckedContinuation<WorkoutForecast, Error>?
    func workoutForecast(_ request: WorkoutForecastRequest) async throws -> WorkoutForecast {
        try await withCheckedThrowingContinuation { continuation in self.continuation = continuation; started.fulfill() }
    }
    func complete() {
        continuation?.resume(returning: try! JSONDecoder().decode(WorkoutForecast.self, from: workoutJSON()))
        continuation = nil
    }
    func listBeverages() async throws -> [BeverageLog] { [] }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw ServiceError.invalidResponse }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary { throw ServiceError.invalidResponse }
}

private actor UnsupportedWorkoutService: BeverageService {
    func listBeverages() async throws -> [BeverageLog] { [] }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw ServiceError.invalidResponse }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary { throw ServiceError.invalidResponse }
}

private actor RecordedWonderService: BeverageService {
    let result: Result<HydrationContextComparison, Error>
    init(result: Result<HydrationContextComparison, Error>) { self.result = result }
    func recordedWonderComparison(scenario: String) async throws -> HydrationContextComparison { try result.get() }
    func listBeverages() async throws -> [BeverageLog] { [] }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw ServiceError.invalidResponse }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary { throw ServiceError.invalidResponse }
}
