import Foundation

struct HydrationScoreRequest: Encodable, Sendable {
    let timezone: String, measurement_count: Int, processing_consent: Bool
    func validate() throws {
        guard processing_consent else { throw ServiceError.consent }
        guard timezone.count <= 128, TimeZone(identifier: timezone) != nil, (0...32).contains(measurement_count) else { throw ServiceError.invalidResponse }
    }
}
struct HydrationScoreExplanationRequest: Encodable, Sendable {
    let timezone: String, measurement_count: Int, processing_consent: Bool, payload_sha256: String, consent_to_send: Bool
    func validate() throws {
        try HydrationScoreRequest(timezone: timezone, measurement_count: measurement_count, processing_consent: processing_consent).validate()
        guard consent_to_send else { throw ServiceError.consent }
        guard validAnalysisHash(payload_sha256) else { throw ServiceError.invalidResponse }
    }
}
struct HydrationScorePreview: Decodable, Sendable {
    let version: String, payload_sha256: String, model: String, cost_estimate_policy: String
    let facts: HydrationScoreFacts
    let input_bound_tokens: Int, max_output_tokens: Int, worst_case_micro_usd: Int, per_request_cap_micro_usd: Int
    let live_available: Bool
    let account_id: String?
    let saved: HydrationScoreExplanationResult?
    enum CodingKeys: String, CodingKey {
        case version, facts, payload_sha256, model, input_bound_tokens, max_output_tokens, worst_case_micro_usd
        case per_request_cap_micro_usd, live_available, account_id, saved, cost_estimate_policy
    }
    init(from decoder: Decoder) throws {
        try scoreExactKeys(decoder, ["version", "facts", "payload_sha256", "model", "input_bound_tokens", "max_output_tokens", "worst_case_micro_usd", "per_request_cap_micro_usd", "live_available", "account_id", "saved", "cost_estimate_policy"])
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = try c.decode(String.self, forKey: .version); facts = try c.decode(HydrationScoreFacts.self, forKey: .facts)
        payload_sha256 = try c.decode(String.self, forKey: .payload_sha256); model = try c.decode(String.self, forKey: .model)
        input_bound_tokens = try c.decode(Int.self, forKey: .input_bound_tokens); max_output_tokens = try c.decode(Int.self, forKey: .max_output_tokens)
        worst_case_micro_usd = try c.decode(Int.self, forKey: .worst_case_micro_usd)
        per_request_cap_micro_usd = try c.decode(Int.self, forKey: .per_request_cap_micro_usd)
        live_available = try c.decode(Bool.self, forKey: .live_available); account_id = try c.decodeIfPresent(String.self, forKey: .account_id)
        saved = try c.decodeIfPresent(HydrationScoreExplanationResult.self, forKey: .saved)
        cost_estimate_policy = try c.decode(String.self, forKey: .cost_estimate_policy)
    }
    func validate(expected: HydrationScoreFacts) throws {
        try facts.validate(expected: expected)
        guard version == "wonder-score-preview-v1", model == "muse-wonder-1.0", validAnalysisHash(payload_sha256),
              (1...1_000_000).contains(input_bound_tokens), max_output_tokens == 1024,
              per_request_cap_micro_usd == 250000, (0...250000).contains(worst_case_micro_usd),
              worst_case_micro_usd == input_bound_tokens * 4 + max_output_tokens * 20,
              cost_estimate_policy == "existing_reference_prices_not_a_verified_live_quote",
              account_id.map(MetaAccount.known.contains) ?? true, !live_available || account_id != nil else { throw ServiceError.invalidResponse }
        if let saved {
            try saved.validate(); try saved.facts.validate(expected: facts)
            guard saved.payload_sha256 == payload_sha256 else { throw ServiceError.invalidResponse }
        }
    }
}
struct HydrationScoreExplanationResponse: Decodable, Sendable {
    let replayed: Bool, saved: Bool
    let result: HydrationScoreExplanationResult
    enum CodingKeys: String, CodingKey { case replayed, saved, result }
    init(from decoder: Decoder) throws {
        try scoreExactKeys(decoder, ["replayed", "saved", "result"])
        let c = try decoder.container(keyedBy: CodingKeys.self)
        replayed = try c.decode(Bool.self, forKey: .replayed); saved = try c.decode(Bool.self, forKey: .saved)
        result = try c.decode(HydrationScoreExplanationResult.self, forKey: .result)
    }
}
struct HydrationScoreExplanationResult: Decodable, Sendable {
    struct Insight: Decodable, Identifiable, Sendable {
        let id: String, title: String, text: String
        enum CodingKeys: String, CodingKey { case id, title, text }
        init(from decoder: Decoder) throws {
            try scoreExactKeys(decoder, ["id", "title", "text"])
            let c = try decoder.container(keyedBy: CodingKeys.self)
            id = try c.decode(String.self, forKey: .id); title = try c.decode(String.self, forKey: .title); text = try c.decode(String.self, forKey: .text)
        }
    }
    struct Provenance: Decodable, Sendable {
        let mode: String, provider: String, model: String, account_id: String, attempt_id: String
        let selection_origin: String, text_origin: String, numbers_checked_against: String
        enum CodingKeys: String, CodingKey { case mode, provider, model, account_id, attempt_id, selection_origin, text_origin, numbers_checked_against }
        init(from decoder: Decoder) throws {
            try scoreExactKeys(decoder, ["mode", "provider", "model", "account_id", "attempt_id", "selection_origin", "text_origin", "numbers_checked_against"])
            let c = try decoder.container(keyedBy: CodingKeys.self)
            mode = try c.decode(String.self, forKey: .mode); provider = try c.decode(String.self, forKey: .provider)
            model = try c.decode(String.self, forKey: .model); account_id = try c.decode(String.self, forKey: .account_id)
            attempt_id = try c.decode(String.self, forKey: .attempt_id); selection_origin = try c.decode(String.self, forKey: .selection_origin)
            text_origin = try c.decode(String.self, forKey: .text_origin); numbers_checked_against = try c.decode(String.self, forKey: .numbers_checked_against)
        }
    }
    let version: String, payload_sha256: String, generated_at: String
    let facts: HydrationScoreFacts
    let insights: [Insight]
    let provenance: Provenance
    let provider_observations: [String: Double?]
    let limitations: [String]
    enum CodingKeys: String, CodingKey { case version, facts, payload_sha256, insights, generated_at, provenance, provider_observations, limitations }
    init(from decoder: Decoder) throws {
        try scoreExactKeys(decoder, ["version", "facts", "payload_sha256", "insights", "generated_at", "provenance", "provider_observations", "limitations"])
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = try c.decode(String.self, forKey: .version); facts = try c.decode(HydrationScoreFacts.self, forKey: .facts)
        payload_sha256 = try c.decode(String.self, forKey: .payload_sha256); insights = try c.decode([Insight].self, forKey: .insights)
        generated_at = try c.decode(String.self, forKey: .generated_at); provenance = try c.decode(Provenance.self, forKey: .provenance)
        provider_observations = try c.decode([String: Double?].self, forKey: .provider_observations)
        limitations = try c.decode([String].self, forKey: .limitations)
    }
    func validate() throws {
        try facts.validate()
        guard version == "wonder-score-live-v1", validAnalysisHash(payload_sha256),
              generated_at.hasSuffix("Z") || generated_at.hasSuffix("+00:00"), CalibrationHistoryValidation.date(generated_at) != nil,
              provenance.mode == "meta_live", provenance.provider == "Meta", provenance.model == "muse-wonder-1.0",
              MetaAccount.known.contains(provenance.account_id), UUID(uuidString: provenance.attempt_id) != nil,
              provenance.selection_origin == "muse-wonder-1.0", provenance.text_origin == "hydra_reviewed_selected_by_muse",
              provenance.numbers_checked_against == "facts", limitations == Self.fixedLimitations,
              Set(provider_observations.keys) == ["latency_ms", "input_tokens", "output_tokens", "usage_derived_cost_micro_usd", "billed_cost_usd"],
              provider_observations["billed_cost_usd"] == .some(nil),
              provider_observations.filter({ $0.key != "billed_cost_usd" }).values.allSatisfy({ $0.map { $0.isFinite && $0 >= 0 && $0.rounded() == $0 } ?? false }),
              (3...6).contains(insights.count), Set(insights.map(\.id)).count == insights.count,
              Set(["today_alignment", "recent_consistency", "measurement_support"]).isSubset(of: Set(insights.map(\.id))) else { throw ServiceError.invalidResponse }
        let choices = Self.allowedTexts(facts)
        for insight in insights {
            guard Self.titles[insight.id] == insight.title, choices[insight.id]?.contains(insight.text) == true else { throw ServiceError.invalidResponse }
        }
    }
    static let titles = ["today_alignment": "Today's goal alignment", "recent_consistency": "Recorded consistency",
        "measurement_support": "Measurement support", "goal_cap": "Capped goal rewards", "unlogged_unknown": "Unlogged intake is unknown", "research_meaning": "Experimental meaning"]
    static let fixedLimitations = ["Experimental product rubric; not hydration status or a drinking requirement.",
        "Extra logged volume above the current chosen goal earns no extra points.", "An unlogged day does not establish no actual consumption.",
        "Measurement support does not establish physiological accuracy or narrower uncertainty."]
    static func allowedTexts(_ facts: HydrationScoreFacts) -> [String: [String]] {
        var choices = [
            "today_alignment": facts.today_ml > 0 ? ["Today's logged beverage volume is compared with the current chosen goal.", "The current chosen goal is the reference for today's logged volume."] : ["Today's record has no logged beverage volume in this snapshot.", "No beverage volume is logged for today in this snapshot."],
            "recent_consistency": facts.previous_days.contains(where: \.logged) ? ["Recorded prior-day volumes are compared with the current chosen goal.", "The current chosen goal is the retrospective reference for recorded consistency."] : ["The preceding local dates have no logged beverage volume in this snapshot.", "This snapshot contains no logged beverage volume for the preceding local dates."],
            "measurement_support": facts.measurement_count > 0 ? ["Validated manual sessions contribute measurement support to this snapshot.", "The measurement component reflects documented valid manual sessions."] : ["No validated manual sessions contribute measurement support to this snapshot.", "This snapshot has no valid manual sessions for the measurement component."],
            "goal_cap": ["Logged volume beyond the current chosen goal earns no extra score points.", "The goal-based contributions stop growing at the current chosen goal."],
            "research_meaning": ["This score is an unvalidated product rubric, not a physiological measurement.", "The score describes recorded goal alignment, consistency and measurement support."]]
        if facts.previous_days.contains(where: { !$0.logged }) {
            choices["unlogged_unknown"] = ["Unlogged prior dates earn no recorded-consistency points; actual consumption is unknown.", "Absence of a beverage log does not establish absence of consumption."]
        }
        return choices
    }
}

