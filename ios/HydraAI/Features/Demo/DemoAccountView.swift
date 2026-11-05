import SwiftUI

/// A distinct app identity and sandbox, labelled throughout normal navigation.
struct DemoAccountView: View {
    @EnvironmentObject private var store: BeverageStore
    @State private var ready = false
    @State private var message: String?

    var body: some View {
        Group {
            if ready { RootView() }
            else {
                VStack(spacing: 16) {
                    Text("Hydra Demo").font(.largeTitle.bold())
                    if let message {
                        Text(message).multilineTextAlignment(.center)
                        Button("Try preparation again") { Task { await prepare() } }
                    } else { ProgressView("Preparing simulated account…") }
                }.padding()
            }
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            HStack {
                Image(systemName: "theatermasks")
                Text("DEMO · simulated data").font(.caption.weight(.semibold))
                    .accessibilityIdentifier("demoAccountBadge")
                Spacer()
            }
            .padding(.horizontal, 16).padding(.vertical, 7)
            .foregroundStyle(Color.primary)
            .background(Color.orange.opacity(0.18))
        }
        .task { await prepare() }
    }

    @MainActor private func prepare() async {
        guard !ready else { return }
        message = nil
        do {
            try store.configuration.save()
            try await store.prepareDemoAccount()
            ready = true
        } catch {
            guard !Task.isCancelled else { return }
            message = "The simulated account could not be prepared. \(error.localizedDescription)"
        }
    }
}

struct DemoSettingsSection: View {
    @EnvironmentObject private var store: BeverageStore
    @State private var confirmingReset = false
    @State private var resetting = false
    @State private var message: String?

    private var bundledModel: Bool {
        Bundle.main.url(forResource: "HydraBeverage", withExtension: "mlmodelc") != nil
    }

    var body: some View {
        Section {
            Label("Demo Athlete · fictional account", systemImage: "theatermasks")
            Text("This app contains simulated drink history and profile answers. It is separate from your Hydra records.")
                .font(.footnote).foregroundStyle(.secondary)
            LabeledContent("Camera model", value: bundledModel ? "Stored in this app" : "Unavailable")
                .accessibilityIdentifier("demoBundledModel")
            Text("Meta DINOv2 beverage categories and Apple label reading run on this iPhone. Photos are not uploaded on this path.")
                .font(.footnote).foregroundStyle(.secondary)
            Button(resetting ? "Restoring demo…" : "Reset simulated account") { confirmingReset = true }
                .disabled(resetting || !store.canLog)
                .accessibilityIdentifier("resetDemoAccount")
            if let message { Text(message).font(.footnote).accessibilityIdentifier("demoResetStatus") }
        } header: { Text("Demo account") }
        footer: { Text("Reset restores only this demo app's fictional history, profile and goal. Your Hydra app is unaffected.") }
        .confirmationDialog("Reset this simulated demo account?", isPresented: $confirmingReset, titleVisibility: .visible) {
            Button("Reset simulated account", role: .destructive) { Task { await reset() } }
                .accessibilityIdentifier("confirmResetDemoAccount")
        } message: {
            Text("Edits in Hydra Demo will be replaced with its original simulated sample data. Your separate Hydra records stay untouched.")
        }
    }

    @MainActor private func reset() async {
        resetting = true; message = nil
        defer { resetting = false }
        do {
            try await store.prepareDemoAccount(reset: true)
            message = "Simulated demo account restored."
        } catch { message = "Could not restore the demo. \(error.localizedDescription)" }
    }
}
