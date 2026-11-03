import XCTest

/// Explicitly opted-in Simulator check against a staged, financially blocked backend.
/// Uses labeled sample workout context; no history is saved and no Meta action is tapped.
final class WonderReadinessUITests: XCTestCase {
    /// Owner-assisted physical follow-up after setup. No connection overrides or
    /// Save action: the GET must authenticate using the URL and Keychain already saved.
    func testSavedOwnerConnectionReportsReadinessWithoutInjectedCredentials() throws {
        continueAfterFailure = false
        guard ProcessInfo.processInfo.environment["HYDRA_E2E_SAVED_WONDER_READY"] == "1" else {
            throw XCTSkip("Requires an explicitly activated owner backend and completed on-device setup")
        }
        let app = XCUIApplication()
        app.launchEnvironment = [:]
        app.launch(); addTeardownBlock { app.terminate() }
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 12))
        app.tabBars.buttons["Settings"].tap()
        let check = app.buttons["checkWonderReadiness"]; reveal(check, in: app, attempts: 18); check.tap()
        let status = app.staticTexts["wonderReadinessStatus"]
        XCTAssertTrue(status.waitForExistence(timeout: 15))
        XCTAssertEqual(status.label, "Ready for a previewed, consented request")
        let risk = app.staticTexts["wonderReadinessRisk"]; reveal(risk, in: app)
        XCTAssertTrue(risk.label.contains("final billing remain unverified"))
        // No screenshot or personal values collected; no paid control is tapped.
    }

    func testReadyOwnerRiskStatusStillDisclosesUnverifiedBillingWithoutDispatch() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard env["HYDRA_E2E_WONDER_READY"] == "1",
              let backend = env["HYDRA_E2E_BACKEND_URL"], let token = env["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires the explicitly activated owner-risk local backend; GET-only verification")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token]
        app.launchHydra(); addTeardownBlock { app.terminate() }
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        let check = app.buttons["checkWonderReadiness"]; reveal(check, in: app); check.tap()
        let status = app.staticTexts["wonderReadinessStatus"]
        XCTAssertTrue(status.waitForExistence(timeout: 15))
        XCTAssertEqual(status.label, "Ready for a previewed, consented request")
        let risk = app.staticTexts["wonderReadinessRisk"]; reveal(risk, in: app)
        XCTAssertTrue(risk.label.contains("final billing remain unverified"))
        XCTAssertTrue(risk.label.contains("tokens only"))
        attach(app, "Actual owner-risk backend is ready with unverified billing disclosed")
        app.tabBars.buttons["Today"].tap()
        let goal = app.staticTexts["hydrationScoreGoalRequired"]; reveal(goal, in: app)
        XCTAssertTrue(goal.label.contains("your own"))
        XCTAssertFalse(app.buttons["explainHydrationScore"].exists)
    }

    func testBlockedReadinessAndPersonalPreviewOfferNoPaidAction() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard env["HYDRA_E2E_WONDER_BLOCKED_READINESS"] == "1",
              let backend = env["HYDRA_E2E_BACKEND_URL"], let token = env["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires an explicitly staged blocked backend and synthetic Simulator context")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token,
                                 "HYDRA_SAMPLE_HEALTH_WORKOUTS": "1"]
        app.launchHydra()
        addTeardownBlock { app.terminate() }
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        let check = app.buttons["checkWonderReadiness"]; reveal(check, in: app); check.tap()
        let status = app.staticTexts["wonderReadinessStatus"]
        XCTAssertTrue(status.waitForExistence(timeout: 15))
        XCTAssertEqual(status.label, "Live Wonder is currently blocked")
        let finality = app.staticTexts["wonderReadinessReason-current_invoice_finality_required"]
        reveal(finality, in: app)
        XCTAssertEqual(finality.label, "Final billing for a recent request still needs confirmation.")
        let risk = app.staticTexts["wonderReadinessRisk"]; reveal(risk, in: app)
        XCTAssertTrue(risk.label.contains("remain unverified"))
        attach(app, "Actual backend reports blocked financial readiness")

        app.tabBars.buttons["Insights"].tap()
        let workout = app.buttons["insightsWorkout"]; reveal(workout, in: app); workout.tap()
        let last = app.buttons["useLastWorkout"]; reveal(last, in: app); last.tap()
        let provenance = app.staticTexts["workoutProvenance"]
        XCTAssertTrue(provenance.waitForExistence(timeout: 10))
        XCTAssertTrue(provenance.label.hasPrefix("Sample workout (not your data) on "))
        fill("22", field: "Temperature", in: app); fill("55", field: "Humidity, %", in: app)
        if app.buttons["Done"].exists { app.buttons["Done"].tap() }
        let estimate = app.buttons["estimateWorkout"]; reveal(estimate, in: app); estimate.tap()
        let analysis = app.staticTexts["hydrationAnalysisProvenance"]; reveal(analysis, in: app, attempts: 14)
        XCTAssertTrue(analysis.waitForExistence(timeout: 15))
        let consent = app.switches["richAnalysisBackendConsent"]; reveal(consent, in: app, attempts: 12)
        XCTAssertEqual(consent.value as? String, "0")
        let preview = app.buttons["prepareRichAnalysis"]; XCTAssertFalse(preview.isEnabled)
        consent.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap(); preview.tap()
        let facts = app.staticTexts["richAnalysisPreview"]; reveal(facts, in: app, attempts: 14)
        XCTAssertTrue(facts.waitForExistence(timeout: 15))
        let unavailable = app.staticTexts["richAnalysisUnavailable"]; reveal(unavailable, in: app, attempts: 16)
        XCTAssertTrue(unavailable.label.contains("Check live Wonder availability in Settings"))
        XCTAssertFalse(app.buttons["explainRichAnalysis"].exists)
        XCTAssertFalse(app.switches["richAnalysisMetaConsent"].exists)
        attach(app, "Blocked personal preview retains exact facts without a paid action")
    }
    private func reveal(_ element: XCUIElement, in app: XCUIApplication, attempts: Int = 10) {
        for _ in 0..<attempts where !element.isHittable { app.swipeUp() }
        XCTAssertTrue(element.isHittable)
    }
    private func fill(_ value: String, field name: String, in app: XCUIApplication) {
        // A previous row's keyboard toolbar can cover the next trailing input.
        // Match the working workout-flow helper: dismiss, reveal, tap its value.
        if app.buttons["Done"].exists { app.buttons["Done"].tap() }
        let field = app.textFields[name]; reveal(field, in: app)
        field.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 3))
        if let existing = field.value as? String, existing != name {
            field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: existing.count))
        }
        field.typeText(value)
    }
    private func attach(_ app: XCUIApplication, _ name: String) {
        let item = XCTAttachment(screenshot: app.screenshot()); item.name = name; item.lifetime = .keepAlways; add(item)
    }
}
