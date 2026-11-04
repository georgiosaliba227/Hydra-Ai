import Foundation

enum HydrationScoreError: Error { case goalRequired, unavailable }
enum HydrationScoreAvailability: Equatable {
    case available(HydrationScoreFacts), goalRequired, unavailable
    var facts: HydrationScoreFacts? { if case .available(let value) = self { value } else { nil } }
}

/// Product-defined research rubric. It cannot estimate physiological hydration.
struct HydrationScoreFacts: Codable, Equatable, Sendable {
    struct Day: Codable, Equatable, Sendable {
        let local_date: String
        let total_ml: Double
        let logged: Bool
    }
    struct Components: Codable, Equatable, Sendable {
        let today_points: Double, consistency_points: Double, measurement_points: Double
    }
    let version: String
    let local_date: String
    let timezone: String
    let goal_ml: Int
    let today_ml: Double
    let previous_days: [Day]
    let measurement_count: Int
    let components: Components
    let score: Int
    let research_only: Bool
}

enum HydrationScore {
    static let version = "hydration-research-score-v1"
    static func calendar(_ timezone: TimeZone) -> Calendar {
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = timezone; return calendar
    }
    static func localDate(_ date: Date, timezone: TimeZone) -> String {
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = calendar(timezone); formatter.timeZone = timezone; formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }
    static func calculate(logs: [BeverageLog], goalMl: Int?, samples: [WorkoutForecastRequest.Sample],
                          now: Date, timezone: TimeZone) throws -> HydrationScoreFacts {
        guard let goalMl else { throw HydrationScoreError.goalRequired }
        guard (100...10000).contains(goalMl), now.timeIntervalSinceReferenceDate.isFinite,
              Set(logs.map(\.id)).count == logs.count,
              logs.allSatisfy({ (1...5000).contains($0.consumedMl) && $0.revision >= 1 && $0.consumedAt.timeIntervalSinceReferenceDate.isFinite })
        else { throw HydrationScoreError.unavailable }
        try CalibrationHistoryValidation.validate(samples, now: now)
        let calendar = calendar(timezone), today = calendar.startOfDay(for: now)
        let date = localDate(today, timezone: timezone)
        var totals: [String: Double] = [:]
        for log in logs where DateOrdering.notAfter(log.consumedAt, now) {
            let key = localDate(log.consumedAt, timezone: timezone)
            totals[key, default: 0] += Double(log.consumedMl)
        }
        let previous: [HydrationScoreFacts.Day] = try (1...7).reversed().map { offset in
            guard let day = calendar.date(byAdding: .day, value: -offset, to: today) else { throw HydrationScoreError.unavailable }
            let key = localDate(day, timezone: timezone), amount = totals[key, default: 0]
            return .init(local_date: key, total_ml: amount, logged: amount > 0)
        }
        let todayMl = totals[date, default: 0]
        guard todayMl <= 1_000_000_000, previous.allSatisfy({ $0.total_ml <= 1_000_000_000 }) else { throw HydrationScoreError.unavailable }
        let t = min(todayMl / Double(goalMl), 1)
        let c = previous.reduce(0) { $0 + min($1.total_ml / Double(goalMl), 1) } / 7
        let m = Double(min(samples.count, 6)) / 6
        let components = HydrationScoreFacts.Components(today_points: 50 * t,
            consistency_points: 30 * c, measurement_points: 20 * m)
        let score = Int(floor(components.today_points + components.consistency_points + components.measurement_points + 0.5))
        return .init(version: version, local_date: date, timezone: timezone.identifier, goal_ml: goalMl, today_ml: todayMl,
            previous_days: previous, measurement_count: samples.count, components: components, score: score, research_only: true)
    }
    static func availability(logs: [BeverageLog], summary: DailySummary?, state: LoadState,
                             mutationPending: Bool, isOffline: Bool, historyReadable: Bool,
                             samples: [WorkoutForecastRequest.Sample], now: Date, timezone: TimeZone) -> HydrationScoreAvailability {
        guard state == .loaded, !mutationPending, !isOffline, let summary,
              summary.localDate == localDate(now, timezone: timezone), summary.timezone == timezone.identifier
        else { return .unavailable }
        guard let goal = summary.goal else { return .goalRequired }
        guard goal.isValid, historyReadable,
              let facts = try? calculate(logs: logs, goalMl: goal.dailyBeverageGoalMl, samples: samples, now: now, timezone: timezone),
              abs(facts.today_ml - summary.beverageTotalMl) <= 1e-9 else { return .unavailable }
        return .available(facts)
    }
}

