import Foundation

enum GoalReferenceGroup: String, Codable, CaseIterable { case men, women, preferNotToSay }
enum GoalEligibility: String, Codable, CaseIterable { case generalAdult, pregnantOrBreastfeeding, clinicianDirectedFluid, unsure }
enum GoalSupplement: String, Codable, CaseIterable { case creatine, electrolytes, other }

/// Manually supplied local context. Only the separately confirmed beverage goal leaves this device.
/// Shape validity is separate from eligibility for the published adult reference.
struct GoalProfile: Codable, Equatable {
    var birthDate: String?
    var ageYears: Int?
    var referenceGroup: GoalReferenceGroup?
    var eligibility: GoalEligibility?
    var heightCm: Double?
    var weightKg: Double?
    var supplements: [GoalSupplement]

    init(birthDate: String? = nil, ageYears: Int? = nil, referenceGroup: GoalReferenceGroup? = nil,
         eligibility: GoalEligibility? = nil, heightCm: Double? = nil, weightKg: Double? = nil,
         supplements: [GoalSupplement] = []) {
        self.birthDate = birthDate; self.ageYears = ageYears; self.referenceGroup = referenceGroup
        self.eligibility = eligibility; self.heightCm = heightCm; self.weightKg = weightKg
        self.supplements = supplements
    }
}

enum GoalProfileValidationError: LocalizedError, Equatable {
    case conflictingAgeMethods, invalidBirthDate, futureBirthDate, invalidAge
    case invalidHeight, invalidWeight, invalidSupplements

    var errorDescription: String? {
        switch self {
        case .conflictingAgeMethods: "Choose either birthday or self-entered age, using one method at a time."
        case .invalidBirthDate: "Enter a valid Gregorian birthday in YYYY-MM-DD format."
        case .futureBirthDate: "Birthday cannot be in the future."
        case .invalidAge: "Age must be between 0 and 130 years."
        case .invalidHeight: "Optional height must be a finite positive value no greater than 300 cm."
        case .invalidWeight: "Optional weight must be a finite positive value no greater than 500 kg."
        case .invalidSupplements: "Choose each supplement context once, with at most three choices."
        }
    }
}

enum GoalProfileValidation {
    static func validate(_ profile: GoalProfile, now: Date = .now, calendar: Calendar = .current) throws {
        _ = try age(profile, now: now, calendar: calendar)
        if let height = profile.heightCm, !height.isFinite || height <= 0 || height > 300 {
            throw GoalProfileValidationError.invalidHeight
        }
        if let weight = profile.weightKg, !weight.isFinite || weight <= 0 || weight > 500 {
            throw GoalProfileValidationError.invalidWeight
        }
        guard profile.supplements.count <= 3, Set(profile.supplements).count == profile.supplements.count else {
            throw GoalProfileValidationError.invalidSupplements
        }
    }

    /// Derives civil age with Gregorian dates in the supplied calendar's timezone.
    /// A February 29 birthday advances on March 1 in a non-leap year.
    /// Self-entered age stays unchanged until the user edits it.
    static func age(_ profile: GoalProfile, now: Date = .now, calendar: Calendar = .current) throws -> Int? {
        guard profile.birthDate == nil || profile.ageYears == nil else {
            throw GoalProfileValidationError.conflictingAgeMethods
        }
        if let age = profile.ageYears {
            guard (0...130).contains(age) else { throw GoalProfileValidationError.invalidAge }
            return age
        }
        guard let birthday = profile.birthDate else { return nil }
        guard birthday.range(of: #"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"#, options: .regularExpression) != nil else {
            throw GoalProfileValidationError.invalidBirthDate
        }
        let fields = birthday.split(separator: "-").compactMap { Int($0) }
        guard fields.count == 3, fields[0] > 0 else { throw GoalProfileValidationError.invalidBirthDate }
        let year = fields[0], month = fields[1], day = fields[2]
        // Validate the Gregorian civil date in UTC so historical skipped local days or
        // midnight DST transitions cannot normalize an otherwise valid birthday.
        var gregorian = Calendar(identifier: .gregorian)
        gregorian.timeZone = TimeZone(secondsFromGMT: 0)!
        guard let parsed = gregorian.date(from: DateComponents(year: year, month: month, day: day)),
              gregorian.dateComponents([.year, .month, .day], from: parsed) == DateComponents(year: year, month: month, day: day) else {
            throw GoalProfileValidationError.invalidBirthDate
        }
        gregorian.timeZone = calendar.timeZone
        let today = gregorian.dateComponents([.year, .month, .day], from: now)
        guard let currentYear = today.year, let currentMonth = today.month, let currentDay = today.day else {
            throw GoalProfileValidationError.invalidBirthDate
        }
        guard year < currentYear || (year == currentYear && (month < currentMonth || (month == currentMonth && day <= currentDay))) else {
            throw GoalProfileValidationError.futureBirthDate
        }
        let beforeBirthday = currentMonth < month || (currentMonth == month && currentDay < day)
        let age = currentYear - year - (beforeBirthday ? 1 : 0)
        guard (0...130).contains(age) else { throw GoalProfileValidationError.invalidAge }
        return age
    }
}
