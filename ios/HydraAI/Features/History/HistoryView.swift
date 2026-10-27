import SwiftUI

struct HistoryView: View {
    @EnvironmentObject private var store: BeverageStore

    private var sortedLogs: [BeverageLog] {
        store.logs.sorted { $0.consumedAt > $1.consumedAt }
    }

    private var days: [Date] {
        Array(Set(sortedLogs.map { Calendar.current.startOfDay(for: $0.consumedAt) })).sorted(by: >)
    }

    private func logs(on day: Date) -> [BeverageLog] {
        sortedLogs.filter { Calendar.current.isDate($0.consumedAt, inSameDayAs: day) }
    }

    var body: some View {
        List {
            if case .failed(let message) = store.state {
                Text(message).foregroundStyle(.red)
            }
            Section {
                WeeklyVolumeView(logs: store.logs)
                    .listRowInsets(EdgeInsets(top: 12, leading: 16, bottom: 12, trailing: 16))
            }

            if days.isEmpty {
                ContentUnavailableView(
                    "No beverage history",
                    systemImage: "clock.arrow.circlepath",
                    description: Text("Confirmed beverages will appear here.")
                )
            }

            ForEach(days, id: \.self) { day in
                let dayLogs = logs(on: day)
                Section {
                    ForEach(dayLogs) { log in
                        BeverageRow(log: log)
                    }
                } header: {
                    HStack {
                        Text(day, format: .dateTime.weekday(.wide).month(.abbreviated).day())
                        Spacer()
                        Text("\(dayLogs.reduce(0) { $0 + $1.consumedMl }.formatted()) mL")
                    }
                }
            }
        }
        .refreshable { await store.refresh() }
        .navigationTitle("History")
        .task {
            await store.refresh()
        }
    }
}
