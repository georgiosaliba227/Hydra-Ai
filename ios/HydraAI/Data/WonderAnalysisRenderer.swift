import Foundation

/// Native reconstruction of the versioned backend renderer. Provider/response prose is never authoritative.
/// Only the model's validated ranked IDs choose which locally vetted factual clauses are displayed.
enum WonderAnalysisRenderer {
    private static let posix = Locale(identifier: "en_US_POSIX")
    static func whole(_ value: Double) -> String {
        let rounded = value.rounded(.toNearestOrEven)
        return rounded == 0 ? "0" : String(format: "%.0f", locale: posix, rounded)
    }
    static func duration(_ value: Double) -> String {
        value.rounded() == value ? whole(value) : String(value)
    }
    private static func decimal(_ value: Double) -> String {
        var result = String(format: "%.1f", locale: posix, value)
        while result.hasSuffix("0") { result.removeLast() }
        if result.hasSuffix(".") { result.removeLast() }
        return result
    }
    static func comparisons(_ facts: WonderAnalysisFacts) -> [String: String] {
        guard let c = facts.values["workout_comparison"]?.object else { return [:] }
        var result: [String: String] = [:]
        for (kind, planned, typical, tolerance, higher, lower) in [
            ("duration", "planned_duration_minutes", "typical_duration_minutes", 0.0, "longer", "shorter"),
            ("temperature", "planned_temperature_c", "typical_temperature_c", 3.0, "warmer", "cooler"),
            ("humidity", "planned_humidity_percent", "typical_humidity_percent", 10.0, "more humid", "less humid")] {
            if let current = c[planned]?.number, let prior = c[typical]?.number {
                let close = kind == "duration" ? abs(current - prior) * 100 <= prior * 10 : abs(current - prior) < tolerance
                result[kind] = close ? "similar" : current > prior ? higher : lower
            }
        }
        return result
    }
    static func applicability(_ facts: WonderAnalysisFacts) -> Set<String> {
        let v = facts.values
        func number(_ group: String, _ key: String) -> Double? { v[group]?.object?[key]?.number }
        func text(_ group: String, _ key: String) -> String? { v[group]?.object?[key]?.text }
        let synthetic = v["mode"] == .text("synthetic_demo"), estimated = text("forecast", "status") == "estimated"
        let comparison = comparisons(facts), context = v["trend_context"]?.object
        let missing = v["missing_inputs"].map { if case .array(let values) = $0 { return !values.isEmpty }; return false } ?? false
        let environmentMissing = number("environment", "temperature_c") == nil || number("environment", "humidity_percent") == nil
        let knownElectrolyte = ["sodium", "potassium"].contains { text("intake", $0 + "_status") == "complete" }
        let incompleteElectrolyte = ["sodium", "potassium"].contains { text("intake", $0 + "_status") != "complete" }
        let currentDays = context?["last_7_days"]?.object?["logged_days"]?.number ?? 0
        let previousDays = context?["previous_7_days"]?.object?["logged_days"]?.number ?? 0
        let timing = context?["time_of_day_ml"]?.object?.values.compactMap(\.number).reduce(0, +) ?? 0
        let actual = text("forecast", "interval_kind") == "conditional_measurement_envelope"
        let accounting = text("accounting", "status") == "estimated"
        let conditions: [String: Bool] = [
            "summary_record": true, "summary_estimate": estimated, "summary_missing": missing,
            "loss_estimate": estimated, "loss_no_estimate": !estimated,
            "loss_history": (number("calibration", "comparable_samples") ?? 0) > 0,
            "loss_limited_history": !synthetic && (number("calibration", "comparable_samples") ?? 0) < 3,
            "loss_actual": estimated && actual,
            "activity_context": number("activity", "duration_minutes") != nil,
            "activity_missing": number("activity", "duration_minutes") == nil,
            "activity_duration_comparison": comparison["duration"] != nil,
            "activity_history": (number("calibration", "total_samples") ?? 0) > 0,
            "environment_reported": number("environment", "temperature_c") != nil || number("environment", "humidity_percent") != nil,
            "environment_missing": environmentMissing,
            "environment_shift": ["temperature", "humidity"].contains { comparison[$0].map { $0 != "similar" } ?? false },
            "environment_context": true,
            "beverage_volume": !synthetic && (number("intake", "beverage_count") ?? 0) > 0,
            "beverage_no_logs": !synthetic && number("intake", "beverage_count") == 0,
            "beverage_synthetic": synthetic,
            "beverage_water_known": number("intake", "water_ml") != nil,
            "beverage_water_unknown": !synthetic && number("intake", "water_ml") == nil,
            "beverage_electrolytes_known": knownElectrolyte,
            "beverage_electrolytes_incomplete": !synthetic && incompleteElectrolyte,
            "trends_logged_days": (number("trends", "logged_days") ?? 0) > 0,
            "trends_no_logs": number("trends", "logged_days") == 0,
            "trends_synthetic": synthetic,
            "trends_week_change": context != nil && context?["change_pct"]?.number != nil && currentDays > 0 && previousDays > 0,
            "trends_week_missing": context != nil && (currentDays < 7 || previousDays < 7),
            "trends_timing": context != nil && timing > 0,
            "trends_calibration": (number("calibration", "comparable_samples") ?? 0) > 0,
            "uncertainty_missing": missing,
            "uncertainty_history": ["historical_error_envelope", "personal_runtime_measurement_error_envelope"].contains(text("forecast", "interval_kind") ?? ""),
            "uncertainty_actual": actual, "uncertainty_synthetic": synthetic,
            "uncertainty_accounting": accounting, "uncertainty_no_accounting": !accounting,
            "measurement_comparable": true,
            "measurement_composition": !synthetic && (number("intake", "water_ml") == nil || incompleteElectrolyte),
            "measurement_environment": environmentMissing,
            "measurement_repeat": (number("calibration", "comparable_samples") ?? 0) > 0,
            "measurement_timing": !accounting && !synthetic]
        return Set(conditions.filter(\.value).keys)
    }
    static func placeholders(_ facts: WonderAnalysisFacts) throws -> [String: String] {
        try facts.validateShape()
        let v = facts.values
        func n(_ group: String, _ key: String) -> Double? { v[group]?.object?[key]?.number }
        func s(_ group: String, _ key: String) -> String? { v[group]?.object?[key]?.text }
        func w(_ value: Double) -> String { whole(value) }
        let loss = s("forecast", "status") == "estimated"
            ? "research estimate \(w(floor(n("forecast", "lower_ml")!))) to \(w(ceil(n("forecast", "upper_ml")!))) mL, with point \(w(n("forecast", "value_ml")!)) mL"
            : "no numerical estimate is available"
        let beverage = n("intake", "beverage_volume_ml").map { "\(w($0)) mL of logged beverage volume" } ?? "personal beverage logs are excluded from this synthetic case"
        let activity = n("activity", "duration_minutes").map { "\(Self.duration($0)) minutes of \(s("activity", "intensity") ?? "unspecified-intensity") \(s("activity", "activity") ?? "exercise")" } ?? "workout duration and activity are unavailable"
        let environment = [n("environment", "temperature_c").map { "temperature \(decimal($0)) °C" } ?? "temperature unavailable",
                           n("environment", "humidity_percent").map { "humidity \(decimal($0))%" } ?? "humidity unavailable"].joined(separator: "; ")
        let nutrient = ["sodium", "potassium"].map { name in
            n("intake", name + "_mg").map { "documented \(name) \(decimal($0)) mg" }
                ?? "\(name) composition \(s("intake", name + "_status") == "partial" ? "incomplete; total withheld" : "unknown")"
        }.joined(separator: "; ")
        let history: String
        if let days = n("trends", "logged_days"), days > 0 {
            history = "\(w(days)) logged days in the \(w(n("trends", "window_days")!))-day descriptive record; recorded day totals range from \(w(floor(n("trends", "beverage_lower_ml")!))) to \(w(ceil(n("trends", "beverage_upper_ml")!))) mL"
        } else { history = n("trends", "logged_days") == 0 ? "no prior logged-day totals are available" : "personal logged history is excluded from this synthetic case" }
        let comparison = comparisons(facts), context = v["workout_comparison"]?.object
        let duration = comparison["duration"].map { "planned duration \(w(context!["planned_duration_minutes"]!.number!)) minutes is \($0) relative to the prior typical duration \(w(context!["typical_duration_minutes"]!.number!)) minutes" } ?? "duration comparison unavailable"
        var environmentComparison: [String] = []
        if let context {
            for (kind, planned, prior, unit) in [("temperature", "planned_temperature_c", "typical_temperature_c", "°C"), ("humidity", "planned_humidity_percent", "typical_humidity_percent", "%")] {
                if let description = comparison[kind] {
                    environmentComparison.append("planned \(kind) \(w(context[planned]!.number!)) \(unit) is \(description) relative to prior typical \(w(context[prior]!.number!)) \(unit)")
                }
            }
        }
        var weeklyComparison = "logged pattern context unavailable", weeklyLogging = weeklyComparison, timingPattern = weeklyComparison
        if let trend = v["trend_context"]?.object {
            let current = trend["last_7_days"]!.object!, previous = trend["previous_7_days"]!.object!
            if let change = trend["change_pct"]?.number {
                let label = change != 0 ? "\(w(abs(change)))% \(change > 0 ? "more" : "less") logged volume"
                    : current["total_ml"] == previous["total_ml"] ? "unchanged logged volume" : "percentage change rounds to 0%"
                weeklyComparison = "\(w(current["total_ml"]!.number!)) mL logged in the latest week versus \(w(previous["total_ml"]!.number!)) mL in the preceding week; \(label)"
            }
            weeklyLogging = "\(w(current["logged_days"]!.number!)) logged days in the latest week and \(w(previous["logged_days"]!.number!)) in the preceding week; coverage is unverified"
            let periods = trend["time_of_day_ml"]!.object!, peak = periods.values.compactMap(\.number).max() ?? 0
            let winners = periods.filter { $0.value.number == peak }.keys.map { $0.replacingOccurrences(of: "_ml", with: "") }
            timingPattern = peak > 0 && winners.count == 1 ? "the \(winners[0]) bucket has the largest recorded volume, \(w(peak)) mL across the logged window" : "the logged timing buckets have no unique largest volume"
        }
        let missing: [String]
        if case .array(let codes) = v["missing_inputs"] { missing = codes.compactMap { $0.text.flatMap { missingLabels[$0] } } } else { missing = [] }
        return ["record_summary": beverage + "; " + loss,
            "research_scope": "this is research context, not total body hydration, an intake target or a diagnosis",
            "loss_estimate": loss,
            "calibration_context": "\(w(n("calibration", "total_samples")!)) supplied observations; \(w(n("calibration", "comparable_samples")!)) comparable and \(w(n("calibration", "recent_samples")!)) recent comparable observations",
            "activity_context": activity,
            "activity_history": "workout comparability depends on documented conditions, protocol and instrument error bounds",
            "environment_context": environment, "environment_role": "environment is context; no added weather adjustment is applied",
            "beverage_context": beverage,
            "water_context": n("intake", "water_ml").map { "documented water content \(w($0)) mL" } ?? "water composition unknown",
            "electrolyte_context": nutrient,
            "logging_scope": "logging completeness is unverified; volume does not measure retention",
            "history_context": history,
            "trend_scope": "logged-day patterns do not determine physiological needs; logging coverage is unverified and absent logs are not measured zero consumption",
            "uncertainty_context": "measurement errors and incompatible observations limit interpretation; historical envelopes do not guarantee future coverage",
            "missing_context": missing.isEmpty ? "the supplied fields do not remove measurement and generalization uncertainty" : "missing evidence includes " + missing.joined(separator: "; "),
            "accounting_context": "matched completed-workout arithmetic is unavailable; planned losses are not subtracted",
            "duration_comparison": duration,
            "environment_comparison": environmentComparison.isEmpty ? "environment comparison unavailable" : environmentComparison.joined(separator: "; "),
            "weekly_comparison": weeklyComparison, "weekly_logging": weeklyLogging, "timing_pattern": timingPattern,
            "measurement_context": "comparable dry before-and-after weighing, recorded workout consumption and urine, timing, environment and instrument error bounds"]
    }
    static func render(_ template: String, values: [String: String]) -> String {
        values.reduce(template) { $0.replacingOccurrences(of: "{\($1.key)}", with: $1.value) }
    }
}

