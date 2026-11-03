import Foundation
import CryptoKit
import Security

/// Only explicitly entered manual measurements can cross this persistence boundary.
/// No HealthKit records, backend credentials, processing consent, or explanations are retained.
enum CalibrationHistoryError: LocalizedError {
    case consent, invalid, duplicate, limit, unavailable, corrupt
    var errorDescription: String? {
        switch self {
        case .consent: "Choose Save on this iPhone before saving manual measurements."
        case .invalid: "A manual measurement has an invalid date, condition, value or error bound. Check the measurements before using them."
        case .duplicate: "A measurement with that event or completion time already exists. It cannot count as new evidence."
        case .limit: "History holds at most 32 measurements. Delete a saved measurement before adding another."
        case .unavailable: "Saved manual history is unavailable. Nothing will be overwritten. Retry when this iPhone is unlocked, or delete saved history explicitly."
        case .corrupt: "Saved manual history could not be validated. Nothing will be overwritten. You can delete saved history explicitly to start again."
        }
    }
}

enum CalibrationHistoryValidation {
    static func date(_ timestamp: String) -> Date? {
        guard timestamp.range(of: #"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"#, options: .regularExpression) != nil else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: timestamp) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: timestamp)
    }

    static func validate(_ samples: [WorkoutForecastRequest.Sample], now: Date = .now) throws {
        guard samples.count <= 32 else { throw CalibrationHistoryError.limit }
        var events = Set<UUID>(), instants = Set<Date>()
        for sample in samples {
            guard let observed = date(sample.observed_at), observed <= now else { throw CalibrationHistoryError.invalid }
            guard events.insert(sample.event_id).inserted, instants.insert(observed).inserted else { throw CalibrationHistoryError.duplicate }
            let c = sample.conditions, m = sample.measurement, e = sample.errors
            func valid(_ value: Double, _ lower: Double, _ upper: Double) -> Bool { value.isFinite && (lower...upper).contains(value) }
            guard ["running", "cycling", "walking", "strength", "other"].contains(c.activity),
                  ["low", "moderate", "high"].contains(c.intensity),
                  valid(c.temperature_c, -60, 60), valid(c.humidity_percent, 0, 100),
                  valid(m.pre_mass_kg, 0.01, 500), valid(m.post_mass_kg, 0.01, 500),
                  valid(m.consumed_ml, 0, 50000), valid(m.urine_ml, 0, 50000), valid(m.duration_minutes, 0.01, 1440),
                  valid(e.pre_mass_kg, 0, 500), valid(e.post_mass_kg, 0, 500),
                  valid(e.consumed_ml, 0, 50000), valid(e.urine_ml, 0, 50000),
                  valid(e.duration_minutes, 0, 1440), e.duration_minutes < m.duration_minutes,
                  m.protocol_confirmed, m.provenance == ["user_entered_manual_weighing"],
                  e.provenance == ["user_reported_instrument_error_bounds"] else { throw CalibrationHistoryError.invalid }
        }
    }
}

// A synthesized decoder would silently ignore immutable fields with default values. Validate them instead.
extension WorkoutForecastRequest.Measurement {
    enum CodingKeys: String, CodingKey { case pre_mass_kg, post_mass_kg, consumed_ml, urine_ml, duration_minutes, protocol_confirmed, provenance }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        guard try c.decode(Bool.self, forKey: .protocol_confirmed),
              try c.decode([String].self, forKey: .provenance) == ["user_entered_manual_weighing"] else { throw CalibrationHistoryError.invalid }
        self.init(pre_mass_kg: try c.decode(Double.self, forKey: .pre_mass_kg), post_mass_kg: try c.decode(Double.self, forKey: .post_mass_kg),
                  consumed_ml: try c.decode(Double.self, forKey: .consumed_ml), urine_ml: try c.decode(Double.self, forKey: .urine_ml),
                  duration_minutes: try c.decode(Double.self, forKey: .duration_minutes))
    }
}
extension WorkoutForecastRequest.Errors {
    enum CodingKeys: String, CodingKey { case pre_mass_kg, post_mass_kg, consumed_ml, urine_ml, duration_minutes, provenance }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        guard try c.decode([String].self, forKey: .provenance) == ["user_reported_instrument_error_bounds"] else { throw CalibrationHistoryError.invalid }
        self.init(pre_mass_kg: try c.decode(Double.self, forKey: .pre_mass_kg), post_mass_kg: try c.decode(Double.self, forKey: .post_mass_kg),
                  consumed_ml: try c.decode(Double.self, forKey: .consumed_ml), urine_ml: try c.decode(Double.self, forKey: .urine_ml),
                  duration_minutes: try c.decode(Double.self, forKey: .duration_minutes))
    }
}

