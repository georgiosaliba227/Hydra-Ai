import SwiftUI

/// Muse Wonder explains the user's own 14-day trends. The exact data is shown before anything is sent.
struct TrendsView: View {
    @EnvironmentObject private var store: BeverageStore
    @StateObject private var controller = WonderTrendsController()
    @State private var consent = false
    @State private var task: Task<Void, Never>?

    private var connected: Bool { store.isConfigured && !store.isOffline }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: HydraSpacing.section) {
                intro
                if !connected {
                    StatusBanner(text: "Connect to your backend in Settings to see trends.", systemImage: "link", tint: .hydraTint)
                }
                if controller.state == .loading {
                    ProgressView("Loading your last 14 days…").frame(maxWidth: .infinity).hydraCard()
                }
                if case .failed(let message) = controller.state {
                    StatusBanner(text: message)
                        .accessibilityElement(children: .combine)
                        .accessibilityIdentifier("trendsError")
                }
                if let result = controller.result { resultSection(result) }
                if let preview = controller.preview { sendSection(preview) }
                InfoNote("Wellness information, not medical advice. Your drink log describes what you drank, not your hydration.",
                         systemImage: "heart.circle")
                    .padding(.horizontal, 4)
            }
            .hydraScreen()
        }
        .background(Color.hydraBackground)
        .navigationTitle("Your trends")
        .task { reload() }
        .onChange(of: store.configurationGeneration) { _, _ in reload() }
        .onDisappear { task?.cancel(); task = nil; controller.invalidate() }
    }

    private var intro: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Meta's Muse Wonder 1.0 explains patterns in your last 14 days of drinks.")
                .font(.subheadline)
                .fixedSize(horizontal: false, vertical: true)
            HydraDisclosure(title: "How it works") {
                Text("Wonder picks what matters and writes the wording. Hydra fills in every number from your own log and rejects any advice or medical claims before you see it.")
            }
        }
        .hydraCard()
    }

    // MARK: - Result

    @ViewBuilder private func resultSection(_ result: WonderTrends) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Your 14 days", trailing: "through \(result.facts.through_date)")
            VStack(alignment: .leading, spacing: 10) {
                Label("Muse Wonder 1.0", systemImage: "sparkles")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color.hydraTint)
                Text(result.summary)
                    .font(.title3.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("trendsSummary")
            }
            .hydraCard(padding: 20)

            ForEach(result.insights) { insight in
                HStack(alignment: .top, spacing: 12) {
                    IconBadge(systemName: Self.symbol(for: insight.id))
                    VStack(alignment: .leading, spacing: 4) {
                        Text(insight.title).font(.headline)
                        Text(insight.text)
                            .font(.subheadline)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityIdentifier("trendsInsight-\(insight.id)")
                    }
                }
                .hydraCard()
            }

            HydraDisclosure(title: "How this was made", systemImage: "gearshape.2", identifier: "trendsProvenance") {
                Text("Wording by Muse Wonder 1.0. Every number was filled in by Hydra from your log.")
                ProvenanceLine(label: "Model", value: "\(result.provenance.provider) · \(result.provenance.model)")
                if let input = result.inputTokens, let output = result.outputTokens {
                    ProvenanceLine(label: "Tokens", value: "\(input) in · \(output) out")
                }
                if let cost = result.costUSD {
                    ProvenanceLine(label: "Cost (usage-based)", value: "$\(cost.formatted(.number.precision(.fractionLength(4))))")
                    ProvenanceLine(label: "Account", value: result.provenance.account_id)
                    Text("Final billing pending.")
                }
                ProvenanceLine(label: "Attempt", value: result.provenance.attempt_id)
                ForEach(Array(result.limitations.enumerated()), id: \.offset) { _, limitation in
                    Text("• \(limitation)")
                }
            }
            .padding(.horizontal, 4)
        }
    }

    private static func symbol(for insight: String) -> String {
        switch insight {
        case "week_over_week": "arrow.left.arrow.right"
        case "goal_progress": "target"
        case "logging_consistency": "calendar"
        case "beverage_mix": "cup.and.saucer.fill"
        case "timing": "clock"
        default: "sparkles"
        }
    }

    // MARK: - Preview and consent

    @ViewBuilder private func sendSection(_ preview: TrendPreview) -> some View {
        let facts = preview.facts
        if !preview.explainable {
            StatusBanner(text: "Log drinks in the last 14 days to see trends.", systemImage: "drop", tint: .hydraTint)
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("trendsInsufficient")
        } else {
            VStack(alignment: .leading, spacing: 10) {
                SectionTitle("What would be sent to Meta")
                VStack(alignment: .leading, spacing: 0) {
                    factRow("Last 7 days", "\(facts.last_7_days.total_ml.formatted()) mL · \(facts.last_7_days.logged_days) of 7 days logged")
                    Divider()
                    factRow("Previous 7 days", "\(facts.previous_7_days.total_ml.formatted()) mL · \(facts.previous_7_days.logged_days) of 7 days logged")
                    if let goal = facts.goal_ml, let met = facts.goal_met_days_last_7 {
                        Divider()
                        factRow("Your goal", "\(goal.formatted()) mL · reached \(met) of the last 7 days")
                    }
                    if !facts.categories.isEmpty {
                        Divider()
                        factRow("Drink mix", facts.categories.prefix(3).map { "\($0.category) \($0.share_pct)%" }.joined(separator: " · "))
                    }
                }
                .hydraCard(padding: 14)
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("trendsPreview")
                Text("Daily totals, drink types, times of day and your goal for the 14 days through \(facts.through_date). Nothing else.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
            }
            consentCard(preview)
        }
    }

    private func factRow(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.footnote).foregroundStyle(.secondary)
            Text(value).font(.body.monospacedDigit())
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private func consentCard(_ preview: TrendPreview) -> some View {
        if controller.alreadyExplained {
            StatusBanner(text: "This data was already explained. Showing the saved result; nothing new is sent or charged.",
                         systemImage: "checkmark.seal", tint: .green)
        } else if preview.live_available, let account = preview.account_id {
            VStack(alignment: .leading, spacing: HydraSpacing.item) {
                Toggle("Send this summary to Meta's Muse Wonder", isOn: $consent)
                    .font(.body.weight(.medium))
                    .accessibilityIdentifier("trendsConsent")
                Button {
                    explain()
                } label: {
                    HStack {
                        if controller.explaining { ProgressView().tint(.white) }
                        Label("Explain my trends", systemImage: "sparkles")
                    }
                    .font(.body.weight(.semibold))
                    .frame(maxWidth: .infinity, minHeight: 30)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!consent || !connected || controller.explaining)
                .accessibilityIdentifier("trendsExplain")
                if let worst = preview.worst_case_micro_usd {
                    Text("One request, charged to \(account). Worst case \(HydraFormat.usd(micro: Double(worst))). Never retried automatically.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .hydraCard()
        } else {
            StatusBanner(text: "Live Muse Wonder isn't set up on this backend. Saved explanations still appear here.",
                         systemImage: "info.circle", tint: .secondary)
        }
    }

    private func reload() {
        guard connected, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
        consent = false
        task?.cancel()
        task = Task { await controller.load(service: service) }
    }

    private func explain() {
        guard consent, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
        consent = false
        task = Task { await controller.explain(service: service) }
    }
}
