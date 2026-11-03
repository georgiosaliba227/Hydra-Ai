import Foundation

/// Aggregated facts about a planned workout and the user's previous sessions, computed by the backend's tested
/// code (docs/architecture/WONDER_WORKOUT_API.md). This is exactly what would be sent to Meta.
struct WorkoutFacts: Codable, Equatable, Sendable {
    struct Planned: Codable, Equatable, Sendable {
        let activity: String
        let intensity: String?
        let time_of_day: String
        let duration_minutes: Int
        let temperature_c: Int?
        let humidity_percent: Int?
        let conditions_confirmed: Bool
    }
    struct History: Codable, Equatable, Sendable {
        let sessions: Int
        let activity_sessions: Int
        let matching_sessions: Int
        let weigh_in_sessions: Int
        let typical_duration_minutes: Int?
        let typical_temperature_c: Int?
        let typical_humidity_percent: Int?
        let measured_loss_ml: Int?
    }
    struct Estimate: Codable, Equatable, Sendable {
        let status: String
        let value_ml: Int?
        let lower_ml: Int?
        let upper_ml: Int?
        let sample_count: Int
        let missing_inputs: [String]
    }
    struct Comparison: Codable, Equatable, Sendable {
        let duration: String?
        let temperature: String?
        let humidity: String?
        let estimate: String?
    }
    let version: String
    let timezone: String
    let planned: Planned
    let history: History
    let estimate: Estimate
    let comparison: Comparison
    let suggested_measurement: String
    let applicable_insights: [String]

    static let activities: Set<String> = ["running", "cycling", "walking", "strength", "other"]
    static let missingCodes: Set<String> = ["complete_environment_and_intensity", "confirmed_comparable_conditions",
                                            "usable_measurements_with_error_bounds", "actual_measurement_for_started_exercise"]

    var isValid: Bool {
        let counts = [history.sessions, history.activity_sessions, history.matching_sessions, history.weigh_in_sessions]
        let estimateOK: Bool
        switch estimate.status {
        case "estimated":
            if let value = estimate.value_ml, let lower = estimate.lower_ml, let upper = estimate.upper_ml {
                estimateOK = 0 <= lower && lower <= value && value <= upper && estimate.sample_count >= 1
                    && estimate.missing_inputs.isEmpty
            } else { estimateOK = false }
        case "insufficient_data":
            estimateOK = estimate.value_ml == nil && estimate.lower_ml == nil && estimate.upper_ml == nil
                && estimate.sample_count == 0
        default:
            estimateOK = false
        }
        return version == "wonder-workout-facts-v1" && TimeZone(identifier: timezone) != nil
            && Self.activities.contains(planned.activity)
            && planned.intensity.map(["low", "moderate", "high"].contains) ?? true
            && ["morning", "afternoon", "evening", "night"].contains(planned.time_of_day)
            && (1...1440).contains(planned.duration_minutes)
            && counts.allSatisfy({ (0...32).contains($0) })
            && history.matching_sessions <= history.activity_sessions && history.activity_sessions <= history.sessions
            && history.weigh_in_sessions <= history.activity_sessions
            && (history.measured_loss_ml == nil) == (history.weigh_in_sessions == 0)
            && estimateOK && Set(estimate.missing_inputs).isSubset(of: Self.missingCodes)
            && ["repeat_weigh_in", "weigh_this_workout", "record_conditions", "confirm_conditions"].contains(suggested_measurement)
            && Set(applicable_insights).isSubset(of: WonderWorkout.insightIds)
    }
}

/// Muse Wonder's explanation of a planned workout; the backend checked every number against the facts.
/// `summary_template` and each insight's `template` are deliberately not decoded: they are never displayed.
struct WonderWorkout: Decodable, Equatable, Sendable {
    /// Insight ids and the fixed titles Hydra shows for them.
    static let insightTitles: [String: String] = [
        "duration_vs_typical": "Duration vs your usual",
        "weather_vs_typical": "Weather vs your usual",
        "comparable_history": "Your previous sessions",
        "estimate": "The estimate",
        "estimate_vs_previous": "Estimate vs your measurements",
        "missing_information": "What is missing",
        "refine_estimate": "What would refine it",
    ]
    static var insightIds: Set<String> { Set(insightTitles.keys) }

    let version: String
    let facts: WorkoutFacts
    let payload_sha256: String
    let summary: String
    let insights: [WonderTrends.Insight]
    let generated_at: String
    let provenance: WonderTrends.Provenance
    let provider_observations: [String: Double?]
    let limitations: [String]

