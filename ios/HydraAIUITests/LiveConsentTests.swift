import XCTest

/// Only the dedicated local fake-provider server may enable this case.
final class LiveConsentTests: XCTestCase {
    /// Opt-in local adapter test. The sole selectable asset is the owner's
    /// one-litre example, imported with a unique 2051 date by the Mac driver.
    func testLocalTrainedMetaLabelAndConfirmEditWithoutLogging() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard env["HYDRA_E2E_LOCAL_META"] == "1", let backend = env["HYDRA_E2E_BACKEND_URL"], let token = env["HYDRA_E2E_API_TOKEN"] else {
            throw XCTSkip("Requires explicitly selected local trained adapter and owned fixture")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Camera"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Camera"].tap()
        let header = app.staticTexts["recognitionHeader"]
        let trained = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS 'trained Meta model'"), object: header)
        XCTAssertEqual(XCTWaiter.wait(for: [trained], timeout: 15), .completed)
        app.buttons["chooseBeveragePhoto"].tap()
        let image = app.images.matching(NSPredicate(format: "label CONTAINS '2051'")).firstMatch
        let cell = app.cells.matching(NSPredicate(format: "label CONTAINS '2051'")).firstMatch
        if image.waitForExistence(timeout: 8) { image.tap() }
        else if cell.exists { cell.tap() }
        else {
            if app.buttons["Cancel"].exists { app.buttons["Cancel"].tap() }
            throw XCTSkip("Owned fixture date unavailable; no other asset selected")
        }
        let consent = app.switches["photoConsent"]
        XCTAssertTrue(consent.waitForExistence(timeout: 10))
        if !consent.isHittable { app.swipeUp() }
        XCTAssertFalse(app.switches["metaPhotoConsent"].exists)
        consent.switches.firstMatch.tap()
        let analyze = app.buttons["analyzePhoto"]
        if !analyze.isHittable { app.swipeUp() }
        XCTAssertTrue(analyze.isEnabled)
        analyze.tap()
        XCTAssertTrue(app.staticTexts["reviewDrinkName"].waitForExistence(timeout: 210))
        XCTAssertTrue(app.staticTexts["reviewDrinkName"].label.uppercased().contains("DASANI"))
        XCTAssertEqual(app.staticTexts["photoLabelCapacity"].label, "Printed size: 1000 mL")
        XCTAssertEqual(app.staticTexts["photoVolume"].label, "1000 mL")
        XCTAssertEqual(app.staticTexts["consumptionAssumptionSummary"].label, "Assuming a full container, all consumed.")
        XCTAssertTrue(app.buttons["savePhotoBeverage"].isEnabled)
        app.buttons["editRecognitionEntry"].tap()
        XCTAssertTrue(app.textFields["photoIdentity"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.textFields["photoConsumed"].exists)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Local trained Meta exact one-litre label and edit review"
        screenshot.lifetime = .keepAlways; add(screenshot)
        app.buttons["Cancel"].tap()
        XCTAssertTrue(app.staticTexts["recognitionResultSource"].waitForExistence(timeout: 5))
    }

