import XCTest

/// Opt-in: sets a user goal against a LOCAL synthetic-data backend and checks Today's progress.
final class GoalUITests: XCTestCase {
    func testOfflineDrinkLoggingFillsGoalAndSurvivesRelaunch() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap()
        let offline = app.switches["offlineMode"]
        // SwiftUI exposes the entire row as the switch; tap the trailing control.
        if offline.value as? String != "1" {
            offline.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5)).tap()
        }
        XCTAssertEqual(offline.value as? String, "1")
        app.buttons["saveConnection"].tap()
        XCTAssertTrue(app.staticTexts["Offline demo"].waitForExistence(timeout: 5))
        let clear = app.buttons["Clear goal"]
        for _ in 0..<3 where !clear.isHittable { app.swipeUp() }
        XCTAssertTrue(clear.waitForExistence(timeout: 5), "Offline mode must support a user-chosen goal")
        clear.tap()
        app.tabBars.buttons["Today"].tap()
        let setup = app.buttons["setDailyGoal"]
        XCTAssertTrue(setup.waitForExistence(timeout: 10))
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout: 10))
        let initial = try XCTUnwrap(Int(total.value as? String ?? ""))
        setup.tap()
        let field = app.textFields["goalField"]
        for _ in 0..<3 where !field.isHittable { app.swipeUp() }
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 6) + "1000")
        if app.toolbars.buttons["Done"].exists { app.toolbars.buttons["Done"].tap() }
        app.buttons["saveGoal"].tap()
        XCTAssertTrue(app.staticTexts["goalMessage"].waitForExistence(timeout: 10))
        app.navigationBars.buttons["Today"].tap()

        let progress = app.descendants(matching: .any).matching(identifier: "goalProgress").firstMatch
        XCTAssertTrue(progress.waitForExistence(timeout: 10))
        func expectTotal(_ value: Int) {
            let expectation = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", String(value)), object: total)
            XCTAssertEqual(XCTWaiter.wait(for: [expectation], timeout: 10), .completed)
        }
        app.buttons["quickAdd-water-250"].tap()
        expectTotal(initial + 250)
        if initial == 0 { XCTAssertTrue(progress.label.contains("25%"), progress.label) }
        app.buttons["quickAdd-water-500"].tap()
        expectTotal(initial + 750)
        if initial == 0 { XCTAssertTrue(progress.label.contains("75%"), progress.label) }
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Home hydration progress after logging drinks"
        attachment.lifetime = .keepAlways
        add(attachment)

        app.terminate(); app.launch()
        expectTotal(initial + 750)
        XCTAssertTrue(progress.waitForExistence(timeout: 10))
        XCTAssertTrue(progress.label.contains("1,000"), progress.label)
    }

    func testUserGoalShowsProgressOnToday() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        guard let backend = environment["HYDRA_E2E_BACKEND_URL"],
              let token = environment["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires opt-in local synthetic-data backend")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        let field = app.textFields["goalField"]
        for _ in 0..<3 where !field.waitForExistence(timeout: 3) { app.swipeUp() }
        field.tap(); field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 6) + "1500")
        let done = app.toolbars.buttons["Done"]
        if done.waitForExistence(timeout: 3) { done.tap() }
        let save = app.buttons["saveGoal"]
        for _ in 0..<3 where !save.isHittable { app.swipeUp() }
        save.tap()
        XCTAssertTrue(app.staticTexts["goalMessage"].waitForExistence(timeout: 10))
        app.tabBars.buttons["Today"].tap()
        let progress = app.descendants(matching: .any).matching(identifier: "goalProgress").firstMatch
        XCTAssertTrue(progress.waitForExistence(timeout: 15))
        XCTAssertTrue(progress.label.contains("your own goal"), progress.label)
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "User-chosen goal progress on Today"; attachment.lifetime = .keepAlways
        add(attachment)
    }
}
