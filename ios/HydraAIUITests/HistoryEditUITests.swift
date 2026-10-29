import XCTest

/// Opt-in: corrects and deletes a log against a LOCAL synthetic-data backend. No AI calls.
final class HistoryEditUITests: XCTestCase {
    func testEditAndDeleteUpdateTheServerTotal() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        guard let backend = environment["HYDRA_E2E_BACKEND_URL"],
              let token = environment["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires opt-in local synthetic-data backend")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout: 20))
        guard let value = total.value as? String, let initial = Int(value) else { XCTFail("Daily total must be numeric"); return }

        func expectTotal(_ expected: Int, _ message: String) {
            app.tabBars.buttons["Today"].tap()
            let predicate = NSPredicate(format: "value == %@", String(expected))
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: predicate, object: total)], timeout: 20), .completed, message)
        }
        func row(_ milliliters: Int) -> XCUIElement {
            app.tabBars.buttons["History"].tap()
            let match = app.descendants(matching: .any)
                .matching(NSPredicate(format: "label CONTAINS %@", "\(milliliters) milliliters")).firstMatch
            XCTAssertTrue(match.waitForExistence(timeout: 15), "History must show the \(milliliters) mL log")
            return match
        }

        app.buttons["logBeverage"].tap()
        let volume = app.textFields["consumedVolume"]
        XCTAssertTrue(volume.waitForExistence(timeout: 10))
        volume.tap(); volume.typeText("137")
        app.buttons["saveBeverage"].tap()
        expectTotal(initial + 137, "Logging adds the consumed amount")

        row(137).swipeLeft()
        XCTAssertTrue(app.buttons["Edit"].waitForExistence(timeout: 5)); app.buttons["Edit"].tap()
        let edit = app.textFields["editVolume"]
        XCTAssertTrue(edit.waitForExistence(timeout: 10))
        edit.tap(); edit.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 6) + "211")
        app.buttons["saveBeverageEdit"].tap()
        expectTotal(initial + 211, "A correction replaces the logged amount")

        row(211).swipeLeft()
        XCTAssertTrue(app.buttons["Delete"].waitForExistence(timeout: 5)); app.buttons["Delete"].tap()
        let confirm = app.buttons["Delete 211 mL water"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 5)); confirm.tap()
        expectTotal(initial, "Deleting removes the log from the server total")
    }
}
