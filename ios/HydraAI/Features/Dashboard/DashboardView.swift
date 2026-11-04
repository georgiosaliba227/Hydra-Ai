import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var store: BeverageStore
    @State private var showingManualLog = false

    private var todaysLogs: [BeverageLog] {
        store.logs
            .filter { Calendar.current.isDateInToday($0.consumedAt) }
            .sorted { $0.consumedAt > $1.consumedAt }
    }

    private var todayVolumeMl: Int {
        guard let value = store.summary?.beverageTotalMl, value < Double(Int.max) else { return 0 }
        return Int(value)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: HydraSpacing.section) {
                statusBanners
                if store.summary != nil {
                    TodayProgressCard(volumeMl: todayVolumeMl, goal: store.summary?.goal)
                    if store.summary?.goal == nil && !store.configuration.offline {
                        NavigationLink {
                            GuidedGoalSetupView(profileStore: store.goalProfiles)
                        } label: { Label("Set up your daily goal", systemImage: "target") }
                            .accessibilityIdentifier("todayGoalSetup")
                    }
                } else {
                    StatusBanner(text: "Today's total appears once your drinks have loaded.",
                                 systemImage: "hourglass", tint: .secondary)
                }
                QuickAddCard(showingManualLog: $showingManualLog)
                recentSection
                insightsSection
            }
            .hydraScreen()
        }
        .hydraReadableScrollEdges()
        .background(Color.hydraBackground)
        .refreshable { await store.refresh() }
        .navigationTitle("Today")
        .sheet(isPresented: $showingManualLog) {
            NavigationStack {
                ManualLogView()
            }
        }
        .task {
            await store.refresh()
        }
    }

    // MARK: - Sections

    @ViewBuilder private var statusBanners: some View {
        if !store.isConfigured {
            StatusBanner(text: "Connect to your backend in Settings, or choose the offline demo there.",
                         systemImage: "link", tint: .hydraTint)
        }
        if case .failed(let message) = store.state {
            StatusBanner(text: message) {
                Button("Refresh") { Task { await store.refresh() } }
                    .buttonStyle(.bordered)
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("connectionError")
        }
        if let pending = store.pending {
            StatusBanner(text: "Waiting to confirm \(pending.request.consumedMl) mL \(pending.request.category). Nothing is lost; retry when you're back online.",
                         systemImage: "clock.badge.exclamationmark") {
                Button("Retry pending beverage") {
                    Task { try? await store.retryPending() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(store.isSaving)
                .accessibilityIdentifier("retryPending")
            }
        }
    }

    private var insightsSection: some View {
        NavigationLink { InsightsView() } label: {
            FeatureRow(title: "Explore insights", subtitle: "Trends, workouts and drink questions", systemImage: "sparkles")
        }
        .buttonStyle(.plain)
        .hydraCard(padding: 12)
        .accessibilityIdentifier("exploreInsights")
    }

    private var recentSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Today's drinks")
            VStack(alignment: .leading, spacing: 0) {
                if todaysLogs.isEmpty {
                    Label {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Nothing logged yet today").font(.headline)
                            Text("Add a drink after you've had it.")
                                .font(.subheadline).foregroundStyle(.secondary)
                        }
                    } icon: {
                        Image(systemName: "drop").foregroundStyle(Color.hydraTint)
                    }
                } else {
                    let recent = Array(todaysLogs.prefix(5))
                    ForEach(recent) { log in
                        BeverageRow(log: log)
                            .padding(.vertical, 8)
                        if log.id != recent.last?.id {
                            Divider().padding(.leading, 48)
                        }
                    }
                    if todaysLogs.count > 5 {
                        Text("See every drink in History.")
                            .font(.footnote).foregroundStyle(.secondary).padding(.top, 8)
                    }
                }
            }
            .hydraCard()
        }
    }


}

// MARK: - Progress

