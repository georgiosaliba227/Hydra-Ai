import XCTest

/// Opt-in: asks the local-rules assistant on a LOCAL synthetic-data backend. No AI calls.
final class AssistantUITests: XCTestCase {
    func testSuggestedAndUrgentQuestionsShowReviewedAnswers() throws {
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
        app.tabBars.buttons["Today"].tap()
        let link = app.buttons["askAssistant"]
        for _ in 0..<4 where !link.isHittable { app.swipeUp() }
        XCTAssertTrue(link.waitForExistence(timeout: 10)); link.tap()

        let suggestion = app.buttons["suggested-creatine_water"]
        XCTAssertTrue(suggestion.waitForExistence(timeout: 15)); suggestion.tap()
        let creatine = app.staticTexts["assistantAnswer-creatine"]
        for _ in 0..<4 where !creatine.waitForExistence(timeout: 3) { app.swipeUp() }
        XCTAssertTrue(creatine.label.contains("creatine"))
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Reviewed creatine answer with evidence"; attachment.lifetime = .keepAlways
        add(attachment)

        for _ in 0..<4 where !app.textFields["assistantQuestion"].isHittable { app.swipeDown() }
        let field = app.textFields["assistantQuestion"]
        XCTAssertTrue(field.waitForExistence(timeout: 5)); field.tap(); field.typeText("I fainted after my run")
        app.buttons["assistantAsk"].tap()
        let urgent = app.staticTexts["assistantAnswer-urgent"]
        for _ in 0..<4 where !urgent.waitForExistence(timeout: 3) { app.swipeUp() }
        XCTAssertTrue(urgent.label.contains("urgent medical care"))
    }
}
