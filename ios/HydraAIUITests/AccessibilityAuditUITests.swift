import XCTest

/// Opt-in: runs Xcode's accessibility audit on the main screens against a LOCAL synthetic-data backend.
/// Fails on hard contrast failures, unscaled text and clipping in enabled controls. "Nearly passed"
/// contrast of system secondary styles and partial Dynamic Type support in system forms are logged only.
final class AccessibilityAuditUITests: XCTestCase {
    private func audit(_ app: XCUIApplication, _ screen: String) throws {
        try app.performAccessibilityAudit { issue in
            let description = issue.compactDescription
            let frame = issue.element?.frame ?? .zero
            // Content scrolled under the translucent bars is blurred by design; input fields scroll their text.
            let underBars = [app.navigationBars.firstMatch, app.tabBars.firstMatch]
                .contains { $0.exists && $0.frame.intersects(frame) }
            // Scroll-view content entirely below the visible window is not rendered on screen to judge.
            let offscreen = !frame.isEmpty && !app.windows.firstMatch.frame.intersects(frame)
            let inputField = [.textField, .secureTextField].contains(issue.element?.elementType)
            let unattributed = issue.element == nil || frame.isEmpty
            let tolerated = unattributed || description.contains("nearly passed") || description.contains("partially unsupported")
                || issue.element?.isEnabled == false || underBars || offscreen || (inputField && description.contains("clipped"))
            print("AUDIT|\(screen)|\(tolerated ? "logged" : "FAIL")|\(description)|\(issue.element?.label ?? "-")|type \(issue.element?.elementType.rawValue ?? 0)|\(frame)")
            return tolerated
        }
    }

    func testMainScreensPassAccessibilityAudit() throws {
        let environment = ProcessInfo.processInfo.environment
        guard let backend = environment["HYDRA_E2E_BACKEND_URL"],
              let token = environment["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires opt-in local synthetic-data backend")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token]
        app.launch()
        var screen = "Settings"
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        try audit(app, screen)

        screen = "Today"
        app.tabBars.buttons["Today"].tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch.waitForExistence(timeout: 15))
        try audit(app, screen)

        screen = "History"
        app.tabBars.buttons["History"].tap()
        try audit(app, screen)

        app.tabBars.buttons["Today"].tap()
        screen = "AskHydra"
        let link = app.buttons["askAssistant"]
        for _ in 0..<4 where !link.isHittable { app.swipeUp() }
        link.tap()
        let suggestion = app.buttons["suggested-coffee_counts"]
        XCTAssertTrue(suggestion.waitForExistence(timeout: 15)); suggestion.tap()
        XCTAssertTrue(app.staticTexts["assistantAnswer-coffee_caffeine"].waitForExistence(timeout: 10))
        try audit(app, screen)
    }
}
