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
        todaysLogs.reduce(0) { $0 + $1.consumedMl }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                LoggedVolumeCard(
                    title: "Logged today",
                    volumeMl: todayVolumeMl,
                    detail: "Confirmed beverage volume · \(Date.now.formatted(date: .abbreviated, time: .omitted))"
                )

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
