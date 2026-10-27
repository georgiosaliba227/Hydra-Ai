import XCTest

/// Explicit opt-in physical-device tests with a dedicated synthetic backend.
final class PhysicalRecognitionTests: XCTestCase {
    private var env: [String: String] { ProcessInfo.processInfo.environment }
    override func setUpWithError() throws {
        continueAfterFailure = false
        guard env["HYDRA_E2E_PHYSICAL_EXTRAS"] == "1", env["HYDRA_E2E_BACKEND_URL"] != nil,
              env["HYDRA_E2E_API_TOKEN"] != nil else {
            throw XCTSkip("Requires opt-in synthetic physical-device session")
        }
    }
    private func launch(libraryFixture: Bool = false) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": env["HYDRA_E2E_BACKEND_URL"]!,
                                 "HYDRA_TEST_API_TOKEN": env["HYDRA_E2E_API_TOKEN"]!, "HYDRA_TEST_PHOTO_FIXTURE": "1"]
        if libraryFixture { app.launchEnvironment["HYDRA_TEST_LIBRARY_FIXTURE"] = "1" }
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        let settings = app.tabBars.buttons["Settings"]
        settings.tap()
        let save = app.buttons["saveConnection"]
        if !save.waitForExistence(timeout: 5), !settings.isSelected { settings.tap() }
        XCTAssertTrue(save.waitForExistence(timeout: 5)); save.tap()
        app.tabBars.buttons["Today"].tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch.waitForExistence(timeout: 15))
        return app
    }
    private func total(_ app: XCUIApplication) throws -> Int {
        try XCTUnwrap(Int(app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch.value as? String ?? ""))
    }
    private func assertTotal(_ app: XCUIApplication, _ expected: Int) {
        let label = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(label.waitForExistence(timeout: 15))
        let check = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", String(expected)), object: label)
        XCTAssertEqual(XCTWaiter.wait(for: [check], timeout: 20), .completed)
    }
    private func analyze(_ app: XCUIApplication) {
        let consent = app.switches["photoConsent"]
        if !consent.isHittable { app.swipeUp() }
        if (consent.value as? String) != "1" { consent.tap() }
        let button = app.buttons["analyzePhoto"]
        if !button.isHittable { app.swipeUp() }
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: button)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 5), .completed)
        button.tap()
    }
    private func scenario(_ app: XCUIApplication, _ name: String) {
        app.buttons["mockScenario"].tap()
        let option = app.buttons[name]
        XCTAssertTrue(option.waitForExistence(timeout: 5)); option.tap()
    }
    private func control(_ action: String) throws {
        guard env["HYDRA_E2E_FAULT_DRIVER"] == "stdout-v1", ["pause", "resume"].contains(action) else {
            throw XCTSkip("Requires the Mac-side stdout fault driver")
        }
        // The Mac driver watches this marker and signals only its owned mock
        // backend. No extra LAN access is requested by the UI test runner.
        let marker = "HYDRA_PHYSICAL_\(action.uppercased())_BACKEND_V1\n"
        FileHandle.standardOutput.write(Data(marker.utf8))
        Thread.sleep(forTimeInterval: 2)
    }
    func testExistingSyntheticPhotoThroughNativePicker() throws {
        let app = launch(libraryFixture: true)
        app.tabBars.buttons["Camera"].tap()
        app.buttons["addLibraryFixture"].tap()
        let permission = XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.firstMatch
        if permission.waitForExistence(timeout: 3) {
            let allow = permission.buttons.matching(NSPredicate(format: "label BEGINSWITH[c] 'Allow'")).firstMatch
            XCTAssertTrue(allow.exists); allow.tap()
        }
        XCTAssertTrue(app.staticTexts["libraryFixtureReady"].waitForExistence(timeout: 15))
        app.buttons["chooseBeveragePhoto"].tap()
        // Inspect only the date marker, never enumerate or pick personal assets.
        let image = app.images.matching(NSPredicate(format: "label CONTAINS '2050'")).firstMatch
        let cell = app.cells.matching(NSPredicate(format: "label CONTAINS '2050'")).firstMatch
        if image.waitForExistence(timeout: 8) { image.tap() }
        else if cell.exists { cell.tap() }
        else {
            let cancel = app.buttons["Cancel"]
            if cancel.exists { cancel.tap() }
            throw XCTSkip("System picker did not expose the synthetic asset's date; no personal asset was selected")
        }
        XCTAssertTrue(app.images["Selected beverage photo"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.buttons["analyzePhoto"].isEnabled)
        analyze(app)
        XCTAssertTrue(app.buttons["Enter or correct beverage details"].waitForExistence(timeout: 15))
    }
    func testMockAPIFailureThenExplicitAnalysisRetry() throws {
        let app = launch(); let initial = try total(app)
        app.tabBars.buttons["Camera"].tap(); app.buttons["syntheticPhoto"].tap()
        scenario(app, "API failure"); analyze(app)
        let alert = app.alerts["Analysis unavailable"]
        XCTAssertTrue(alert.waitForExistence(timeout: 20)); alert.buttons["OK"].tap()
        scenario(app, "Generic coffee"); analyze(app)
        XCTAssertTrue(app.buttons["Review Coffee (low confidence)"].waitForExistence(timeout: 20))
        app.tabBars.buttons["Today"].tap(); assertTotal(app, initial)
    }
    func testNetworkFailureAndPendingSaveRetryAfterRestart() throws {
        let app = launch(); let initial = try total(app)
        app.tabBars.buttons["Camera"].tap(); app.buttons["syntheticPhoto"].tap(); analyze(app)
        let enter = app.buttons["Enter or correct beverage details"]
        XCTAssertTrue(enter.waitForExistence(timeout: 20)); enter.tap()
        app.textFields["photoIdentity"].tap(); app.textFields["photoIdentity"].typeText("Network retry tea")
        app.textFields["photoContainer"].tap(); app.textFields["photoContainer"].typeText("300")
        app.textFields["photoConsumed"].tap(); app.textFields["photoConsumed"].typeText("125")
        app.buttons["photoKeyboardDone"].tap()
        app.switches["confirmPhotoDetails"].coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        try control("pause")
        do {
            app.buttons["savePhotoBeverage"].tap()
            let cancel = app.buttons["Cancel"]
            let completed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: cancel)
            XCTAssertEqual(XCTWaiter.wait(for: [completed], timeout: 40), .completed)
            app.swipeUp()
            let pendingMessage = app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Retry pending beverage'")).firstMatch
            XCTAssertTrue(pendingMessage.waitForExistence(timeout: 5))
            cancel.tap()
            app.terminate(); app.launchEnvironment = [:]; app.launch()
            XCTAssertTrue(app.buttons["retryPending"].waitForExistence(timeout: 20))
        } catch {
            try? control("resume")
            throw error
        }
        try control("resume")
        app.buttons["retryPending"].tap(); assertTotal(app, initial + 125)
        XCTAssertFalse(app.buttons["retryPending"].exists)
        app.terminate(); app.launch()
        assertTotal(app, initial + 125)
    }
}