/// The connection binding lives only in this device's Keychain. Filenames use unrelated random UUIDs.
/// A changed token is a different connection; returning to the exact prior connection restores its profile.
enum CalibrationConnectionScope {
    struct Binding: Codable {
        let id: UUID
        let endpoint: String
        let tokenFingerprint: String
    }
    static func resolve(_ configuration: APIConfiguration) throws -> UUID {
        let url = try configuration.validatedURL()
        let endpoint = "\(url.scheme!.lowercased())://\(url.host!.lowercased()):\(url.port ?? (url.scheme == "https" ? 443 : 80))"
        let fingerprint = SHA256.hash(data: Data(configuration.token.utf8)).map { String(format: "%02x", $0) }.joined()
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "HydraAI.manualCalibrationProfiles", kSecAttrAccount as String: "connection-scopes-v1"]
        var read = query; read[kSecReturnData as String] = true
        var result: CFTypeRef?
        let status = SecItemCopyMatching(read as CFDictionary, &result)
        var bindings: [Binding]
        if status == errSecItemNotFound { bindings = [] }
        else {
            guard status == errSecSuccess, let data = result as? Data,
                  let decoded = try? JSONDecoder().decode([Binding].self, from: data) else { throw CalibrationHistoryError.unavailable }
            bindings = decoded
        }
        if let existing = bindings.first(where: { $0.endpoint == endpoint && $0.tokenFingerprint == fingerprint }) { return existing.id }
        let binding = Binding(id: UUID(), endpoint: endpoint, tokenFingerprint: fingerprint)
        bindings.append(binding)
        let attributes: [String: Any] = [kSecValueData as String: try JSONEncoder().encode(bindings),
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        let writeStatus = status == errSecItemNotFound
            ? SecItemAdd(query.merging(attributes) { _, new in new } as CFDictionary, nil)
            : SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        guard writeStatus == errSecSuccess else { throw CalibrationHistoryError.unavailable }
        return binding.id
    }
}

