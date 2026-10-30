import SwiftUI

/// Hub for the AI features, so they are one tap from the tab bar instead of buried under Today.
struct InsightsView: View {
    @EnvironmentObject private var store: BeverageStore

    private var connected: Bool { store.isConfigured && !store.isOffline }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: HydraSpacing.section) {
                Text("Powered by Meta's Muse Wonder and Hydra's own models. You always see what would be sent before anything leaves your backend.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                if !connected {
                    StatusBanner(text: "Insights need your backend. Connect in Settings.",
                                 systemImage: "link", tint: .hydraTint)
                }

                card(destination: TrendsView(), identifier: "insightsTrends",
                     title: "Your trends", systemImage: "chart.line.uptrend.xyaxis", badge: "Meta AI",
                     text: "A plain-language read of your last 14 days: how this week compares, your drink mix and timing.",
                     points: ["Preview exactly what's sent", "Sent only after you agree"])

                card(destination: WorkoutForecastView(), identifier: "insightsWorkout",
                     title: "Plan a workout", systemImage: "figure.run", badge: nil,
                     text: "Estimate how much fluid you might lose as sweat during a planned workout.",
                     points: ["Try it with a simulated workout", "Runs on your backend, not Meta"])

                card(destination: AssistantView(), identifier: "insightsAsk",
                     title: "Ask Hydra", systemImage: "bubble.left.and.text.bubble.right", badge: nil,
                     text: "Quick answers to common drink questions, like whether coffee counts.",
                     points: ["Reviewed answers with sources", "Questions stay on your backend"])

                NavigationLink { HealthActivityPermissionView() } label: {
                    FeatureRow(title: "Apple Health", subtitle: "Today's steps, read on this iPhone only",
                               systemImage: "heart.text.square")
                }
                .buttonStyle(.plain)
                .hydraCard(padding: 12)
                .accessibilityIdentifier("insightsHealth")

                InfoNote("Wellness information, not medical advice. Hydra never diagnoses dehydration or tells you how much to drink.",
                         systemImage: "heart.circle")
                    .padding(.horizontal, 4)
            }
            .hydraScreen()
        }
        .background(Color.hydraBackground)
        .navigationTitle("Insights")
    }

    private func card<Destination: View>(destination: Destination, identifier: String, title: String,
                                         systemImage: String, badge: String?, text: String, points: [String]) -> some View {
        NavigationLink { destination } label: {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    IconBadge(systemName: systemImage)
                    Text(title).font(.title3.bold()).foregroundStyle(.primary)
                    if let badge {
                        Text(badge)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Color.hydraTint)
                            .padding(.horizontal, 8).padding(.vertical, 3)
                            .background(Color.hydraTint.opacity(0.12), in: Capsule())
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(.tertiary)
                        .accessibilityHidden(true)
                }
                Text(text)
                    .font(.subheadline)
                    .foregroundStyle(.primary)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(points, id: \.self) { point in
                        Label(point, systemImage: "checkmark")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .hydraCard()
            .contentShape(Rectangle())
            .accessibilityElement(children: .combine)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(identifier)
    }
}
