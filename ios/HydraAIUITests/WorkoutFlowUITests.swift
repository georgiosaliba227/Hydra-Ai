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
        XCTAssertTrue(richUnavailable.label.contains("currently unavailable"), richUnavailable.label)
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

    func testExperimentalModelRequiresExplicitChoiceAndResetsItsReviewWhenSwitched() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        guard let backend = environment["HYDRA_E2E_BACKEND_URL"], let token = environment["HYDRA_E2E_API_TOKEN"], token.count >= 32 else {
            throw XCTSkip("Requires opt-in local synthetic-data backend")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": backend, "HYDRA_TEST_API_TOKEN": token, "HYDRA_SAMPLE_HEALTH_WORKOUTS": "1"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Insights"].tap()
        let card = app.buttons["insightsWorkout"]; reveal(card, in: app); card.tap()
        let model = app.switches["experimentalPersonalModel"]
        reveal(model, in: app)
        XCTAssertEqual(model.value as? String, "0", "The existing baseline stays the default")
        model.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        XCTAssertEqual(model.value as? String, "1")
        XCTAssertTrue(app.staticTexts["experimentalPersonalModelNotice"].label.contains("may perform worse"))
        let last = app.buttons["useLastWorkout"]; reveal(last, in: app); last.tap()
        XCTAssertTrue(app.staticTexts["workoutProvenance"].waitForExistence(timeout: 10))
        type("22", into: "Temperature, °C", in: app); type("55", into: "Humidity, %", in: app)
        if app.buttons["Done"].exists { app.buttons["Done"].tap() }
        let estimate = app.buttons["estimateWorkout"]; reveal(estimate, in: app); estimate.tap()
        let selection = app.staticTexts["runtimeLearningSelection"]
        reveal(selection, in: app, attempts: 10)
        XCTAssertEqual(selection.label, "Baseline retained", "Cold start is an honest v3 abstention/fallback")
        XCTAssertFalse(app.staticTexts["workoutWonderPlaceholder"].exists)
        attach(app, "Opt-in experimental runtime retains baseline without measurements")
        let consent = app.switches["richAnalysisBackendConsent"]; reveal(consent, in: app, attempts: 12)
        XCTAssertEqual(consent.value as? String, "0")
        let prepare = app.buttons["prepareRichAnalysis"]; XCTAssertFalse(prepare.isEnabled)
        consent.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap(); prepare.tap()
        let preview = app.staticTexts["richAnalysisPreview"]; reveal(preview, in: app, attempts: 10)
        XCTAssertTrue(preview.exists)
        let unavailable = app.staticTexts["richAnalysisUnavailable"]; reveal(unavailable, in: app, attempts: 14)
        XCTAssertTrue(unavailable.label.contains("currently unavailable"))
        XCTAssertFalse(app.buttons["explainRichAnalysis"].exists)
        XCTAssertFalse(app.switches["richAnalysisMetaConsent"].exists)
        attach(app, "V3 detailed preview is explicitly reviewed with live dispatch disabled")
        for _ in 0..<18 {
            if model.exists && model.isHittable { break }
            app.swipeDown()
        }
        XCTAssertTrue(model.isHittable)
        model.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        XCTAssertEqual(model.value as? String, "0")
        let calibrationConsent = app.switches["workoutCalibrationConsent"]; reveal(calibrationConsent, in: app)
        XCTAssertEqual(calibrationConsent.value as? String, "0")
        reveal(estimate, in: app)
        XCTAssertFalse(app.staticTexts["runtimeLearningSelection"].exists)
        XCTAssertFalse(app.staticTexts["richAnalysisPreview"].exists)
        XCTAssertFalse(app.switches["richAnalysisMetaConsent"].exists)
        attach(app, "Changing the model clears results and all review consent")
    }

    /// Requires an externally prepared Simulator profile containing only six invented manual sessions.
    /// This test never seeds production data or dispatches a provider request.
    func testSavedSyntheticMeasurementsFitPersonalRuntimeAgainstLocalBackend() throws {
        continueAfterFailure = false
        guard ProcessInfo.processInfo.environment["HYDRA_E2E_SAVED_CALIBRATION_RUNTIME"] == "1" else {
            throw XCTSkip("Requires explicit opt-in and an externally seeded synthetic Simulator history")
        }
        let app = XCUIApplication()
        app.launchEnvironment = ["HYDRA_TEST_BACKEND_URL": "http://127.0.0.1:19998",
                                 "HYDRA_TEST_API_TOKEN": "synthetic-calibration-ui-token-not-a-secret"]
        app.launch()
        addTeardownBlock { app.terminate() }
        XCTAssertTrue(app.tabBars.buttons["Settings"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Settings"].tap(); app.buttons["saveConnection"].tap()
        app.tabBars.buttons["Insights"].tap()
        let card = app.buttons["insightsWorkout"]; reveal(card, in: app); card.tap()

        let savedCount = app.descendants(matching: .any).matching(identifier: "savedCalibrationCount").firstMatch
        reveal(savedCount, in: app, attempts: 12)
        XCTAssertEqual(savedCount.value as? String, "6", "The test requires exactly six externally seeded invented records")
        workoutTop(in: app)
        let model = app.switches["experimentalPersonalModel"]; reveal(model, in: app)
        XCTAssertEqual(model.value as? String, "0")
        model.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        XCTAssertEqual(model.value as? String, "1")
        type("60", into: "Duration, min", in: app)
        type("22", into: "Temperature, °C", in: app)
        type("55", into: "Humidity, %", in: app)
        if app.buttons["Done"].exists { app.buttons["Done"].tap() }
        let conditions = app.switches["Conditions match my past measurements"]
        reveal(conditions, in: app)
        XCTAssertEqual(conditions.value as? String, "0")
        conditions.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        XCTAssertEqual(conditions.value as? String, "1")

        reveal(savedCount, in: app, attempts: 12)
        let localSaveConsent = app.switches["saveCalibrationConsent"]; reveal(localSaveConsent, in: app)
        XCTAssertEqual(localSaveConsent.value as? String, "0")
        let useSaved = app.buttons["useSavedCalibration"]; reveal(useSaved, in: app); useSaved.tap()
        workoutTop(in: app)
        let sessionCount = app.descendants(matching: .any).matching(identifier: "sessionCalibrationCount").firstMatch
        reveal(sessionCount, in: app)
        XCTAssertEqual(sessionCount.value as? String, "6")
        let processingConsent = app.switches["workoutCalibrationConsent"]
        reveal(processingConsent, in: app)
        XCTAssertEqual(processingConsent.value as? String, "0", "Loading saved records cannot restore processing consent")
        processingConsent.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        XCTAssertEqual(processingConsent.value as? String, "1")
        let estimate = app.buttons["estimateWorkout"]; reveal(estimate, in: app, attempts: 14)
        XCTAssertTrue(estimate.isEnabled); estimate.tap()

        let selection = app.staticTexts["runtimeLearningSelection"]; reveal(selection, in: app, attempts: 10)
        XCTAssertEqual(selection.label, "Experimental personal fit selected")
        let prediction = app.staticTexts["workoutPrediction"]
        XCTAssertTrue(prediction.label.contains("442 mL"), prediction.label)
        let range = app.staticTexts["workoutPredictionRange"]
        XCTAssertTrue(range.label.contains("280–700 mL"), range.label)
        XCTAssertFalse(app.staticTexts["workoutWonderPlaceholder"].exists)
        attach(app, "Saved synthetic manual history selects the personal runtime fit")

        let analysis = app.staticTexts["hydrationAnalysisProvenance"]; reveal(analysis, in: app, attempts: 10)
        XCTAssertTrue(analysis.label.contains("Research analysis"))
        let loss = app.buttons["hydrationAnalysis-workout_loss"]; reveal(loss, in: app); loss.tap()
        let facts = app.buttons["Facts and provenance"]; reveal(facts, in: app); facts.tap()
        for amount in ["280 mL", "700 mL", "442 mL"] {
            let fact = app.staticTexts.matching(NSPredicate(format: "label == %@", amount)).firstMatch
            reveal(fact, in: app, attempts: 8)
            XCTAssertTrue(fact.exists, "The local analysis must retain the forecast's numerical values")
        }
        attach(app, "Local analysis agrees with selected runtime point and envelope")

        let summaryConsent = app.switches["richAnalysisBackendConsent"]; reveal(summaryConsent, in: app, attempts: 14)
        XCTAssertEqual(summaryConsent.value as? String, "0")
        let prepare = app.buttons["prepareRichAnalysis"]; XCTAssertFalse(prepare.isEnabled)
        summaryConsent.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap(); prepare.tap()
        let preview = app.staticTexts["richAnalysisPreview"]; reveal(preview, in: app, attempts: 10)
        XCTAssertTrue(preview.exists)
        let previewNumbers = app.staticTexts.matching(NSPredicate(format: "identifier == %@ AND label CONTAINS %@",
            "richAnalysisFacts-forecast", "Value Ml: 442 mL")).firstMatch
        reveal(previewNumbers, in: app)
        XCTAssertTrue(previewNumbers.label.contains("Lower Ml: 280 mL"), previewNumbers.label)
        XCTAssertTrue(previewNumbers.label.contains("Upper Ml: 700 mL"), previewNumbers.label)
        attach(app, "Selected personal runtime numbers bound to the detailed preview")
        let unavailable = app.staticTexts["richAnalysisUnavailable"]; reveal(unavailable, in: app, attempts: 16)
        XCTAssertTrue(unavailable.label.contains("currently unavailable"))
        XCTAssertFalse(app.buttons["explainRichAnalysis"].exists)
        XCTAssertFalse(app.switches["richAnalysisMetaConsent"].exists)
        attach(app, "Selected runtime preview has no live Meta action")

        workoutTop(in: app)
        let deleteAll = app.buttons["deleteAllCalibrationHistory"]; reveal(deleteAll, in: app, attempts: 16); deleteAll.tap()
        let confirm = app.buttons.matching(NSPredicate(format: "label == %@", "Delete all saved manual measurements"))
            .allElementsBoundByIndex.first { $0.isHittable }
        try XCTUnwrap(confirm).tap()
        workoutTop(in: app); reveal(savedCount, in: app, attempts: 12)
        XCTAssertEqual(savedCount.value as? String, "0", "Remove the seeded synthetic history when finished")
        XCTAssertFalse(app.staticTexts["runtimeLearningSelection"].exists)
        attach(app, "Selected-fit synthetic history deleted after verification")
    }

    private func workoutTop(in app: XCUIApplication) {
        for _ in 0..<20 {
            if app.buttons["runWorkoutDemo"].exists && app.buttons["runWorkoutDemo"].isHittable { return }
            app.swipeDown()
        }
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
