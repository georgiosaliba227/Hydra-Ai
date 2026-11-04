import Foundation

enum LoadState: Equatable {
    case idle, loading, loaded
    case failed(String)
}

enum BeverageEditError: LocalizedError {
    case changedElsewhere
    var errorDescription: String? {
        "This beverage changed since it was loaded. The latest version is shown; review it and edit again."
    }
}

struct PendingBeverage: Codable {
    let key: UUID
    let request: CreateBeverageRequest
    let destination: String
}

enum GoalMutationError: LocalizedError {
    case busy, connectionChanged
    var errorDescription: String? {
        switch self {
        case .busy: "Another save is in progress. Wait for it to finish before confirming a goal."
        case .connectionChanged: "The connection changed. Review the goal for the selected destination."
        }
    }
}

@MainActor
final class BeverageStore: ObservableObject {
    @Published private(set) var logs: [BeverageLog] = []
    @Published private(set) var state: LoadState = .idle
    @Published private(set) var intakeHistory: IntakeHistoryForecast?
    @Published private(set) var intakeHistoryState: LoadState = .idle
    @Published private(set) var summary: DailySummary?
    @Published private(set) var pending: PendingBeverage?
    @Published private(set) var configuration: APIConfiguration
    @Published private(set) var configurationGeneration = UUID()
    @Published private(set) var isSaving = false
    @Published private(set) var isSettingGoal = false
    let goalProfiles: GoalProfileStore

    private var service: (any BeverageService)?
    private let pendingURL: URL
    private var pendingReadError = false
    private var refreshVersion = 0
    private var historyTask: Task<Void, Never>?
    private var currentRecognitionReceipts: Set<UUID> = []
    private var onDeviceResults: [UUID: OnDeviceRecognitionProvenance] = [:]
    private var goalMutationID: UUID?

    private func invalidateHistory() {
        refreshVersion += 1
        historyTask?.cancel(); historyTask = nil
        intakeHistory = nil; intakeHistoryState = .idle
    }
    var isConfigured: Bool { service != nil }
    var isOffline: Bool { configuration.offline || configuration.onDevice }
    var isOnDevice: Bool { configuration.onDevice }
    var hasInsightsConnection: Bool { configuration.backendInsightsConfiguration != nil }
    func insightsService() throws -> HTTPBeverageService {
        guard let connection = configuration.backendInsightsConfiguration else { throw ServiceError.configuration }
        return try HTTPBeverageService(configuration: connection)
    }

    /// Read from the selected phone destination, never from server history.
    func deviceTrendSnapshot(now: Date = .now, zone: TimeZone = .current) async throws -> DeviceTrendSnapshot {
        guard isOnDevice, canLog, let service else { throw ServiceError.pending }
        let generation = configurationGeneration, version = refreshVersion
        let logs = try await service.listBeverages()
        let goal = try await service.goalSettings().daily_beverage_goal_ml
        try Task.checkCancellation()
        guard generation == configurationGeneration, version == refreshVersion, canLog else { throw GoalMutationError.connectionChanged }
        return try DeviceTrendSnapshot.make(logs: logs, goal: goal, now: now, zone: zone)
    }

