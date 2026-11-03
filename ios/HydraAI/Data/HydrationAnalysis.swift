import Foundation

/// Nonbillable, deterministic analysis. Muse Wonder stays in its separate preview/consent workflow.
struct HydrationAnalysis: Decodable, Sendable {
    struct Numerical: Decodable, Sendable {
        let version: String, status: String, model_version: String, quantity: String, units: String
        let value_ml: Double?, lower_ml: Double?, upper_ml: Double?
        let interval_kind: String, personalization_status: String
        let sample_count: Int
        let synthetic: Bool
        let learning: PersonalRuntimeLearning?
        let research_only: Bool?
        func matches(_ forecast: WorkoutForecast) -> Bool {
            version == forecast.version && status == forecast.status && model_version == forecast.modelVersion
                && quantity == forecast.quantity && units == forecast.units && value_ml == forecast.valueMl
                && lower_ml == forecast.lowerMl && upper_ml == forecast.upperMl && interval_kind == forecast.intervalKind
                && sample_count == forecast.sampleCount && synthetic == forecast.synthetic
                && personalization_status == forecast.personalizationStatus && learning == forecast.learning && research_only == forecast.researchOnly
        }
    }
    struct Intake: Decodable, Sendable {
        struct Composition: Decodable, Sendable {
            let sodium_mg: Double?, potassium_mg: Double?
            let status: String, sodium_status: String, potassium_status: String
            let provenance: [String]
        }
        let status: String, local_date: String, start_utc: String, end_utc: String, timezone: String
        let beverage_count: Int?, beverage_volume_ml: Double?, water_ml: Double?
        let composition: Composition
        let completeness: String
        let provenance: [String]
    }
    struct Accounting: Decodable, Sendable {
        let status: String, quantity: String, timezone: String
        let start_utc: String?, end_utc: String?
        let value_ml: Double?, lower_ml: Double?, upper_ml: Double?, logged_beverage_volume_ml: Double?
        let reasons: [String], provenance: [String]
    }
    struct Environment: Decodable, Sendable {
        let temperature_c: Double?, humidity_percent: Double?, intensity: String?
        let source: String
        let context_only: Bool
    }
    struct Calibration: Decodable, Sendable {
        let total_samples: Int, comparable_samples: Int, recent_samples: Int
        let personalization_status: String
        let history_retained_by_caller: Bool
    }
    struct Section: Decodable, Identifiable, Sendable {
        let id: String, title: String, evidence_status: String, text: String
        let facts: [String: WorkoutForecast.Factor]
    }
    struct Wonder: Decodable, Sendable {
        struct Preview: Decodable, Sendable {
            let version: String
            let facts: WorkoutFacts
            let explainable: Bool
            let payload_sha256: String?
            let input_bound_tokens: Int?, worst_case_micro_usd: Int?
        }
        let status: String
        let preview: Preview?
        let saved: WonderWorkout?
        let reason: String?
        let provider_called: Bool
    }
    let version: String, generated_at: String, timezone: String, mode: String, text_origin: String
    let research_only: Bool
    let numerical_forecast: Numerical
    let intake: Intake
    let exercise_accounting: Accounting
    let environmental_context: Environment
    let calibration: Calibration
    let missing_inputs: [String]
    let sections: [Section]
    let wonder: Wonder
    let limitations: [String]

