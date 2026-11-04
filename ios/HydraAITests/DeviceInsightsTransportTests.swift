import XCTest
@testable import HydraAI

final class DeviceInsightsTransportTests: XCTestCase {
    private let config = APIConfiguration(baseURL: "http://127.0.0.1:8772", token: String(repeating: "x", count: 32), offline: false)
    private let now = ISO8601DateFormatter().date(from: "2026-11-01T16:30:00Z")!
    override func tearDown() { FixtureURLProtocol.handler = nil }

    private func service() throws -> HTTPBeverageService {
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        return try HTTPBeverageService(configuration: config, session: URLSession(configuration: options))
    }
    private func fixture(_ name: String) throws -> Data {
        try Data(contentsOf: XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "json")))
    }
    private func snapshot() throws -> DeviceTrendSnapshot {
        let log = BeverageLog(id: UUID(), consumedMl: 250, category: "Private personal name", consumedAt: now,
                              timezone: "UTC", source: "manual", revision: 1, beverageType: "water")
        return try .make(logs: [log], goal: 2000, now: now, zone: TimeZone(identifier: "UTC")!)
    }
    private func contextRequest() -> AssistantRequest {
        .make(questionId: "coffee_counts", includeToday: true, now: now, zone: TimeZone(identifier: "UTC")!)
    }

    func testTrendsPostsOnlyReviewedAggregatesAndValidatesRealBackendFixture() async throws {
        let expected = try fixture("device-trends-v1")
        FixtureURLProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/v1/device-insights/trends")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Cache-Control"), "no-store")
            let body = try XCTUnwrap(request.httpBodyStream).readAll()
            let text = try XCTUnwrap(String(data: body, encoding: .utf8))
            XCTAssertFalse(text.contains("Private personal name"))
            XCTAssertFalse(text.contains("consumed_at"))
            XCTAssertFalse(text.contains("recognition"))
            let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
            XCTAssertEqual(json["source"] as? String, "on_device_summary")
            XCTAssertEqual(json["consent_to_process"] as? Bool, true)
            return (200, expected)
        }
        let response = try await service().deviceTrends(snapshot())
        XCTAssertEqual(response.facts.last_7_days.total_ml, 250)
    }

    func testUnavailableDeviceRouteNeverFallsBackToServerHistoryOrRetries() async throws {
        var calls = 0
        FixtureURLProtocol.handler = { request in
            calls += 1
            XCTAssertEqual(request.url?.path, "/v1/device-insights/trends")
            return (404, Data())
        }
        do { _ = try await service().deviceTrends(snapshot()); XCTFail("Expected no fallback") }
        catch ServiceError.server(404) { }
        XCTAssertEqual(calls, 1)
    }

    func testAssistantWrapsPhoneContextAndRejectsDifferentServerTotal() async throws {
        let good = try fixture("device-assistant-v1")
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: good) as? [String: Any])
        var context = try XCTUnwrap(json["intake_context"] as? [String: Any]); context["beverage_total_ml"] = 999
        json["intake_context"] = context
        let wrong = try JSONSerialization.data(withJSONObject: json)
        FixtureURLProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/v1/device-insights/assistant")
            return (200, wrong)
        }
        let envelope = try DeviceAssistantEnvelope(request: contextRequest(), todayLoggedTotalMl: 250)
        do { _ = try await service().askDeviceAssistant(envelope); XCTFail("Must reject unrelated server context") }
        catch ServiceError.invalidResponse { }
        FixtureURLProtocol.handler = { _ in (200, good) }
        let answer = try await service().askDeviceAssistant(envelope)
        XCTAssertEqual(answer.intake_context?.beverage_total_ml, 250)
    }

    @MainActor
    func testOnDeviceStoreBuildsSnapshotFromSelectedLocalServiceWithoutBackendCalls() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let local = LocalBeverageService(fileURL: directory.appendingPathComponent("phone.json"))
        _ = try await local.createBeverage(.init(category: "water", consumedMl: 250, consumedAt: now, timezone: "UTC", source: "manual"), idempotencyKey: UUID())
        _ = try await local.updateGoal(2000)
        let store = BeverageStore(service: local, pendingURL: directory.appendingPathComponent("pending.json"),
                                  configuration: .init(baseURL: config.baseURL, token: config.token, offline: false, onDevice: true, insightsEnabled: true),
                                  goalProfiles: GoalProfileStore(directory: directory.appendingPathComponent("profiles")))
        FixtureURLProtocol.handler = { _ in XCTFail("Local summary must not read server history"); return (500, Data()) }
        let result = try await store.deviceTrendSnapshot(now: now, zone: TimeZone(identifier: "UTC")!)
        XCTAssertEqual(result.days.last?.total_ml, 250)
        XCTAssertEqual(result.goal_ml, 2000)
        let total = try await store.deviceAssistantTotal(for: contextRequest(), generation: store.configurationGeneration)
        XCTAssertEqual(total, 250)
        XCTAssertTrue(store.canLog)
        XCTAssertTrue(store.isOnDevice)
        FixtureURLProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/v1/device-insights/trends")
            return (503, Data())
        }
        do { _ = try await service().deviceTrends(result); XCTFail("Synthetic backend is unavailable") }
        catch ServiceError.server(503) { }
        try await store.add(category: "water", consumedMl: 125, at: now)
        let phoneLogs = try await local.listBeverages()
        XCTAssertEqual(phoneLogs.reduce(0) { $0 + $1.consumedMl }, 375)
        XCTAssertTrue(store.canLog, "Backend feature failure cannot block the phone's local saves")
    }

    @MainActor
    func testQuestionWithoutContextWorksWhenPendingLocalStorageIsUnreadable() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let pending = directory.appendingPathComponent("pending.json")
        try Data("corrupt synthetic pending".utf8).write(to: pending)
        let store = BeverageStore(pendingURL: pending, configuration: .init(baseURL: "", token: "", offline: false, onDevice: true),
                                  goalProfiles: GoalProfileStore(directory: directory.appendingPathComponent("profiles")))
        XCTAssertFalse(store.canLog)
        let total = try await store.deviceAssistantTotal(for: .make(questionId: "coffee_counts", includeToday: false), generation: store.configurationGeneration)
        XCTAssertNil(total)
    }

    @MainActor
    func testCapturedConnectionCannotReadAfterOptInIsRevoked() async throws {
        let saved = try SavedConnectionState(); defer { saved.restore() }
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let local = APIConfiguration(baseURL: config.baseURL, token: config.token, offline: false, onDevice: true, insightsEnabled: true)
        let store = BeverageStore(pendingURL: directory.appendingPathComponent("pending.json"), configuration: local,
                                  goalProfiles: GoalProfileStore(directory: directory.appendingPathComponent("profiles")))
        let previous = store.configurationGeneration
        var revoked = local; revoked.insightsEnabled = false
        try store.configure(revoked)
        do {
            _ = try await store.deviceAssistantTotal(for: .make(questionId: "coffee_counts", includeToday: false), generation: previous)
            XCTFail("The previous backend cannot dispatch after connection changes")
        } catch GoalMutationError.connectionChanged { }
        XCTAssertTrue(store.canLog)
        XCTAssertFalse(store.hasInsightsConnection)
    }

    @MainActor
    func testAssistantUsesPhoneEndpointAndCapturedTotal() async throws {
        let service = DeviceAssistantSpy(answerData: try fixture("device-assistant-v1"))
        let controller = AssistantController()
        await controller.ask(contextRequest(), service: service, deviceSummary: { 250 })
        XCTAssertEqual(controller.state, .loaded)
        XCTAssertEqual(controller.answer?.intake_context?.beverage_total_ml, 250)
        let count = await service.calls
        XCTAssertEqual(count, 1)
    }

    @MainActor
    func testChangedQuestionDuringLocalReadCannotSendStaleContext() async throws {
        let service = DeviceAssistantSpy(answerData: try fixture("device-assistant-v1"))
        let controller = AssistantController(), gate = SuspendedPhoneTotal()
        let started = await gate.started
        let task = Task { await controller.ask(contextRequest(), service: service, deviceSummary: { await gate.read() }) }
        await fulfillment(of: [started], timeout: 2)
        controller.invalidate()
        await gate.release()
        await task.value
        let count = await service.calls
        XCTAssertEqual(count, 0)
        XCTAssertNil(controller.answer)
        XCTAssertEqual(controller.state, .idle)
    }
}

