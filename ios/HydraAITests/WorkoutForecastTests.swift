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
            XCTAssertEqual(request.url?.path, "/v1/workout-forecasts")
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