    private enum CodingKeys: String, CodingKey {
        case version, generated_at, timezone, mode, text_origin, research_only, numerical_forecast
        case intake, exercise_accounting, environmental_context, calibration, missing_inputs, sections, wonder, limitations
        case learning
    }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        // Learning belongs only to numerical_forecast, never a second unbound analysis root.
        guard !c.contains(.learning) else { throw ServiceError.invalidResponse }
        version = try c.decode(String.self, forKey: .version); generated_at = try c.decode(String.self, forKey: .generated_at)
        timezone = try c.decode(String.self, forKey: .timezone); mode = try c.decode(String.self, forKey: .mode)
        text_origin = try c.decode(String.self, forKey: .text_origin); research_only = try c.decode(Bool.self, forKey: .research_only)
        numerical_forecast = try c.decode(Numerical.self, forKey: .numerical_forecast)
        intake = try c.decode(Intake.self, forKey: .intake); exercise_accounting = try c.decode(Accounting.self, forKey: .exercise_accounting)
        environmental_context = try c.decode(Environment.self, forKey: .environmental_context)
        calibration = try c.decode(Calibration.self, forKey: .calibration)
        missing_inputs = try c.decode([String].self, forKey: .missing_inputs); sections = try c.decode([Section].self, forKey: .sections)
        wonder = try c.decode(Wonder.self, forKey: .wonder); limitations = try c.decode([String].self, forKey: .limitations)
    }

    func validate(request: WorkoutForecastRequest, forecast: WorkoutForecast, workflow: ForecastWorkflow = .legacy) throws {
        try request.validate()
        try forecast.validate(request: request, workflow: workflow)
        let synthetic = mode == "synthetic_demo"
        func nonnegative(_ value: Double?) -> Bool { value.map { $0.isFinite && $0 >= 0 } ?? true }
        func bounded(_ values: [String], count: Int = 64, length: Int = 1000) -> Bool {
            values.count <= count && values.allSatisfy { !$0.isEmpty && $0.count <= length }
        }
        guard version == (workflow.isRuntime ? "hydration-analysis-v3" : "hydration-analysis-v1"), timezone == request.timezone, mode == request.mode,
              research_only, text_origin == "deterministic_local",
              (generated_at.hasSuffix("Z") || generated_at.hasSuffix("+00:00")),
              CalibrationHistoryValidation.date(generated_at) != nil, numerical_forecast.matches(forecast),
              intake.timezone == timezone, intake.completeness == "unverified",
              let start = CalibrationHistoryValidation.date(intake.start_utc),
              let end = CalibrationHistoryValidation.date(intake.end_utc), DateOrdering.notAfter(start, end),
              intake.local_date.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) != nil,
              nonnegative(intake.beverage_volume_ml), nonnegative(intake.water_ml),
              nonnegative(intake.composition.sodium_mg), nonnegative(intake.composition.potassium_mg),
              ["complete", "partial", "unknown"].contains(intake.composition.status),
              ["complete", "partial", "unknown"].contains(intake.composition.sodium_status),
              ["complete", "partial", "unknown"].contains(intake.composition.potassium_status),
              bounded(intake.provenance), bounded(intake.composition.provenance),
              calibration.history_retained_by_caller, calibration.total_samples == request.samples.count,
              (0...32).contains(calibration.total_samples),
              (0...calibration.total_samples).contains(calibration.comparable_samples),
              (0...calibration.comparable_samples).contains(calibration.recent_samples),
              calibration.personalization_status == numerical_forecast.personalization_status,
              bounded(missing_inputs, count: 32, length: 128), bounded(limitations), !limitations.isEmpty,
              !wonder.provider_called, ["preview_only", "not_applicable", "unavailable"].contains(wonder.status)
        else { throw ServiceError.invalidResponse }
        if synthetic {
            guard intake.status == "unavailable_in_synthetic", intake.beverage_count == nil,
                  intake.beverage_volume_ml == nil, intake.water_ml == nil,
                  intake.composition.sodium_mg == nil, intake.composition.potassium_mg == nil else { throw ServiceError.invalidResponse }
        } else {
            guard intake.status == "logged", let count = intake.beverage_count, count >= 0,
                  intake.beverage_volume_ml != nil else { throw ServiceError.invalidResponse }
        }
        if intake.composition.sodium_status != "complete", intake.composition.sodium_mg != nil { throw ServiceError.invalidResponse }
        if intake.composition.potassium_status != "complete", intake.composition.potassium_mg != nil { throw ServiceError.invalidResponse }
        let accounting = exercise_accounting
        guard accounting.timezone == timezone, accounting.quantity == "logged_intake_minus_measured_exercise_loss",
              bounded(accounting.reasons), bounded(accounting.provenance), nonnegative(accounting.logged_beverage_volume_ml) else { throw ServiceError.invalidResponse }
        // The current iPhone contract can send planned exercise only, never an actual completed measurement.
        guard accounting.status == "unavailable", accounting.value_ml == nil, accounting.lower_ml == nil,
              accounting.upper_ml == nil, accounting.start_utc == nil, accounting.end_utc == nil,
              accounting.logged_beverage_volume_ml == nil, !accounting.reasons.isEmpty else { throw ServiceError.invalidResponse }
        let environment = environmental_context
        guard environment.context_only,
              environment.temperature_c.map({ $0.isFinite && (-60...60).contains($0) }) ?? true,
              environment.humidity_percent.map({ $0.isFinite && (0...100).contains($0) }) ?? true,
              environment.intensity.map(["low", "moderate", "high"].contains) ?? true,
              ["server_synthetic", "user_reported", "unavailable"].contains(environment.source) else { throw ServiceError.invalidResponse }
        let ids: Set<String> = ["summary", "workout_loss", "activity", "environment", "beverages", "trends", "uncertainty", "measurement"]
        guard sections.count == 8, Set(sections.map(\.id)) == ids,
              sections.allSatisfy({ section in
                  (1...120).contains(section.title.count) && (1...2000).contains(section.text.count)
                    && ["measured", "estimated", "context_only", "insufficient_data", "synthetic"].contains(section.evidence_status)
                    && (synthetic ? section.evidence_status == "synthetic" : section.evidence_status != "synthetic")
                    && section.facts.count <= 32 && section.facts.values.allSatisfy(\.valid)
              }) else { throw ServiceError.invalidResponse }
        // A detail card must repeat the authoritative values exactly, rather than introducing another estimate.
        let lossFacts = sections.first { $0.id == "workout_loss" }!.facts
        func numberMatches(_ field: WorkoutForecast.Factor?, _ value: Double?) -> Bool {
            if let value, case .number(let number) = field { return value == number }
            if value == nil, case .null = field { return true }
            return false
        }
        func textMatches(_ field: WorkoutForecast.Factor?, _ value: String) -> Bool {
            if case .text(let text) = field { return text == value }
            return false
        }
        guard numberMatches(lossFacts["value_ml"], numerical_forecast.value_ml),
              numberMatches(lossFacts["lower_ml"], numerical_forecast.lower_ml),
              numberMatches(lossFacts["upper_ml"], numerical_forecast.upper_ml),
              numberMatches(lossFacts["sample_count"], Double(numerical_forecast.sample_count)),
              textMatches(lossFacts["status"], numerical_forecast.status),
              textMatches(lossFacts["model_version"], numerical_forecast.model_version),
              textMatches(lossFacts["units"], numerical_forecast.units),
              textMatches(lossFacts["interval_kind"], numerical_forecast.interval_kind),
              numberMatches(sections.first { $0.id == "summary" }?.facts["logged_beverage_volume_ml"], intake.beverage_volume_ml),
              numberMatches(sections.first { $0.id == "beverages" }?.facts["beverage_volume_ml"], intake.beverage_volume_ml),
              numberMatches(sections.first { $0.id == "beverages" }?.facts["water_ml"], intake.water_ml),
              numberMatches(sections.first { $0.id == "environment" }?.facts["temperature_c"], environment.temperature_c),
              numberMatches(sections.first { $0.id == "environment" }?.facts["humidity_percent"], environment.humidity_percent)
        else { throw ServiceError.invalidResponse }
        let forecastEvidence = synthetic ? "synthetic" : numerical_forecast.status == "estimated" ? "estimated" : "insufficient_data"
        guard sections.filter({ ["summary", "workout_loss"].contains($0.id) }).allSatisfy({ $0.evidence_status == forecastEvidence })
        else { throw ServiceError.invalidResponse }
        if !synthetic {
            let exercise = request.exercise
            let activity = sections.first { $0.id == "activity" }!.facts
            func optionalTextMatches(_ field: WorkoutForecast.Factor?, _ value: String?) -> Bool {
                if let value { return textMatches(field, value) }
                if case .null = field { return true }
                return false
            }
            guard environment.temperature_c == exercise?.conditions.temperature_c,
                  environment.humidity_percent == exercise?.conditions.humidity_percent,
                  environment.intensity == exercise?.conditions.intensity,
                  environment.source == (exercise == nil ? "unavailable" : "user_reported"),
                  optionalTextMatches(activity["activity"], exercise?.conditions.activity),
                  optionalTextMatches(activity["intensity"], exercise?.conditions.intensity),
                  numberMatches(activity["duration_minutes"], exercise?.duration_minutes)
            else { throw ServiceError.invalidResponse }
        }
        if workflow.isRuntime {
            guard wonder.preview == nil, wonder.saved == nil, wonder.status == "not_applicable" else { throw ServiceError.invalidResponse }
        }
        if let preview = wonder.preview {
            guard wonder.status == "preview_only", !synthetic, request.exercise != nil,
                  preview.version == "wonder-workout-v1", preview.facts.isValid,
                  preview.facts.timezone == timezone, preview.facts.planned.activity == request.exercise?.conditions.activity,
                  preview.explainable == (preview.payload_sha256 != nil),
                  preview.payload_sha256.map({ $0.count == 64 }) ?? true,
                  preview.input_bound_tokens.map({ $0 >= 0 }) ?? true,
                  preview.worst_case_micro_usd.map({ $0 >= 0 && $0 <= 250000 }) ?? true else { throw ServiceError.invalidResponse }
        } else if wonder.status == "preview_only" { throw ServiceError.invalidResponse }
        if let saved = wonder.saved {
            try saved.validate()
            guard let preview = wonder.preview, saved.facts == preview.facts,
                  saved.payload_sha256 == preview.payload_sha256 else { throw ServiceError.invalidResponse }
        }
    }
}

@MainActor final class HydrationAnalysisController: ObservableObject {
    @Published private(set) var result: HydrationAnalysis?
    @Published private(set) var state: LoadState = .idle
    private var generation = UUID()
    func invalidate() { generation = UUID(); result = nil; state = .idle }
    func load(_ request: WorkoutForecastRequest, forecast: WorkoutForecast, service: any BeverageService, workflow: ForecastWorkflow = .legacy) async {
        guard !Task.isCancelled else { return }
        invalidate(); let current = generation; state = .loading
        do {
            let result = try await (workflow.isRuntime ? service.hydrationAnalysisV3(request) : service.hydrationAnalysis(request))
            try result.validate(request: request, forecast: forecast, workflow: workflow)
            guard generation == current, !Task.isCancelled else { return }
            self.result = result; state = .loaded
        } catch {
            guard generation == current, !Task.isCancelled else { return }
            state = .failed("Detailed analysis unavailable. Your workout estimate remains above; edit or estimate again to refresh it.")
        }
    }
}
