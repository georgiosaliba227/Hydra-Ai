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

                VStack(alignment: .leading, spacing: 12) {
                    Text("Recent today")
                        .font(.title3.bold())

                    if todaysLogs.isEmpty {
                        ContentUnavailableView(
                            "No beverages logged today",
                            systemImage: "drop",
                            description: Text("Add a beverage after you have consumed it.")
                        )
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
