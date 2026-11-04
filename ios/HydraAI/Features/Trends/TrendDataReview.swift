import SwiftUI

/// A separate review owns its default-off consent. Opening it never starts inference.
struct TrendDataReview: View {
    let preview: TrendPreview
    @ObservedObject var controller: WonderTrendsController
    let connected: Bool
    let explain: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var consent = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: HydraSpacing.section) {
                Text("What would be sent to Meta").font(.title3.bold())
                Text("Your drink-log summary for the 14 days through \(preview.facts.through_date). No individual health records or photos.")
                    .font(.subheadline).foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 12) {
                    week("Last 7 days", preview.facts.last_7_days)
                    Divider()
                    week("Previous 7 days", preview.facts.previous_7_days)
                    HydraDisclosure(title: "View the complete summary", identifier: "trendsCompletePayload") {
                        completeSummary
                    }
                }
                .hydraCard()
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("trendsPreview")
                sendControls
                if case .failed(let message) = controller.state { StatusBanner(text: message) }
            }
            .hydraScreen()
        }
        .hydraReadableScrollEdges()
        .background(Color.hydraBackground)
        .navigationTitle("Review your data")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Close") { dismiss() }.accessibilityIdentifier("closeTrendsReview")
            }
        }
        .onChange(of: controller.alreadyExplained) { _, explained in if explained { dismiss() } }
        .onDisappear { consent = false }
    }

    private func week(_ label: String, _ week: TrendFacts.Week) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.subheadline).foregroundStyle(.secondary)
            Text("\(week.total_ml.formatted()) mL logged").font(.headline.monospacedDigit())
            Text("\(week.logged_days) of 7 days with logs").font(.subheadline)
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private var sendControls: some View {
        if controller.alreadyExplained {
            InfoNote("This summary already has a saved explanation. Nothing new will be sent.")
        } else if preview.live_available, let account = preview.account_id, let worst = preview.worst_case_micro_usd {
            VStack(alignment: .leading, spacing: 14) {
                Text("One request to Meta's Muse Wonder") .font(.headline)
                Text("Up to \(HydraFormat.usd(micro: Double(worst))) · \(account)")
                    .font(.subheadline).fixedSize(horizontal: false, vertical: true)
                Toggle("I agree to send this summary to Meta", isOn: $consent)
                    .disabled(controller.explaining)
                    .accessibilityIdentifier("trendsConsent")
                Button {
                    guard consent, connected, !controller.explaining else { return }
                    consent = false
                    explain()
                } label: {
                    HStack {
                        if controller.explaining { ProgressView().tint(.white) }
                        Label("Explain my trends", systemImage: "sparkles")
                    }
                    .frame(maxWidth: .infinity, minHeight: 30)
                }
                .buttonStyle(.borderedProminent).controlSize(.large)
                .disabled(!consent || !connected || controller.explaining)
                .accessibilityIdentifier("trendsExplain")
                Text("Never retried automatically.").font(.caption).foregroundStyle(.secondary)
            }
            .hydraCard()
        } else {
            InfoNote("Live Muse explanations aren't available on this connection. Nothing will be sent.")
        }
    }

    private var completeSummary: some View {
        let facts = preview.facts
        return VStack(alignment: .leading, spacing: 12) {
            Text("Daily totals & drink counts").font(.headline)
            ForEach(facts.days, id: \.date) { day in
                LabeledContent(day.date, value: "\(day.total_ml.formatted()) mL · \(day.drinks) drinks logged")
            }
            Text("Days without logs are unknown, not zero intake.")
            Divider()
            LabeledContent("Window", value: "\(facts.window_days) days through \(facts.through_date)")
            LabeledContent("Timezone", value: facts.timezone)
            LabeledContent("Last week's daily average logged", value: "\(facts.last_7_days.average_ml.formatted()) mL")
            LabeledContent("Previous week's daily average logged", value: "\(facts.previous_7_days.average_ml.formatted()) mL")
            if let change = facts.change_pct { LabeledContent("Logged volume change", value: "\(change)%") }
            if let goal = facts.goal_ml { LabeledContent("Your goal", value: "\(goal.formatted()) mL") }
            if let met = facts.goal_met_days_last_7 { LabeledContent("Days goal reached last week", value: met.formatted()) }
            Text("Every drink category").font(.headline)
            ForEach(facts.categories, id: \.category) { category in
                LabeledContent(category.category.replacingOccurrences(of: "_", with: " ").capitalized, value: "\(category.total_ml.formatted()) mL · \(category.share_pct)%")
            }
            LabeledContent("Other categories", value: "\(facts.other_categories_ml.formatted()) mL")
            Text("Time of day").font(.headline)
            LabeledContent("Morning", value: "\(facts.time_of_day_ml.morning_ml.formatted()) mL")
            LabeledContent("Afternoon", value: "\(facts.time_of_day_ml.afternoon_ml.formatted()) mL")
            LabeledContent("Evening", value: "\(facts.time_of_day_ml.evening_ml.formatted()) mL")
            LabeledContent("Night", value: "\(facts.time_of_day_ml.night_ml.formatted()) mL")
            DisclosureGroup("Exact data payload") {
                Text(payload).font(.caption.monospaced())
                    .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var payload: String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return (try? encoder.encode(preview.facts)).flatMap { String(data: $0, encoding: .utf8) } ?? "Summary unavailable."
    }
}
