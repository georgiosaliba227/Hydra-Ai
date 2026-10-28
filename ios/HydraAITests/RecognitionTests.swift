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
    @MainActor func testPreparedExportAndAnalysisUseIdenticalMetadataStrippedBytes() async throws {
        let original = UIGraphicsImageRenderer(size: CGSize(width: 1800, height: 900)).image { context in
            UIColor.green.setFill(); context.fill(CGRect(x: 0, y: 0, width: 1800, height: 900))
        }
        let taggedData = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(taggedData, "public.jpeg" as CFString, 1, nil))
        CGImageDestinationAddImage(destination, try XCTUnwrap(original.cgImage), [
            kCGImagePropertyGPSDictionary: [kCGImagePropertyGPSLatitude: 37.5, kCGImagePropertyGPSLatitudeRef: "N"],
            kCGImagePropertyExifDictionary: [kCGImagePropertyExifUserComment: "PRIVATE ORIGINAL METADATA"]
        ] as CFDictionary)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        let originalSource = try XCTUnwrap(CGImageSourceCreateWithData(taggedData, nil))
        let originalProperties = try XCTUnwrap(CGImageSourceCopyPropertiesAtIndex(originalSource, 0, nil)) as NSDictionary
        XCTAssertNotNil(originalProperties[kCGImagePropertyGPSDictionary])
        let prepared = try PreparedRecognitionPhoto(image: XCTUnwrap(UIImage(data: taggedData as Data)))
        let exportedJPEG = prepared.export.jpeg
        let source = try XCTUnwrap(CGImageSourceCreateWithData(exportedJPEG as CFData, nil))
        let properties = try XCTUnwrap(CGImageSourceCopyPropertiesAtIndex(source, 0, nil)) as NSDictionary
        XCTAssertNil(properties[kCGImagePropertyGPSDictionary])
        XCTAssertNil((properties[kCGImagePropertyExifDictionary] as? NSDictionary)?[kCGImagePropertyExifUserComment])
        XCTAssertLessThanOrEqual(properties[kCGImagePropertyPixelWidth] as! Int, 1600)
        FixtureURLProtocol.handler = { request in
            let body = try JSONSerialization.jsonObject(with: request.httpBody ?? Data(reading: request.httpBodyStream!)) as! [String: Any]
            XCTAssertEqual(body["image_base64"] as? String, exportedJPEG.base64EncodedString(), "Approval export must be the exact analyzed copy")
            return (200, Data(self.result.utf8))
        }
        _ = try await service().analyzePhoto(prepared.export.jpeg, scenario: "generic")
        XCTAssertEqual(prepared.export.jpeg, exportedJPEG)
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

final class GuardedRecognitionTests: XCTestCase {
    override func tearDown() { FixtureURLProtocol.handler = nil }
    func testLiveFailuresNeverAdviseRetryOrRepeatRequest() async throws {
        let config = APIConfiguration(baseURL: "http://127.0.0.1:8000", token: String(repeating: "t", count: 32), offline: false)
        for failure in ["http", "timeout", "invalidResponse"] {
            var calls = 0
            let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
            FixtureURLProtocol.handler = { _ in
                calls += 1
                if failure == "timeout" { throw URLError(.timedOut) }
                return failure == "http" ? (503, Data()) : (200, Data("invalid".utf8))
            }
            let service = try HTTPBeverageService(configuration: config, session: URLSession(configuration: options))
            do {
                _ = try await service.analyzePhoto(Data([1, 2, 3]), scenario: "ambiguous", mode: "meta_live", metaConsent: true)
                XCTFail("Expected unverified live result")
            } catch ServiceError.liveRecognitionUnverified {
                let message = ServiceError.liveRecognitionUnverified.localizedDescription
                XCTAssertTrue(message.contains("Do not retry"))
                XCTAssertFalse(message.contains("Retry when"))
            }
            XCTAssertEqual(calls, 1, "A failed live attempt must never be repeated automatically")
        }
    }

