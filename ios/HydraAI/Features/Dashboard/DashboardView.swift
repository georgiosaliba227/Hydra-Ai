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

    private var historyCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Previous 7 days").font(.headline)
            if let history = store.intakeHistory?.historicalLoggedIntake {
                if let lower = history.beverageLowerMl, let upper = history.beverageUpperMl {
                    Text("Logged-day range: \(lower.formatted(.number.precision(.fractionLength(0...1))))–\(upper.formatted(.number.precision(.fractionLength(0...1)))) mL")
                } else {
                    Text("No beverages logged in the previous 7 days.")
                }
                Text("\(history.loggedDays) days with logs · \(history.daysWithoutLogs) days without logs")
                    .accessibilityIdentifier("historyCoverage")
                Text("Logs may be incomplete. Days without logs are unknown, not measured zero intake.")
            } else if case .loading = store.intakeHistoryState {
                Text("Loading logged-intake history…")
            } else if case .failed(let message) = store.intakeHistoryState {
                Text(message)
            } else {
                Text(store.isOffline ? "Connect to your backend to view logged-intake history." : "Logged-intake history is unavailable until refreshed.")
            }
            Text("Daily hydration requirement unavailable. Logged amounts are descriptive and are not a drinking target.")
                .accessibilityIdentifier("dailyRequirementUnavailable")
        }
        .font(.footnote)
        .foregroundStyle(.secondary)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("intakeHistoryCard")
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text(store.isOffline ? "Offline demo · local data" : "Backend · confirmed beverage accounting")
                    .font(.caption).foregroundStyle(.secondary)
                if !store.isConfigured {
                    Text("Open Settings to connect to your backend or explicitly choose the offline demo.")
                }
                if case .failed(let message) = store.state {
                    Text(message).foregroundStyle(.red).accessibilityIdentifier("connectionError")
                    Button("Refresh") { Task { await store.refresh() } }
                }
                if let pending = store.pending {
                    Text("Awaiting confirmation: \(pending.request.consumedMl) mL \(pending.request.category)")
                    Button("Retry pending beverage") {
                        Task { try? await store.retryPending() }
                    }
                    .disabled(store.isSaving).accessibilityIdentifier("retryPending")
                }
                if store.summary != nil {
                LoggedVolumeCard(
                    title: "Logged today",
                    volumeMl: todayVolumeMl,
                    detail: "Confirmed beverage volume · \(Date.now.formatted(date: .abbreviated, time: .omitted))"
                )

                .accessibilityIdentifier("dailyTotal")
                if let goal = store.summary?.goal, goal.isValid {
                    VStack(alignment: .leading, spacing: 6) {
                        ProgressView(value: min(goal.progressRatio, 1))
                        Text("\(todayVolumeMl.formatted()) of \(goal.dailyBeverageGoalMl.formatted()) mL · your own goal")
                            .font(.subheadline)
                        Text("A goal you set, not a recommendation. Change it in Settings.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityIdentifier("goalProgress")
                }
                } else {
                    Text("Daily total unavailable until loaded.")
                }

                Text("Beverage volume is different from water content or a hydration recommendation.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)

                Button {
                    showingManualLog = true
                } label: {
                    Label("Log a beverage", systemImage: "plus.circle.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!store.canLog)
                .accessibilityIdentifier("logBeverage")

                historyCard

                NavigationLink { WorkoutForecastView() } label: {
                    Label("Workout forecast · separate from intake", systemImage: "figure.run")
                }
                .accessibilityIdentifier("workoutForecast")

                NavigationLink { AssistantView() } label: {
                    Label("Ask Hydra · reviewed answers", systemImage: "questionmark.bubble")
                }
                .accessibilityIdentifier("askAssistant")

                VStack(alignment: .leading, spacing: 12) {
                    Text("Recent today")
                        .font(.title3.bold())

                    if todaysLogs.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Label("No beverages logged today", systemImage: "drop")
                                .font(.headline)
                            Text("Add a beverage after you have consumed it.")
                                .font(.subheadline)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    } else {
                        ForEach(todaysLogs.prefix(5)) { log in
                            BeverageRow(log: log)
                            if log.id != todaysLogs.prefix(5).last?.id {
                                Divider()
                            }
                        }
                    }
                }
            }
            .padding()
        }
        .refreshable { await store.refresh() }
        .navigationTitle("Hydra AI")
        .sheet(isPresented: $showingManualLog) {
            NavigationStack {
                ManualLogView()
            }
        }
        .task {
            await store.refresh()
        }
    }
}
