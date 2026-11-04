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
    @EnvironmentObject private var context: DailyContextCoordinator
    @State private var url = ""
    @State private var token = ""
    @State private var offline = false
    @State private var error: String?
    @State private var goalValue: Double?
    @State private var goalEdit = UUID()
    @State private var goalFieldReset = UUID()
    @State private var goalInputValid = true
    @State private var goalMessage: String?
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
                Text("Connection").foregroundStyle(.primary)
            } footer: {
                Text(offline ? "Offline demo records stay on this iPhone and are not uploaded."
                             : "Use your Hydra backend access token, not a Meta API key. It's stored in the Keychain.")
            }
            Section("Display units") {
                Picker("Units", selection: $units.system) {
                    ForEach(DisplayUnitSystem.allCases, id: \.self) { system in
                        Text(system.label).tag(system)
                    }
                }
                .pickerStyle(.menu)
                .accessibilityIdentifier("displayUnitsPicker")
            }
            DailyContextSettingsSections()
            Section {
                NavigationLink {
                    GuidedGoalSetupView(profileStore: store.goalProfiles)
                } label: { Label("Calculate my starting goal", systemImage: "list.clipboard") }
                .accessibilityIdentifier("guidedGoalSetup")
                if !store.isOffline && store.isConfigured {
                    HydraDisclosure(title: "Choose a custom goal", identifier: "customGoalEntry") {
                        CanonicalQuantityField("Daily goal", value: Binding(get: { goalValue }, set: {
                            goalEdit = UUID(); goalValue = $0; goalMessage = nil
                        }), quantity: .volume, accessibilityIdentifier: "goalField", isInputValid: $goalInputValid)
                            .id(goalFieldReset)
                        Button("Save goal") {
                            let candidate = parsedGoal, generation = store.configurationGeneration
                            Task { await saveGoal(candidate, generation: generation) }
                        }
                        .disabled(parsedGoal == nil || store.isSettingGoal)
                        .accessibilityIdentifier("saveGoal")
                        Button("Clear goal", role: .destructive) {
                            let generation = store.configurationGeneration
                            Task { await saveGoal(nil, generation: generation) }
                        }.disabled(store.isSettingGoal)
                    }
                    if let goalMessage { Text(goalMessage).font(.footnote).accessibilityIdentifier("goalMessage") }
                }
            } header: {
                Text("Daily goal (optional)")
            } footer: {
                Text("Review an approximate published adult beverage starting reference or choose your own goal. Confirm before changing it. Profile answers stay on this iPhone; only your confirmed goal goes to the backend.")
            }
            Section {
                NavigationLink { HealthActivityPermissionView() } label: {
                    Label("Apple Health", systemImage: "heart.text.square")
                }
            } footer: {
                Text("Optional. Reads today's steps on this iPhone; Health records aren't sent anywhere.")
            }
            if !store.isOffline && store.isConfigured {
                WonderReadinessSection()
                Section {
                    NavigationLink { OwnerSyntheticWonderView() } label: {
                        Label("Recorded Wonder test", systemImage: "text.magnifyingglass")
                    }
                    .accessibilityIdentifier("openOwnerWonderResult")
                } footer: {
                    Text("View a recorded model demonstration on simulated data. Loading it makes no Meta request.")
                }
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
                    Text("Export includes backend drinks, goal, saved corrections and opted-in training photos. Export manual measurements from Plan a workout and local profile answers from Guided goal setup. Deleting also erases saved manual measurements and goal profiles on this iPhone, and cannot be undone.")
                }
            }
            Section("Privacy & AI") {
                DisclosureGroup("What's sent where") {
                    Text("Backend mode sends the drinks you confirm to your backend. Photos go to your backend only after you consent and tap Analyze; Meta mode needs a separate consent before a photo is sent to Meta. Apple Health records stay on this iPhone.")
                    Text("Camera checks the backend mode before analysis. Mock responses are synthetic. In Meta mode a photo goes to Meta only with separate consent and a server-approved budget permit. Suggestions always need your confirmation; zero retention is not promised.")
                    Text("The local trained camera processes photos on your configured Mac. Wonder explanations use a separate preview and consent for the displayed aggregates; context updates never send them automatically.")
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
            Text("Your drinks, goal, correction memory and opted-in training photos are erased from the backend. Saved manual measurements, goal profiles and automatic context preferences on this iPhone are also erased. This cannot be undone.")
        }
        .onAppear { url = store.configuration.baseURL; token = store.configuration.token; offline = store.isOffline }
        .onChange(of: store.configurationGeneration) { _, _ in
            goalEdit = UUID(); goalValue = nil; goalInputValid = true; goalMessage = nil; goalFieldReset = UUID()
        }
        .task(id: store.configurationGeneration) {
            let generation = store.configurationGeneration, edit = goalEdit
            do {
                let goal = try await store.currentGoal()
                guard !Task.isCancelled, generation == store.configurationGeneration, edit == goalEdit else { return }
                goalValue = goal.map(Double.init)
            } catch { }
        }
    }

    private var parsedGoal: Int? {
        guard goalInputValid, let value = goalValue, value.isFinite, (100...10_000).contains(value) else { return nil }
        return Int(value.rounded())
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
    private func saveGoal(_ milliliters: Int?, generation: UUID) async {
        guard generation == store.configurationGeneration else { return }
        do {
            try await store.setGoal(milliliters)
            guard !Task.isCancelled, generation == store.configurationGeneration else { return }
            goalEdit = UUID(); goalValue = milliliters.map(Double.init); goalFieldReset = UUID()
            goalMessage = milliliters == nil ? "Goal cleared." : "Goal saved."
        } catch {
            guard !Task.isCancelled, generation == store.configurationGeneration else { return }
            goalMessage = "Goal confirmation failed. The server may have accepted the change; check the current goal before trying again. \(error.localizedDescription)"
        }
    }

    @MainActor
    private func exportData() async {
        do { export = ExportDocument(data: try await store.exportData()); dataMessage = nil }
        catch { dataMessage = "Could not export. \(error.localizedDescription)" }
    }

    @MainActor
    private func deleteAll() async {
        context.disableAutomaticWeather()
        await context.setHealthAutoEnabled(false)
        do {
            let count = try await store.deleteAllData()
            goalValue = nil
            dataMessage = "Deleted \(count) logged \(count == 1 ? "drink" : "drinks") and your goal, plus saved manual history, goal profiles, and automatic context on this iPhone."
        } catch ServiceError.server(409) {
            dataMessage = "Local manual measurements, goal profiles, and automatic context were cleared. Your backend is busy, so backend data has not been deleted. Wait for that request to finish, then choose Delete again."
        } catch {
            dataMessage = "Could not finish deleting your data. Automatic context is off. Local measurements and profiles are erased before the backend request, but a storage failure may leave local records. Check Guided goal setup and Plan a workout. \(error.localizedDescription)"
        }
    }
}
