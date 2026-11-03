import XCTest
@testable import HydraAI

final class DateBoundaryTests: XCTestCase {
    func testReferenceEpochAdjacentInstantsRemainDistinct() {
        let earlier = Date(timeIntervalSinceReferenceDate: 0.000000001)
        let later = Date(timeIntervalSinceReferenceDate: 0.000000002)
        XCTAssertFalse(DateBoundary.onOrBefore(later, earlier))
        XCTAssertFalse(DateBoundary.onOrAfter(earlier, later))
    }
    func testInclusiveBoundsUseFiniteTimestamps() {
        let date = Date(timeIntervalSince1970: 946_684_800)
        XCTAssertTrue(DateBoundary.onOrAfter(date, date))
        XCTAssertTrue(DateBoundary.onOrBefore(date, date))
        XCTAssertFalse(DateBoundary.onOrAfter(date.addingTimeInterval(-1), date))
        XCTAssertFalse(DateBoundary.onOrBefore(date.addingTimeInterval(1), date))
        for value in [Double.nan, .infinity, -.infinity] {
            let invalid = Date(timeIntervalSince1970: value)
            XCTAssertFalse(DateBoundary.onOrAfter(invalid, date))
            XCTAssertFalse(DateBoundary.onOrBefore(invalid, date))
            XCTAssertFalse(DateBoundary.onOrAfter(date, invalid))
            XCTAssertFalse(DateBoundary.onOrBefore(date, invalid))
        }
    }
    func testCreationKeepsHistoricalAndFutureDateChecksAtExactBoundaries() throws {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let earliest = Date(timeIntervalSince1970: 946_684_800)
        func request(_ date: Date) -> CreateBeverageRequest {
            CreateBeverageRequest(category: "Tea", consumedMl: 200, consumedAt: date, timezone: "UTC", source: "manual")
        }
        XCTAssertNoThrow(try request(earliest).validate(now: now))
        XCTAssertNoThrow(try request(now.addingTimeInterval(60)).validate(now: now))
        XCTAssertThrowsError(try request(earliest.addingTimeInterval(-1)).validate(now: now))
        XCTAssertThrowsError(try request(now.addingTimeInterval(61)).validate(now: now))
    }
}
