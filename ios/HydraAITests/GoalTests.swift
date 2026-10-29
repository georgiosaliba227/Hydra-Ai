import Foundation
import XCTest
@testable import HydraAI

final class GoalTests: XCTestCase {
    private let configuration = APIConfiguration(baseURL: "http://127.0.0.1:8000", token: String(repeating: "x", count: 32), offline: false)
    override func tearDown() { FixtureURLProtocol.handler = nil }

    private func service() throws -> HTTPBeverageService {
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        return try HTTPBeverageService(configuration: configuration, session: URLSession(configuration: options))
    }

    func testSummaryGoalDecodesAndRejectsNonUserGoals() throws {
        let body = #"{"local_date":"2026-10-28","timezone":"UTC","beverage_total_ml":500,"estimated_water_ml":null,"forecast_status":"insufficient_data","goal":{"daily_beverage_goal_ml":2000,"basis":"user_confirmed","remaining_ml":1500,"progress_ratio":0.25}}"#
        let summary = try JSONDecoder().decode(DailySummary.self, from: Data(body.utf8))
        XCTAssertEqual(summary.goal?.dailyBeverageGoalMl, 2000); XCTAssertTrue(summary.goal?.isValid == true)
        let recommended = try JSONDecoder().decode(DailySummary.self, from: Data(body.replacingOccurrences(of: "user_confirmed", with: "recommended").utf8))
        XCTAssertFalse(recommended.goal!.isValid, "Only a user-chosen goal may be shown")
        let none = try JSONDecoder().decode(DailySummary.self, from: Data(body.replacingOccurrences(of: #","goal":{"daily_beverage_goal_ml":2000,"basis":"user_confirmed","remaining_ml":1500,"progress_ratio":0.25}"#, with: "").utf8))
        XCTAssertNil(none.goal)
    }

    func testUpdateGoalSendsExplicitNullToClear() async throws {
        var bodies: [String] = []
        FixtureURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "PUT"); XCTAssertEqual(request.url!.path, "/v1/settings")
            let stream = request.httpBodyStream!; stream.open(); defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 256); let count = stream.read(&buffer, maxLength: 256)
            let sent = String(decoding: buffer[0..<max(count, 0)], as: UTF8.self); bodies.append(sent)
            let goal = sent.contains("null") ? "null" : "1500"
            return (200, Data(#"{"version":"settings-v1","daily_beverage_goal_ml":\#(goal),"goal_basis":"user_confirmed","updated_at":"2026-10-29T00:00:00Z"}"#.utf8))
        }
        let saved = try await service().updateGoal(1500)
        XCTAssertEqual(saved.daily_beverage_goal_ml, 1500)
        let cleared = try await service().updateGoal(nil)
        XCTAssertNil(cleared.daily_beverage_goal_ml)
        XCTAssertEqual(bodies, [#"{"daily_beverage_goal_ml":1500}"#, #"{"daily_beverage_goal_ml":null}"#])
        do { _ = try await service().updateGoal(50); XCTFail("Out-of-range goal sent") } catch BeverageValidationError.invalidVolume {}
    }
}
