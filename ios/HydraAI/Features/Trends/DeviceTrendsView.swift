import SwiftUI

/// The phone previews its own aggregates. Sending is a separate, explicit action.
struct DeviceTrendsView: View {
    @EnvironmentObject private var units: DisplayUnits
    @EnvironmentObject private var store: BeverageStore
    @State private var snapshot: DeviceTrendSnapshot?
    @State private var result: DeviceTrendSummary?
    @State private var message: String?
    @State private var loading = false
    @State private var sending = false
    @State private var generation = UUID()
    @State private var task: Task<Void, Never>?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: HydraSpacing.section) {
                Text("Your last 14 days").font(.title2.bold())
                Text("Review a summary from this iPhone's log, then send it to your Hydra backend to see patterns.")
                    .font(.subheadline).foregroundStyle(.secondary)
                if !store.hasInsightsConnection {
                    StatusBanner(text: "Connect backend features in Settings to use this summary.", systemImage: "link", tint: .hydraTint)
                    NavigationLink("Open Settings") { BackendSettingsView() }
                }
                if loading { ProgressView("Preparing your summary…") }
                if let message { StatusBanner(text: message).accessibilityIdentifier("trendsError") }
                if let snapshot {
                    preview(snapshot)
                    if result == nil {
                        Button { send(snapshot) } label: {
                            Label(sending ? "Finding patterns…" : "Send summary & show trends", systemImage: "chart.line.uptrend.xyaxis")
                                .frame(maxWidth: .infinity, minHeight: 30)
                        }
                        .buttonStyle(.borderedProminent).controlSize(.large)
                        .disabled(sending || !store.hasInsightsConnection)
                        .accessibilityIdentifier("sendDeviceTrends")
                    }
                }
                if let result {
                    VStack(alignment: .leading, spacing: 8) {
                        Label("From this iPhone's log", systemImage: "iphone").font(.caption.weight(.semibold)).foregroundStyle(Color.hydraTint)
                        Text(units.text(result.summary)).font(.title3.weight(.semibold)).accessibilityIdentifier("trendsSummary")
                    }.hydraCard()
                    ForEach(result.insights) { insight in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(insight.title).font(.headline)
                            Text(units.text(insight.text)).accessibilityIdentifier("trendsInsight-\(insight.id)")
                        }.hydraCard()
                    }
                    Text("Calculated by Hydra from the summary you shared. No AI provider was called. The backend does not save this summary.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Button("Refresh summary") { prepare() }
                    .disabled(sending || loading)
                    .accessibilityIdentifier("refreshDeviceTrends")
                InfoNote("Days without logs are unknown intake. Your drink log does not measure hydration.", systemImage: "heart.circle")
            }.hydraScreen()
        }
        .hydraReadableScrollEdges()
        .background(Color.hydraBackground)
        .navigationTitle("Your trends")
        .task(id: store.configurationGeneration) { prepare() }
        .onDisappear { task?.cancel(); task = nil; generation = UUID() }
    }

    private func preview(_ snapshot: DeviceTrendSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Summary to share").font(.headline)
            Text("14 days through \(snapshot.through_date) · \(snapshot.timezone)").font(.subheadline)
            Text("\(units.volume(snapshot.days.reduce(0) { $0 + $1.total_ml })) logged")
                .font(.title3.weight(.semibold)).accessibilityIdentifier("deviceTrendsPreviewTotal")
            if let goal = snapshot.goal_ml { Text("Current goal: \(units.volume(goal))/day") }
            Text("Includes daily totals, drink counts, drink types and totals by time of day. No drink names, photos, individual timestamps, profile or Apple Health data.")
                .font(.footnote).foregroundStyle(.secondary)
            DisclosureGroup("See daily totals") {
                ForEach(snapshot.days, id: \.date) { day in
                    LabeledContent(day.date, value: "\(units.volume(day.total_ml)) · \(day.drinks) drinks")
                        .font(.footnote)
                }
                ForEach(snapshot.categories, id: \.category) { category in
                    LabeledContent(category.category.replacingOccurrences(of: "_", with: " ").capitalized,
                                   value: "\(units.volume(category.total_ml))").font(.footnote)
                }
                LabeledContent("Morning", value: units.volume(snapshot.time_of_day_ml.morning_ml)).font(.footnote)
                LabeledContent("Afternoon", value: units.volume(snapshot.time_of_day_ml.afternoon_ml)).font(.footnote)
                LabeledContent("Evening", value: units.volume(snapshot.time_of_day_ml.evening_ml)).font(.footnote)
                LabeledContent("Night", value: units.volume(snapshot.time_of_day_ml.night_ml)).font(.footnote)
            }
        }.hydraCard()
    }

    private func prepare() {
        task?.cancel(); generation = UUID()
        let current = generation
        snapshot = nil; result = nil; message = nil; loading = true; sending = false
        task = Task { @MainActor in
            defer { if current == generation { loading = false } }
            do {
                let value = try await store.deviceTrendSnapshot()
                guard current == generation, !Task.isCancelled else { return }
                snapshot = value
            } catch {
                guard current == generation, !Task.isCancelled else { return }
                message = "Could not prepare the phone summary. \(error.localizedDescription)"
            }
        }
    }

    private func send(_ snapshot: DeviceTrendSnapshot) {
        guard !sending, let service = try? store.insightsService() else { return }
        let current = generation, connection = store.configurationGeneration
        sending = true; message = nil
        task = Task { @MainActor in
            defer { if current == generation { sending = false } }
            do {
                _ = try await service.deviceInsightsCapabilities()
                guard current == generation, connection == store.configurationGeneration, !Task.isCancelled else { return }
                let answer = try await service.deviceTrends(snapshot)
                guard current == generation, connection == store.configurationGeneration, !Task.isCancelled else { return }
                result = answer
            } catch {
                guard current == generation, connection == store.configurationGeneration, !Task.isCancelled else { return }
                message = "Trends are unavailable. Check the backend connection in Settings. Your phone log is saved."
            }
        }
    }
}
