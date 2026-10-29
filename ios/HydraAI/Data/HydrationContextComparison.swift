import Foundation

/// The client rejects context that changes numbers or claims an unobserved live result.
struct HydrationContextComparison: Decodable, Sendable {
    struct NumericalSnapshot: Decodable, Equatable, Sendable {
        let version: String
        let status: String
        let model_version: String
        let quantity: String
        let units: String
        let value_ml: Double?
        let lower_ml: Double?
        let upper_ml: Double?
        let interval_kind: String
        let sample_count: Int
        let synthetic: Bool

        func matches(_ forecast: WorkoutForecast) -> Bool {
            version == forecast.version && status == forecast.status && model_version == forecast.modelVersion
                && quantity == forecast.quantity && units == forecast.units && value_ml == forecast.valueMl
                && lower_ml == forecast.lowerMl && upper_ml == forecast.upperMl && interval_kind == forecast.intervalKind
                && sample_count == forecast.sampleCount && synthetic == forecast.synthetic
        }
    }
    struct Interpretation: Decodable, Equatable, Sendable {
        let factors: [String]
        let missing_information: [String]
        let contradictions: [String]
        let uncertainty: [String]
        let measurement_suggestions: [String]
        let numerical_abstention: Bool
        let reviewed_text: [String: [String]]

        private enum CodingKeys: String, CodingKey, CaseIterable {
            case factors, missing_information, contradictions, uncertainty, measurement_suggestions, numerical_abstention, reviewed_text
        }
        private struct OpenKey: CodingKey {
            let stringValue: String
            let intValue: Int? = nil
            init?(stringValue: String) { self.stringValue = stringValue }
            init?(intValue: Int) { return nil }
        }
        init(from decoder: Decoder) throws {
            let open = try decoder.container(keyedBy: OpenKey.self)
            guard Set(open.allKeys.map(\.stringValue)) == Set(CodingKeys.allCases.map(\.rawValue)) else {
                throw ServiceError.invalidResponse
            }
            let values = try decoder.container(keyedBy: CodingKeys.self)
            factors = try values.decode([String].self, forKey: .factors)
            missing_information = try values.decode([String].self, forKey: .missing_information)
            contradictions = try values.decode([String].self, forKey: .contradictions)
            uncertainty = try values.decode([String].self, forKey: .uncertainty)
            measurement_suggestions = try values.decode([String].self, forKey: .measurement_suggestions)
            numerical_abstention = try values.decode(Bool.self, forKey: .numerical_abstention)
            reviewed_text = try values.decode([String: [String]].self, forKey: .reviewed_text)
        }

        private static let allowed: [String: Set<String>] = [
            "factors": ["workout_duration", "environment_reported", "personal_calibration", "intake_logged", "thirst_reported", "heart_rate_context", "supplement_context"],
            "missing_information": ["calibration_measurements", "measurement_error_bounds", "environmental_context", "intake_completeness", "electrolyte_composition"],
            "contradictions": ["negative_mass_balance", "incompatible_conditions"],
            "uncertainty": ["synthetic_evidence_only", "not_daily_requirement", "insufficient_measurements", "environment_context_not_numeric_effect", "biometrics_not_dehydration", "supplements_no_automatic_adjustment"],
            "measurement_suggestions": ["comparable_dry_weighing", "record_intake_urine", "record_error_bounds", "record_environment", "review_inconsistent_measurement", "compare_conditions"]
        ]
        func validate(abstention: Bool) throws {
            let fields = ["factors": factors, "missing_information": missing_information, "contradictions": contradictions,
                          "uncertainty": uncertainty, "measurement_suggestions": measurement_suggestions]
            guard numerical_abstention == abstention, Set(reviewed_text.keys) == Set(fields.keys),
                  uncertainty.contains("synthetic_evidence_only"), uncertainty.contains("not_daily_requirement") else {
                throw ServiceError.invalidResponse
            }
            for (name, values) in fields {
                guard Set(values).count == values.count, Set(values).isSubset(of: Self.allowed[name]!),
                      let texts = reviewed_text[name], texts.count == values.count,
                      texts.allSatisfy({ !$0.isEmpty && $0.count <= 500 }) else { throw ServiceError.invalidResponse }
            }
        }
    }
    struct System: Decodable, Sendable {
        let prediction: NumericalSnapshot?
        let interpretation: Interpretation?
    }
    struct Provenance: Decodable, Sendable {
        let mode: String
        let provider: String?
        let model: String?
        let candidate_model: String
        let candidate_tier: String
        let model_identity_verified: Bool
        let live_dispatch_enabled: Bool
        let interpretation_origin: String
        let account_id: String?
        let attempt_id: String?
    }
    let version: String
    let scenario: String
    let synthetic: Bool
    let provenance: Provenance
    let provider_observations: [String: Double?]
    let systems: [String: System]
    let limitations: [String]

