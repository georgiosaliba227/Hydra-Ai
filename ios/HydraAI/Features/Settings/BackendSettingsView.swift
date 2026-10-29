import SwiftUI

struct BackendSettingsView: View {
    @EnvironmentObject private var store: BeverageStore
    @State private var url = ""
    @State private var token = ""
    @State private var offline = false
    @State private var error: String?
    @State private var goalText = ""
    @State private var goalMessage: String?
    @FocusState private var goalFocused: Bool

    var body: some View {
        Form {
            Section("Connection") {
                Toggle("Offline demo (separate local data)", isOn: $offline)
                    .accessibilityIdentifier("offlineMode")
                if !offline {
                    TextField("Backend URL", text: $url)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                        .accessibilityIdentifier("backendURL")
                    SecureField("Development access token", text: $token)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .accessibilityIdentifier("backendToken")
                }
                Button("Save connection") {
                    do {
                        try store.configure(.init(baseURL: url.trimmingCharacters(in: .whitespacesAndNewlines), token: token, offline: offline))
                        error = nil
                        Task { await store.refresh() }
                    } catch { self.error = error.localizedDescription }
                }
                .accessibilityIdentifier("saveConnection")
                Text(offline ? "Offline demo records stay on this device and are not uploaded." : "Use your local Hydra backend access token, not a Meta API key. The token is stored in Keychain. Backend mode sends confirmed beverage entries. Photos are sent to this backend only after consent and Analyze; Meta mode requires separate consent before sending photos to Meta. HealthKit records stay on device.")
                    .font(.footnote)
                Text("For simulator: 127.0.0.1 reaches this Mac. For an iPhone: use the Mac's private LAN address on a trusted network. Public connections require HTTPS.")
                    .font(.footnote)
            }
            if let error { Text(error).foregroundStyle(.red) }
            if !store.isOffline && store.isConfigured {
                Section("Daily beverage goal (optional)") {
                    TextField("Goal in mL, e.g. 2000", text: $goalText)
                        .keyboardType(.numberPad)
                        .focused($goalFocused)
                        .accessibilityIdentifier("goalField")
                    Button("Save goal") { goalFocused = false; Task { await saveGoal(Int(goalText)) } }
                        .disabled(Int(goalText).map { !(100...10_000).contains($0) } ?? true)
                        .accessibilityIdentifier("saveGoal")
                    Button("Clear goal", role: .destructive) { Task { await saveGoal(nil) } }
                    Text("A goal you choose for logged beverage volume. Hydra does not recommend an amount; daily needs vary and include water from food.")
                        .font(.footnote)
                    if let goalMessage { Text(goalMessage).font(.footnote).accessibilityIdentifier("goalMessage") }
                }
            }
            Section("AI") { Text("Camera verifies the backend mode before analysis. Mock responses are synthetic. Meta mode sends the photo to Meta only with separate consent and a server-approved budget permit. Suggestions always require confirmation; zero retention is not promised.") }
        }
        .navigationTitle("Settings")
        .toolbar { ToolbarItemGroup(placement: .keyboard) {
            Spacer(); Button("Done") { goalFocused = false }
        } }
        .onAppear { url = store.configuration.baseURL; token = store.configuration.token; offline = store.isOffline }
        .task {
            if let goal = try? await store.currentGoal() { goalText = String(goal) }
        }
    }

    @MainActor
    private func saveGoal(_ milliliters: Int?) async {
        do {
            try await store.setGoal(milliliters)
            goalText = milliliters.map(String.init) ?? ""
            goalMessage = milliliters == nil ? "Goal cleared." : "Goal saved."
        } catch {
            goalMessage = "Could not save the goal. \(error.localizedDescription)"
        }
    }
}
