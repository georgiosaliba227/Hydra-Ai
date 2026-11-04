import XCTest
@testable import HydraAI

final class GoalSetupDraftTests: XCTestCase {
    private let now = ISO8601DateFormatter().date(from: "2026-11-03T12:00:00Z")!
    private var calendar: Calendar { var c = Calendar(identifier: .gregorian); c.timeZone = TimeZone(secondsFromGMT: 0)!; return c }
    private func adult() -> GoalSetupDraft {
        var draft = GoalSetupDraft()
        draft.birthdayText = "01/15/1996"
        draft.referenceGroup = .men; draft.eligibility = .generalAdult
        return draft
    }
    // These tests catch silently discarded invalid optional answers and stale review snapshots.
    func testStrictBirthdayAndExclusiveAgeMethod() throws {
        var draft = adult()
        XCTAssertEqual(try draft.resolve(now: now, calendar: calendar).birthDate, "1996-01-15")
        for invalid in ["1/15/1996", "02/30/1996", "11/04/2026", "", "1996-01-15"] {
            draft.birthdayText = invalid
            if invalid.isEmpty { XCTAssertNil(try draft.resolve(now: now, calendar: calendar).birthDate) }
            else { XCTAssertThrowsError(try draft.resolve(now: now, calendar: calendar), invalid) }
        }
        draft.ageMethod = .age; draft.ageText = "30"
        let profile = try draft.resolve(now: now, calendar: calendar)
        XCTAssertEqual(profile.ageYears, 30); XCTAssertNil(profile.birthDate)
        draft.ageText = "30.0"; XCTAssertThrowsError(try draft.resolve(now: now, calendar: calendar))
    }
    func testOptionalHeightInvalidTextDoesNotBecomeAbsentOrVanishOnUnitSwitch() throws {
        var draft = adult()
        draft.editHeightFeet("five"); draft.editHeightInches("11")
        XCTAssertThrowsError(try draft.resolve(now: now, calendar: calendar))
        draft.switchHeightSystem(.metric); draft.switchHeightSystem(.us)
        XCTAssertEqual(draft.heightFeetText, "five")
        XCTAssertThrowsError(try draft.resolve(now: now, calendar: calendar))
        draft.editHeightFeet(""); draft.editHeightInches("")
        XCTAssertNil(try draft.resolve(now: now, calendar: calendar).heightCm)
        draft.weightInputValid = false
        XCTAssertThrowsError(try draft.resolve(now: now, calendar: calendar))
    }
    func testCanonicalHeightRoundTripsWithoutRoundedPresentationDrift() throws {
        var draft = GoalSetupDraft(profile: GoalProfile(heightCm: 180.123456789))
        for _ in 0..<20 { draft.switchHeightSystem(.metric); draft.switchHeightSystem(.us) }
        XCTAssertEqual(try XCTUnwrap(draft.resolve(now: now, calendar: calendar).heightCm), 180.123456789, accuracy: 1e-12)
        draft.editHeightFeet("5"); draft.editHeightInches("11")
        XCTAssertEqual(try XCTUnwrap(draft.resolve(now: now, calendar: calendar).heightCm), 180.34, accuracy: 1e-9)
        draft.editHeightInches("12"); XCTAssertThrowsError(try draft.resolve(now: now, calendar: calendar))
    }
    func testReviewIsBoundToEveryAnswerAndResetClearsIt() throws {
        var draft = adult(); try draft.calculate(now: now, calendar: calendar)
        XCTAssertNotNil(draft.currentReview)
        draft.weightKg = 80; XCTAssertNil(draft.currentReview)
        try draft.calculate(now: now, calendar: calendar)
        draft.supplements = [.creatine]; XCTAssertNil(draft.currentReview)
        draft.reset(profile: nil); XCTAssertEqual(draft.birthdayText, ""); XCTAssertNil(draft.referenceGroup); XCTAssertNil(draft.currentReview)
    }
    func testBodyContextDoesNotChangeSourceRowAndUnavailableCanStillSaveProfile() throws {
        var draft = adult(); try draft.calculate(now: now, calendar: calendar)
        guard case .reference(let baseline) = draft.currentReview?.result else { return XCTFail("Missing reference") }
        draft.editHeightFeet("5"); draft.editHeightInches("11"); draft.weightKg = 81.6466266; draft.supplements = [.creatine]
        try draft.calculate(now: now, calendar: calendar)
        guard case .reference(let contextual) = draft.currentReview?.result else { return XCTFail("Missing reference") }
        XCTAssertEqual(baseline, contextual); XCTAssertEqual(contextual.beverageMl, 3000); XCTAssertEqual(contextual.totalWaterMl, 3700)
        draft.eligibility = .unsure; try draft.calculate(now: now, calendar: calendar)
        guard case .unavailable = draft.currentReview?.result else { return XCTFail("Expected custom path") }
        XCTAssertEqual(try draft.resolve(now: now, calendar: calendar).eligibility, .unsure)
    }
}