    func validate(forecast: WorkoutForecast) throws {
        guard version == "hydration-context-comparison-v2", scenario == "complete", synthetic, forecast.synthetic,
              provenance.mode == "mock", provenance.provider == nil, provenance.model == nil,
              provenance.account_id == nil, provenance.attempt_id == nil,
              ["muse-spark-1.3", "muse-wonder-1.0"].contains(provenance.candidate_model),
              provenance.candidate_tier == "Standard", !provenance.model_identity_verified, !provenance.live_dispatch_enabled,
              provenance.interpretation_origin == "local_rules_and_reviewed_text",
              Set(provider_observations.keys) == ["latency_ms", "input_tokens", "output_tokens", "billed_cost_usd"],
              provider_observations.values.allSatisfy({ $0 == nil }), Set(systems.keys) == ["A", "B", "C"],
              let a = systems["A"], let b = systems["B"], let c = systems["C"],
              let prediction = a.prediction, prediction.matches(forecast), prediction == c.prediction,
              a.interpretation == nil, b.prediction == nil, let interpretation = b.interpretation,
              interpretation == c.interpretation, !limitations.isEmpty, limitations.count <= 16 else { throw ServiceError.invalidResponse }
        try interpretation.validate(abstention: forecast.status != "estimated")
    }

    static let recordedObservationKeys: Set<String> = ["latency_ms", "input_tokens", "output_tokens", "usage_derived_cost_micro_usd"]

    /// A recorded, already-settled Muse Wonder result. Replaying it never sends a Meta request.
    func validateRecorded() throws {
        guard version == "hydration-context-comparison-v2", scenario == "complete", synthetic,
              provenance.mode == "meta_live", provenance.provider == "Meta",
              provenance.model == "muse-wonder-1.0", provenance.candidate_model == "muse-wonder-1.0",
              provenance.candidate_tier == "Standard", provenance.model_identity_verified, provenance.live_dispatch_enabled,
              provenance.interpretation_origin == "meta_selection_and_reviewed_text",
              provenance.account_id == "georgiosaliba227", let attempt = provenance.attempt_id, UUID(uuidString: attempt) != nil,
              Set(provider_observations.keys) == Self.recordedObservationKeys.union(["billed_cost_usd"]),
              provider_observations["billed_cost_usd"] == .some(nil),
              Self.recordedObservationKeys.allSatisfy({ ((provider_observations[$0] ?? nil) ?? -1) >= 0 }),
              Set(systems.keys) == ["A", "B", "C"], let a = systems["A"], let b = systems["B"], let c = systems["C"],
              let prediction = a.prediction, prediction.synthetic, prediction == c.prediction,
              a.interpretation == nil, b.prediction == nil, let interpretation = b.interpretation,
              interpretation == c.interpretation, !limitations.isEmpty, limitations.count <= 16 else { throw ServiceError.invalidResponse }
        try interpretation.validate(abstention: prediction.status != "estimated")
    }
}

/// Replays the recorded Muse Wonder result. Connection changes and leaving the screen discard late replies.
@MainActor final class RecordedWonderController: ObservableObject {
    @Published private(set) var result: HydrationContextComparison?
    @Published private(set) var state: LoadState = .idle
    private var generation = UUID()

    func invalidate() {
        generation = UUID(); result = nil; state = .idle
    }

    func load(service: any BeverageService) async {
        invalidate()
        let current = generation
        state = .loading
        do {
            let result = try await service.recordedWonderComparison(scenario: "complete")
            try result.validateRecorded()
            guard current == generation, !Task.isCancelled else { return }
            self.result = result; state = .loaded
        } catch ServiceError.server(let code) where code == 404 {
            guard current == generation, !Task.isCancelled else { return }
            state = .failed("No recorded Muse Wonder result is available yet.")
        } catch {
            guard current == generation, !Task.isCancelled else { return }
            state = .failed("Recorded Muse Wonder result unavailable or failed validation.")
        }
    }
}

struct LongitudinalHistory: Decodable, Sendable {
    let total_samples: Int
    let comparable_samples: Int
    let recent_samples: Int
    let first_observed_at: String?
    let last_observed_at: String?
    let method: String
    let history_retained_by_caller: Bool

    func validate(request: WorkoutForecastRequest, forecast: WorkoutForecast) throws {
        guard !forecast.synthetic, history_retained_by_caller, total_samples == request.samples.count,
              comparable_samples >= 0, comparable_samples <= total_samples, recent_samples == min(5, comparable_samples),
              method == "recent_comparable_median_with_historical_error_envelope" else { throw ServiceError.invalidResponse }
        if forecast.status == "estimated", forecast.modelVersion == "personal-longitudinal-v2", comparable_samples != forecast.sampleCount {
            throw ServiceError.invalidResponse
        }
        if comparable_samples == 0 {
            guard first_observed_at == nil, last_observed_at == nil else { throw ServiceError.invalidResponse }
        } else {
            guard let first_observed_at, let last_observed_at,
                  let first = Self.instant(first_observed_at), let last = Self.instant(last_observed_at),
                  let generated = Self.instant(forecast.generatedAt), first <= last, last < generated else { throw ServiceError.invalidResponse }
        }
    }
    private static func instant(_ text: String) -> Date? {
        guard text.hasSuffix("Z") || text.hasSuffix("+00:00") else { return nil }
        let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: text) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: text)
    }
}
