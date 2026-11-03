import SwiftUI

/// Only presentation converts. Storage, evidence and consent contracts remain mL/kg/°C.
enum DisplayQuantity { case volume, mass, temperature, temperatureDifference }

enum DisplayUnitSystem: String, CaseIterable {
    case us, metric
    var label: String { self == .us ? "US (fl oz, lb, °F)" : "Metric (mL, kg, °C)" }
    func symbol(for quantity: DisplayQuantity) -> String {
        switch quantity {
        case .volume: return self == .us ? "fl oz" : "mL"
        case .mass: return self == .us ? "lb" : "kg"
        case .temperature, .temperatureDifference: return self == .us ? "°F" : "°C"
        }
    }
    func spokenUnit(for quantity: DisplayQuantity) -> String {
        switch quantity {
        case .volume: return self == .us ? "US fluid ounces" : "milliliters"
        case .mass: return self == .us ? "pounds" : "kilograms"
        case .temperature, .temperatureDifference: return self == .us ? "degrees Fahrenheit" : "degrees Celsius"
        }
    }
    func canonicalValue(_ value: Double, quantity: DisplayQuantity) -> Double {
        guard self == .us else { return value }
        switch quantity {
        case .volume: return value * 29.5735295625
        case .mass: return value * 0.45359237
        case .temperature: return (value - 32) * 5 / 9
        case .temperatureDifference: return value * 5 / 9
        }
    }
    func displayValue(_ value: Double, quantity: DisplayQuantity) -> Double {
        guard self == .us else { return value }
        switch quantity {
        case .volume: return value / 29.5735295625
        case .mass: return value / 0.45359237
        case .temperature: return value * 9 / 5 + 32
        case .temperatureDifference: return value * 9 / 5
        }
    }
    /// Presentation of vetted canonical prose only. Never use for payload JSON or hashes.
    /// Unitless numbers, IDs, mg, minutes and provider model data remain unchanged.
    func displayText(_ canonicalText: String) -> String {
        guard self == .us else { return canonicalText }
        let numberPattern = #"(-?(?:[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?|\.[0-9]+))"#
        let pattern = #"(?<![A-Za-z0-9_.,])"# + numberPattern + #"(?:\s*(to|–|±)\s*"# + numberPattern + #")?\s+(mL|kg|°C)(?![A-Za-z])"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return canonicalText }
        var result = canonicalText
        for match in regex.matches(in: canonicalText, range: NSRange(canonicalText.startIndex..., in: canonicalText)).reversed() {
            func part(_ index: Int) -> String? {
                Range(match.range(at: index), in: canonicalText).map { String(canonicalText[$0]) }
            }
            guard let first = part(1).flatMap({ Double($0.replacingOccurrences(of: ",", with: "")) }), let unit = part(4), let target = Range(match.range, in: result) else { continue }
            let quantity: DisplayQuantity = unit == "mL" ? .volume : unit == "kg" ? .mass : .temperature
            var replacement = number(first, quantity: quantity)
            if let separator = part(2), let second = part(3).flatMap({ Double($0.replacingOccurrences(of: ",", with: "")) }) {
                if separator == "±" {
                    let errorQuantity: DisplayQuantity = quantity == .temperature ? .temperatureDifference : quantity
                    replacement += " ± " + number(second, quantity: errorQuantity)
                } else {
                    // As with typed intervals, round the two displayed ends outward.
                    let scale = quantity == .mass ? 1000.0 : 10.0
                    let low = floor(displayValue(first, quantity: quantity) * scale) / scale
                    let high = ceil(displayValue(second, quantity: quantity) * scale) / scale
                    replacement = number(canonicalValue(low, quantity: quantity), quantity: quantity)
                    replacement += (separator == "to" ? " to " : separator) + number(canonicalValue(high, quantity: quantity), quantity: quantity)
                }
            }
            result.replaceSubrange(target, with: replacement + " " + symbol(for: quantity))
        }
        return result
    }
    func number(_ canonical: Double, quantity: DisplayQuantity) -> String {
        let value = displayValue(canonical, quantity: quantity)
        guard value.isFinite else { return "Unknown" }
        if value != 0 && abs(value) < 1e-11 { return String(value) }
        let precision: Int = quantity == .mass ? 3 : (self == .metric && quantity == .volume ? 0 : 1)
        // Never visually turn a small nonzero instrument bound into zero.
        let digits = value != 0 && abs(value) < pow(10, -Double(precision))
            ? min(12, max(precision, Int(ceil(-log10(abs(value)))) + 1)) : precision
        var text = String(format: "%.*f", locale: Locale(identifier: "en_US_POSIX"), digits, value)
        if text.contains(".") { while text.hasSuffix("0") { text.removeLast() }; if text.hasSuffix(".") { text.removeLast() } }
        return text == "-0" ? "0" : text
    }
}

