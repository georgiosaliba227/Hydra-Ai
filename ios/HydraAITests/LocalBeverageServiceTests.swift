import XCTest
@testable import HydraAI

final class LocalBeverageServiceTests: XCTestCase {
    private func directory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("hydra-local-\(UUID().uuidString)")
    }
    private func request(_ category: String = "tea", volume: Int = 250) -> CreateBeverageRequest {
        CreateBeverageRequest(category: category, consumedMl: volume, consumedAt: Date(timeIntervalSince1970: 1_700_000_000.123), timezone: "America/New_York", source: "manual")
    }
    private func result(id: UUID = UUID(), model: String = "dinov2-small-beverage-v1", mode: String = "on_device") -> RecognitionResult {
        RecognitionResult(version: "recognition-v1", mode: mode, model: model,
            candidates: [RecognitionCandidate(identity: "Water", productId: nil, containerMl: 500, confidence: "low", uncertaintyReasons: ["Verify the suggestion."])], requiresConfirmation: true, recognitionId: id)
    }

    func testRealLocalSaveIsDurableAndReplayDoesNotDuplicateAfterEditingOrDeleting() async throws {
        let root = directory(); defer { try? FileManager.default.removeItem(at: root) }
        let url = root.appendingPathComponent("real.json"), key = UUID()
        let service = LocalBeverageService(fileURL: url), submitted = request()
        let first = try await service.createBeverage(submitted, idempotencyKey: key)
        let restored = LocalBeverageService(fileURL: url)
        let replay = try await restored.createBeverage(submitted, idempotencyKey: key)
        XCTAssertEqual(first, replay)
        let edit = UpdateBeverageRequest(correcting: first, category: "coffee", consumedMl: 200, consumedAt: first.consumedAt)
        let updated = try await restored.updateBeverage(id: first.id, edit)
        XCTAssertEqual(updated.revision, 2)
        let editedReplay = try await restored.createBeverage(submitted, idempotencyKey: key)
        XCTAssertEqual(editedReplay, updated)
        let edited = try await restored.listBeverages()
        XCTAssertEqual(edited.map(\.consumedMl), [200])
        try await restored.deleteBeverage(id: updated.id, revision: updated.revision)
        do { _ = try await LocalBeverageService(fileURL: url).createBeverage(submitted, idempotencyKey: key); XCTFail("Deleted entry replayed") } catch ServiceError.server(410) { }
        let deleted = try await restored.listBeverages()
        XCTAssertTrue(deleted.isEmpty, "A retry must not resurrect a deleted entry")
        do { _ = try await restored.createBeverage(request("other"), idempotencyKey: key); XCTFail("Conflicting replay accepted") } catch { }
    }

    func testLocalGoalSummaryExportAndDeleteAllSurviveRestart() async throws {
        let root = directory(); defer { try? FileManager.default.removeItem(at: root) }
        let url = root.appendingPathComponent("real.json")
        let service = LocalBeverageService(fileURL: url)
        _ = try await service.createBeverage(request(), idempotencyKey: UUID())
        _ = try await service.updateGoal(2_000)
        let restored = LocalBeverageService(fileURL: url)
        let summary = try await restored.dailySummary(date: "2023-11-14", timezone: "America/New_York")
        XCTAssertEqual(summary.beverageTotalMl, 250)
        XCTAssertNil(summary.estimatedWaterMl)
        XCTAssertEqual(summary.goal?.remainingMl, 1_750)
        XCTAssertEqual(summary.goal?.progressRatio, 0.125)
        let exported = try await restored.exportData()
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: exported) as? [String: Any])
        XCTAssertEqual(object["version"] as? String, "export-v1")
        XCTAssertEqual((object["beverages"] as? [Any])?.count, 1)
        let count = try await restored.deleteAllData()
        XCTAssertEqual(count, 1)
        let after = LocalBeverageService(fileURL: url)
        let logs = try await after.listBeverages(), goal = try await after.goalSettings()
        XCTAssertTrue(logs.isEmpty); XCTAssertNil(goal.daily_beverage_goal_ml)
        let empty = try await after.dailySummary(date: "2023-11-14", timezone: "America/New_York")
        XCTAssertEqual(empty.estimatedWaterMl, 0)
    }

    func testCorruptionBlocksReadWriteAndDeletionWithoutResettingEvidence() async throws {
        let root = directory(); defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let url = root.appendingPathComponent("real.json"), broken = Data("broken".utf8)
        try broken.write(to: url)
        let service = LocalBeverageService(fileURL: url)
        do { _ = try await service.listBeverages(); XCTFail("Corruption ignored") } catch { }
        do { _ = try await service.createBeverage(request(), idempotencyKey: UUID()); XCTFail("Corruption overwritten") } catch { }
        do { _ = try await service.deleteAllData(); XCTFail("Corruption reset") } catch { }
        XCTAssertEqual(try Data(contentsOf: url), broken)
    }

    func testDeletingOneEntryRemovesItsContentAndPreventsResurrection() async throws {
        let root = directory(); defer { try? FileManager.default.removeItem(at: root) }
        let url = root.appendingPathComponent("real.json"), key = UUID()
        let service = LocalBeverageService(fileURL: url), submitted = request("Private beverage name")
        let log = try await service.createBeverage(submitted, idempotencyKey: key)
        try await service.deleteBeverage(id: log.id, revision: log.revision)
        XCTAssertFalse(try String(contentsOf: url, encoding: .utf8).contains("Private beverage name"))
        do { _ = try await service.createBeverage(submitted, idempotencyKey: key); XCTFail("Deleted mutation recreated") } catch ServiceError.server(410) { }
        let logs = try await service.listBeverages(); XCTAssertTrue(logs.isEmpty)
    }

    func testOnDeviceProvenanceSurvivesCorrectionAndExportButCannotEnterHTTPOrDemo() async throws {
        let root = directory(); defer { try? FileManager.default.removeItem(at: root) }
        let original = result().candidates[0]
        var submitted = CreateBeverageRequest(category: "Corrected water", consumedMl: 500, consumedAt: .now, timezone: "UTC", source: "confirmed_recognition", recognitionId: UUID(), containerMl: 500, consumptionAssumption: "full_container")
        submitted.onDeviceRecognition = OnDeviceRecognitionProvenance(modelID: "dinov2-small-beverage-v1", originalCandidate: original, processedAt: .now)
        XCTAssertThrowsError(try submitted.validate(), "Default boundary must reject local provenance before HTTP or mock dispatch")
        let service = LocalBeverageService(fileURL: root.appendingPathComponent("real.json"))
        let first = try await service.createBeverage(submitted, idempotencyKey: UUID())
        let updated = try await service.updateBeverage(id: first.id, UpdateBeverageRequest(correcting: first, category: first.category, consumedMl: 250, consumedAt: first.consumedAt))
        XCTAssertNil(updated.consumptionAssumption)
        XCTAssertEqual(updated.onDeviceRecognition?.originalCandidate.identity, "Water")
        let export = String(decoding: try await service.exportData(), as: UTF8.self)
        XCTAssertTrue(export.contains("dinov2-small-beverage-v1"))
        XCTAssertFalse(export.contains("photo_base64")); XCTAssertFalse(export.contains("synthetic"))
        do { _ = try await MockBeverageService(fileURL: root.appendingPathComponent("demo.json")).createBeverage(submitted, idempotencyKey: UUID()); XCTFail("Real provenance entered demo") } catch { }
        XCTAssertFalse(FileManager.default.fileExists(atPath: root.appendingPathComponent("demo.json").path))
    }

    @MainActor func testOnDeviceReceiptIsRequiredAndBoundToModeModelAndGeneration() async throws {
        let root = directory(); defer { try? FileManager.default.removeItem(at: root) }
        let service = LocalBeverageService(fileURL: root.appendingPathComponent("real.json"))
        let store = BeverageStore(service: service, pendingURL: root.appendingPathComponent("pending.json"), configuration: APIConfiguration(baseURL: "", token: "", offline: false, onDevice: true))
        XCTAssertTrue(store.isOnDevice); XCTAssertTrue(store.isOffline)
        let generation = store.configurationGeneration, valid = result()
        XCTAssertFalse(store.registerRecognitionReceipt(valid.recognitionId!, generation: generation), "Generic server receipts cannot authorize on-device saves")
        XCTAssertFalse(store.registerOnDeviceResult(result(model: "wrong"), generation: generation))
        XCTAssertFalse(store.registerOnDeviceResult(result(mode: "mock"), generation: generation))
        XCTAssertFalse(store.registerOnDeviceResult(valid, generation: UUID()))
        do { try await store.add(category: "water", consumedMl: 500, at: .now, source: "confirmed_recognition", recognitionId: valid.recognitionId); XCTFail("Unauthenticated local result saved") } catch { }
        XCTAssertNil(store.pending)
        XCTAssertTrue(store.registerOnDeviceResult(valid, generation: generation))
        try await store.add(category: "Corrected water", consumedMl: 500, at: .now, source: "confirmed_recognition", containerMl: 500, recognitionId: valid.recognitionId, consumptionAssumption: "full_container")
        XCTAssertEqual(store.logs.first?.onDeviceRecognition?.originalCandidate.identity, "Water")
        XCTAssertEqual(store.logs.first?.category, "Corrected water")
        let export = try await store.exportData(); XCTAssertFalse(export.isEmpty)
        _ = try await store.deleteAllData()
        XCTAssertFalse(store.registerOnDeviceResult(valid, generation: generation))
    }

    @MainActor func testOnDevicePendingRetryRetainsProvenanceAndKeyAndCannotSwitchDestination() async throws {
        let root = directory(); defer { try? FileManager.default.removeItem(at: root) }
        let blocker = root.appendingPathComponent("blocker")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try Data("file prevents directory".utf8).write(to: blocker)
        let localURL = blocker.appendingPathComponent("real.json"), pendingURL = root.appendingPathComponent("pending.json")
        let configuration = APIConfiguration(baseURL: "", token: "", offline: false, onDevice: true)
        let first = BeverageStore(service: LocalBeverageService(fileURL: localURL), pendingURL: pendingURL, configuration: configuration)
        let output = result()
        XCTAssertTrue(first.registerOnDeviceResult(output, generation: first.configurationGeneration))
        do { try await first.add(category: "Water", consumedMl: 500, at: .now, source: "confirmed_recognition", recognitionId: output.recognitionId); XCTFail("Expected unavailable local directory") } catch { }
        let key = try XCTUnwrap(first.pending?.key)
        XCTAssertEqual(first.pending?.destination, "on_device")
        XCTAssertThrowsError(try first.configure(APIConfiguration(baseURL: "", token: "", offline: true)))
        let wrongDestination = BeverageStore(service: LocalBeverageService(fileURL: localURL), pendingURL: pendingURL, configuration: APIConfiguration(baseURL: "", token: "", offline: true))
        do { try await wrongDestination.retryPending(); XCTFail("Local pending sent to demo destination") } catch { }
        try FileManager.default.removeItem(at: blocker)
        let restored = BeverageStore(service: LocalBeverageService(fileURL: localURL), pendingURL: pendingURL, configuration: configuration)
        XCTAssertEqual(restored.pending?.key, key)
        try await restored.retryPending()
        XCTAssertNil(restored.pending)
        XCTAssertEqual(restored.logs.map(\.id), [key])
        XCTAssertEqual(restored.logs.first?.onDeviceRecognition?.originalCandidate.identity, "Water")
    }

    func testLocalServiceRejectsServerRecognitionAndInvalidMetadata() async throws {
        let root = directory(); defer { try? FileManager.default.removeItem(at: root) }
        let service = LocalBeverageService(fileURL: root.appendingPathComponent("real.json"))
        let server = CreateBeverageRequest(category: "water", consumedMl: 200, consumedAt: .now, timezone: "UTC", source: "confirmed_recognition", recognitionId: UUID())
        do { _ = try await service.createBeverage(server, idempotencyKey: UUID()); XCTFail("Server receipt stored as local inference") } catch { }
        var invalid = server
        invalid.onDeviceRecognition = OnDeviceRecognitionProvenance(modelID: "wrong", originalCandidate: result().candidates[0], processedAt: .now)
        do { _ = try await service.createBeverage(invalid, idempotencyKey: UUID()); XCTFail("Wrong model accepted") } catch { }
        do { _ = try await service.updateGoal(99); XCTFail("Invalid goal accepted") } catch { }
    }

    func testDebugLaunchCanSelectOnDeviceWithoutBackendCredentials() {
        let previous = ProcessInfo.processInfo.environment["HYDRA_TEST_ON_DEVICE"]
        setenv("HYDRA_TEST_ON_DEVICE", "1", 1)
        defer { if let previous { setenv("HYDRA_TEST_ON_DEVICE", previous, 1) } else { unsetenv("HYDRA_TEST_ON_DEVICE") } }
        let config = APIConfiguration.load()
        XCTAssertTrue(config.onDevice)
        XCTAssertFalse(config.offline)
    }

    func testLocalRecordsRemainExcludedFromBackupAcrossAtomicReplacements() async throws {
        let root = directory(); defer { try? FileManager.default.removeItem(at: root) }
        let url = root.appendingPathComponent("real.json")
        let service = LocalBeverageService(fileURL: url)
        _ = try await service.createBeverage(request(), idempotencyKey: UUID())
        XCTAssertEqual(try URL(fileURLWithPath: url.path).resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
        _ = try await service.updateGoal(2_000)
        XCTAssertEqual(try URL(fileURLWithPath: url.path).resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        XCTAssertEqual((attributes[.posixPermissions] as? NSNumber)?.intValue, 0o600)
        _ = try await service.deleteAllData()
        XCTAssertEqual(try URL(fileURLWithPath: url.path).resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
    }

    @MainActor func testOnDevicePendingBackupExclusionSurvivesRestartAndSubsequentWrite() async throws {
        let root = directory(); defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let blocker = root.appendingPathComponent("blocked"), pendingURL = root.appendingPathComponent("pending.json")
        try Data("block writes".utf8).write(to: blocker)
        let configuration = APIConfiguration(baseURL: "", token: "", offline: false, onDevice: true)
        let localURL = blocker.appendingPathComponent("real.json")
        let store = BeverageStore(service: LocalBeverageService(fileURL: localURL), pendingURL: pendingURL, configuration: configuration)
        do { try await store.add(category: "Water", consumedMl: 250, at: .now); XCTFail("Write should fail") } catch { }
        XCTAssertNotNil(store.pending)
        XCTAssertEqual(try URL(fileURLWithPath: pendingURL.path).resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
        let originalBytes = try Data(contentsOf: pendingURL), key = try XCTUnwrap(store.pending?.key)
        // Simulate old metadata at restart; repairing metadata must preserve the mutation.
        var unexcludedURL = pendingURL, values = URLResourceValues(); values.isExcludedFromBackup = false
        try unexcludedURL.setResourceValues(values)
        let restored = BeverageStore(service: LocalBeverageService(fileURL: localURL), pendingURL: pendingURL, configuration: configuration)
        XCTAssertEqual(try URL(fileURLWithPath: pendingURL.path).resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
        XCTAssertEqual(try Data(contentsOf: pendingURL), originalBytes)
        XCTAssertEqual(restored.pending?.key, key)
        try FileManager.default.removeItem(at: blocker)
        try await restored.retryPending()
        XCTAssertEqual(restored.logs.map(\.id), [key]); XCTAssertNil(restored.pending)
        let secondBlocker = root.appendingPathComponent("blocked-again")
        try Data("block writes".utf8).write(to: secondBlocker)
        let second = BeverageStore(service: LocalBeverageService(fileURL: secondBlocker.appendingPathComponent("real.json")), pendingURL: pendingURL, configuration: configuration)
        do { try await second.add(category: "Tea", consumedMl: 150, at: .now); XCTFail("Write should fail") } catch { }
        XCTAssertNotNil(second.pending)
        XCTAssertEqual(try URL(fileURLWithPath: pendingURL.path).resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
    }

    func testSavedRecognitionRemainsUsableAfterClockRollbackWhileNewFutureInputIsRejected() async throws {
        let root = directory(); defer { try? FileManager.default.removeItem(at: root) }
        let url = root.appendingPathComponent("real.json")
        let admittedAt = Date(timeIntervalSince1970: 2_000_000_000), earlier = admittedAt.addingTimeInterval(-3_600)
        var submitted = CreateBeverageRequest(category: "Water", consumedMl: 500, consumedAt: admittedAt, timezone: "UTC", source: "confirmed_recognition", recognitionId: UUID(), containerMl: 500, consumptionAssumption: "full_container")
        submitted.onDeviceRecognition = OnDeviceRecognitionProvenance(modelID: "dinov2-small-beverage-v1", originalCandidate: result().candidates[0], processedAt: admittedAt)
        let original = LocalBeverageService(fileURL: url, now: { admittedAt })
        let saved = try await original.createBeverage(submitted, idempotencyKey: UUID())
        let rolledBack = LocalBeverageService(fileURL: url, now: { earlier })
        let logs = try await rolledBack.listBeverages()
        XCTAssertEqual(logs, [saved])
        XCTAssertEqual(logs.first?.containerMl, 500)
        XCTAssertEqual(logs.first?.onDeviceRecognition?.processedAt, admittedAt)
        let export = try await rolledBack.exportData(); XCTAssertFalse(export.isEmpty)
        _ = try await rolledBack.updateGoal(2_000)
        let fresh = CreateBeverageRequest(category: "Tea", consumedMl: 100, consumedAt: earlier, timezone: "UTC", source: "manual")
        _ = try await rolledBack.createBeverage(fresh, idempotencyKey: UUID())
        let futureConsumption = CreateBeverageRequest(category: "Tea", consumedMl: 100, consumedAt: admittedAt, timezone: "UTC", source: "manual")
        do { _ = try await rolledBack.createBeverage(futureConsumption, idempotencyKey: UUID()); XCTFail("New future consumption accepted") } catch BeverageValidationError.futureDate { }
        var futureProvenance = CreateBeverageRequest(category: "Water", consumedMl: 500, consumedAt: earlier, timezone: "UTC", source: "confirmed_recognition", recognitionId: UUID(), containerMl: 500)
        futureProvenance.onDeviceRecognition = submitted.onDeviceRecognition
        do { _ = try await rolledBack.createBeverage(futureProvenance, idempotencyKey: UUID()); XCTFail("New future provenance accepted") } catch ServiceError.invalidResponse { }
        let changedTime = UpdateBeverageRequest(correcting: saved, category: saved.category, consumedMl: saved.consumedMl, consumedAt: admittedAt.addingTimeInterval(100))
        do { _ = try await rolledBack.updateBeverage(id: saved.id, changedTime); XCTFail("New future timestamp accepted") } catch BeverageValidationError.futureDate { }
        let changedAmount = UpdateBeverageRequest(correcting: saved, category: saved.category, consumedMl: 250, consumedAt: saved.consumedAt)
        let updated = try await rolledBack.updateBeverage(id: saved.id, changedAmount)
        XCTAssertEqual(updated.containerMl, 500)
        XCTAssertEqual(updated.onDeviceRecognition, saved.onDeviceRecognition)
        try await rolledBack.deleteBeverage(id: updated.id, revision: updated.revision)
        let count = try await rolledBack.deleteAllData(); XCTAssertEqual(count, 1)
    }

    @MainActor func testLegacyServerAndDemoPendingBackupPolicyRemainsUnchanged() throws {
        let root = directory(); defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        for (index, destination) in ["offline", "http://127.0.0.1:8123"].enumerated() {
            let url = root.appendingPathComponent("pending-\(index).json")
            let item = PendingBeverage(key: UUID(), request: request(), destination: destination)
            let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
            let bytes = try encoder.encode(item); try bytes.write(to: url, options: .atomic)
            var mutableURL = url, values = URLResourceValues(); values.isExcludedFromBackup = false
            try mutableURL.setResourceValues(values)
            let store = BeverageStore(service: LocalBeverageService(fileURL: root.appendingPathComponent("unused.json")), pendingURL: url,
                configuration: APIConfiguration(baseURL: destination, token: "", offline: destination == "offline"))
            XCTAssertEqual(store.pending?.key, item.key)
            XCTAssertEqual(try Data(contentsOf: url), bytes)
            XCTAssertEqual(try URL(fileURLWithPath: url.path).resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, false)
        }
    }

    func testOnDeviceAndDemoSettingsAreMutuallyExclusive() {
        var config = APIConfiguration(baseURL: "saved", token: "saved", offline: true, onDevice: true)
        XCTAssertTrue(config.onDevice); XCTAssertFalse(config.offline)
        config.offline = true
        XCTAssertFalse(config.onDevice)
        config.onDevice = true
        XCTAssertFalse(config.offline)
        XCTAssertEqual(config.baseURL, "saved"); XCTAssertEqual(config.token, "saved")
    }
}
