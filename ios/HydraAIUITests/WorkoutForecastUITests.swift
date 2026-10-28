import XCTest

/// A loopback backend with only synthetic test data is required; no live AI.
final class WorkoutForecastUITests: XCTestCase {
    func testSyntheticPredictionIsSeparateFromConsumedVolume() throws {
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
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout: 15))
        let initial = total.value as? String
        let forecast = app.buttons["workoutForecast"]
        if !forecast.isHittable { app.swipeUp() }
        XCTAssertTrue(forecast.waitForExistence(timeout: 10)); forecast.tap()
        let demo = app.buttons["runWorkoutDemo"]
        XCTAssertTrue(demo.waitForExistence(timeout: 10)); XCTAssertTrue(demo.isEnabled); demo.tap()
        let prediction = app.staticTexts["workoutPrediction"]
        XCTAssertTrue(prediction.waitForExistence(timeout: 15))
        XCTAssertTrue(prediction.label.contains("sweat loss"))
        XCTAssertTrue(app.staticTexts["SIMULATED · not your measurements"].exists)
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Synthetic workout forecast separated from consumption"; attachment.lifetime = .keepAlways
        add(attachment)
        app.navigationBars.buttons.firstMatch.tap()
        if !total.isHittable { app.swipeDown() }
        XCTAssertTrue(total.waitForExistence(timeout: 10))
        XCTAssertEqual(total.value as? String, initial, "A prediction must never increase confirmed consumption")
        XCTAssertTrue(app.buttons["logBeverage"].exists)
    }
}