extension HydrationScoreFacts.Day {
    enum CodingKeys: String, CodingKey { case local_date, total_ml, logged }
    init(from decoder: Decoder) throws {
        try scoreExactKeys(decoder, ["local_date", "total_ml", "logged"])
        let c = try decoder.container(keyedBy: CodingKeys.self)
        local_date = try c.decode(String.self, forKey: .local_date); total_ml = try c.decode(Double.self, forKey: .total_ml)
        logged = try c.decode(Bool.self, forKey: .logged)
    }
}
extension HydrationScoreFacts.Components {
    enum CodingKeys: String, CodingKey { case today_points, consistency_points, measurement_points }
    init(from decoder: Decoder) throws {
        try scoreExactKeys(decoder, ["today_points", "consistency_points", "measurement_points"])
        let c = try decoder.container(keyedBy: CodingKeys.self)
        today_points = try c.decode(Double.self, forKey: .today_points)
        consistency_points = try c.decode(Double.self, forKey: .consistency_points)
        measurement_points = try c.decode(Double.self, forKey: .measurement_points)
    }
}
extension HydrationScoreFacts {
    enum CodingKeys: String, CodingKey {
        case version, local_date, timezone, goal_ml, today_ml, previous_days, measurement_count, components, score, research_only
    }
    init(from decoder: Decoder) throws {
        try scoreExactKeys(decoder, ["version", "local_date", "timezone", "goal_ml", "today_ml", "previous_days", "measurement_count", "components", "score", "research_only"])
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = try c.decode(String.self, forKey: .version); local_date = try c.decode(String.self, forKey: .local_date)
        timezone = try c.decode(String.self, forKey: .timezone); goal_ml = try c.decode(Int.self, forKey: .goal_ml)
        today_ml = try c.decode(Double.self, forKey: .today_ml); previous_days = try c.decode([Day].self, forKey: .previous_days)
        measurement_count = try c.decode(Int.self, forKey: .measurement_count); components = try c.decode(Components.self, forKey: .components)
        score = try c.decode(Int.self, forKey: .score); research_only = try c.decode(Bool.self, forKey: .research_only)
    }
    func validate(expected: HydrationScoreFacts? = nil) throws {
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian); formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"; formatter.isLenient = false
        guard version == HydrationScore.version, research_only, (100...10000).contains(goal_ml),
              (0...32).contains(measurement_count), timezone.count <= 128, TimeZone(identifier: timezone) != nil,
              let today = formatter.date(from: local_date), formatter.string(from: today) == local_date,
              today_ml.isFinite, (0...1_000_000_000).contains(today_ml), previous_days.count == 7
        else { throw ServiceError.invalidResponse }
        var civil = Calendar(identifier: .gregorian); civil.timeZone = TimeZone(secondsFromGMT: 0)!
        for (index, day) in previous_days.enumerated() {
            guard let expectedDay = civil.date(byAdding: .day, value: index - 7, to: today),
                  day.local_date == formatter.string(from: expectedDay), day.total_ml.isFinite,
                  (0...1_000_000_000).contains(day.total_ml), day.logged == (day.total_ml > 0) else { throw ServiceError.invalidResponse }
        }
        let t = min(today_ml / Double(goal_ml), 1)
        let c = previous_days.reduce(0) { $0 + min($1.total_ml / Double(goal_ml), 1) } / 7
        let m = Double(min(measurement_count, 6)) / 6
        let numeric = Components(today_points: 50 * t, consistency_points: 30 * c, measurement_points: 20 * m)
        func close(_ a: Double, _ b: Double) -> Bool { a.isFinite && b.isFinite && abs(a - b) <= 1e-9 }
        guard close(components.today_points, numeric.today_points), close(components.consistency_points, numeric.consistency_points),
              close(components.measurement_points, numeric.measurement_points),
              score == Int(floor(numeric.today_points + numeric.consistency_points + numeric.measurement_points + 0.5))
        else { throw ServiceError.invalidResponse }
        if let expected {
            guard local_date == expected.local_date, timezone == expected.timezone, goal_ml == expected.goal_ml,
                  today_ml == expected.today_ml, previous_days == expected.previous_days,
                  measurement_count == expected.measurement_count, score == expected.score,
                  close(components.today_points, expected.components.today_points),
                  close(components.consistency_points, expected.components.consistency_points),
                  close(components.measurement_points, expected.components.measurement_points) else { throw ServiceError.invalidResponse }
        }
    }
}
