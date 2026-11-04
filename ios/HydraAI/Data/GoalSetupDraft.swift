import Foundation

/// Editable manual answers, separate from both a reviewed snapshot and any confirmed backend goal.
struct GoalSetupDraft {
    enum AgeMethod: Hashable { case birthday, age }
    struct Review: Equatable { let profile: GoalProfile; let result: GoalReferenceResult }
    enum InputError: LocalizedError {
        case birthday, age, height, weight
        var errorDescription: String? {
            switch self {
            case .birthday: "Enter a valid birthday in MM/DD/YYYY format, or clear it and use age only."
            case .age: "Enter a whole-number age between 0 and 130, or clear the age field."
            case .height: "Correct or clear the optional height. Use a positive height up to 300 cm; inches must be less than 12."
            case .weight: "Correct or clear the optional weight before continuing."
            }
        }
    }
    var ageMethod: AgeMethod = .birthday { didSet { if oldValue != ageMethod { edited() } } }
    var birthdayText = "" { didSet { if oldValue != birthdayText { edited() } } }
    var ageText = "" { didSet { if oldValue != ageText { edited() } } }
    var referenceGroup: GoalReferenceGroup? { didSet { if oldValue != referenceGroup { edited() } } }
    var eligibility: GoalEligibility? { didSet { if oldValue != eligibility { edited() } } }
    var weightKg: Double? { didSet { edited() } }
    var weightInputValid = true { didSet { if oldValue != weightInputValid { edited() } } }
    var supplements: [GoalSupplement] = [] { didSet { if oldValue != supplements { edited() } } }
    private(set) var heightFeetText = ""
    private(set) var heightInchesText = ""
    private(set) var heightCentimetersText = ""
    private(set) var heightInputValid = true
    private(set) var inputRevision = 0
    private(set) var currentReview: Review?
    private var heightCm: Double?
    private var heightSystem: DisplayUnitSystem = .us

    init(profile: GoalProfile? = nil) {
        guard let profile else { return }
        if let birthday = profile.birthDate {
            let pieces = birthday.split(separator: "-")
            if pieces.count == 3 { birthdayText = "\(pieces[1])/\(pieces[2])/\(pieces[0])" }
        } else if let age = profile.ageYears { ageMethod = .age; ageText = String(age) }
        referenceGroup = profile.referenceGroup; eligibility = profile.eligibility
        heightCm = profile.heightCm; weightKg = profile.weightKg; supplements = profile.supplements
        renderHeight()
    }

    mutating func reset(profile: GoalProfile?) { self = GoalSetupDraft(profile: profile) }
    mutating func editHeightFeet(_ text: String) { heightFeetText = text; parseUSHeight(); edited() }
    mutating func editHeightInches(_ text: String) { heightInchesText = text; parseUSHeight(); edited() }
    mutating func editHeightCentimeters(_ text: String) {
        heightCentimetersText = text
        if text.isEmpty { heightCm = nil; heightInputValid = true }
        else if let value = Self.number(text), value > 0, value <= 300 { heightCm = value; heightInputValid = true }
        else { heightCm = nil; heightInputValid = false }
        edited()
    }
    /// Display conversion never reparses rounded text or discards an unresolved invalid answer.
    mutating func switchHeightSystem(_ system: DisplayUnitSystem) {
        heightSystem = system
        if heightInputValid { renderHeight() }
    }
    mutating func calculate(now: Date = .now, calendar: Calendar = .current) throws {
        currentReview = nil
        let profile = try resolve(now: now, calendar: calendar)
        currentReview = Review(profile: profile, result: GoalReferenceCalculator.evaluate(profile, now: now, calendar: calendar))
    }
    func resolve(now: Date = .now, calendar: Calendar = .current) throws -> GoalProfile {
        guard heightInputValid else { throw InputError.height }
        guard weightInputValid else { throw InputError.weight }
        var profile = GoalProfile(referenceGroup: referenceGroup, eligibility: eligibility,
                                  heightCm: heightCm, weightKg: weightKg, supplements: supplements)
        switch ageMethod {
        case .birthday:
            if !birthdayText.isEmpty {
                guard birthdayText.range(of: #"^[0-9]{2}/[0-9]{2}/[0-9]{4}$"#, options: .regularExpression) != nil else { throw InputError.birthday }
                let fields = birthdayText.split(separator: "/")
                profile.birthDate = "\(fields[2])-\(fields[0])-\(fields[1])"
            }
        case .age:
            if !ageText.isEmpty {
                guard ageText.range(of: #"^[0-9]{1,3}$"#, options: .regularExpression) != nil,
                      let age = Int(ageText), (0...130).contains(age) else { throw InputError.age }
                profile.ageYears = age
            }
        }
        try GoalProfileValidation.validate(profile, now: now, calendar: calendar)
        return profile
    }

    private mutating func edited() { currentReview = nil; inputRevision += 1 }
    private static func number(_ text: String) -> Double? {
        let normalized = text.replacingOccurrences(of: ",", with: ".")
        guard normalized.range(of: #"^[0-9]+(?:\.[0-9]*)?$|^\.[0-9]+$"#, options: .regularExpression) != nil,
              let value = Double(normalized), value.isFinite else { return nil }
        return value
    }
    private mutating func parseUSHeight() {
        if heightFeetText.isEmpty && heightInchesText.isEmpty { heightCm = nil; heightInputValid = true; return }
        guard let feet = heightFeetText.isEmpty ? 0 : Self.number(heightFeetText), feet.rounded(.towardZero) == feet,
              let inches = heightInchesText.isEmpty ? 0 : Self.number(heightInchesText), inches < 12 else {
            heightCm = nil; heightInputValid = false; return
        }
        let centimeters = (feet * 12 + inches) * 2.54
        guard centimeters.isFinite, centimeters > 0, centimeters <= 300 else { heightCm = nil; heightInputValid = false; return }
        heightCm = centimeters; heightInputValid = true
    }
    private mutating func renderHeight() {
        guard let heightCm else { heightFeetText = ""; heightInchesText = ""; heightCentimetersText = ""; return }
        if heightSystem == .metric { heightCentimetersText = Self.decimal(heightCm) }
        else {
            // Round the displayed total before splitting so 11.999 inches never renders as an invalid 12.
            let totalInches = (heightCm / 2.54 * 1000).rounded() / 1000
            let feet = floor(totalInches / 12)
            heightFeetText = String(Int(feet)); heightInchesText = Self.decimal(totalInches - feet * 12)
        }
    }
    private static func decimal(_ value: Double) -> String {
        var text = String(format: "%.3f", locale: Locale(identifier: "en_US_POSIX"), value)
        while text.hasSuffix("0") { text.removeLast() }
        if text.hasSuffix(".") { text.removeLast() }
        return text
    }
}