private struct ScoreWireKey: CodingKey {
    let stringValue: String; var intValue: Int? { nil }
    init?(stringValue: String) { self.stringValue = stringValue }; init?(intValue: Int) { return nil }
}
func scoreExactKeys(_ decoder: Decoder, _ expected: Set<String>) throws {
    let c = try decoder.container(keyedBy: ScoreWireKey.self)
    guard Set(c.allKeys.map(\.stringValue)) == expected else { throw ServiceError.invalidResponse }
}

@MainActor final class HydrationScoreWonderController: ObservableObject {
    @Published var processingConsent = false
    @Published var metaConsent = false
    @Published private(set) var preview: HydrationScorePreview?
    @Published private(set) var result: HydrationScoreExplanationResult?
    @Published private(set) var state: LoadState = .idle
    @Published private(set) var explaining = false
    @Published private(set) var explainError: String?
    @Published private(set) var replayed = false
    private var attempted = Set<String>(), generation = UUID()
    var isQuarantined: Bool { preview.map { attempted.contains($0.payload_sha256) && result == nil } ?? false }
    var canOffer: Bool { processingConsent && preview?.live_available == true && result == nil && !isQuarantined && !explaining }
    func invalidate() {
        generation = UUID(); processingConsent = false; metaConsent = false; preview = nil; result = nil
        state = .idle; explaining = false; explainError = nil; replayed = false
    }
    func prepare(facts: HydrationScoreFacts, service: any BeverageService) async {
        guard processingConsent, !explaining, state != .loading, !Task.isCancelled else { return }
        let current = generation; state = .loading; preview = nil; result = nil; metaConsent = false; explainError = nil
        do {
            try facts.validate()
            let response = try await service.hydrationScorePreview(.init(timezone: facts.timezone, measurement_count: facts.measurement_count, processing_consent: true))
            try response.validate(expected: facts)
            guard generation == current, !Task.isCancelled else { return }
            preview = response; result = response.saved; replayed = response.saved != nil; state = .loaded
        } catch {
            guard generation == current, !Task.isCancelled else { return }
            state = .failed("Score facts could not be confirmed against your current Home snapshot. Refresh your logs and review again. Nothing was sent to Meta.")
        }
    }
    func explain(service: any BeverageService) async {
        guard metaConsent, canOffer, let preview, !Task.isCancelled else { return }
        let current = generation, digest = preview.payload_sha256
        attempted.insert(digest); explaining = true; explainError = nil
        defer { if generation == current { explaining = false } }
        do {
            let request = HydrationScoreExplanationRequest(timezone: preview.facts.timezone, measurement_count: preview.facts.measurement_count,
                processing_consent: true, payload_sha256: digest, consent_to_send: true)
            let response = try await service.explainHydrationScore(request)
            try response.result.validate(); try response.result.facts.validate(expected: preview.facts)
            guard response.result.payload_sha256 == digest, response.result.provenance.account_id == preview.account_id else { throw ServiceError.invalidResponse }
            guard generation == current, !Task.isCancelled else { return }
            result = response.result; replayed = response.replayed
            if !response.saved { explainError = "This explanation could not be saved. It remains visible for this visit; these facts will not be charged again from this screen." }
        } catch let error as WonderRequestError {
            let safe = Self.preAdmission(error)
            if safe { attempted.remove(digest) }
            guard generation == current, !Task.isCancelled else { return }
            if safe { self.preview = nil; metaConsent = false; state = .idle }
            explainError = safe ? "No request was admitted. Check backend availability, then prepare and review a fresh preview."
                : "This attempt may have been charged. These facts will not be sent again. Prepare a preview only to recover a saved result, or ask for an account review."
        } catch {
            guard generation == current, !Task.isCancelled else { return }
            explainError = "This attempt may have been charged. These facts will not be sent again. A preview can recover a saved result without another request."
        }
    }
    private static func preAdmission(_ error: WonderRequestError) -> Bool {
        switch (error.status, error.code) {
        case (409, "score_preview_stale"), (422, "goal_required"), (409, "wonder_busy"), (409, "wonder_blocked"),
             (503, "wonder_unavailable"), (422, "invalid_request"): true
        default: false
        }
    }
}
