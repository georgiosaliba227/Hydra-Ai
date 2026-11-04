import Foundation

/// An approximate population starting reference, not an individual requirement.
struct GoalStartingReference: Codable, Equatable {
    let beverageMl: Int
    /// Food-inclusive water is explanatory context; it is never the logged-beverage goal.
    let totalWaterMl: Int
    let ageYears: Int
    let methodVersion: String
    let sourceURL: String
}

enum GoalReferenceUnavailableReason: Equatable, LocalizedError {
    case invalidProfile(String)
    case missingAge, under19, missingReferenceGroup, declinedReferenceGroup, missingEligibility
    case unsupportedEligibility(GoalEligibility)

    var message: String {
        switch self {
        case .invalidProfile(let reason): reason
        case .missingAge: "Enter your age or birthday to see a starting reference, or choose a custom goal."
        case .under19: "This starting reference is for adults aged 19 or older. You can choose a custom goal."
        case .missingReferenceGroup: "Choose a published reference group, or choose a custom goal."
        case .declinedReferenceGroup: "No reference group was selected. You can choose a custom goal."
        case .missingEligibility: "Answer whether the general adult reference applies, or choose a custom goal."
        case .unsupportedEligibility(.pregnantOrBreastfeeding):
            "This general adult reference does not cover pregnancy or breastfeeding. You can choose a custom goal."
        case .unsupportedEligibility(.clinicianDirectedFluid):
            "A general starting reference is unavailable with clinician-directed fluid management. Follow your clinician's guidance when choosing a custom goal."
        case .unsupportedEligibility(.unsure), .unsupportedEligibility(.generalAdult):
            "A starting reference is unavailable when its applicability is uncertain. You can choose a custom goal."
        }
    }
    var errorDescription: String? { message }
}

enum GoalReferenceResult: Equatable {
    case reference(GoalStartingReference)
    case unavailable(GoalReferenceUnavailableReason)
}

enum GoalReferenceCalculator {
    static let methodVersion = "adult-beverage-reference-nasem-2005-v1"
    static let sourceURL = "https://www.nationalacademies.org/read/10925/chapter/6"

    static func evaluate(_ profile: GoalProfile, now: Date = .now, calendar: Calendar = .current) -> GoalReferenceResult {
        do {
            try GoalProfileValidation.validate(profile, now: now, calendar: calendar)
            guard let age = try GoalProfileValidation.age(profile, now: now, calendar: calendar) else {
                return .unavailable(.missingAge)
            }
            guard age >= 19 else { return .unavailable(.under19) }
            guard let eligibility = profile.eligibility else { return .unavailable(.missingEligibility) }
            guard eligibility == .generalAdult else { return .unavailable(.unsupportedEligibility(eligibility)) }
            guard let group = profile.referenceGroup else { return .unavailable(.missingReferenceGroup) }
            let beverageMl: Int, totalWaterMl: Int
            switch group {
            case .men: beverageMl = 3000; totalWaterMl = 3700
            case .women: beverageMl = 2200; totalWaterMl = 2700
            case .preferNotToSay: return .unavailable(.declinedReferenceGroup)
            }
            // Published approximate beverage portions are used directly. Body size,
            // supplements, exercise and heat supply no numerical coefficient here.
            return .reference(GoalStartingReference(beverageMl: beverageMl, totalWaterMl: totalWaterMl,
                                                     ageYears: age, methodVersion: methodVersion, sourceURL: sourceURL))
        } catch {
            return .unavailable(.invalidProfile(error.localizedDescription))
        }
    }
}
