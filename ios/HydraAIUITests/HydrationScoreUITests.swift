import XCTest

/// Requires a disposable local backend with the documented synthetic Home fixture.
final class HydrationScoreUITests: XCTestCase {
    func testHomeScoreWhyPreviewAndGoalChangeWithoutMetaDispatch() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard env["HYDRA_E2E_HOME_SCORE"] == "1", let backend = env["HYDRA_E2E_BACKEND_URL"],
              let token = env["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires disposable synthetic Home score backend")
        }
        let app = XCUIApplication(); app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token]
        app.launchHydra(); addTeardownBlock { app.terminate() }
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Today"].tap()
        let anyScore = app.descendants(matching: .any).matching(identifier: "hydrationScoreValue").firstMatch
        XCTAssertTrue(anyScore.waitForExistence(timeout: 15))
        XCTAssertEqual(anyScore.value as? String, "38 out of 100")
        attach(app, "Experimental combined Home score on invented test records")
        let why = app.buttons["whyHydrationScore"]; reveal(why, in: app); why.tap()
        XCTAssertTrue(app.staticTexts["hydrationScoreFormula"].waitForExistence(timeout: 5))
        let processing = app.switches["scoreProcessingConsent"]; reveal(processing, in: app)
        XCTAssertEqual(processing.value as? String, "0")
        let prepare = app.buttons["previewScoreWonder"]; XCTAssertFalse(prepare.isEnabled)
        processing.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap(); prepare.tap()
        let exact = app.buttons["scoreWonderExactFacts"]
        XCTAssertTrue(exact.waitForExistence(timeout: 15))
        let unavailable = app.staticTexts["scoreWonderUnavailable"]; reveal(unavailable, in: app)
        XCTAssertTrue(unavailable.label.contains("currently unavailable"))
        XCTAssertFalse(app.buttons["explainHydrationScore"].exists); XCTAssertFalse(app.switches["scoreMetaConsent"].exists)
        attach(app, "Exact score preview keeps live Meta action unavailable")
        app.tabBars.buttons["Settings"].tap()
        let goal = app.textFields["goalField"]; reveal(goal, in: app); goal.tap()
        if let value = goal.value as? String { goal.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: value.count)) }
        goal.typeText("2000")
        if app.buttons["Done"].exists { app.buttons["Done"].tap() }
        let save = app.buttons["saveGoal"]; reveal(save, in: app); save.tap()
        app.tabBars.buttons["Today"].tap()
        if app.navigationBars.buttons["Today"].exists { app.navigationBars.buttons["Today"].tap() }
        for _ in 0..<12 where !why.isHittable { app.swipeDown() }
        XCTAssertTrue(anyScore.waitForExistence(timeout: 15))
        expectation(for: NSPredicate(format: "value == %@", "34 out of 100"), evaluatedWith: anyScore)
        waitForExpectations(timeout: 15)
        why.tap()
        reveal(processing, in: app)
        XCTAssertEqual(processing.value as? String, "0")
        XCTAssertFalse(prepare.isEnabled)
        XCTAssertFalse(app.buttons["scoreWonderExactFacts"].exists)
    }
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<16 where !element.isHittable { app.swipeUp() }
        XCTAssertTrue(element.isHittable)
    }
    private func attach(_ app: XCUIApplication, _ name: String) {
        let item = XCTAttachment(screenshot: app.screenshot()); item.name = name; item.lifetime = .keepAlways; add(item)
    }
}
