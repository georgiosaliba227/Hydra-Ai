import CryptoKit
import Foundation

/// Read-only replay of the operator's one-use, invented-data demonstration.
/// This type cannot be used as an ordinary personal Wonder result or forecast.
struct OwnerSyntheticWonderResult: Decodable, Sendable {
    static let payloadHash = "12ef839f44757b452034632ef91c50ff44455e6c02c99104230f4c46d02ab34c"
    private static let fixedFactsHash = "6b5c3e9963e6bea6fa5a3d3013162f6368cc3f6e7c40a979201cebb829f1e3e6"
    struct Receipt: Decodable, Sendable {
        let account_id: String, attempt_id: String, model: String, payload_sha256: String, state: String
        let input_tokens: Int, output_tokens: Int, cached_tokens: Int, usage_derived_cost_micro_usd: Int
        let token_reservation_micro_usd: Int, published_token_bound_micro_usd: Int
        let provider_invoice_final: Bool, provider_extras_bounded: Bool
        enum CodingKeys: String, CodingKey, CaseIterable {
            case account_id, attempt_id, model, payload_sha256, state, input_tokens, output_tokens, cached_tokens
            case usage_derived_cost_micro_usd, token_reservation_micro_usd, published_token_bound_micro_usd
            case provider_invoice_final, provider_extras_bounded
        }
        init(from decoder: Decoder) throws {
            try ownerExactKeys(decoder, Set(CodingKeys.allCases.map(\.rawValue)))
            let c = try decoder.container(keyedBy: CodingKeys.self)
            account_id = try c.decode(String.self, forKey: .account_id); attempt_id = try c.decode(String.self, forKey: .attempt_id)
            model = try c.decode(String.self, forKey: .model); payload_sha256 = try c.decode(String.self, forKey: .payload_sha256)
            state = try c.decode(String.self, forKey: .state)
            input_tokens = try c.decode(Int.self, forKey: .input_tokens); output_tokens = try c.decode(Int.self, forKey: .output_tokens)
            cached_tokens = try c.decode(Int.self, forKey: .cached_tokens)
            usage_derived_cost_micro_usd = try c.decode(Int.self, forKey: .usage_derived_cost_micro_usd)
            token_reservation_micro_usd = try c.decode(Int.self, forKey: .token_reservation_micro_usd)
            published_token_bound_micro_usd = try c.decode(Int.self, forKey: .published_token_bound_micro_usd)
            provider_invoice_final = try c.decode(Bool.self, forKey: .provider_invoice_final)
            provider_extras_bounded = try c.decode(Bool.self, forKey: .provider_extras_bounded)
        }
    }
    struct Analysis: Decodable, Sendable {
        struct Provenance: Decodable, Sendable {
            let selection_origin: String, text_origin: String, provider: String, model: String, numbers_checked_against: String
            let provider_authenticity_or_billing_attested: Bool
            enum CodingKeys: String, CodingKey, CaseIterable {
                case selection_origin, text_origin, provider, model, numbers_checked_against, provider_authenticity_or_billing_attested
            }
            init(from decoder: Decoder) throws {
                try ownerExactKeys(decoder, Set(CodingKeys.allCases.map(\.rawValue)))
                let c = try decoder.container(keyedBy: CodingKeys.self)
                selection_origin = try c.decode(String.self, forKey: .selection_origin)
                text_origin = try c.decode(String.self, forKey: .text_origin)
                provider = try c.decode(String.self, forKey: .provider); model = try c.decode(String.self, forKey: .model)
                numbers_checked_against = try c.decode(String.self, forKey: .numbers_checked_against)
                provider_authenticity_or_billing_attested = try c.decode(Bool.self, forKey: .provider_authenticity_or_billing_attested)
            }
        }
        let version: String, payload_sha256: String
        let facts: WonderAnalysisFacts
        let sections: [WonderAnalysisResult.Section]
        let dispatch_supported: Bool
        let limitations: [String]
        let provenance: Provenance
        enum CodingKeys: String, CodingKey, CaseIterable {
            case version, payload_sha256, facts, sections, dispatch_supported, limitations, provenance
        }
        init(from decoder: Decoder) throws {
            try ownerExactKeys(decoder, Set(CodingKeys.allCases.map(\.rawValue)))
            let c = try decoder.container(keyedBy: CodingKeys.self)
            version = try c.decode(String.self, forKey: .version); payload_sha256 = try c.decode(String.self, forKey: .payload_sha256)
            facts = try c.decode(WonderAnalysisFacts.self, forKey: .facts)
            sections = try c.decode([WonderAnalysisResult.Section].self, forKey: .sections)
            dispatch_supported = try c.decode(Bool.self, forKey: .dispatch_supported)
            limitations = try c.decode([String].self, forKey: .limitations)
            provenance = try c.decode(Provenance.self, forKey: .provenance)
        }
    }
    let version: String, mode: String, generated_at: String
    let result: Analysis
    let receipt: Receipt
    enum CodingKeys: String, CodingKey, CaseIterable { case version, mode, generated_at, result, receipt }
    init(from decoder: Decoder) throws {
        try ownerExactKeys(decoder, Set(CodingKeys.allCases.map(\.rawValue)))
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = try c.decode(String.self, forKey: .version); mode = try c.decode(String.self, forKey: .mode)
        generated_at = try c.decode(String.self, forKey: .generated_at)
        result = try c.decode(Analysis.self, forKey: .result); receipt = try c.decode(Receipt.self, forKey: .receipt)
    }
    func validate() throws {
        try result.facts.validateShape()
        guard version == "wonder-owner-once-result-v1", mode == "synthetic_demo",
              generated_at.hasSuffix("Z") || generated_at.hasSuffix("+00:00"),
              CalibrationHistoryValidation.date(generated_at) != nil,
              result.version == "wonder-analysis-preview-v2", result.payload_sha256 == Self.payloadHash,
              !result.dispatch_supported, result.facts.values["mode"] == .text("synthetic_demo"),
              result.provenance.selection_origin == "checked_provider_reply",
              result.provenance.text_origin == "hydra_vetted_scaffolds_and_facts",
              result.provenance.provider == "Meta", result.provenance.model == "muse-wonder-1.0",
              result.provenance.numbers_checked_against == "facts", !result.provenance.provider_authenticity_or_billing_attested,
              result.limitations == Self.recordedLimitations,
              receipt.account_id == "georgiosaliba227", receipt.model == "muse-wonder-1.0",
              UUID(uuidString: receipt.attempt_id)?.uuidString.lowercased() == receipt.attempt_id,
              receipt.payload_sha256 == Self.payloadHash, receipt.state == "billing_pending",
              !receipt.provider_invoice_final, !receipt.provider_extras_bounded,
              receipt.token_reservation_micro_usd == 250000, receipt.published_token_bound_micro_usd == 59960,
              (0...4750).contains(receipt.input_tokens), (0...2048).contains(receipt.output_tokens),
              (0...receipt.input_tokens).contains(receipt.cached_tokens),
              receipt.usage_derived_cost_micro_usd == receipt.input_tokens * 4 + receipt.output_tokens * 20
        else { throw ServiceError.invalidResponse }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let digest = SHA256.hash(data: try encoder.encode(result.facts)).map { String(format: "%02x", $0) }.joined()
        guard digest == Self.fixedFactsHash else { throw ServiceError.invalidResponse }
        try WonderAnalysisResult.validateSections(result.sections, facts: result.facts)
    }
    func localText(_ section: WonderAnalysisResult.Section) throws -> String {
        let values = try WonderAnalysisRenderer.placeholders(result.facts)
        guard let caveat = WonderAnalysisRenderer.requiredCaveats[section.id] else { throw ServiceError.invalidResponse }
        let templates = try section.insights.map { insight -> String in
            guard let contract = WonderAnalysisResult.insightContracts[section.id]?[insight.id] else { throw ServiceError.invalidResponse }
            return contract.1
        }
        return WonderAnalysisRenderer.render((templates + [caveat]).joined(separator: " "), values: values)
    }
    static let recordedLimitations = [
        "Offline contract and mock/recorded validation only; live dispatch and client integration are not implemented here.",
        "Muse Wonder can select vetted scaffolds; Hydra authors the factual clauses and supplies every number.",
        "Logged intake does not measure hydration status, retention or a required intake amount.",
        "Workout loss is a research mass-balance proxy; historical envelopes do not guarantee future interval coverage.",
        "Recorded consistency checks do not attest provider authenticity, billing settlement or spending authorization.",
        "Displayed amounts are rounded to whole mL; range endpoints are rounded outward. Numeric facts remain unchanged.",
    ]
}

private struct OwnerWonderKey: CodingKey {
    let stringValue: String
    var intValue: Int? { nil }
    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { return nil }
}
private func ownerExactKeys(_ decoder: Decoder, _ expected: Set<String>) throws {
    let c = try decoder.container(keyedBy: OwnerWonderKey.self)
    guard Set(c.allKeys.map(\.stringValue)) == expected else { throw ServiceError.invalidResponse }
}

@MainActor final class OwnerSyntheticWonderController: ObservableObject {
    @Published private(set) var result: OwnerSyntheticWonderResult?
    @Published private(set) var state: LoadState = .idle
    private var generation = UUID()
    func invalidate() { generation = UUID(); result = nil; state = .idle }
    func load(service: HTTPBeverageService) async {
        guard state != .loading, !Task.isCancelled else { return }
        let current = generation; state = .loading; result = nil
        do {
            let record = try await service.ownerSyntheticWonderResult()
            guard generation == current, !Task.isCancelled else { return }
            result = record; state = .loaded
        } catch {
            guard generation == current, !Task.isCancelled else { return }
            state = .failed("No verified recorded Wonder test is available from this backend. Loading it makes no Meta request.")
        }
    }
}
