import Foundation
import XCTest
@testable import HydraAI

final class FixtureURLProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, Data))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, data) = try Self.handler!(request)
            client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data); client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { }
}

final class HTTPIntegrationTests: XCTestCase {
    let configuration = APIConfiguration(baseURL: "http://127.0.0.1:8000", token: String(repeating: "x", count: 32), offline: false)
    private func service() throws -> HTTPBeverageService {
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        return try HTTPBeverageService(configuration: configuration, session: URLSession(configuration: options))
    }
    private func log(_ id: String) -> String {
        """
        {"id":"\(id)","category":"water","consumed_ml":250,"consumed_at":"2026-10-26T15:00:00.123456Z","timezone":"America/New_York","source":"manual","revision":1}
        """
    }
    override func tearDown() { FixtureURLProtocol.handler = nil }

    func testFetchesEveryHistoryPageAndSendsAuth() async throws {
        let first = UUID().uuidString, second = UUID().uuidString
        var calls = 0
        FixtureURLProtocol.handler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer \(self.configuration.token)")
            calls += 1
            if calls == 1 { return (200, Data("{\"items\":[\(self.log(first))],\"next_cursor\":\"page2\"}".utf8)) }
            XCTAssertTrue(request.url!.query!.contains("cursor=page2"))
            return (200, Data("{\"items\":[\(self.log(second))],\"next_cursor\":null}".utf8))
        }
        let logs = try await service().listBeverages()
        XCTAssertEqual(logs.count, 2); XCTAssertEqual(calls, 2)
        XCTAssertEqual(logs[0].consumedMl, 250)
    }

    func testCreateUsesStableIdempotencyHeader() async throws {
        let key = UUID()
        FixtureURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), key.uuidString)
            XCTAssertEqual(request.url!.path, "/v1/beverages")
            return (201, Data(self.log(UUID().uuidString).utf8))
        }
        _ = try await service().createBeverage(.init(category: "water", consumedMl: 250, consumedAt: Date(timeIntervalSince1970: 1_700_000_000), timezone: "UTC", source: "manual"), idempotencyKey: key)
    }

    func testSummaryUsesRequestedDateAndTimezone() async throws {
        FixtureURLProtocol.handler = { request in
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!
            XCTAssertEqual(query.first { $0.name == "timezone" }?.value, "America/New_York")
            return (200, Data("{\"local_date\":\"2026-10-26\",\"timezone\":\"America/New_York\",\"beverage_total_ml\":750.0,\"estimated_water_ml\":null,\"forecast_status\":\"insufficient_data\"}".utf8))
        }
        let summary = try await service().dailySummary(date: "2026-10-26", timezone: "America/New_York")
        XCTAssertEqual(summary.beverageTotalMl, 750); XCTAssertNil(summary.estimatedWaterMl)
    }

    func testUnauthorizedIsVisibleAndNoOfflineFallback() async throws {
        FixtureURLProtocol.handler = { _ in (401, Data("{}".utf8)) }
        do { _ = try await service().listBeverages(); XCTFail("Expected failure") }
        catch ServiceError.unauthorized { }
    }

    func testRuntimeConfigurationPersistsCredentialInKeychain() throws {
        let previous = APIConfiguration.load()
        defer { try? previous.save() }
        let config = APIConfiguration(baseURL: "http://127.0.0.1:8000", token: UUID().uuidString, offline: false)
        try config.save()
        let loaded = APIConfiguration.load()
        XCTAssertEqual(loaded.baseURL, config.baseURL)
        XCTAssertEqual(loaded.token, config.token)
        XCTAssertFalse(loaded.offline)
        XCTAssertNil(UserDefaults.standard.string(forKey: "hydra.token"))
    }

    func testRejectsPublicHTTPAndCredentialInURL() throws {
        XCTAssertThrowsError(try APIConfiguration(baseURL: "http://example.com", token: configuration.token, offline: false).validatedURL())
        XCTAssertThrowsError(try APIConfiguration(baseURL: "https://user:pass@example.com", token: configuration.token, offline: false).validatedURL())
        XCTAssertThrowsError(try APIConfiguration(baseURL: "http://127.0.0.1", token: "short", offline: false).validatedURL())
    }

    @MainActor
    func testPendingRequestSurvivesRestartAndRetriesSameKey() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let file = directory.appendingPathComponent("pending.json")
        defer { try? FileManager.default.removeItem(at: directory) }
        let service = RecordingService()
        let first = BeverageStore(service: service, pendingURL: file, configuration: configuration)
        do { try await first.add(category: "water", consumedMl: 250, at: Date(timeIntervalSince1970: 1_700_000_000)); XCTFail("Expected lost response") }
        catch { }
        XCTAssertNotNil(first.pending)
        let key = first.pending!.key
        let restarted = BeverageStore(service: service, pendingURL: file, configuration: configuration)
        XCTAssertEqual(restarted.pending?.key, key)
        XCTAssertFalse(restarted.canLog)
        try await restarted.retryPending()
        let received = await service.keys
        XCTAssertEqual(received, [key, key]); XCTAssertNil(restarted.pending)
        XCTAssertFalse(FileManager.default.fileExists(atPath: file.path))
        XCTAssertEqual(restarted.summary?.beverageTotalMl, 250)
    }

    @MainActor
    func testCorruptPendingFileBlocksNewSubmission() async throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: file) }
        try Data("broken".utf8).write(to: file)
        let store = BeverageStore(service: RecordingService(), pendingURL: file, configuration: configuration)
        XCTAssertFalse(store.canLog)
        if case .failed = store.state { } else { XCTFail("Expected recovery error") }
    }
}

private actor RecordingService: BeverageService {
    var keys: [UUID] = []
    func listBeverages() async throws -> [BeverageLog] { [] }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary {
        DailySummary(localDate: date, timezone: timezone, beverageTotalMl: 250, estimatedWaterMl: nil, forecastStatus: "insufficient_data")
    }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog {
        keys.append(idempotencyKey)
        if keys.count == 1 { throw URLError(.timedOut) }
        return BeverageLog(id: UUID(), consumedMl: request.consumedMl, category: request.category, consumedAt: request.consumedAt, timezone: request.timezone, source: "manual", revision: 1)
    }
}
