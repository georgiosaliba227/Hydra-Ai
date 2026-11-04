import XCTest
@testable import HydraAI

final class DeviceInsightsTests: XCTestCase {
    private let now = ISO8601DateFormatter().date(from: "2026-10-28T23:00:00Z")!
    private let utc = TimeZone(identifier: "UTC")!

    private func log(_ ml: Int, _ category: String, _ at: String, type: String? = nil) -> BeverageLog {
        BeverageLog(id: UUID(), consumedMl: ml, category: category, consumedAt: ISO8601DateFormatter().date(from: at)!,
                    timezone: "UTC", source: "manual", revision: 1, beverageType: type)
    }
    private var sampleLogs: [BeverageLog] {
        [log(100, "Coffee", "2026-10-15T08:00:00Z"), log(400, "Water", "2026-10-15T13:00:00Z"),
         log(1000, "Water", "2026-10-22T18:00:00Z"), log(500, "Water", "2026-10-28T23:00:00Z")]
    }
    private func decoded(_ object: [String: Any]) throws -> DeviceTrendSummary {
        try JSONDecoder().decode(DeviceTrendSummary.self, from: JSONSerialization.data(withJSONObject: object))
    }
    private func replacing(_ object: Any, path: ArraySlice<String>, with value: Any) -> Any {
        guard let first = path.first else { return value }
        if var dictionary = object as? [String: Any] {
            if path.count == 1 { dictionary[first] = value }
            else { dictionary[first] = replacing(dictionary[first]!, path: path.dropFirst(), with: value) }
            return dictionary
        }
        var array = object as! [Any]
        let index = Int(first)!
        array[index] = replacing(array[index], path: path.dropFirst(), with: value)
        return array
    }
    private func response() -> [String: Any] {
        let days = (15...28).map { day -> [String: Any] in
            ["date": "2026-10-\(day)", "total_ml": [15: 500, 22: 1000, 28: 500][day] ?? 0,
             "drinks": [15: 2, 22: 1, 28: 1][day] ?? 0]
        }
        return ["version": "device-insights-v1", "source": "on_device_summary", "payload_sha256": String(repeating: "a", count: 64),
                "summary": "You logged 2000 mL over 3 recorded days in this 14-day window.",
                "facts": ["version": "wonder-trends-facts-v1", "timezone": "GMT", "through_date": "2026-10-28", "window_days": 14,
                          "days": days, "last_7_days": ["total_ml": 1500, "average_ml": 214, "logged_days": 2],
                          "previous_7_days": ["total_ml": 500, "average_ml": 71, "logged_days": 1], "change_pct": 200,
                          "goal_ml": 900, "goal_met_days_last_7": 1,
                          "categories": [["category": "water", "total_ml": 1900, "share_pct": 95], ["category": "coffee", "total_ml": 100, "share_pct": 5]],
                          "other_categories_ml": 0, "time_of_day_ml": ["morning_ml": 100, "afternoon_ml": 400, "evening_ml": 1000, "night_ml": 500],
                          "applicable_insights": ["week_over_week", "goal_progress", "logging_consistency", "beverage_mix", "timing"]],
                "insights": [["id": "week_over_week", "title": "This week vs last week", "text": "Last 7 days: 1500 mL logged; previous 7 days: 500 mL."],
                             ["id": "goal_progress", "title": "Your goal", "text": "Logged totals reached your 900 mL goal on 1 of the last 7 days."],
                             ["id": "logging_consistency", "title": "Logging habit", "text": "Drinks were recorded on 3 of these 14 days. Days without logs are unknown intake."]],
                "provenance": ["mode": "deterministic", "provider": NSNull(), "model": NSNull(), "history_source": "on_device_summary", "storage": "ephemeral"]]
    }

