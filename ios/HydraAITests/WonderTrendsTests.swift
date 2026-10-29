import XCTest
@testable import HydraAI

/// Muse Wonder trend explanations: client-side checks on backend-shaped JSON. No network.
final class WonderTrendsTests: XCTestCase {
    // Produced by backend/wonder_trends.py through a fake Meta transport on a disposable ledger.
    static let resultJSON = #"{"version":"wonder-trends-v1","facts":{"version":"wonder-trends-facts-v1","timezone":"America/New_York","through_date":"2026-10-28","window_days":14,"days":[{"date":"2026-10-15","total_ml":1500,"drinks":1},{"date":"2026-10-16","total_ml":1750,"drinks":2},{"date":"2026-10-17","total_ml":1500,"drinks":1},{"date":"2026-10-18","total_ml":1750,"drinks":2},{"date":"2026-10-19","total_ml":1500,"drinks":1},{"date":"2026-10-20","total_ml":1750,"drinks":2},{"date":"2026-10-21","total_ml":1500,"drinks":1},{"date":"2026-10-22","total_ml":2050,"drinks":2},{"date":"2026-10-23","total_ml":1800,"drinks":1},{"date":"2026-10-24","total_ml":2050,"drinks":2},{"date":"2026-10-25","total_ml":1800,"drinks":1},{"date":"2026-10-26","total_ml":2050,"drinks":2},{"date":"2026-10-27","total_ml":1800,"drinks":1},{"date":"2026-10-28","total_ml":2050,"drinks":2}],"goal_ml":2000,"categories":[{"category":"water","total_ml":23100,"share_pct":93},{"category":"coffee","total_ml":1750,"share_pct":7}],"other_categories_ml":0,"time_of_day_ml":{"morning_ml":1750,"afternoon_ml":23100,"evening_ml":0,"night_ml":0},"last_7_days":{"total_ml":13600,"average_ml":1943,"logged_days":7},"previous_7_days":{"total_ml":11250,"average_ml":1607,"logged_days":7},"change_pct":21,"goal_met_days_last_7":4,"applicable_insights":["week_over_week","goal_progress","logging_consistency","beverage_mix","timing"]},"payload_sha256":"9e6c5e6f20b35f0000463d3126bb94a216392e2c463723fa8b3bfb063bd48814","summary":"You logged 13600 mL in the last 7 days.","insights":[{"id":"week_over_week","title":"This week vs last week","text":"That is 21% more than the week before."},{"id":"goal_progress","title":"Your goal","text":"You reached your 2 L goal on 4 of 7 days."}],"generated_at":"2026-10-29T13:22:15.515291+00:00","provenance":{"mode":"meta_live","provider":"Meta","model":"muse-wonder-1.0","account_id":"aminealichaouche","attempt_id":"ec643305-a419-472b-94ea-18b881348f2d","text_origin":"muse_wonder_checked","numbers_checked_against":"facts"},"provider_observations":{"latency_ms":0,"input_tokens":900,"output_tokens":120,"usage_derived_cost_micro_usd":6000,"billed_cost_usd":null},"limitations":["Wellness information, not medical advice.","Muse Wonder wrote these explanations; Hydra checked every number against your log.","Logged volume is not a measurement of hydration status."]}"#
    static let previewJSON = #"{"version":"wonder-trends-v1","facts":{"version":"wonder-trends-facts-v1","timezone":"America/New_York","through_date":"2026-10-28","window_days":14,"days":[{"date":"2026-10-15","total_ml":1500,"drinks":1},{"date":"2026-10-16","total_ml":1750,"drinks":2},{"date":"2026-10-17","total_ml":1500,"drinks":1},{"date":"2026-10-18","total_ml":1750,"drinks":2},{"date":"2026-10-19","total_ml":1500,"drinks":1},{"date":"2026-10-20","total_ml":1750,"drinks":2},{"date":"2026-10-21","total_ml":1500,"drinks":1},{"date":"2026-10-22","total_ml":2050,"drinks":2},{"date":"2026-10-23","total_ml":1800,"drinks":1},{"date":"2026-10-24","total_ml":2050,"drinks":2},{"date":"2026-10-25","total_ml":1800,"drinks":1},{"date":"2026-10-26","total_ml":2050,"drinks":2},{"date":"2026-10-27","total_ml":1800,"drinks":1},{"date":"2026-10-28","total_ml":2050,"drinks":2}],"goal_ml":2000,"categories":[{"category":"water","total_ml":23100,"share_pct":93},{"category":"coffee","total_ml":1750,"share_pct":7}],"other_categories_ml":0,"time_of_day_ml":{"morning_ml":1750,"afternoon_ml":23100,"evening_ml":0,"night_ml":0},"last_7_days":{"total_ml":13600,"average_ml":1943,"logged_days":7},"previous_7_days":{"total_ml":11250,"average_ml":1607,"logged_days":7},"change_pct":21,"goal_met_days_last_7":4,"applicable_insights":["week_over_week","goal_progress","logging_consistency","beverage_mix","timing"]},"explainable":true,"payload_sha256":"9e6c5e6f20b35f0000463d3126bb94a216392e2c463723fa8b3bfb063bd48814","input_bound_tokens":3127,"worst_case_micro_usd":22748,"live_available":true,"account_id":"aminealichaouche","saved":null,"latest":null}"#

