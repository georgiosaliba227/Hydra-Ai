import SwiftUI

/// Muse Wonder explains the user's own 14-day trends. The exact data is shown before anything is sent.
struct TrendsView: View {
    @EnvironmentObject private var store: BeverageStore
    @StateObject private var controller = WonderTrendsController()
    @State private var showingReview = false
    @State private var task: Task<Void, Never>?

    private var connected: Bool { store.isConfigured && !store.isOffline }

    var body: some View {
        Group {
            if store.isOnDevice { DeviceTrendsView() }
            else { serverBody }
        }
    }

    private var serverBody: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: HydraSpacing.section) {
                    if controller.result == nil { intro }
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
                    if controller.explaining { ProgressView("Writing your explanation…") }
                    if let preview = controller.preview {
                        if preview.explainable {
                            Button { showingReview = true } label: {
                                Label(controller.alreadyExplained ? "Review data" : "Review data & explain", systemImage: "sparkles")
                                    .frame(maxWidth: .infinity, minHeight: 30)
                            }
                            .buttonStyle(.borderedProminent).controlSize(.large)
                            .disabled(controller.explaining)
                            .accessibilityIdentifier("reviewTrendsData")
                        } else {
                            ContentUnavailableView("Start with a drink", systemImage: "drop",
                                description: Text("Log drinks to see patterns from your last 14 days."))
                                .accessibilityIdentifier("trendsInsufficient")
                        }
                    }
                    InfoNote("Your drink log describes what you drank. It does not measure hydration.",
                             systemImage: "heart.circle")
                        .padding(.horizontal, 4)
                }
                .hydraScreen()
                .id("trendsTop")
            }
            .onChange(of: controller.result?.payload_sha256) { _, digest in
                if digest != nil { proxy.scrollTo("trendsTop", anchor: .top) }
            }
        }
        .hydraReadableScrollEdges()
        .background(Color.hydraBackground)
        .navigationTitle("Your trends")
        .task { reload() }
        .onChange(of: store.configurationGeneration) { _, _ in showingReview = false; reload() }
        .onDisappear { showingReview = false; task?.cancel(); task = nil; controller.invalidate() }
        .sheet(isPresented: $showingReview) {
            if let preview = controller.preview {
                NavigationStack {
                    TrendDataReview(preview: preview, controller: controller, connected: connected, explain: explain)
                }
            }
        }
    }

    private var intro: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Your last 14 days").font(.title2.bold())
            Text("Muse AI explains patterns in your drink log. Review your summary before choosing to share it.")
                .font(.subheadline).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Result

    @ViewBuilder private func resultSection(_ result: WonderTrends) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("14 days through \(result.facts.through_date)").font(.subheadline).foregroundStyle(.secondary)
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

            if let first = result.insights.first { insightCard(first) }
            if result.insights.count > 1 {
                HydraDisclosure(title: "More insights", systemImage: "sparkles", identifier: "trendsMoreInsights") {
                    ForEach(Array(result.insights.dropFirst())) { insight in insightCard(insight) }
                }
            }

            HydraDisclosure(title: "Sources & details", systemImage: "gearshape.2", identifier: "trendsProvenance") {
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

    private func insightCard(_ insight: WonderTrends.Insight) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(insight.title, systemImage: Self.symbol(for: insight.id))
                .font(.headline).foregroundStyle(Color.hydraTint)
            Text(insight.text).font(.body)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("trendsInsight-\(insight.id)")
        }
        .hydraCard()
    }

    private func reload() {
        task?.cancel(); task = nil; controller.invalidate()
        guard connected, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
        task = Task { await controller.load(service: service) }
    }

    private func explain() {
        guard connected, !controller.explaining, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
        task = Task { await controller.explain(service: service) }
    }
}