extension WonderAnalysisRenderer {
    static let requiredCaveats: [String: String] = [
        "summary": "{research_scope}.",
        "workout_loss": "{uncertainty_context}.",
        "activity": "{activity_history}.",
        "environment": "{environment_role}.",
        "beverages": "{logging_scope}.",
        "trends": "{trend_scope}.",
        "uncertainty": "{research_scope}.",
        "measurement": "These observations support evidence collection, not a drinking prescription.",
    ]
    static let missingLabels: [String: String] = [
        "exercise": "a supplied workout",
        "complete_environment_and_intensity": "complete environmental and intensity context",
        "confirmed_comparable_conditions": "confirmation of comparable conditions",
        "usable_measurements_with_error_bounds": "usable comparable measurements with error bounds",
        "actual_measurement_for_started_exercise": "a completed measurement for the started workout",
        "intake_completeness": "verified logging completeness",
        "documented_water_composition": "documented water composition",
        "complete_electrolyte_composition": "complete electrolyte composition",
        "environmental_context": "environmental context",
    ]
    static let liveLimitations = [
        "Muse Wonder selected vetted wording; Hydra authored the factual clauses and filled every number.",
        "Logged intake does not measure hydration status, retention or a required intake amount.",
        "Workout loss is a research mass-balance proxy; historical envelopes do not guarantee future interval coverage.",
        "Recorded consistency checks do not attest provider authenticity, billing settlement or spending authorization.",
        "Displayed amounts are rounded to whole mL; range endpoints are rounded outward. Numeric facts remain unchanged.",
    ]
}
