import SwiftUI

/// A GET-only viewer: opening or refreshing this screen cannot invoke a model.
struct OwnerSyntheticWonderView: View {
    @EnvironmentObject private var store: BeverageStore
    @StateObject private var controller = OwnerSyntheticWonderController()
    var body: some View {
        Form {
            Section {
                Text("This demonstration uses simulated data, not your measurements or logged drinks.")
                    .accessibilityIdentifier("ownerWonderSyntheticLabel")
                Button("Load saved Wonder test") {
                    guard !store.isOffline, let service = try? HTTPBeverageService(configuration: store.configuration) else { return }
                    Task { await controller.load(service: service) }
                }
                .disabled(store.isOffline || !store.isConfigured || controller.state == .loading)
                .accessibilityIdentifier("loadOwnerWonderResult")
                if controller.state == .loading { ProgressView("Loading saved analysis…") }
                if case .failed(let message) = controller.state {
                    Text(message).font(.footnote).foregroundStyle(.secondary).accessibilityIdentifier("ownerWonderUnavailable")
                }
            } footer: {
                Text("Viewing a saved result makes no new Meta request and incurs no new inference charge.")
            }
            if let record = controller.result {
                Section {
                    Text("Real Muse Wonder response · simulated data")
                        .font(.headline).accessibilityIdentifier("ownerWonderResult")
                    Text("Muse Wonder ranked supported findings. Hydra supplied the wording and calculated every number.")
                        .font(.subheadline)
                    ForEach(record.result.sections) { section in
                        DisclosureGroup(section.title) {
                            Text((try? record.localText(section)) ?? "Validated analysis unavailable.")
                                .fixedSize(horizontal: false, vertical: true)
                            Text("Simulated evidence").font(.caption).foregroundStyle(.secondary)
                        }
                        .accessibilityIdentifier("ownerWonderSection-\(section.id)")
                    }
                }
                Section("Request record") {
                    Text("Usage-based token cost estimate: \(HydraFormat.usd(micro: Double(record.receipt.usage_derived_cost_micro_usd))).")
                    Text("Final invoice unverified. Provider extras are unverified.")
                        .accessibilityIdentifier("ownerWonderFinality")
                    Text("Token reservation: \(HydraFormat.usd(micro: Double(record.receipt.token_reservation_micro_usd))). This is not a provider spending cap.")
                    Text("Model: \(record.receipt.model)")
                    Text("Generated: \(record.generated_at)")
                }
                .font(.caption).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Recorded Wonder test")
        .onChange(of: store.configurationGeneration) { _, _ in controller.invalidate() }
        .onDisappear { controller.invalidate() }
    }
}
