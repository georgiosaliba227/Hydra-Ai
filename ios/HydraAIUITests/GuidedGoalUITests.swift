import XCTest

/// Explicit synthetic profile + disposable backend. Never fill a real profile from tests.
final class GuidedGoalUITests: XCTestCase {
    func testRequestedProfileQuestionsCalculateAndConfirmAdultBeverageReference() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard env["HYDRA_E2E_GUIDED_GOAL"] == "1", let backend = env["HYDRA_E2E_BACKEND_URL"],
              let token = env["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires an explicitly activated synthetic profile and local mock backend")
        }
        let app = XCUIApplication(), suite = "HydraUITests.Goal.\(UUID().uuidString)"
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token,
            "HYDRA_TEST_UNIT_SYSTEM": "us", "HYDRA_TEST_CONTEXT_SETUP": "skip",
            "HYDRA_TEST_CONTEXT_SUITE": suite, "HYDRA_TEST_GOAL_PROFILE_SUITE": suite]
        app.launch(); addTeardownBlock { app.terminate() }
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 10))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        let setup = app.buttons["guidedGoalSetup"]; reveal(setup, app); setup.tap()
        XCTAssertTrue(app.staticTexts["guidedGoalTitle"].waitForExistence(timeout: 8))
        type("01/15/1996", into: "profileBirthday", app: app)
        choose("Men (published reference)", picker: "profileReferenceGroup", app: app)
        choose("General adult reference applies", picker: "profileEligibility", app: app)
        type("5", into: "profileHeightFeet", app: app)
        type("11", into: "profileHeightInches", app: app)
        type("180", into: "profileWeight", app: app)
        done(app)
        let creatine = app.switches["profileCreatine"]; reveal(creatine, app)
        creatine.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        let calculate = app.buttons["calculateGoalReference"]; reveal(calculate, app); calculate.tap()
        let reference = app.staticTexts["goalStartingReference"]; reveal(reference, app)
        XCTAssertTrue(reference.label.contains("101.4")); XCTAssertTrue(reference.label.contains("fl oz"))
        let context = app.staticTexts["goalReferenceContext"]; reveal(context, app)
        XCTAssertTrue(context.label.contains("no numerical adjustment"))
        let apply = app.buttons["useGoalReference"]; reveal(apply, app); apply.tap()
        let status = app.staticTexts["goalApplyStatus"]
        reveal(status, app)
        XCTAssertTrue(status.waitForExistence(timeout: 10))
        expectation(for: NSPredicate(format: "label CONTAINS %@", "Goal confirmed"), evaluatedWith: status)
        waitForExpectations(timeout: 10)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Published adult reference from invented profile; no body or creatine coefficient"
        screenshot.lifetime = .keepAlways; add(screenshot)
        app.tabBars.buttons["Today"].tap()
        let score = app.descendants(matching: .any).matching(identifier: "hydrationScoreValue").firstMatch
        XCTAssertTrue(score.waitForExistence(timeout: 10))
        app.terminate(); app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 10))
        app.tabBars.buttons["Settings"].tap()
        reveal(setup, app); setup.tap()
        XCTAssertTrue(app.textFields["profileBirthday"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.textFields["profileBirthday"].value as? String, "01/15/1996")
    }

    func testOfflineGuidedCalculationDoesNotOfferStorageOrBackendConfirmation() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard env["HYDRA_E2E_GUIDED_GOAL"] == "1", let backend = env["HYDRA_E2E_BACKEND_URL"],
              let token = env["HYDRA_E2E_API_TOKEN"] else { throw XCTSkip("Requires disposable profile fixture") }
        let app = XCUIApplication(), suite = "HydraUITests.Goal.\(UUID().uuidString)"
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token,
            "HYDRA_TEST_UNIT_SYSTEM": "us", "HYDRA_TEST_CONTEXT_SETUP": "skip",
            "HYDRA_TEST_CONTEXT_SUITE": suite, "HYDRA_TEST_GOAL_PROFILE_SUITE": suite]
        app.launch(); addTeardownBlock { app.terminate() }
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 10))
        app.tabBars.buttons["Settings"].tap()
        let offline = app.switches["offlineMode"]
        offline.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        XCTAssertEqual(offline.value as? String, "1")
        app.buttons["saveConnection"].tap()
        XCTAssertTrue(app.staticTexts["Offline demo"].waitForExistence(timeout: 5))
        let setup = app.buttons["guidedGoalSetup"]; reveal(setup, app); setup.tap()
        app.segmentedControls["profileAgeMethod"].buttons["Age only"].tap()
        type("30", into: "profileAgeYears", app: app)
        choose("Women (published reference)", picker: "profileReferenceGroup", app: app)
        choose("General adult reference applies", picker: "profileEligibility", app: app)
        let calculate = app.buttons["calculateGoalReference"]; reveal(calculate, app); calculate.tap()
        let reference = app.staticTexts["goalStartingReference"]; reveal(reference, app)
        XCTAssertTrue(reference.label.contains("74.4"))
        let confirm = app.buttons["useGoalReference"]; reveal(confirm, app); XCTAssertFalse(confirm.isEnabled)
        let save = app.buttons["saveGoalProfileOnly"]; reveal(save, app); XCTAssertFalse(save.isEnabled)
    }

    private func choose(_ label: String, picker: String, app: XCUIApplication) {
        done(app)
        let control = app.buttons[picker]; reveal(control, app); control.tap()
        app.buttons[label].tap()
    }
    private func type(_ value: String, into id: String, app: XCUIApplication) {
        done(app)
        let field = app.textFields[id]; reveal(field, app); field.tap(); field.typeText(value)
    }
    private func done(_ app: XCUIApplication) { if app.buttons["Done"].exists { app.buttons["Done"].tap() } }
    private func reveal(_ element: XCUIElement, _ app: XCUIApplication) {
        app.revealFormElement(element)
    }
}
