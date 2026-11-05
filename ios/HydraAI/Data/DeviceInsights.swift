import Foundation

/// Aggregate construction performs no I/O. The caller owns connection disclosure and the explicit send action.
struct DeviceTrendSnapshot: Encodable, Sendable {
    struct Category: Encodable, Equatable, Sendable { let category: String; let total_ml: Int }
    let version = "device-insights-v1"
    let source = "on_device_summary"
    let consent_to_process = true
    let timezone: String
    let through_date: String
    let days: [TrendFacts.Day]
    let goal_ml: Int?
    let categories: [Category]
    let time_of_day_ml: TrendFacts.TimeOfDay
    var todayLoggedTotalMl: Int { days.last?.total_ml ?? 0 }

    private init(timezone: String, throughDate: String, days: [TrendFacts.Day], goal: Int?,
                 categories: [Category], times: TrendFacts.TimeOfDay) {
        self.timezone = timezone; through_date = throughDate; self.days = days; goal_ml = goal
        self.categories = categories; time_of_day_ml = times
    }

    static func make(logs: [BeverageLog], goal: Int?, now: Date = .now, zone: TimeZone = .current) throws -> Self {
        guard now.timeIntervalSince1970.isFinite, DeviceInsightBoundary.validZone(zone.identifier),
              goal.map({ (100...10_000).contains($0) }) ?? true else { throw ServiceError.invalidResponse }
        let local = DeviceInsightBoundary.formatter(zone)
        let through = local.string(from: now)
        guard let civil = DeviceInsightBoundary.day(through) else { throw ServiceError.invalidResponse }
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = zone
        var civilCalendar = Calendar(identifier: .gregorian); civilCalendar.timeZone = TimeZone(secondsFromGMT: 0)!
        let civilFormatter = DeviceInsightBoundary.formatter(civilCalendar.timeZone)
        // Generate civil dates in UTC so a skipped local date (e.g. Apia 2011-12-30) still has a zero bucket.
        let dates = try (-13...0).map { offset -> String in
            guard let value = civilCalendar.date(byAdding: .day, value: offset, to: civil) else { throw ServiceError.invalidResponse }
            let text = civilFormatter.string(from: value)
            guard DeviceInsightBoundary.day(text) != nil else { throw ServiceError.invalidResponse }
            return text
        }
        let positions = Dictionary(uniqueKeysWithValues: dates.enumerated().map { ($0.element, $0.offset) })
        var volumes = [Int](repeating: 0, count: 14), counts = volumes, times = [Int](repeating: 0, count: 4)
        var categories: [String: Int] = [:], total = 0
        for log in logs {
            guard (1...5000).contains(log.consumedMl), log.consumedAt.timeIntervalSince1970.isFinite,
                  log.consumedAt.timeIntervalSince1970 >= 946_684_800 else { throw ServiceError.invalidResponse }
            // Persisted future timestamps are valid after clock rollback. Match LocalBeverageService's local-date
            // bucketing: include same-day entries, exclude other days outside this window, never export timestamps.
            guard let index = positions[local.string(from: log.consumedAt)] else { continue }
            let (next, overflow) = total.addingReportingOverflow(log.consumedMl)
            guard !overflow, next <= 1_000_000_000, counts[index] < 1000 else { throw ServiceError.invalidResponse }
            total = next; volumes[index] += log.consumedMl; counts[index] += 1
            let hour = calendar.component(.hour, from: log.consumedAt)
            let period = (5..<12).contains(hour) ? 0 : (12..<17).contains(hour) ? 1 : (17..<22).contains(hour) ? 2 : 3
            times[period] += log.consumedMl
            let category = DeviceInsightBoundary.category(log.beverageType ?? log.category)
            categories[category, default: 0] += log.consumedMl
        }
        let ranked = categories.map { Category(category: $0.key, total_ml: $0.value) }.sorted {
            $0.total_ml == $1.total_ml ? $0.category < $1.category : $0.total_ml > $1.total_ml
        }
        guard ranked.count <= 12, ranked.reduce(0, { $0 + $1.total_ml }) == total, times.reduce(0, +) == total else { throw ServiceError.invalidResponse }
        return Self(timezone: zone.identifier, throughDate: through,
            days: dates.indices.map { .init(date: dates[$0], total_ml: volumes[$0], drinks: counts[$0]) }, goal: goal,
            categories: ranked, times: .init(morning_ml: times[0], afternoon_ml: times[1], evening_ml: times[2], night_ml: times[3]))
    }

