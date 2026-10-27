import SwiftUI

struct BackendSettingsView: View {
    @EnvironmentObject private var store: BeverageStore
    @State private var url = ""
    @State private var token = ""
    @State private var offline = false
    @State private var error: String?

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
                Text(offline ? "Offline demo records stay on this device and are not uploaded." : "Use your local Hydra backend access token, not a Meta API key. The token is stored in Keychain. Backend mode sends confirmed beverage entries only; photos and HealthKit stay on device.")
                    .font(.footnote)
                Text("For simulator: 127.0.0.1 reaches this Mac. For an iPhone: use the Mac's private LAN address on a trusted network. Public connections require HTTPS.")
                    .font(.footnote)
            }
            if let error { Text(error).foregroundStyle(.red) }
            Section("AI") { Text("Meta requests are disabled. Recognition remains a local manual-confirmation flow.") }
        }
        .navigationTitle("Settings")
        .onAppear { url = store.configuration.baseURL; token = store.configuration.token; offline = store.isOffline }
    }
}