    func validate() throws {
        guard version == "wonder-workout-v1", facts.isValid, payload_sha256.count == 64,
              provenance.mode == "meta_live", provenance.provider == "Meta", provenance.model == "muse-wonder-1.0",
              MetaAccount.known.contains(provenance.account_id), UUID(uuidString: provenance.attempt_id) != nil,
              provenance.text_origin == "muse_wonder_checked", provenance.numbers_checked_against == "facts",
              // Hydra fills placeholders into checked templates, so rendered text can exceed the template limits.
              (1...1200).contains(summary.count), (1...3).contains(insights.count),
              Set(insights.map(\.id)).count == insights.count,
              insights.allSatisfy({ facts.applicable_insights.contains($0.id) && Self.insightTitles[$0.id] == $0.title
                  && (1...1500).contains($0.text.count) }),
              Set(provider_observations.keys) == WonderTrends.observationKeys.union(["billed_cost_usd"]),
              provider_observations["billed_cost_usd"] == .some(nil),
              WonderTrends.observationKeys.allSatisfy({ ((provider_observations[$0] ?? nil) ?? -1) >= 0 }),
              (1...8).contains(limitations.count) else { throw ServiceError.invalidResponse }
    }

    var inputTokens: Int? { (provider_observations["input_tokens"] ?? nil).map { Int($0) } }
    var outputTokens: Int? { (provider_observations["output_tokens"] ?? nil).map { Int($0) } }
    var costUSD: Double? { (provider_observations["usage_derived_cost_micro_usd"] ?? nil).map { $0 / 1_000_000 } }
}

/// `POST /v1/wonder/workout/preview`: what would be sent, its worst-case cost and any saved explanation.
struct WorkoutWonderPreview: Decodable, Equatable, Sendable {
    let version: String
    let facts: WorkoutFacts
    let explainable: Bool
    let payload_sha256: String?
    let input_bound_tokens: Int?
    let worst_case_micro_usd: Int?
    let live_available: Bool
    let account_id: String?
    let saved: WonderWorkout?

    func validate(request: WorkoutForecastRequest) throws {
        guard version == "wonder-workout-v1", facts.isValid, facts.timezone == request.timezone,
              facts.planned.activity == request.exercise?.conditions.activity,
              explainable == (payload_sha256 != nil), explainable == (worst_case_micro_usd != nil),
              payload_sha256.map({ $0.count == 64 }) ?? true,
              account_id.map(MetaAccount.known.contains) ?? true,
              live_available == (account_id != nil) else { throw ServiceError.invalidResponse }
        if let saved {
            try saved.validate()
            guard saved.payload_sha256 == payload_sha256 else { throw ServiceError.invalidResponse }
        }
    }
}

extension WorkoutForecastRequest {
    /// Wonder explains only a personal request with a planned workout (the synthetic demo has none).
    func validateForWonder() throws {
        try validate()
        guard mode == "personal", exercise != nil else { throw ServiceError.invalidResponse }
    }
}

/// The personal workout-forecast request plus the previewed hash and explicit consent.
/// Encodes the forecast request's own fields unchanged, so the backend recomputes exactly the previewed facts.
struct WorkoutExplanationRequest: Encodable, Sendable {
    let forecast: WorkoutForecastRequest
    let payload_sha256: String
    let consent_to_send = true

    private enum CodingKeys: String, CodingKey { case payload_sha256, consent_to_send }

    func encode(to encoder: Encoder) throws {
        try forecast.encode(to: encoder)
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(payload_sha256, forKey: .payload_sha256)
        try container.encode(consent_to_send, forKey: .consent_to_send)
    }
}

struct WorkoutExplanationResponse: Decodable, Sendable {
    let replayed: Bool
    let saved: Bool
    let result: WonderWorkout
}

/// A Wonder endpoint's error envelope: `{"code", "message", "request_id", "retryable"}`, plus `attempt_id`
/// for `wonder_attempt_unresolved`.
struct WonderRequestError: Error, Equatable, Sendable {
    let status: Int
    let code: String?
    let attemptId: String?

    init(status: Int, code: String? = nil, attemptId: String? = nil) {
        self.status = status; self.code = code; self.attemptId = attemptId
    }

    init(status: Int, body: Data) {
        struct Envelope: Decodable { let code: String?; let attempt_id: String? }
        let envelope = try? JSONDecoder().decode(Envelope.self, from: body)
        self.init(status: status, code: envelope?.code,
                  attemptId: envelope?.attempt_id.flatMap { UUID(uuidString: $0) != nil ? $0 : nil })
    }
}

/// Discards late replies when the workout changes, the screen closes or the backend connection changes.
@MainActor final class WonderWorkoutController: ObservableObject {
    @Published private(set) var preview: WorkoutWonderPreview?
    @Published private(set) var result: WonderWorkout?
    /// Preview loading and failures.
    @Published private(set) var state: LoadState = .idle
    @Published private(set) var explaining = false
    /// Why the last "Explain" did not produce a result.
    @Published private(set) var explainError: String?
    /// True when the shown result is a saved one, so nothing new was sent or charged.
    @Published private(set) var replayed = false
    /// The payload explained during this visit; the same data is never offered for sending again.
    @Published private(set) var explainedDigest: String?
    /// A payload whose attempt failed after reservation; never offered again.
    @Published private(set) var unresolvedDigest: String?
    /// The exact request previewed; "Explain" sends it again unchanged plus the hash and consent.
    private(set) var request: WorkoutForecastRequest?
    private var generation = UUID()

