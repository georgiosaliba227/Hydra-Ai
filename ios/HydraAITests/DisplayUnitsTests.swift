import XCTest
@testable import HydraAI

final class DisplayUnitsTests: XCTestCase {
    func testUSVolumeAndMassUseExactDefinedConversions() {
        XCTAssertEqual(DisplayUnitSystem.us.canonicalValue(8, quantity: .volume), 236.5882365, accuracy: 0.00000001)
        XCTAssertEqual(DisplayUnitSystem.us.canonicalValue(1, quantity: .mass), 0.45359237, accuracy: 0.00000001)
        XCTAssertEqual(DisplayUnitSystem.us.displayValue(236.5882365, quantity: .volume), 8, accuracy: 0.00000001)
    }
    func testTemperatureAndErrorBoundsHaveDifferentOffsets() {
        XCTAssertEqual(DisplayUnitSystem.us.canonicalValue(32, quantity: .temperature), 0, accuracy: 0.00000001)
        XCTAssertEqual(DisplayUnitSystem.us.canonicalValue(212, quantity: .temperature), 100, accuracy: 0.00000001)
        XCTAssertEqual(DisplayUnitSystem.us.displayValue(2, quantity: .temperatureDifference), 3.6, accuracy: 0.00000001)
    }
    func testInputPreservesUntouchedCanonicalAndTransientDecimalEdits() {
        var input = CanonicalQuantityInput(canonicalValue: 250, system: .us, quantity: .volume)
        XCTAssertEqual(input.text, "8.5")
        XCTAssertEqual(input.canonicalValue, 250)
        for _ in 0..<10 { input.switchSystem(.metric); input.switchSystem(.us) }
        XCTAssertEqual(input.canonicalValue, 250)
        input.edit("8.")
        XCTAssertEqual(input.text, "8.")
        XCTAssertEqual(input.canonicalValue!, 236.5882365, accuracy: 0.00000001)
        input.edit(".")
        XCTAssertNil(input.canonicalValue)
        XCTAssertEqual(input.text, ".")
        input.edit("8.5")
        XCTAssertEqual(input.canonicalValue!, 8.5 * 29.5735295625, accuracy: 0.00000001)
        input.switchSystem(.metric)
        XCTAssertEqual(input.canonicalValue!, 8.5 * 29.5735295625, accuracy: 0.00000001)
    }
    func testVettedTextConvertsRangesBoundsAndLeavesOtherNumbersAlone() {
        let source = "Loss 250 to 500 mL; mass 70 ± 0.1 kg; temperature 20 ± 2 °C; 30 min; 15 mg; 2026."
        XCTAssertEqual(DisplayUnitSystem.us.displayText(source), "Loss 8.4 to 17 fl oz; mass 154.324 ± 0.22 lb; temperature 68 ± 3.6 °F; 30 min; 15 mg; 2026.")
        XCTAssertEqual(DisplayUnitSystem.metric.displayText(source), source)
        XCTAssertEqual(DisplayUnitSystem.us.displayText("1,417 mL; 1,2 mL"), "47.9 fl oz; 1,2 mL")
        XCTAssertEqual(DisplayUnitSystem.us.displayText("Dose 250 mL/day; x250 mL; id_250 mL"), "Dose 8.5 fl oz/day; x250 mL; id_250 mL")
    }
    func testUnsupportedNumericTokensAreNeverPartiallyConverted() {
        for source in ["250-500 mL", "250 - 500 mL", "250 -500 mL", "250- 500 mL", "250—500 mL", "1/2 kg", "1e -3 kg", "1e-3 kg", "1e+3 mL", "−5 °C", "+-5 °C", "--5 °C", "1.2.3 kg", "x-5 °C", "id_-5 °C"] {
            XCTAssertEqual(DisplayUnitSystem.us.displayText(source), source, source)
        }
        XCTAssertEqual(DisplayUnitSystem.us.displayText("-5 °C"), "23 °F")
        XCTAssertEqual(DisplayUnitSystem.us.displayText("250–500 mL"), "8.4–17 fl oz")
    }
    func testWholeMlValidationBeforeRoundingAndSmallErrorDisplay() {
        XCTAssertEqual(CanonicalQuantityInput.wholeMilliliters(250), 250)
        XCTAssertNil(CanonicalQuantityInput.wholeMilliliters(5000.1))
        XCTAssertNil(CanonicalQuantityInput.wholeMilliliters(-1))
        XCTAssertNil(CanonicalQuantityInput.wholeMilliliters(.infinity))
        XCTAssertNotEqual(DisplayUnitSystem.us.number(0.01, quantity: .volume), "0")
    }
    func testInvalidAndNonfiniteInputDoesNotBecomeQuantity() {
        for text in ["", "nan", "inf", "-inf", "1e999", "garbage", "1,2,3"] {
            var input = CanonicalQuantityInput(canonicalValue: nil, system: .us, quantity: .volume)
            input.edit(text)
            XCTAssertNil(input.canonicalValue, text)
        }
    }
    @MainActor func testPreferenceDefaultsUSAndPersistsMetric() {
        let name = "DisplayUnitsTests-\(UUID())"
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        XCTAssertEqual(DisplayUnits(defaults: defaults).system, .us)
        let units = DisplayUnits(defaults: defaults)
        units.system = .metric
        XCTAssertEqual(DisplayUnits(defaults: defaults).system, .metric)
        XCTAssertEqual(units.volume(250), "250 mL")
    }
}