    fileprivate var expectedFacts: TrendFacts {
        func week(_ days: ArraySlice<TrendFacts.Day>) -> TrendFacts.Week {
            let total = days.reduce(0) { $0 + $1.total_ml }
            return .init(total_ml: total, average_ml: DeviceInsightBoundary.rounded(total, over: 7), logged_days: days.filter { $0.drinks > 0 }.count)
        }
        let last = week(days.suffix(7)), previous = week(days.prefix(7)), total = days.reduce(0) { $0 + $1.total_ml }
        let applicable = [("week_over_week", last.logged_days > 0 && previous.logged_days > 0),
                          ("goal_progress", goal_ml != nil && last.logged_days > 0),
                          ("logging_consistency", days.contains { $0.drinks > 0 }), ("beverage_mix", !categories.isEmpty), ("timing", total > 0)]
            .filter(\.1).map(\.0)
        return .init(version: "wonder-trends-facts-v1", timezone: timezone, through_date: through_date, window_days: 14, days: days,
            last_7_days: last, previous_7_days: previous,
            change_pct: previous.total_ml == 0 ? nil : DeviceInsightBoundary.rounded(100 * (last.total_ml - previous.total_ml), over: previous.total_ml),
            goal_ml: goal_ml, goal_met_days_last_7: goal_ml.map { goal in days.suffix(7).filter { $0.total_ml >= goal }.count },
            categories: categories.map { .init(category: $0.category, total_ml: $0.total_ml,
                share_pct: total == 0 ? 0 : DeviceInsightBoundary.rounded(100 * $0.total_ml, over: total)) },
            other_categories_ml: 0, time_of_day_ml: time_of_day_ml, applicable_insights: applicable)
    }
}

struct DeviceTrendSummary: Decodable, Sendable {
    struct Insight: Decodable, Identifiable, Sendable {
        let id: String; let title: String; let text: String
        enum CodingKeys: String, CodingKey { case id, title, text }
        init(from decoder: Decoder) throws {
            try DeviceInsightBoundary.keys(decoder, ["id", "title", "text"])
            let c = try decoder.container(keyedBy: CodingKeys.self)
            id = try c.decode(String.self, forKey: .id); title = try c.decode(String.self, forKey: .title); text = try c.decode(String.self, forKey: .text)
        }
    }
    struct Provenance: Decodable, Sendable {
        let mode: String; let provider: String?; let model: String?; let history_source: String; let storage: String
        enum CodingKeys: String, CodingKey { case mode, provider, model, history_source, storage }
        init(from decoder: Decoder) throws {
            try DeviceInsightBoundary.keys(decoder, ["mode", "provider", "model", "history_source", "storage"])
            let c = try decoder.container(keyedBy: CodingKeys.self)
            mode = try c.decode(String.self, forKey: .mode); provider = try c.decodeIfPresent(String.self, forKey: .provider)
            model = try c.decodeIfPresent(String.self, forKey: .model); history_source = try c.decode(String.self, forKey: .history_source)
            storage = try c.decode(String.self, forKey: .storage)
        }
    }
    let version: String; let source: String; let facts: TrendFacts; let payload_sha256: String
    let summary: String; let insights: [Insight]; let provenance: Provenance
    enum CodingKeys: String, CodingKey { case version, source, facts, payload_sha256, summary, insights, provenance }
    init(from decoder: Decoder) throws {
        try DeviceInsightBoundary.keys(decoder, ["version", "source", "facts", "payload_sha256", "summary", "insights", "provenance"])
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = try c.decode(String.self, forKey: .version); source = try c.decode(String.self, forKey: .source)
        let factDecoder = try c.superDecoder(forKey: .facts)
        try DeviceInsightBoundary.factKeys(factDecoder)
        facts = try TrendFacts(from: factDecoder)
        payload_sha256 = try c.decode(String.self, forKey: .payload_sha256); summary = try c.decode(String.self, forKey: .summary)
        insights = try c.decode([Insight].self, forKey: .insights); provenance = try c.decode(Provenance.self, forKey: .provenance)
    }
    func validate(for snapshot: DeviceTrendSnapshot) throws {
        guard version == "device-insights-v1", source == "on_device_summary", facts == snapshot.expectedFacts,
              provenance.mode == "deterministic", provenance.provider == nil, provenance.model == nil,
              provenance.history_source == "on_device_summary", provenance.storage == "ephemeral",
              payload_sha256.utf8.count == 64, payload_sha256.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
              DeviceInsightBoundary.text(summary, limit: 240), insights.count <= 3,
              insights.isEmpty == facts.applicable_insights.isEmpty, Set(insights.map(\.id)).count == insights.count,
              insights.allSatisfy({ facts.applicable_insights.contains($0.id) && DeviceInsightBoundary.text($0.title, limit: 80)
                  && DeviceInsightBoundary.text($0.text, limit: 300) }) else { throw ServiceError.invalidResponse }
        // This digest describes canonical server facts. No hash equality claim is made from Swift's different nil encoding.
    }
}

