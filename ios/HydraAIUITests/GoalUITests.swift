import XCTest

/// Opt-in: sets a user goal against a LOCAL synthetic-data backend and checks Today's progress.
final class GoalUITests: XCTestCase {
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
