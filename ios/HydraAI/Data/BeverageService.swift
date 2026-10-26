import Foundation

protocol BeverageService: Sendable {
    func listBeverages() async throws -> [BeverageLog]
    func createBeverage(_ request: CreateBeverageRequest) async throws -> BeverageLog
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

    func createBeverage(_ request: CreateBeverageRequest) throws -> BeverageLog {
        try request.validate()
        // Encode and decode to exercise the planned v1 wire shape in mock mode.
        let submitted = try decoder.decode(CreateBeverageRequest.self, from: encoder.encode(request))
        let log = BeverageLog(
            id: UUID(), consumedMl: submitted.consumedMl, category: submitted.category,
            consumedAt: submitted.consumedAt, timezone: submitted.timezone,
            source: "manual", revision: 1
        )
        var logs = try listBeverages()
        logs.append(log)
        try FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try encoder.encode(logs).write(to: fileURL, options: .atomic)
        return log
    }
}
