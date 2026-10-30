import SwiftUI
import UniformTypeIdentifiers

struct ExportDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.json] }
    let data: Data
    init(data: Data) { self.data = data }
    init(configuration: ReadConfiguration) throws { data = configuration.file.regularFileContents ?? Data() }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { FileWrapper(regularFileWithContents: data) }
}

struct BackendSettingsView: View {
    @EnvironmentObject private var store: BeverageStore
    @State private var url = ""
    @State private var token = ""
    @State private var offline = false
    @State private var error: String?
    @State private var goalText = ""
    @State private var goalMessage: String?
    @FocusState private var goalFocused: Bool
    @State private var export: ExportDocument?
    @State private var confirmingDeleteAll = false
    @State private var dataMessage: String?

    var body: some View {
        Form {
            Section {
                LabeledContent {
                    Text(statusText).foregroundStyle(.secondary)
                } label: {
                    Label("Status", systemImage: statusSymbol)
                }
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
                if let error { Text(error).foregroundStyle(.red) }
            } header: {
                Text("Connection")
            } footer: {
                Text(offline ? "Offline demo records stay on this iPhone and are not uploaded."
                             : "Use your Hydra backend access token, not a Meta API key. It's stored in the Keychain.")
            }
            if !store.isOffline && store.isConfigured {
                Section {
                    HStack {
                        TextField("e.g. 2000", text: $goalText)
                            .alignmentGuide(.listRowSeparatorLeading) { $0[.leading] }
                            .keyboardType(.numberPad)
                            .focused($goalFocused)
                            .accessibilityLabel("Daily goal in milliliters")
                            .accessibilityIdentifier("goalField")
                        Text("mL").foregroundStyle(.secondary).accessibilityHidden(true)
                    }
                    Button("Save goal") { goalFocused = false; Task { await saveGoal(Int(goalText)) } }
                        .disabled(Int(goalText).map { !(100...10_000).contains($0) } ?? true)
                        .accessibilityIdentifier("saveGoal")
                    Button("Clear goal", role: .destructive) { Task { await saveGoal(nil) } }
                    if let goalMessage { Text(goalMessage).font(.footnote).accessibilityIdentifier("goalMessage") }
                } header: {
                    Text("Daily goal (optional)")
                } footer: {
                    Text("A goal you choose for logged drinks. Hydra doesn't recommend an amount; daily needs vary and include water from food.")
                }
            }
            Section {
                NavigationLink { HealthActivityPermissionView() } label: {
                    Label("Apple Health", systemImage: "heart.text.square")
                }
            } footer: {
                Text("Optional. Reads today's steps on this iPhone; Health records aren't sent anywhere.")
            }
            if !store.isOffline && store.isConfigured {
                Section {
                    Button("Export my data (JSON)") { Task { await exportData() } }
                        .accessibilityIdentifier("exportData")
                    Button("Delete all my data", role: .destructive) { confirmingDeleteAll = true }
                        .disabled(!store.canLog)
                        .accessibilityIdentifier("deleteAllData")
                    if let dataMessage { Text(dataMessage).font(.footnote).accessibilityIdentifier("dataMessage") }
                } header: {
                    Text("Your data")
                } footer: {
                    Text("Export includes your logged drinks and goal. Deleting erases them from your backend and can't be undone.")
                }
            }
            Section("Privacy & AI") {
                DisclosureGroup("What's sent where") {
                    Text("Backend mode sends the drinks you confirm to your backend. Photos go to your backend only after you consent and tap Analyze; Meta mode needs a separate consent before a photo is sent to Meta. Apple Health records stay on this iPhone.")
                    Text("Camera checks the backend mode before analysis. Mock responses are synthetic. In Meta mode a photo goes to Meta only with separate consent and a server-approved budget permit. Suggestions always need your confirmation; zero retention is not promised.")
                }
                .font(.footnote)
                DisclosureGroup("Connecting a device") {
                    Text("Simulator: 127.0.0.1 reaches this Mac. iPhone: use the Mac's private LAN address on a trusted network. Public connections require HTTPS.")
                }
                .font(.footnote)
            }
        }
        .navigationTitle("Settings")
        .fileExporter(isPresented: Binding(get: { export != nil }, set: { if !$0 { export = nil } }),
                      document: export, contentType: .json, defaultFilename: "hydra-export") { result in
            if case .failure = result { dataMessage = "Export was not saved." }
        }
        .confirmationDialog("Delete all your Hydra data?", isPresented: $confirmingDeleteAll, titleVisibility: .visible) {
            Button("Delete all my data", role: .destructive) { Task { await deleteAll() } }
        } message: {
            Text("Every logged drink and your goal are erased from the backend. This cannot be undone.")
        }
        .toolbar { ToolbarItemGroup(placement: .keyboard) {
            Spacer(); Button("Done") { goalFocused = false }
        } }
        .onAppear { url = store.configuration.baseURL; token = store.configuration.token; offline = store.isOffline }
        .task {
            if let goal = try? await store.currentGoal() { goalText = String(goal) }
        }
    }

    private var statusText: String {
        if store.isOffline { return "Offline demo" }
        if !store.isConfigured { return "Not connected" }
        if case .failed = store.state { return "Can't reach backend" }
        return "Connected"
    }

    private var statusSymbol: String {
        if store.isOffline { return "iphone" }
        if !store.isConfigured { return "link.badge.plus" }
        if case .failed = store.state { return "exclamationmark.triangle" }
        return "checkmark.circle"
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

    @MainActor
    private func exportData() async {
        do { export = ExportDocument(data: try await store.exportData()); dataMessage = nil }
        catch { dataMessage = "Could not export. \(error.localizedDescription)" }
    }

    @MainActor
    private func deleteAll() async {
        do {
            let count = try await store.deleteAllData()
            goalText = ""
            dataMessage = "Deleted \(count) logged \(count == 1 ? "drink" : "drinks") and your goal."
        } catch {
            dataMessage = "Could not delete your data. \(error.localizedDescription)"
        }
    }
}
