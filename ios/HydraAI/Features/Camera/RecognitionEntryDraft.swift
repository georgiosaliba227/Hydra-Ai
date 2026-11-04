import Foundation

enum RecognitionVolumeUnit: String, CaseIterable, Identifiable {
    case millilitres = "mL", usFlOz = "US fl oz", litres = "L"
    var id: String { rawValue }
    private var factor: Double {
        switch self { case .millilitres: 1; case .usFlOz: 29.5735295625; case .litres: 1000 }
    }
    func millilitres(_ input: String) -> Int? {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard text.range(of: #"^[0-9]{1,5}(?:[.,][0-9]{1,3})?$"#, options: .regularExpression) != nil,
              let value = Double(text.replacingOccurrences(of: ",", with: ".")) else { return nil }
        let ml = value * factor
        guard ml > 0, ml <= 5000, ml.isFinite else { return nil }
        let rounded = Int(ml.rounded())
        return (1...5000).contains(rounded) ? rounded : nil
    }
    func text(for ml: Int) -> String {
        let digits = self == .millilitres ? 0 : self == .usFlOz ? 2 : 3
        var result = String(format: "%.*f", locale: Locale(identifier: "en_US_POSIX"), digits, Double(ml) / factor)
        if result.contains(".") {
            while result.last == "0" { result.removeLast() }
            if result.last == "." { result.removeLast() }
        }
        return result
    }
}

/// User confirmation state. Changing units never changes a financial permit.
struct RecognitionEntryDraft {
    static let drinkTypes = ["Water", "Coffee", "Tea", "Sports drink", "Energy drink", "Juice", "Soda", "Milk", "Plant milk", "Beer", "Wine", "Other"]
    let candidate: RecognitionCandidate
    var identity: String
    private(set) var drinkType: String
    private(set) var volumeText: String
    private(set) var unit: RecognitionVolumeUnit = .millilitres
    private(set) var drankAll = true
    private(set) var correctedLiquidMl: Int?
    let allowsCapacityCorrection: Bool
    private(set) var capacityText: String
    private(set) var capacityUnit: RecognitionVolumeUnit = .millilitres
    private(set) var capacityWasEdited = false
    private var fullContainer = false

    init(candidate: RecognitionCandidate, allowsCapacityCorrection: Bool = false) {
        self.candidate = candidate
        self.allowsCapacityCorrection = allowsCapacityCorrection
        capacityText = candidate.suggestedCapacity.map(String.init) ?? ""
        identity = candidate.suggestedIdentity
        drinkType = Self.normalizedType(candidate.personalCorrection?.beverageType ?? candidate.category ?? candidate.identity)
        volumeText = candidate.wholeLiquidMl.map(String.init) ?? ""
        correctedLiquidMl = candidate.personalCorrection?.liquidMl
        applyWholeDrinkDefault()
    }
    private static func normalizedType(_ text: String) -> String {
        let normalized = text.lowercased().filter(\.isLetter)
        return drinkTypes.first { $0.lowercased().filter(\.isLetter) == normalized } ?? "Other"
    }
    var consumedMl: Int? { unit.millilitres(volumeText) }
    var assumption: String? { drankAll ? (fullContainer ? "full_container" : "entire_liquid") : nil }
    var confirmedCapacityMl: Int? {
        if allowsCapacityCorrection { return capacityUnit.millilitres(capacityText) }
        guard let capacity = candidate.suggestedCapacity,
              max(consumedMl ?? 0, correctedLiquidMl ?? 0) <= capacity else { return nil }
        return capacity
    }
    var valid: Bool {
        consumedMl != nil && !identity.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && identity.count <= 80 && capacityIsValid
    }
    var capacityIsValid: Bool {
        guard allowsCapacityCorrection else { return true }
        if capacityText.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty { return true }
        guard let capacity=confirmedCapacityMl else { return false }
        return consumedMl.map { $0<=capacity } ?? true
    }
    var isCorrection: Bool {
        identity.trimmingCharacters(in: .whitespacesAndNewlines) != candidate.identity ||
        drinkType != Self.normalizedType(candidate.category ?? candidate.identity) ||
        correctedLiquidMl != nil || confirmedCapacityMl != candidate.containerMl
    }
    var keepsProductMatch: Bool {
        identity.trimmingCharacters(in: .whitespacesAndNewlines) == candidate.identity &&
        drinkType == Self.normalizedType(candidate.category ?? candidate.identity) &&
        (!allowsCapacityCorrection || confirmedCapacityMl == candidate.containerMl)
    }
    mutating func setCapacity(_ text: String) {
        guard allowsCapacityCorrection else { return }
        capacityText=text; capacityWasEdited=true
        if fullContainer {
            unit = .millilitres
            volumeText=confirmedCapacityMl.map(String.init) ?? ""
            correctedLiquidMl=nil
            // Replacing text passes through empty/partial values. Keep the
            // full-container intent until the user edits the logged amount.
        }
    }
    mutating func setCapacityUnit(_ next: RecognitionVolumeUnit) {
        let capacity=confirmedCapacityMl
        capacityUnit=next
        if let capacity { capacityText=next.text(for:capacity) }
    }
    mutating func setVolume(_ text: String) {
        volumeText = text; fullContainer = false
        if drankAll { correctedLiquidMl = consumedMl }
    }
    mutating func setUnit(_ next: RecognitionVolumeUnit) {
        let ml = consumedMl
        unit = next
        if let ml { volumeText = next.text(for: ml) }
    }
    mutating func selectPreset(_ ml: Int) {
        unit = .millilitres; setVolume(String(ml))
    }
    mutating func setDrankAll(_ all: Bool) {
        drankAll = all; fullContainer = false
        unit = .millilitres
        if all { applyWholeDrinkDefault() } else { volumeText = "" }
    }
    private mutating func applyWholeDrinkDefault() {
        volumeText = (correctedLiquidMl ?? candidate.wholeLiquidMl).map(String.init) ?? ""
        if allowsCapacityCorrection && capacityWasEdited {
            if confirmedCapacityMl != nil { useFullContainer() }
            return
        }
        guard correctedLiquidMl == nil, let label = candidate.labelCapacityMl,
              (1...5000).contains(label), candidate.suggestedCapacity == label else { return }
        // A readable label supports capacity, not measured fill. The review
        // explicitly asks the user to confirm a full-container assumption.
        // Clearly partial fill and exact-photo liquid corrections keep priority.
        if candidate.estimatedLiquidMlMin == nil && candidate.estimatedLiquidMlMax == nil {
            useFullContainer()
        } else if let lower = candidate.estimatedLiquidMlMin, let upper = candidate.estimatedLiquidMlMax,
                  ["visual_estimate", "visible_measurement"].contains(candidate.volumeBasis ?? ""),
                  lower > 0, lower <= upper, upper == label {
            useFullContainer()
        }
    }
    mutating func useFullContainer() {
        guard let capacity = allowsCapacityCorrection ? confirmedCapacityMl : candidate.suggestedCapacity else { return }
        drankAll = true; fullContainer = true; correctedLiquidMl = nil
        unit = .millilitres; volumeText = String(capacity)
    }
    mutating func chooseType(_ type: String) {
        guard Self.drinkTypes.contains(type) else { return }
        let genericName = Self.drinkTypes.contains { $0.caseInsensitiveCompare(identity.trimmingCharacters(in: .whitespacesAndNewlines)) == .orderedSame }
        if identity.isEmpty || Self.normalizedType(identity) == drinkType && genericName { identity = type }
        drinkType = type
    }
}
