import XCTest

/// Opt-in: against a LOCAL mock backend (no live Wonder), with labelled sample Health workouts.
/// Walks Insights → Plan a workout → Use my last workout → estimate → the Wonder section, and never taps a
/// billable action: there is no "Explain this workout" button to tap on a mock backend, and the weather
/// lookup (Open-Meteo) is never started.
final class WorkoutFlowUITests: XCTestCase {
    func testLastWorkoutPrefillAndWonderSectionOnAMockBackend() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        guard let backend = environment["HYDRA_E2E_BACKEND_URL"],
              let token = environment["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires opt-in local synthetic-data backend")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token,
                                 "HYDRA_SAMPLE_HEALTH_WORKOUTS": "1"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()

        app.tabBars.buttons["Insights"].tap()
        let card = app.buttons["insightsWorkout"]
        reveal(card, in: app)
        card.tap()

        // Step 1: the last workout comes from the labelled sample Health data, read on device.
        let lastWorkout = app.buttons["useLastWorkout"]
        XCTAssertTrue(lastWorkout.waitForExistence(timeout: 10))
        reveal(lastWorkout, in: app)
        lastWorkout.tap()
        let provenance = app.staticTexts["workoutProvenance"]
        XCTAssertTrue(provenance.waitForExistence(timeout: 10))
        XCTAssertTrue(provenance.label.hasPrefix("Sample workout (not your data) on "), provenance.label)
        let heartRateNote = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@",
                                                                 "Heart rate is shown for context only")).firstMatch
        XCTAssertTrue(heartRateNote.waitForExistence(timeout: 5), "Heart rate is shown with its context-only note")
        XCTAssertTrue(app.staticTexts["Filled in the activity, duration and start time. Pick the intensity yourself."].exists)
        attach(app, "Use my last workout filled in from sample Health data")

        // Step 2: weather lookup is off until the user agrees; it is never started here.
        let weather = app.buttons["fillWeather"]
        reveal(weather, in: app)
        XCTAssertFalse(weather.isEnabled, "Fill in the weather needs location consent first")
        let consent = app.switches["weatherConsent"]
        XCTAssertTrue(consent.exists)
        XCTAssertEqual(consent.value as? String, "0", "Weather consent is off by default")
        type("22", into: "Temperature, °C", in: app)
        type("55", into: "Humidity, %", in: app)
        if app.buttons["Done"].exists { app.buttons["Done"].tap() }

        // Step 3: the estimate runs on the user's backend (not Meta), then Wonder shows what would be sent.
        let estimate = app.buttons["estimateWorkout"]
        reveal(estimate, in: app)
        estimate.tap()
        let insufficient = app.staticTexts["workoutInsufficientData"]
        let prediction = app.staticTexts["workoutPrediction"]
        XCTAssertTrue(insufficient.waitForExistence(timeout: 15) || prediction.exists)

        let analysis = app.staticTexts["hydrationAnalysisProvenance"]
        reveal(analysis, in: app, attempts: 10)
        XCTAssertTrue(analysis.label.contains("Research analysis"), analysis.label)
        let activity = app.buttons["hydrationAnalysis-activity"]
        reveal(activity, in: app)
        activity.tap()
        let localAnalysis = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Duration and activity describe the supplied workout")).firstMatch
        reveal(localAnalysis, in: app)
        XCTAssertTrue(localAnalysis.waitForExistence(timeout: 5))
        attach(app, "Deterministic research analysis separated from Muse Wonder")

        let richConsent = app.switches["richAnalysisBackendConsent"]
        reveal(richConsent, in: app, attempts: 10)
        XCTAssertEqual(richConsent.value as? String, "0")
        let prepare = app.buttons["prepareRichAnalysis"]
        XCTAssertFalse(prepare.isEnabled)
        richConsent.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        XCTAssertEqual(richConsent.value as? String, "1")
        prepare.tap()
        let richPreview = app.staticTexts["richAnalysisPreview"]
        reveal(richPreview, in: app, attempts: 10)
        XCTAssertTrue(richPreview.exists)
        attach(app, "Detailed Wonder aggregate preview with no live dispatch")
        let richUnavailable = app.staticTexts["richAnalysisUnavailable"]
        reveal(richUnavailable, in: app, attempts: 14)
        XCTAssertTrue(richUnavailable.label.contains("isn't enabled"), richUnavailable.label)
        XCTAssertFalse(app.buttons["explainRichAnalysis"].exists)
        XCTAssertFalse(app.switches["richAnalysisMetaConsent"].exists)
        XCTAssertTrue(app.staticTexts["richAnalysisReferenceCost"].label.contains("Reference cost estimate"))
        attach(app, "Reference price estimate and disabled detailed Wonder dispatch")

        let unavailable = app.staticTexts["workoutWonderUnavailable"]
        reveal(unavailable, in: app, attempts: 10)
        XCTAssertTrue(unavailable.label.contains("isn't set up on this backend"), unavailable.label)
        let preview = app.descendants(matching: .any).matching(identifier: "workoutWonderPreview").firstMatch
        XCTAssertTrue(preview.exists)
        XCTAssertTrue(app.staticTexts["What would be sent to Meta"].exists)
        XCTAssertFalse(app.buttons["workoutWonderExplain"].exists, "Nothing can be sent from a mock backend")
        XCTAssertFalse(app.switches["workoutWonderConsent"].exists)
        attach(app, "Wonder explains this workout on a mock backend")
    }

    /// Form rows below the fold are created lazily; scroll until the element is on screen.
    private func reveal(_ element: XCUIElement, in app: XCUIApplication, attempts: Int = 6) {
        for _ in 0..<attempts {
            if element.waitForExistence(timeout: 2), element.isHittable { return }
            app.swipeUp()
        }
        XCTAssertTrue(element.exists, "\(element) not found")
    }

    private func type(_ text: String, into label: String, in app: XCUIApplication) {
        if app.buttons["Done"].exists { app.buttons["Done"].tap() }
        let field = app.textFields[label]
        reveal(field, in: app)
        field.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 3))
        field.typeText(text)
    }

    private func attach(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