struct DeviceInsightsCapabilities: Decodable, Sendable {
    let version: String; let history_source: String; let max_days: Int; let provider_dispatch: Bool
    enum CodingKeys: String, CodingKey { case version, history_source, max_days, provider_dispatch }
    init(from decoder: Decoder) throws {
        try DeviceInsightBoundary.keys(decoder, ["version", "history_source", "max_days", "provider_dispatch"])
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = try c.decode(String.self, forKey: .version); history_source = try c.decode(String.self, forKey: .history_source)
        max_days = try c.decode(Int.self, forKey: .max_days); provider_dispatch = try c.decode(Bool.self, forKey: .provider_dispatch)
    }
    func validate() throws {
        guard version == "device-insights-v1", history_source == "on_device_summary", max_days == 14, !provider_dispatch else { throw ServiceError.invalidResponse }
    }
}

struct DeviceAssistantEnvelope: Encodable, Sendable {
    let version = "device-insights-v1"; let source = "on_device_summary"; let consent_to_process = true
    let request: AssistantRequest
    let today_logged_total_ml: Int?
    init(request: AssistantRequest, todayLoggedTotalMl: Int? = nil) throws {
        let known: Set<String> = ["coffee_counts", "creatine_water", "workout_sweat", "milk_vs_water", "daily_amount", "logged_meaning", "heart_rate", "hot_weather"]
        guard (request.question == nil) != (request.question_id == nil), request.source == nil || request.source == "local_rules" else { throw ServiceError.invalidResponse }
        if let question = request.question {
            guard question.unicodeScalars.count <= 1000, (1...300).contains(question.trimmingCharacters(in: .whitespacesAndNewlines).unicodeScalars.count) else { throw ServiceError.invalidResponse }
        }
        if let id = request.question_id, !known.contains(id) { throw ServiceError.invalidResponse }
        if request.context_scope == "today_logged_total" {
            guard let date = request.date, DeviceInsightBoundary.day(date) != nil, let zone = request.timezone,
                  DeviceInsightBoundary.validZone(zone), let total = todayLoggedTotalMl, (0...1_000_000_000).contains(total) else { throw ServiceError.invalidResponse }
        } else {
            guard request.context_scope == "none", request.date == nil, request.timezone == nil, todayLoggedTotalMl == nil else { throw ServiceError.invalidResponse }
        }
        self.request = request; today_logged_total_ml = todayLoggedTotalMl
    }
    func validate(answer: AssistantAnswer) throws {
        try answer.validate(request: request)
        if let context = answer.intake_context {
            guard let total = today_logged_total_ml, context.beverage_total_ml == Double(total),
                  context.note == "Confirmed beverage volume from this iPhone's log, not a hydration measurement." else { throw ServiceError.invalidResponse }
        }
    }
}

