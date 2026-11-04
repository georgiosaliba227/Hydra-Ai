import XCTest

/// Run only on a fresh disposable simulator and a loopback synthetic backend.
final class DeviceInsightsEndToEndTests: XCTestCase {
    func testPhoneLogFeedsTrendsAndAssistantWhileWorkoutStaysSeparate() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard let backend = env["HYDRA_E2E_DEVICE_INSIGHTS_URL"],
              let token = env["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires opt-in synthetic device-insights fixture")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_SKIP_GOAL_SETUP": "1", "HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token, "HYDRA_TEST_ON_DEVICE": "1"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap()
        let optional = app.switches["backendInsightsMode"]
        XCTAssertTrue(optional.waitForExistence(timeout: 10))
        XCTAssertEqual(optional.value as? String, "0", "A new install must not opt in automatically")
        optional.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '1'"), object: optional)], timeout: 5), .completed)
        let save = app.buttons["saveConnection"]
        for _ in 0..<4 where !save.isHittable { app.swipeUp() }
        save.tap()
        let connectionScreen = XCTAttachment(screenshot: app.screenshot())
        connectionScreen.name = "Optional backend connection after save"
        connectionScreen.lifetime = .keepAlways
        add(connectionScreen)
        let check = app.buttons["checkBackendInsights"]
        for _ in 0..<4 where !check.isHittable { app.swipeUp() }
        XCTAssertTrue(check.waitForExistence(timeout: 5)); check.tap()
        let status = app.staticTexts["backendInsightsStatus"]
        XCTAssertTrue(status.waitForExistence(timeout: 15))
        XCTAssertTrue(status.label.contains("No drink data was sent"))

        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout: 15))
        XCTAssertEqual(total.value as? String, "0", "Use a fresh disposable simulator")
        app.buttons["quickAdd-water-500"].tap()
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '500'"), object: total)], timeout: 15), .completed)

        app.tabBars.buttons["Insights"].tap(); app.buttons["insightsTrends"].tap()
        let preview = app.staticTexts["deviceTrendsPreviewTotal"]
        XCTAssertTrue(preview.waitForExistence(timeout: 15)); XCTAssertTrue(preview.label.contains("500 mL"))
        XCTAssertFalse(app.staticTexts["trendsSummary"].exists, "Opening preview must not send it")
        let send = app.buttons["sendDeviceTrends"]
        for _ in 0..<5 where !send.isHittable { app.swipeUp() }
        XCTAssertTrue(send.isEnabled); send.tap()
        let summary = app.staticTexts["trendsSummary"]
        XCTAssertTrue(summary.waitForExistence(timeout: 20)); XCTAssertTrue(summary.label.contains("500 mL"))
        let trends = XCTAttachment(screenshot: app.screenshot()); trends.name = "Phone summary trends"; trends.lifetime = .keepAlways; add(trends)
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.buttons["insightsAsk"].tap()
        let options = app.buttons["assistantOptions"]
        XCTAssertTrue(options.waitForExistence(timeout: 10)); options.tap()
        let include = app.switches["assistantIncludeToday"]
        for _ in 0..<5 where !include.isHittable { app.swipeUp() }
        include.tap()
        let suggestion = app.buttons["suggested-coffee_counts"]
        for _ in 0..<5 where !suggestion.isHittable { app.swipeUp() }
        XCTAssertTrue(suggestion.waitForExistence(timeout: 15)); suggestion.tap()
        let context = app.staticTexts["assistantIntakeContext"]
        for _ in 0..<5 where !context.waitForExistence(timeout: 3) { app.swipeUp() }
        XCTAssertTrue(context.label.contains("500 mL"))
        let assistant = XCTAttachment(screenshot: app.screenshot()); assistant.name = "Phone total in Ask Hydra"; assistant.lifetime = .keepAlways; add(assistant)
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.buttons["insightsWorkout"].tap(); app.buttons["openWorkoutDemo"].tap()
        let run = app.buttons["runWorkoutDemo"]
        XCTAssertTrue(run.waitForExistence(timeout: 10)); XCTAssertTrue(run.isEnabled); run.tap()
        XCTAssertTrue(app.staticTexts["workoutPrediction"].waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["SIMULATED · not your measurements"].exists)
        app.buttons["closeWorkoutDemo"].tap()
        app.tabBars.buttons["Today"].tap()
        XCTAssertEqual(total.value as? String, "500", "An estimate must not change confirmed volume")
        app.terminate(); app.launch()
        XCTAssertTrue(total.waitForExistence(timeout: 15)); XCTAssertEqual(total.value as? String, "500")
    }
}