    func testLiveDisclosureRequiredBeforeNetwork() async throws {
        let config = APIConfiguration(baseURL: "http://127.0.0.1:8000", token: String(repeating: "t", count: 32), offline: false)
        let options = URLSessionConfiguration.ephemeral; options.protocolClasses = [FixtureURLProtocol.self]
        FixtureURLProtocol.handler = { _ in XCTFail("No transmission without explicit Meta consent"); return (500, Data()) }
        let service = try HTTPBeverageService(configuration: config, session: URLSession(configuration: options))
        do { _ = try await service.analyzePhoto(Data([1,2,3]), scenario: "ambiguous", mode: "meta_live"); XCTFail("Expected consent denial") }
        catch ServiceError.consent { }
    }
    func testLiveResponseNeedsReceiptAndSeparatesSource() throws {
        let identifier = UUID().uuidString
        let valid = """
        {"version":"recognition-v1","mode":"meta_live","model":"muse-spark-1.3","recognition_id":"\(identifier)","requires_confirmation":true,"candidates":[{"identity":"Tea","category":"tea","brand":null,"product":null,"product_id":null,"container_ml":300,"confidence":"low","uncertainty_reasons":["Verify capacity"]}]}
        """
        let result = try JSONDecoder().decode(RecognitionResult.self, from: Data(valid.utf8))
        XCTAssertNoThrow(try result.validate())
        XCTAssertEqual(result.recognitionId?.uuidString, identifier)
        XCTAssertEqual(result.candidates[0].category, "tea")
        let missing = valid.replacingOccurrences(of: "\"recognition_id\":\"\(identifier)\",", with: "")
        XCTAssertThrowsError(try JSONDecoder().decode(RecognitionResult.self, from: Data(missing.utf8)).validate())
    }
    func testReceiptSurvivesPendingPayloadEncoding() throws {
        let request = CreateBeverageRequest(category: "Tea", consumedMl: 125, consumedAt: .now, timezone: "America/New_York", source: "confirmed_recognition", recognitionId: UUID(), containerMl: 300)
        let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
        let decoder = JSONDecoder(); decoder.dateDecodingStrategy = .iso8601
        let data = try encoder.encode(request)
        let restored = try decoder.decode(CreateBeverageRequest.self, from: data)
        XCTAssertEqual(restored.recognitionId, request.recognitionId)
        XCTAssertTrue(String(decoding: data, as: UTF8.self).contains("recognition_id"))
        XCTAssertFalse(String(decoding: data, as: UTF8.self).contains("image_base64"))
    }

    func testDuplicateNamesAndIdenticalCandidatesKeepDistinctStableLocalIDs() throws {
        let candidate = """
        {"identity":"Tea","product_id":null,"container_ml":300,"confidence":"low","uncertainty_reasons":["Verify capacity"]}
        """
        let other = candidate.replacingOccurrences(of: "300", with: "450")
        let data = Data("""
        {"version":"recognition-v1","mode":"mock","model":"muse-spark-1.3","requires_confirmation":true,"candidates":[\(candidate),\(other),\(candidate)]}
        """.utf8)
        let result = try JSONDecoder().decode(RecognitionResult.self, from: data)
        try result.validate()
        let ids = result.candidates.map(\.id)
        XCTAssertEqual(Set(ids).count, 3)
        XCTAssertEqual(result.candidates.map(\.id), ids, "Reading IDs again must not regenerate them")
        XCTAssertEqual(result.candidates.map(\.containerMl), [300, 450, 300])
        let copied = result
        XCTAssertEqual(copied.candidates.map(\.id), ids)
        var edited = copied.candidates[1]
        edited.brand = "User correction"
        XCTAssertEqual(edited.id, ids[1], "Value updates must preserve selection identity")
        let wire = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(edited)) as? [String: Any])
        XCTAssertNil(wire["id"], "Local row identity must not change the API payload")
        let fresh = try JSONDecoder().decode(RecognitionResult.self, from: data)
        XCTAssertTrue(Set(fresh.candidates.map(\.id)).isDisjoint(with: ids), "A new response has new alternatives")
    }

    func testRecognitionLabelsSeparateMockLiveAndUnverifiedModes() {
        let mock = RecognitionPresentation(mode: "mock")
        let live = RecognitionPresentation(mode: "meta_live")
        XCTAssertEqual(mock.header, "Take or choose a photo, try mock analysis, then confirm what you drank.")
        XCTAssertEqual(live.header, "Take or choose a photo for live Meta analysis, then confirm what you drank.")
        for label in [mock.header, mock.photoDescription, mock.analyzeTitle, mock.resultTitle, mock.suggestionTitle] {
            XCTAssertTrue(label.lowercased().contains("mock"))
            XCTAssertFalse(label.lowercased().contains("live"))
        }
        for label in [live.header, live.photoDescription, live.analyzeTitle, live.resultTitle, live.suggestionTitle] {
            XCTAssertTrue(label.contains("Meta"))
            XCTAssertTrue(label.lowercased().contains("live"))
            XCTAssertFalse(label.lowercased().contains("mock"))
        }
        for mode: String? in [nil, "", "unknown"] {
            let unavailable = RecognitionPresentation(mode: mode)
            XCTAssertEqual(unavailable, .unavailable)
            for label in [unavailable.header, unavailable.photoDescription, unavailable.analyzeTitle, unavailable.resultTitle, unavailable.suggestionTitle] {
                XCTAssertFalse(label.lowercased().contains("mock"))
                XCTAssertFalse(label.lowercased().contains("live"))
                XCTAssertFalse(label.contains("Meta"))
            }
        }
    }
}
