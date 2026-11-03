import Foundation

protocol BeverageService: Sendable {
    func listBeverages() async throws -> [BeverageLog]
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog
    func dailySummary(date: String, timezone: String) async throws -> DailySummary
    func workoutForecast(_ request: WorkoutForecastRequest) async throws -> WorkoutForecast
    func intakeHistory(date: String, timezone: String) async throws -> IntakeHistoryForecast
    func recordedWonderComparison(scenario: String) async throws -> HydrationContextComparison
    func updateBeverage(id: UUID, _ request: UpdateBeverageRequest) async throws -> BeverageLog
    func assistantQuestions() async throws -> [AssistantQuestion]
    func goalSettings() async throws -> GoalSettings
    func exportData() async throws -> Data
    func deleteAllData() async throws -> Int
    func updateGoal(_ milliliters: Int?) async throws -> GoalSettings
    func askAssistant(_ request: AssistantRequest) async throws -> AssistantAnswer
    func wonderTrendPreview(timezone: String) async throws -> TrendPreview
    func explainTrends(_ request: TrendExplanationRequest) async throws -> TrendExplanationResponse
    /// Succeeds when the log is gone, including when it was already deleted.
    func deleteBeverage(id: UUID, revision: Int) async throws
}

/// Offline stand-in for GET and POST /v1/beverages. It round-trips the same
/// snake_case JSON payloads while the authenticated backend is being built.
actor MockBeverageService: BeverageService {
    private let fileURL: URL
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    init(fileURL: URL? = nil) {
        let folder = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        self.fileURL = fileURL ?? folder.appendingPathComponent("HydraAI/mock-beverages-v1.json")
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        self.encoder = encoder
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder
    }

    func listBeverages() throws -> [BeverageLog] {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return [] }
        return try decoder.decode([BeverageLog].self, from: Data(contentsOf: fileURL))
            .sorted { $0.consumedAt > $1.consumedAt }
    }

    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) throws -> BeverageLog {
        try request.validate()
        // Encode and decode to exercise the planned v1 wire shape in mock mode.
        let submitted = try decoder.decode(CreateBeverageRequest.self, from: encoder.encode(request))
        let log = BeverageLog(
            id: idempotencyKey, consumedMl: submitted.consumedMl, category: submitted.category,
            consumedAt: submitted.consumedAt, timezone: submitted.timezone,
            source: submitted.source, revision: 1
        )
        var logs = try listBeverages()
        if let existing = logs.first(where: { $0.id == idempotencyKey }) {
            guard existing == log else { throw ServiceError.pending }; return existing
        }
        logs.append(log)
        try save(logs)
        return log
    }

    func updateBeverage(id: UUID, _ request: UpdateBeverageRequest) throws -> BeverageLog {
        try request.validate()
        var logs = try listBeverages()
        guard let index = logs.firstIndex(where: { $0.id == id }) else { throw ServiceError.server(404) }
        let current = logs[index]
        guard current.revision == request.revision else { throw ServiceError.server(409) }
        let updated = BeverageLog(id: id, consumedMl: request.consumedMl ?? current.consumedMl,
                                  category: request.category ?? current.category,
                                  consumedAt: request.consumedAt ?? current.consumedAt, timezone: current.timezone,
                                  source: current.source, revision: current.revision + 1)
        logs[index] = updated
        try save(logs)
        return updated
    }

    func deleteBeverage(id: UUID, revision: Int) throws {
        let logs = try listBeverages()
        if let current = logs.first(where: { $0.id == id }), current.revision != revision { throw ServiceError.server(409) }
        try save(logs.filter { $0.id != id })
    }

    private func save(_ logs: [BeverageLog]) throws {
        try FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try encoder.encode(logs).write(to: fileURL, options: .atomic)
    }
}


extension BeverageService {
    func workoutForecast(_ request: WorkoutForecastRequest) async throws -> WorkoutForecast {
        throw ServiceError.invalidResponse
    }