    func testExplicitMetaConsentSourceAndConfirmedReceipt() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard env["HYDRA_E2E_LIVE_SIMULATION"] == "1", let backend = env["HYDRA_E2E_BACKEND_URL"], let token = env["HYDRA_E2E_API_TOKEN"] else {
            throw XCTSkip("Requires local fake-provider live-mode simulation")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token, "HYDRA_TEST_PHOTO_FIXTURE": "1"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap()
        XCTAssertTrue(app.buttons["saveConnection"].waitForExistence(timeout: 10));app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Camera"].tap()
        let header = app.staticTexts["recognitionHeader"]
        XCTAssertTrue(header.waitForExistence(timeout: 10))
        let liveHeader = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS 'live Meta analysis'"), object: header)
        XCTAssertEqual(XCTWaiter.wait(for: [liveHeader], timeout: 10), .completed)
        XCTAssertFalse(header.label.lowercased().contains("mock"))
        app.buttons["syntheticPhoto"].tap()
        XCTAssertTrue(app.buttons["exportPreparedPhoto"].waitForExistence(timeout: 10))
        let refresh = app.buttons["refreshRecognitionMode"]
        refresh.tap()
        let refreshed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: refresh)
        XCTAssertEqual(XCTWaiter.wait(for: [refreshed], timeout: 10), .completed)
        XCTAssertTrue(app.buttons["exportPreparedPhoto"].exists, "Refreshing mode must preserve the prepared image")
        XCTAssertEqual(app.switches["photoConsent"].value as? String, "0")
        XCTAssertEqual(app.switches["metaPhotoConsent"].value as? String, "0")
        let analyze = app.buttons["analyzePhoto"]
        XCTAssertTrue(analyze.waitForExistence(timeout: 10));XCTAssertFalse(analyze.isEnabled)
        app.swipeUp()
        let backendConsent = app.switches["photoConsent"]
        backendConsent.tap()
        if backendConsent.value as? String != "1" {
            backendConsent.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        }
        XCTAssertEqual(backendConsent.value as? String, "1")
        XCTAssertFalse(analyze.isEnabled)
        let metaConsent = app.switches["metaPhotoConsent"]
        if !metaConsent.isHittable { app.swipeUp() }
        metaConsent.tap()
        if metaConsent.value as? String != "1" {
            metaConsent.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        }
        XCTAssertEqual(metaConsent.value as? String, "1")
        // Refresh after granting both consents, not only while they are already off.
        app.swipeDown()
        refresh.tap()
        let consentReset = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: refresh)
        XCTAssertEqual(XCTWaiter.wait(for: [consentReset], timeout: 10), .completed)
        XCTAssertTrue(app.buttons["exportPreparedPhoto"].exists)
        XCTAssertEqual(backendConsent.value as? String, "0")
        XCTAssertEqual(metaConsent.value as? String, "0")
        XCTAssertFalse(analyze.isEnabled)
        app.swipeUp()
        backendConsent.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        metaConsent.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        XCTAssertEqual(backendConsent.value as? String, "1")
        XCTAssertEqual(metaConsent.value as? String, "1")
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: analyze)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 5), .completed)
        XCTAssertEqual(analyze.label, "Analyze with live Meta")
        XCTAssertTrue(app.staticTexts["recognitionSource"].label.hasPrefix("Live Meta analysis"))
        analyze.tap()
        XCTAssertTrue(app.staticTexts["photoVolume"].waitForExistence(timeout: 15))
        app.buttons["Cancel"].tap()
        let reviews = app.buttons.matching(NSPredicate(format: "label == %@", "Confirm tea (low confidence)"))
        XCTAssertTrue(reviews.element(boundBy: 1).waitForExistence(timeout: 20))
        XCTAssertEqual(reviews.count, 2)
        XCTAssertEqual(app.staticTexts["recognitionResultSource"].label, "Live Meta result — confirmation required")
        let firstID = reviews.element(boundBy: 0).identifier
        let secondID = reviews.element(boundBy: 1).identifier
        XCTAssertTrue(firstID.hasPrefix("recognitionCandidate-"))
        XCTAssertNotEqual(firstID, secondID)
        reviews.element(boundBy: 0).tap()
        XCTAssertTrue(app.staticTexts["photoVolume"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["photoVolume"].label, "Volume unclear")
        app.buttons["Cancel"].tap()
        XCTAssertTrue(app.buttons[firstID].waitForExistence(timeout: 10))
        XCTAssertEqual(reviews.element(boundBy: 1).identifier, secondID)
        app.buttons[secondID].tap()
        XCTAssertTrue(app.staticTexts["photoVolume"].waitForExistence(timeout: 10))
        app.buttons["editRecognitionEntry"].tap()
        let details = app.buttons["Photo details"]
        if !details.isHittable { app.swipeUp() }
        details.tap()
        XCTAssertTrue(app.staticTexts["photoCapacity"].label.contains("450 mL"))
        app.swipeDown()
        let partial = app.switches["assumeEntireLiquid"]
        if !partial.isHittable { app.swipeUp() }
        partial.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        let consumed = app.textFields["photoConsumed"]
        consumed.tap();consumed.typeText("125");app.buttons["photoKeyboardDone"].tap()
        app.buttons["savePhotoBeverage"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 15))
        app.buttons["syntheticPhoto"].tap()
        XCTAssertTrue(app.buttons["exportPreparedPhoto"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.switches["photoConsent"].value as? String, "0")
        XCTAssertEqual(app.switches["metaPhotoConsent"].value as? String, "0")
        XCTAssertFalse(app.buttons["analyzePhoto"].isEnabled)
        XCTAssertFalse(app.staticTexts["recognitionResultSource"].exists)
        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        let check = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '125'"), object: total)
        XCTAssertEqual(XCTWaiter.wait(for: [check], timeout: 20), .completed)
    }
}