@MainActor final class CalibrationHistoryStore: ObservableObject {
    @Published private(set) var records: [WorkoutForecastRequest.Sample] = []
    @Published private(set) var errorMessage: String?
    private let directory: URL
    private let scopeResolver: (APIConfiguration) throws -> UUID
    private var scope: UUID?
    private var blocked = false
    var canSave: Bool { scope != nil && !blocked }
    private struct Saved: Codable {
        let version: Int
        let profile: UUID
        let records: [WorkoutForecastRequest.Sample]
    }
    private struct Export: Encodable {
        let version = "manual-calibration-export-v1"
        let source = "user_entered_manual_measurements_only"
        let display_timezone = TimeZone.current.identifier
        let records: [WorkoutForecastRequest.Sample]
    }
    init(directory: URL? = nil, scopeResolver: ((APIConfiguration) throws -> UUID)? = nil) {
        self.directory = directory ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("HydraAI/manual-calibration-v1", isDirectory: true)
        self.scopeResolver = scopeResolver ?? CalibrationConnectionScope.resolve
    }
    func configure(_ configuration: APIConfiguration, now: Date = .now) {
        records = []; errorMessage = nil; scope = nil; blocked = false
        guard !configuration.offline, (try? configuration.validatedURL()) != nil else { return }
        do {
            scope = try scopeResolver(configuration)
            try reload(now: now)
        } catch { fail(error) }
    }
    func reload(now: Date = .now) throws {
        guard let scope else { throw CalibrationHistoryError.unavailable }
        let file = directory.appendingPathComponent(scope.uuidString + ".json")
        do {
            if FileManager.default.fileExists(atPath: directory.path) {
                let folder = try directory.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
                guard folder.isDirectory == true, folder.isSymbolicLink != true else { throw CalibrationHistoryError.unavailable }
            }
            guard FileManager.default.fileExists(atPath: file.path) else { records = []; errorMessage = nil; blocked = false; return }
            let values = try file.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey, .isSymbolicLinkKey])
            guard values.isRegularFile == true, values.isSymbolicLink != true, (values.fileSize ?? Int.max) <= 262144 else { throw CalibrationHistoryError.corrupt }
            let saved = try JSONDecoder().decode(Saved.self, from: Data(contentsOf: file))
            guard saved.version == 1, saved.profile == scope else { throw CalibrationHistoryError.corrupt }
            try CalibrationHistoryValidation.validate(saved.records, now: now)
            records = saved.records; errorMessage = nil; blocked = false
        } catch { fail(error); throw error }
    }
    func save(_ samples: [WorkoutForecastRequest.Sample], consent: Bool, now: Date = .now) throws {
        guard consent else { throw CalibrationHistoryError.consent }
        guard canSave else { throw CalibrationHistoryError.unavailable }
        try reload(now: now) // Detect a changed/corrupt file before any write.
        try CalibrationHistoryValidation.validate(samples, now: now)
        var merged = records
        for sample in samples {
            if let prior = merged.first(where: { $0.event_id == sample.event_id }) {
                let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
                guard try encoder.encode(prior) == encoder.encode(sample) else { throw CalibrationHistoryError.duplicate }
            } else { merged.append(sample) }
        }
        try CalibrationHistoryValidation.validate(merged, now: now)
        try persist(merged)
    }
    func delete(ids: Set<UUID>, now: Date = .now) throws {
        guard canSave else { throw CalibrationHistoryError.unavailable }
        try reload(now: now)
        try persist(records.filter { !ids.contains($0.event_id) })
    }
    /// Explicitly clears every connection's local manual history, including unreadable files.
    func deleteAll() throws {
        do {
            if FileManager.default.fileExists(atPath: directory.path) { try FileManager.default.removeItem(at: directory) }
            records = []; blocked = false; errorMessage = nil
        } catch { fail(error); throw CalibrationHistoryError.unavailable }
    }
    func exportData(now: Date = .now) throws -> Data {
        guard canSave else { throw CalibrationHistoryError.unavailable }
        try reload(now: now)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try encoder.encode(Export(records: records))
    }
    private func persist(_ next: [WorkoutForecastRequest.Sample]) throws {
        guard let scope, !blocked else { throw CalibrationHistoryError.unavailable }
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                   attributes: [.protectionKey: FileProtectionType.complete])
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: directory.path)
            var folder = directory, excluded = URLResourceValues(); excluded.isExcludedFromBackup = true
            try folder.setResourceValues(excluded)
            var file = directory.appendingPathComponent(scope.uuidString + ".json")
            let data = try JSONEncoder().encode(Saved(version: 1, profile: scope, records: next))
            try data.write(to: file, options: [.atomic, .completeFileProtection])
            try file.setResourceValues(excluded)
            records = next; errorMessage = nil
        } catch { fail(error); throw CalibrationHistoryError.unavailable }
    }
    private func fail(_ error: Error) {
        records = []; blocked = true
        errorMessage = ((error as? CalibrationHistoryError) ?? .unavailable).localizedDescription
    }
}