    func intakeHistory(date: String, timezone: String) async throws -> IntakeHistoryForecast {
        throw ServiceError.invalidResponse
    }

    func recordedWonderComparison(scenario: String) async throws -> HydrationContextComparison {
        throw ServiceError.invalidResponse
    }

    func updateBeverage(id: UUID, _ request: UpdateBeverageRequest) async throws -> BeverageLog {
        throw ServiceError.invalidResponse
    }

    func deleteBeverage(id: UUID, revision: Int) async throws {
        throw ServiceError.invalidResponse
    }

    func assistantQuestions() async throws -> [AssistantQuestion] {
        throw ServiceError.invalidResponse
    }

    func goalSettings() async throws -> GoalSettings {
        throw ServiceError.invalidResponse
    }

    func exportData() async throws -> Data {
        throw ServiceError.invalidResponse
    }

    func deleteAllData() async throws -> Int {
        throw ServiceError.invalidResponse
    }

    func updateGoal(_ milliliters: Int?) async throws -> GoalSettings {
        throw ServiceError.invalidResponse
    }

    func askAssistant(_ request: AssistantRequest) async throws -> AssistantAnswer {
        throw ServiceError.invalidResponse
    }

    func wonderTrendPreview(timezone: String) async throws -> TrendPreview {
        throw ServiceError.invalidResponse
    }

    func explainTrends(_ request: TrendExplanationRequest) async throws -> TrendExplanationResponse {
        throw ServiceError.invalidResponse
    }

    func createBeverage(_ request: CreateBeverageRequest) async throws -> BeverageLog {
        try await createBeverage(request, idempotencyKey: UUID())
    }
}

extension MockBeverageService {
    private var goalFileURL: URL { fileURL.deletingPathExtension().appendingPathExtension("goal.json") }

    func goalSettings() async throws -> GoalSettings { try loadGoal() }

    private func loadGoal() throws -> GoalSettings {
        guard FileManager.default.fileExists(atPath: goalFileURL.path) else {
            return GoalSettings(version: "settings-v1", daily_beverage_goal_ml: nil, goal_basis: "user_confirmed")
        }
        let settings = try decoder.decode(GoalSettings.self, from: Data(contentsOf: goalFileURL))
        guard settings.version == "settings-v1", settings.goal_basis == "user_confirmed",
              settings.daily_beverage_goal_ml.map({ (100...10_000).contains($0) }) ?? true else {
            throw ServiceError.invalidResponse
        }
        return settings
    }

    func updateGoal(_ milliliters: Int?) async throws -> GoalSettings {
        guard milliliters.map({ (100...10_000).contains($0) }) ?? true else {
            throw BeverageValidationError.invalidVolume
        }
        let settings = GoalSettings(version: "settings-v1", daily_beverage_goal_ml: milliliters, goal_basis: "user_confirmed")
        try FileManager.default.createDirectory(at: goalFileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try encoder.encode(settings).write(to: goalFileURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        return settings
    }

    func dailySummary(date: String, timezone: String) throws -> DailySummary {
        guard let zone = TimeZone(identifier: timezone) else { throw ServiceError.invalidResponse }
        let formatter = DateFormatter(); formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = zone; formatter.dateFormat = "yyyy-MM-dd"
        let logs = try listBeverages().filter { formatter.string(from: $0.consumedAt) == date }
        let total = Double(logs.reduce(0) { $0 + $1.consumedMl })
        let goal = try loadGoal().daily_beverage_goal_ml.map { milliliters in
            DailySummary.Goal(dailyBeverageGoalMl: milliliters, basis: "user_confirmed",
                              remainingMl: max(Double(milliliters) - total, 0), progressRatio: total / Double(milliliters))
        }
        return DailySummary(localDate: date, timezone: timezone, beverageTotalMl: total,
                            estimatedWaterMl: logs.isEmpty ? 0 : nil, forecastStatus: "insufficient_data", goal: goal)
    }
}
