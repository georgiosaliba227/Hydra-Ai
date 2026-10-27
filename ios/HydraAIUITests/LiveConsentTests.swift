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
        XCTAssertTrue(app.buttons["saveConnection"].waitForExistence(timeout: 10));app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Camera"].tap();app.buttons["syntheticPhoto"].tap()
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
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: analyze)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 5), .completed)
        analyze.tap()
        let review = app.buttons["Review tea (low confidence)"]
        XCTAssertTrue(review.waitForExistence(timeout: 20));review.tap()
        XCTAssertTrue(app.staticTexts["Meta suggestion — verify every field"].waitForExistence(timeout: 10))
        let consumed = app.textFields["photoConsumed"]
        consumed.tap();consumed.typeText("125");app.buttons["photoKeyboardDone"].tap()
        app.switches["confirmPhotoDetails"].coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        app.buttons["savePhotoBeverage"].tap()
        XCTAssertTrue(app.buttons["syntheticPhoto"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        let check = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '125'"), object: total)
        XCTAssertEqual(XCTWaiter.wait(for: [check], timeout: 20), .completed)
    }
}