    var alreadyExplained: Bool {
        preview?.saved != nil || (explainedDigest != nil && explainedDigest == preview?.payload_sha256)
    }

    /// Whether the consent toggle and "Explain this workout" are offered at all.
    var canOffer: Bool {
        guard let preview, preview.explainable, preview.live_available, preview.account_id != nil,
              let digest = preview.payload_sha256 else { return false }
        return !alreadyExplained && unresolvedDigest != digest
    }

    func invalidate() {
        generation = UUID(); preview = nil; result = nil; state = .idle; explaining = false; explainError = nil
        replayed = false; explainedDigest = nil; request = nil
    }

    /// Not billable: the user's own backend computes the facts. Nothing is sent to Meta.
    /// Returns this load's generation so a caller can tell whether it is still current.
    @discardableResult
    func loadPreview(_ request: WorkoutForecastRequest, service: any BeverageService) async -> UUID {
        let keepUnresolved = unresolvedDigest
        invalidate()
        unresolvedDigest = keepUnresolved
        let current = generation
        state = .loading
        do {
            try request.validateForWonder()
            let preview = try await service.wonderWorkoutPreview(request)
            try preview.validate(request: request)
            guard current == generation, !Task.isCancelled else { return current }
            self.request = request
            self.preview = preview
            result = preview.saved
            replayed = preview.saved != nil
            state = .loaded
        } catch {
            guard current == generation, !Task.isCancelled else { return current }
            state = .failed(Self.previewMessage(for: error))
        }
        return current
    }

    /// One billable request for exactly the previewed payload, only with consent; never retried automatically.
    func explain(consent: Bool, service: any BeverageService) async {
        guard consent, canOffer, !explaining, let request, let digest = preview?.payload_sha256 else { return }
        let current = generation
        explaining = true
        explainError = nil
        defer { if current == generation { explaining = false } }
        do {
            let response = try await service.explainWorkout(WorkoutExplanationRequest(forecast: request, payload_sha256: digest))
            guard current == generation, !Task.isCancelled else { return }
            guard response.result.payload_sha256 == digest else { throw ServiceError.invalidResponse }
            result = response.result
            replayed = response.replayed
            explainedDigest = digest
        } catch let error as WonderRequestError {
            guard current == generation, !Task.isCancelled else { return }
            if error.code == "wonder_attempt_unresolved" || error.status == 502 { unresolvedDigest = digest }
            if error.code == "workout_preview_stale" {
                // The facts changed (for example the start time passed). Preview again; consent is asked again.
                let fresh = await loadPreview(request, service: service)
                guard fresh == generation, !Task.isCancelled else { return }
            }
            explainError = Self.message(for: error)
        } catch {
            guard current == generation, !Task.isCancelled else { return }
            explainError = "Muse Wonder's reply could not be shown. Nothing will be retried automatically."
        }
    }

    nonisolated static func previewMessage(for error: Error) -> String {
        if let error = error as? WonderRequestError, error.code == "invalid_request" || error.status == 422 {
            return "Hydra couldn't prepare a summary of this workout. Check the fields above and estimate again."
        }
        return "Muse Wonder's preview is unavailable. Your estimate above still works."
    }

    nonisolated static func message(for error: WonderRequestError) -> String {
        switch error.code {
        case "workout_preview_stale":
            return "Your workout or measurements changed since the preview. Review the updated summary and agree again."
        case "workout_insufficient_history":
            return "Log a previous session of this activity first. Add a measured workout under \"Your own measurements\"."
        case "wonder_blocked":
            return "Muse Wonder is paused by a spending safeguard. Nothing was sent or charged."
        case "wonder_busy":
            return "Another Muse Wonder request is in progress. Try again in a moment."
        case "wonder_attempt_unresolved":
            let attempt = error.attemptId.map { " (attempt \($0))" } ?? ""
            return "The request failed after it was reserved. Don't try again; a developer must review this attempt\(attempt)."
        case "wonder_unavailable":
            return "Live Muse Wonder isn't set up on this backend."
        case "invalid_request":
            return "Hydra couldn't send this workout. Check the fields above and estimate again."
        default:
            switch error.status {
            case 502: return "The request failed after it was reserved. Don't try again; a developer must review this attempt."
            case 503: return "Live Muse Wonder isn't set up on this backend."
            default: return "Muse Wonder is unavailable. Your estimate above still works."
            }
        }
    }
}
