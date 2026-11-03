import XCTest
@testable import HydraAI

/// Synthetic fixtures and in-memory fake transport only. No inference, account or billing evidence.
final class WonderAnalysisTests: XCTestCase {
    override func tearDown() { FixtureURLProtocol.handler = nil }
    private func assertCalls(_ expected: Int, service: AnalysisWonderStub) async {
        let actual = await service.explainCount
        XCTAssertEqual(actual, expected)
    }
    private func data(_ name: String) throws -> Data {
        try Data(contentsOf: XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "json")))
    }
    private func preview(live: Bool = true, saved: Bool = false) throws -> WonderAnalysisPreview {
        var body = try JSONSerialization.jsonObject(with: data(saved ? "wonder-analysis-saved-preview-fake" : "wonder-analysis-preview")) as! [String: Any]
        body["live_available"] = live; body["dispatch_supported"] = live
        if live { body["account_id"] = "georgiosaliba227" }
        return try JSONDecoder().decode(WonderAnalysisPreview.self, from: JSONSerialization.data(withJSONObject: body))
    }
    private func response() throws -> WonderAnalysisResponse { try JSONDecoder().decode(WonderAnalysisResponse.self, from: data("wonder-analysis-result-fake")) }
    private func request() throws -> WorkoutForecastRequest {
        let body = try JSONSerialization.jsonObject(with: data("hydration-analysis-personal-request")) as! [String: Any]
        let exercise = body["exercise"] as! [String: Any]
        return .init(mode: "personal", timezone: "UTC", exercise: .init(event_id: UUID(), starts_at: exercise["starts_at"] as! String,
            duration_minutes: 30, conditions: .init(activity: "running", intensity: "moderate", temperature_c: 20, humidity_percent: 60),
            comparable_conditions_confirmed: true),
            samples: try JSONDecoder().decode([WorkoutForecastRequest.Sample].self, from: JSONSerialization.data(withJSONObject: body["samples"]!)),
            calibration_processing_consent: true)
    }
    private func forecast() throws -> WorkoutForecast {
        let body = try JSONSerialization.jsonObject(with: data("hydration-analysis-personal")) as! [String: Any]
        var numeric = body["numerical_forecast"] as! [String: Any]
        numeric["generated_at"] = body["generated_at"]; numeric["timezone"] = "UTC"; numeric["mode"] = "personal"
        numeric["explanation_policy"] = "Meta_may_explain_reviewed_results_only_no_numeric_recalculation"
        return try JSONDecoder().decode(WorkoutForecast.self, from: JSONSerialization.data(withJSONObject: numeric))
    }
    func testPreviewRejectsHiddenFactsChangedNumbersAndFalseCostAttestation() throws {
        let original = try JSONSerialization.jsonObject(with: data("wonder-analysis-preview")) as! [String: Any]
        try preview(live: false).validate(request: request(), forecast: forecast())
        for mutation in ["hidden", "number", "cost", "environment"] {
            var body = original, facts = original["facts"] as! [String: Any]
            switch mutation {
            case "hidden": facts["body_mass_kg"] = 70
            case "number": var numeric = facts["forecast"] as! [String: Any]; numeric["value_ml"] = 701; facts["forecast"] = numeric
            case "environment": var c = facts["environment"] as! [String: Any]; c["temperature_c"] = 40; facts["environment"] = c
            default: body["verified_for_billing"] = true
            }
            body["facts"] = facts
            let changed = try JSONDecoder().decode(WonderAnalysisPreview.self, from: JSONSerialization.data(withJSONObject: body))
            XCTAssertThrowsError(try changed.validate(request: request(), forecast: forecast()), mutation)
        }
    }
    func testRejectsInventedRenderedTextTemplatesLimitationsAndInapplicableFindings() throws {
        let original = try JSONSerialization.jsonObject(with: data("wonder-analysis-result-fake")) as! [String: Any]
        for mutation in ["section_text", "insight_text", "section_template", "limitation", "loss_no_estimate", "known_water", "environment_shift", "weekly_change"] {
            var result = original["result"] as! [String: Any], sections = result["sections"] as! [[String: Any]]
            if mutation == "section_text" { sections[0]["text"] = "Drink 5000 mL." }
            if mutation == "section_template" { sections[0]["template"] = "Drink 5000 mL." }
            if mutation == "limitation" { result["limitations"] = ["Drink 5000 mL."] }
            if mutation == "insight_text" { var insights = sections[0]["insights"] as! [[String: Any]]; insights[0]["text"] = "The estimate is 701 mL."; sections[0]["insights"] = insights }
            let replacement: (Int, String, String, String)?
            switch mutation {
            case "loss_no_estimate": replacement = (1, "loss_no_estimate", "Numerical abstention", "{loss_estimate}.")
            case "known_water": replacement = (4, "beverage_water_known", "Documented water", "{water_context}.")
            case "environment_shift": replacement = (3, "environment_shift", "Different historical conditions", "{environment_comparison}.")
            case "weekly_change": replacement = (5, "trends_week_change", "Logged weekly comparison", "{weekly_comparison}.")
            default: replacement = nil
            }
            if let (index, id, title, template) = replacement {
                var insights = sections[index]["insights"] as! [[String: Any]]
                insights[0]["id"] = id; insights[0]["title"] = title; insights[0]["template"] = template; sections[index]["insights"] = insights
            }
            result["sections"] = sections
            let changed = try JSONDecoder().decode(WonderAnalysisResult.self, from: JSONSerialization.data(withJSONObject: result))
            XCTAssertThrowsError(try changed.validate(), mutation)
        }
    }

    func testNativeRendererPreservesFractionalMinutesAndRoundsOnlyLossDisplay() throws {
        let original = try JSONSerialization.jsonObject(with: data("wonder-analysis-preview")) as! [String: Any]
        let baseFacts = original["facts"] as! [String: Any]
        for (minutes, expected) in [(0.5, "0.5"), (1.5, "1.5"), (0.01, "0.01")] {
            var body = baseFacts, activity = baseFacts["activity"] as! [String: Any]
            activity["duration_minutes"] = minutes; body["activity"] = activity
            var comparison = baseFacts["workout_comparison"] as! [String: Any]
            comparison["planned_duration_minutes"] = max(1, minutes.rounded(.toNearestOrAwayFromZero)); body["workout_comparison"] = comparison
            let facts = try JSONDecoder().decode(WonderAnalysisFacts.self, from: JSONSerialization.data(withJSONObject: body))
            XCTAssertEqual(try WonderAnalysisRenderer.placeholders(facts)["activity_context"], "\(expected) minutes of moderate running")
        }
        var body = baseFacts, forecast = baseFacts["forecast"] as! [String: Any]
        forecast["value_ml"] = 700.5; forecast["lower_ml"] = 645.1; forecast["upper_ml"] = 755.1; body["forecast"] = forecast
        var environment = baseFacts["environment"] as! [String: Any]
        environment["temperature_c"] = 20.25; environment["humidity_percent"] = 60.25; body["environment"] = environment
        let facts = try JSONDecoder().decode(WonderAnalysisFacts.self, from: JSONSerialization.data(withJSONObject: body))
        let rendered = try WonderAnalysisRenderer.placeholders(facts)
        XCTAssertEqual(rendered["loss_estimate"], "research estimate 645 to 756 mL, with point 700 mL")
        XCTAssertEqual(rendered["environment_context"], "temperature 20.2 °C; humidity 60.2%")
    }

    @MainActor func testDefaultOffAndMissingConsentNeverDispatch() async throws {
        let service = AnalysisWonderStub(preview: try preview(live: false), response: try response())
        let controller = WonderAnalysisController()
        await controller.loadPreview(try request(), forecast: try forecast(), service: service)
        XCTAssertNotNil(controller.preview); XCTAssertFalse(controller.canOffer)
        await controller.explain(consent: true, service: service)
        await assertCalls(0, service: service)
        await service.setPreview(try preview())
        await controller.loadPreview(try request(), forecast: try forecast(), service: service)
        XCTAssertTrue(controller.canOffer)
        await controller.explain(consent: false, service: service)
        await assertCalls(0, service: service)
    }
    @MainActor func testSavedPreviewReplaysAllEightSectionsWithoutDispatch() async throws {
        let service = AnalysisWonderStub(preview: try preview(saved: true), response: try response())
        let controller = WonderAnalysisController()
        await controller.loadPreview(try request(), forecast: try forecast(), service: service)
        XCTAssertEqual(controller.result?.sections.count, 8); XCTAssertTrue(controller.replayed)
        XCTAssertFalse(controller.canOffer)
        XCTAssertTrue(controller.result?.sections.allSatisfy { (1...3).contains($0.insights.count) } == true)
        await controller.explain(consent: true, service: service)
        await assertCalls(0, service: service)
    }
    @MainActor func testAmbiguousTransportQuarantinesDigestAcrossInvalidationAndRefresh() async throws {
        let service = AnalysisWonderStub(preview: try preview(), response: try response(), failure: URLError(.timedOut))
        let controller = WonderAnalysisController()
        await controller.loadPreview(try request(), forecast: try forecast(), service: service)
        await controller.explain(consent: true, service: service)
        XCTAssertTrue(controller.isQuarantined); XCTAssertFalse(controller.canOffer)
        controller.invalidate()
        await controller.loadPreview(try request(), forecast: try forecast(), service: service)
        XCTAssertTrue(controller.isQuarantined)
        await controller.explain(consent: true, service: service)
        await assertCalls(1, service: service)
        await service.setPreview(try preview(saved: true))
        await controller.loadPreview(try request(), forecast: try forecast(), service: service)
        XCTAssertNotNil(controller.result); XCTAssertTrue(controller.replayed)
        await assertCalls(1, service: service)
    }
    @MainActor func testKnownSafeStaleResponseRequiresExplicitNewPreviewAndNoAutomaticRetry() async throws {
        let service = AnalysisWonderStub(preview: try preview(), response: try response(),
                                         failure: WonderRequestError(status: 409, code: "analysis_preview_stale"))
        let controller = WonderAnalysisController()
        await controller.loadPreview(try request(), forecast: try forecast(), service: service)
        await controller.explain(consent: true, service: service)
        XCTAssertNil(controller.preview); XCTAssertFalse(controller.canOffer)
        await assertCalls(1, service: service)
        await controller.loadPreview(try request(), forecast: try forecast(), service: service)
        XCTAssertFalse(controller.isQuarantined); XCTAssertTrue(controller.canOffer)
    }
    @MainActor func testHTTPExplainUsesExactConsentedPayloadAndQuarantinesUnknownServerFailure() async throws {
        var previewBody = try JSONSerialization.jsonObject(with: data("wonder-analysis-preview")) as! [String: Any]
        previewBody["live_available"] = true; previewBody["dispatch_supported"] = true; previewBody["account_id"] = "georgiosaliba227"
        let previewData = try JSONSerialization.data(withJSONObject: previewBody)
        let digest = previewBody["payload_sha256"] as! String
        var sends = 0
        FixtureURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Cache-Control"), "no-store")
            if request.url?.path == "/v1/wonder/analysis/preview" { return (200, previewData) }
            XCTAssertEqual(request.url?.path, "/v1/wonder/analysis")
            sends += 1
            let bodyData: Data
            if let data = request.httpBody { bodyData = data }
            else {
                let stream = try XCTUnwrap(request.httpBodyStream); stream.open(); defer { stream.close() }
                var data = Data(), buffer = [UInt8](repeating: 0, count: 1024)
                while stream.hasBytesAvailable { let n = stream.read(&buffer, maxLength: buffer.count); if n <= 0 { break }; data.append(contentsOf: buffer.prefix(n)) }
                bodyData = data
            }
            let body = try XCTUnwrap(JSONSerialization.jsonObject(with: bodyData) as? [String: Any])
            XCTAssertEqual(Set(body.keys), ["mode", "timezone", "exercise", "samples", "calibration_processing_consent", "payload_sha256", "consent_to_send"])
            XCTAssertEqual(body["consent_to_send"] as? Bool, true)
            XCTAssertEqual(body["payload_sha256"] as? String, digest)
            return (503, Data("{}".utf8)) // No known pre-admission code: failure remains ambiguous.
        }
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        let service = try HTTPBeverageService(configuration: .init(baseURL: "http://127.0.0.1:8000", token: String(repeating: "t", count: 32), offline: false), session: URLSession(configuration: options))
        let controller = WonderAnalysisController()
        await controller.loadPreview(try request(), forecast: try forecast(), service: service)
        XCTAssertTrue(controller.canOffer)
        await controller.explain(consent: true, service: service)
        XCTAssertTrue(controller.isQuarantined)
        await controller.explain(consent: true, service: service)
        XCTAssertEqual(sends, 1)
    }

    @MainActor func testMalformedSuccessRemainsQuarantinedAndLateResultCannotRestoreState() async throws {
        var body = try JSONSerialization.jsonObject(with: data("wonder-analysis-result-fake")) as! [String: Any]
        var result = body["result"] as! [String: Any]; result["payload_sha256"] = String(repeating: "a", count: 64); body["result"] = result
        let invalid = try JSONDecoder().decode(WonderAnalysisResponse.self, from: JSONSerialization.data(withJSONObject: body))
        let service = AnalysisWonderStub(preview: try preview(), response: invalid)
        let controller = WonderAnalysisController()
        await controller.loadPreview(try request(), forecast: try forecast(), service: service)
        await controller.explain(consent: true, service: service)
        XCTAssertTrue(controller.isQuarantined); XCTAssertNil(controller.result)
        let delayed = DelayedRichService(preview: try preview(), response: try response())
        let other = WonderAnalysisController()
        await other.loadPreview(try request(), forecast: try forecast(), service: delayed)
        let task = Task { await other.explain(consent: true, service: delayed) }
        await fulfillment(of: [delayed.started], timeout: 2)
        await other.explain(consent: true, service: delayed) // A second tap while the first awaits cannot dispatch.
        task.cancel(); other.invalidate(); await delayed.complete(); await task.value
        XCTAssertNil(other.result); XCTAssertNil(other.preview); XCTAssertEqual(other.state, .idle)
        await other.loadPreview(try request(), forecast: try forecast(), service: delayed)
        XCTAssertTrue(other.isQuarantined); XCTAssertFalse(other.canOffer)
    }
}

