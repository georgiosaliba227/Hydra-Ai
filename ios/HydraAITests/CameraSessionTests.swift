import Foundation
import XCTest
@testable import HydraAI

@MainActor
final class CameraSessionTests: XCTestCase {
    private func result() -> RecognitionResult {
        RecognitionResult(version: "recognition-v1", mode: "meta_live", model: "muse-spark-1.3",
                          candidates: [], requiresConfirmation: true, recognitionId: UUID())
    }

    private func ready(_ session: CameraSession, generation: UUID) throws {
        let ticket = try XCTUnwrap(session.beginCapabilities(generation: generation))
        XCTAssertTrue(session.completeCapabilities("meta_live", ticket: ticket, currentGeneration: generation))
        session.consent = true; session.metaConsent = true
    }

    func testStableConfigurationRequiresBothConsentsAndAcceptsItsResult() throws {
        let session = CameraSession(), generation = UUID()
        let capability = try XCTUnwrap(session.beginCapabilities(generation: generation))
        XCTAssertNil(session.beginAnalysis(generation: generation))
        XCTAssertTrue(session.completeCapabilities("meta_live", ticket: capability, currentGeneration: generation))
        session.consent = true
        XCTAssertNil(session.beginAnalysis(generation: generation))
        session.metaConsent = true
        let analysis = try XCTUnwrap(session.beginAnalysis(generation: generation))
        XCTAssertNil(session.beginAnalysis(generation: generation))
        let output = result()
        XCTAssertTrue(session.completeAnalysis(output, ticket: analysis, currentGeneration: generation))
        XCTAssertEqual(session.result?.recognitionId, output.recognitionId)
        XCTAssertFalse(session.isAnalyzing)
    }

    func testNewGenerationCannotSendUsingConsentBeforeViewObservesChange() throws {
        let session = CameraSession(), original = UUID(), next = UUID()
        try ready(session, generation: original)
        XCTAssertNil(session.beginAnalysis(generation: next))
        XCTAssertFalse(session.consent); XCTAssertFalse(session.metaConsent)
        XCTAssertNil(session.mode); XCTAssertNil(session.result)
    }

    func testDelayedCapabilitiesDoNotOverwriteNewConnectionOrItsLoadingState() async throws {
        let session = CameraSession(), original = UUID(), next = UUID()
        let old = try XCTUnwrap(session.beginCapabilities(generation: original))
        let response = CameraDeferred<String>()
        let completion = Task { @MainActor in
            let mode = await response.receive()
            return session.completeCapabilities(mode, ticket: old, currentGeneration: next)
        }
        let current = try XCTUnwrap(session.beginCapabilities(generation: next))
        await response.resolve("meta_live")
        let accepted = await completion.value
        XCTAssertFalse(accepted)
        XCTAssertTrue(session.isLoadingCapabilities); XCTAssertNil(session.mode)
        XCTAssertTrue(session.completeCapabilities("mock", ticket: current, currentGeneration: next))
        XCTAssertEqual(session.mode, "mock")
    }

    func testDelayedCapabilityErrorCannotClearNewMode() throws {
        let session = CameraSession(), original = UUID(), next = UUID()
        let old = try XCTUnwrap(session.beginCapabilities(generation: original))
        let current = try XCTUnwrap(session.beginCapabilities(generation: next))
        XCTAssertTrue(session.completeCapabilities("mock", ticket: current, currentGeneration: next))
        XCTAssertFalse(session.completeCapabilities(nil, ticket: old, currentGeneration: next))
        XCTAssertEqual(session.mode, "mock")
    }

    func testDelayedRecognitionSuccessIsDiscardedAcrossAtoBtoA() async throws {
        let session = CameraSession(), firstA = UUID(), b = UUID(), secondA = UUID()
        try ready(session, generation: firstA)
        let old = try XCTUnwrap(session.beginAnalysis(generation: firstA))
        let response = CameraDeferred<RecognitionResult>()
        let completion = Task { @MainActor in
            let output = await response.receive()
            return session.completeAnalysis(output, ticket: old, currentGeneration: secondA)
        }
        session.bind(to: b)
        try ready(session, generation: secondA)
        let current = try XCTUnwrap(session.beginAnalysis(generation: secondA))
        await response.resolve(result())
        let accepted = await completion.value
        XCTAssertFalse(accepted)
        XCTAssertTrue(session.isAnalyzing); XCTAssertNil(session.result)
        let output = result()
        XCTAssertTrue(session.completeAnalysis(output, ticket: current, currentGeneration: secondA))
        XCTAssertEqual(session.result?.recognitionId, output.recognitionId)
    }

    func testDelayedRecognitionErrorCannotReplaceNewSuccess() async throws {
        let session = CameraSession(), original = UUID(), next = UUID()
        try ready(session, generation: original)
        let old = try XCTUnwrap(session.beginAnalysis(generation: original))
        let response = CameraDeferred<Bool>()
        let completion = Task { @MainActor in
            _ = await response.receive()
            return session.completeAnalysis(nil, ticket: old, currentGeneration: next)
        }
        try ready(session, generation: next)
        let current = try XCTUnwrap(session.beginAnalysis(generation: next))
        let output = result()
        XCTAssertTrue(session.completeAnalysis(output, ticket: current, currentGeneration: next))
        await response.resolve(true)
        let accepted = await completion.value
        XCTAssertFalse(accepted, "The view must not present an error from the old backend")
        XCTAssertEqual(session.result?.recognitionId, output.recognitionId)
        XCTAssertFalse(session.isAnalyzing)
    }