private enum DeviceInsightBoundary {
    static let zones = Set(TimeZone.knownTimeZoneIdentifiers).union(["UTC", "GMT"])
    static let categories: Set<String> = ["beer", "coffee", "energy", "juice", "milk", "other", "plant_milk", "soda", "sports", "tea", "water", "wine"]
    static func validZone(_ value: String) -> Bool { zones.contains(value) }
    static func formatter(_ zone: TimeZone) -> DateFormatter {
        let f = DateFormatter(); f.calendar = Calendar(identifier: .gregorian); f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = zone; f.dateFormat = "yyyy-MM-dd"; f.isLenient = false
        return f
    }
    static func day(_ value: String) -> Date? {
        guard value.range(of: #"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"#, options: .regularExpression) != nil else { return nil }
        let f = formatter(TimeZone(secondsFromGMT: 0)!)
        guard let date = f.date(from: value), f.string(from: date) == value else { return nil }
        return date
    }
    static func category(_ value: String) -> String {
        let value = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let aliases = ["energy drink": "energy", "energy_drink": "energy", "sports drink": "sports", "sports_drink": "sports",
                       "plant milk": "plant_milk", "beverage": "other"]
        if let alias = aliases[value] { return alias }
        return categories.contains(value) ? value : "other"
    }
    /// Python round() uses nearest, ties to even, including signed week-over-week changes.
    static func rounded(_ numerator: Int, over denominator: Int) -> Int {
        let quotient = numerator / denominator, remainder = abs(numerator % denominator)
        if remainder * 2 < denominator || (remainder * 2 == denominator && quotient.isMultiple(of: 2)) { return quotient }
        return quotient + (numerator < 0 ? -1 : 1)
    }
    static func text(_ value: String, limit: Int) -> Bool {
        (1...limit).contains(value.unicodeScalars.count) && !value.unicodeScalars.contains { CharacterSet.controlCharacters.contains($0) }
    }
    struct Key: CodingKey {
        let stringValue: String; var intValue: Int? { nil }
        init(_ value: String) { stringValue = value }
        init?(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { return nil }
    }
    static func keys(_ decoder: Decoder, _ expected: Set<String>) throws {
        guard Set(try decoder.container(keyedBy: Key.self).allKeys.map(\.stringValue)) == expected else { throw ServiceError.invalidResponse }
    }
    static func factKeys(_ decoder: Decoder) throws {
        try keys(decoder, ["version", "timezone", "through_date", "window_days", "days", "last_7_days", "previous_7_days", "change_pct",
                           "goal_ml", "goal_met_days_last_7", "categories", "other_categories_ml", "time_of_day_ml", "applicable_insights"])
        let c = try decoder.container(keyedBy: Key.self)
        for name in ["last_7_days", "previous_7_days"] { try keys(c.superDecoder(forKey: Key(name)), ["total_ml", "average_ml", "logged_days"]) }
        try keys(c.superDecoder(forKey: Key("time_of_day_ml")), ["morning_ml", "afternoon_ml", "evening_ml", "night_ml"])
        for (name, fields, maximum) in [("days", Set(["date", "total_ml", "drinks"]), 14), ("categories", Set(["category", "total_ml", "share_pct"]), 12)] {
            var array = try c.nestedUnkeyedContainer(forKey: Key(name))
            guard (array.count ?? maximum + 1) <= maximum else { throw ServiceError.invalidResponse }
            while !array.isAtEnd { try keys(array.superDecoder(), fields) }
        }
    }
}
