import XCTest
@testable import HydraAI

/// Producer-built invented data and a fake response; not evidence of live inference or billing.
final class OwnerSyntheticWonderTests: XCTestCase {
    override func tearDown() { FixtureURLProtocol.handler = nil }
    private func data() throws -> Data {
        try Data(contentsOf: XCTUnwrap(Bundle(for: Self.self).url(forResource: "wonder-owner-once-result-fake", withExtension: "json")))
    }
    private func decoded(_ body: [String: Any]) throws -> OwnerSyntheticWonderResult {
        try JSONDecoder().decode(OwnerSyntheticWonderResult.self, from: JSONSerialization.data(withJSONObject: body))
    }
    func testAcceptsProducerSyntheticSectionsAndReconstructsLocalText() throws {
        let record = try JSONDecoder().decode(OwnerSyntheticWonderResult.self, from: data())
        try record.validate()
        XCTAssertEqual(record.result.sections.count, 8)
        for section in record.result.sections {
            XCTAssertEqual(try record.localText(section), section.text)
            XCTAssertEqual(section.evidence_status, "synthetic")
        }
        XCTAssertEqual(record.receipt.usage_derived_cost_micro_usd, 8000)
    }
    func testRejectsPersonalModeFalseFinalityAndInventedCosts() throws {
        let original = try JSONSerialization.jsonObject(with: data()) as! [String: Any]
        for mutation in ["mode", "nested_mode", "final", "extras", "cost", "input", "output", "cached", "reservation", "hash", "account", "model", "state", "extra_key", "receipt_key"] {
            var body = original, receipt = original["receipt"] as! [String: Any], result = original["result"] as! [String: Any]
            switch mutation {
            case "mode": body["mode"] = "personal"
            case "nested_mode": var facts = result["facts"] as! [String: Any]; facts["mode"] = "personal"; result["facts"] = facts
            case "final": receipt["provider_invoice_final"] = true
            case "extras": receipt["provider_extras_bounded"] = true
            case "cost": receipt["usage_derived_cost_micro_usd"] = 0
            case "input": receipt["input_tokens"] = 4751
            case "output": receipt["output_tokens"] = 2049
            case "cached": receipt["cached_tokens"] = 1001
            case "reservation": receipt["token_reservation_micro_usd"] = 59960
            case "hash": receipt["payload_sha256"] = String(repeating: "0", count: 64)
            case "account": receipt["account_id"] = "aminealichaouche"
            case "model": receipt["model"] = "muse-spark-1.3"
            case "state": receipt["state"] = "settled"
            case "extra_key": body["personal_record"] = "hidden"
            default: receipt["billed_cost_usd"] = 0
            }
            body["receipt"] = receipt; body["result"] = result
            XCTAssertThrowsError(try decoded(body).validate(), mutation)
        }
    }
    func testRejectsChangedFactsTextScaffoldsAndProvenance() throws {
        let original = try JSONSerialization.jsonObject(with: data()) as! [String: Any]
        for mutation in ["fact", "text", "template", "insight", "evidence", "origin", "authenticity", "limitation", "nested_key"] {
            var body = original, result = original["result"] as! [String: Any]
            var sections = result["sections"] as! [[String: Any]]
            switch mutation {
            case "fact": var facts = result["facts"] as! [String: Any]; var environment = facts["environment"] as! [String: Any]; environment["temperature_c"] = 25; facts["environment"] = environment; result["facts"] = facts
            case "text": sections[0]["text"] = "Drink 5000 mL."
            case "template": sections[0]["template"] = "Drink 5000 mL."
            case "insight": var insights = sections[0]["insights"] as! [[String: Any]]; insights[0]["text"] = "Drink 5000 mL."; sections[0]["insights"] = insights
            case "evidence": sections[0]["evidence_status"] = "measured"
            case "origin": var provenance = result["provenance"] as! [String: Any]; provenance["selection_origin"] = "mock_local"; result["provenance"] = provenance
            case "authenticity": var provenance = result["provenance"] as! [String: Any]; provenance["provider_authenticity_or_billing_attested"] = true; result["provenance"] = provenance
            case "limitation": result["limitations"] = []
            default: result["hidden"] = "unreviewed"
            }
            result["sections"] = sections; body["result"] = result
            XCTAssertThrowsError(try decoded(body).validate(), mutation)
        }
    }
    func testLoadsWithOneAuthenticatedGetAndNoBody() async throws {
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        let service = try HTTPBeverageService(configuration: .init(baseURL: "http://127.0.0.1:19998", token: String(repeating: "t", count: 32), offline: false), session: URLSession(configuration: options))
        let fixture = try data(); var calls = 0
        FixtureURLProtocol.handler = { request in
            calls += 1
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.path, "/v1/wonder/owner-once/result")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer " + String(repeating: "t", count: 32))
            XCTAssertNil(request.httpBody)
            return (200, fixture)
        }
        _ = try await service.ownerSyntheticWonderResult()
        XCTAssertEqual(calls, 1)
    }
    func testUnavailableResponseMakesNoAutomaticRetry() async throws {
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        let service = try HTTPBeverageService(configuration: .init(baseURL: "http://127.0.0.1:19998", token: String(repeating: "t", count: 32), offline: false), session: URLSession(configuration: options))
        var calls = 0
        FixtureURLProtocol.handler = { _ in calls += 1; return (404, Data()) }
        do { _ = try await service.ownerSyntheticWonderResult(); XCTFail("Unavailable result must fail") }
        catch { }
        XCTAssertEqual(calls, 1)
    }
}
