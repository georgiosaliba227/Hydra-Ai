import SwiftUI

struct HistoryView: View {
    @EnvironmentObject private var store: BeverageStore
    @State private var editing: BeverageLog?
    @State private var pendingDeletion: BeverageLog?
    @State private var actionError: String?

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
            if let actionError {
                Text(actionError).foregroundStyle(.red).accessibilityIdentifier("historyActionError")
            }
            Section {
                WeeklyVolumeView(logs: store.logs)
                    .listRowInsets(EdgeInsets(top: 12, leading: 16, bottom: 12, trailing: 16))
            }

            if days.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Image(systemName: "clock.arrow.circlepath").accessibilityHidden(true)
                        Text("No beverage history").fixedSize(horizontal: false, vertical: true)
                    }
                    .font(.headline)
                    Text("Confirmed beverages will appear here.")
                        .font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            ForEach(days, id: \.self) { day in
                let dayLogs = logs(on: day)
                Section {
                    ForEach(dayLogs) { log in
                        BeverageRow(log: log)
                            .swipeActions(edge: .trailing) {
                                Button("Delete", role: .destructive) { pendingDeletion = log }
                                    .disabled(!store.canLog)
                                Button("Edit") { actionError = nil; editing = log }
                                    .disabled(!store.canLog)
                            }
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
        .sheet(item: $editing) { log in
            NavigationStack { EditBeverageView(log: log) }
        }
        .confirmationDialog("Delete this beverage?", isPresented: Binding(
            get: { pendingDeletion != nil }, set: { if !$0 { pendingDeletion = nil } }
        ), titleVisibility: .visible, presenting: pendingDeletion) { log in
            Button("Delete \(log.consumedMl.formatted()) mL \(log.category)", role: .destructive) {
                Task { await delete(log) }
            }
        } message: { _ in
            Text("It is removed from history and daily totals. Its details are erased from the backend.")
        }
        .navigationTitle("History")
        .task {
            await store.refresh()
        }
    }

    @MainActor
    private func delete(_ log: BeverageLog) async {
        actionError = nil
        do {
            try await store.delete(log)
        } catch {
            actionError = "Could not delete the beverage. \(error.localizedDescription)"
        }
    }
}
