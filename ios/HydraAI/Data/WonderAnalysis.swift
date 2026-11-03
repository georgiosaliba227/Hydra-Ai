import Foundation

/// An exact, bounded fact tree. Every decoded field is available for the consent preview.
indirect enum WonderAnalysisValue: Codable, Equatable, Sendable {
    case null, number(Double), text(String), flag(Bool), object([String: Self]), array([Self])
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let value = try? c.decode(Bool.self) { self = .flag(value) }
        else if let value = try? c.decode(Double.self) { self = .number(value) }
        else if let value = try? c.decode(String.self) { self = .text(value) }
        else if let value = try? c.decode([String: Self].self) { self = .object(value) }
        else { self = .array(try c.decode([Self].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .number(let value): try c.encode(value)
        case .text(let value): try c.encode(value)
        case .flag(let value): try c.encode(value)
        case .object(let value): try c.encode(value)
        case .array(let value): try c.encode(value)
        }
    }
    var object: [String: Self]? { if case .object(let value) = self { value } else { nil } }
    var number: Double? { if case .number(let value) = self { value } else { nil } }
    var text: String? { if case .text(let value) = self { value } else { nil } }
}
struct WonderAnalysisFacts: Codable, Equatable, Sendable {
    let values: [String: WonderAnalysisValue]
    init(from decoder: Decoder) throws { values = try decoder.singleValueContainer().decode([String: WonderAnalysisValue].self) }
    func encode(to encoder: Encoder) throws { var c = encoder.singleValueContainer(); try c.encode(values) }
    func validate(request: WorkoutForecastRequest, forecast: WorkoutForecast) throws {
        try validateShape()
        try request.validate(); try forecast.validate(request: request)
        guard values["mode"] == .text(request.mode),
              values["forecast"]?.object?["status"] == .text(forecast.status),
              values["forecast"]?.object?["interval_kind"] == .text(forecast.intervalKind),
              matches(values["forecast"]?.object?["value_ml"], forecast.valueMl),
              matches(values["forecast"]?.object?["lower_ml"], forecast.lowerMl),
              matches(values["forecast"]?.object?["upper_ml"], forecast.upperMl),
              values["calibration"]?.object?["total_samples"]?.number == Double(request.samples.count)
        else { throw ServiceError.invalidResponse }
        if request.mode == "personal" {
            let exercise = request.exercise
            guard matches(values["activity"]?.object?["activity"], exercise?.conditions.activity),
                  matches(values["activity"]?.object?["intensity"], exercise?.conditions.intensity),
                  matches(values["activity"]?.object?["duration_minutes"], exercise?.duration_minutes),
                  matches(values["environment"]?.object?["temperature_c"], exercise?.conditions.temperature_c),
                  matches(values["environment"]?.object?["humidity_percent"], exercise?.conditions.humidity_percent)
            else { throw ServiceError.invalidResponse }
            if let comparison = values["workout_comparison"]?.object {
                guard let exercise,
                      comparison["planned_duration_minutes"]?.number == max(1, exercise.duration_minutes.rounded(.toNearestOrAwayFromZero)),
                      comparison["planned_temperature_c"]?.number == exercise.conditions.temperature_c.rounded(.toNearestOrAwayFromZero),
                      comparison["planned_humidity_percent"]?.number == exercise.conditions.humidity_percent.rounded(.toNearestOrAwayFromZero)
                else { throw ServiceError.invalidResponse }
            }
        }
    }
}
struct WonderAnalysisResult: Decodable, Sendable {
    struct Insight: Decodable, Identifiable, Sendable { let id: String, title: String, template: String, text: String }
    struct Section: Decodable, Identifiable, Sendable {
        let id: String, title: String, template: String, text: String, evidence_status: String
        let insights: [Insight]
    }
    struct Provenance: Decodable, Sendable {
        let mode: String, provider: String, model: String, account_id: String, attempt_id: String
        let selection_origin: String, text_origin: String, numbers_checked_against: String
    }
    let version: String, payload_sha256: String, generated_at: String
    let facts: WonderAnalysisFacts
    let sections: [Section]
    let provenance: Provenance
    let provider_observations: [String: Double?]
    let limitations: [String]
    func validate() throws { try validateResult() }
}
struct WonderAnalysisPreview: Decodable, Sendable {
    let version: String, model: String, payload_sha256: String, status: String
    let facts: WonderAnalysisFacts
    let explainable: Bool
    let reason: String?
    let input_bound_tokens: Int?, max_output_tokens: Int?, worst_case_micro_usd: Int?, per_request_cap_micro_usd: Int
    let live_available: Bool, dispatch_supported: Bool, verified_for_billing: Bool
    let cost_estimate_policy: String
    let account_id: String?
    let saved: WonderAnalysisResult?
    func validate(request: WorkoutForecastRequest, forecast: WorkoutForecast) throws {
        try facts.validate(request: request, forecast: forecast)
        guard version == "wonder-analysis-preview-v2", model == "muse-wonder-1.0", validAnalysisHash(payload_sha256),
              ["available", "unavailable"].contains(status), !verified_for_billing,
              cost_estimate_policy == "existing_reference_prices_not_a_verified_live_quote",
              per_request_cap_micro_usd == 250000,
              input_bound_tokens.map({ (1...1000000).contains($0) }) ?? true,
              max_output_tokens.map({ (1...2048).contains($0) }) ?? true,
              worst_case_micro_usd.map({ (0...250000).contains($0) }) ?? true,
              account_id.map(MetaAccount.known.contains) ?? true,
              !live_available || (dispatch_supported && account_id != nil && explainable),
              !explainable || (input_bound_tokens != nil && max_output_tokens != nil && worst_case_micro_usd != nil)
        else { throw ServiceError.invalidResponse }
        if let saved {
            try saved.validate()
            guard saved.payload_sha256 == payload_sha256, saved.facts == facts else { throw ServiceError.invalidResponse }
        }
    }
}
struct WonderAnalysisResponse: Decodable, Sendable {
    let replayed: Bool, saved: Bool
    let result: WonderAnalysisResult
}
/// No transport retry. Quarantine is recorded before dispatch and survives all view invalidations.
@MainActor final class WonderAnalysisController: ObservableObject {
    @Published private(set) var preview: WonderAnalysisPreview?
    @Published private(set) var result: WonderAnalysisResult?
    @Published private(set) var state: LoadState = .idle
    @Published private(set) var explaining = false
    @Published private(set) var explainError: String?
    @Published private(set) var replayed = false
    @Published private(set) var resultSaved = false
    private var attemptedDigests: Set<String> = []
    private var generation = UUID()
    private var request: WorkoutForecastRequest?
    var isQuarantined: Bool { preview.map { attemptedDigests.contains($0.payload_sha256) && result == nil } ?? false }
    var canOffer: Bool {
        guard let preview, request?.mode == "personal", preview.explainable, preview.live_available,
              preview.dispatch_supported, preview.account_id != nil, result == nil, !explaining else { return false }
        return !attemptedDigests.contains(preview.payload_sha256)
    }
    func invalidate() {
        generation = UUID(); preview = nil; result = nil; state = .idle; request = nil
        explaining = false; explainError = nil; replayed = false; resultSaved = false
    }
    func loadPreview(_ request: WorkoutForecastRequest, forecast: WorkoutForecast, service: any BeverageService) async {
        guard !Task.isCancelled else { return }
        invalidate(); let current = generation; state = .loading
        do {
            let preview = try await service.wonderAnalysisPreview(request)
            try preview.validate(request: request, forecast: forecast)
            guard generation == current, !Task.isCancelled else { return }
            self.request = request; self.preview = preview
            result = preview.saved; replayed = preview.saved != nil; resultSaved = preview.saved != nil
            state = .loaded
        } catch {
            guard generation == current, !Task.isCancelled else { return }
            state = .failed("Detailed Muse Wonder preview is unavailable. Your local research analysis still works. Nothing was sent to Meta.")
        }
    }
    func explain(consent: Bool, service: any BeverageService) async {
        guard !Task.isCancelled, consent, canOffer, let request, let preview else { return }
        let current = generation, digest = preview.payload_sha256
        attemptedDigests.insert(digest) // Before any await: a timeout/cancel may still have charged the server attempt.
        explaining = true; explainError = nil
        defer { if current == generation { explaining = false } }
        do {
            let response = try await service.explainHydrationAnalysis(.init(forecast: request, payload_sha256: digest))
            try response.result.validate()
            guard response.result.payload_sha256 == digest, response.result.facts == preview.facts,
                  response.result.provenance.account_id == preview.account_id else { throw ServiceError.invalidResponse }
            guard generation == current, !Task.isCancelled else { return }
            result = response.result; replayed = response.replayed; resultSaved = response.saved
            if !response.saved { explainError = "This result could not be saved on your backend. It is shown for this visit; these facts will not be sent again from this screen." }
        } catch let error as WonderRequestError {
            let safe = Self.safeBeforeReservation(error)
            if safe { attemptedDigests.remove(digest) }
            guard generation == current, !Task.isCancelled else { return }
            if safe { self.preview = nil; self.request = nil; state = .idle }
            explainError = safe
                ? "No analysis request was admitted. The preview may be stale or a backend safeguard is active. Prepare a new preview and review it before agreeing again."
                : "The result is uncertain and may have been charged. These facts will not be sent again. A developer must review the backend attempt; preparing a preview can recover a saved result without another Meta request."
        } catch {
            guard generation == current, !Task.isCancelled else { return }
            explainError = "The result is uncertain and may have been charged. These facts will not be sent again. Prepare a preview only to check for a saved result, or ask a developer to review the backend attempt."
        }
    }
    private static func safeBeforeReservation(_ error: WonderRequestError) -> Bool {
        switch (error.status, error.code) {
        case (409, "analysis_preview_stale"), (409, "wonder_busy"), (409, "wonder_blocked"),
             (503, "wonder_unavailable"), (422, "analysis_insufficient_data"), (422, "invalid_request"): true
        default: false
        }
    }
}
