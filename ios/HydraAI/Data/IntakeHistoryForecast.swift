import Foundation

/// A history-only projection of the forecast contract; never a drinking target.
struct IntakeHistoryForecast: Decodable, Sendable {
    struct UnavailableRange: Decodable, Sendable {
        let status: String
        let lowerMl: Double?
        let upperMl: Double?
        enum CodingKeys: String, CodingKey {
            case status, lowerMl = "lower_ml", upperMl = "upper_ml"
        }
        var isUnavailable: Bool { status == "insufficient_data" && lowerMl == nil && upperMl == nil }
    }
    struct Day: Decodable, Sendable {
        let localDate: String
        let timezone: String
        let beverageTotalMl: Double
        enum CodingKeys: String, CodingKey {
            case localDate = "local_date", timezone, beverageTotalMl = "beverage_total_ml"
        }
    }
    struct History: Decodable, Sendable {
        let windowDays: Int
        let loggedDays: Int
        let daysWithoutLogs: Int
        let kind: String
        let beverageLowerMl: Double?
        let beverageUpperMl: Double?
        let days: [Day]
        let completeness: String
        enum CodingKeys: String, CodingKey {
            case windowDays = "window_days", loggedDays = "logged_days", daysWithoutLogs = "days_without_logs"
            case kind, days, completeness
            case beverageLowerMl = "beverage_lower_ml", beverageUpperMl = "beverage_upper_ml"
        }
    }
    let version: String
    let generatedAt: String
    let localDate: String
    let timezone: String
    let historicalLoggedIntake: History
    let dailyRequirement: UnavailableRange
    let exerciseLoss: UnavailableRange
    let predictionValidated: Bool
    enum CodingKeys: String, CodingKey {
        case version, generatedAt = "generated_at", localDate = "local_date", timezone
        case historicalLoggedIntake = "historical_logged_intake", dailyRequirement = "daily_requirement"
        case exerciseLoss = "exercise_loss", predictionValidated = "prediction_validated"
    }

    func validate(date: String, timezone requestedZone: String) throws {
        guard version == "personal-exercise-loss-v1", localDate == date, timezone == requestedZone,
              let zone = TimeZone(identifier: requestedZone), !predictionValidated,
              dailyRequirement.isUnavailable, exerciseLoss.isUnavailable,
              generatedAt.hasSuffix("Z") || generatedAt.hasSuffix("+00:00") else { throw ServiceError.invalidResponse }
        let timestamp = ISO8601DateFormatter()
        timestamp.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if timestamp.date(from: generatedAt) == nil {
            timestamp.formatOptions = [.withInternetDateTime]
            guard timestamp.date(from: generatedAt) != nil else { throw ServiceError.invalidResponse }
        }
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian); formatter.timeZone = zone
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.dateFormat = "yyyy-MM-dd"
        formatter.isLenient = false
        guard let end = formatter.date(from: date), formatter.string(from: end) == date else { throw ServiceError.invalidResponse }
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = zone
        guard let start = calendar.date(byAdding: .day, value: -7, to: end) else { throw ServiceError.invalidResponse }
        let history = historicalLoggedIntake
        guard history.windowDays == 7, (0...7).contains(history.loggedDays),
              history.daysWithoutLogs == 7 - history.loggedDays,
              history.days.count == history.loggedDays,
              history.kind == "descriptive_logged_totals_not_needs", history.completeness == "unverified",
              Set(history.days.map(\.localDate)).count == history.days.count else { throw ServiceError.invalidResponse }
        for day in history.days {
            guard day.timezone == requestedZone, day.beverageTotalMl.isFinite, day.beverageTotalMl >= 0,
                  let instant = formatter.date(from: day.localDate), formatter.string(from: instant) == day.localDate,
                  instant >= start, instant < end else { throw ServiceError.invalidResponse }
        }
        if history.days.isEmpty {
            guard history.beverageLowerMl == nil, history.beverageUpperMl == nil else { throw ServiceError.invalidResponse }
        } else {
            guard let lower = history.beverageLowerMl, let upper = history.beverageUpperMl,
                  lower.isFinite, upper.isFinite, lower >= 0, upper >= lower,
                  lower == history.days.map(\.beverageTotalMl).min(),
                  upper == history.days.map(\.beverageTotalMl).max() else { throw ServiceError.invalidResponse }
        }
    }
}
