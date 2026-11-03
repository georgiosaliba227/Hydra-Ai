import XCTest

/// Explicit disposable-backend fixture: one invented 250 mL drink, no real profile.
final class USUnitsEndToEndTests: XCTestCase {
    func testUSLoggingUntouchedEditMetricSwitchAndSavedConnection() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard env["HYDRA_E2E_US_UNITS"] == "1", let backend = env["HYDRA_E2E_BACKEND_URL"],
              let token = env["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires disposable backend seeded with exactly 250 mL of invented intake")
        }
        let app = XCUIApplication()
        let suite = "HydraUITests.US.\(UUID().uuidString)"
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token,
            "HYDRA_TEST_UNIT_SYSTEM": "us", "HYDRA_TEST_CONTEXT_SETUP": "skip", "HYDRA_TEST_CONTEXT_SUITE": suite]
        app.launch(); addTeardownBlock { app.terminate() }
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 10))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        expect(total, "8.5 fl oz")
        app.tabBars.buttons["History"].tap()
        let row = app.descendants(matching: .any).matching(identifier: "beverageRow").firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10)); row.swipeLeft()
        app.buttons["Edit"].tap()
        XCTAssertTrue(app.textFields["editVolume"].waitForExistence(timeout: 5))
        // Keep the rounded 8.5 fl oz presentation untouched; save must retain 250 mL.
        app.buttons["saveBeverageEdit"].tap()
        app.tabBars.buttons["Today"].tap()
        app.buttons["logBeverage"].tap()
        let amount = app.textFields["consumedVolume"]
        XCTAssertTrue(amount.waitForExistence(timeout: 5)); amount.tap(); amount.typeText("8")
        app.buttons["saveBeverage"].tap()
        expect(total, "16.5 fl oz")
        app.tabBars.buttons["Settings"].tap()
        let goal = app.textFields["goalField"]; reveal(goal, app)
        goal.tap(); goal.typeText("64")
        if app.buttons["Done"].exists { app.buttons["Done"].tap() }
        let saveGoal = app.buttons["saveGoal"]; reveal(saveGoal, app); saveGoal.tap()
        XCTAssertTrue(app.staticTexts["goalMessage"].waitForExistence(timeout: 5))
        let picker = app.buttons["displayUnitsPicker"]
        for _ in 0..<16 where !picker.isHittable { app.swipeDown() }
        XCTAssertTrue(picker.isHittable); picker.tap()
        app.buttons["Metric (mL, kg, °C)"].tap()
        reveal(goal, app)
        XCTAssertEqual(goal.value as? String, "1893") // round(64 US fl oz), preserved at the API boundary.
        app.tabBars.buttons["Today"].tap()
        expect(total, "487 mL") // 250 + round(8 × 29.5735295625), never 251 +237.
        app.terminate()
        app.launchEnvironment = ["HYDRA_TEST_CONTEXT_SETUP": "skip", "HYDRA_TEST_CONTEXT_SUITE": suite]
        app.launch()
        let restored = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        expect(restored, "487 mL")
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = "Exact synthetic intake retained across US editing, metric switch and credential-free relaunch"
        image.lifetime = .keepAlways; add(image)
    }

    private func expect(_ element: XCUIElement, _ value: String) {
        XCTAssertTrue(element.waitForExistence(timeout: 15))
        let check = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", value), object: element)
        XCTAssertEqual(XCTWaiter.wait(for: [check], timeout: 15), .completed)
    }
    private func reveal(_ element: XCUIElement, _ app: XCUIApplication) {
        for _ in 0..<16 where !element.isHittable { app.swipeUp() }
        XCTAssertTrue(element.isHittable)
    }
}
