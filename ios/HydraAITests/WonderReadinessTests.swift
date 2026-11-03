import XCTest
@testable import HydraAI

/// Synthetic status fixtures only; no live gateway, financial state or personal data.
final class WonderReadinessTests: XCTestCase {
    override func tearDown() { FixtureURLProtocol.handler = nil }
    private func body(status: String = "blocked", policy: String = "owner_accepted_risk") -> [String: Any] {
        ["version": "wonder-readiness-v1", "configured": true, "status": status,
         "account_id": "georgiosaliba227", "policy": policy,
         "blocked_reasons": status == "ready" ? [] : ["current_invoice_finality_required"],
         "all_charge_categories_verified": policy == "verified", "per_request_token_cap_micro_usd": 250000]
    }
    private func decode(_ object: [String: Any]) throws -> WonderReadiness {
        try JSONDecoder().decode(WonderReadiness.self, from: JSONSerialization.data(withJSONObject: object))
    }
    func testAcceptsDisabledBlockedAndReadyWithExplicitRiskStatus() throws {
        let disabled: [String: Any] = ["version": "wonder-readiness-v1", "configured": false, "status": "disabled",
            "account_id": NSNull(), "policy": NSNull(), "blocked_reasons": ["live_disabled"],
            "all_charge_categories_verified": NSNull(), "per_request_token_cap_micro_usd": 250000]
        XCTAssertEqual(try decode(disabled).status, .disabled)
        let blocked = try decode(body())
        XCTAssertEqual(blocked.status, .blocked)
        XCTAssertEqual(blocked.blocked_reasons.first?.message, "Final billing for a recent request still needs confirmation.")
        XCTAssertEqual(blocked.all_charge_categories_verified, false)
        XCTAssertEqual(try decode(body(status: "ready")).status, .ready)
        XCTAssertEqual(try decode(body(status: "ready", policy: "verified")).status, .ready)
    }
    func testRejectsUnknownFieldsAndContradictoryReadinessClaims() throws {
        for mutation in ["version", "status", "policy", "account", "cap", "ready_blocked", "blocked_empty", "duplicate", "unknown_reason", "risk_verified", "verified_ready_unverified", "disabled_configured", "missing_field", "secret", "reason_secret"] {
            var object = body()
            switch mutation {
            case "version": object["version"] = "wonder-readiness-v0"
            case "status": object["status"] = "probably_ready"
            case "policy": object["policy"] = "bypass_all"
            case "account": object["account_id"] = "someone_else"
            case "cap": object["per_request_token_cap_micro_usd"] = 250001
            case "ready_blocked": object["status"] = "ready"
            case "blocked_empty": object["blocked_reasons"] = []
            case "duplicate": object["blocked_reasons"] = ["current_invoice_finality_required", "current_invoice_finality_required"]
            case "unknown_reason": object["blocked_reasons"] = ["go_ahead_anyway"]
            case "risk_verified": object["all_charge_categories_verified"] = true
            case "verified_ready_unverified": object["policy"] = "verified"; object["status"] = "ready"; object["blocked_reasons"] = []; object["all_charge_categories_verified"] = false
            case "disabled_configured": object["status"] = "disabled"
            case "missing_field": object.removeValue(forKey: "all_charge_categories_verified")
            case "secret": object["private_ledger_path"] = "/private/placeholder"
            default: object["blocked_reasons"] = ["key_sha256:placeholder"]
            }
            XCTAssertThrowsError(try decode(object), mutation)
        }
    }
    func testEverySupportedBlockerHasPlainLanguageCopy() throws {
        let codes = ["live_disabled", "owner_policy_not_recorded", "owner_policy_invalid", "quote_expired", "account_observation_stale",
            "cross_ledger_status_unverified", "notification_delivery_unverified", "current_invoice_finality_required", "request_in_flight",
            "financial_failure_requires_review", "budget_exhausted", "verified_financial_checks_required", "storage_unavailable"]
        for code in codes {
            var object = body(); object["blocked_reasons"] = [code]
            if code == "live_disabled" {
                object["configured"] = false; object["status"] = "disabled"; object["account_id"] = NSNull()
                object["policy"] = NSNull(); object["all_charge_categories_verified"] = NSNull()
            }
            let message = try XCTUnwrap(decode(object).blocked_reasons.first?.message)
            XCTAssertFalse(message.isEmpty); XCTAssertFalse(message.contains("_"))
        }
    }
    func testReadinessUsesOneAuthenticatedGetWithoutBodyOrRetry() async throws {
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        let service = try HTTPBeverageService(configuration: .init(baseURL: "http://127.0.0.1:19998", token: String(repeating: "t", count: 32), offline: false), session: URLSession(configuration: options))
        let data = try JSONSerialization.data(withJSONObject: body()); var calls = 0
        FixtureURLProtocol.handler = { request in
            calls += 1
            XCTAssertEqual(request.httpMethod, "GET"); XCTAssertEqual(request.url?.path, "/v1/wonder/readiness")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer " + String(repeating: "t", count: 32))
            XCTAssertNil(request.httpBody); return (200, data)
        }
        let response = try await service.wonderReadiness()
        XCTAssertEqual(response.status, .blocked)
        XCTAssertEqual(calls, 1)
        FixtureURLProtocol.handler = { _ in calls += 1; return (503, Data()) }
        do { _ = try await service.wonderReadiness(); XCTFail("Unavailable readiness must fail") } catch { }
        XCTAssertEqual(calls, 2)
    }
    @MainActor func testConnectionChangeDiscardsLateReadinessResponse() async throws {
        let started = expectation(description: "Readiness began")
        let service = SuspendedReadinessService(started: started)
        let controller = WonderReadinessController()
        let task = Task { await controller.load(service: service) }
        await fulfillment(of: [started], timeout: 5)
        controller.invalidate()
        await service.finish(try decode(body()))
        await task.value
        XCTAssertNil(controller.result); XCTAssertEqual(controller.state, .idle)
    }
}

private actor SuspendedReadinessService: WonderReadinessService {
    let started: XCTestExpectation
    private var continuation: CheckedContinuation<WonderReadiness, Error>?
    init(started: XCTestExpectation) { self.started = started }
    func wonderReadiness() async throws -> WonderReadiness {
        try await withCheckedThrowingContinuation { continuation in self.continuation = continuation; started.fulfill() }
    }
    func finish(_ result: WonderReadiness) { continuation?.resume(returning: result); continuation = nil }
}
