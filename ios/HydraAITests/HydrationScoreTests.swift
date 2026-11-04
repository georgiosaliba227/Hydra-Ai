import XCTest
@testable import HydraAI

/// Invented measurements exercise the experimental rubric, never physiological accuracy.
final class HydrationScoreTests: XCTestCase {
    private let now = ISO8601DateFormatter().date(from: "2026-11-03T18:00:00Z")!
    private let zone = TimeZone(identifier: "America/New_York")!
    private func log(_ amount: Int, at text: String, id: UUID = UUID()) -> BeverageLog {
        .init(id: id, consumedMl: amount, category: "water", consumedAt: ISO8601DateFormatter().date(from: text)!, timezone: "UTC", source: "manual", revision: 1)
    }
    private func sample(day: Int) -> WorkoutForecastRequest.Sample {
        .init(event_id: UUID(), observed_at: String(format: "2026-10-%02dT12:00:00Z", day),
            conditions: .init(activity: "running", intensity: "moderate", temperature_c: 22, humidity_percent: 55),
            measurement: .init(pre_mass_kg: 70, post_mass_kg: 69.5, consumed_ml: 200, urine_ml: 0, duration_minutes: 45),
            errors: .init(pre_mass_kg: 0.05, post_mass_kg: 0.05, consumed_ml: 10, urine_ml: 0, duration_minutes: 1))
    }
    func testCombinedRubricKeepsContributionsUnroundedAndRoundsOnlyFinalSum() throws {
        let facts = try HydrationScore.calculate(logs: [log(500, at: "2026-11-03T12:00:00Z"),
            log(1000, at: "2026-11-02T12:00:00Z"), log(1000, at: "2026-11-01T12:00:00Z")],
            goalMl: 1000, samples: [sample(day: 30)], now: now, timezone: zone)
        XCTAssertEqual(facts.components.today_points, 25)
        XCTAssertEqual(facts.components.consistency_points, 60.0 / 7, accuracy: 1e-10)
        XCTAssertEqual(facts.components.measurement_points, 20.0 / 6, accuracy: 1e-10)
        XCTAssertEqual(facts.score, 37)
        XCTAssertEqual(facts.measurement_count, 1)
    }
    func testCapsEachGoalAndMeasurementContributionAndRetainsKnownEmptyDays() throws {
        var logs = [log(5000, at: "2026-11-03T12:00:00Z")]
        for day in 27...31 { logs.append(log(5000, at: String(format: "2026-10-%02dT12:00:00Z", day))) }
        logs += [log(5000, at: "2026-11-01T12:00:00Z"), log(5000, at: "2026-11-02T12:00:00Z")]
        let full = try HydrationScore.calculate(logs: logs, goalMl: 1000, samples: (23...29).map(sample), now: now, timezone: zone)
        XCTAssertEqual(full.score, 100)
        XCTAssertEqual(full.components.today_points, 50)
        XCTAssertEqual(full.components.consistency_points, 30)
        XCTAssertEqual(full.components.measurement_points, 20)
        let empty = try HydrationScore.calculate(logs: [], goalMl: 1000, samples: [], now: now, timezone: zone)
        XCTAssertEqual(empty.score, 0)
        XCTAssertEqual(empty.previous_days.count, 7)
        XCTAssertTrue(empty.previous_days.allSatisfy { !$0.logged && $0.total_ml == 0 })
    }
    func testReferenceOperationOrderKeepsCrossLanguageComponentsStable() throws {
        let facts = try HydrationScore.calculate(logs: [], goalMl: 1000, samples: [sample(day: 30)], now: now, timezone: zone)
        XCTAssertEqual(facts.components.measurement_points, 20 * (1.0 / 6))
    }
    func testHalfPointRoundingAndMissingOrInvalidInputsDoNotBecomeZero() throws {
        let half = try HydrationScore.calculate(logs: [log(10, at: "2026-11-03T12:00:00Z")], goalMl: 1000, samples: [], now: now, timezone: zone)
        XCTAssertEqual(half.score, 1)
        XCTAssertThrowsError(try HydrationScore.calculate(logs: [], goalMl: nil, samples: [], now: now, timezone: zone))
        XCTAssertThrowsError(try HydrationScore.calculate(logs: [], goalMl: 0, samples: [], now: now, timezone: zone))
        let duplicate = sample(day: 30)
        XCTAssertThrowsError(try HydrationScore.calculate(logs: [], goalMl: 1000, samples: [duplicate, duplicate], now: now, timezone: zone))
        XCTAssertThrowsError(try HydrationScore.calculate(logs: [log(-1, at: "2026-11-03T12:00:00Z")], goalMl: 1000, samples: [], now: now, timezone: zone))
    }
    func testSevenPreviousLocalDaysHandleFallDSTAndExcludeFutureLogs() throws {
        let date = ISO8601DateFormatter().date(from: "2026-11-02T18:00:00Z")!
        let facts = try HydrationScore.calculate(logs: [log(1000, at: "2026-11-01T05:30:00Z"), log(1000, at: "2026-11-01T06:30:00Z"),
            log(1000, at: "2026-10-26T04:00:00Z"), log(500, at: "2026-10-26T03:59:59Z"), log(5000, at: "2026-11-02T19:00:00Z")],
            goalMl: 1000, samples: [], now: date, timezone: zone)
        XCTAssertEqual(facts.local_date, "2026-11-02")
        XCTAssertEqual(facts.today_ml, 0)
        XCTAssertEqual(facts.previous_days.map(\.local_date), ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01"])
        XCTAssertEqual(facts.previous_days.last?.total_ml, 2000)
        XCTAssertEqual(facts.components.consistency_points, 60.0 / 7, accuracy: 1e-10)
    }
    func testEditsDeletionGoalAndTimezoneChangesRecomputeTheSnapshot() throws {
        let instant = ISO8601DateFormatter().date(from: "2026-11-03T02:00:00Z")!
        let logs = [log(1000, at: "2026-11-02T23:00:00Z")]
        let original = try HydrationScore.calculate(logs: logs, goalMl: 1000, samples: [], now: instant, timezone: zone)
        let changedGoal = try HydrationScore.calculate(logs: logs, goalMl: 2000, samples: [], now: instant, timezone: zone)
        let deleted = try HydrationScore.calculate(logs: [], goalMl: 1000, samples: [], now: instant, timezone: zone)
        let utc = try HydrationScore.calculate(logs: logs, goalMl: 1000, samples: [], now: instant, timezone: TimeZone(secondsFromGMT: 0)!)
        XCTAssertEqual(original.score, 50); XCTAssertEqual(changedGoal.score, 25); XCTAssertEqual(deleted.score, 0)
        XCTAssertEqual(utc.today_ml, 0); XCTAssertEqual(utc.previous_days.last?.total_ml, 1000)
        XCTAssertNotEqual(original.local_date, utc.local_date)
    }
    func testUnavailableLoadingPendingStaleOrCorruptSourcesNeverYieldZero() throws {
        let summary = DailySummary(localDate: "2026-11-03", timezone: zone.identifier, beverageTotalMl: 0,
            estimatedWaterMl: nil, forecastStatus: "unavailable", goal: .init(dailyBeverageGoalMl: 1000, basis: "user_confirmed", remainingMl: 1000, progressRatio: 0))
        for variation in ["loading", "failed", "pending", "history", "offline", "stale"] {
            let current = variation == "stale" ? DailySummary(localDate: "2026-11-02", timezone: zone.identifier, beverageTotalMl: 0, estimatedWaterMl: nil, forecastStatus: "unavailable", goal: summary.goal) : summary
            let state: LoadState = variation == "loading" ? .loading : variation == "failed" ? .failed("Unavailable") : .loaded
            let value = HydrationScore.availability(logs: [], summary: current, state: state,
                mutationPending: variation == "pending", isOffline: variation == "offline", historyReadable: variation != "history",
                samples: [], now: now, timezone: zone)
            XCTAssertEqual(value, .unavailable, variation)
        }
        let noGoal = DailySummary(localDate: summary.localDate, timezone: summary.timezone, beverageTotalMl: 0, estimatedWaterMl: nil, forecastStatus: "unavailable")
        XCTAssertEqual(HydrationScore.availability(logs: [], summary: noGoal, state: .loaded, mutationPending: false,
            isOffline: false, historyReadable: true, samples: [], now: now, timezone: zone), .goalRequired)
    }
}