private actor SuspendedPhoneTotal {
    let started = XCTestExpectation(description: "Phone summary suspended")
    private var continuation: CheckedContinuation<Int?, Never>?
    func read() async -> Int? {
        await withCheckedContinuation { continuation = $0; started.fulfill() }
    }
    func release() { continuation?.resume(returning: 250); continuation = nil }
}

private actor DeviceAssistantSpy: BeverageService {
    let answerData: Data
    private(set) var calls = 0
    init(answerData: Data) { self.answerData = answerData }
    func askDeviceAssistant(_ envelope: DeviceAssistantEnvelope) async throws -> AssistantAnswer {
        calls += 1
        let answer = try JSONDecoder().decode(AssistantAnswer.self, from: answerData)
        try envelope.validate(answer: answer)
        return answer
    }
    func askAssistant(_ request: AssistantRequest) async throws -> AssistantAnswer {
        XCTFail("The on-device question must not use the server-history endpoint")
        throw ServiceError.invalidResponse
    }
    func listBeverages() async throws -> [BeverageLog] { [] }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary { throw ServiceError.invalidResponse }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog { throw ServiceError.invalidResponse }
}

private extension InputStream {
    func readAll() -> Data {
        open(); defer { close() }
        var data = Data(), buffer = [UInt8](repeating: 0, count: 4096)
        while true {
            let count = read(&buffer, maxLength: buffer.count)
            if count <= 0 { return data }
            data.append(buffer, count: count)
        }
    }
}
