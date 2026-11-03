import Foundation
import XCTest
@testable import HydraAI

final class GoalReferenceTests: XCTestCase {
    private var utc: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        return calendar
    }
    private func date(_ value: String) -> Date {
        ISO8601DateFormatter().date(from: value)!
    }
    private var now: Date { date("2026-11-03T12:00:00Z") }
    private func adult(_ age: Int = 30, group: GoalReferenceGroup = .men) -> GoalProfile {
        GoalProfile(ageYears: age, referenceGroup: group, eligibility: .generalAdult)
    }
    private func reference(_ profile: GoalProfile, now: Date? = nil, calendar: Calendar? = nil,
                           file: StaticString = #filePath, line: UInt = #line) throws -> GoalStartingReference {
        switch GoalReferenceCalculator.evaluate(profile, now: now ?? self.now, calendar: calendar ?? utc) {
        case .reference(let value): return value
        case .unavailable(let reason):
            XCTFail("Expected starting reference: \(reason.message)", file: file, line: line)
            throw NSError(domain: "GoalReferenceTests", code: 1)
        }
    }
    private func assertUnavailable(_ profile: GoalProfile, now: Date? = nil, calendar: Calendar? = nil,
                                   file: StaticString = #filePath, line: UInt = #line) {
        switch GoalReferenceCalculator.evaluate(profile, now: now ?? self.now, calendar: calendar ?? utc) {
        case .reference: XCTFail("Expected no automatic reference", file: file, line: line)
        case .unavailable(let reason): XCTAssertFalse(reason.message.isEmpty, file: file, line: line)
        }
    }

    // Catches using food-inclusive totals, an age coefficient, or the wrong published row.
    func testAdultBandsUsePublishedBeverageRowsSeparatelyFromTotalWater() throws {
        for age in [19, 30, 31, 50, 51, 70, 71, 90, 130] {
            for (group, beverage, total) in [(GoalReferenceGroup.men, 3000, 3700), (.women, 2200, 2700)] {
                let value = try reference(adult(age, group: group))
                XCTAssertEqual(value.beverageMl, beverage)
                XCTAssertEqual(value.totalWaterMl, total)
                XCTAssertEqual(value.ageYears, age)
                XCTAssertEqual(value.methodVersion, "adult-beverage-reference-nasem-2005-v1")
                XCTAssertEqual(value.sourceURL, "https://www.nationalacademies.org/read/10925/chapter/6")
            }
        }
    }

    func testNineteenthBirthdayBeforeOnAndAfter() throws {
        let profile = GoalProfile(birthDate: "2007-11-03", referenceGroup: .men, eligibility: .generalAdult)
        assertUnavailable(profile, now: date("2026-11-02T23:59:59Z"))
        XCTAssertEqual(try reference(profile, now: date("2026-11-03T00:00:00Z")).ageYears, 19)
        XCTAssertEqual(try reference(profile, now: date("2026-11-04T00:00:00Z")).beverageMl, 3000)
    }

    func testBirthdayUsesLocalCivilDayAndGregorianEvenForOtherCalendarIdentifiers() throws {
        let profile = GoalProfile(birthDate: "2007-11-03", referenceGroup: .women, eligibility: .generalAdult)
        var local = Calendar(identifier: .buddhist)
        local.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        assertUnavailable(profile, now: date("2026-11-03T07:59:59Z"), calendar: local)
        XCTAssertEqual(try reference(profile, now: date("2026-11-03T08:00:00Z"), calendar: local).ageYears, 19)
        local.timeZone = TimeZone(identifier: "Pacific/Kiritimati")!
        XCTAssertEqual(try reference(profile, now: date("2026-11-02T10:00:00Z"), calendar: local).ageYears, 19)
    }

    func testLeapBirthdayAdvancesOnMarchFirstInNonLeapYear() throws {
        let profile = GoalProfile(birthDate: "2008-02-29", referenceGroup: .men, eligibility: .generalAdult)
        assertUnavailable(profile, now: date("2027-02-28T23:59:59Z"))
        XCTAssertEqual(try reference(profile, now: date("2027-03-01T00:00:00Z")).ageYears, 19)
        XCTAssertEqual(try GoalProfileValidation.age(profile, now: date("2028-02-28T12:00:00Z"), calendar: utc), 19)
        XCTAssertEqual(try GoalProfileValidation.age(profile, now: date("2028-02-29T00:00:00Z"), calendar: utc), 20)
    }

    func testImpossibleMalformedAndFutureDatesCannotBecomeReferences() {
        for birthday in ["2007-02-29", "2008-02-30", "2007-13-03", "2007-00-03", "2007-11-00", "2007-1-03", "07-11-03", "2007-11-03T00:00:00Z", " 2007-11-03", "0000-11-03", "2026-11-04", "2027-01-01", ""] {
            let profile = GoalProfile(birthDate: birthday, referenceGroup: .men, eligibility: .generalAdult)
            XCTAssertThrowsError(try GoalProfileValidation.validate(profile, now: now, calendar: utc), birthday)
            assertUnavailable(profile)
        }
    }

    func testAgeOnlyIsSelfEnteredAndBothAgeMethodsAreRejected() throws {
        XCTAssertEqual(try reference(adult(19), now: date("2027-11-03T12:00:00Z")).ageYears, 19)
        let conflict = GoalProfile(birthDate: "2007-11-03", ageYears: 19, referenceGroup: .men, eligibility: .generalAdult)
        XCTAssertThrowsError(try GoalProfileValidation.validate(conflict, now: now, calendar: utc))
        assertUnavailable(conflict)
    }

    func testInputAgeBoundsApplyToBothMethodsWithoutMakingChildrenEligible() throws {
        for age in [0, 18, 19, 130] {
            XCTAssertNoThrow(try GoalProfileValidation.validate(adult(age), now: now, calendar: utc))
        }
        for age in [-1, 131, Int.max, Int.min] {
            XCTAssertThrowsError(try GoalProfileValidation.validate(adult(age), now: now, calendar: utc))
            assertUnavailable(adult(age))
        }
        assertUnavailable(adult(0)); assertUnavailable(adult(18))
        let oldest = GoalProfile(birthDate: "1896-11-03", referenceGroup: .men, eligibility: .generalAdult)
        XCTAssertEqual(try reference(oldest).ageYears, 130)
        let tooOld = GoalProfile(birthDate: "1895-11-03", referenceGroup: .men, eligibility: .generalAdult)
        XCTAssertThrowsError(try GoalProfileValidation.validate(tooOld, now: now, calendar: utc))
        assertUnavailable(tooOld)
    }

    func testMissingAnswersAreValidShapesButNeverProduceAnInferredReference() throws {
        let profiles = [GoalProfile(), GoalProfile(referenceGroup: .men, eligibility: .generalAdult),
                        GoalProfile(ageYears: 30, eligibility: .generalAdult),
                        GoalProfile(ageYears: 30, referenceGroup: .men), adult(30, group: .preferNotToSay)]
        for profile in profiles {
            XCTAssertNoThrow(try GoalProfileValidation.validate(profile, now: now, calendar: utc))
            assertUnavailable(profile)
        }
        XCTAssertNil(try GoalProfileValidation.age(GoalProfile(), now: now, calendar: utc))
    }

    func testExcludedOrUncertainApplicabilityAbstains() throws {
        for eligibility in [GoalEligibility.pregnantOrBreastfeeding, .clinicianDirectedFluid, .unsure] {
            var profile = adult(); profile.eligibility = eligibility
            XCTAssertNoThrow(try GoalProfileValidation.validate(profile, now: now, calendar: utc))
            assertUnavailable(profile)
        }
    }

    func testOptionalBodyMeasurementsRejectNonfiniteNonpositiveAndOversizedValues() {
        for invalid in [Double.nan, .infinity, -.infinity, 0, -1, 300.01] {
            var profile = adult(); profile.heightCm = invalid
            XCTAssertThrowsError(try GoalProfileValidation.validate(profile, now: now, calendar: utc))
            assertUnavailable(profile)
        }
        for invalid in [Double.nan, .infinity, -.infinity, 0, -1, 500.01] {
            var profile = adult(); profile.weightKg = invalid
            XCTAssertThrowsError(try GoalProfileValidation.validate(profile, now: now, calendar: utc))
            assertUnavailable(profile)
        }
    }

    func testOptionalBodyAndSupplementAnswersDoNotApplyNumericalAdjustments() throws {
        for group in [GoalReferenceGroup.men, .women] {
            let baseline = try reference(adult(group: group))
            for (height, weight, supplements) in [(0.1, 0.1, [GoalSupplement.creatine]),
                                                  (180, 80, [.electrolytes, .other]),
                                                  (300, 500, [.creatine, .electrolytes, .other])] {
                var profile = adult(group: group)
                profile.heightCm = height; profile.weightKg = weight; profile.supplements = supplements
                XCTAssertNoThrow(try GoalProfileValidation.validate(profile, now: now, calendar: utc))
                XCTAssertEqual(try reference(profile), baseline)
            }
        }
    }

    func testDuplicateAndOversizedSupplementAnswersAreRejected() {
        for supplements in [[GoalSupplement.creatine, .creatine], [.creatine, .electrolytes, .other, .other]] {
            var profile = adult(); profile.supplements = supplements
            XCTAssertThrowsError(try GoalProfileValidation.validate(profile, now: now, calendar: utc))
            assertUnavailable(profile)
        }
    }

    func testProfileRoundTripPreservesOptionalContextAndRejectsUnknownEnumValues() throws {
        let profile = GoalProfile(birthDate: "1996-02-29", referenceGroup: .women, eligibility: .generalAdult,
                                  heightCm: 170.18, weightKg: 68.0388555, supplements: [.creatine, .electrolytes])
        XCTAssertEqual(try JSONDecoder().decode(GoalProfile.self, from: JSONEncoder().encode(profile)), profile)
        for json in [#"{"supplements":["unreviewed"]}"#, #"{"referenceGroup":"inferred","supplements":[]}"#,
                     #"{"eligibility":"unreviewed","supplements":[]}"#] {
            XCTAssertThrowsError(try JSONDecoder().decode(GoalProfile.self, from: Data(json.utf8)))
        }
    }
}