    func testChangedStoreGenerationRejectsOldReceiptBeforeCreatingPendingLog() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let configA = APIConfiguration(baseURL: "http://127.0.0.1:8123", token: String(repeating: "a", count: 32), offline: false)
        let configB = APIConfiguration(baseURL: "http://127.0.0.1:8124", token: String(repeating: "b", count: 32), offline: false)
        let store = BeverageStore(service: CameraRecordingService(), pendingURL: directory.appendingPathComponent("pending.json"), configuration: configA)
        let original = store.configurationGeneration, receipt = UUID()
        XCTAssertTrue(store.registerRecognitionReceipt(receipt, generation: original))
        try store.configure(configB)
        let middle = store.configurationGeneration
        try store.configure(configA)
        XCTAssertNotEqual(store.configurationGeneration, original)
        XCTAssertNotEqual(store.configurationGeneration, middle)
        XCTAssertFalse(store.registerRecognitionReceipt(UUID(), generation: original))
        do {
            try await store.add(category: "tea", consumedMl: 125, at: .now, source: "confirmed_recognition", containerMl: 250, recognitionId: receipt)
            XCTFail("Receipt from the previous configuration must not be sent")
        } catch ServiceError.liveRecognitionUnverified { }
        XCTAssertNil(store.pending)
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent("pending.json").path))
    }

    func testCurrentReceiptAndManualLoggingStillWork() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let service = CameraRecordingService()
        let store = BeverageStore(service: service, pendingURL: directory.appendingPathComponent("pending.json"),
                                  configuration: APIConfiguration(baseURL: "http://127.0.0.1:8123", token: String(repeating: "t", count: 32), offline: false))
        let receipt = UUID()
        XCTAssertTrue(store.registerRecognitionReceipt(receipt, generation: store.configurationGeneration))
        try await store.add(category: "tea", consumedMl: 125, at: .now, source: "confirmed_recognition", containerMl: 250, recognitionId: receipt)
        try await store.add(category: "water", consumedMl: 200, at: .now)
        let requests = await service.requests
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests[0].recognitionId, receipt)
        XCTAssertEqual(requests[1].source, "manual")
        XCTAssertNil(requests[1].recognitionId)
    }

    func testPersistedPendingReceiptCanRetryAfterRestartWithoutNewInference() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appendingPathComponent("pending.json")
        let service = CameraRecordingService(failFirst: true)
        let configuration = APIConfiguration(baseURL: "http://127.0.0.1:8123", token: String(repeating: "t", count: 32), offline: false)
        let original = BeverageStore(service: service, pendingURL: file, configuration: configuration)
        let receipt = UUID()
        XCTAssertTrue(original.registerRecognitionReceipt(receipt, generation: original.configurationGeneration))
        do {
            try await original.add(category: "tea", consumedMl: 125, at: .now, source: "confirmed_recognition", containerMl: 250, recognitionId: receipt)
            XCTFail("Expected synthetic first confirmation failure")
        } catch let error as URLError { XCTAssertEqual(error.code, .timedOut) }
        let key = try XCTUnwrap(original.pending?.key)
        let restored = BeverageStore(service: service, pendingURL: file, configuration: configuration)
        try await restored.retryPending()
        let requests = await service.requests, keys = await service.keys
        XCTAssertEqual(keys, [key, key])
        XCTAssertEqual(requests.map(\.recognitionId), [receipt, receipt])
        XCTAssertNil(restored.pending)
    }
}

private actor CameraDeferred<Value: Sendable> {
    private var value: Value?
    private var continuation: CheckedContinuation<Value, Never>?
    func receive() async -> Value {
        if let value { return value }
        return await withCheckedContinuation { continuation = $0 }
    }
    func resolve(_ value: Value) {
        self.value = value
        continuation?.resume(returning: value); continuation = nil
    }
}

private actor CameraRecordingService: BeverageService {
    let failFirst: Bool
    var requests: [CreateBeverageRequest] = []
    var keys: [UUID] = []
    init(failFirst: Bool = false) { self.failFirst = failFirst }
    func listBeverages() async throws -> [BeverageLog] { [] }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary {
        DailySummary(localDate: date, timezone: timezone, beverageTotalMl: 125, estimatedWaterMl: nil, forecastStatus: "insufficient_data")
    }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog {
        requests.append(request); keys.append(idempotencyKey)
        if failFirst && requests.count == 1 { throw URLError(.timedOut) }
        return BeverageLog(id: idempotencyKey, consumedMl: request.consumedMl, category: request.category,
                           consumedAt: request.consumedAt, timezone: request.timezone, source: request.source, revision: 1)
    }
}
