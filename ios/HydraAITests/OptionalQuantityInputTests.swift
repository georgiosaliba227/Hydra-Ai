import XCTest
@testable import HydraAI

final class OptionalQuantityInputTests: XCTestCase {
    func testInvalidNonemptyOptionalValueSurvivesUnitSwitchUntilExplicitlyCleared() {
        var input = CanonicalQuantityInput(canonicalValue: nil, system: .us, quantity: .mass)
        input.edit("-")
        XCTAssertNil(input.canonicalValue)
        input.switchSystem(.metric)
        XCTAssertEqual(input.text, "-")
        XCTAssertNil(input.canonicalValue)
        input.edit("")
        XCTAssertEqual(input.text, "")
        XCTAssertNil(input.canonicalValue)
    }
}