    private func object(_ json: String) -> [String: Any] {
        try! JSONSerialization.jsonObject(with: Data(json.utf8)) as! [String: Any]
    }

    private func decodeResult(_ change: (inout [String: Any]) -> Void = { _ in }) throws -> WonderTrends {
        var value = object(Self.resultJSON)
        change(&value)
        return try JSONDecoder().decode(WonderTrends.self, from: JSONSerialization.data(withJSONObject: value))
    }

    func testBackendResultDecodesAndValidates() throws {
        let result = try decodeResult()
        XCTAssertNoThrow(try result.validate())
        XCTAssertEqual(result.provenance.account_id, "aminealichaouche")
        XCTAssertEqual(result.insights.map(\.id), ["week_over_week", "goal_progress"])
        XCTAssertEqual(result.costUSD, 0.006)
        XCTAssertEqual(result.facts.days.count, 14)
    }

    func testTamperedOrUnexpectedResultsAreRejected() throws {
        let tampering: [(inout [String: Any]) -> Void] = [
            { var p = $0["provenance"] as! [String: Any]; p["account_id"] = "someone-else"; $0["provenance"] = p },
            { var p = $0["provenance"] as! [String: Any]; p["model"] = "muse-spark-1.3"; $0["provenance"] = p },
            { var p = $0["provenance"] as! [String: Any]; p["text_origin"] = "reviewed_text"; $0["provenance"] = p },
            { var o = $0["provider_observations"] as! [String: Any]; o["billed_cost_usd"] = 0.01; $0["provider_observations"] = o },
            { $0["insights"] = [] as [Any] },
            { $0["insights"] = [["id": "diagnosis", "title": "Diagnosis", "text": "Hidden."]] },
            { $0["summary"] = String(repeating: "x", count: 241) },
            { $0["version"] = "wonder-trends-v0" },
        ]
        for change in tampering {
            XCTAssertThrowsError(try decodeResult(change).validate())
        }
    }

    func testPreviewValidatesAndRequiresAConfiguredAccountForLiveUse() throws {
        var value = object(Self.previewJSON)
        let preview = try JSONDecoder().decode(TrendPreview.self, from: JSONSerialization.data(withJSONObject: value))
        XCTAssertNoThrow(try preview.validate())
        XCTAssertTrue(preview.explainable)
        value["account_id"] = NSNull()
        let unconfigured = try JSONDecoder().decode(TrendPreview.self, from: JSONSerialization.data(withJSONObject: value))
        XCTAssertThrowsError(try unconfigured.validate())  // live without an account
    }

    @MainActor func testControllerSendsThePreviewedPayloadOnceThenStops() async throws {
        let service = TrendService(preview: Self.previewJSON, result: Self.resultJSON)
        let controller = WonderTrendsController()
        await controller.load(service: service, zone: TimeZone(identifier: "America/New_York")!)
        XCTAssertNotNil(controller.preview)
        XCTAssertFalse(controller.alreadyExplained)
        await controller.explain(service: service, zone: TimeZone(identifier: "America/New_York")!)
        XCTAssertEqual(controller.result?.summary, try decodeResult().summary)
        XCTAssertTrue(controller.alreadyExplained)
        await controller.explain(service: service, zone: TimeZone(identifier: "America/New_York")!)
        let sent = await service.sent
        XCTAssertEqual(sent.map(\.payload_sha256), [controller.preview!.payload_sha256!])
        XCTAssertEqual(sent.first?.consent_to_send, true)
    }

    @MainActor func testServerRefusalsExplainWhatHappened() async throws {
        let service = TrendService(preview: Self.previewJSON, result: Self.resultJSON, status: 502)
        let controller = WonderTrendsController()
        await controller.load(service: service)
        await controller.explain(service: service)
        XCTAssertEqual(controller.state, .failed(WonderTrendsController.message(for: 502)))
        XCTAssertNil(controller.result)
        XCTAssertTrue(WonderTrendsController.message(for: 502).contains("Don't try again"))
    }
}

private actor TrendService: BeverageService {
    let preview: String
    let result: String
    let status: Int?
    private(set) var sent: [TrendExplanationRequest] = []

    init(preview: String, result: String, status: Int? = nil) {
        self.preview = preview; self.result = result; self.status = status
    }

    func listBeverages() async throws -> [BeverageLog] { [] }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw ServiceError.invalidResponse }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary { throw ServiceError.invalidResponse }

    func wonderTrendPreview(timezone: String) async throws -> TrendPreview {
        let value = try JSONDecoder().decode(TrendPreview.self, from: Data(preview.utf8))
        try value.validate()
        return value
    }

    func explainTrends(_ request: TrendExplanationRequest) async throws -> TrendExplanationResponse {
        sent.append(request)
        if let status { throw ServiceError.server(status) }
        let decoded = try JSONDecoder().decode(WonderTrends.self, from: Data(result.utf8))
        try decoded.validate()
        return TrendExplanationResponse(replayed: false, saved: true, result: decoded)
    }
}