    func deviceAssistantTotal(for request: AssistantRequest, generation: UUID) async throws -> Int? {
        guard generation == configurationGeneration else { throw GoalMutationError.connectionChanged }
        guard isOnDevice else { throw ServiceError.configuration }
        guard request.context_scope == "today_logged_total" else { return nil }
        guard canLog, let service else { throw ServiceError.pending }
        guard let date = request.date, let timezone = request.timezone else { throw ServiceError.invalidResponse }
        let version = refreshVersion
        let result = try await service.dailySummary(date: date, timezone: timezone)
        try Task.checkCancellation()
        guard generation == configurationGeneration, version == refreshVersion, canLog else { throw GoalMutationError.connectionChanged }
        guard result.localDate == date, result.timezone == timezone, result.beverageTotalMl.isFinite,
              (0...1_000_000_000).contains(result.beverageTotalMl), result.beverageTotalMl.rounded() == result.beverageTotalMl else { throw ServiceError.invalidResponse }
        return Int(result.beverageTotalMl)
    }
    var canLog: Bool { service != nil && pending == nil && !pendingReadError && !isSaving && !isSettingGoal }
    private var destination: String { Self.destination(for: configuration) }
    private static func destination(for config: APIConfiguration) -> String {
        config.onDevice ? "on_device" : config.offline ? "offline" : config.baseURL
    }
    private static func makeService(for config: APIConfiguration) throws -> any BeverageService {
        if config.onDevice {
            #if DEBUG
            if let directory = goalTestDirectory {
                return LocalBeverageService(fileURL: directory.appendingPathComponent("beverages.json"))
            }
            #endif
            return LocalBeverageService()
        }
        if config.offline { return MockBeverageService() }
        return try HTTPBeverageService(configuration: config)
    }

    init(service: (any BeverageService)? = nil, pendingURL: URL? = nil, configuration: APIConfiguration = .load(),
         goalProfiles: GoalProfileStore? = nil) {
        self.configuration = configuration
        self.goalProfiles = goalProfiles ?? Self.makeGoalProfiles()
        self.goalProfiles.configure(configuration)
        let folder = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        #if DEBUG
        self.pendingURL = pendingURL ?? Self.goalTestDirectory?.appendingPathComponent("pending.json") ?? folder.appendingPathComponent("HydraAI/pending-beverage-v1.json")
        #else
        self.pendingURL = pendingURL ?? folder.appendingPathComponent("HydraAI/pending-beverage-v1.json")
        #endif
        self.service = service ?? (try? Self.makeService(for: configuration))
        if FileManager.default.fileExists(atPath: self.pendingURL.path) {
            do {
                let decoder = JSONDecoder(); decoder.dateDecodingStrategy = .iso8601
                let restored = try decoder.decode(PendingBeverage.self, from: Data(contentsOf: self.pendingURL))
                if restored.destination == "on_device" { try OnDeviceProtectedFile.protectExisting(self.pendingURL) }
                pending = restored
            } catch {
                pendingReadError = true
                state = .failed("The saved pending beverage could not be read. Logging is blocked to avoid duplicate entries; preserve the pending file for recovery.")
            }
        }
    }

    private static func makeGoalProfiles() -> GoalProfileStore {
        #if DEBUG
        if let directory = goalTestDirectory {
            return GoalProfileStore(directory: directory.appendingPathComponent("profiles", isDirectory: true))
        }
        #endif
        return GoalProfileStore()
    }

    #if DEBUG
    private static var goalTestDirectory: URL? {
        guard let suite = ProcessInfo.processInfo.environment["HYDRA_TEST_GOAL_PROFILE_SUITE"],
              suite.hasPrefix("HydraUITests."), let id = UUID(uuidString: String(suite.suffix(36))) else { return nil }
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .resolvingSymlinksInPath().appendingPathComponent("HydraAI/goal-setup-tests-v1/\(id.uuidString)", isDirectory: true)
    }
    #endif

    func configure(_ config: APIConfiguration) throws {
        if let pending, pending.destination != Self.destination(for: config) { throw ServiceError.pending }
        let next = try Self.makeService(for: config)
        try config.save()
        invalidateHistory()
        configurationGeneration = UUID()
        currentRecognitionReceipts.removeAll()
        onDeviceResults.removeAll()
        configuration = config; goalProfiles.configure(config)
        service = next; logs = []; summary = nil; state = .idle
    }

