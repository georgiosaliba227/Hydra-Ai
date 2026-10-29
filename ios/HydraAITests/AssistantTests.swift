import Foundation
import XCTest
@testable import HydraAI

final class AssistantTests: XCTestCase {
    private func answer(topics: [String] = ["creatine"], escalation: Bool = false, context: [String: Any]? = nil,
                        provenance: [String: Any]? = nil, questionId: Any = "creatine_water") -> [String: Any] {
        ["version": "assistant-v1", "question_id": questionId, "topics": topics, "escalation": escalation,
         "answers": topics.map { ["topic": $0, "text": "Reviewed \($0) text.",
                                  "evidence": [["title": "Source", "url": "https://example.org/a", "kind": "research"]]] },
         "intake_context": context ?? NSNull(),
         "provenance": provenance ?? ["mode": "local_rules", "provider": NSNull(), "model": NSNull(), "answer_origin": "reviewed_text"],
         "limitations": ["Wellness information, not medical advice."]]
    }

    private func decode(_ body: [String: Any]) throws -> AssistantAnswer {
        try JSONDecoder().decode(AssistantAnswer.self, from: JSONSerialization.data(withJSONObject: body))
    }

    func testRequestOnlyIncludesTodayWithConsent() throws {
        let zone = TimeZone(identifier: "Europe/Paris")!
        let plain = AssistantRequest.make(questionId: "creatine_water", includeToday: false, zone: zone)
        let encoded = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(plain)) as? [String: Any])
        XCTAssertEqual(Set(encoded.keys), ["question_id", "context_scope"])
        let consented = AssistantRequest.make(question: "  coffee?  ", includeToday: true, now: Date(timeIntervalSince1970: 1_761_696_000), zone: zone)
        XCTAssertEqual(consented.question, "coffee?"); XCTAssertEqual(consented.context_scope, "today_logged_total")
        XCTAssertEqual(consented.date, "2025-10-29"); XCTAssertEqual(consented.timezone, "Europe/Paris")
        XCTAssertThrowsError(try AssistantRequest.make(question: String(repeating: "x", count: 301), includeToday: false).validate())
        XCTAssertThrowsError(try AssistantRequest(question: "a", question_id: "b").validate())
    }

    func testValidAnswerAndConsentedContextAreAccepted() throws {
        let request = AssistantRequest.make(questionId: "creatine_water", includeToday: false)
        XCTAssertNoThrow(try decode(answer()).validate(request: request))
        let consented = AssistantRequest(question: nil, question_id: "creatine_water", context_scope: "today_logged_total", date: "2026-10-29", timezone: "UTC")
        let context: [String: Any] = ["local_date": "2026-10-29", "timezone": "UTC", "beverage_total_ml": 750, "note": "Confirmed volume."]
        XCTAssertNoThrow(try decode(answer(context: context)).validate(request: consented))
        XCTAssertThrowsError(try decode(answer(context: context)).validate(request: request), "Context without consent is rejected")
        XCTAssertThrowsError(try decode(answer()).validate(request: consented), "Missing consented context is rejected")
    }

    func testGeneratedUnsafeOrInconsistentAnswersAreRejected() throws {
        let request = AssistantRequest.make(questionId: "creatine_water", includeToday: false)
        let generated: [String: Any] = ["mode": "meta_live", "provider": "Meta", "model": "muse-wonder-1.0", "answer_origin": "model_text"]
        for body in [answer(provenance: generated), answer(topics: ["urgent"], escalation: false),
                     answer(topics: ["creatine", "urgent"], escalation: true), answer(questionId: "other"),
                     answer(topics: ["a", "b", "c", "d", "e"])] {
            XCTAssertThrowsError(try decode(body).validate(request: request))
        }
        var insecure = answer()
        insecure["answers"] = [["topic": "creatine", "text": "x", "evidence": [["title": "s", "url": "http://example.org", "kind": "research"]]]]
        XCTAssertThrowsError(try decode(insecure).validate(request: request))
        let free = AssistantRequest.make(question: "I fainted", includeToday: false)
        XCTAssertNoThrow(try decode(answer(topics: ["urgent", "exercise_sweat"], escalation: true, questionId: NSNull())).validate(request: free))
    }

    @MainActor func testControllerShowsFailureWhenUnavailable() async {
        let controller = AssistantController()
        await controller.ask(.make(question: "coffee?", includeToday: false), service: UnavailableAssistant())
        XCTAssertNil(controller.answer)
        XCTAssertEqual(controller.state, .failed("The assistant is unavailable. Logging still works."))
    }
}

private actor UnavailableAssistant: BeverageService {
    func listBeverages() async throws -> [BeverageLog] { [] }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw ServiceError.invalidResponse }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary { throw ServiceError.invalidResponse }
}

final class RecordedWonderAssistantTests: XCTestCase {
    private func recorded(_ changes: (inout [String: Any]) -> Void = { _ in }) throws -> AssistantAnswer {
        var body: [String: Any] = ["version": "assistant-v1", "question_id": "hot_weather", "topics": ["exercise_sweat", "weather"],
            "escalation": false, "intake_context": NSNull(),
            "answers": ["exercise_sweat", "weather"].map { ["topic": $0, "text": "Reviewed \($0).",
                        "evidence": [["title": "NATA", "url": "https://pmc.ncbi.nlm.nih.gov/x", "kind": "research"]]] },
            "provenance": ["mode": "meta_live", "provider": "Meta", "model": "muse-wonder-1.0", "answer_origin": "reviewed_text",
                           "topic_selection": "muse-wonder-1.0", "account_id": "georgiosaliba227", "attempt_id": UUID().uuidString.lowercased()],
            "provider_observations": ["latency_ms": 640, "input_tokens": 410, "output_tokens": 30,
                                      "usage_derived_cost_micro_usd": 2240, "billed_cost_usd": NSNull()],
            "limitations": ["Muse Wonder chose which reviewed answers apply; it did not write them."]]
        changes(&body)
        return try JSONDecoder().decode(AssistantAnswer.self, from: JSONSerialization.data(withJSONObject: body))
    }

    func testRecordedWonderAnswerIsAcceptedOnlyWhenRequested() throws {
        let asked = AssistantRequest.recordedWonder(questionId: "hot_weather")
        XCTAssertNoThrow(try asked.validate())
        let answer = try recorded()
        XCTAssertNoThrow(try answer.validate(request: asked)); XCTAssertTrue(answer.isRecordedWonder)
        XCTAssertThrowsError(try answer.validate(request: .make(questionId: "hot_weather", includeToday: false)),
                             "A live-labelled answer must never satisfy a local-rules request")
        XCTAssertThrowsError(try AssistantRequest(question: "hot?", source: "recorded_wonder").validate())
    }

    func testTamperedRecordedWonderAnswersAreRejected() throws {
        let asked = AssistantRequest.recordedWonder(questionId: "hot_weather")
        let tampers: [(inout [String: Any]) -> Void] = [
            { var p = $0["provenance"] as! [String: Any]; p["topic_selection"] = "muse-spark-1.3"; $0["provenance"] = p },
            { var p = $0["provenance"] as! [String: Any]; p["account_id"] = "someone-else"; $0["provenance"] = p },
            { var o = $0["provider_observations"] as! [String: Any]; o["billed_cost_usd"] = 0.01; $0["provider_observations"] = o },
            { $0["provider_observations"] = NSNull() },
            { $0["escalation"] = true },
        ]
        for tamper in tampers { XCTAssertThrowsError(try recorded(tamper).validate(request: asked)) }
    }
}
