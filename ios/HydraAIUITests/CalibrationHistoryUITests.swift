import XCTest

/// No live provider or external service: storage and relaunch use manually typed synthetic values.
final class CalibrationHistoryUITests: XCTestCase {
    func testExplicitSaveRestoresManualHistoryAfterRelaunchWithFreshConsentAndSelectiveDeletion() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": "http://127.0.0.1:19998",
                                 "HYDRA_TEST_API_TOKEN": "synthetic-calibration-ui-token-not-a-secret"]
        app.launchHydra()
        openForecast(app)
        let deleteAll = app.buttons["deleteAllCalibrationHistory"]
        reveal(deleteAll, app)
        deleteAll.tap()
        app.buttons.matching(NSPredicate(format: "label == %@", "Delete all saved manual measurements")).allElementsBoundByIndex.first(where: { $0.isHittable })!.tap()
        top(app)
        type("22", field: "Temperature", app); done(app)
        type("55", field: "Humidity, %", app)
        done(app)
        let addGroup = app.buttons["Add a measured workout"]
        reveal(addGroup, app); addGroup.tap()
        for (field, value) in [("Weight before", "70"), ("Weight after", "69.6"),
                               ("Drank during", "200"), ("Urine during", "10"),
                               ("Measured duration, min", "45"), ("Each weighing ±", "0.05"),
                               ("Amount drunk ±", "10"), ("Urine ±", "1"), ("Duration ±, min", "1")] {
            type(value, field: field, app); done(app)
        }
        let protocolConsent = app.switches["calibrationProtocolConfirmed"]
        reveal(protocolConsent, app)
        protocolConsent.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        XCTAssertEqual(protocolConsent.value as? String, "1")
        let add = app.buttons["addCalibrationMeasurement"]
        reveal(add, app); add.tap()
        let sessionCount = app.descendants(matching: .any).matching(identifier: "sessionCalibrationCount").firstMatch
        top(app); reveal(sessionCount, app)
        XCTAssertEqual(sessionCount.value as? String, "1")
        let saveConsent = app.switches["saveCalibrationConsent"]
        reveal(saveConsent, app)
        XCTAssertEqual(saveConsent.value as? String, "0")
        let save = app.buttons["saveCalibrationHistory"]
        XCTAssertFalse(save.isEnabled)
        saveConsent.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        XCTAssertEqual(saveConsent.value as? String, "1")
        XCTAssertTrue(save.isEnabled); save.tap()
        reveal(app.staticTexts["calibrationHistoryMessage"], app)
        XCTAssertTrue(app.staticTexts["calibrationHistoryMessage"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["calibrationHistoryMessage"].label.contains("saved on this iPhone"), app.staticTexts["calibrationHistoryMessage"].label)
        attach(app, "Explicit local manual calibration save")

        app.terminate(); app.launchHydra()
        openForecast(app)
        let savedCount = app.descendants(matching: .any).matching(identifier: "savedCalibrationCount").firstMatch
        reveal(savedCount, app)
        XCTAssertEqual(savedCount.value as? String, "1")
        XCTAssertEqual(app.switches["saveCalibrationConsent"].value as? String, "0")
        let load = app.buttons["useSavedCalibration"]
        reveal(load, app); load.tap()
        top(app)
        let backendConsent = app.switches["workoutCalibrationConsent"]
        reveal(backendConsent, app)
        XCTAssertEqual(backendConsent.value as? String, "0")
        XCTAssertFalse(app.staticTexts["workoutWonderSummary"].exists)
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "savedCalibration-")).firstMatch
        reveal(row, app); row.tap()
        let delete = app.buttons["Delete saved measurement"]
        reveal(delete, app); delete.tap()
        top(app); reveal(savedCount, app)
        XCTAssertEqual(savedCount.value as? String, "0")
        attach(app, "Restored manual history deleted with no restored consent")
        app.terminate(); app.launchHydra(); openForecast(app); reveal(savedCount, app)
        XCTAssertEqual(savedCount.value as? String, "0")
    }
    private func openForecast(_ app: XCUIApplication) {
        XCTAssertTrue(app.tabBars.buttons["Insights"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Insights"].tap()
        let forecast = app.buttons["insightsWorkout"]
        reveal(forecast, app); forecast.tap()
        XCTAssertTrue(app.navigationBars["Plan a workout"].waitForExistence(timeout: 10))
    }
    private func reveal(_ element: XCUIElement, _ app: XCUIApplication) {
        for _ in 0..<18 {
            if element.exists && element.isHittable { return }
            app.swipeUp()
        }
        XCTAssertTrue(element.exists, "Missing \(element)")
    }
    private func top(_ app: XCUIApplication) {
        for _ in 0..<15 {
            if app.buttons["runWorkoutDemo"].exists && app.buttons["runWorkoutDemo"].isHittable { return }
            app.swipeDown()
        }
    }
    private func type(_ value: String, field label: String, _ app: XCUIApplication) {
        let field = app.textFields[label]; reveal(field, app)
        field.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        if !app.keyboards.firstMatch.waitForExistence(timeout: 2) {
            field.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        }
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 2), label)
        field.typeText(value)
        XCTAssertEqual(field.value as? String, value, label)
    }
    private func done(_ app: XCUIApplication) { if app.buttons["Done"].exists { app.buttons["Done"].tap() } }
    private func attach(_ app: XCUIApplication, _ title: String) {
        let screenshot = XCTAttachment(screenshot: app.screenshot()); screenshot.name = title; screenshot.lifetime = .keepAlways; add(screenshot)
    }
}
