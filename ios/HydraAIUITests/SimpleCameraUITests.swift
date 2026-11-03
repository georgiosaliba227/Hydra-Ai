import XCTest

/// Generated photo and a local mock backend only; never enables Meta.
final class SimpleCameraUITests: XCTestCase {
    override func tearDownWithError() throws {
        let env = ProcessInfo.processInfo.environment
        guard let restore = env["HYDRA_E2E_RESTORE_BACKEND_URL"], let token = env["HYDRA_E2E_API_TOKEN"] else { return }
        // Physical runs use an isolated synthetic server. Restore the owner's
        // normal connection even if a UI assertion failed; never erase app data.
        let app = XCUIApplication(); app.terminate()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": restore, "HYDRA_TEST_API_TOKEN": token]
        app.launchHydra()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap()
        XCTAssertTrue(app.buttons["saveConnection"].waitForExistence(timeout: 10))
        app.buttons["saveConnection"].tap()
        XCTAssertEqual(app.textFields["backendURL"].value as? String, restore)
        app.tabBars.buttons["Today"].tap()
    }
    private func start() throws -> (XCUIApplication, Int) {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard env["HYDRA_E2E_SIMPLE_CAMERA"] == "1", let url = env["HYDRA_E2E_BACKEND_URL"], let token = env["HYDRA_E2E_API_TOKEN"] else { throw XCTSkip("Synthetic simple-camera backend required") }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": url, "HYDRA_TEST_API_TOKEN": token, "HYDRA_TEST_PHOTO_FIXTURE": "1"]
        app.launchHydra()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap()
        XCTAssertTrue(app.buttons["saveConnection"].waitForExistence(timeout: 10))
        app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout: 15))
        return (app, try XCTUnwrap(total.metricMillilitersValue))
    }
    private func analyze(_ app: XCUIApplication, scenario: String = "Generic coffee") {
        app.tabBars.buttons["Camera"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 10)); app.buttons["syntheticPhoto"].tap()
        app.buttons["mockScenario"].tap(); app.buttons[scenario].tap()
        let consent = app.switches["photoConsent"]
        if !consent.isHittable { app.swipeUp() }
        consent.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        app.buttons["analyzePhoto"].tap()
        XCTAssertTrue(app.staticTexts["photoVolume"].waitForExistence(timeout: 15))
    }
    private func total(_ app: XCUIApplication, _ expected: Int) {
        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        let check = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", "\(expected) mL"), object: total)
        XCTAssertEqual(XCTWaiter.wait(for: [check], timeout: 15), .completed)
    }
    private func replace(_ field: XCUIElement, _ text: String) {
        field.tap(withNumberOfTaps: 3, numberOfTouches: 1)
        let value = field.value as? String ?? ""
        if !value.isEmpty && value != field.placeholderValue { field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: value.count)) }
        field.typeText(text)
        let done = XCUIApplication().buttons["photoKeyboardDone"]
        if done.exists { done.tap() }
    }
    private func screenshot(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
    func test05FinishedDrinkNeedsOnlyConfirmAndPartialIsOptionalInEdit() throws {
        let (app, initial) = try start(); analyze(app)
        // Earlier edit tests can leave personal memory for this fixture. The
        // review must save the displayed whole-drink size in either case.
        let wholeDrinkMl = try XCTUnwrap(Int(app.staticTexts["photoVolume"].label.replacingOccurrences(of: ",", with: "").filter(\.isNumber)))
        XCTAssertEqual(app.staticTexts["consumptionAssumptionSummary"].label, "Confirm logs the whole drink.")
        XCTAssertFalse(app.textFields["photoConsumed"].exists)
        XCTAssertFalse(app.switches["assumeEntireLiquid"].exists)
        XCTAssertFalse(app.buttons["logDifferentAmount"].exists)
        XCTAssertTrue(app.buttons["savePhotoBeverage"].isEnabled)
        screenshot(app, "Finished drink one-tap review")
        app.buttons["editRecognitionEntry"].tap()
        let partial = app.buttons["logDifferentAmount"]
        if !partial.isHittable { app.swipeUp() }
        XCTAssertTrue(partial.waitForExistence(timeout: 5))
        XCTAssertFalse(app.switches["assumeEntireLiquid"].exists)
        app.buttons["savePhotoBeverage"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 15))
        total(app, initial + wholeDrinkMl)
    }
    func test06UnknownSizeIsEnteredInlineWithoutConsumptionQuestion() throws {
        let (app, initial) = try start(); analyze(app, scenario: "Missing nutrition")
        let size = app.textFields["photoConsumed"]
        XCTAssertTrue(size.waitForExistence(timeout: 5))
        XCTAssertEqual(size.placeholderValue, "Drink size")
        XCTAssertFalse(app.textFields["photoIdentity"].exists, "Size entry should not require opening Edit")
        XCTAssertFalse(app.switches["assumeEntireLiquid"].exists)
        XCTAssertFalse(app.buttons["savePhotoBeverage"].isEnabled)
        app.segmentedControls["photoVolumeUnit"].buttons["US fl oz"].tap()
        replace(size, "20")
        XCTAssertEqual(app.staticTexts["photoVolume"].label.replacingOccurrences(of: ",", with: "").filter(\.isNumber), "591")
        XCTAssertEqual(app.staticTexts["consumptionAssumptionSummary"].label, "Confirm logs the whole drink.")
        XCTAssertTrue(app.buttons["savePhotoBeverage"].isEnabled)
        screenshot(app, "Finished drink size entered inline")
        app.buttons["savePhotoBeverage"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 15))
        total(app, initial + 591)
    }
    func test01WholeLiquidReviewHasConfirmAndEditAndLogsAssumption() throws {
        let (app, initial) = try start(); analyze(app)
        XCTAssertEqual(app.staticTexts["photoVolume"].label, "200 mL")
        XCTAssertFalse(app.textFields["photoIdentity"].exists)
        XCTAssertFalse(app.textFields["photoConsumed"].exists)
        XCTAssertTrue(app.buttons["editRecognitionEntry"].exists)
        XCTAssertTrue(app.buttons["savePhotoBeverage"].isEnabled)
        screenshot(app, "Simple camera review")
        app.buttons["savePhotoBeverage"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 15))
        total(app, initial + 200)
        app.tabBars.buttons["History"].tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'beverageRow' AND label CONTAINS 'Assumed all liquid consumed'")).firstMatch.waitForExistence(timeout: 10))
    }
    func test02EditDrinkTypeAndFluidOunceVolume() throws {
        let (app, initial) = try start(); analyze(app)
        app.buttons["editRecognitionEntry"].tap()
        XCTAssertTrue(app.textFields["photoIdentity"].waitForExistence(timeout: 10))
        app.buttons["photoDrinkType"].tap(); app.buttons["Sports drink"].tap()
        replace(app.textFields["photoIdentity"], "BODYARMOR LYTE")
        app.segmentedControls["photoVolumeUnit"].buttons["US fl oz"].tap()
        replace(app.textFields["photoConsumed"], "16.9")
        XCTAssertEqual(app.staticTexts["photoVolume"].label, "500 mL")
        screenshot(app, "Simple camera edit")
        app.buttons["savePhotoBeverage"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 15))
        total(app, initial + 500)
    }
    func test03PartialAmountWithPresetAndUnitSelection() throws {
        let (app, initial) = try start(); analyze(app)
        app.buttons["editRecognitionEntry"].tap()
        app.buttons["volumePreset-355"].tap()
        XCTAssertEqual(app.staticTexts["photoVolume"].label, "355 mL")
        app.buttons["logDifferentAmount"].tap()
        XCTAssertFalse(app.buttons["savePhotoBeverage"].isEnabled)
        replace(app.textFields["photoConsumed"], "125")
        app.buttons["savePhotoBeverage"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 15))
        total(app, initial + 125)
    }
    func test04PrintedOneLitreLabelUsesFullContainerAssumption() throws {
        guard ProcessInfo.processInfo.environment["HYDRA_E2E_LABEL_CAMERA"] == "1" else {
            throw XCTSkip("One-litre label fixture required")
        }
        let (app, initial) = try start(); analyze(app)
        XCTAssertEqual(app.staticTexts["photoVolume"].label.replacingOccurrences(of: ",", with: "").filter(\.isNumber), "1000")
        XCTAssertTrue(app.staticTexts["photoVolume"].label.contains("mL"))
        XCTAssertEqual(app.staticTexts["photoLabelCapacity"].label.replacingOccurrences(of: ",", with: "").filter(\.isNumber), "1000")
        XCTAssertTrue(app.staticTexts["photoLabelCapacity"].label.hasPrefix("Printed size:"))
        XCTAssertEqual(app.staticTexts["consumptionAssumptionSummary"].label, "Confirm logs the whole drink.")
        XCTAssertTrue(app.buttons["editRecognitionEntry"].exists)
        XCTAssertTrue(app.buttons["savePhotoBeverage"].isEnabled)
        screenshot(app, "Printed one litre label review")
        app.buttons["savePhotoBeverage"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 15))
        total(app, initial + 1000)
        app.tabBars.buttons["History"].tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'beverageRow' AND label CONTAINS 'Assumed full container consumed'")).firstMatch.waitForExistence(timeout: 10))
    }

}