    func refresh() async {
        invalidateHistory()
        guard !pendingReadError else { return }
        guard let service else { state = .failed(ServiceError.configuration.localizedDescription); return }
        let version = refreshVersion
        state = .loading
        let formatter = DateFormatter(); formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = .current; formatter.dateFormat = "yyyy-MM-dd"
        let date = formatter.string(from: .now), zone = TimeZone.current.identifier
        do {
            let nextLogs = try await service.listBeverages()
            let nextSummary = try await service.dailySummary(date: date, timezone: zone)
            guard version == refreshVersion else { return }
            guard nextSummary.beverageTotalMl.isFinite, nextSummary.beverageTotalMl >= 0,
                  nextSummary.goal?.isValid ?? true else { throw ServiceError.invalidResponse }
            logs = nextLogs; summary = nextSummary; state = .loaded
            if !isOffline && pending == nil {
                intakeHistoryState = .loading
                historyTask = Task { [weak self] in
                    do {
                        let history = try await service.intakeHistory(date: date, timezone: zone)
                        try history.validate(date: date, timezone: zone)
                        guard let self, version == self.refreshVersion, !Task.isCancelled else { return }
                        self.intakeHistory = history; self.intakeHistoryState = .loaded
                    } catch {
                        guard let self, version == self.refreshVersion, !Task.isCancelled else { return }
                        self.intakeHistoryState = .failed("Logged-intake history unavailable. Beverage logging still works.")
                    }
                }
            }
        } catch {
            guard version == refreshVersion else { return }
            state = .failed("Could not refresh beverages. \(error.localizedDescription)")
        }
    }

    /// A transient camera result may be confirmed only on its original backend
    /// configuration. Already-persisted pending mutations retain their retry path.
    func registerRecognitionReceipt(_ receipt: UUID, generation: UUID) -> Bool {
        guard generation == configurationGeneration, !isOnDevice else { return false }
        currentRecognitionReceipts.insert(receipt)
        return true
    }

    /// Only the active on-phone recognizer can register a local confirmation.
    func registerOnDeviceResult(_ result: RecognitionResult, generation: UUID) -> Bool {
        guard isOnDevice, generation == configurationGeneration,
              result.version == "recognition-v1", result.mode == "on_device",
              result.model == "dinov2-small-beverage-v1", result.requiresConfirmation,
              result.candidates.count == 1, let receipt = result.recognitionId,
              let candidate = result.candidates.first else { return false }
        let provenance = OnDeviceRecognitionProvenance(modelID: result.model, originalCandidate: candidate, processedAt: .now)
        guard (try? provenance.validate()) != nil else { return false }
        currentRecognitionReceipts.insert(receipt)
        onDeviceResults[receipt] = provenance
        return true
    }

    func add(category: String, consumedMl: Int, at: Date, source: String = "manual", productId: String? = nil, containerMl: Int? = nil, recognitionId: UUID? = nil, recognitionFeedback: RecognitionFeedback? = nil, consumptionAssumption: String? = nil, beverageType: String? = nil) async throws {
        guard canLog else { throw ServiceError.pending }
        if let recognitionId, !currentRecognitionReceipts.contains(recognitionId) {
            throw ServiceError.liveRecognitionUnverified
        }
        if isOnDevice && source == "confirmed_recognition" {
            guard let recognitionId, onDeviceResults[recognitionId] != nil, recognitionFeedback == nil else { throw ServiceError.invalidResponse }
        }
        var request = CreateBeverageRequest(category: category.trimmingCharacters(in: .whitespacesAndNewlines), consumedMl: consumedMl, consumedAt: at, timezone: TimeZone.current.identifier, source: source, recognitionId: recognitionId, productId: productId, containerMl: containerMl, recognitionFeedback: recognitionFeedback, consumptionAssumption: consumptionAssumption, beverageType: beverageType)
        request.onDeviceRecognition = isOnDevice ? recognitionId.flatMap { onDeviceResults[$0] } : nil
        try request.validate(allowOnDevice: isOnDevice)
        let item = PendingBeverage(key: UUID(), request: request, destination: destination)
        do {
            let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
            if isOnDevice {
                try OnDeviceProtectedFile.write(encoder.encode(item), to: pendingURL)
            } else {
                try FileManager.default.createDirectory(at: pendingURL.deletingLastPathComponent(), withIntermediateDirectories: true)
                try encoder.encode(item).write(to: pendingURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
            }
        } catch { throw ServiceError.storage }
        pending = item
        try await retryPending()
    }

    /// Corrections and deletions wait for any pending creation so ordering stays unambiguous.
    func update(_ log: BeverageLog, category: String, consumedMl: Int, at: Date) async throws {
        guard canLog, let service else { throw ServiceError.pending }
        let request = UpdateBeverageRequest(correcting: log, category: category, consumedMl: consumedMl, consumedAt: at)
        guard request.hasChanges else { return }
        try request.validate()
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await service.updateBeverage(id: log.id, request)
        } catch ServiceError.server(409) {
            await refresh()
            throw BeverageEditError.changedElsewhere
        }
        await refresh()
    }

