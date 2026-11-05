import SwiftUI

/// One short description per destination; the feature explains itself when opened.
struct InsightsView: View {
    @EnvironmentObject private var store: BeverageStore
    private var connected: Bool { store.hasInsightsConnection }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: HydraSpacing.section) {
                Text("Make sense of your drinks and activity.")
                    .font(.subheadline).foregroundStyle(.secondary)
                if !connected {
                    VStack(alignment: .leading, spacing: 6) {
                        InfoNote("Connect to use insights.", systemImage: "link")
                        NavigationLink("Open Settings") { BackendSettingsView() }
                            .frame(minHeight: 44)
                    }
                }
                VStack(spacing: 0) {
                    NavigationLink { TrendsView() } label: {
                        FeatureRow(title: "Your trends", subtitle: "Patterns in your drink log",
                                   systemImage: "chart.line.uptrend.xyaxis", badge: store.isOnDevice ? nil : "Muse AI")
                    }
                    .accessibilityIdentifier("insightsTrends")
                    Divider()
                    NavigationLink { WorkoutForecastView() } label: {
                        FeatureRow(title: "Plan a workout", subtitle: "Estimate workout sweat loss", systemImage: "figure.run")
                    }
                    .accessibilityIdentifier("insightsWorkout")
                    Divider()
                    NavigationLink { AssistantView() } label: {
                        FeatureRow(title: "Ask Hydra", subtitle: "Common drink questions", systemImage: "bubble.left.and.text.bubble.right")
                    }
                    .accessibilityIdentifier("insightsAsk")
                }
                .buttonStyle(.plain).hydraCard(padding: 12)
                NavigationLink { HealthActivityPermissionView() } label: {
                    FeatureRow(title: "Apple Health", subtitle: "Activity on this iPhone", systemImage: "heart.text.square")
                }
                .buttonStyle(.plain).hydraCard(padding: 12)
                .accessibilityIdentifier("insightsHealth")
                Text("Wellness information, not medical advice.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            .hydraScreen()
        }
        .hydraReadableScrollEdges()
        .background(Color.hydraBackground)
        .navigationTitle("Insights")
    }
}