/// Keeps the canonical quantity separate from its rounded editable presentation.
/// Partial/invalid typing is retained; switching units never reparses rounded text.
struct CanonicalQuantityInput {
    private(set) var canonicalValue: Double?
    private(set) var text: String
    private(set) var system: DisplayUnitSystem
    let quantity: DisplayQuantity
    init(canonicalValue: Double?, system: DisplayUnitSystem, quantity: DisplayQuantity) {
        self.system = system; self.quantity = quantity
        self.canonicalValue = canonicalValue.flatMap { $0.isFinite ? $0 : nil }
        text = self.canonicalValue.map { system.number($0, quantity: quantity) } ?? ""
    }
    mutating func edit(_ value: String) {
        text = value
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: ",", with: ".")
        guard let number = Double(normalized), number.isFinite else { canonicalValue = nil; return }
        let converted = system.canonicalValue(number, quantity: quantity)
        canonicalValue = converted.isFinite ? converted : nil
    }
    mutating func switchSystem(_ system: DisplayUnitSystem) {
        self.system = system
        text = canonicalValue.map { system.number($0, quantity: quantity) } ?? ""
    }
    mutating func setCanonicalValue(_ value: Double?) {
        canonicalValue = value.flatMap { $0.isFinite ? $0 : nil }
        text = canonicalValue.map { system.number($0, quantity: quantity) } ?? ""
    }
    /// The API records beverage volume as whole mL; validate before rounding.
    static func wholeMilliliters(_ value: Double?, range: ClosedRange<Int> = 1...5_000) -> Int? {
        guard let value, value.isFinite, value >= Double(range.lowerBound), value <= Double(range.upperBound) else { return nil }
        return Int(value.rounded())
    }
}

@MainActor final class DisplayUnits: ObservableObject {
    private let defaults: UserDefaults
    static let preferenceKey = "hydra.displayUnitSystem"
    @Published var system: DisplayUnitSystem { didSet { defaults.set(system.rawValue, forKey: Self.preferenceKey) } }
    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        #if DEBUG
        let override = ProcessInfo.processInfo.environment["HYDRA_TEST_UNIT_SYSTEM"].flatMap(DisplayUnitSystem.init(rawValue:))
        #else
        let override: DisplayUnitSystem? = nil
        #endif
        system = override ?? defaults.string(forKey: Self.preferenceKey).flatMap(DisplayUnitSystem.init(rawValue:)) ?? .us
    }
    func format(_ canonical: Double, quantity: DisplayQuantity, includeUnit: Bool = true) -> String {
        guard canonical.isFinite else { return "Unknown" }
        return system.number(canonical, quantity: quantity) + (includeUnit ? " " + system.symbol(for: quantity) : "")
    }
    func text(_ canonicalText: String) -> String { system.displayText(canonicalText) }
    func volume(_ value: Double) -> String { format(value, quantity: .volume) }
    func volume(_ value: Int) -> String { volume(Double(value)) }
    func volumeAccessibility(_ value: Int) -> String { "\(system.number(Double(value), quantity: .volume)) \(system.spokenUnit(for: .volume))" }
    func mass(_ value: Double) -> String { format(value, quantity: .mass) }
    func temperature(_ value: Double) -> String { format(value, quantity: .temperature) }
    func range(_ lower: Double, _ upper: Double, quantity: DisplayQuantity = .volume) -> String {
        // Display interval endpoints outward so rounding cannot imply a narrower estimate.
        let scale = quantity == .mass ? 1000.0 : (system == .metric && quantity == .volume ? 1.0 : 10.0)
        let low = floor(system.displayValue(lower, quantity: quantity) * scale) / scale
        let high = ceil(system.displayValue(upper, quantity: quantity) * scale) / scale
        return "\(system.number(system.canonicalValue(low, quantity: quantity), quantity: quantity))–\(system.number(system.canonicalValue(high, quantity: quantity), quantity: quantity)) \(system.symbol(for: quantity))"
    }
}

/// Reusable canonical binding for forms. Parent validation always receives canonical units.
struct CanonicalQuantityField: View {
    @EnvironmentObject private var units: DisplayUnits
    let title: String
    @Binding var value: Double?
    let quantity: DisplayQuantity
    var accessibilityIdentifier: String?
    @State private var input: CanonicalQuantityInput
    @FocusState private var isFocused: Bool
    init(_ title: String, value: Binding<Double?>, quantity: DisplayQuantity, accessibilityIdentifier: String? = nil) {
        self.title = title; _value = value; self.quantity = quantity; self.accessibilityIdentifier = accessibilityIdentifier
        _input = State(initialValue: CanonicalQuantityInput(canonicalValue: value.wrappedValue, system: .us, quantity: quantity))
    }
    var body: some View {
        HStack {
            TextField(title, text: Binding(get: { input.text }, set: { text in
                input.edit(text); value = input.canonicalValue
            }))
            .focused($isFocused)
            .keyboardType(quantity == .temperature ? .numbersAndPunctuation : .decimalPad)
            .accessibilityLabel("\(title) in \(units.system.spokenUnit(for: quantity))")
            .accessibilityIdentifier(accessibilityIdentifier ?? title)
            Text(units.system.symbol(for: quantity)).foregroundStyle(.secondary).accessibilityHidden(true)
        }
        .toolbar {
            if isFocused {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") { isFocused = false }
                }
            }
        }
        .onAppear { input.setCanonicalValue(value); input.switchSystem(units.system) }
        .onChange(of: units.system) { _, system in input.switchSystem(system) }
        .onChange(of: value) { _, value in
            // Avoid turning the user's "8." into "8" during their own edit.
            if value != input.canonicalValue { input.setCanonicalValue(value) }
        }
    }
}
