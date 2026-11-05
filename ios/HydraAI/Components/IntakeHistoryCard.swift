import SwiftUI

/// Historical coverage belongs beside the drink history, away from today’s logging actions.
struct IntakeHistoryCard: View {
    @EnvironmentObject private var store: BeverageStore
    @EnvironmentObject private var units: DisplayUnits
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Previous 7 days")
            VStack(alignment: .leading, spacing: 8) {
                if let history = store.intakeHistory?.historicalLoggedIntake {
                    if let lower = history.beverageLowerMl, let upper = history.beverageUpperMl {
                        HStack(alignment: .firstTextBaseline, spacing: 4) {
                            Text(units.range(lower, upper))
                                .font(.title2.bold().monospacedDigit())
                            Text("on days you logged").font(.subheadline).foregroundStyle(.secondary)
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
