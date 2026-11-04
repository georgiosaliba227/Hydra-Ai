import XCTest
@testable import HydraAI

final class DateOrderingTests: XCTestCase {
    func testNonfiniteDatesNeverSatisfyEitherInclusiveBound() {
        let valid = Date(timeIntervalSinceReferenceDate: 800_000_000)
        for value in [Double.nan, .infinity, -.infinity] {
            let invalid = Date(timeIntervalSinceReferenceDate: value)
            XCTAssertFalse(DateOrdering.notAfter(invalid, valid))
            XCTAssertFalse(DateOrdering.notBefore(invalid, valid))
            XCTAssertFalse(DateOrdering.notAfter(valid, invalid))
            XCTAssertFalse(DateOrdering.notBefore(valid, invalid))
        }
    }
    func testEqualityAndReversedBoundsUseTheSameInclusiveInstant() {
        let cutoff = Date(timeIntervalSinceReferenceDate: 800_000_000)
        let before = cutoff.addingTimeInterval(-0.25), after = cutoff.addingTimeInterval(0.25)
        XCTAssertTrue(DateOrdering.notAfter(cutoff, cutoff)); XCTAssertTrue(DateOrdering.notBefore(cutoff, cutoff))
        XCTAssertTrue(DateOrdering.notAfter(before, cutoff)); XCTAssertTrue(DateOrdering.notBefore(after, cutoff))
        XCTAssertFalse(DateOrdering.notAfter(after, cutoff)); XCTAssertFalse(DateOrdering.notBefore(before, cutoff))
    }
    func testReferenceTimePreservesSubsecondOrderingWithoutEpochOffsetRounding() {
        let earlier = Date(timeIntervalSinceReferenceDate: 0.000000001)
        let later = Date(timeIntervalSinceReferenceDate: 0.000000002)
        XCTAssertTrue(DateOrdering.notAfter(earlier, later)); XCTAssertFalse(DateOrdering.notAfter(later, earlier))
        XCTAssertTrue(DateOrdering.notBefore(later, earlier)); XCTAssertFalse(DateOrdering.notBefore(earlier, later))
    }
    func testLoggingDateCutoffsIncludeExactBoundaryAndRejectNextRepresentableInstant() throws {
        let now = Date(timeIntervalSinceReferenceDate: 800_000_000)
        let limit = now.addingTimeInterval(60)
        func request(_ date: Date) -> CreateBeverageRequest {
            .init(category: "water", consumedMl: 125, consumedAt: date, timezone: "UTC", source: "manual")
        }
        XCTAssertNoThrow(try request(limit).validate(now: now))
        XCTAssertThrowsError(try request(Date(timeIntervalSinceReferenceDate: limit.timeIntervalSinceReferenceDate.nextUp)).validate(now: now))
        let earliest = Date(timeIntervalSince1970: 946_684_800)
        XCTAssertNoThrow(try request(earliest).validate(now: now))
        XCTAssertThrowsError(try request(Date(timeIntervalSinceReferenceDate: earliest.timeIntervalSinceReferenceDate.nextDown)).validate(now: now))
    }
}
