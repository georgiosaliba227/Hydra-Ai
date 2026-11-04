import XCTest

/// Dedicated synthetic backend only; this case never enables a provider.
final class CameraCorrectionsUITests: XCTestCase {
    func testEditConfirmAndPersonalMemoryWithSeparateTrainingOptIn() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard env["HYDRA_E2E_CAMERA_CORRECTIONS"] == "1",
              let url = env["HYDRA_E2E_BACKEND_URL"], let token = env["HYDRA_E2E_API_TOKEN"] else {
            throw XCTSkip("Requires a dedicated synthetic camera-correction backend")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": url, "HYDRA_TEST_API_TOKEN": token, "HYDRA_TEST_PHOTO_FIXTURE": "1"]
        app.launchHydra()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout: 15))
        let initial = try XCTUnwrap(total.metricMillilitersValue)
        app.tabBars.buttons["Camera"].tap()
        try analyzeFixture(app)
        let edit = app.buttons["editRecognitionEntry"]
        XCTAssertTrue(edit.waitForExistence(timeout: 15))
        if !edit.isHittable { app.swipeUp() }
        edit.tap()
        let identity = app.textFields["photoIdentity"]
        XCTAssertTrue(identity.waitForExistence(timeout: 10))
        replace(identity, with: "Corrected tea")
        app.buttons["photoDrinkType"].tap(); app.buttons["Tea"].tap()
        replace(app.textFields["photoConsumed"], with: "240")
        let confirm = app.buttons["savePhotoBeverage"]
        XCTAssertEqual(app.staticTexts["photoVolume"].label, "240 mL")
        app.buttons["logDifferentAmount"].tap()
        XCTAssertFalse(confirm.isEnabled, "Partial consumption requires a separate amount")
        app.textFields["photoConsumed"].tap(); app.textFields["photoConsumed"].typeText("125")
        app.buttons["photoKeyboardDone"].tap()
        let options = app.buttons["Correction options"]
        if !options.isHittable { app.swipeUp() }
        XCTAssertTrue(options.waitForExistence(timeout: 10)); options.tap()
        let remember = app.switches["rememberPhotoCorrection"]
        if !remember.isHittable { app.swipeUp() }
        XCTAssertEqual(remember.value as? String, "1")
        let training = app.switches["shareCorrectionTraining"]
        for _ in 0..<3 {
            if !training.isHittable || training.frame.maxY >= confirm.frame.minY { app.swipeUp() }
            else { break }
        }
        XCTAssertLessThan(training.frame.maxY, confirm.frame.minY, "The full switch must be above the sticky confirmation bar")
        XCTAssertEqual(training.value as? String, "0", "Training must never be preselected")
        let controls = XCTAttachment(screenshot: app.screenshot()); controls.name = "Optional correction controls"; controls.lifetime = .keepAlways; add(controls)
        // SwiftUI's outer Switch includes the multiline label row. Its native
        // child is the actual control, independent of text size or row height.
        training.switches.firstMatch.tap()
        XCTAssertEqual(training.value as? String, "1")
        XCTAssertTrue(confirm.isEnabled); confirm.tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Today"].tap()
        let counted = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", "\(initial + 125) mL"), object: total)
        XCTAssertEqual(XCTWaiter.wait(for: [counted], timeout: 15), .completed)
        app.tabBars.buttons["Camera"].tap()
        try analyzeFixture(app)
        let memory = app.staticTexts["personalCorrectionSuggestion"].firstMatch
        XCTAssertTrue(memory.waitForExistence(timeout: 15))
        XCTAssertTrue(memory.label.contains("Corrected tea"))
        XCTAssertTrue(app.staticTexts.matching(identifier: "personalLiquidCorrection").firstMatch.label.contains("240 mL"))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Demo suggested: Coffee")).firstMatch.exists)
    }

    private func analyzeFixture(_ app: XCUIApplication) throws {
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 10)); app.buttons["syntheticPhoto"].tap()
        app.buttons["mockScenario"].tap(); app.buttons["Generic coffee"].tap()
        let consent = app.switches["photoConsent"]
        if !consent.isHittable { app.swipeUp() }
        consent.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        let analyze = app.buttons["analyzePhoto"]
        XCTAssertTrue(analyze.isEnabled); analyze.tap()
    }

    private func replace(_ field: XCUIElement, with value: String) {
        let done = XCUIApplication().buttons["photoKeyboardDone"]
        if done.exists && done.isHittable { done.tap() }
        let app = XCUIApplication()
        for _ in 0..<12 {
            if field.exists && field.isHittable,
               field.frame.maxY < app.buttons["savePhotoBeverage"].frame.minY - 8 { break }
            app.swipeUp()
        }
        let current = field.value as? String ?? ""
        // Focus once at the trailing edge. A triple tap reuses its first point
        // after the keyboard moves the form and can hit another control.
        field.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5)).tap()
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        if !current.isEmpty && current != field.placeholderValue {
            field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: current.count))
        }
        field.typeText(value)
        XCTAssertEqual(field.value as? String, value)
        if done.exists && done.isHittable { done.tap() }
    }
}
