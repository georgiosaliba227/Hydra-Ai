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
    @EnvironmentObject private var units: DisplayUnits
    @State private var url = ""
    @State private var token = ""
    @State private var offline = false
    @State private var onDevice = false
    @State private var insightsEnabled = false
    @State private var connectionMessage: String?
    @State private var checkingConnection = false
    @State private var error: String?
    @State private var goalText = ""
    @State private var goalMessage: String?
    @State private var goalEditRevision = UUID()
    @State private var loadingGoal = true
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
                Toggle("On this iPhone (works offline)", isOn: $onDevice)
                    .accessibilityIdentifier("onDeviceMode")
                    .onChange(of: onDevice) { _, enabled in if enabled { offline = false } }
                if !onDevice {
                    Toggle("Offline demo (separate local data)", isOn: $offline)
                        .accessibilityIdentifier("offlineMode")
                }
                if onDevice {
                    Toggle("Connect backend features", isOn: $insightsEnabled)
                        .accessibilityIdentifier("backendInsightsMode")
                    if insightsEnabled {
                        Text("Trends sends a summary of your phone's drink totals after you review it. Ask Hydra sends your question and today's total only if you include it. Workout estimates send the inputs you review. Your photos and stored drinks stay on this iPhone.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
                if !offline && (!onDevice || insightsEnabled) {
                    TextField("Backend URL", text: $url)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                        .accessibilityIdentifier("backendURL")
                    SecureField("Development access token", text: $token)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .accessibilityIdentifier("backendToken")
                }
                Button("Save connection") {
                    do {
                        try store.configure(.init(baseURL: url.trimmingCharacters(in: .whitespacesAndNewlines), token: token, offline: offline, onDevice: onDevice, insightsEnabled: insightsEnabled))
                        error = nil
                        connectionMessage = nil
                        Task { await store.refresh() }
                    } catch { self.error = error.localizedDescription }
                }
                .accessibilityIdentifier("saveConnection")
                if store.hasInsightsConnection {
                    Button(checkingConnection ? "Checking backend…" : "Check backend features") { Task { await checkConnection() } }
                        .disabled(checkingConnection)
                        .accessibilityIdentifier("checkBackendInsights")
                }
                if let connectionMessage { Text(connectionMessage).font(.footnote).accessibilityIdentifier("backendInsightsStatus") }
                if let error { Text(error).foregroundStyle(.red) }
            } header: {
                Text("Connection").foregroundStyle(.primary)
            } footer: {
                Text(onDevice ? "Camera analysis and confirmed drinks stay on this iPhone. Your server settings and existing server history are preserved separately."
                             : offline ? "Offline demo records stay on this iPhone and are not uploaded."
                             : "Use your Hydra backend access token, not a Meta API key. It's stored in the Keychain.")
            }
            if (!store.isOffline || store.isOnDevice) && store.isConfigured {
                Section {
                    NavigationLink {
                        GuidedGoalSetupView(profileStore: store.goalProfiles)
                    } label: { Label("Guided goal setup", systemImage: "person.crop.circle.badge.checkmark") }
                        .accessibilityIdentifier("guidedGoalSetup")
                    HStack {
                        TextField("e.g. 2000", text: Binding(get: { goalText }, set: { goalText = $0; goalEditRevision = UUID() }))
                            .alignmentGuide(.listRowSeparatorLeading) { $0[.leading] }
                            .keyboardType(.numberPad)
                            .focused($goalFocused)
                            .accessibilityLabel("Daily goal in milliliters")
                            .accessibilityIdentifier("goalField")
                        Text("mL").foregroundStyle(.secondary).accessibilityHidden(true)
                    }
                    Button("Save goal") { goalFocused = false; Task { await saveGoal(Int(goalText)) } }
                        .disabled(loadingGoal || store.isSettingGoal || (Int(goalText).map { !(100...10_000).contains($0) } ?? true))
                        .accessibilityIdentifier("saveGoal")
                    Button("Clear goal", role: .destructive) { Task { await saveGoal(nil) } }
                        .disabled(loadingGoal || store.isSettingGoal)
                    if let goalMessage { Text(goalMessage).font(.footnote).accessibilityIdentifier("goalMessage") }
                } header: {
                    Text("Daily goal (optional)")
                } footer: {
                    Text("Review a published adult starting reference in guided setup, or choose your own goal for logged drinks. A starting reference is not a measured personal requirement.")
                }
            }
            Section {
                Picker("Display units", selection: $units.system) {
                    Text("US").tag(DisplayUnitSystem.us)
                    Text("Metric").tag(DisplayUnitSystem.metric)
                }.accessibilityIdentifier("displayUnits")
                NavigationLink { HealthActivityPermissionView() } label: {
                    Label("Apple Health", systemImage: "heart.text.square")
                }
            } footer: {
                Text("Optional. Reads today's steps on this iPhone; Health records aren't sent anywhere.")
            }
            if (!store.isOffline || store.isOnDevice) && store.isConfigured {
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
                    Text(store.isOnDevice ? "Export includes this iPhone's drinks, goal and original camera suggestions. Profile answers have their own export in guided setup. Deleting clears these local records and this destination's saved profile. Other connection profiles, server and demo data stay separate."
                         : "Export includes your drinks, goal, saved corrections and training photos you opted in to contribute. Deleting erases them from your backend and can't be undone.")
                }
            }
            Section("Privacy & AI") {
                DisclosureGroup("What's sent where") {
                    Text("On this iPhone mode uses the bundled Meta category model and Apple label reading locally. It works without a server or internet. Confirmed entries stay in a separate local store, including the original suggestion and your corrected details. Photos are not retained or used for training.")
                    Text("Backend mode sends the drinks you confirm to your backend. Photos go to your backend only after you consent and tap Analyze; Meta mode needs a separate consent before a photo is sent to Meta. Apple Health records stay on this iPhone.")
                    Text("Camera checks the backend mode before analysis. Mock responses are synthetic. In Meta mode a photo goes to Meta only with separate consent and a server-approved budget permit. Suggestions always need your confirmation; zero retention is not promised.")
                    Text("Remembered corrections improve your own suggestions without retraining Muse. Training contribution is a separate, optional choice on an edited entry: your backend stages the latest 20 opted-in photos and corrections for future reviewed training. Nothing uploads a training dataset to Meta automatically.")
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
            Text(store.isOnDevice ? "This iPhone's local drinks, goal, original suggestions and saved profile will be erased. This cannot be undone. Other connection profiles, server and demo records stay separate."
                 : "Your drinks, goal, correction memory and opted-in training photos are erased from the backend. This cannot be undone.")
        }
        .toolbar { ToolbarItemGroup(placement: .keyboard) {
            Spacer(); Button("Done") { goalFocused = false }
        } }
        .onAppear { url = store.configuration.baseURL; token = store.configuration.token; offline = store.configuration.offline; onDevice = store.isOnDevice; insightsEnabled = store.configuration.insightsEnabled }
        .task(id: store.configurationGeneration) {
            let connection = store.configurationGeneration, revision = goalEditRevision
            goalText = ""; goalMessage = nil; loadingGoal = true
            defer { if connection == store.configurationGeneration { loadingGoal = false } }
            let goal = try? await store.currentGoal()
            guard connection == store.configurationGeneration, revision == goalEditRevision, !Task.isCancelled else { return }
            goalText = goal.map(String.init) ?? ""
        }
    }

    private var statusText: String {
        if store.isOnDevice { return "On this iPhone" }
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
        let revision = goalEditRevision
        do {
            try await store.setGoal(milliliters)
            if revision == goalEditRevision { goalText = milliliters.map(String.init) ?? "" }
            goalMessage = milliliters == nil ? "Goal cleared." : "Goal saved."
        } catch {
            goalMessage = "Could not save the goal. \(error.localizedDescription)"
        }
    }

    @MainActor
    private func checkConnection() async {
        let generation = store.configurationGeneration
        checkingConnection = true
        defer { checkingConnection = false }
        do {
            _ = try await store.insightsService().deviceInsightsCapabilities()
            guard generation == store.configurationGeneration, !Task.isCancelled else { return }
            connectionMessage = "Backend features connected. No drink data was sent."
        } catch {
            guard generation == store.configurationGeneration, !Task.isCancelled else { return }
            connectionMessage = "Backend features unavailable. \(error.localizedDescription)"
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
