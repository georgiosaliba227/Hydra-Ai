import Foundation

func validAnalysisHash(_ value: String) -> Bool {
    value.count == 64 && value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
}

extension WonderAnalysisFacts {
    func matches(_ field: WonderAnalysisValue?, _ value: Double?) -> Bool { field == value.map(WonderAnalysisValue.number) ?? .null }
    func matches(_ field: WonderAnalysisValue?, _ value: String?) -> Bool { field == value.map(WonderAnalysisValue.text) ?? .null }
    func validateShape() throws {
        func require(_ flag: Bool) throws { if !flag { throw ServiceError.invalidResponse } }
        func bounded(_ value: WonderAnalysisValue, depth: Int = 0) -> Bool {
            guard depth <= 5 else { return false }
            switch value {
            case .null, .flag: return true
            case .number(let number): return number.isFinite
            case .text(let text): return text.count <= 256
            case .array(let values): return values.count <= 32 && values.allSatisfy { bounded($0, depth: depth + 1) }
            case .object(let values): return values.count <= 32 && values.keys.allSatisfy { $0.count <= 128 } && values.values.allSatisfy { bounded($0, depth: depth + 1) }
            }
        }
        let schema: [String: Set<String>] = [
            "forecast": ["status", "value_ml", "lower_ml", "upper_ml", "interval_kind"],
            "intake": ["beverage_count", "beverage_volume_ml", "water_ml", "sodium_mg", "potassium_mg", "sodium_status", "potassium_status", "completeness"],
            "activity": ["activity", "duration_minutes", "intensity"],
            "environment": ["temperature_c", "humidity_percent", "context_only"],
            "calibration": ["total_samples", "comparable_samples", "recent_samples"],
            "trends": ["window_days", "logged_days", "beverage_lower_ml", "beverage_upper_ml"],
            "accounting": ["status", "quantity", "value_ml", "lower_ml", "upper_ml"],
            "workout_comparison": ["planned_duration_minutes", "typical_duration_minutes", "planned_temperature_c", "typical_temperature_c", "planned_humidity_percent", "typical_humidity_percent"],
            "trend_context": ["last_7_days", "previous_7_days", "change_pct", "time_of_day_ml"]]
        try require(Set(values.keys) == Set(schema.keys).union(["version", "mode", "research_only", "missing_inputs"]))
        try require(bounded(.object(values)) && values["version"] == .text("wonder-analysis-facts-v2") && values["research_only"] == .flag(true))
        try require(["personal", "synthetic_demo"].contains(values["mode"]?.text ?? ""))
        for (key, keys) in schema {
            if ["workout_comparison", "trend_context"].contains(key), values[key] == .null { continue }
            try require(values[key]?.object.map { Set($0.keys) == keys } ?? false)
        }
        func number(_ group: String, _ key: String, range: ClosedRange<Double> = 0...Double.greatestFiniteMagnitude,
                    optional: Bool = false, integer: Bool = false) throws -> Double? {
            let value = values[group]?.object?[key]
            if optional && value == .null { return nil }
            guard let n = value?.number, n.isFinite, range.contains(n), !integer || n.rounded() == n else { throw ServiceError.invalidResponse }
            return n
        }
        let forecast = values["forecast"]!.object!, intake = values["intake"]!.object!
        try require(["estimated", "insufficient_data"].contains(forecast["status"]?.text ?? ""))
        try require(["historical_error_envelope", "conditional_measurement_envelope", "synthetic_participant_split_conformal", "synthetic_empirical_calibration_envelope"].contains(forecast["interval_kind"]?.text ?? ""))
        if forecast["status"] == .text("estimated") {
            let point = try number("forecast", "value_ml")!, lower = try number("forecast", "lower_ml")!, upper = try number("forecast", "upper_ml")!
            try require(lower <= point && point <= upper)
        } else { try require(["value_ml", "lower_ml", "upper_ml"].allSatisfy { forecast[$0] == .null }) }
        for key in ["beverage_volume_ml", "water_ml", "sodium_mg", "potassium_mg"] { _ = try number("intake", key, optional: true) }
        _ = try number("intake", "beverage_count", optional: true, integer: true)
        try require(intake["completeness"] == .text("unverified"))
        for nutrient in ["sodium", "potassium"] {
            let status = intake[nutrient + "_status"]?.text ?? ""
            try require(["complete", "partial", "unknown"].contains(status))
            try require((status == "complete") == (intake[nutrient + "_mg"] != .null))
        }
        _ = try number("environment", "temperature_c", range: -60...60, optional: true)
        _ = try number("environment", "humidity_percent", range: 0...100, optional: true)
        try require(values["environment"]?.object?["context_only"] == .flag(true))
        let activity = values["activity"]!.object!
        try require(activity["activity"] == .null || WorkoutDraft.activities.contains(activity["activity"]?.text ?? ""))
        try require(activity["intensity"] == .null || WorkoutDraft.intensities.contains(activity["intensity"]?.text ?? ""))
        _ = try number("activity", "duration_minutes", range: 0.000001...1440, optional: true)
        let total = try number("calibration", "total_samples", range: 0...32, integer: true)!
        let comparable = try number("calibration", "comparable_samples", range: 0...total, integer: true)!
        _ = try number("calibration", "recent_samples", range: 0...comparable, integer: true)
        try require(values["trends"]?.object?["window_days"] == .number(14))
        _ = try number("trends", "logged_days", range: 0...14, optional: true, integer: true)
        let lower = try number("trends", "beverage_lower_ml", optional: true), upper = try number("trends", "beverage_upper_ml", optional: true)
        try require((lower == nil) == (upper == nil))
        let loggedDays = values["trends"]?.object?["logged_days"]?.number ?? 0
        try require((loggedDays > 0) == (lower != nil && upper != nil))
        if let lower, let upper { try require(lower <= upper) }
        let accounting = values["accounting"]!.object!
        // There is no actual-completed-measurement field in this iPhone's planned-workout contract.
        try require(accounting["status"] == .text("unavailable") && accounting["quantity"] == .text("logged_intake_minus_measured_exercise_loss"))
        try require(["value_ml", "lower_ml", "upper_ml"].allSatisfy { accounting[$0] == .null })
        if values["workout_comparison"] != .null {
            for key in schema["workout_comparison"]! {
                let range: ClosedRange<Double> = key.hasSuffix("temperature_c") ? -60...60 : key.hasSuffix("humidity_percent") ? 0...100 : 1...1440
                _ = try number("workout_comparison", key, range: range, optional: key != "planned_duration_minutes", integer: true)
            }
        }
        if let context = values["trend_context"]?.object {
            for key in ["last_7_days", "previous_7_days"] {
                guard let week = context[key]?.object, Set(week.keys) == ["total_ml", "logged_days"],
                      let amount = week["total_ml"]?.number, amount >= 0,
                      let days = week["logged_days"]?.number, (0...7).contains(days), days.rounded() == days else { throw ServiceError.invalidResponse }
            }
            guard let timing = context["time_of_day_ml"]?.object,
                  Set(timing.keys) == ["morning_ml", "afternoon_ml", "evening_ml", "night_ml"],
                  timing.values.allSatisfy({ $0.number.map { $0 >= 0 } ?? false }) else { throw ServiceError.invalidResponse }
            _ = try number("trend_context", "change_pct", range: -100...1000000000000, optional: true, integer: true)
        }
        guard case .array(let missing) = values["missing_inputs"], missing.count <= 16 else { throw ServiceError.invalidResponse }
        let codes: Set<String> = ["exercise", "complete_environment_and_intensity", "confirmed_comparable_conditions", "usable_measurements_with_error_bounds", "actual_measurement_for_started_exercise", "intake_completeness", "documented_water_composition", "complete_electrolyte_composition", "environmental_context"]
        try require(missing.allSatisfy { $0.text.map(codes.contains) ?? false })
        if values["mode"] == .text("synthetic_demo") {
            try require(["beverage_count", "beverage_volume_ml", "water_ml", "sodium_mg", "potassium_mg"].allSatisfy { intake[$0] == .null })
            try require(total == 0 && values["trends"]?.object?["logged_days"] == .null && values["trend_context"] == .null)
        } else { try require(intake["beverage_count"]?.number != nil && intake["beverage_volume_ml"]?.number != nil) }
    }
}

