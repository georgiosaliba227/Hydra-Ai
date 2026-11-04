import XCTest

/// A loopback backend with only synthetic test data is required; no live AI.
final class WorkoutForecastUITests: XCTestCase {
    func testUnavailableDemoDoesNotAskForPersonalMeasurements() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        guard let backend = environment["HYDRA_E2E_REVIEW_BACKEND_URL"],
              let token = environment["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires the nonbillable review fixture with --unavailable-demo")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_SKIP_GOAL_SETUP": "1", "HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Insights"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Insights"].tap(); app.buttons["insightsWorkout"].tap()
        app.buttons["openWorkoutDemo"].tap(); app.buttons["runWorkoutDemo"].tap()
        let unavailable = app.staticTexts["workoutInsufficientData"]
        XCTAssertTrue(unavailable.waitForExistence(timeout: 15))
        XCTAssertEqual(unavailable.label, "Demo unavailable")
        XCTAssertFalse(app.staticTexts["There isn't enough comparable data for a personal estimate yet."].exists)
        XCTAssertTrue(app.staticTexts["SIMULATED · not your measurements"].exists)
    }

    func testSyntheticPredictionIsSeparateFromConsumedVolume() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        guard let backend = environment["HYDRA_E2E_BACKEND_URL"],
              let token = environment["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires opt-in local synthetic-data backend")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_SKIP_GOAL_SETUP": "1", "HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout: 15))
        let initial = total.value as? String
        app.tabBars.buttons["Insights"].tap()
        let forecast = app.buttons["insightsWorkout"]
        if !forecast.isHittable { app.swipeUp() }
        XCTAssertTrue(forecast.waitForExistence(timeout: 10)); forecast.tap()
        app.buttons["openWorkoutDemo"].tap()
        let demo = app.buttons["runWorkoutDemo"]
        XCTAssertTrue(demo.waitForExistence(timeout: 10)); XCTAssertTrue(demo.isEnabled); demo.tap()
        let prediction = app.staticTexts["workoutPrediction"]
        XCTAssertTrue(prediction.waitForExistence(timeout: 15))
        XCTAssertTrue(prediction.label.contains("sweat loss"))
        XCTAssertTrue(app.staticTexts["SIMULATED · not your measurements"].exists)
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Synthetic workout forecast separated from consumption"; attachment.lifetime = .keepAlways
        add(attachment)
        let research = app.buttons["workoutResearchDetails"]
        for _ in 0..<5 where !research.isHittable { app.swipeUp() }
        research.tap()
        let comparison = app.buttons["contextComparison"]
        for _ in 0..<6 {
            if comparison.isHittable { break }
            app.swipeUp()
        }
        XCTAssertTrue(comparison.waitForExistence(timeout: 10)); comparison.tap()
        // List rows below the fold are created lazily; scroll until each appears.
        for label in ["A · Existing numerical estimate", "B · Contextual mock; no numerical prediction",
                      "C · Same estimate plus contextual mock"] {
            let row = app.staticTexts[label]
            for _ in 0..<4 where !row.waitForExistence(timeout: 2) { app.swipeUp() }
            XCTAssertTrue(row.exists, label)
        }
        let contextAttachment = XCTAttachment(screenshot: app.screenshot())
        contextAttachment.name = "A B C contextual comparison with explicit mock provenance"; contextAttachment.lifetime = .keepAlways
        add(contextAttachment)
        app.buttons["closeWorkoutDemo"].tap()
        app.tabBars.buttons["Today"].tap()
        if !total.isHittable { app.swipeDown() }
        XCTAssertTrue(total.waitForExistence(timeout: 10))
        XCTAssertEqual(total.value as? String, initial, "A prediction must never increase confirmed consumption")
        XCTAssertTrue(app.buttons["logBeverage"].exists)
    }
}