/// Today's logged total, with a ring only when the user has chosen a goal.
private struct TodayProgressCard: View {
    let volumeMl: Int
    let goal: DailySummary.Goal?
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .largeTitle) private var ringSize: CGFloat = 128
    @ScaledMetric(relativeTo: .largeTitle) private var numberSize: CGFloat = 32

    private var validGoal: DailySummary.Goal? { goal.flatMap { $0.isValid ? $0 : nil } }
    private var visibleProgress: Double { min(max(validGoal?.progressRatio ?? 0, 0), 1) }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(Date.now.formatted(.dateTime.weekday(.wide).month().day()))
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.secondary)
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 16) { ring; details }
            } else {
                HStack(spacing: 20) { ring; details }
            }
            InfoNote("Drink volume you logged — not a measure of hydration.")
        }
        .hydraCard(padding: 20)
    }

    private var ring: some View {
        ZStack {
            // Water rises inside the outline using the user's existing goal.
            // Keep it translucent so the logged amount remains readable.
            Circle()
                .fill(Color.hydraTint.opacity(0.24))
                .mask(alignment: .bottom) {
                    Rectangle().frame(height: max(0, ringSize - 14) * visibleProgress)
                }
                .padding(7)
                .animation(.snappy, value: visibleProgress)
            Circle().stroke(Color.hydraTint.opacity(0.15), lineWidth: 14)
            if let validGoal {
                Circle()
                    .trim(from: 0, to: min(validGoal.progressRatio, 1))
                    .stroke(Color.hydraTint, style: StrokeStyle(lineWidth: 14, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .animation(.snappy, value: validGoal.progressRatio)
            }
            VStack(spacing: 0) {
                Text(volumeMl.formatted())
                    .font(.system(size: numberSize, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .contentTransition(.numericText())
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Text("mL").font(.subheadline.weight(.medium)).foregroundStyle(.secondary)
            }
            .padding(18)
        }
        .frame(width: ringSize, height: ringSize)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Logged today, \(volumeMl.formatted()) milliliters")
        .accessibilityValue(String(volumeMl))
        .accessibilityIdentifier("dailyTotal")
    }

    @ViewBuilder private var details: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Logged today").font(.headline)
            if let validGoal {
                let percent = Int((min(validGoal.progressRatio, 9.99) * 100).rounded())
                VStack(alignment: .leading, spacing: 4) {
                    Text(validGoal.progressRatio >= 1 ? "Goal reached" : "\(percent)% of your goal")
                        .font(.title3.bold())
                        .foregroundStyle(Color.hydraTint)
                    Text("\(volumeMl.formatted()) of \(validGoal.dailyBeverageGoalMl.formatted()) mL · your own goal")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("goalProgress")
                Text("A goal you set, not a recommendation.")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                Text("No goal set").font(.title3.bold())
                Text("You can choose your own goal in Settings.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - Quick add

/// One tap logs a common drink through the same confirmed store path as the full form.
private struct QuickAddCard: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @EnvironmentObject private var store: BeverageStore
    @Binding var showingManualLog: Bool
    @State private var confirmation: String?
    @State private var errorMessage: String?
    @State private var savedCount = 0
    @State private var hideTask: Task<Void, Never>?

    private struct Preset: Identifiable {
        let label: String
        let category: String
        let volumeMl: Int
        var id: String { "\(category)-\(volumeMl)" }
    }

    private let presets = [
        Preset(label: "Water", category: "water", volumeMl: 250),
        Preset(label: "Water", category: "water", volumeMl: 500),
        Preset(label: "Coffee", category: "coffee", volumeMl: 250),
        Preset(label: "Tea", category: "tea", volumeMl: 250),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Log a drink")
            VStack(alignment: .leading, spacing: HydraSpacing.item) {
                LazyVGrid(columns: dynamicTypeSize.isAccessibilitySize ? [GridItem(.flexible())] : [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
                    ForEach(presets) { preset in
                        Button { Task { await add(preset) } } label: {
                            HStack(spacing: 10) {
                                Image(systemName: BeverageStyle.symbol(for: preset.category))
                                    .foregroundStyle(Color.hydraTint)
                                    .accessibilityHidden(true)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(preset.label).font(.subheadline.weight(.semibold)).foregroundStyle(.primary)
                                        .fixedSize()
                                    Text("\(preset.volumeMl) mL").font(.footnote).foregroundStyle(.secondary)
                                        .fixedSize()
                                }
                                .accessibilityHidden(true)
                                Spacer(minLength: 0)
                                Image(systemName: "plus").font(.footnote.bold()).foregroundStyle(Color.hydraTint)
                                    .accessibilityHidden(true)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
                            .background(Color.hydraTint.opacity(0.10), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .disabled(!store.canLog)
                        .opacity(store.canLog ? 1 : 0.5)
                        .accessibilityLabel("Add \(preset.volumeMl) milliliters of \(preset.label.lowercased())")
                        .accessibilityHint("Logs it now as a drink you've had")
                        .accessibilityIdentifier("quickAdd-\(preset.id)")
                    }
                }

                Button {
                    showingManualLog = true
                } label: {
                    Label("Log another drink", systemImage: "plus.circle.fill")
                        .font(.body.weight(.semibold))
                        .frame(maxWidth: .infinity, minHeight: 30)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!store.canLog)
                .accessibilityIdentifier("logBeverage")

                if let confirmation {
                    Label(confirmation, systemImage: "checkmark.circle.fill")
                        .font(.subheadline)
                        .foregroundStyle(.green)
                        .transition(.opacity)
                        .accessibilityIdentifier("quickAddConfirmation")
                }
                if let errorMessage {
                    Text(errorMessage)
                        .font(.subheadline)
                        .foregroundStyle(.red)
                        .accessibilityAddTraits(.updatesFrequently)
                }
                Text("Tap only after you've had the drink. Each tap adds one entry you can edit in History.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .hydraCard()
        }
        .sensoryFeedback(.success, trigger: savedCount)
    }

    @MainActor
    private func add(_ preset: Preset) async {
        errorMessage = nil
        do {
            try await store.add(category: preset.category, consumedMl: preset.volumeMl, at: .now)
            savedCount += 1
            withAnimation { confirmation = "Added \(preset.volumeMl) mL \(preset.label.lowercased())" }
            UIAccessibility.post(notification: .announcement, argument: confirmation)
            hideTask?.cancel()
            hideTask = Task {
                try? await Task.sleep(for: .seconds(3))
                guard !Task.isCancelled else { return }
                withAnimation { confirmation = nil }
            }
        } catch {
            confirmation = nil
            errorMessage = "Couldn't add it. \(error.localizedDescription) If it's waiting to confirm, use Retry above."
        }
    }
}
