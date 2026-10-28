import Foundation

/// Explicit manual inputs. No HealthKit fields or arbitrary model prompt are encoded.
struct WorkoutForecastRequest: Encodable, Sendable {
    struct Conditions: Encodable, Sendable {
        let activity: String
        let intensity: String
        let temperature_c: Double
        let humidity_percent: Double
    }
    struct Measurement: Encodable, Sendable {
        let pre_mass_kg: Double
        let post_mass_kg: Double
        let consumed_ml: Double
        let urine_ml: Double
        let duration_minutes: Double
        let protocol_confirmed = true
        let provenance = ["user_entered_manual_weighing"]
    }
    struct Errors: Encodable, Sendable {
        let pre_mass_kg: Double
        let post_mass_kg: Double
        let consumed_ml: Double
        let urine_ml: Double
        let duration_minutes: Double
        let provenance = ["user_reported_instrument_error_bounds"]
    }
    struct Sample: Encodable, Sendable {
        let event_id: UUID
        let observed_at: String
        let conditions: Conditions
        let measurement: Measurement
        let errors: Errors
    }
    struct Exercise: Encodable, Sendable {
        let event_id: UUID
        let starts_at: String
        let duration_minutes: Double
        let conditions: Conditions
        let comparable_conditions_confirmed: Bool
        let duration_source = "manual"
    }
    let mode: String
    let timezone: String
    let exercise: Exercise?
    let samples: [Sample]
    let calibration_processing_consent: Bool

    static func demonstration(timezone: String) -> Self {
        Self(mode: "synthetic_demo", timezone: timezone, exercise: nil, samples: [], calibration_processing_consent: false)
    }

    func validate() throws {
        guard TimeZone(identifier: timezone) != nil, samples.count <= 32 else { throw ServiceError.invalidResponse }
        if mode == "synthetic_demo" {
            guard exercise == nil, samples.isEmpty, !calibration_processing_consent else { throw ServiceError.invalidResponse }
        } else {
            guard mode == "personal", samples.isEmpty || calibration_processing_consent else { throw ServiceError.invalidResponse }
        }
    }
}

struct WorkoutForecast: Decodable, Sendable {
    enum Factor: Decodable, Sendable {
        case number(Double), text(String), flag(Bool), null, object([String: Factor]), array([Factor])
        init(from decoder: Decoder) throws {
            let value = try decoder.singleValueContainer()
            if value.decodeNil() { self = .null }
            else if let flag = try? value.decode(Bool.self) { self = .flag(flag) }
            else if let number = try? value.decode(Double.self) { self = .number(number) }
            else if let text = try? value.decode(String.self) { self = .text(text) }
            else if let object = try? value.decode([String: Factor].self) { self = .object(object) }
            else { self = .array(try value.decode([Factor].self)) }
        }
        var display: String {
            switch self {
            case .number(let number): number.formatted(.number.precision(.fractionLength(0...2)))
            case .text(let text): text.replacingOccurrences(of: "_", with: " ")
            case .flag(let flag): flag ? "yes" : "no"
            case .null: "missing"
            case .object(let object): object.keys.sorted().map { "\($0): \(object[$0]!.display)" }.joined(separator: ", ")
            case .array(let values): values.map(\.display).joined(separator: ", ")
            }
        }
        var valid: Bool {
            switch self {
            case .number(let number): number.isFinite
            case .text(let text): text.count <= 500
            case .object(let values): values.count <= 32 && values.values.allSatisfy(\.valid)
            case .array(let values): values.count <= 32 && values.allSatisfy(\.valid)
            default: true
            }
        }
    }
    struct MockExplanation: Decodable, Sendable {
        let version: String
        let mode: String
        let provider: String?
        let model: String?
        let account_id: String?
        let attempt_id: String?
        let explanations: [String]
        let prediction: Double?
    }
    let version: String
    let status: String
    let modelVersion: String
    let quantity: String
    let units: String
    let valueMl: Double?
    let lowerMl: Double?
    let upperMl: Double?
    let intervalKind: String
    let dataSufficiency: String
    let personalizationStatus: String
    let sampleCount: Int
    let provenance: [String]
    let inputFactors: [String: Factor]
    let limitations: [String]
    let synthetic: Bool
    let generatedAt: String
    let timezone: String
    let mode: String
    let mockExplanation: MockExplanation?
    let explanationPolicy: String

