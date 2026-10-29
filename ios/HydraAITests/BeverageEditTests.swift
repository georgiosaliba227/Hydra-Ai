import Foundation
import XCTest
@testable import HydraAI

final class BeverageEditTests: XCTestCase {
    private let configuration = APIConfiguration(baseURL: "http://127.0.0.1:8000", token: String(repeating: "x", count: 32), offline: false)
    private let id = UUID()
    private let consumedAt = Date(timeIntervalSince1970: 1_700_000_000)

    override func tearDown() { FixtureURLProtocol.handler = nil }

    private func service() throws -> HTTPBeverageService {
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        return try HTTPBeverageService(configuration: configuration, session: URLSession(configuration: options))
    }

    private func log(source: String = "manual", revision: Int = 1, ml: Int = 250) -> BeverageLog {
        BeverageLog(id: id, consumedMl: ml, category: "coffee", consumedAt: consumedAt, timezone: "UTC", source: source, revision: revision)
    }

    private func json(revision: Int, ml: Int) -> Data {
        Data("""
        {"id":"\(id.uuidString.lowercased())","category":"coffee","consumed_ml":\(ml),"consumed_at":"2023-11-14T22:13:20.000000Z","timezone":"UTC","source":"manual","revision":\(revision)}
        """.utf8)
    }

    private func body(_ request: URLRequest) -> [String: Any] {
        guard let stream = request.httpBodyStream else { return [:] }
        stream.open(); defer { stream.close() }
        var data = Data(); var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable { let count = stream.read(&buffer, maxLength: buffer.count); if count <= 0 { break }; data.append(buffer, count: count) }
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    func testCorrectionSendsOnlyChangedFields() throws {
        let unchanged = UpdateBeverageRequest(correcting: log(), category: " coffee ", consumedMl: 250, consumedAt: consumedAt)
        XCTAssertFalse(unchanged.hasChanges)
        let volume = UpdateBeverageRequest(correcting: log(), category: "coffee", consumedMl: 400, consumedAt: consumedAt)
        let encoded = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(volume)) as? [String: Any])
        XCTAssertEqual(Set(encoded.keys), ["revision", "consumed_ml"])
        let photo = UpdateBeverageRequest(correcting: log(source: "confirmed_recognition"), category: "Water", consumedMl: 250, consumedAt: consumedAt)
        XCTAssertNil(photo.category, "A photo-confirmed product category is never sent")
        XCTAssertThrowsError(try UpdateBeverageRequest(correcting: log(), category: "coffee", consumedMl: 5_001, consumedAt: consumedAt).validate())
        XCTAssertThrowsError(try UpdateBeverageRequest(correcting: log(), category: "coffee", consumedMl: 250, consumedAt: .now.addingTimeInterval(3_600)).validate())
    }

    func testPatchUsesRevisionAndVerifiesTheReturnedLog() async throws {
        FixtureURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "PATCH")
            XCTAssertEqual(request.url!.path, "/v1/beverages/\(self.id.uuidString.lowercased())")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer \(self.configuration.token)")
            let sent = self.body(request)
            XCTAssertEqual(sent["revision"] as? Int, 1); XCTAssertEqual(sent["consumed_ml"] as? Int, 400)
            return (200, self.json(revision: 2, ml: 400))
        }
        let request = UpdateBeverageRequest(correcting: log(), category: "coffee", consumedMl: 400, consumedAt: consumedAt)
        let updated = try await service().updateBeverage(id: id, request)
        XCTAssertEqual(updated.revision, 2); XCTAssertEqual(updated.consumedMl, 400)

        FixtureURLProtocol.handler = { _ in (200, self.json(revision: 5, ml: 400)) }
        do { _ = try await service().updateBeverage(id: id, request); XCTFail("Unexpected revision accepted") }
        catch ServiceError.invalidResponse {}
        FixtureURLProtocol.handler = { _ in (409, Data(#"{"code":"revision_conflict"}"#.utf8)) }
        do { _ = try await service().updateBeverage(id: id, request); XCTFail("Conflict accepted") }
        catch ServiceError.server(let code) { XCTAssertEqual(code, 409) }
    }

    func testDeleteTreatsAlreadyDeletedAsSuccess() async throws {
        var statuses = [204, 404, 500]
        FixtureURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "DELETE")
            XCTAssertEqual(request.url!.path, "/v1/beverages/\(self.id.uuidString.lowercased())")
            XCTAssertEqual(request.url!.query, "revision=3")
            return (statuses.removeFirst(), Data())
        }
        try await service().deleteBeverage(id: id, revision: 3)
        try await service().deleteBeverage(id: id, revision: 3)
        do { try await service().deleteBeverage(id: id, revision: 3); XCTFail("Server error accepted") }
        catch ServiceError.server(let code) { XCTAssertEqual(code, 500) }
    }

    @MainActor func testOfflineStoreEditsDeletesAndExplainsConflicts() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let mock = MockBeverageService(fileURL: folder.appendingPathComponent("logs.json"))
        let offline = APIConfiguration(baseURL: "", token: "", offline: true)
        let store = BeverageStore(service: mock, pendingURL: folder.appendingPathComponent("pending.json"), configuration: offline)
        try await store.add(category: "water", consumedMl: 250, at: consumedAt)
        let original = try XCTUnwrap(store.logs.first)
        try await store.update(original, category: "tea", consumedMl: 300, at: consumedAt)
        let corrected = try XCTUnwrap(store.logs.first)
        XCTAssertEqual(corrected.category, "tea"); XCTAssertEqual(corrected.consumedMl, 300); XCTAssertEqual(corrected.revision, 2)
        do { try await store.update(original, category: "juice", consumedMl: 200, at: consumedAt); XCTFail("Stale edit accepted") }
        catch BeverageEditError.changedElsewhere {}
        XCTAssertEqual(store.logs.first?.consumedMl, 300, "A stale edit changes nothing and shows the latest version")
        do { try await store.delete(original); XCTFail("Stale delete accepted") } catch BeverageEditError.changedElsewhere {}
        XCTAssertEqual(store.logs.count, 1, "A stale delete removes nothing")
        try await store.delete(corrected)
        XCTAssertTrue(store.logs.isEmpty)
    }
}
