import Foundation

/// The two Meta accounts a backend may be configured to charge; one per backend, never switched.
enum MetaAccount {
    static let known: Set<String> = ["georgiosaliba227", "aminealichaouche"]
}

/// Aggregated facts about the last 14 days, computed by the backend's tested code. This is exactly what is sent.
struct TrendFacts: Codable, Equatable, Sendable {
    struct Day: Codable, Equatable, Sendable { let date: String; let total_ml: Int; let drinks: Int }
    struct Week: Codable, Equatable, Sendable { let total_ml: Int; let average_ml: Int; let logged_days: Int }
    struct Category: Codable, Equatable, Sendable { let category: String; let total_ml: Int; let share_pct: Int }
    struct TimeOfDay: Codable, Equatable, Sendable { let morning_ml: Int; let afternoon_ml: Int; let evening_ml: Int; let night_ml: Int }
    let version: String
    let timezone: String
    let through_date: String
    let window_days: Int
    let days: [Day]
    let last_7_days: Week
    let previous_7_days: Week
    let change_pct: Int?
    let goal_ml: Int?
    let goal_met_days_last_7: Int?
    let categories: [Category]
    let other_categories_ml: Int
    let time_of_day_ml: TimeOfDay
    let applicable_insights: [String]

    var isValid: Bool {
        version == "wonder-trends-facts-v1" && window_days == 14 && days.count == 14 && categories.count <= 12
            && days.allSatisfy({ $0.total_ml >= 0 && $0.drinks >= 0 })
            && Set(applicable_insights).isSubset(of: WonderTrends.insightIds)
    }
}

/// Muse Wonder's explanation of the user's own trends; the backend checked every number against the facts.
struct WonderTrends: Decodable, Equatable, Sendable {
    static let insightIds: Set<String> = ["week_over_week", "goal_progress", "logging_consistency", "beverage_mix", "timing"]
    static let observationKeys: Set<String> = ["latency_ms", "input_tokens", "output_tokens", "usage_derived_cost_micro_usd"]

    struct Insight: Decodable, Equatable, Identifiable, Sendable {
        let id: String
        let title: String
        let text: String
    }
    struct Provenance: Decodable, Equatable, Sendable {
        let mode: String
        let provider: String
        let model: String
        let account_id: String
        let attempt_id: String
        let text_origin: String
        let numbers_checked_against: String
    }
    let version: String
    let facts: TrendFacts
    let payload_sha256: String
    let summary: String
    let insights: [Insight]
    let generated_at: String
    let provenance: Provenance
    let provider_observations: [String: Double?]
    let limitations: [String]

    func validate() throws {
        guard version == "wonder-trends-v1", facts.isValid, payload_sha256.count == 64,
              provenance.mode == "meta_live", provenance.provider == "Meta", provenance.model == "muse-wonder-1.0",
              MetaAccount.known.contains(provenance.account_id), UUID(uuidString: provenance.attempt_id) != nil,
              provenance.text_origin == "muse_wonder_checked", provenance.numbers_checked_against == "facts",
              (1...240).contains(summary.count), (1...3).contains(insights.count),
              Set(insights.map(\.id)).count == insights.count,
              insights.allSatisfy({ facts.applicable_insights.contains($0.id) && (1...300).contains($0.text.count) }),
              Set(provider_observations.keys) == Self.observationKeys.union(["billed_cost_usd"]),
              provider_observations["billed_cost_usd"] == .some(nil),
              Self.observationKeys.allSatisfy({ ((provider_observations[$0] ?? nil) ?? -1) >= 0 }),
              (1...8).contains(limitations.count) else { throw ServiceError.invalidResponse }
    }

    var inputTokens: Int? { (provider_observations["input_tokens"] ?? nil).map { Int($0) } }
    var outputTokens: Int? { (provider_observations["output_tokens"] ?? nil).map { Int($0) } }
    var costUSD: Double? { (provider_observations["usage_derived_cost_micro_usd"] ?? nil).map { $0 / 1_000_000 } }
}

struct TrendPreview: Decodable, Sendable {
    let version: String
    let facts: TrendFacts
    let explainable: Bool
    let payload_sha256: String?
    let input_bound_tokens: Int?
    let worst_case_micro_usd: Int?
    let live_available: Bool
    let account_id: String?
    let saved: WonderTrends?
    let latest: WonderTrends?

    func validate() throws {
        guard version == "wonder-trends-v1", facts.isValid, explainable == (payload_sha256 != nil),
              explainable == (worst_case_micro_usd != nil), account_id.map(MetaAccount.known.contains) ?? true,
              live_available == (account_id != nil) else { throw ServiceError.invalidResponse }
        try saved?.validate()
        try latest?.validate()
    }
}

struct TrendExplanationRequest: Encodable, Sendable {
    let timezone: String
    let payload_sha256: String
    var consent_to_send = true
}

struct TrendExplanationResponse: Decodable, Sendable {
    let replayed: Bool
    let saved: Bool
    let result: WonderTrends
}

/// Discards late replies when the screen closes or the backend connection changes.
@MainActor final class WonderTrendsController: ObservableObject {
    @Published private(set) var preview: TrendPreview?
    @Published private(set) var result: WonderTrends?
    @Published private(set) var state: LoadState = .idle
    @Published private(set) var explaining = false
    /// The payload explained during this visit; the same data is never offered for sending again.
    @Published private(set) var explainedDigest: String?
    private var generation = UUID()

    var alreadyExplained: Bool { preview?.saved != nil || (explainedDigest != nil && explainedDigest == preview?.payload_sha256) }

    func invalidate() {
        generation = UUID(); preview = nil; result = nil; state = .idle; explaining = false; explainedDigest = nil
    }

    func load(service: any BeverageService, zone: TimeZone = .current) async {
        invalidate()
        let current = generation
        state = .loading
        do {
            let preview = try await service.wonderTrendPreview(timezone: zone.identifier)
            guard current == generation, !Task.isCancelled else { return }
            self.preview = preview
            result = preview.saved ?? preview.latest
            state = .loaded
        } catch {
            guard current == generation, !Task.isCancelled else { return }
            state = .failed("Trends are unavailable. Logging still works.")
        }
    }

    /// One billable request for exactly the previewed payload; never retried automatically.
    func explain(service: any BeverageService, zone: TimeZone = .current) async {
        guard let digest = preview?.payload_sha256, !explaining, !alreadyExplained else { return }
        let current = generation
        explaining = true
        defer { if current == generation { explaining = false } }
        do {
            let response = try await service.explainTrends(TrendExplanationRequest(timezone: zone.identifier, payload_sha256: digest))
            guard current == generation, !Task.isCancelled else { return }
            guard response.result.payload_sha256 == digest else { throw ServiceError.invalidResponse }
            result = response.result
            explainedDigest = digest
            state = .loaded
        } catch ServiceError.server(let code) {
            guard current == generation, !Task.isCancelled else { return }
            state = .failed(Self.message(for: code))
        } catch {
            guard current == generation, !Task.isCancelled else { return }
            state = .failed("Muse Wonder's reply could not be shown. Nothing will be retried automatically.")
        }
    }

    static func message(for status: Int) -> String {
        switch status {
        case 409: "Muse Wonder is paused by a spending safeguard, or your log changed. Reload and check the preview."
        case 502: "The request failed after it was reserved. Don't try again; a developer needs to check the bill."
        case 503: "Live Muse Wonder isn't set up on this backend."
        default: "Muse Wonder is unavailable. Logging still works."
        }
    }
}