    enum CodingKeys: String, CodingKey {
        case version, status, quantity, units, provenance, limitations, synthetic, timezone, mode
        case modelVersion = "model_version", valueMl = "value_ml", lowerMl = "lower_ml", upperMl = "upper_ml"
        case intervalKind = "interval_kind", dataSufficiency = "data_sufficiency", personalizationStatus = "personalization_status"
        case sampleCount = "sample_count", inputFactors = "input_factors", generatedAt = "generated_at"
        case mockExplanation = "mock_explanation", explanationPolicy = "explanation_policy"
    }

    func validate(request: WorkoutForecastRequest) throws {
        try request.validate()
        guard version == "workout-forecast-v1", quantity == "estimated_sweat_loss", units == "mL",
              timezone == request.timezone, mode == request.mode, synthetic == (mode == "synthetic_demo"),
              !modelVersion.isEmpty, modelVersion.count <= 200,
              !dataSufficiency.isEmpty, !personalizationStatus.isEmpty,
              (0...32).contains(sampleCount), !limitations.isEmpty, limitations.count <= 64,
              provenance.count <= 64, inputFactors.count <= 32, inputFactors.values.allSatisfy(\.valid),
              explanationPolicy == "Meta_may_explain_reviewed_results_only_no_numeric_recalculation",
              generatedAt.hasSuffix("Z") || generatedAt.hasSuffix("+00:00") else { throw ServiceError.invalidResponse }
        let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if formatter.date(from: generatedAt) == nil {
            formatter.formatOptions = [.withInternetDateTime]
            guard formatter.date(from: generatedAt) != nil else { throw ServiceError.invalidResponse }
        }
        if status == "estimated" {
            guard let valueMl, let lowerMl, let upperMl, valueMl.isFinite, lowerMl.isFinite, upperMl.isFinite,
                  0 <= lowerMl, lowerMl <= valueMl, valueMl <= upperMl, !provenance.isEmpty,
                  !intervalKind.isEmpty, intervalKind != "none" else { throw ServiceError.invalidResponse }
            if synthetic {
                guard sampleCount == 0, intervalKind.hasPrefix("synthetic_") else { throw ServiceError.invalidResponse }
            } else {
                guard modelVersion == "personal-exercise-loss-v1", sampleCount > 0, sampleCount <= request.samples.count,
                      intervalKind == "conditional_measurement_envelope" else { throw ServiceError.invalidResponse }
            }
        } else {
            guard status == "insufficient_data", valueMl == nil, lowerMl == nil, upperMl == nil else { throw ServiceError.invalidResponse }
        }
        if let explanation = mockExplanation {
            guard synthetic, explanation.version == "hydration-explanation-v1", explanation.mode == "mock",
                  explanation.provider == nil, explanation.model == nil, explanation.account_id == nil,
                  explanation.attempt_id == nil, explanation.prediction == nil,
                  explanation.explanations.count <= 6 else { throw ServiceError.invalidResponse }
        }
    }
}

/// Transient results only. Edits and connection changes invalidate late replies.
@MainActor final class WorkoutForecastController: ObservableObject {
    @Published private(set) var result: WorkoutForecast?
    @Published private(set) var state: LoadState = .idle
    private var generation = UUID()

    func invalidate() {
        generation = UUID(); result = nil; state = .idle
    }

    func load(_ request: WorkoutForecastRequest, service: any BeverageService) async {
        guard !Task.isCancelled else { return }
        invalidate()
        let current = generation
        state = .loading
        do {
            try request.validate()
            let result = try await service.workoutForecast(request)
            try result.validate(request: request)
            guard current == generation, !Task.isCancelled else { return }
            self.result = result; state = .loaded
        } catch {
            guard current == generation, !Task.isCancelled else { return }
            state = .failed("Workout estimate unavailable. Beverage logging still works.")
        }
    }
}
