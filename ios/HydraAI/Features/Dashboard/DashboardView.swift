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
                } else {
                    StatusBanner(text: "Today's total appears once your drinks have loaded.",
                                 systemImage: "hourglass", tint: .secondary)
                }
                QuickAddCard(showingManualLog: $showingManualLog)
                insightsSection
                recentSection
                weekSection
            }
            .hydraScreen()
        }
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
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Insights")
            VStack(spacing: 0) {
                NavigationLink { TrendsView() } label: {
                    FeatureRow(title: "Your trends", subtitle: "Meta AI explains your last 14 days",
                               systemImage: "chart.line.uptrend.xyaxis")
                }
                .accessibilityIdentifier("wonderTrends")
                Divider().padding(.leading, 50)
                NavigationLink { WorkoutForecastView() } label: {
                    FeatureRow(title: "Plan a workout", subtitle: "Estimate sweat loss for a planned session",
                               systemImage: "figure.run")
                }
                .accessibilityIdentifier("workoutForecast")
                Divider().padding(.leading, 50)
                NavigationLink { AssistantView() } label: {
                    FeatureRow(title: "Ask Hydra", subtitle: "Reviewed answers with sources",
                               systemImage: "bubble.left.and.text.bubble.right")
                }
                .accessibilityIdentifier("askAssistant")
            }
            .buttonStyle(.plain)
            .hydraCard(padding: 12)
        }
    }

    private var recentSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Today's drinks", trailing: todaysLogs.isEmpty ? nil : "\(todaysLogs.count) logged")
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

    private var weekSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Previous 7 days")
            VStack(alignment: .leading, spacing: 8) {
                if let history = store.intakeHistory?.historicalLoggedIntake {
                    if let lower = history.beverageLowerMl, let upper = history.beverageUpperMl {
                        HStack(alignment: .firstTextBaseline, spacing: 4) {
                            Text("\(HydraFormat.milliliters(lower))–\(HydraFormat.milliliters(upper))")
                                .font(.title2.bold().monospacedDigit())
                            Text("mL on days you logged").font(.subheadline).foregroundStyle(.secondary)
                        }
                        .accessibilityElement(children: .combine)
                    } else {
                        Text("No drinks logged in the previous 7 days.").font(.subheadline)
                    }
                    Text("\(history.loggedDays) days with logs · \(history.daysWithoutLogs) without")
                        .font(.subheadline)
                        .accessibilityIdentifier("historyCoverage")
                    InfoNote("Days without logs are unknown, not zero.")
                } else if case .loading = store.intakeHistoryState {
                    ProgressView().frame(maxWidth: .infinity, alignment: .leading)
                } else if case .failed(let message) = store.intakeHistoryState {
                    Text(message).font(.subheadline).foregroundStyle(.secondary)
                } else {
                    Text(store.isOffline ? "Connect to your backend to see past days." : "Pull down to refresh past days.")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
            }
            .hydraCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("intakeHistoryCard")

            Text("Hydra shows the drinks you log. It doesn't measure hydration or set a daily requirement — any goal is one you choose.")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 4)
                .accessibilityIdentifier("dailyRequirementUnavailable")
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
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
                    ForEach(presets) { preset in
                        Button { Task { await add(preset) } } label: {
                            HStack(spacing: 10) {
                                Image(systemName: BeverageStyle.symbol(for: preset.category))
                                    .foregroundStyle(Color.hydraTint)
                                    .accessibilityHidden(true)
                                VStack(alignment: .leading, spacing: 0) {
                                    Text(preset.label).font(.subheadline.weight(.semibold)).foregroundStyle(.primary)
                                    Text("\(preset.volumeMl) mL").font(.footnote).foregroundStyle(.secondary)
                                }
                                Spacer(minLength: 0)
                                Image(systemName: "plus").font(.footnote.bold()).foregroundStyle(Color.hydraTint)
                                    .accessibilityHidden(true)
                            }
                            .padding(.horizontal, 12)
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
