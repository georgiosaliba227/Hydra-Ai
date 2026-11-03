import Foundation

/// Financial availability only. This response never grants personal-data consent.
struct WonderReadiness: Decodable, Sendable {
    enum Status: String, Decodable, Sendable { case disabled, blocked, ready }
    enum Reason: String, Decodable, Hashable, Identifiable, Sendable {
        case liveDisabled = "live_disabled"
        case ownerPolicyNotRecorded = "owner_policy_not_recorded"
        case ownerPolicyInvalid = "owner_policy_invalid"
        case quoteExpired = "quote_expired"
        case accountObservationStale = "account_observation_stale"
        case crossLedgerStatusUnverified = "cross_ledger_status_unverified"
        case notificationDeliveryUnverified = "notification_delivery_unverified"
        case currentInvoiceFinalityRequired = "current_invoice_finality_required"
        case requestInFlight = "request_in_flight"
        case financialFailureRequiresReview = "financial_failure_requires_review"
        case budgetExhausted = "budget_exhausted"
        case verifiedFinancialChecksRequired = "verified_financial_checks_required"
        case storageUnavailable = "storage_unavailable"
        var id: String { rawValue }
        var message: String {
            switch self {
            case .liveDisabled: "Live Wonder is disabled on this backend."
            case .ownerPolicyNotRecorded: "The backend's owner authorization has not been recorded."
            case .ownerPolicyInvalid: "The backend's owner authorization needs review."
            case .quoteExpired: "The model price quote needs renewal."
            case .accountObservationStale: "The account's latest billing and credit check needs renewal."
            case .crossLedgerStatusUnverified: "Current spending activity across the developers' accounts needs confirmation."
            case .notificationDeliveryUnverified: "Spending notification delivery needs confirmation."
            case .currentInvoiceFinalityRequired: "Final billing for a recent request still needs confirmation."
            case .requestInFlight: "Another request is still running."
            case .financialFailureRequiresReview: "A prior request needs a financial review."
            case .budgetExhausted: "The existing spending allocation or account limit blocks another request."
            case .verifiedFinancialChecksRequired: "The backend's standard financial checks need completion."
            case .storageUnavailable: "The backend's financial records are unavailable."
            }
        }
    }
    let version: String
    let configured: Bool
    let status: Status
    let account_id: String?
    let policy: String?
    let blocked_reasons: [Reason]
    let all_charge_categories_verified: Bool?
    let per_request_token_cap_micro_usd: Int
    enum CodingKeys: String, CodingKey, CaseIterable {
        case version, configured, status, account_id, policy, blocked_reasons
        case all_charge_categories_verified, per_request_token_cap_micro_usd
    }
    init(from decoder: Decoder) throws {
        let keys = try decoder.container(keyedBy: ReadinessWireKey.self)
        guard Set(keys.allKeys.map(\.stringValue)) == Set(CodingKeys.allCases.map(\.rawValue)) else { throw ServiceError.invalidResponse }
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = try c.decode(String.self, forKey: .version)
        configured = try c.decode(Bool.self, forKey: .configured)
        status = try c.decode(Status.self, forKey: .status)
        account_id = try c.decodeIfPresent(String.self, forKey: .account_id)
        policy = try c.decodeIfPresent(String.self, forKey: .policy)
        blocked_reasons = try c.decode([Reason].self, forKey: .blocked_reasons)
        all_charge_categories_verified = try c.decodeIfPresent(Bool.self, forKey: .all_charge_categories_verified)
        per_request_token_cap_micro_usd = try c.decode(Int.self, forKey: .per_request_token_cap_micro_usd)
        guard version == "wonder-readiness-v1", per_request_token_cap_micro_usd == 250000,
              account_id.map(MetaAccount.known.contains) ?? true,
              policy.map({ ["verified", "owner_accepted_risk"].contains($0) }) ?? true,
              Set(blocked_reasons).count == blocked_reasons.count,
              policy != "owner_accepted_risk" || all_charge_categories_verified == false
        else { throw ServiceError.invalidResponse }
        switch status {
        case .disabled:
            guard !configured, account_id == nil, policy == nil, all_charge_categories_verified == nil,
                  blocked_reasons == [.liveDisabled] else { throw ServiceError.invalidResponse }
        case .blocked:
            guard configured, account_id != nil, policy != nil, !blocked_reasons.isEmpty,
                  !blocked_reasons.contains(.liveDisabled) else { throw ServiceError.invalidResponse }
        case .ready:
            guard configured, account_id != nil, policy != nil, blocked_reasons.isEmpty,
                  policy != "verified" || all_charge_categories_verified == true else { throw ServiceError.invalidResponse }
        }
    }
    var statusText: String {
        switch status {
        case .disabled: "Live Wonder is disabled"
        case .blocked: "Live Wonder is currently blocked"
        case .ready: "Ready for a previewed, consented request"
        }
    }
}

private struct ReadinessWireKey: CodingKey {
    let stringValue: String
    var intValue: Int? { nil }
    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { return nil }
}

protocol WonderReadinessService: Sendable {
    func wonderReadiness() async throws -> WonderReadiness
}
extension HTTPBeverageService: WonderReadinessService { }

@MainActor final class WonderReadinessController: ObservableObject {
    @Published private(set) var result: WonderReadiness?
    @Published private(set) var state: LoadState = .idle
    private var generation = UUID()
    func invalidate() { generation = UUID(); result = nil; state = .idle }
    func load(service: any WonderReadinessService) async {
        guard state != .loading, !Task.isCancelled else { return }
        let current = generation; state = .loading; result = nil
        do {
            let readiness = try await service.wonderReadiness()
            guard generation == current, !Task.isCancelled else { return }
            result = readiness; state = .loaded
        } catch {
            guard generation == current, !Task.isCancelled else { return }
            state = .failed("Could not check live Wonder availability. No Meta request was made.")
        }
    }
}