extension WonderAnalysisResult {
    static let insightContracts: [String: [String: (String, String)]] = [
        "summary": [
            "summary_record": ("Available record", "{record_summary}."),
            "summary_estimate": ("Research estimate", "{loss_estimate}."),
            "summary_missing": ("Missing evidence", "{missing_context}."),
        ],
        "workout_loss": [
            "loss_estimate": ("Estimated loss", "{loss_estimate}."),
            "loss_no_estimate": ("Numerical abstention", "{loss_estimate}."),
            "loss_history": ("Comparable observations", "{calibration_context}."),
            "loss_limited_history": ("Limited personal history", "{calibration_context}; the comparable history is limited."),
            "loss_actual": ("Completed measurement", "{loss_estimate}; this proxy uses the supplied completed measurement."),
        ],
        "activity": [
            "activity_context": ("Supplied workout", "{activity_context}."),
            "activity_missing": ("Missing activity", "{activity_context}."),
            "activity_duration_comparison": ("Duration comparison", "{duration_comparison}."),
            "activity_history": ("Personal activity history", "{calibration_context}."),
        ],
        "environment": [
            "environment_reported": ("Reported conditions", "{environment_context}."),
            "environment_missing": ("Missing conditions", "{environment_context}."),
            "environment_shift": ("Different historical conditions", "{environment_comparison}."),
            "environment_context": ("Environmental scope", "{environment_role}."),
        ],
        "beverages": [
            "beverage_volume": ("Logged volume", "{beverage_context}."),
            "beverage_no_logs": ("No current logs", "{beverage_context}; absence of a log does not establish no consumption."),
            "beverage_synthetic": ("Synthetic exclusion", "{beverage_context}."),
            "beverage_water_known": ("Documented water", "{water_context}."),
            "beverage_water_unknown": ("Unknown water composition", "{water_context}."),
            "beverage_electrolytes_known": ("Documented electrolytes", "{electrolyte_context}."),
            "beverage_electrolytes_incomplete": ("Incomplete electrolytes", "{electrolyte_context}."),
        ],
        "trends": [
            "trends_logged_days": ("Descriptive intake history", "{history_context}."),
            "trends_no_logs": ("No prior logged days", "{history_context}."),
            "trends_synthetic": ("Synthetic exclusion", "{history_context}."),
            "trends_week_change": ("Logged weekly comparison", "{weekly_comparison}."),
            "trends_week_missing": ("Unverified logging coverage", "{weekly_logging}."),
            "trends_timing": ("Logged timing pattern", "{timing_pattern}."),
            "trends_calibration": ("Comparable workout history", "{calibration_context}."),
        ],
        "uncertainty": [
            "uncertainty_missing": ("Missing inputs", "{missing_context}."),
            "uncertainty_history": ("Historical envelope", "{uncertainty_context}."),
            "uncertainty_actual": ("Measurement uncertainty", "{uncertainty_context}."),
            "uncertainty_synthetic": ("Synthetic evidence", "this simulated scenario does not establish physiological validity."),
            "uncertainty_accounting": ("Conditional exercise arithmetic", "{accounting_context}."),
            "uncertainty_no_accounting": ("Accounting abstention", "{accounting_context}."),
        ],
        "measurement": [
            "measurement_comparable": ("Comparable measurements", "{measurement_context}."),
            "measurement_composition": ("Composition documentation", "{water_context}; {electrolyte_context}."),
            "measurement_environment": ("Environmental documentation", "{environment_context}; documenting workout conditions supports comparison."),
            "measurement_repeat": ("Additional comparable session", "{calibration_context}; a further comparable completed measurement can document variability."),
            "measurement_timing": ("Measurement window", "{accounting_context}; check the observed window and recorded consumption before comparing."),
        ],
    ]
    static let sectionTitles = ["summary": "Hydration-related summary", "workout_loss": "Workout fluid-loss estimate",
        "activity": "Activity context", "environment": "Environmental context", "beverages": "Beverage and electrolyte context",
        "trends": "Personal trends", "uncertainty": "Prediction uncertainty", "measurement": "Measurement insights"]
    func validateResult() throws {
        try facts.validateShape()
        guard version == "wonder-analysis-v2", validAnalysisHash(payload_sha256),
              (generated_at.hasSuffix("Z") || generated_at.hasSuffix("+00:00")), CalibrationHistoryValidation.date(generated_at) != nil,
              provenance.mode == "meta_live", provenance.provider == "Meta", provenance.model == "muse-wonder-1.0",
              MetaAccount.known.contains(provenance.account_id), UUID(uuidString: provenance.attempt_id) != nil,
              provenance.selection_origin == "muse_wonder_selected_scaffolds",
              provenance.text_origin == "hydra_vetted_scaffolds_and_facts", provenance.numbers_checked_against == "facts",
              Set(provider_observations.keys) == ["latency_ms", "input_tokens", "output_tokens", "usage_derived_cost_micro_usd", "billed_cost_usd"],
              provider_observations["billed_cost_usd"] == .some(nil),
              provider_observations.filter({ $0.key != "billed_cost_usd" }).values.allSatisfy({ $0.map { $0.isFinite && $0 >= 0 } ?? false }),
              limitations == WonderAnalysisRenderer.liveLimitations,
              facts.values["mode"] == .text("personal"),
              sections.count == 8, Set(sections.map(\.id)) == Set(Self.sectionTitles.keys) else { throw ServiceError.invalidResponse }
        let synthetic = facts.values["mode"] == .text("synthetic_demo")
        let estimated = facts.values["forecast"]?.object?["status"] == .text("estimated")
        let placeholders = try WonderAnalysisRenderer.placeholders(facts)
        let applicable = WonderAnalysisRenderer.applicability(facts)
        for section in sections {
            let evidence = synthetic ? "synthetic" : ["summary", "workout_loss"].contains(section.id) ? (estimated ? "estimated" : "insufficient_data") : "context_only"
            guard Self.sectionTitles[section.id] == section.title, section.evidence_status == evidence,
                  (1...8000).contains(section.text.count), (1...2000).contains(section.template.count),
                  (1...3).contains(section.insights.count), Set(section.insights.map(\.id)).count == section.insights.count,
                  section.insights.allSatisfy({ insight in
                      guard let expected = Self.insightContracts[section.id]?[insight.id] else { return false }
                      return applicable.contains(insight.id) && insight.title == expected.0 && insight.template == expected.1
                        && insight.text == WonderAnalysisRenderer.render(expected.1, values: placeholders)
                  }) else { throw ServiceError.invalidResponse }
            let template = (section.insights.map(\.template) + [WonderAnalysisRenderer.requiredCaveats[section.id]!]).joined(separator: " ")
            guard section.template == template,
                  section.text == WonderAnalysisRenderer.render(template, values: placeholders) else { throw ServiceError.invalidResponse }
            // Current requests cannot support an actual loss/accounting finding.
            guard !section.insights.contains(where: { ["loss_actual", "uncertainty_actual", "uncertainty_accounting"].contains($0.id) }) else { throw ServiceError.invalidResponse }
        }
    }
}
