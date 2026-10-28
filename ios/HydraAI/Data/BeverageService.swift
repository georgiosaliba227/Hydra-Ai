import Foundation

protocol BeverageService: Sendable {
    func listBeverages() async throws -> [BeverageLog]
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog
    func dailySummary(date: String, timezone: String) async throws -> DailySummary
    func intakeHistory(date: String, timezone: String) async throws -> IntakeHistoryForecast
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
        try FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try encoder.encode(logs).write(to: fileURL, options: .atomic)
        return log
    }
}


extension BeverageService {
    func intakeHistory(date: String, timezone: String) async throws -> IntakeHistoryForecast {
        throw ServiceError.invalidResponse
    }

    func createBeverage(_ request: CreateBeverageRequest) async throws -> BeverageLog {
        try await createBeverage(request, idempotencyKey: UUID())
    }
}

extension MockBeverageService {
    func dailySummary(date: String, timezone: String) throws -> DailySummary {
        guard let zone = TimeZone(identifier: timezone) else { throw ServiceError.invalidResponse }
        let formatter = DateFormatter(); formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = zone; formatter.dateFormat = "yyyy-MM-dd"
        let logs = try listBeverages().filter { formatter.string(from: $0.consumedAt) == date }
        return DailySummary(localDate: date, timezone: timezone, beverageTotalMl: Double(logs.reduce(0) { $0 + $1.consumedMl }), estimatedWaterMl: logs.isEmpty ? 0 : nil, forecastStatus: "insufficient_data")
    }
}
