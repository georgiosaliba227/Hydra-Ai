import XCTest

/// Invented profile answers run only in a simulator with an isolated profile suite.
/// No server, provider, Apple Health access or real profile is used.
final class GuidedDeviceGoalUITests: XCTestCase {
    func testAdultStartingReferenceConfirmsLocallyAndRestoresProfileAfterRestart() throws {
        let app = try launch()
        XCTAssertTrue(app.staticTexts["guidedGoalTitle"].waitForExistence(timeout: 15))
        chooseAge("30", app)
        choose("Men (published reference)", picker: "profileReferenceGroup", app)
        choose("General adult reference applies", picker: "profileEligibility", app)
        type("175", into: "profileHeightCm", app)
        type("70", into: "profileWeight", app)
        done(app)
        let creatine = app.switches["profileCreatine"]; reveal(creatine, app)
        creatine.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        let calculate = app.buttons["calculateGoalReference"]; reveal(calculate, app); calculate.tap()
        let reference = app.staticTexts["goalStartingReference"]; reveal(reference, app)
        XCTAssertTrue(reference.label.contains("3000 mL"), reference.label)
        let context = app.staticTexts["goalReferenceContext"]; reveal(context, app)
        XCTAssertTrue(context.label.contains("no numerical adjustment"), context.label)
        let destination = app.staticTexts["goalConfirmationDestination"]; reveal(destination, app)
        XCTAssertTrue(destination.label.contains("only on this iPhone"), destination.label)
        let confirm = app.buttons["useGoalReference"]; reveal(confirm, app)
        XCTAssertTrue(confirm.isEnabled); confirm.tap()
        waitForSetupDismissal(app)
        app.tabBars.buttons["Today"].tap()
        app.buttons["quickAdd-water-500"].tap()
        let progress = app.descendants(matching: .any).matching(identifier: "goalProgress").firstMatch
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS '17%'"), object: progress)], timeout: 10), .completed)
        let proof = XCTAttachment(screenshot: app.screenshot()); proof.name = "Confirmed reference drives water progress"; proof.lifetime = .keepAlways; add(proof)
        openSettingsSetup(app)
        XCTAssertEqual(app.textFields["profileAgeYears"].value as? String, "30")
        let height = app.textFields["profileHeightCm"]; reveal(height, app)
        XCTAssertEqual(height.value as? String, "175")
        app.terminate(); app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        openSettingsSetup(app)
        XCTAssertEqual(app.textFields["profileAgeYears"].value as? String, "30")
    }

    func testUnder19ReferenceIsUnavailableButCustomGoalNeedsNoSavedProfile() throws {
        let app = try launch()
        XCTAssertTrue(app.staticTexts["guidedGoalTitle"].waitForExistence(timeout: 15))
        chooseAge("18", app)
        choose("Women (published reference)", picker: "profileReferenceGroup", app)
        choose("General adult reference applies", picker: "profileEligibility", app)
        let calculate = app.buttons["calculateGoalReference"]; reveal(calculate, app); calculate.tap()
        let unavailable = app.staticTexts["goalReferenceUnavailable"]; reveal(unavailable, app)
        XCTAssertTrue(unavailable.label.contains("19 or older"), unavailable.label)
        XCTAssertFalse(app.buttons["useGoalReference"].exists)
        let custom = app.buttons["guidedCustomAlternative"]; reveal(custom, app); custom.tap()
        type("1500", into: "guidedCustomGoal", app)
        done(app)
        let confirm = app.buttons["guidedConfirmCustomGoal"]; reveal(confirm, app)
        XCTAssertTrue(confirm.isEnabled); confirm.tap()
        waitForSetupDismissal(app)
        openSettingsSetup(app)
        // Custom confirmation did not persist the unconfirmed age/group answers.
        XCTAssertTrue(app.textFields["profileBirthday"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.textFields["profileAgeYears"].exists)
    }

    private func launch() throws -> XCUIApplication {
        #if !targetEnvironment(simulator)
        throw XCTSkip("Synthetic goal setup is restricted to simulator verification")
        #else
        continueAfterFailure = false
        let app = XCUIApplication(), suite = "HydraUITests.Goal.\(UUID().uuidString)"
        app.launchEnvironment = ["HYDRA_TEST_ON_DEVICE": "1", "HYDRA_TEST_UNIT_SYSTEM": "metric",
            "HYDRA_TEST_CONTEXT_SETUP": "skip", "HYDRA_TEST_CONTEXT_SUITE": suite,
            "HYDRA_TEST_GOAL_PROFILE_SUITE": suite]
        app.launch(); addTeardownBlock { app.terminate() }
        return app
        #endif
    }
    private func chooseAge(_ age: String, _ app: XCUIApplication) {
        let method = app.segmentedControls["profileAgeMethod"]; reveal(method, app)
        method.buttons["Age only"].tap()
        type(age, into: "profileAgeYears", app)
    }
    private func choose(_ label: String, picker: String, _ app: XCUIApplication) {
        done(app)
        let control = app.buttons[picker]; reveal(control, app); control.tap()
        app.buttons[label].tap()
    }
    private func type(_ value: String, into identifier: String, _ app: XCUIApplication) {
        done(app)
        let field = app.textFields[identifier]; reveal(field, app); field.tap(); field.typeText(value)
    }
    private func done(_ app: XCUIApplication) {
        let button = app.toolbars.buttons["Done"].firstMatch
        if button.exists { button.tap() }
    }
    private func reveal(_ element: XCUIElement, _ app: XCUIApplication) {
        for _ in 0..<10 {
            if element.exists && element.isHittable { return }
            app.swipeUp()
        }
        for _ in 0..<10 {
            if element.exists && element.isHittable { return }
            app.swipeDown()
        }
        XCTAssertTrue(element.exists && element.isHittable, "Missing form control: \(element.identifier)")
    }
    private func waitForSetupDismissal(_ app: XCUIApplication) {
        expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: app.staticTexts["guidedGoalTitle"])
        waitForExpectations(timeout: 10)
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 10))
    }
    private func openSettingsSetup(_ app: XCUIApplication) {
        app.tabBars.buttons["Settings"].tap()
        let setup = app.buttons["guidedGoalSetup"]; reveal(setup, app); setup.tap()
        XCTAssertTrue(app.staticTexts["guidedGoalTitle"].waitForExistence(timeout: 8))
    }
}
