import XCTest

/// Only the dedicated local fake-provider server may enable this case.
final class LiveConsentTests: XCTestCase {
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
        XCTAssertTrue(app.buttons["saveConnection"].waitForExistence(timeout: 10)); app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout: 15))
        let dashboard = XCTAttachment(screenshot: app.screenshot()); dashboard.name = "Hydra Today"; dashboard.lifetime = .keepAlways; add(dashboard)
        app.tabBars.buttons["Camera"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 10))
        let camera = XCTAttachment(screenshot: app.screenshot()); camera.name = "Hydra Camera"; camera.lifetime = .keepAlways; add(camera)
        app.buttons["syntheticPhoto"].tap()
        let scan = app.buttons["analyzePhoto"]
        XCTAssertTrue(scan.waitForExistence(timeout: 10))
        XCTAssertEqual(scan.label, "Scan photo")
        XCTAssertTrue(app.staticTexts["scanSharingDisclosure"].label.contains("Meta"))
        XCTAssertTrue(app.staticTexts["scanSharingDisclosure"].label.contains("retain"))
        // Canceling must leave the picture on device, with no result or logging.
        app.buttons["cancelPhotoScan"].tap()
        XCTAssertFalse(app.staticTexts["recognitionResultSource"].exists)
        XCTAssertTrue(app.images["Selected beverage photo"].exists)
        app.buttons["cameraOptions"].tap()
        XCTAssertTrue(app.buttons["exportPreparedPhoto"].waitForExistence(timeout: 10))
        let refresh = app.buttons["refreshRecognitionMode"]
        refresh.tap()
        let refreshed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: refresh)
        XCTAssertEqual(XCTWaiter.wait(for: [refreshed], timeout: 10), .completed)
        XCTAssertTrue(app.buttons["exportPreparedPhoto"].exists, "Refresh preserves the exact approval image")
        app.buttons["Done"].tap()
        app.buttons["reviewPhotoSharing"].tap()
        XCTAssertTrue(scan.waitForExistence(timeout: 10))
        scan.tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "scanInProgress").firstMatch.waitForExistence(timeout: 5))
        let scanner = XCTAttachment(screenshot: app.screenshot()); scanner.name = "Hydra Scanning"; scanner.lifetime = .keepAlways; add(scanner)
        let reviews = app.buttons.matching(NSPredicate(format: "label == %@", "Review tea (low confidence)"))
        XCTAssertTrue(reviews.element(boundBy: 0).waitForExistence(timeout: 20))
        XCTAssertEqual(reviews.count, 2)
        XCTAssertEqual(app.staticTexts["recognitionResultSource"].label, "Here’s what we found")
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@ OR value CONTAINS %@", "300 mL", "300 mL")).firstMatch.exists, "Results display capacity before opening confirmation")
        let results = XCTAttachment(screenshot: app.screenshot()); results.name = "Hydra Scan Results"; results.lifetime = .keepAlways; add(results)
        let firstID = reviews.element(boundBy: 0).identifier
        let secondID = reviews.element(boundBy: 1).identifier
        XCTAssertTrue(firstID.hasPrefix("recognitionCandidate-")); XCTAssertNotEqual(firstID, secondID)
        if !app.buttons[firstID].isHittable { app.swipeUp() }
        app.buttons[firstID].tap()
        XCTAssertTrue(app.textFields["photoContainer"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.textFields["photoContainer"].value as? String, "300")
        app.buttons["Cancel"].tap()
        XCTAssertTrue(app.buttons[firstID].waitForExistence(timeout: 10))
        XCTAssertEqual(reviews.element(boundBy: 1).identifier, secondID)
        for _ in 0..<4 where !app.buttons[secondID].isHittable { app.swipeUp() }
        app.buttons[secondID].tap()
        XCTAssertTrue(app.textFields["photoContainer"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.textFields["photoContainer"].value as? String, "450")
        let consumed = app.textFields["photoConsumed"]
        consumed.tap(); consumed.typeText("125"); app.buttons["photoKeyboardDone"].tap()
        app.switches["confirmPhotoDetails"].coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        app.buttons["savePhotoBeverage"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 15))
        app.buttons["syntheticPhoto"].tap()
        XCTAssertTrue(scan.waitForExistence(timeout: 10), "Each new photo requires explicit consent")
        app.buttons["cancelPhotoScan"].tap()
        XCTAssertFalse(app.staticTexts["recognitionResultSource"].exists)
        app.tabBars.buttons["Today"].tap()
        let check = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '125'"), object: total)
        XCTAssertEqual(XCTWaiter.wait(for: [check], timeout: 20), .completed)
    }
}
