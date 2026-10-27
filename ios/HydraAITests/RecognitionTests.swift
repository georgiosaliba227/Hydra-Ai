import XCTest
import UIKit
import ImageIO
@testable import HydraAI

final class RecognitionTests: XCTestCase {
    let configuration = APIConfiguration(baseURL: "http://127.0.0.1:8000", token: String(repeating: "t", count: 32), offline: false)
    let result = """
    {"version":"recognition-v1","mode":"mock","model":"muse-spark-1.3","requires_confirmation":true,"candidates":[{"identity":"Coffee","product_id":null,"container_ml":250,"confidence":"low","uncertainty_reasons":["Synthetic demo; verify capacity"],"nutrition":null}]}
    """
    override func tearDown() { FixtureURLProtocol.handler = nil }
    private func service() throws -> HTTPBeverageService {
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        return try HTTPBeverageService(configuration: configuration, session: URLSession(configuration: options))
    }
    func testAnalysisUsesConsentedBackendOnlyAndNoLoggingMutation() async throws {
        var calls = 0
        FixtureURLProtocol.handler = { request in
            calls += 1
            XCTAssertEqual(request.url?.path, "/v1/recognitions")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer \(self.configuration.token)")
            let body = try JSONSerialization.jsonObject(with: request.httpBody ?? Data(reading: request.httpBodyStream!)) as! [String: Any]
            XCTAssertEqual(body["photo_consent"] as? Bool, true)
            XCTAssertEqual(body["mock_scenario"] as? String, "generic")
            XCTAssertEqual(body["image_base64"] as? String, Data([1,2,3]).base64EncodedString())
            XCTAssertEqual(body.count, 3)
            return (200, Data(self.result.utf8))
        }
        let response = try await service().analyzePhoto(Data([1,2,3]), scenario: "generic")
        XCTAssertEqual(response.candidates.first?.containerMl, 250)
        XCTAssertTrue(response.requiresConfirmation); XCTAssertEqual(calls, 1)
    }
    func testAmbiguousAndFailureRemainUnlogged() async throws {
        FixtureURLProtocol.handler = { _ in (503, Data()) }
        do { _ = try await service().analyzePhoto(Data(), scenario: "failure"); XCTFail("Expected failure") }
        catch ServiceError.server(503) { }
        let ambiguous = result.replacingOccurrences(of: "[{\"identity\":\"Coffee\",\"product_id\":null,\"container_ml\":250,\"confidence\":\"low\",\"uncertainty_reasons\":[\"Synthetic demo; verify capacity\"],\"nutrition\":null}]", with: "[]")
        let decoded = try JSONDecoder().decode(RecognitionResult.self, from: Data(ambiguous.utf8))
        try decoded.validate(); XCTAssertTrue(decoded.candidates.isEmpty)
    }
    func testUntrustedOrUnconfirmedResponseRejected() throws {
        for invalid in [result.replacingOccurrences(of: "\"requires_confirmation\":true", with: "\"requires_confirmation\":false"), result.replacingOccurrences(of: "\"container_ml\":250", with: "\"container_ml\":5001"), result.replacingOccurrences(of: "\"mode\":\"mock\"", with: "\"mode\":\"live\"")] {
            let decoded = try JSONDecoder().decode(RecognitionResult.self, from: Data(invalid.utf8))
            XCTAssertThrowsError(try decoded.validate())
        }
    }
    @MainActor func testPhotoPreprocessingBoundsDimensionsAndOmitsGPS() throws {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 2400, height: 1200)).image { context in
            UIColor.blue.setFill(); context.fill(CGRect(x: 0,y: 0,width: 2400,height: 1200))
        }
        let jpeg = try PhotoPreparation.jpeg(image)
        XCTAssertLessThanOrEqual(jpeg.count, 1_048_576)
        let source = CGImageSourceCreateWithData(jpeg as CFData, nil)!
        let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil)! as NSDictionary
        XCTAssertLessThanOrEqual(properties[kCGImagePropertyPixelWidth] as! Int, 1600)
        XCTAssertNil(properties[kCGImagePropertyGPSDictionary])
    }
    func testConfirmedVolumeAndCorrectionBoundary() throws {
        var request = CreateBeverageRequest(category: "Coffee", consumedMl: 150, consumedAt: .now, timezone: "America/New_York", source: "confirmed_recognition", containerMl: 250)
        XCTAssertNoThrow(try request.validate())
        request.containerMl = 100
        XCTAssertThrowsError(try request.validate())
    }
    @MainActor func testPhotoConfirmationPendingSurvivesRestartWithoutImage() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let pending = directory.appendingPathComponent("pending.json")
        let service = PhotoRecordingService()
        let first = BeverageStore(service: service, pendingURL: pending, configuration: configuration)
        do { try await first.add(category: "Corrected tea", consumedMl: 125, at: Date(timeIntervalSince1970: 1_700_000_000), source: "confirmed_recognition", containerMl: 250); XCTFail("Expected timeout") } catch { }
        let key = try XCTUnwrap(first.pending?.key)
        let restored = BeverageStore(service: service, pendingURL: pending, configuration: configuration)
        XCTAssertEqual(restored.pending?.request.containerMl, 250)
        XCTAssertEqual(restored.pending?.request.category, "Corrected tea")
        XCTAssertNil(restored.pending?.request.productId)
        XCTAssertFalse(try String(contentsOf: pending, encoding: .utf8).contains("image"))
        try await restored.retryPending()
        let keys = await service.keys
        XCTAssertEqual(keys, [key,key]); XCTAssertNil(restored.pending)
    }
}

private actor PhotoRecordingService: BeverageService {
    var keys: [UUID] = []
    func listBeverages() async throws -> [BeverageLog] { [] }
    func dailySummary(date: String, timezone: String) async throws -> DailySummary {
        DailySummary(localDate: date, timezone: timezone, beverageTotalMl: 125, estimatedWaterMl: nil, forecastStatus: "insufficient_data")
    }
    func createBeverage(_ request: CreateBeverageRequest, idempotencyKey: UUID) async throws -> BeverageLog {
        keys.append(idempotencyKey)
        if keys.count == 1 { throw URLError(.timedOut) }
        return BeverageLog(id: idempotencyKey, consumedMl: request.consumedMl, category: request.category, consumedAt: request.consumedAt, timezone: request.timezone, source: request.source, revision: 1)
    }
}

private extension Data {
    init(reading stream: InputStream) {
        self.init(); stream.open(); defer { stream.close() }
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4096)
        defer { buffer.deallocate() }
        while stream.hasBytesAvailable {
            let count = stream.read(buffer, maxLength: 4096)
            if count <= 0 { break }
            append(buffer, count: count)
        }
    }
}
