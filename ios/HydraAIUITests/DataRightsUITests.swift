import XCTest

/// Opt-in: deletes all data on a LOCAL synthetic-data backend and checks Today returns to zero.
final class DataRightsUITests: XCTestCase {
    func testDeleteAllMyDataClearsTotals() throws {
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
        app.buttons["logBeverage"].tap()
        let volume = app.textFields["consumedVolume"]
        XCTAssertTrue(volume.waitForExistence(timeout: 10)); volume.tap(); volume.typeText("123")
        app.buttons["saveBeverage"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout: 15))

        app.tabBars.buttons["Settings"].tap()
        let delete = app.buttons["deleteAllData"]
        for _ in 0..<4 where !delete.isHittable { app.swipeUp() }
        delete.tap()
        let confirm = app.sheets.buttons["Delete all my data"].exists ? app.sheets.buttons["Delete all my data"]
                                                                       : app.buttons.matching(identifier: "Delete all my data").element(boundBy: 1)
        XCTAssertTrue(confirm.waitForExistence(timeout: 5)); confirm.tap()
        XCTAssertTrue(app.staticTexts["dataMessage"].waitForExistence(timeout: 10))
        app.tabBars.buttons["Today"].tap()
        let zero = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", "0"), object: total)
        XCTAssertEqual(XCTWaiter.wait(for: [zero], timeout: 20), .completed, "Deleting all data empties today's total")
    }
}
