import XCTest

/// No Health/location access is enabled and no Meta action is invoked by these checks.
final class DailyContextSetupUITests: XCTestCase {
    func testOptedInSampleHealthPrefillsWithoutManualImportAfterRelaunch() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = [
            "HYDRA_TEST_CONTEXT_SUITE": "HydraUITests.Context.\(UUID().uuidString)",
            "HYDRA_TEST_UNIT_SYSTEM": "us", "HYDRA_SAMPLE_HEALTH_WORKOUTS": "1",
            "HYDRA_TEST_BACKEND_URL": "http://127.0.0.1:19998",
            "HYDRA_TEST_API_TOKEN": String(repeating: "x", count: 32)
        ]
        app.launch(); addTeardownBlock { app.terminate() }
        let connect = app.buttons["connectAutomaticHealth"]
        XCTAssertTrue(connect.waitForExistence(timeout: 8)); reveal(connect, app: app); connect.tap()
        let finish = app.buttons["finishContextSetup"]
        reveal(finish, app: app)
        XCTAssertTrue(finish.waitForExistence(timeout: 5)); finish.tap()
        app.terminate(); app.launch()
        XCTAssertTrue(app.tabBars.buttons["Insights"].waitForExistence(timeout: 8))
        XCTAssertFalse(app.staticTexts["contextSetupTitle"].exists)
        app.tabBars.buttons["Insights"].tap()
        let plan = app.buttons["insightsWorkout"]; reveal(plan, app: app); plan.tap()
        let provenance = app.staticTexts["workoutProvenance"]
        XCTAssertTrue(provenance.waitForExistence(timeout: 10))
        XCTAssertTrue(provenance.label.hasPrefix("Sample workout (not your data) on "))
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Automatic Apple Health prefill using labeled sample data after relaunch"
        screenshot.lifetime = .keepAlways; add(screenshot)
    }

    func testFirstUseSetupCanBeSkippedAndDoesNotRepeat() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = [
            "HYDRA_TEST_CONTEXT_SUITE": "HydraUITests.Context.\(UUID().uuidString)",
            "HYDRA_TEST_UNIT_SYSTEM": "us",
            "HYDRA_TEST_BACKEND_URL": "http://127.0.0.1:19998",
            "HYDRA_TEST_API_TOKEN": String(repeating: "x", count: 32)
        ]
        app.launch()
        addTeardownBlock { app.terminate() }
        XCTAssertTrue(app.staticTexts["contextSetupTitle"].waitForExistence(timeout: 8))
        reveal(app.buttons["connectAutomaticHealth"], app: app)
        let disclosure = app.staticTexts["automaticWeatherDisclosure"]
        reveal(disclosure, app: app)
        XCTAssertTrue(disclosure.label.contains("rounded"))
        reveal(app.buttons["enableAutomaticWeather"], app: app)
        let finish = app.buttons["finishContextSetup"]
        reveal(finish, app: app); finish.tap()
        XCTAssertTrue(app.tabBars.buttons["Insights"].waitForExistence(timeout: 5))
        app.terminate()
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Insights"].waitForExistence(timeout: 8))
        XCTAssertFalse(app.staticTexts["contextSetupTitle"].exists)
        app.tabBars.buttons["Insights"].tap()
        let plan = app.buttons["insightsWorkout"]
        reveal(plan, app: app); plan.tap()
        let temperature = app.textFields["Temperature"]
        reveal(temperature, app: app)
        XCTAssertTrue(temperature.exists)
        XCTAssertTrue(temperature.label.contains("Fahrenheit"))
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "US units after optional setup; no Health or weather enabled"
        screenshot.lifetime = .keepAlways; add(screenshot)
    }

    private func reveal(_ element: XCUIElement, app: XCUIApplication) {
        for _ in 0..<12 where !element.isHittable { app.swipeUp() }
        XCTAssertTrue(element.isHittable)
    }
}