    func exportData() async throws -> Data {
        guard let service, !configuration.offline else { throw ServiceError.configuration }
        return try await service.exportData()
    }

    /// Erases the selected destination's records and local profile; other scopes stay separate.
    func deleteAllData() async throws -> Int {
        guard canLog, let service, !configuration.offline else { throw ServiceError.pending }
        isSaving = true
        defer { isSaving = false }
        try goalProfiles.deleteCurrent()
        let count = try await service.deleteAllData()
        // Delete-all also erases local camera receipts on the backend. Revoke
        // displayed and delayed results before they can become pending saves.
        configurationGeneration = UUID()
        currentRecognitionReceipts.removeAll()
        onDeviceResults.removeAll()
        await refresh()
        return count
    }

    func currentGoal() async throws -> Int? {
        guard let service else { throw ServiceError.configuration }
        let generation = configurationGeneration
        let result = try await service.goalSettings().daily_beverage_goal_ml
        try Task.checkCancellation()
        guard generation == configurationGeneration else { throw GoalMutationError.connectionChanged }
        return result
    }

    /// Saves a goal the user chose (nil clears it), then reloads today's progress.
    func setGoal(_ milliliters: Int?) async throws {
        guard let service else { throw ServiceError.configuration }
        guard !isSettingGoal && !isSaving else { throw GoalMutationError.busy }
        try Task.checkCancellation()
        let generation = configurationGeneration, mutation = UUID()
        isSettingGoal = true; goalMutationID = mutation
        defer { if goalMutationID == mutation { goalMutationID = nil; isSettingGoal = false } }
        _ = try await service.updateGoal(milliliters)
        try Task.checkCancellation()
        guard generation == configurationGeneration else { throw GoalMutationError.connectionChanged }
        await refresh()
        try Task.checkCancellation()
        guard generation == configurationGeneration else { throw GoalMutationError.connectionChanged }
    }

    func delete(_ log: BeverageLog) async throws {
        guard canLog, let service else { throw ServiceError.pending }
        isSaving = true
        defer { isSaving = false }
        do {
            try await service.deleteBeverage(id: log.id, revision: log.revision)
        } catch ServiceError.server(409) {
            await refresh()
            throw BeverageEditError.changedElsewhere
        }
        await refresh()
    }

    func retryPending() async throws {
        guard !isSaving, !pendingReadError, let service, let item = pending, item.destination == destination else { throw ServiceError.pending }
        try item.request.validate(allowOnDevice: isOnDevice)
        if isOnDevice && item.request.source == "confirmed_recognition" && item.request.onDeviceRecognition == nil { throw ServiceError.invalidResponse }
        invalidateHistory()
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await service.createBeverage(item.request, idempotencyKey: item.key)
            // Retain the same mutation until both server success and local removal succeed.
            try FileManager.default.removeItem(at: pendingURL)
            pending = nil
            await refresh()
        } catch {
            state = .failed("Beverage confirmation is pending. Retry safely with the same request. \(error.localizedDescription)")
            throw error
        }
    }
}
