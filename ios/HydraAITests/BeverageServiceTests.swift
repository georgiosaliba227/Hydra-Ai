import Foundation
import XCTest
@testable import HydraAI

final class BeverageServiceTests: XCTestCase {
    private var testFile: URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("HydraAI-tests-\(UUID().uuidString)")
            .appendingPathComponent("beverages.json")
    }

    func testManualLogRoundTripsV1FieldsAndPersists() async throws {
        let file = testFile
        defer { try? FileManager.default.removeItem(at: file.deletingLastPathComponent()) }
        let service = MockBeverageService(fileURL: file)
        let time = Date(timeIntervalSince1970: 1_700_000_000)
        let saved = try await service.createBeverage(.init(
            category: "tea", consumedMl: 250, consumedAt: time,
            timezone: "America/New_York", source: "manual"
        ))

        XCTAssertEqual(saved.consumedMl, 250)
        XCTAssertEqual(saved.source, "manual")
        XCTAssertEqual(saved.revision, 1)
        let persisted = try await MockBeverageService(fileURL: file).listBeverages()
        XCTAssertEqual(persisted, [saved])
        let json = try String(contentsOf: file, encoding: .utf8)
        XCTAssertTrue(json.contains("\"consumed_ml\""))
        XCTAssertTrue(json.contains("\"consumed_at\""))
        XCTAssertFalse(json.contains("consumedMl"))
    }

    func testRejectsInvalidVolumeWithoutPersisting() async throws {
        let file = testFile
        defer { try? FileManager.default.removeItem(at: file.deletingLastPathComponent()) }
        let service = MockBeverageService(fileURL: file)
        for amount in [0, -1, 5_001] {
            do {
                _ = try await service.createBeverage(.init(
                    category: "water", consumedMl: amount, consumedAt: .now,
                    timezone: "America/New_York", source: "manual"
                ))
                XCTFail("Invalid volume \(amount) was accepted")
            } catch BeverageValidationError.invalidVolume {
                // Expected.
            }
        }
        let stored = try await service.listBeverages()
        XCTAssertTrue(stored.isEmpty)
    }

    func testRejectsFutureConsumptionAndBadTimezone() async throws {
        let service = MockBeverageService(fileURL: testFile)
        let future = Date.now.addingTimeInterval(3_600)
        do {
            _ = try await service.createBeverage(.init(
                category: "water", consumedMl: 250, consumedAt: future,
                timezone: "America/New_York", source: "manual"
            ))
            XCTFail("Future consumption was accepted")
        } catch BeverageValidationError.futureDate { }
        do {
            _ = try await service.createBeverage(.init(
                category: "water", consumedMl: 250, consumedAt: .now,
                timezone: "not-a-timezone", source: "manual"
            ))
            XCTFail("Bad timezone was accepted")
        } catch BeverageValidationError.invalidTimezone { }
    }
}
