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

    @MainActor
    func testOfflineGoalPersistsAndUpdatesAfterLogging() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let file = folder.appendingPathComponent("drinks.json")
        let config = APIConfiguration(baseURL: "", token: "", offline: true)
        let store = BeverageStore(service: MockBeverageService(fileURL: file),
                                  pendingURL: folder.appendingPathComponent("pending.json"), configuration: config)
        await store.refresh()
        XCTAssertNil(store.summary?.goal, "No target is invented before the user chooses one")
        try await store.setGoal(1000)
        try await store.add(category: "water", consumedMl: 250, at: .now)
        XCTAssertEqual(store.summary?.beverageTotalMl, 250)
        XCTAssertEqual(store.summary?.goal?.progressRatio, 0.25)
        XCTAssertEqual(store.summary?.goal?.remainingMl, 750)
        try await store.add(category: "tea", consumedMl: 500, at: .now)
        XCTAssertEqual(store.summary?.goal?.progressRatio, 0.75)

        let restarted = BeverageStore(service: MockBeverageService(fileURL: file),
                                      pendingURL: folder.appendingPathComponent("pending.json"), configuration: config)
        await restarted.refresh()
        XCTAssertEqual(restarted.summary?.goal?.dailyBeverageGoalMl, 1000)
        XCTAssertEqual(restarted.summary?.goal?.progressRatio, 0.75)
        try await restarted.add(category: "coffee", consumedMl: 500, at: .now)
        XCTAssertEqual(restarted.summary?.goal?.progressRatio, 1.25)
        XCTAssertEqual(restarted.summary?.goal?.remainingMl, 0)
        try await restarted.setGoal(nil)
        XCTAssertNil(restarted.summary?.goal)
        XCTAssertEqual(restarted.summary?.beverageTotalMl, 1250, "Clearing a goal preserves drinks")
        let cleared = try await MockBeverageService(fileURL: file).goalSettings()
        XCTAssertNil(cleared.daily_beverage_goal_ml)
    }

    func testOfflineGoalRejectsInvalidValuesAndStaysIsolated() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let demo = MockBeverageService(fileURL: folder.appendingPathComponent("demo.json"))
        _ = try await demo.updateGoal(1500)
        for value in [0, 99, 10_001] {
            do {
                _ = try await demo.updateGoal(value)
                XCTFail("Invalid goal accepted: \(value)")
            } catch BeverageValidationError.invalidVolume { }
        }
        let saved = try await demo.goalSettings()
        XCTAssertEqual(saved.daily_beverage_goal_ml, 1500)
        let separate = try await MockBeverageService(fileURL: folder.appendingPathComponent("other.json")).goalSettings()
        XCTAssertNil(separate.daily_beverage_goal_ml, "Demo goals cannot leak between stores")
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
