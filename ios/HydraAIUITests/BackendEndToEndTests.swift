import XCTest

/// Opt-in test against a running LOCAL, synthetic-data backend. No AI calls.
final class BackendEndToEndTests: XCTestCase {
    func testManualLoggingAndRestartPersistence() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        guard let backend = environment["HYDRA_E2E_BACKEND_URL"],
              let token = environment["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Set HYDRA_E2E_BACKEND_URL and HYDRA_E2E_API_TOKEN in the UI test runner environment to opt into a local backend integration run.")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap()
        let save = app.buttons["saveConnection"]
        XCTAssertTrue(save.waitForExistence(timeout: 10))
        save.tap()
        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout: 20), "Backend summary must be loaded before logging.")
        guard let value = total.value as? String, let initial = Int(value) else {
            XCTFail("Daily total must expose its integer mL value."); return
        }
        XCTAssertFalse(app.buttons["retryPending"].exists, "Resolve any existing pending test beverage before this run.")
        let logButton = app.buttons["logBeverage"]
        XCTAssertTrue(logButton.isEnabled)
        logButton.tap()
        let volume = app.textFields["consumedVolume"]
        XCTAssertTrue(volume.waitForExistence(timeout: 10))
        volume.tap(); volume.typeText("125")
        app.buttons["saveBeverage"].tap()
        let updated = String(initial + 125)
        let updatedExpectation = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", updated), object: total)
        XCTAssertEqual(XCTWaiter.wait(for: [updatedExpectation], timeout: 20), .completed, "Server total must increase by the actual consumed amount.")

        // Do not pass connection overrides again: success requires saved URL + Keychain.
        app.terminate()
        app.launchEnvironment = [:]
        app.launch()
        let restored = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(restored.waitForExistence(timeout: 20))
        let persistence = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", updated), object: restored)
        XCTAssertEqual(XCTWaiter.wait(for: [persistence], timeout: 20), .completed, "Relaunched app must retrieve the persisted backend total without injected credentials.")
        XCTAssertFalse(app.buttons["retryPending"].exists)
    }
    func testMockPhotoRequiresConfirmationAndLogsConsumedAmount() throws {
        let env = ProcessInfo.processInfo.environment
        guard let backend = env["HYDRA_E2E_BACKEND_URL"], let token = env["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires opt-in synthetic local backend")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token, "HYDRA_TEST_PHOTO_FIXTURE": "1"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout: 15))
        let initial = try XCTUnwrap(Int(total.value as? String ?? ""))
        app.tabBars.buttons["Camera"].tap()
        let header = app.staticTexts["recognitionHeader"]
        XCTAssertTrue(header.waitForExistence(timeout: 10))
        let mockHeader = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS 'mock analysis'"), object: header)
        XCTAssertEqual(XCTWaiter.wait(for: [mockHeader], timeout: 10), .completed)
        app.buttons["syntheticPhoto"].tap()
        let analyze = app.buttons["analyzePhoto"]
        XCTAssertTrue(analyze.waitForExistence(timeout: 10)); XCTAssertFalse(analyze.isEnabled)
        XCTAssertEqual(analyze.label, "Analyze with mock Meta response")
        app.switches["photoConsent"].tap()
        analyze.tap()
        let enter = app.buttons["Enter or correct beverage details"]
        if !enter.isHittable { app.swipeUp() }
        XCTAssertTrue(enter.waitForExistence(timeout: 15)); enter.tap()
        let save = app.buttons["savePhotoBeverage"]
        XCTAssertTrue(save.waitForExistence(timeout: 10)); XCTAssertFalse(save.isEnabled)
        let identity = app.textFields["photoIdentity"]
        identity.tap(); identity.typeText("Corrected tea")
        let capacity = app.textFields["photoContainer"]
        capacity.tap(); capacity.typeText("300")
        let consumed = app.textFields["photoConsumed"]
        consumed.tap(); consumed.typeText("125")
        XCTAssertFalse(save.isEnabled)
        app.buttons["photoKeyboardDone"].tap()
        let confirm = app.switches["confirmPhotoDetails"]
        if !confirm.isHittable { app.swipeUp() }
        confirm.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: save)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 5), .completed)
        XCTAssertTrue(save.isEnabled); save.tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Today"].tap()
        let expected = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", String(initial + 125)), object: total)
        XCTAssertEqual(XCTWaiter.wait(for: [expected], timeout: 20), .completed)
    }

}