private actor AnalysisWonderStub: BeverageService {
    var preview: WonderAnalysisPreview
    let response: WonderAnalysisResponse
    let failure: Error?
    private(set) var explainCount = 0
    init(preview: WonderAnalysisPreview, response: WonderAnalysisResponse, failure: Error? = nil) {
        self.preview = preview; self.response = response; self.failure = failure
    }
    func setPreview(_ value: WonderAnalysisPreview) { preview = value }
    func wonderAnalysisPreview(_ request: WorkoutForecastRequest) async throws -> WonderAnalysisPreview { preview }
    func explainHydrationAnalysis(_ request: WorkoutExplanationRequest) async throws -> WonderAnalysisResponse {
        explainCount += 1; if let failure { throw failure }; return response
    }
    func listBeverages() async throws -> [BeverageLog] { [] }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw ServiceError.invalidResponse }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary { throw ServiceError.invalidResponse }
}
private actor DelayedRichService: BeverageService {
    let preview: WonderAnalysisPreview, response: WonderAnalysisResponse
    let started = XCTestExpectation(description: "Rich explanation started")
    var continuation: CheckedContinuation<WonderAnalysisResponse, Error>?
    init(preview: WonderAnalysisPreview, response: WonderAnalysisResponse) { self.preview = preview; self.response = response }
    func wonderAnalysisPreview(_ request: WorkoutForecastRequest) async throws -> WonderAnalysisPreview { preview }
    func explainHydrationAnalysis(_ request: WorkoutExplanationRequest) async throws -> WonderAnalysisResponse {
        try await withCheckedThrowingContinuation { continuation in self.continuation = continuation; started.fulfill() }
    }
    func complete() { continuation?.resume(returning: response); continuation = nil }
    func listBeverages() async throws -> [BeverageLog] { [] }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw ServiceError.invalidResponse }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary { throw ServiceError.invalidResponse }
}
