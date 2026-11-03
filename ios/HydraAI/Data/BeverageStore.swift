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
        case .busy: "Another goal confirmation is in progress. Wait for it to finish."
        case .connectionChanged: "The backend connection changed. Review your goal for the selected connection."
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
    let calibrationHistory: CalibrationHistoryStore
    let goalProfiles: GoalProfileStore

    private var service: (any BeverageService)?
    private let pendingURL: URL
    private var pendingReadError = false
    private var refreshVersion = 0
    private var historyTask: Task<Void, Never>?
    private var currentRecognitionReceipts: Set<UUID> = []
    private var goalMutationID: UUID?

    private func invalidateHistory() {
        refreshVersion += 1
        historyTask?.cancel(); historyTask = nil
        intakeHistory = nil; intakeHistoryState = .idle
    }
    var isConfigured: Bool { service != nil }
    var isOffline: Bool { configuration.offline }
    var canLog: Bool { service != nil && pending == nil && !pendingReadError && !isSaving && !isSettingGoal }
    private var destination: String { configuration.offline ? "offline" : configuration.baseURL }

    init(service: (any BeverageService)? = nil, pendingURL: URL? = nil, configuration: APIConfiguration = .load(),
         calibrationHistory: CalibrationHistoryStore? = nil, goalProfiles: GoalProfileStore? = nil) {
        self.configuration = configuration
        self.calibrationHistory = calibrationHistory ?? CalibrationHistoryStore()
        self.calibrationHistory.configure(configuration)
        self.goalProfiles = goalProfiles ?? Self.makeGoalProfiles()
        self.goalProfiles.configure(configuration)
        let folder = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        self.pendingURL = pendingURL ?? Self.makePendingURL(in: folder)
        self.service = service ?? (configuration.offline ? MockBeverageService() : try? HTTPBeverageService(configuration: configuration))
        if FileManager.default.fileExists(atPath: self.pendingURL.path) {
            do {
                let decoder = JSONDecoder(); decoder.dateDecodingStrategy = .iso8601
                pending = try decoder.decode(PendingBeverage.self, from: Data(contentsOf: self.pendingURL))
            } catch {
                pendingReadError = true
                state = .failed("The saved pending beverage could not be read. Logging is blocked to avoid duplicate entries; preserve the pending file for recovery.")
            }
        }
    }

    private static func makePendingURL(in folder: URL) -> URL {
        #if DEBUG
        if let suite = ProcessInfo.processInfo.environment["HYDRA_TEST_CONTEXT_SUITE"],
           suite.hasPrefix("HydraUITests."), let id = UUID(uuidString: String(suite.suffix(36))) {
            return folder.appendingPathComponent("HydraAI/pending-tests-v1/\(id.uuidString)/pending-beverage-v1.json")
        }
        #endif
        return folder.appendingPathComponent("HydraAI/pending-beverage-v1.json")
    }

    private static func makeGoalProfiles() -> GoalProfileStore {
        #if DEBUG
        if let suite = ProcessInfo.processInfo.environment["HYDRA_TEST_GOAL_PROFILE_SUITE"],
           suite.hasPrefix("HydraUITests."), let id = UUID(uuidString: String(suite.suffix(36))) {
            let directory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .resolvingSymlinksInPath().appendingPathComponent("HydraAI/goal-profile-tests-v1/\(id.uuidString)", isDirectory: true)
            return GoalProfileStore(directory: directory)
        }
        #endif
        return GoalProfileStore()
    }

    func configure(_ config: APIConfiguration) throws {
        if let pending, pending.destination != (config.offline ? "offline" : config.baseURL) { throw ServiceError.pending }
        let next: any BeverageService = config.offline ? MockBeverageService() : try HTTPBeverageService(configuration: config)
        try config.save()
        invalidateHistory()
        configurationGeneration = UUID()
        // An outstanding PUT still owns its gate even if its connection was replaced.
        currentRecognitionReceipts.removeAll()
        configuration = config; calibrationHistory.configure(config); goalProfiles.configure(config)
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
        guard generation == configurationGeneration else { return false }
        currentRecognitionReceipts.insert(receipt)
        return true
    }

    func add(category: String, consumedMl: Int, at: Date, source: String = "manual", productId: String? = nil, containerMl: Int? = nil, recognitionId: UUID? = nil) async throws {
        guard canLog else { throw ServiceError.pending }
        if let recognitionId, !currentRecognitionReceipts.contains(recognitionId) {
            throw ServiceError.liveRecognitionUnverified
        }
        let request = CreateBeverageRequest(category: category.trimmingCharacters(in: .whitespacesAndNewlines), consumedMl: consumedMl, consumedAt: at, timezone: TimeZone.current.identifier, source: source, recognitionId: recognitionId, productId: productId, containerMl: containerMl)
        try request.validate()
        let item = PendingBeverage(key: UUID(), request: request, destination: destination)
        do {
            let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
            try FileManager.default.createDirectory(at: pendingURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            try encoder.encode(item).write(to: pendingURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
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
        guard let service, !isOffline else { throw ServiceError.configuration }
        return try await service.exportData()
    }

    /// Erases every log and the goal on the backend; blocked while a creation is pending.
    func deleteAllData() async throws -> Int {
        guard canLog, let service, !isOffline else { throw ServiceError.pending }
        isSaving = true
        defer { isSaving = false }
        // Clear all local manual profiles even if the backend is unavailable. Fail visibly if local erasure fails.
        var localError: Error?
        do { try calibrationHistory.deleteAll() } catch { localError = error }
        do { try goalProfiles.deleteAll() } catch { if localError == nil { localError = error } }
        if let localError { throw localError }
        let count = try await service.deleteAllData()
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
