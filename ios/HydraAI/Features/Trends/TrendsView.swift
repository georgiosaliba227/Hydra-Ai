import SwiftUI

/// Muse Wonder explains the user's own 14-day trends. The exact data is shown before anything is sent.
struct TrendsView: View {
    @EnvironmentObject private var store: BeverageStore
    @StateObject private var controller = WonderTrendsController()
    @State private var consent = false
    @State private var task: Task<Void, Never>?

    private var connected: Bool { store.isConfigured && !store.isOffline }

    var body: some View {
        Form {
            Section {
                Text("Muse Wonder 1.0 explains patterns in your last 14 days. Wonder picks what matters and writes the wording; Hydra fills in every number from your log and rejects advice or medical claims. Wellness information, not medical advice.")
                    .font(.footnote)
                if !connected { Text("Connect to your local backend in Settings to see trends.") }
            }
            if controller.state == .loading { Section { ProgressView() } }
            if case .failed(let message) = controller.state {
                Section { Text(message).foregroundStyle(.secondary).accessibilityIdentifier("trendsError") }
            }
            if let result = controller.result { resultSections(result) }
            if let preview = controller.preview { sendSections(preview) }
        }
        .navigationTitle("Your trends")
        .task { reload() }
        .onChange(of: store.configurationGeneration) { _, _ in reload() }
        .onDisappear { task?.cancel(); task = nil; controller.invalidate() }
    }

    @ViewBuilder private func resultSections(_ result: WonderTrends) -> some View {
        Section {
            Text(result.summary).font(.headline).accessibilityIdentifier("trendsSummary")
        } header: {
            Text("Muse Wonder 1.0")
        } footer: {
            Text("Based on your log through \(result.facts.through_date).")
        }
        ForEach(result.insights) { insight in
            Section(insight.title) {
                Text(insight.text).accessibilityIdentifier("trendsInsight-\(insight.id)")
            }
        }
        Section("How this was made") {
            Text("Wording by Muse Wonder 1.0. Every number was filled in by Hydra from your log.").font(.caption)
            if let input = result.inputTokens, let output = result.outputTokens {
                Text("\(input) input · \(output) output tokens").font(.caption)
            }
            if let cost = result.costUSD {
                Text("Usage-derived cost $\(cost.formatted(.number.precision(.fractionLength(4)))) on \(result.provenance.account_id); final billing pending.")
                    .font(.caption)
            }
            Text("Attempt \(result.provenance.attempt_id)").font(.caption2)
            ForEach(Array(result.limitations.enumerated()), id: \.offset) { _, limitation in
                Text(limitation).font(.footnote)
            }
        }
        .accessibilityIdentifier("trendsProvenance")
    }

    @ViewBuilder private func sendSections(_ preview: TrendPreview) -> some View {
        let facts = preview.facts
        if !preview.explainable {
            Section { Text("Log drinks in the last 14 days to see trends.").accessibilityIdentifier("trendsInsufficient") }
        } else {
            Section {
                Text("Last 7 days: \(facts.last_7_days.total_ml) mL on \(facts.last_7_days.logged_days) of 7 days")
                Text("Previous 7 days: \(facts.previous_7_days.total_ml) mL on \(facts.previous_7_days.logged_days) of 7 days")
                if let goal = facts.goal_ml, let met = facts.goal_met_days_last_7 {
                    Text("Your goal: \(goal) mL, reached on \(met) of the last 7 days")
                }
                if !facts.categories.isEmpty {
                    Text(facts.categories.prefix(3).map { "\($0.category) \($0.share_pct)%" }.joined(separator: " · "))
                }
            } header: {
                Text("What would be sent to Meta")
            } footer: {
                Text("Daily totals, drink types, times of day and your goal for the 14 days through \(facts.through_date). Nothing else.")
            }
            .accessibilityIdentifier("trendsPreview")
            if controller.alreadyExplained {
                Section { Text("This data was already explained. Showing the saved result; nothing new is sent or charged.").font(.footnote) }
            } else if preview.live_available, let account = preview.account_id {
                Section {
                    Toggle("Send this summary to Meta's Muse Wonder", isOn: $consent)
                        .accessibilityIdentifier("trendsConsent")
                    Button("Explain my trends") { explain() }
                        .disabled(!consent || !connected || controller.explaining)
                        .accessibilityIdentifier("trendsExplain")
                    if controller.explaining { ProgressView() }
                } footer: {
                    if let worst = preview.worst_case_micro_usd {
                        Text("One request, charged to \(account). Worst case $\((Double(worst) / 1_000_000).formatted(.number.precision(.fractionLength(4)))). Never retried automatically.")
                    }
                }
            } else {
                Section { Text("Live Muse Wonder isn't set up on this backend. Saved explanations still appear here.").font(.footnote) }
            }
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
