import SwiftUI

struct WonderReadinessSection: View {
    @EnvironmentObject private var store: BeverageStore
    @StateObject private var controller = WonderReadinessController()
    var body: some View {
        Section {
            Button("Check live Wonder availability") {
                guard !store.isOffline, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
                Task { await controller.load(service: service) }
            }
            .disabled(store.isOffline || !store.isConfigured || controller.state == .loading)
            .accessibilityIdentifier("checkWonderReadiness")
            if controller.state == .loading { ProgressView("Checking backend availability…") }
            if case .failed(let message) = controller.state {
                Text(message).font(.footnote).foregroundStyle(.secondary).accessibilityIdentifier("wonderReadinessError")
            }
            if let readiness = controller.result {
                Text(readiness.statusText).font(.subheadline.weight(.semibold))
                    .accessibilityIdentifier("wonderReadinessStatus")
                if readiness.policy == "owner_accepted_risk" {
                    Text("Provider extras and final billing remain unverified. The displayed cap covers tokens only; backend rules still apply.")
                        .font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("wonderReadinessRisk")
                }
                ForEach(readiness.blocked_reasons) { reason in
                    Text(reason.message).font(.footnote)
                        .accessibilityIdentifier("wonderReadinessReason-\(reason.rawValue)")
                }
            }
        } header: {
            Text("Muse Wonder availability")
        } footer: {
            Text("This check makes no Meta request or financial change. Each new analysis still needs its exact facts previewed and consented to.")
        }
        .onChange(of: store.configurationGeneration) { _, _ in controller.invalidate() }
        .onDisappear { controller.invalidate() }
    }
}
