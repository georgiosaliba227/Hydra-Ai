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
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Camera"].tap()
        try analyzeFixture(app)
        let edit = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "editRecognition-")).firstMatch
        XCTAssertTrue(edit.waitForExistence(timeout: 15))
        if !edit.isHittable { app.swipeUp() }
        edit.tap()
        let identity = app.textFields["photoIdentity"]
        XCTAssertTrue(identity.waitForExistence(timeout: 10))
        replace(identity, with: "Corrected tea")
        replace(app.textFields["photoContainer"], with: "300")
        replace(app.textFields["correctedPhotoLiquid"], with: "240")
        let confirm = app.buttons["savePhotoBeverage"]
        XCTAssertFalse(confirm.isEnabled, "A detected container is not an amount consumed")
        app.textFields["photoConsumed"].tap(); app.textFields["photoConsumed"].typeText("125")
        app.buttons["photoKeyboardDone"].tap()
        let remember = app.switches["rememberPhotoCorrection"]
        if !remember.isHittable { app.swipeUp() }
        XCTAssertEqual(remember.value as? String, "1")
        let training = app.switches["shareCorrectionTraining"]
        if !training.isHittable { app.swipeUp() }
        XCTAssertEqual(training.value as? String, "0", "Training must never be preselected")
        training.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        XCTAssertEqual(training.value as? String, "1")
        XCTAssertTrue(confirm.isEnabled); confirm.tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        let counted = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '125'"), object: total)
        XCTAssertEqual(XCTWaiter.wait(for: [counted], timeout: 15), .completed)
        app.tabBars.buttons["Camera"].tap()
        try analyzeFixture(app)
        let memory = app.staticTexts["personalCorrectionSuggestion"].firstMatch
        XCTAssertTrue(memory.waitForExistence(timeout: 15))
        XCTAssertTrue(memory.label.contains("Corrected tea"))
        XCTAssertTrue(app.staticTexts["personalLiquidCorrection"].label.contains("240 mL"))
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
        let current = field.value as? String ?? ""
        if current.isEmpty || current == field.placeholderValue {
            // Repeated taps on an empty lower row can hit the keyboard toolbar
            // after the first tap changes layout. There is no text to select.
            // LabeledContent exposes the whole row as the field's AX frame;
            // its long visible-liquid label occupies the center of that row.
            field.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5)).tap()
        } else {
            field.tap(withNumberOfTaps: 3, numberOfTouches: 1)
            field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: current.count))
        }
        field.typeText(value)
        XCTAssertEqual(field.value as? String, value)
        if done.exists && done.isHittable { done.tap() }
    }
}
