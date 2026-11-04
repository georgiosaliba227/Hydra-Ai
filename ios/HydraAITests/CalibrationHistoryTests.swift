import XCTest
@testable import HydraAI

final class CalibrationHistoryTests: XCTestCase {
    private let now = ISO8601DateFormatter().date(from: "2026-11-02T12:00:00Z")!
    private func sample(id: UUID = UUID(), observed: String = "2026-11-01T12:00:00Z") -> WorkoutForecastRequest.Sample {
        .init(event_id: id, observed_at: observed,
              conditions: .init(activity: "running", intensity: "moderate", temperature_c: 22, humidity_percent: 55),
              measurement: .init(pre_mass_kg: 70, post_mass_kg: 69.6, consumed_ml: 200, urine_ml: 0, duration_minutes: 45),
              errors: .init(pre_mass_kg: 0.05, post_mass_kg: 0.05, consumed_ml: 10, urine_ml: 0, duration_minutes: 1))
    }
    private func folder() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }
    private var configuration: APIConfiguration { .init(baseURL: "http://127.0.0.1:8000", token: String(repeating: "a", count: 32), offline: false) }

    @MainActor func testNoFileUntilExplicitSaveAndRestoresOnlyOriginalConnection() throws {
        let folder = try folder(), scope = UUID(), otherScope = UUID()
        let history = CalibrationHistoryStore(directory: folder, scopeResolver: { _ in scope })
        history.configure(configuration)
        XCTAssertFalse(FileManager.default.fileExists(atPath: folder.path))
        XCTAssertThrowsError(try history.save([sample()], consent: false, now: now))
        XCTAssertFalse(FileManager.default.fileExists(atPath: folder.path))
        try history.save([sample()], consent: true, now: now)
        let file = folder.appendingPathComponent(scope.uuidString + ".json")
        XCTAssertEqual(try file.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
        // Simulator does not expose physical data-protection attributes; exercise this assertion on a device.
        #if !targetEnvironment(simulator)
        let attributes = try FileManager.default.attributesOfItem(atPath: file.path)
        let protection = (attributes[.protectionKey] as? FileProtectionType)?.rawValue ?? (attributes[.protectionKey] as? String)
        XCTAssertEqual(protection, FileProtectionType.complete.rawValue)
        #endif
        let restored = CalibrationHistoryStore(directory: folder, scopeResolver: { _ in scope })
        restored.configure(configuration, now: now)
        XCTAssertEqual(restored.records.count, 1)
        XCTAssertEqual(restored.records.first?.measurement.pre_mass_kg, 70)
        let other = CalibrationHistoryStore(directory: folder, scopeResolver: { _ in otherScope })
        other.configure(configuration, now: now)
        XCTAssertTrue(other.records.isEmpty)
        XCTAssertEqual(restored.records.count, 1)
        let exported = String(decoding: try restored.exportData(now: now), as: UTF8.self)
        for prohibited in ["127.0.0.1", configuration.token, scope.uuidString, "consent", "heart_rate", "explanation"] {
            XCTAssertFalse(exported.contains(prohibited), prohibited)
        }
        XCTAssertTrue(exported.contains("user_entered_manual_weighing"))
        XCTAssertTrue(exported.contains("user_reported_instrument_error_bounds"))
    }

    func testValidationRejectsDuplicateEventsDuplicateInstantsFutureAndInvalidBounds() throws {
        let id = UUID()
        XCTAssertThrowsError(try CalibrationHistoryValidation.validate([sample(id: id), sample(id: id, observed: "2026-10-31T12:00:00Z")], now: now))
        XCTAssertThrowsError(try CalibrationHistoryValidation.validate([sample(), sample(observed: "2026-11-01T07:00:00-05:00")], now: now))
        XCTAssertThrowsError(try CalibrationHistoryValidation.validate([sample(observed: "2026-11-03T12:00:00Z")], now: now))
        XCTAssertThrowsError(try CalibrationHistoryValidation.validate([sample(observed: "2026-11-01T12:00:00")], now: now))
        let original = sample()
        let bad = WorkoutForecastRequest.Sample(event_id: UUID(), observed_at: original.observed_at,
            conditions: .init(activity: "running", intensity: "moderate", temperature_c: .nan, humidity_percent: 55),
            measurement: original.measurement, errors: original.errors)
        XCTAssertThrowsError(try CalibrationHistoryValidation.validate([bad], now: now))
        let uncertain = WorkoutForecastRequest.Sample(event_id: UUID(), observed_at: original.observed_at, conditions: original.conditions,
            measurement: original.measurement,
            errors: .init(pre_mass_kg: 0, post_mass_kg: 0, consumed_ml: 0, urine_ml: 0, duration_minutes: 45))
        XCTAssertThrowsError(try CalibrationHistoryValidation.validate([uncertain], now: now))
    }

    func testDecoderRejectsForgedMeasurementProvenanceAndProtocol() throws {
        let encoded = try JSONEncoder().encode(sample())
        var body = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        var measurement = try XCTUnwrap(body["measurement"] as? [String: Any])
        for (key, value) in [("protocol_confirmed", false as Any), ("provenance", ["healthkit"] as Any)] {
            var changed = measurement; changed[key] = value; body["measurement"] = changed
            XCTAssertThrowsError(try JSONDecoder().decode(WorkoutForecastRequest.Sample.self, from: JSONSerialization.data(withJSONObject: body)))
        }
        measurement["provenance"] = ["user_entered_manual_weighing"]
        body["measurement"] = measurement
        XCTAssertNoThrow(try JSONDecoder().decode(WorkoutForecastRequest.Sample.self, from: JSONSerialization.data(withJSONObject: body)))
        var errors = body["errors"] as! [String: Any]; errors["provenance"] = ["healthkit"]
        body["errors"] = errors
        XCTAssertThrowsError(try JSONDecoder().decode(WorkoutForecastRequest.Sample.self, from: JSONSerialization.data(withJSONObject: body)))
    }

    @MainActor func testCorruptionBlocksOverwriteUntilExplicitDeleteAndDeletionSurvivesRestart() throws {
        let folder = try folder(), scope = UUID()
        let history = CalibrationHistoryStore(directory: folder, scopeResolver: { _ in scope })
        history.configure(configuration)
        try history.save([sample()], consent: true, now: now)
        let file = folder.appendingPathComponent(scope.uuidString + ".json")
        let corrupt = Data("broken history".utf8)
        try corrupt.write(to: file)
        history.configure(configuration, now: now)
        XCTAssertNotNil(history.errorMessage)
        XCTAssertThrowsError(try history.save([sample()], consent: true, now: now))
        XCTAssertEqual(try Data(contentsOf: file), corrupt)
        try history.deleteAll()
        XCTAssertFalse(FileManager.default.fileExists(atPath: folder.path))
        XCTAssertNil(history.errorMessage)
        try history.save([sample()], consent: true, now: now)
        try history.delete(ids: Set(history.records.map(\.event_id)), now: now)
        let restored = CalibrationHistoryStore(directory: folder, scopeResolver: { _ in scope })
        restored.configure(configuration, now: now)
        XCTAssertTrue(restored.records.isEmpty)
    }

    @MainActor func testCapRejectsThirtyThirdWithoutReplacingSavedRecords() throws {
        let folder = try folder(), scope = UUID()
        let history = CalibrationHistoryStore(directory: folder, scopeResolver: { _ in scope })
        history.configure(configuration)
        let samples = (0..<32).map { sample(observed: ISO8601DateFormatter().string(from: now.addingTimeInterval(Double(-$0 - 1) * 3600))) }
        try history.save(samples, consent: true, now: now)
        XCTAssertThrowsError(try history.save([sample(observed: "2026-10-01T12:00:00Z")], consent: true, now: now))
        XCTAssertEqual(history.records.count, 32)
        history.configure(configuration, now: now)
        XCTAssertEqual(history.records.count, 32)
    }

    func testRealKeychainScopeIsStableForNormalizedConnectionAndDifferentForChangedToken() throws {
        let host = "profile-\(UUID().uuidString.lowercased()).local"
        let original = APIConfiguration(baseURL: "http://\(host)", token: String(repeating: "a", count: 32), offline: false)
        let normalized = APIConfiguration(baseURL: "http://\(host):80/", token: original.token, offline: false)
        let changedUser = APIConfiguration(baseURL: original.baseURL, token: String(repeating: "b", count: 32), offline: false)
        let first = try CalibrationConnectionScope.resolve(original)
        XCTAssertEqual(try CalibrationConnectionScope.resolve(normalized), first)
        XCTAssertNotEqual(try CalibrationConnectionScope.resolve(changedUser), first)
        XCTAssertEqual(try CalibrationConnectionScope.resolve(original), first)
    }

    @MainActor func testSettingsDeletionClearsEveryLocalProfileEvenWhenBackendDeletionFails() async throws {
        let folder = try folder(), scope = UUID()
        let history = CalibrationHistoryStore(directory: folder, scopeResolver: { _ in scope })
        let store = BeverageStore(service: FailedDeleteService(), pendingURL: folder.appendingPathComponent("pending.json"),
                                  configuration: configuration, calibrationHistory: history)
        try history.save([sample()], consent: true, now: now)
        do { _ = try await store.deleteAllData(); XCTFail("Backend failure must remain visible") }
        catch { }
        XCTAssertTrue(history.records.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: folder.path))
    }

    @MainActor func testUnavailableDirectoryFailsVisiblyWithoutCreatingHistory() throws {
        let folder = try folder()
        try Data("not a directory".utf8).write(to: folder)
        let history = CalibrationHistoryStore(directory: folder, scopeResolver: { _ in UUID() })
        history.configure(configuration)
        XCTAssertThrowsError(try history.save([sample()], consent: true, now: now))
        XCTAssertNotNil(history.errorMessage)
        XCTAssertEqual(try Data(contentsOf: folder), Data("not a directory".utf8))
    }
}

private actor FailedDeleteService: BeverageService {
    func listBeverages() async throws -> [BeverageLog] { [] }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw ServiceError.invalidResponse }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary { throw ServiceError.invalidResponse }
    func deleteAllData() async throws -> Int { throw URLError(.notConnectedToInternet) }
}
