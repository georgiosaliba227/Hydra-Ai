import Foundation

/// Route selection is explicit. A server/network failure never changes the selected workflow.
enum ForecastWorkflow: Equatable, Sendable {
    case legacy, experimentalRuntime
    var isRuntime: Bool { self == .experimentalRuntime }
}

/// Versioned research metadata. It is never encoded in a provider request or saved as local calibration.
struct PersonalRuntimeLearning: Decodable, Equatable, Sendable {
    enum Method: String, Decodable, Sendable { case baseline = "existing_personal_baseline", fitted = "regularized_duration_rate" }
    enum Reason: String, Decodable, Sendable {
        case actual = "actual_measurement_preserved", unavailable = "baseline_unavailable"
        case insufficient = "insufficient_comparable_history", overlap = "overlapping_measurement_windows"
        case duration = "outside_observed_duration_domain", cadence = "beyond_observed_session_spacing"
        case folds = "insufficient_chronological_validation", retained = "baseline_retained_after_validation"
        case selected = "selected_by_earlier_error_comparison", nonfinite = "nonfinite_candidate"
    }
    struct Support: Decodable, Equatable, Sendable {
        let minimum: Double?, maximum: Double?
        enum CodingKeys: String, CodingKey, CaseIterable { case minimum, maximum }
        init(from decoder: Decoder) throws {
            try Self.requireKeys(decoder, keys: CodingKeys.allCases.map(\.rawValue))
            let c = try decoder.container(keyedBy: CodingKeys.self)
            minimum = try c.decodeIfPresent(Double.self, forKey: .minimum)
            maximum = try c.decodeIfPresent(Double.self, forKey: .maximum)
        }
        private static func requireKeys(_ decoder: Decoder, keys: [String]) throws { try PersonalRuntimeLearning.requireKeys(decoder, keys: keys) }
    }
    let version: String
    let selectedMethod: Method
    let reason: Reason
    let trainingSamples: Int, validationFolds: Int
    let fittedRateMlPerHour: Double?
    let ridgeAlpha: Double
    let supportedDurationMinutes: Support
    let baselineMaeMl: Double?, candidateMaeMl: Double?, pairedGainMl: Double?, gainStandardErrorMl: Double?
    let trainingSha256: String?
    let cadenceMaxGapSeconds: Double?
    let storage: String, validationOrigin: String
    let nominalCoverage: Double?
    enum CodingKeys: String, CodingKey, CaseIterable {
        case version, reason, storage
        case selectedMethod = "selected_method", trainingSamples = "training_samples", validationFolds = "validation_folds"
        case fittedRateMlPerHour = "fitted_rate_ml_per_hour", ridgeAlpha = "ridge_alpha", supportedDurationMinutes = "supported_duration_minutes"
        case baselineMaeMl = "baseline_mae_ml", candidateMaeMl = "candidate_mae_ml", pairedGainMl = "paired_gain_ml"
        case gainStandardErrorMl = "gain_standard_error_ml", trainingSha256 = "training_sha256", cadenceMaxGapSeconds = "cadence_max_gap_seconds"
        case validationOrigin = "validation_origin", nominalCoverage = "nominal_coverage"
    }
    private struct OpenKey: CodingKey {
        let stringValue: String; let intValue: Int? = nil
        init?(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { return nil }
    }
    fileprivate static func requireKeys(_ decoder: Decoder, keys: [String]) throws {
        let c = try decoder.container(keyedBy: OpenKey.self)
        guard Set(c.allKeys.map(\.stringValue)) == Set(keys) else { throw ServiceError.invalidResponse }
    }
    init(from decoder: Decoder) throws {
        try Self.requireKeys(decoder, keys: CodingKeys.allCases.map(\.rawValue))
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = try c.decode(String.self, forKey: .version)
        selectedMethod = try c.decode(Method.self, forKey: .selectedMethod); reason = try c.decode(Reason.self, forKey: .reason)
        trainingSamples = try c.decode(Int.self, forKey: .trainingSamples); validationFolds = try c.decode(Int.self, forKey: .validationFolds)
        fittedRateMlPerHour = try c.decodeIfPresent(Double.self, forKey: .fittedRateMlPerHour)
        ridgeAlpha = try c.decode(Double.self, forKey: .ridgeAlpha)
        supportedDurationMinutes = try c.decode(Support.self, forKey: .supportedDurationMinutes)
        baselineMaeMl = try c.decodeIfPresent(Double.self, forKey: .baselineMaeMl); candidateMaeMl = try c.decodeIfPresent(Double.self, forKey: .candidateMaeMl)
        pairedGainMl = try c.decodeIfPresent(Double.self, forKey: .pairedGainMl); gainStandardErrorMl = try c.decodeIfPresent(Double.self, forKey: .gainStandardErrorMl)
        trainingSha256 = try c.decodeIfPresent(String.self, forKey: .trainingSha256)
        cadenceMaxGapSeconds = try c.decodeIfPresent(Double.self, forKey: .cadenceMaxGapSeconds)
        storage = try c.decode(String.self, forKey: .storage); validationOrigin = try c.decode(String.self, forKey: .validationOrigin)
        guard try c.decodeNil(forKey: .nominalCoverage) else { throw ServiceError.invalidResponse }; nominalCoverage = nil
    }
    func validate(request: WorkoutForecastRequest, forecast: WorkoutForecast) throws {
        func nonnegative(_ value: Double?) -> Bool { value.map { $0.isFinite && $0 >= 0 } ?? true }
        guard version == "personal-runtime-rate-v1", request.mode == "personal", reason != .actual,
              (0...32).contains(trainingSamples), trainingSamples <= request.samples.count,
              (0...max(0, request.samples.count - 3)).contains(validationFolds), ridgeAlpha == 1,
              storage == "request_memory_only", validationOrigin == "earlier_own_measurements", nominalCoverage == nil,
              nonnegative(fittedRateMlPerHour), nonnegative(baselineMaeMl), nonnegative(candidateMaeMl), nonnegative(gainStandardErrorMl),
              pairedGainMl.map(\.isFinite) ?? true,
              trainingSha256.map(validAnalysisHash) ?? true,
              cadenceMaxGapSeconds.map({ $0.isFinite && $0 > 0 }) ?? true else { throw ServiceError.invalidResponse }
        // A partial search can report folds before a final fit (trainingSamples == 0).
        // Once fitted, only strictly earlier prefixes of those fitted sessions can be folds.
        if trainingSamples > 0, validationFolds > max(0, trainingSamples - 3) { throw ServiceError.invalidResponse }
        let support = supportedDurationMinutes
        guard (support.minimum == nil) == (support.maximum == nil) else { throw ServiceError.invalidResponse }
        if let minimum = support.minimum, let maximum = support.maximum {
            guard minimum.isFinite, maximum.isFinite, minimum > 0, maximum <= 1440, minimum <= maximum else { throw ServiceError.invalidResponse }
        }
        let metrics = [baselineMaeMl, candidateMaeMl, pairedGainMl, gainStandardErrorMl]
        guard metrics.allSatisfy({ $0 == nil }) || metrics.allSatisfy({ $0 != nil }) else { throw ServiceError.invalidResponse }
        if let baselineMaeMl, let candidateMaeMl, let pairedGainMl {
            guard abs((baselineMaeMl - candidateMaeMl) - pairedGainMl) <= max(0.000001, abs(pairedGainMl) * 0.000000001) else { throw ServiceError.invalidResponse }
        }
        if selectedMethod == .fitted {
            guard reason == .selected, forecast.status == "estimated", forecast.modelVersion == version,
                  forecast.intervalKind == "personal_runtime_measurement_error_envelope",
                  forecast.personalizationStatus == "fitted_personal_rate", forecast.dataSufficiency == "earlier_own_measurements_research_only",
                  trainingSamples >= 6, validationFolds >= 3,
                  forecast.sampleCount == trainingSamples, forecast.longitudinalHistory?.comparable_samples == trainingSamples,
                  let rate = fittedRateMlPerHour, let exercise = request.exercise, exercise.comparable_conditions_confirmed,
                  let minimum = support.minimum, let maximum = support.maximum,
                  (minimum...maximum).contains(exercise.duration_minutes), trainingSha256 != nil,
                  let gain = pairedGainMl, let error = gainStandardErrorMl, gain > error, gain > 0.000000001,
                  let gap = cadenceMaxGapSeconds,
                  let lastText = forecast.longitudinalHistory?.last_observed_at,
                  let last = CalibrationHistoryValidation.date(lastText), let starts = CalibrationHistoryValidation.date(exercise.starts_at),
                  starts.timeIntervalSince(last) >= 0, starts.timeIntervalSince(last) <= gap,
                  let value = forecast.valueMl,
                  abs(value - rate * exercise.duration_minutes / 60) <= max(0.000001, abs(value) * 0.000000001)
            else { throw ServiceError.invalidResponse }
        } else {
            guard reason != .selected, forecast.modelVersion != version,
                  ["personal-longitudinal-v2", "personal-exercise-loss-v1"].contains(forecast.modelVersion) else { throw ServiceError.invalidResponse }
        }
    }
    var title: String { selectedMethod == .fitted ? "Experimental personal fit selected" : "Baseline retained" }
    var reasonText: String {
        switch reason {
        case .actual: "A completed measurement was preserved."
        case .unavailable: "The baseline could not estimate this workout."
        case .insufficient: "Too few usable comparable measurements to fit the experimental model."
        case .overlap: "Measurement windows overlap."
        case .duration: "The planned duration is outside the observed range."
        case .cadence: "The planned workout is beyond the observed session spacing."
        case .folds: "Too few strictly earlier validation comparisons."
        case .retained: "Earlier error comparisons did not justify replacing the baseline."
        case .selected: "Selected using earlier own measurements; this is not independent accuracy validation."
        case .nonfinite: "The experimental fit could not produce a valid finite result."
        }
    }
}
