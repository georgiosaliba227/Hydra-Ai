import Foundation
import CryptoKit

/// Real records stored on this iPhone, separate from the synthetic offline demo.
/// Every mutation commits its idempotency record and beverage in one protected write.
actor LocalBeverageService: BeverageService {
    private let fileURL: URL
    private let now: @Sendable () -> Date
    // Multiple service instances can exist while settings replace the active one.
    // Keep their read/modify/write transactions atomic within this app process.
    private static let fileLock = NSLock()

    private struct Mutation: Codable {
        let key: UUID
        let requestDigest: String
    }
    private struct Records: Codable {
        let version: String
        var beverages: [BeverageLog]
        var dailyGoalMl: Int?
        var mutations: [Mutation]
        static var empty: Records {
            Records(version: "local-beverages-v1", beverages: [], dailyGoalMl: nil, mutations: [])
        }
    }

    init(fileURL: URL? = nil, now: @escaping @Sendable () -> Date = { .now }) {
        self.now = now
        let folder = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        self.fileURL = fileURL ?? folder.appendingPathComponent("HydraAI/local-beverages-v1.json")
    }

    private func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        // Normalize subsecond dates exactly as the durable pending mutation does.
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }
    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder(); decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
    private func transaction<T>(_ body: () throws -> T) rethrows -> T {
        Self.fileLock.lock(); defer { Self.fileLock.unlock() }
        return try body()
    }

    private func read() throws -> Records {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return .empty }
        do {
            try OnDeviceProtectedFile.protectExisting(fileURL)
            let records = try decoder().decode(Records.self, from: Data(contentsOf: fileURL))
            guard records.version == "local-beverages-v1",
                  Set(records.beverages.map(\.id)).count == records.beverages.count,
                  Set(records.mutations.map(\.key)).count == records.mutations.count,
                  records.dailyGoalMl.map({ (100...10_000).contains($0) }) ?? true else { throw ServiceError.storage }
            for log in records.beverages { try validate(log) }
            guard Set(records.beverages.map(\.id)).isSubset(of: Set(records.mutations.map(\.key))),
                  records.mutations.allSatisfy({ $0.requestDigest.count == 64 && $0.requestDigest.allSatisfy { "0123456789abcdef".contains($0) } }) else { throw ServiceError.storage }
            return records
        } catch { throw ServiceError.storage }
    }
    private func write(_ records: Records) throws {
        do {
            try OnDeviceProtectedFile.write(encoder().encode(records), to: fileURL)
        } catch { throw ServiceError.storage }
    }
    private func validate(_ request: CreateBeverageRequest) throws {
        try request.validate(now: now(), allowOnDevice: true)
        // Server/mock receipts must never become real on-phone recognition logs.
        guard request.recognitionFeedback == nil,
              request.source != "confirmed_recognition" || request.onDeviceRecognition != nil else { throw ServiceError.invalidResponse }
    }
    private func validate(_ log: BeverageLog) throws {
        guard log.revision > 0, !log.category.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              log.category.count <= 80, (1...5000).contains(log.consumedMl),
              TimeZone(identifier: log.timezone) != nil,
              DateBoundary.onOrAfter(log.consumedAt, Date(timeIntervalSince1970: 946_684_800)),
              ["manual", "confirmed_recognition"].contains(log.source),
              log.consumptionAssumption.map({ ["entire_liquid", "full_container"].contains($0) }) ?? true,
              log.beverageType.map({ !$0.isEmpty && $0.count <= 80 }) ?? true else { throw ServiceError.storage }
        if let capacity=log.containerMl {
            guard (1...5000).contains(capacity),log.consumedMl<=capacity else { throw ServiceError.storage }
        }
        if log.consumptionAssumption=="full_container" {
            guard log.containerMl==log.consumedMl else { throw ServiceError.storage }
        }
        if log.source == "confirmed_recognition" {
            guard let provenance = log.onDeviceRecognition else { throw ServiceError.storage }
            try provenance.validatePersisted()
        } else if log.onDeviceRecognition != nil || log.consumptionAssumption != nil || log.beverageType != nil || log.containerMl != nil { throw ServiceError.storage }
    }
    private func makeLog(_ request: CreateBeverageRequest, key: UUID) -> BeverageLog {
        BeverageLog(id: key, consumedMl: request.consumedMl, category: request.category,
            consumedAt: request.consumedAt, timezone: request.timezone, source: request.source, revision: 1,
            consumptionAssumption: request.consumptionAssumption, beverageType: request.beverageType,
            onDeviceRecognition: request.onDeviceRecognition, containerMl: request.containerMl)
    }

    func listBeverages() async throws -> [BeverageLog] {
        try transaction { try read().beverages.sorted { $0.consumedAt > $1.consumedAt } }
    }

    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog {
        try validate(request)
        return try transaction {
            let submitted = try decoder().decode(CreateBeverageRequest.self, from: encoder().encode(request))
            var records = try read()
            let digest = SHA256.hash(data: try encoder().encode(submitted)).map { String(format: "%02x", $0) }.joined()
            if let mutation = records.mutations.first(where: { $0.key == idempotencyKey }) {
                guard mutation.requestDigest == digest else { throw ServiceError.pending }
                guard let existing = records.beverages.first(where: { $0.id == idempotencyKey }) else { throw ServiceError.server(410) }
                return existing
            }
            let log = makeLog(submitted, key: idempotencyKey)
            records.beverages.append(log)
            records.mutations.append(Mutation(key: idempotencyKey, requestDigest: digest))
            try write(records)
            return log
        }
    }

    func updateBeverage(id: UUID, _ request: UpdateBeverageRequest) async throws -> BeverageLog {
        try request.validate(now: now())
        return try transaction {
            var records = try read()
            guard let index = records.beverages.firstIndex(where: { $0.id == id }) else { throw ServiceError.server(404) }
            let current = records.beverages[index]
            guard current.revision == request.revision else { throw ServiceError.server(409) }
            let updated = BeverageLog(id: id, consumedMl: request.consumedMl ?? current.consumedMl,
                category: request.category ?? current.category, consumedAt: request.consumedAt ?? current.consumedAt,
                timezone: current.timezone, source: current.source, revision: current.revision + 1,
                consumptionAssumption: request.consumedMl.map({ $0 != current.consumedMl }) == true ? nil : current.consumptionAssumption,
                beverageType: current.beverageType, onDeviceRecognition: current.onDeviceRecognition,
                containerMl: current.containerMl.flatMap { (request.consumedMl ?? current.consumedMl)<=$0 ? $0 : nil })
            try validate(updated)
            records.beverages[index] = updated
            try write(records)
            return updated
        }
    }

    func deleteBeverage(id: UUID, revision: Int) async throws {
        try transaction {
            var records = try read()
            if let current = records.beverages.first(where: { $0.id == id }), current.revision != revision { throw ServiceError.server(409) }
            records.beverages.removeAll { $0.id == id }
            // Keep only the request digest and key, never deleted beverage content.
            // A delayed retry is rejected instead of resurrecting the entry.
            try write(records)
        }
    }

    func goalSettings() async throws -> GoalSettings {
        try transaction { GoalSettings(version: "settings-v1", daily_beverage_goal_ml: try read().dailyGoalMl, goal_basis: "user_confirmed") }
    }

    func updateGoal(_ milliliters: Int?) async throws -> GoalSettings {
        if let milliliters { guard (100...10_000).contains(milliliters) else { throw BeverageValidationError.invalidVolume } }
        return try transaction {
            var records = try read(); records.dailyGoalMl = milliliters
            try write(records)
            return GoalSettings(version: "settings-v1", daily_beverage_goal_ml: milliliters, goal_basis: "user_confirmed")
        }
    }

    func dailySummary(date: String, timezone: String) async throws -> DailySummary {
        guard let zone = TimeZone(identifier: timezone) else { throw ServiceError.invalidResponse }
        let formatter = DateFormatter(); formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = zone; formatter.dateFormat = "yyyy-MM-dd"
        formatter.isLenient = false
        guard let day = formatter.date(from: date), formatter.string(from: day) == date else { throw ServiceError.invalidResponse }
        return try transaction {
            let records = try read()
            let logs = records.beverages.filter { formatter.string(from: $0.consumedAt) == date }
            let total = logs.reduce(0.0) { $0 + Double($1.consumedMl) }
            let goal = records.dailyGoalMl.map { DailySummary.Goal(dailyBeverageGoalMl: $0, basis: "user_confirmed", remainingMl: max(0, Double($0) - total), progressRatio: total / Double($0)) }
            return DailySummary(localDate: date, timezone: timezone, beverageTotalMl: total,
                estimatedWaterMl: logs.isEmpty ? 0 : nil, forecastStatus: "insufficient_data", goal: goal)
        }
    }

    func exportData() async throws -> Data {
        struct Settings: Encodable {
            let daily_beverage_goal_ml: Int?
            let goal_basis = "user_confirmed"
        }
        struct Export: Encodable {
            let version = "export-v1"
            let source = "on_device"
            let beverages: [BeverageLog]
            let settings: Settings
        }
        return try transaction {
            let records = try read()
            return try encoder().encode(Export(beverages: records.beverages, settings: Settings(daily_beverage_goal_ml: records.dailyGoalMl)))
        }
    }

    func deleteAllData() async throws -> Int {
        try transaction {
            let count = try read().beverages.count
            try write(.empty)
            return count
        }
    }
}
