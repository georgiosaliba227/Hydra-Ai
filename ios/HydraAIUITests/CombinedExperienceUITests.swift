import XCTest

/// Requires an explicit disposable loopback fixture: fake local model and fake Wonder transport.
final class CombinedExperienceUITests: XCTestCase {
    private func start() throws -> XCUIApplication {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard env["HYDRA_E2E_COMBINED"] == "1", let backend = env["HYDRA_E2E_BACKEND_URL"],
              backend.hasPrefix("http://127.0.0.1:"), let token = env["HYDRA_E2E_API_TOKEN"] else {
            throw XCTSkip("Requires disposable combined-backend fixture, never the owner backend")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token,
            "HYDRA_TEST_UNIT_SYSTEM": "us", "HYDRA_TEST_CONTEXT_SETUP": "skip",
            "HYDRA_TEST_CONTEXT_SUITE": "HydraUITests.Combined.\(UUID().uuidString)", "HYDRA_TEST_PHOTO_FIXTURE": "1"]
        app.launch(); addTeardownBlock {
            self.screenshot(app, "Combined synthetic fixture at teardown")
            app.terminate()
        }
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        return app
    }

    func testUSLocalCameraReviewKeepsExactLabelAndConfirmEdit() throws {
        let app = try start()
        app.tabBars.buttons["Camera"].tap()
        let photo = app.buttons["syntheticPhoto"]
        XCTAssertTrue(photo.waitForExistence(timeout: 10)); photo.tap()
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "trained")).firstMatch.exists)
        let consent = app.switches["photoConsent"]; app.revealFormElement(consent)
        consent.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        XCTAssertFalse(app.switches["metaPhotoConsent"].exists)
        let analyze = app.buttons["analyzePhoto"]; app.revealFormElement(analyze); analyze.tap()
        let amount = app.staticTexts["photoVolume"]
        XCTAssertTrue(amount.waitForExistence(timeout: 15))
        XCTAssertEqual(amount.label, "33.8 fl oz")
        XCTAssertEqual(app.staticTexts["photoLabelCapacity"].label, "Printed size: 33.8 fl oz")
        XCTAssertFalse(app.textFields["photoConsumed"].exists)
        app.buttons["editRecognitionEntry"].tap()
        XCTAssertTrue(app.segmentedControls["photoVolumeUnit"].buttons["US fl oz"].isSelected)
        let preset = app.buttons["volumePreset-355"]; app.revealFormElement(preset); preset.tap()
        XCTAssertEqual(amount.label, "12 fl oz")
        XCTAssertTrue(app.segmentedControls["photoVolumeUnit"].buttons["US fl oz"].isSelected)
        let whole = app.buttons["useFullContainer"]; revealCameraControl(whole, app: app)
        XCTAssertEqual(whole.label, "Use full 33.8 fl oz container")
        screenshot(app, "Whole-container action above the sticky confirmation bar")
        print("Synthetic camera button frames: whole=\(whole.frame), confirm=\(app.buttons["savePhotoBeverage"].frame)")
        whole.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        for _ in 0..<8 where !amount.isHittable { app.swipeDown() }
        XCTAssertEqual(amount.label, "33.8 fl oz")
        XCTAssertTrue(app.segmentedControls["photoVolumeUnit"].buttons["US fl oz"].isSelected)
        let date = app.datePickers["photoConsumedAt"]; revealCameraControl(date, app: app)
        XCTAssertTrue(date.exists)
        screenshot(app, "Combined local-camera review in US units; exact one-litre fixture")
        app.buttons["savePhotoBeverage"].tap()
        XCTAssertTrue(photo.waitForExistence(timeout: 15))
        app.tabBars.buttons["Today"].tap()
        let total = app.descendants(matching: .any).matching(identifier: "dailyTotal").firstMatch
        XCTAssertTrue(total.waitForExistence(timeout: 15))
        expectation(for: NSPredicate(format: "value == %@", "33.8 fl oz"), evaluatedWith: total)
        waitForExpectations(timeout: 15)
        app.tabBars.buttons["History"].tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(
            format: "identifier == 'beverageRow' AND label CONTAINS %@", "Assumed full container consumed")).firstMatch.waitForExistence(timeout: 10))
    }

    func testColdStartStillOffersConsentedDetailedWonderAndFreeReplay() throws {
        let app = try start()
        app.tabBars.buttons["Insights"].tap()
        let workout = app.buttons["insightsWorkout"]; app.revealFormElement(workout); workout.tap()
        let experimental = app.switches["experimentalPersonalModel"]
        XCTAssertTrue(experimental.waitForExistence(timeout: 10))
        XCTAssertEqual(experimental.value as? String, "0")
        type("60", into: "Duration, min", app: app)
        type("68", into: "Temperature", app: app)
        type("50", into: "Humidity, %", app: app)
        let estimate = app.buttons["estimateWorkout"]; app.revealFormElement(estimate); estimate.tap()
        let insufficient = app.staticTexts["workoutInsufficientData"]
        XCTAssertTrue(insufficient.waitForExistence(timeout: 15))
        let backendConsent = app.switches["richAnalysisBackendConsent"]; app.revealFormElement(backendConsent)
        XCTAssertEqual(backendConsent.value as? String, "0")
        let preview = app.buttons["prepareRichAnalysis"]; XCTAssertFalse(preview.isEnabled)
        backendConsent.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        preview.tap()
        let facts = app.staticTexts["richAnalysisPreview"]; app.revealFormElement(facts)
        XCTAssertTrue(facts.waitForExistence(timeout: 15))
        let metaConsent = app.switches["richAnalysisMetaConsent"]; app.revealFormElement(metaConsent)
        XCTAssertEqual(metaConsent.value as? String, "0")
        let explain = app.buttons["explainRichAnalysis"]; XCTAssertFalse(explain.isEnabled)
        metaConsent.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        explain.tap()
        let result = app.staticTexts["richAnalysisResult"]; revealAbove(result, app: app)
        XCTAssertTrue(result.waitForExistence(timeout: 15))
        XCTAssertTrue(result.label.contains("Hydra calculated every number"))
        for id in ["summary", "workout_loss", "activity", "environment", "beverages", "trends", "uncertainty", "measurement"] {
            let section = app.descendants(matching: .any).matching(identifier: "richAnalysisResult-\(id)").firstMatch
            app.revealFormElement(section)
            XCTAssertTrue(section.exists, id)
        }
        screenshot(app, "Combined backend: eight grounded sections despite numerical cold start")
        revealAbove(backendConsent, app: app)
        backendConsent.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        preview.tap()
        app.revealFormElement(result)
        expectation(for: NSPredicate(format: "label CONTAINS %@", "Showing the saved analysis"), evaluatedWith: result)
        waitForExpectations(timeout: 15)
        XCTAssertFalse(app.buttons["explainRichAnalysis"].exists)
        screenshot(app, "Combined backend saved replay without another fake provider dispatch")
    }

    private func type(_ text: String, into label: String, app: XCUIApplication) {
        let field = app.textFields[label]; app.revealFormElement(field)
        field.tap(); field.typeText(text)
        if app.buttons["Done"].exists { app.buttons["Done"].tap() }
    }

    private func revealCameraControl(_ control: XCUIElement, app: XCUIApplication) {
        for _ in 0..<12 {
            if control.exists && control.isHittable && control.frame.maxY < app.buttons["savePhotoBeverage"].frame.minY - 8 { return }
            app.swipeUp()
        }
        XCTFail("Camera editor control must be above the sticky confirmation bar")
    }

    private func revealAbove(_ control: XCUIElement, app: XCUIApplication) {
        for _ in 0..<18 {
            if control.exists && control.isHittable { return }
            app.swipeDown()
        }
        XCTAssertTrue(control.isHittable)
    }

    private func screenshot(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