    func testEmptySnapshotHasFourteenDaysAndOnlyAggregateFields() throws {
        XCTAssertNoThrow(try DeviceTrendSnapshot.make(logs: [], goal: nil, now: now, zone: utc))
        guard let snapshot = try? DeviceTrendSnapshot.make(logs: [], goal: nil, now: now, zone: utc) else { return }
        let data = try JSONEncoder().encode(snapshot)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["version"] as? String, "device-insights-v1")
        XCTAssertEqual(object["source"] as? String, "on_device_summary")
        XCTAssertEqual(object["consent_to_process"] as? Bool, true)
        let days = try XCTUnwrap(object["days"] as? [[String: Any]])
        XCTAssertEqual(days.count, 14)
        XCTAssertEqual(days.first?["date"] as? String, "2026-10-15")
        XCTAssertEqual(days.last?["date"] as? String, "2026-10-28")
        XCTAssertTrue(days.allSatisfy { ($0["total_ml"] as? Int) == 0 && ($0["drinks"] as? Int) == 0 })
        XCTAssertEqual((object["categories"] as? [[String: Any]])?.count, 0)
        XCTAssertTrue(Set(object.keys).isSubset(of: ["version", "source", "consent_to_process", "timezone", "through_date", "days", "goal_ml", "categories", "time_of_day_ml"]))
    }

    func testRequestedLocalDayAndTimeBinsMatchLocalStoreIncludingSameDayClockRollback() throws {
        let zone = TimeZone(identifier: "America/New_York")!
        let records = [log(100, "Water", "2026-10-28T03:59:59Z"), log(200, "Water", "2026-10-28T04:00:00Z"),
                       log(300, "Water", "2026-10-28T09:00:00Z"), log(400, "Water", "2026-10-28T16:00:00Z"),
                       log(500, "Water", "2026-10-28T21:00:00Z"), log(600, "Water", "2026-10-29T02:00:00Z"),
                       log(999, "private future name", "2026-10-29T04:00:00Z"), log(888, "private old name", "2026-10-15T03:59:59Z")]
        let snapshot = try DeviceTrendSnapshot.make(logs: records, goal: 2000, now: now, zone: zone)
        XCTAssertEqual(snapshot.timezone, "America/New_York")
        XCTAssertEqual(snapshot.days[12].total_ml, 100)
        XCTAssertEqual(snapshot.days[13].total_ml, 2000)
        XCTAssertEqual(snapshot.days[13].drinks, 5)
        XCTAssertEqual(snapshot.todayLoggedTotalMl, 2000)
        XCTAssertEqual(snapshot.time_of_day_ml, .init(morning_ml: 300, afternoon_ml: 400, evening_ml: 500, night_ml: 900))
        XCTAssertEqual(snapshot.categories.map(\.total_ml), [2100])
    }

    func testGregorianWindowIncludesDSTAndSkippedCivilDatesWithoutDroppingDays() throws {
        for (instant, zone, first, last, included) in [
            ("2026-03-10T12:00:00Z", "America/New_York", "2026-02-25", "2026-03-10", "2026-03-08"),
            ("2011-12-30T12:00:00Z", "Pacific/Apia", "2011-12-18", "2011-12-31", "2011-12-30")
        ] {
            let snapshot = try DeviceTrendSnapshot.make(logs: [], goal: nil, now: ISO8601DateFormatter().date(from: instant)!, zone: TimeZone(identifier: zone)!)
            XCTAssertEqual(snapshot.days.count, 14)
            XCTAssertEqual(Set(snapshot.days.map(\.date)).count, 14)
            XCTAssertEqual(snapshot.days.first?.date, first)
            XCTAssertEqual(snapshot.days.last?.date, last)
            XCTAssertTrue(snapshot.days.contains { $0.date == included })
        }
    }

    func testCategoryProjectionUsesDeclaredTypeThenExactAliasesAndExportsNoIdentityFields() throws {
        let records = [log(250, "private brand marker", "2026-10-28T08:00:00Z", type: "Sports drink"),
                       log(100, "Energy drink", "2026-10-28T08:00:00Z"), log(200, "Plant milk", "2026-10-28T08:00:00Z"),
                       log(300, " Water ", "2026-10-28T08:00:00Z"), log(400, "my private coffee recipe", "2026-10-28T08:00:00Z"),
                       log(500, "Water", "2026-10-28T08:00:00Z", type: "private type marker")]
        let snapshot = try DeviceTrendSnapshot.make(logs: records, goal: 2000, now: now, zone: utc)
        XCTAssertEqual(Dictionary(uniqueKeysWithValues: snapshot.categories.map { ($0.category, $0.total_ml) }),
                       ["sports": 250, "energy": 100, "plant_milk": 200, "water": 300, "other": 900])
        let data = try JSONEncoder().encode(snapshot), text = String(decoding: data, as: UTF8.self)
        for forbidden in ["private", "recipe", "consumed_at", "recognition", "profile", "health", "photo", "container", "2026-10-28T08"] + records.map({ $0.id.uuidString }) {
            XCTAssertFalse(text.contains(forbidden), forbidden)
        }
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let categories = try XCTUnwrap(object["categories"] as? [[String: Any]])
        XCTAssertTrue(categories.allSatisfy { Set($0.keys) == ["category", "total_ml"] })
    }

    func testInvalidVolumesGoalsDatesAndExcessDrinkCountsFailInsteadOfTruncating() throws {
        for ml in [-1, 0, 5001, Int.max] {
            XCTAssertThrowsError(try DeviceTrendSnapshot.make(logs: [log(ml, "Water", "2026-10-28T08:00:00Z")], goal: nil, now: now, zone: utc))
        }
        for goal in [0, 99, 10001, Int.max] {
            XCTAssertThrowsError(try DeviceTrendSnapshot.make(logs: [], goal: goal, now: now, zone: utc))
        }
        for goal in [100, 10000] { XCTAssertNoThrow(try DeviceTrendSnapshot.make(logs: [], goal: goal, now: now, zone: utc)) }
        let invalid = BeverageLog(id: UUID(), consumedMl: 100, category: "Water", consumedAt: Date(timeIntervalSince1970: .nan), timezone: "UTC", source: "manual", revision: 1)
        XCTAssertThrowsError(try DeviceTrendSnapshot.make(logs: [invalid], goal: nil, now: now, zone: utc))
        XCTAssertThrowsError(try DeviceTrendSnapshot.make(logs: [], goal: nil, now: Date(timeIntervalSince1970: .infinity), zone: utc))
        let records = (0..<1000).map { _ in log(1, "Water", "2026-10-28T08:00:00Z") }
        XCTAssertEqual(try DeviceTrendSnapshot.make(logs: records, goal: nil, now: now, zone: utc).todayLoggedTotalMl, 1000)
        XCTAssertThrowsError(try DeviceTrendSnapshot.make(logs: records + [records[0]], goal: nil, now: now, zone: utc))
    }

    func testSummaryAcceptsMatchingDeterministicFactsAndRejectsProvenanceWindowAndDerivedTampering() throws {
        let snapshot = try DeviceTrendSnapshot.make(logs: sampleLogs, goal: 900, now: now, zone: utc)
        try decoded(response()).validate(for: snapshot)
        let changes: [([String], Any)] = [
            (["source"], "server_history"), (["version"], "wonder-trends-v1"), (["payload_sha256"], String(repeating: "g", count: 64)),
            (["provenance", "mode"], "meta_live"), (["provenance", "provider"], "Meta"), (["provenance", "model"], "muse-wonder-1.0"),
            (["provenance", "history_source"], "backend_history"), (["provenance", "storage"], "saved"),
            (["summary"], String(repeating: "x", count: 241)), (["summary"], "a\nb"),
            (["facts", "through_date"], "2026-10-27"), (["facts", "timezone"], "America/New_York"), (["facts", "window_days"], 13),
            (["facts", "goal_ml"], 1000), (["facts", "days", "0", "total_ml"], 501), (["facts", "days", "0", "drinks"], 1),
            (["facts", "last_7_days", "average_ml"], 215), (["facts", "previous_7_days", "logged_days"], 2),
            (["facts", "change_pct"], 201), (["facts", "goal_met_days_last_7"], 2), (["facts", "categories", "0", "share_pct"], 94),
            (["facts", "other_categories_ml"], 1), (["facts", "time_of_day_ml", "night_ml"], 501),
            (["facts", "applicable_insights"], ["diagnosis"]), (["insights", "0", "id"], "diagnosis"),
            (["insights", "1", "id"], "week_over_week"), (["insights", "0", "text"], String(repeating: "x", count: 301)),
            (["insights", "0", "title"], String(repeating: "x", count: 81)), (["provenance", "account_id"], "private-marker")
        ]
        for (path, value) in changes {
            let changed = replacing(response(), path: path[...], with: value) as! [String: Any]
            XCTAssertThrowsError(try decoded(changed).validate(for: snapshot), path.joined(separator: "."))
        }
    }

    func testResponseRoundingMatchesPythonTiesToEvenForCategoryShares() throws {
        let logs = [log(101, "Coffee", "2026-10-28T08:00:00Z"), log(99, "Water", "2026-10-28T08:00:00Z")]
        let snapshot = try DeviceTrendSnapshot.make(logs: logs, goal: nil, now: now, zone: utc)
        var object = response(), facts = object["facts"] as! [String: Any]
        facts["days"] = (15...28).map { ["date": "2026-10-\($0)", "total_ml": $0 == 28 ? 200 : 0, "drinks": $0 == 28 ? 2 : 0] as [String: Any] }
        facts["last_7_days"] = ["total_ml": 200, "average_ml": 29, "logged_days": 1]
        facts["previous_7_days"] = ["total_ml": 0, "average_ml": 0, "logged_days": 0]
        facts["change_pct"] = NSNull(); facts["goal_ml"] = NSNull(); facts["goal_met_days_last_7"] = NSNull()
        facts["categories"] = [["category": "coffee", "total_ml": 101, "share_pct": 50], ["category": "water", "total_ml": 99, "share_pct": 50]]
        facts["time_of_day_ml"] = ["morning_ml": 200, "afternoon_ml": 0, "evening_ml": 0, "night_ml": 0]
        facts["applicable_insights"] = ["logging_consistency", "beverage_mix", "timing"]
        object["facts"] = facts
        object["insights"] = [["id": "beverage_mix", "title": "What you drink", "text": "coffee: 101 mL (50% of logged volume)."]]
        try decoded(object).validate(for: snapshot)
        object = replacing(object, path: ["facts", "categories", "0", "share_pct"][...], with: 51) as! [String: Any]
        XCTAssertThrowsError(try decoded(object).validate(for: snapshot))
    }

    func testEmptySummaryHasNoInsightsAndCannotCarryAnotherWindowsHistory() throws {
        let snapshot = try DeviceTrendSnapshot.make(logs: [], goal: nil, now: now, zone: utc)
        var object = response(), facts = object["facts"] as! [String: Any]
        facts["days"] = (15...28).map { ["date": "2026-10-\($0)", "total_ml": 0, "drinks": 0] as [String: Any] }
        facts["last_7_days"] = ["total_ml": 0, "average_ml": 0, "logged_days": 0]
        facts["previous_7_days"] = ["total_ml": 0, "average_ml": 0, "logged_days": 0]
        facts["change_pct"] = NSNull(); facts["goal_ml"] = NSNull(); facts["goal_met_days_last_7"] = NSNull()
        facts["categories"] = [] as [Any]; facts["applicable_insights"] = [] as [String]
        facts["time_of_day_ml"] = ["morning_ml": 0, "afternoon_ml": 0, "evening_ml": 0, "night_ml": 0]
        object["facts"] = facts; object["insights"] = [] as [Any]; object["summary"] = "No drinks were recorded in this 14-day window."
        try decoded(object).validate(for: snapshot)
        XCTAssertThrowsError(try decoded(response()).validate(for: snapshot))
    }

    func testCapabilitiesRejectAnyProviderDispatchOrWrongBoundary() throws {
        let valid: [String: Any] = ["version": "device-insights-v1", "history_source": "on_device_summary", "max_days": 14, "provider_dispatch": false]
        try JSONDecoder().decode(DeviceInsightsCapabilities.self, from: JSONSerialization.data(withJSONObject: valid)).validate()
        for (key, value) in [("version", "other" as Any), ("history_source", "backend"), ("max_days", 13), ("provider_dispatch", true)] {
            var changed = valid; changed[key] = value
            XCTAssertThrowsError(try JSONDecoder().decode(DeviceInsightsCapabilities.self, from: JSONSerialization.data(withJSONObject: changed)).validate())
        }
    }

    func testAssistantEnvelopeKeepsNestedRequestAndOmitsNilContext() throws {
        let request = AssistantRequest(question: " coffee? ", source: "local_rules")
        let envelope = try DeviceAssistantEnvelope(request: request, todayLoggedTotalMl: nil)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(envelope)) as? [String: Any])
        XCTAssertNil(object["today_logged_total_ml"])
        let nested = try XCTUnwrap(object["request"] as? [String: Any])
        XCTAssertEqual(nested["question"] as? String, " coffee? ")
        XCTAssertEqual(nested["source"] as? String, "local_rules")
        XCTAssertEqual(object["consent_to_process"] as? Bool, true)
        XCTAssertThrowsError(try DeviceAssistantEnvelope(request: request, todayLoggedTotalMl: 0))
        XCTAssertThrowsError(try DeviceAssistantEnvelope(request: .recordedWonder(questionId: "coffee_counts"), todayLoggedTotalMl: nil))
        XCTAssertThrowsError(try DeviceAssistantEnvelope(request: .init(question_id: "invented"), todayLoggedTotalMl: nil))
        XCTAssertThrowsError(try DeviceAssistantEnvelope(request: .init(question: "  "), todayLoggedTotalMl: nil))
    }

    func testAssistantContextRequiresValidDateZoneAndExactReturnedPhoneTotal() throws {
        let request = AssistantRequest.make(questionId: "coffee_counts", includeToday: true, now: now, zone: utc)
        for total in [0, 1_000_000_000] { XCTAssertNoThrow(try DeviceAssistantEnvelope(request: request, todayLoggedTotalMl: total)) }
        for total in [nil, -1, 1_000_000_001] as [Int?] { XCTAssertThrowsError(try DeviceAssistantEnvelope(request: request, todayLoggedTotalMl: total)) }
        var invalid = request; invalid.date = "2026-02-30"
        XCTAssertThrowsError(try DeviceAssistantEnvelope(request: invalid, todayLoggedTotalMl: 250))
        invalid = request; invalid.timezone = "Mars/Base"
        XCTAssertThrowsError(try DeviceAssistantEnvelope(request: invalid, todayLoggedTotalMl: 250))
        let envelope = try DeviceAssistantEnvelope(request: request, todayLoggedTotalMl: 250)
        var answer: [String: Any] = ["version": "assistant-v1", "question_id": "coffee_counts", "topics": ["coffee_caffeine"], "escalation": false,
            "answers": [["topic": "coffee_caffeine", "text": "Reviewed answer.", "evidence": [["title": "Synthetic evidence", "url": "https://example.com/reviewed", "kind": "research"]]]],
            "intake_context": ["local_date": "2026-10-28", "timezone": request.timezone!, "beverage_total_ml": 250,
                               "note": "Confirmed beverage volume from this iPhone's log, not a hydration measurement."],
            "provenance": ["mode": "local_rules", "provider": NSNull(), "model": NSNull(), "answer_origin": "reviewed_text"], "limitations": ["Wellness information."]]
        func check(_ object: [String: Any]) throws {
            try envelope.validate(answer: JSONDecoder().decode(AssistantAnswer.self, from: JSONSerialization.data(withJSONObject: object)))
        }
        try check(answer)
        answer = replacing(answer, path: ["intake_context", "beverage_total_ml"][...], with: 999) as! [String: Any]
        XCTAssertThrowsError(try check(answer))
        answer = replacing(answer, path: ["intake_context", "beverage_total_ml"][...], with: 250) as! [String: Any]
        answer = replacing(answer, path: ["intake_context", "note"][...], with: "Server history") as! [String: Any]
        XCTAssertThrowsError(try check(answer))
    }
}
