import XCTest
@testable import HydraAI

/// Producer-generated invented score facts and fake provider text; no live requests.
final class HydrationScoreWonderTests: XCTestCase {
    override func tearDown() { FixtureURLProtocol.handler = nil }
    private func data(_ name: String) throws -> Data { try Data(contentsOf: XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "json"))) }
    private func object(_ name: String) throws -> [String: Any] { try JSONSerialization.jsonObject(with: data(name)) as! [String: Any] }
    private func preview(live: Bool = false, saved: Bool = false) throws -> HydrationScorePreview {
        var value = try object("hydration-score-preview-fake")
        value["live_available"] = live; value["account_id"] = live ? "aminealichaouche" : NSNull()
        if saved { value["saved"] = try object("hydration-score-response-fake")["result"] }
        return try JSONDecoder().decode(HydrationScorePreview.self, from: JSONSerialization.data(withJSONObject: value))
    }
    private func assertCalls(_ service: ScoreStub, previews: Int? = nil, explains: Int? = nil) async {
        if let previews { let actual = await service.previewCalls; XCTAssertEqual(actual, previews) }
        if let explains { let actual = await service.explainCalls; XCTAssertEqual(actual, explains) }
    }
    private func response() throws -> HydrationScoreExplanationResponse { try JSONDecoder().decode(HydrationScoreExplanationResponse.self, from: data("hydration-score-response-fake")) }
    func testProducerVariedSnapshotMatchesNativeCalculationAndValidatesReviewedProse() throws {
        let input = try object("hydration-score-inputs-fake"), request = input["request"] as! [String: Any]
        let clock = ISO8601DateFormatter().date(from: input["now"] as! String)!
        let logs = (input["records"] as! [[String: Any]]).map { record in
            BeverageLog(id: UUID(), consumedMl: record["consumed_ml"] as! Int, category: "water", consumedAt: ISO8601DateFormatter().date(from: record["consumed_at"] as! String)!, timezone: "UTC", source: "manual", revision: 1)
        }
        let samples = (1...2).map { day in WorkoutForecastRequest.Sample(event_id: UUID(), observed_at: "2026-10-0\(day)T12:00:00Z",
            conditions: .init(activity: "running", intensity: "moderate", temperature_c: 22, humidity_percent: 55),
            measurement: .init(pre_mass_kg: 70, post_mass_kg: 69.5, consumed_ml: 200, urine_ml: 0, duration_minutes: 45),
            errors: .init(pre_mass_kg: 0.05, post_mass_kg: 0.05, consumed_ml: 10, urine_ml: 0, duration_minutes: 1)) }
        let local = try HydrationScore.calculate(logs: logs, goalMl: input["goal_ml"] as? Int, samples: samples, now: clock, timezone: TimeZone(identifier: request["timezone"] as! String)!)
        let value = try preview()
        try value.validate(expected: local)
        XCTAssertEqual(local.score, 39)
        XCTAssertEqual(value.facts.components.measurement_points, local.components.measurement_points)
        try response().result.validate()
    }
    func testRejectsHiddenChangedOrFabricatedScoreFactsAndWording() throws {
        let original = try object("hydration-score-response-fake")
        for mutation in ["score", "component", "hidden", "date", "logged", "count", "prose", "title", "duplicate", "origin", "final_charge"] {
            var body = original, result = original["result"] as! [String: Any], facts = result["facts"] as! [String: Any]
            switch mutation {
            case "score": facts["score"] = 100
            case "component": var c = facts["components"] as! [String: Any]; c["today_points"] = 50; facts["components"] = c
            case "hidden": facts["body_mass_kg"] = 70
            case "date": var days = facts["previous_days"] as! [[String: Any]]; days[0]["local_date"] = "2026-11-01"; facts["previous_days"] = days
            case "logged": var days = facts["previous_days"] as! [[String: Any]]; days[0]["logged"] = true; facts["previous_days"] = days
            case "count": facts["measurement_count"] = 33
            case "prose": var insights = result["insights"] as! [[String: Any]]; insights[0]["text"] = "Drink 2000 mL now."; result["insights"] = insights
            case "title": var insights = result["insights"] as! [[String: Any]]; insights[0]["title"] = "You are dehydrated"; result["insights"] = insights
            case "duplicate": var insights = result["insights"] as! [[String: Any]]; insights[1] = insights[0]; result["insights"] = insights
            case "origin": var p = result["provenance"] as! [String: Any]; p["text_origin"] = "muse_wrote_every_number"; result["provenance"] = p
            default: var p = result["provider_observations"] as! [String: Any]; p["billed_cost_usd"] = 0; result["provider_observations"] = p
            }
            result["facts"] = facts; body["result"] = result
            XCTAssertThrowsError(try JSONDecoder().decode(HydrationScoreExplanationResponse.self, from: JSONSerialization.data(withJSONObject: body)).result.validate(), mutation)
        }
    }
    @MainActor func testFreshProcessingAndMetaConsentAreSeparateAndSavedReplayIsFree() async throws {
        let service = ScoreStub(preview: try preview(live: true), response: try response()), controller = HydrationScoreWonderController()
        let facts = try preview().facts
        await controller.prepare(facts: facts, service: service)
        await assertCalls(service, previews: 0)
        controller.processingConsent = true; await controller.prepare(facts: facts, service: service)
        XCTAssertTrue(controller.canOffer); XCTAssertFalse(controller.metaConsent)
        await controller.explain(service: service)
        await assertCalls(service, explains: 0)
        controller.metaConsent = true; await controller.explain(service: service)
        XCTAssertNotNil(controller.result); await assertCalls(service, explains: 1)
        controller.invalidate(); XCTAssertFalse(controller.processingConsent); XCTAssertFalse(controller.metaConsent)
        let recorded = ScoreStub(preview: try preview(saved: true), response: try response())
        controller.processingConsent = true; await controller.prepare(facts: facts, service: recorded)
        XCTAssertNotNil(controller.result); XCTAssertTrue(controller.replayed); XCTAssertFalse(controller.canOffer)
        await assertCalls(recorded, explains: 0)
    }
    @MainActor func testUnknownAttemptFailureQuarantinesFactsAcrossInvalidation() async throws {
        let service = ScoreStub(preview: try preview(live: true), response: try response(), fault: URLError(.timedOut))
        let controller = HydrationScoreWonderController(), facts = try preview().facts
        controller.processingConsent = true; await controller.prepare(facts: facts, service: service)
        controller.metaConsent = true; await controller.explain(service: service)
        XCTAssertTrue(controller.isQuarantined); XCTAssertFalse(controller.canOffer)
        controller.invalidate(); controller.processingConsent = true; await controller.prepare(facts: facts, service: service)
        XCTAssertTrue(controller.isQuarantined); XCTAssertFalse(controller.metaConsent)
        controller.metaConsent = true; await controller.explain(service: service)
        await assertCalls(service, explains: 1)
    }
    func testHTTPPreviewAndExplanationSendOnlyExactAggregateRequestWithoutRetry() async throws {
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        let service = try HTTPBeverageService(configuration: .init(baseURL: "http://127.0.0.1:19998", token: String(repeating: "t", count: 32), offline: false), session: URLSession(configuration: options))
        let fixture = try data("hydration-score-preview-fake"), facts = try preview().facts; var calls = 0
        FixtureURLProtocol.handler = { request in
            calls += 1; XCTAssertEqual(request.httpMethod, "POST"); XCTAssertEqual(request.url?.path, "/v1/wonder/score/preview")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer " + String(repeating: "t", count: 32))
            let bytes: Data
            if let direct = request.httpBody { bytes = direct }
            else {
                let stream = try XCTUnwrap(request.httpBodyStream); stream.open(); defer { stream.close() }
                var collected = Data(), buffer = [UInt8](repeating: 0, count: 1024)
                while stream.hasBytesAvailable { let n = stream.read(&buffer, maxLength: buffer.count); if n <= 0 { break }; collected.append(buffer, count: n) }
                bytes = collected
            }
            let body = try JSONSerialization.jsonObject(with: bytes) as! [String: Any]
            XCTAssertEqual(Set(body.keys), ["timezone", "measurement_count", "processing_consent"])
            XCTAssertEqual(body["measurement_count"] as? Int, 2); return (200, fixture)
        }
        _ = try await service.hydrationScorePreview(.init(timezone: facts.timezone, measurement_count: 2, processing_consent: true))
        XCTAssertEqual(calls, 1)
        FixtureURLProtocol.handler = { _ in calls += 1; return (502, Data("{\"code\":\"wonder_attempt_unresolved\"}".utf8)) }
        do { _ = try await service.explainHydrationScore(.init(timezone: facts.timezone, measurement_count: 2, processing_consent: true, payload_sha256: try preview().payload_sha256, consent_to_send: true)); XCTFail("Expected uncertain failure") } catch { }
        XCTAssertEqual(calls, 2)
    }
}

private actor ScoreStub: BeverageService {
    let prepared: HydrationScorePreview, response: HydrationScoreExplanationResponse, fault: Error?
    private(set) var previewCalls = 0, explainCalls = 0
    init(preview: HydrationScorePreview, response: HydrationScoreExplanationResponse, fault: Error? = nil) { self.prepared = preview; self.response = response; self.fault = fault }
    func hydrationScorePreview(_ request: HydrationScoreRequest) throws -> HydrationScorePreview { previewCalls += 1; return prepared }
    func explainHydrationScore(_ request: HydrationScoreExplanationRequest) throws -> HydrationScoreExplanationResponse { explainCalls += 1; if let fault { throw fault }; return response }
    func listBeverages() -> [BeverageLog] { [] }
    func dailySummary(date: String, timezone: String) throws -> DailySummary { throw ServiceError.invalidResponse }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) throws -> BeverageLog { throw ServiceError.invalidResponse }
}
